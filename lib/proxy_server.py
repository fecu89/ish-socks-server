""" General base class for proxies """

from __future__ import annotations

import asyncio
import random
import socket
import time
from asyncio.staggered import staggered_race
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Sequence, Type, Optional

from . import status

SocketAddress = tuple[str, int]
Connection = tuple[asyncio.StreamReader, asyncio.StreamWriter]


def af_by_address(domain: str) -> int | None:
    try:
        socket.inet_pton(socket.AF_INET, domain)
        return socket.AF_INET
    except Exception:
        pass

    try:
        socket.inet_pton(socket.AF_INET6, domain)
        return socket.AF_INET6
    except Exception:
        return None


@dataclass
class GenericAddress:
    ipv4: SocketAddress | None = None
    ipv6: SocketAddress | None = None


HAPPY_EYEBALLS_DELAY = 0.05  # seconds
CONNECT_TIMEOUT = 75  # seconds
# Clients (e.g. browser preconnects) may open a connection and never send a request
HANDSHAKE_TIMEOUT = 60  # seconds
DNS_CACHE_TTL = 60  # seconds; getaddrinfo doesn't report record TTLs
DNS_CACHE_MAX_ENTRIES = 1024


async def forwarder_loop(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    stat_fn: Callable[[int], None],
    activity_fn: Callable[[], None] | None = None,
) -> None:
    try:
        while 1:
            buf = await reader.read(65536)
            if not buf:
                break
            stat_fn(len(buf))
            if activity_fn is not None:
                activity_fn()
            writer.write(buf)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


class IdleTracker:
    """Closes a forwarded connection once neither direction has carried data for a while."""

    def __init__(self) -> None:
        self.last_activity = time.monotonic()

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    async def watch(
        self, timeout: float, writers: Sequence[asyncio.StreamWriter]
    ) -> None:
        while True:
            remaining = self.last_activity + timeout - time.monotonic()
            if remaining <= 0:
                # Closing the transports makes both forwarder loops see EOF and exit
                for writer in writers:
                    writer.close()
                return
            await asyncio.sleep(remaining)


# XXX: should make this a more generic address type enum and convert from socks5
class Socks5AddressType(IntEnum):
    IPV4 = 1
    DOMAIN = 3
    IPV6 = 4


class CustomSourceAddressResolver:
    def __init__(self, resolver: "dns.asyncresolver.Resolver", connect_host_ipv4: str | None, connect_host_ipv6: str | None):
        self.resolver = resolver
        self.resolver_source: str | None = None
        if connect_host_ipv4 is not None or connect_host_ipv6 is not None:
            resolvers_by_af: dict[int, list[str]] = {socket.AF_INET: [], socket.AF_INET6: []}
            for ns in self.resolver.nameservers:
                resolvers_by_af[af_by_address(ns)].append(ns)

            if resolvers_by_af[socket.AF_INET] and connect_host_ipv4 is not None:
                self.resolver_source = connect_host_ipv4
                self.resolver.nameservers = resolvers_by_af[socket.AF_INET]
            elif resolvers_by_af[socket.AF_INET6] and connect_host_ipv6 is not None:
                self.resolver_source = connect_host_ipv6
                self.resolver.nameservers = resolvers_by_af[socket.AF_INET6]
            else:
                raise Exception("Resolver does not have any suitable nameservers!")

    async def resolve_ipv4(self, domain):
        answer = await self.resolver.resolve(
            domain, "A", source=self.resolver_source
        )
        return [rr.address for rr in answer]

    async def resolve_ipv6(self, domain):
        answer = await self.resolver.resolve(
            domain, "AAAA", source=self.resolver_source
        )
        return [rr.address for rr in answer]


class DefaultAddressResolver:
    """System resolver with a short-lived cache.

    Some libcs (e.g. musl on iSH) don't cache lookups, and browsers open many
    connections to the same host at once, so concurrent lookups share one query.
    """

    def __init__(
        self,
        cache_ttl: float = DNS_CACHE_TTL,
        max_entries: int = DNS_CACHE_MAX_ENTRIES,
    ):
        self.cache_ttl = cache_ttl
        self.max_entries = max_entries
        self._cache: dict[tuple[int, str], tuple[float, asyncio.Future]] = {}

    async def _resolve(self, addr: str, family: int) -> list[str]:
        loop = asyncio.get_running_loop()
        now = loop.time()
        key = (family, addr)
        entry = self._cache.get(key)
        if entry is None or entry[0] < now:
            if len(self._cache) >= self.max_entries:
                self._cache = {k: v for k, v in self._cache.items() if v[0] >= now}
                if len(self._cache) >= self.max_entries:
                    self._cache.clear()
            future = asyncio.ensure_future(
                loop.getaddrinfo(addr, None, family=family)
            )
            future.add_done_callback(lambda f: self._forget_failure(key, f))
            entry = (now + self.cache_ttl, future)
            self._cache[key] = entry
        # shield: one cancelled caller (e.g. losing a happy-eyeballs race)
        # must not cancel the lookup other callers are sharing
        info = await asyncio.shield(entry[1])
        return list({item[4][0] for item in info})

    def _forget_failure(self, key: tuple[int, str], future: asyncio.Future) -> None:
        # retrieving the exception also silences "exception was never retrieved"
        if future.cancelled() or future.exception() is not None:
            entry = self._cache.get(key)
            if entry is not None and entry[1] is future:
                del self._cache[key]

    async def resolve_ipv4(self, addr):
        return await self._resolve(addr, socket.AF_INET)

    async def resolve_ipv6(self, addr):
        return await self._resolve(addr, socket.AF_INET6)


class AsyncProxyHandler:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: "AsyncProxyServer",
    ):
        self.reader = reader
        self.writer = writer
        self.server = server

        peer_addr = writer.get_extra_info("peername")
        if peer_addr is None:
            self.log_tag = "<unknown>"
        elif len(peer_addr) == 2:
            # IPv4
            self.log_tag = "%s:%s" % peer_addr
        elif len(peer_addr) == 4:
            # IPv6
            self.log_tag = "[%s]:%s" % peer_addr[:2]
        else:
            self.log_tag = "[%s]" % (peer_addr,)

    async def tcp_forward(self, connection: Connection) -> None:
        s_reader, s_writer = connection
        idle = IdleTracker()
        watchdog = None
        if self.server.idle_timeout:
            watchdog = asyncio.ensure_future(
                idle.watch(self.server.idle_timeout, (self.writer, s_writer))
            )
        try:
            await asyncio.gather(
                forwarder_loop(
                    s_reader,
                    self.writer,
                    self.server.traffic_stats.add_inbound,
                    idle.touch,
                ),
                forwarder_loop(
                    self.reader,
                    s_writer,
                    self.server.traffic_stats.add_outbound,
                    idle.touch,
                ),
                return_exceptions=True,
            )
        finally:
            if watchdog is not None:
                watchdog.cancel()

    async def handle(self) -> None:
        pass


class AsyncProxyServer:
    def __init__(
        self,
        handler_class: Type[AsyncProxyHandler],
        listen_hosts: str | Sequence[str] = ("::", "0.0.0.0"),
        listen_port: int = 9876,
        traffic_stats: status.TrafficStats | None = None,
        resolver: Optional["dns.asyncresolver.Resolver"] = None,
        connect_host_ipv4: str | None = None,
        connect_host_ipv6: str | None = None,
        idle_timeout: float | None = None,
    ):
        self.handler_class = handler_class
        self.listen_hosts = listen_hosts
        self.listen_port = listen_port
        self.traffic_stats = traffic_stats or status.SimpleTrafficStats()
        self.resolver: DefaultAddressResolver | CustomSourceAddressResolver
        if resolver:
            self.resolver = CustomSourceAddressResolver(resolver, connect_host_ipv4, connect_host_ipv6)
        else:
            self.resolver = DefaultAddressResolver()
        self.connect_host_ipv4 = connect_host_ipv4
        self.connect_host_ipv6 = connect_host_ipv6
        self.idle_timeout = idle_timeout

    async def run(self) -> None:
        server = await asyncio.start_server(
            self.client_connected,
            host=self.listen_hosts,
            port=self.listen_port,
            reuse_address=True,
        )
        await server.serve_forever()

    async def client_connected(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        handler = self.handler_class(reader, writer, server=self)
        self.traffic_stats.add_connection()
        try:
            await handler.handle()
        finally:
            self.traffic_stats.remove_connection()

    async def ipv4_connect(self, address: SocketAddress) -> Connection:
        local_addr = (
            (self.connect_host_ipv4, 0) if self.connect_host_ipv4 is not None else None
        )
        return await asyncio.wait_for(
            asyncio.open_connection(address[0], address[1], local_addr=local_addr),
            timeout=CONNECT_TIMEOUT,
        )

    async def ipv6_connect(self, address: SocketAddress) -> Connection:
        local_addr = (
            (self.connect_host_ipv6, 0) if self.connect_host_ipv6 is not None else None
        )
        return await asyncio.wait_for(
            asyncio.open_connection(address[0], address[1], local_addr=local_addr),
            timeout=CONNECT_TIMEOUT,
        )

    async def tcp_connect(
        self, address_type: int, address: SocketAddress
    ) -> Connection:
        resolved = await self.resolve_address(address_type, address)

        if resolved.ipv4 is not None and resolved.ipv6 is not None:
            ipv6_addr = resolved.ipv6
            ipv4_addr = resolved.ipv4
            # happy eyeballs
            result, result_index, exceptions = await staggered_race(
                [
                    lambda: self.ipv6_connect(ipv6_addr),
                    lambda: self.ipv4_connect(ipv4_addr),
                ],
                delay=HAPPY_EYEBALLS_DELAY,
            )
            if not result:
                raise exceptions[0]
            return result
        elif resolved.ipv4 is not None:
            return await self.ipv4_connect(resolved.ipv4)
        elif resolved.ipv6 is not None:
            return await self.ipv6_connect(resolved.ipv6)
        else:
            raise Exception("Host %s could not be resolved" % (address,))

    async def dummy_resolve(self):
        raise Exception("address family not supported")

    async def _resolve_domain(self, address: SocketAddress) -> GenericAddress:
        domain, port = address

        result = GenericAddress()
        af = af_by_address(domain)
        if af == socket.AF_INET:
            result.ipv4 = address
            return result
        elif af == socket.AF_INET6:
            result.ipv6 = address
            return result

        if self.connect_host_ipv4 is None and self.connect_host_ipv6 is not None:
            ipv4_resolver = self.dummy_resolve()
        else:
            ipv4_resolver = self.resolver.resolve_ipv4(domain)

        if self.connect_host_ipv4 is not None and self.connect_host_ipv6 is None:
            ipv6_resolver = self.dummy_resolve()
        else:
            ipv6_resolver = self.resolver.resolve_ipv6(domain)

        ipv4, ipv6 = await asyncio.gather(
            ipv4_resolver,
            ipv6_resolver,
            return_exceptions=True,
        )
        if not isinstance(ipv4, BaseException) and ipv4:
            result.ipv4 = (random.choice(ipv4), port)
        if not isinstance(ipv6, BaseException) and ipv6:
            result.ipv6 = (random.choice(ipv6), port)
        return result

    async def resolve_address(
        self, address_type: int, address: SocketAddress
    ) -> GenericAddress:
        if address_type == Socks5AddressType.IPV4:
            result = GenericAddress(ipv4=address)
        elif address_type == Socks5AddressType.DOMAIN:
            result = await self._resolve_domain(address)
        elif address_type == Socks5AddressType.IPV6:
            result = GenericAddress(ipv6=address)

        if self.connect_host_ipv4 is None and self.connect_host_ipv6 is not None:
            result.ipv4 = None
        elif self.connect_host_ipv4 is not None and self.connect_host_ipv6 is None:
            result.ipv6 = None

        return result

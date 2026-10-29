#!/usr/bin/env python3
# Socks5/HTTP Proxy server for iSH (iOS), based on the Pythonista version by @nneonneo
# Pretty statistics view and IPv6 support added by @philrosenthal

import logging
import threading

from lib.socks5_server import AsyncSocks5Handler
from lib.http_proxy_server import AsyncHTTPProxyHandler
from lib.proxy_server import AsyncProxyServer
from lib.status import StatusMonitor

logging.basicConfig(level=logging.ERROR)

## Configuration
"""
Typical modes of operation:
- If you are using tethering, connect all clients to the hotspot and keep PROXY_HOST = "172.20.10.1".
- If you are connecting this phone and clients to some other WiFi network, set PROXY_HOST to this phone's address
  on that WiFi network and set USE_SYSTEM_DNS = False.
"""

# IP over which the proxy will be available (default: iOS tethering IP; set to a WiFi IP address if this will be accessed over WiFi)
PROXY_HOST = "172.20.10.1"
# Source IPs for outgoing connections. None lets iOS pick the route for both IPv4 and IPv6.
# To force IPv4 only (e.g. flaky carrier IPv6), set CONNECT_HOST_IPV4 = "0.0.0.0".
CONNECT_HOST_IPV4 = None
CONNECT_HOST_IPV6 = None
# Time out connections after being idle for this long (in seconds)
IDLE_TIMEOUT = 1800
# Host to listen on - 0.0.0.0 to listen on all interfaces
LISTEN_HOST = "0.0.0.0"
# Port numbers to listen on
SOCKS_PORT = 9876 # SOCKS5 server
HTTP_PORT = 9877 # HTTP Proxy server
WPAD_PORT = 8088 # WPAD proxy autodiscovery server

# Use iOS's DNS (also follows a VPN's DNS when one is on). Set to False to query
# CUSTOM_RESOLVERS (or Cloudflare/Google) directly.
USE_SYSTEM_DNS = True
CUSTOM_RESOLVERS = []

## End of configuration

DEFAULT_RESOLVERS = [
    "1.0.0.1",
    "1.1.1.1",
    "8.8.8.8",
    "2606:4700:4700::1111",
    "2606:4700:4700::1001",
    "2001:4860:4860::8844",
]

if USE_SYSTEM_DNS:
    resolver = None
else:
    try:
        from dns import asyncresolver
        from dns import resolver as dns_resolver

        resolver = asyncresolver.Resolver(configure=False)
        resolver.nameservers += CUSTOM_RESOLVERS or DEFAULT_RESOLVERS
        # cache answers (honouring record TTLs) instead of querying per connection
        resolver.cache = dns_resolver.LRUCache()
    except ImportError:
        # pip install dnspython
        print("Warning: dnspython not available; falling back to system DNS")
        resolver = None

initial_output = ""


def create_wpad_server(hhost, hport, phost, pport):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class HTTPHandler(BaseHTTPRequestHandler):
        def do_HEAD(s):
            s.send_response(200)
            s.send_header("Content-type", "application/x-ns-proxy-autoconfig")
            s.end_headers()

        def do_GET(s):
            s.send_response(200)
            s.send_header("Content-type", "application/x-ns-proxy-autoconfig")
            s.end_headers()
            s.wfile.write(
                (
                    """
function FindProxyForURL(url, host)
{
   if (isInNet(host, "192.168.0.0", "255.255.0.0")) {
      return "DIRECT";
   } else if (isInNet(host, "172.16.0.0", "255.240.0.0")) {
      return "DIRECT";
   } else if (isInNet(host, "10.0.0.0", "255.0.0.0")) {
      return "DIRECT";
   } else {
      return "SOCKS5 %s:%d; SOCKS %s:%d";
   }
}
"""
                    % (phost, pport, phost, pport)
                )
                .lstrip()
                .encode()
            )

    HTTPServer.allow_reuse_address = True
    server = HTTPServer((hhost, hport), HTTPHandler)
    return server


def run_wpad_server(server):
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import asyncio

    wpad_server = create_wpad_server(LISTEN_HOST, WPAD_PORT, PROXY_HOST, SOCKS_PORT)

    initial_output += "PAC URL: http://{}:{}/wpad.dat\n".format(PROXY_HOST, WPAD_PORT)
    initial_output += "SOCKS Address: {}:{}\n".format(
        PROXY_HOST or LISTEN_HOST, SOCKS_PORT
    )
    initial_output += "HTTP Proxy Address: {}:{}\n".format(
        PROXY_HOST or LISTEN_HOST, HTTP_PORT
    )
    stats = StatusMonitor(initial_output)
    logging.getLogger().addHandler(stats)

    thread = threading.Thread(target=run_wpad_server, args=(wpad_server,))
    thread.daemon = True
    thread.start()

    async def main():
        server = AsyncProxyServer(
            AsyncSocks5Handler,
            listen_hosts=LISTEN_HOST,
            listen_port=SOCKS_PORT,
            traffic_stats=stats,
            resolver=resolver,
            connect_host_ipv4=CONNECT_HOST_IPV4,
            connect_host_ipv6=CONNECT_HOST_IPV6,
            idle_timeout=IDLE_TIMEOUT,
        )
        asyncio.create_task(server.run())

        server = AsyncProxyServer(
            AsyncHTTPProxyHandler,
            listen_hosts=LISTEN_HOST,
            listen_port=HTTP_PORT,
            traffic_stats=stats,
            resolver=resolver,
            connect_host_ipv4=CONNECT_HOST_IPV4,
            connect_host_ipv6=CONNECT_HOST_IPV6,
            idle_timeout=IDLE_TIMEOUT,
        )
        asyncio.create_task(server.run())

        await stats.render_forever()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down.")
        wpad_server.shutdown()

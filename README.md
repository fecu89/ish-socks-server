# iOS SOCKS Server (iSH / Python 3.9판)

아이폰의 **iSH** 앱에서 SOCKS5/HTTP 프록시 서버를 돌려, 노트북 같은 다른 기기가 아이폰의 인터넷 연결을 쓰게 해 주는 스크립트입니다. 모든 연결이 아이폰에서 직접 나가기 때문에 통신사의 테더링(핫스팟) 차단이나 속도 제한을 피할 수 있습니다.

[nneonneo/iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server)를 iSH 기본 Python(3.9)에서 바로 돌아가도록 고친 버전입니다. 원본은 Pythonista용이고 Python 3.10 이상이 필요합니다.

📖 **사진이 포함된 자세한 사용법**은 블로그에 정리해 두었습니다.
- [1탄: 아이폰 테더링 제한 우회하기 (LG U+ 기준)](https://pyx.kr/post/bypassing-iphone-tethering-limit-lgu-specific)
- [2탄: iSH 백그라운드 실행 방법](https://pyx.kr/post/bypassing-iphone-tethering-limits-lg-u-part-2-running-ish)

> 1탄의 "edge 저장소를 추가해 Python 3.10 이상으로 업그레이드하기" 단계는 이 버전에서는 **필요 없습니다.** iSH 기본 `python3`(3.9)으로 바로 실행됩니다.

## 사용 방법

### 1. 설치

1. App Store에서 [iSH Shell](https://apps.apple.com/kr/app/ish-shell/id1436902243)을 설치합니다.
2. iSH를 열고 Python을 설치합니다.
   ```sh
   apk update
   apk add python3
   ```
3. 코드를 `/root/socks`에 받습니다. 둘 중 편한 방법을 쓰세요.
   - **iSH에서 바로 받기 (간단)**
     ```sh
     apk add git
     git clone https://github.com/fecu89/ish-socks-server ~/socks
     ```
   - **zip으로 받기:** Chrome 등 브라우저로 [저장소](https://github.com/fecu89/ish-socks-server)에 들어가 **Code → Download ZIP**으로 받습니다. 압축을 풀고 폴더 이름을 `socks`로 바꾼 뒤, **파일** 앱의 **iSH** → `root` 폴더에 넣습니다. GitHub 앱에서는 다운로드 버튼이 보이지 않습니다.
   - `dns` 폴더(dnspython)가 함께 들어 있어서 `pip`로 따로 설치할 것은 없습니다.

### 2. 실행

```sh
cd ~/socks
python3 socks5.py
```

- 실행하면 다른 기기에 입력할 주소가 표시됩니다.
  ```
  PAC URL: http://172.20.10.1:8088/wpad.dat
  SOCKS Address: 172.20.10.1:9876
  HTTP Proxy Address: 172.20.10.1:9877
  ```
- 종료하려면 iSH 키보드 위 도구 막대의 **ctrl** 키를 누른 뒤 **c**를 누릅니다.

### 3. 계속 켜 두기

iOS는 화면을 끄거나 다른 앱으로 넘어가면 iSH를 멈춥니다. 둘 중 하나를 고르세요.

**방법 A: 화면을 켜 둔 채로 쓰기**
- iSH 키보드 위의 톱니바퀴 버튼 → **Keep Screen Turned On**을 켭니다.

**방법 B: 백그라운드에서 실행하기 (화면을 꺼도 동작)**
1. 서버를 켜기 전에 아래 명령을 먼저 입력합니다.
   ```sh
   cat /dev/location > /dev/null &
   ```
2. 위치 권한을 물으면 허용합니다.
3. **설정 → 개인정보 보호 및 보안 → 위치 서비스 → iSH**를 **항상**으로 바꿉니다.
4. `python3 socks5.py`로 서버를 실행합니다.

위치 기능을 계속 쓰기 때문에 배터리 소모가 늘어납니다. 원리는 iSH 위키의 [Running in background](https://github.com/ish-app/ish/wiki/Running-in-background) 문서에 있습니다.

### 4. 연결 방식에 맞게 설정

`socks5.py` 위쪽의 설정 부분을 고칩니다. iSH에서 `vi socks5.py`로 열어도 되고, 파일 앱에서 다른 편집기로 열어도 됩니다.

**개인용 핫스팟으로 연결할 때 (기본)**
- 바꿀 것이 없습니다. 기본값 `PROXY_HOST = "172.20.10.1"`이 핫스팟 주소입니다.
- 아이폰 **설정 → 개인용 핫스팟 → 다른 사람의 연결 허용**을 켜고, 다른 기기를 핫스팟에 연결합니다.

**아이폰과 다른 기기가 같은 와이파이에 있을 때**
- iSH는 아이폰의 와이파이 주소를 자동으로 찾지 못하므로 직접 입력해야 합니다.
- 아이폰 **설정 → Wi-Fi → 연결된 네트워크 옆 (i)**에서 IP 주소를 확인한 뒤 다음처럼 바꿉니다.
  ```python
  PROXY_HOST = "192.168.0.23"   # 위에서 확인한 아이폰 IP
  USE_SYSTEM_DNS = False
  ```

### 5. 다른 기기에서 프록시 설정하기

실행 화면에 표시된 주소를 입력합니다.

- **macOS:** 시스템 설정 → 네트워크 → Wi-Fi → 아이폰 핫스팟의 **세부사항** → **프록시** → **SOCKS 프록시**를 켜고 서버 `172.20.10.1`, 포트 `9876`을 입력합니다.
  - 네트워크 **위치**를 따로 하나 만들어(예: `socks`) 거기에 설정해 두면, 평소 설정으로 쉽게 되돌릴 수 있습니다. 블로그 1탄 참고.
  - 시스템 프록시를 따르지 않는 앱은 앱 안에서 따로 설정해야 합니다.
- **iPhone/iPad:** 설정 → Wi-Fi → 네트워크 옆 (i) → **프록시 구성** → **자동** → URL에 PAC URL을 입력합니다.
- **Windows:** 설정 → 네트워크 및 인터넷 → **프록시** → **설정 스크립트 사용**을 켜고 PAC URL을 입력합니다.
- **Android:** 설정 → Wi-Fi → 네트워크 → 고급 → 프록시 **수동** → 호스트 `172.20.10.1`, 포트 `9877`(HTTP 프록시)을 입력합니다. Android는 SOCKS 지원이 제한적이라 HTTP 프록시를 권장합니다.
- **SSH 등 다른 TCP 프로그램:**
  ```sh
  ssh -o ProxyCommand='nc -X 5 -x 172.20.10.1:9876 %h %p' user@host
  ```

## 설정 항목

`socks5.py` 위쪽에 있습니다.

| 항목 | 기본값 | 설명 |
|---|---|---|
| `PROXY_HOST` | `172.20.10.1` | 다른 기기가 접속할 아이폰 주소. PAC 파일과 화면 표시에 쓰입니다. |
| `SOCKS_PORT` | `9876` | SOCKS5 프록시 포트 |
| `HTTP_PORT` | `9877` | HTTP 프록시 포트 |
| `WPAD_PORT` | `8088` | PAC(자동 프록시 설정) 파일 포트 |
| `IDLE_TIMEOUT` | `1800` | 양방향 모두 데이터가 없는 연결을 닫기까지의 시간(초) |
| `USE_SYSTEM_DNS` | `True` | `True`면 iOS의 DNS를(VPN이 켜져 있으면 VPN의 DNS), `False`면 Cloudflare·Google DNS를 직접 사용 |
| `CUSTOM_RESOLVERS` | `[]` | `USE_SYSTEM_DNS = False`일 때 쓸 DNS 서버 목록. 비우면 기본 목록을 씁니다. |
| `CONNECT_HOST_IPV4` / `CONNECT_HOST_IPV6` | `None` | 바깥으로 나가는 연결의 출발 주소. `None`이면 iOS가 IPv4·IPv6 경로를 정합니다. 통신사 IPv6가 불안정하면 `CONNECT_HOST_IPV4 = "0.0.0.0"`으로 IPv4만 쓰게 할 수 있습니다. |

VPN이 켜져 있으면 iOS가 알아서 모든 트래픽을 VPN으로 보내므로 따로 설정할 것은 없습니다.

## 원본과 달라진 점

**iSH / Python 3.9 지원**
- Python 3.9에서 실행됩니다. 원본은 3.10 전용 타입 표기(`int | None`) 때문에 3.9에서 시작하자마자 `TypeError`가 났습니다.
- iSH(Alpine Linux) 전용으로 정리했습니다.
  - Pythonista 전용 코드(`console`, `objc_util`)를 제거했습니다.
  - 네트워크 인터페이스 자동 감지(`lib/ifaddrs.py`)를 제거했습니다. iSH는 인터페이스 목록을 제공하지 않아(`getifaddrs` 실패) 이 코드는 매번 경고만 띄우고 아무 일도 하지 않았습니다. 대신 IPv4/IPv6 경로를 iOS에 맡깁니다.
  - 같은 이유로 iSH에서 효과가 없던 `USE_PHONE_VPN` 설정도 없앴습니다.

**버그 수정**
- HTTP 프록시가 IPv6 주소(`2001:db8::1:443`, `[2001:db8::1]:443`)로 들어온 요청에서 `ValueError`를 내던 문제
- HTTP 프록시가 오류가 나면 응답 없이 연결을 열어 둬서 연결이 계속 쌓이던 문제
**안정성·성능**
- 설정만 있고 쓰이지 않던 `IDLE_TIMEOUT`을 실제로 적용합니다. 양방향 모두 데이터가 없는 연결은 30분 뒤 닫힙니다.
- 접속만 하고 요청을 보내지 않는 연결은 60초 뒤 닫습니다.
- DNS 조회 결과를 저장해 둡니다. 시스템 DNS는 60초, dnspython은 레코드의 TTL만큼 기억합니다.
- 상태 화면은 내용이 바뀔 때만 다시 그립니다. iSH의 CPU 사용을 줄이기 위해서입니다.

## 문제 해결

- **`Address already in use`:** 이미 실행 중인 서버가 있습니다. 기존 창을 종료하거나 iSH를 완전히 껐다 켜세요.
- **화면의 `Connections:` 숫자가 큼:** 브라우저는 사이트 하나에도 연결을 수십 개 만들기 때문에 수십 개는 정상입니다. 브라우징을 멈추면 1분~30분 안에 줄어듭니다.
- **속도가 생각보다 느림:** iSH는 x86 CPU를 흉내 내서 돌아가기 때문에 CPU를 많이 씁니다. 속도가 iSH 성능에 묶일 수 있습니다.

## 출처

- 원본: [nneonneo/iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server) — @nneonneo 작성. 통계 화면과 IPv6 지원은 @philrosenthal이 추가했습니다.
- `dns/` 폴더는 [dnspython](https://www.dnspython.org/) 2.3.0을 그대로 포함한 것입니다(ISC 라이선스, `dns/LICENSE`).
- 원본 코드의 권리는 원작자에게 있습니다. 자세한 내용은 `LICENSE`를 보세요.

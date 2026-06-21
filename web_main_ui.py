# web_main_ui.py
"""
AI Studio Pro — 웹(브라우저) 진입점.

run_gui.bat(new_main_ui.py)는 PyQt 창 안의 QWebEngineView로 Vue를 띄운다.
이 파일(run_WEB_gui.bat)은 **같은 백엔드/같은 vue_bridge**를 재사용하되,
A1111처럼 localhost 포트를 열어 일반 브라우저(폰/타 PC 포함)로 접속하게 한다.

핵심: QWebChannel은 transport 교체가 가능하다. 창 모드는 '동일 프로세스 직통선',
웹 모드는 'WebSocket'을 transport로 쓸 뿐, vue_bridge의 슬롯/시그널/액션 디스패치는
그대로 재사용된다 (재작성 없음). 전부 localhost/LAN이라 인터넷은 필요 없다.

구성:
  - GeneratorMainUI 를 (창을 띄우지 않고) 생성 → 모든 백엔드 로직/프록시가 살아있음
  - QWebSocketServer + WebSocketChannelTransport 로 vue_bridge 를 'backend'로 publish
  - frontend_dist 를 HTTP 정적 서빙(index.html 에 WS 포트 주입)
  - 기본 브라우저 자동 오픈
"""
import sys
import os
import json
import threading
import functools
import mimetypes
from urllib.parse import urlparse, parse_qs, unquote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-logging --log-level=3 --disable-features=WebRtcHideLocalIpsWithMdns",
)
os.environ.setdefault("QT_LOGGING_RULES", "qt.webenginecontext.debug=false")

from config import *  # noqa: F401,F403  (OUTPUT_DIR 등)
from ui.generator_main import GeneratorMainUI

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QObject, pyqtSlot, QEventLoop, QTimer, QJsonDocument
from PyQt6.QtWebChannel import QWebChannel, QWebChannelAbstractTransport
from PyQt6.QtWebSockets import QWebSocketServer
from PyQt6.QtNetwork import QHostAddress

# ── 포트 설정 (환경변수로 덮어쓰기 가능) ──
HTTP_PORT = int(os.environ.get("AISTUDIO_HTTP_PORT", "7800"))
WS_PORT = int(os.environ.get("AISTUDIO_WS_PORT", "7801"))
# 0.0.0.0 바인딩 → 같은 공유기(LAN)의 폰/다른 PC에서도 접속 가능. 외부망 노출은 안 함.
BIND_HOST = os.environ.get("AISTUDIO_BIND", "0.0.0.0")

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DIST = os.path.join(_ROOT, "frontend_dist")


# ──────────────────────────────────────────────────────────────────────────
# QWebChannel ↔ WebSocket transport (Qt 공식 chat 예제의 PyQt 포팅)
# ──────────────────────────────────────────────────────────────────────────
class WebSocketTransport(QWebChannelAbstractTransport):
    """단일 QWebSocket 연결을 QWebChannel transport로 감싼다.

    Qt 공식 'qwebchannel/standalone' 예제의 PyQt 포팅. 메시지를 dict가 아니라
    QJsonDocument/QJsonObject로 주고받아야 핸드셰이크가 완료된다 (dict 직접 emit은
    버전에 따라 QJsonObject 변환이 어긋나 채널 초기화가 멈출 수 있음).
    """

    def __init__(self, socket):
        super().__init__(socket)
        self._socket = socket
        self._socket.textMessageReceived.connect(self._on_text)
        self._socket.disconnected.connect(self.deleteLater)

    @pyqtSlot(str)
    def _on_text(self, message):
        doc = QJsonDocument.fromJson(message.encode("utf-8"))
        if doc.isNull() or not doc.isObject():
            return
        # QWebChannel 로 실제 QJsonObject 를 전달
        self.messageReceived.emit(doc.object(), self)

    def sendMessage(self, message):
        # message: QJsonObject(dict 로 도착) → 컴팩트 JSON 텍스트로 송신
        try:
            doc = QJsonDocument(message)
            text = bytes(doc.toJson(QJsonDocument.JsonFormat.Compact)).decode("utf-8")
            self._socket.sendTextMessage(text)
        except Exception as e:
            print(f"[web] sendMessage 실패: {e}")


class WebChannelServer(QObject):
    """WebSocket 서버를 띄우고 새 연결마다 channel에 transport를 연결한다."""

    def __init__(self, channel, host, port, on_first_client=None):
        super().__init__()
        self._channel = channel
        self._on_first_client = on_first_client
        self._had_client = False
        self._transports = []
        self.server = QWebSocketServer(
            "AIStudioPro", QWebSocketServer.SslMode.NonSecureMode
        )
        addr = QHostAddress.SpecialAddress.Any if host in ("0.0.0.0", "") else QHostAddress(host)
        if not self.server.listen(addr, port):
            raise RuntimeError(
                f"WebSocket 서버가 포트 {port} 에서 listen 실패: {self.server.errorString()}"
            )
        self.server.newConnection.connect(self._on_new_connection)
        print(f"[web] WebChannel(WebSocket) listening on ws://{host}:{port}")

    def _on_new_connection(self):
        socket = self.server.nextPendingConnection()
        transport = WebSocketTransport(socket)
        self._transports.append(transport)
        self._channel.connectTo(transport)
        socket.disconnected.connect(lambda: self._on_disconnect(transport))
        print("[web] 브라우저 연결됨")
        if not self._had_client:
            self._had_client = True
            if self._on_first_client:
                self._on_first_client()

    def _on_disconnect(self, transport):
        try:
            self._transports.remove(transport)
        except ValueError:
            pass


# ──────────────────────────────────────────────────────────────────────────
# 정적 HTTP 서버 (frontend_dist) — index.html 에 WS 포트 주입
# ──────────────────────────────────────────────────────────────────────────
class _DistHandler(SimpleHTTPRequestHandler):
    """frontend_dist 서빙. index.html 에 WS 포트 전역을 주입한다.

    주입 스크립트는 인라인(클래식)이라 Vite의 module 스크립트(deferred)보다 먼저
    실행 → initBridge() 시점에 window.__AISTUDIO_WS_PORT__ 가 보장된다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_DIST, **kwargs)

    def log_message(self, *args):  # 콘솔 스팸 억제
        pass

    def _serve_index(self):
        index_path = os.path.join(_DIST, "index.html")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                html = f.read()
        except OSError:
            self.send_error(404, "frontend_dist/index.html 없음 — 'npm run build' 먼저")
            return
        inject = f"<script>window.__AISTUDIO_WS_PORT__={WS_PORT};</script>"
        if "</head>" in html:
            html = html.replace("</head>", inject + "</head>", 1)
        else:
            html = inject + html
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_local_file(self):
        """`/file?path=<로컬경로>` — 로컬 이미지 파일을 HTTP 로 서빙.

        원격 브라우저는 file:/// 를 못 읽으므로 프론트 mediaUrl() 이 이 경로로 요청한다.
        보안: core.path_safety.safe_input_path 로 검증(존재·일반파일·이미지 확장자·
        시스템 디렉터리 차단). A1111 --listen 과 같은 신뢰 LAN 전제.
        """
        try:
            from core.path_safety import safe_input_path
        except Exception:
            safe_input_path = None
        qs = parse_qs(urlparse(self.path).query)
        raw = unquote((qs.get("path") or [""])[0])
        safe = safe_input_path(raw) if safe_input_path else None
        if not safe or not os.path.isfile(safe):
            print(f"[web] /file 404 — raw={raw!r} safe={safe!r}")
            self.send_error(404, "file not found or not allowed")
            return
        ctype = mimetypes.guess_type(safe)[0] or "application/octet-stream"
        try:
            with open(safe, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404, "read error")
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._serve_index()
            return
        if path == "/file":
            self._serve_local_file()
            return
        super().do_GET()


def _start_http_server():
    httpd = ThreadingHTTPServer((BIND_HOST, HTTP_PORT), _DistHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"[web] HTTP 정적 서버: http://{BIND_HOST}:{HTTP_PORT}")
    return httpd


# ──────────────────────────────────────────────────────────────────────────
# 웹 모드 시작 시퀀스 — 임베드 Vue 로드/대기는 건너뛰고 백엔드만 준비
# ──────────────────────────────────────────────────────────────────────────
def _web_startup(window, app, web_server):
    """창 모드의 _run_startup_sequence 에서 '임베드 뷰 로드/대기'만 제외한 버전.

    순서: 백엔드 선택(호스트에서 1회) → 서버 기동 → 브라우저 접속 대기 →
          접속되면 백엔드 적용(데이터 push). push 시점에 클라이언트가 붙어 있어야
          sticky 가 아닌 이벤트(모델 목록 등)도 유실 없이 도달한다.
    """
    # 1. 백엔드 선택 (호스트 화면에 1회 — 창 모드와 동일 로직)
    if hasattr(window, "_startup_backend_check"):
        window._startup_backend_check()

    # 2. 첫 브라우저 접속 대기 (최대 60초) — 접속 전이면 push 가 유실되므로
    loop = QEventLoop()
    if web_server._had_client:
        pass
    else:
        web_server._on_first_client = loop.quit
        QTimer.singleShot(60000, loop.quit)  # 안전 타임아웃
        print("[web] 브라우저 접속 대기 중…")
        loop.exec()

    # 3. 백엔드 연결 + 모델/샘플러/LoRA → Vue(브라우저)로 push
    try:
        if hasattr(window, "_apply_backend_startup_result"):
            window._apply_backend_startup_result()
    except Exception as e:
        print(f"[web] 백엔드 적용 실패(무시): {e}")
    try:
        if hasattr(window, "_restore_search_deck"):
            QTimer.singleShot(600, window._restore_search_deck)
    except Exception:
        pass


def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "mycompany.myproduct.subproduct.version"
        )

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("AI Studio Pro (Web)")
    app.setOrganizationName("AI Studio")
    app.setStyleSheet("")

    os.makedirs(OUTPUT_DIR, exist_ok=True)  # noqa: F405

    if not os.path.exists(os.path.join(_DIST, "index.html")):
        print("[web] frontend_dist 가 없습니다. 먼저 'cd frontend && npm run build' 하세요.")
        sys.exit(1)

    # 백엔드 윈도우 생성 (창은 띄우지 않음 — 로직/프록시/vue_bridge 만 사용)
    window = GeneratorMainUI()

    # WebChannel + WebSocket 서버
    channel = QWebChannel()
    channel.registerObject("backend", window.vue_bridge)
    web_server = WebChannelServer(channel, BIND_HOST, WS_PORT)

    # HTTP 정적 서버 + 브라우저 오픈
    _start_http_server()
    url = f"http://localhost:{HTTP_PORT}"
    print("=" * 60)
    print(f"[web] 브라우저에서 열기:  {url}")
    print(f"[web] 같은 네트워크의 다른 기기:  http://<이 PC의 IP>:{HTTP_PORT}")
    print("=" * 60)
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    # 백엔드 준비 (브라우저 접속 후 데이터 push)
    QTimer.singleShot(0, functools.partial(_web_startup, window, app, web_server))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

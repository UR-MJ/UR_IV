"""웹 모드 인증, 파일 전송, 제한 브릿지 계약 회귀 테스트."""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import re
import tempfile
import threading
import unittest
from urllib.parse import quote
from unittest import mock

from PIL import Image

try:
    import web_main_ui
    from ui.vue_bridge import VueBridge
    _WEB_IMPORT_ERROR = ""
except ModuleNotFoundError as exc:
    if not (exc.name or "").startswith("PyQt6"):
        raise
    web_main_ui = None
    VueBridge = None
    _WEB_IMPORT_ERROR = str(exc)


@unittest.skipIf(web_main_ui is None, f"PyQt6 WebEngine unavailable: {_WEB_IMPORT_ERROR}")
class TestWebModeSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.thumb_patch = mock.patch.object(web_main_ui, "_THUMB_DIR", cls.temp_dir.name)
        cls.thumb_patch.start()
        cls.image_path = os.path.join(cls.temp_dir.name, "source.png")
        Image.new("RGB", (320, 160), (20, 40, 80)).save(cls.image_path)

        cls.server = web_main_ui.ThreadingHTTPServer(
            ("127.0.0.1", 0), web_main_ui._DistHandler
        )
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.thumb_patch.stop()
        cls.temp_dir.cleanup()

    def _request(self, path, *, headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        conn.close()
        return result

    def _authenticated_cookie(self):
        status, headers, _body = self._request(
            f"/?token={quote(web_main_ui.SESSION_TOKEN)}"
        )
        self.assertEqual(status, 303)
        self.assertNotIn("token=", headers["Location"])
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_http_requires_session_and_cleans_token_url(self):
        status, _headers, _body = self._request("/")
        self.assertEqual(status, 401)

        cookie = self._authenticated_cookie()
        status, headers, body = self._request(
            "/runtime-config.js", headers={"Cookie": cookie}
        )
        self.assertEqual(status, 200)
        self.assertIn(b"__AISTUDIO_WS_PORT__", body)
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")

    def test_file_streaming_cache_and_thumbnail(self):
        cookie = self._authenticated_cookie()
        encoded = quote(self.image_path)
        status, headers, body = self._request(
            f"/file?path={encoded}", headers={"Cookie": cookie}
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(body), os.path.getsize(self.image_path))
        self.assertIn("ETag", headers)
        self.assertIn("Last-Modified", headers)

        status, _headers, body = self._request(
            f"/file?path={encoded}",
            headers={"Cookie": cookie, "If-None-Match": headers["ETag"]},
        )
        self.assertEqual(status, 304)
        self.assertEqual(body, b"")

        status, headers, body = self._request(
            f"/thumbnail?path={encoded}&width=96", headers={"Cookie": cookie}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/jpeg")
        self.assertGreater(len(body), 0)

    def test_origin_and_cookie_validation(self):
        self.assertTrue(web_main_ui._token_matches(web_main_ui.SESSION_TOKEN))
        self.assertFalse(web_main_ui._token_matches("wrong"))
        self.assertEqual(
            web_main_ui._cookie_token(
                f"other=x; {web_main_ui.SESSION_COOKIE}={web_main_ui.SESSION_TOKEN}"
            ),
            web_main_ui.SESSION_TOKEN,
        )
        self.assertTrue(
            web_main_ui._origin_matches(
                f"http://127.0.0.1:{web_main_ui.HTTP_PORT}", "127.0.0.1"
            )
        )
        self.assertFalse(web_main_ui._origin_matches("https://evil.example", "127.0.0.1"))

    def test_websocket_requires_cookie_and_matching_origin(self):
        from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
        from PyQt6.QtNetwork import QNetworkRequest
        from PyQt6.QtWebChannel import QWebChannel
        from PyQt6.QtWebSockets import QWebSocket

        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = VueBridge()
        channel = QWebChannel()
        facade = web_main_ui.WebBridgeFacade(bridge, channel)
        channel.registerObject("backend", facade)
        server = web_main_ui.WebChannelServer(channel, "127.0.0.1", 0)
        port = server.server.serverPort()

        def wait_for(signal, action, timeout=2000):
            loop = QEventLoop()
            fired = []
            signal.connect(lambda: (fired.append(True), loop.quit()))
            QTimer.singleShot(timeout, loop.quit)
            action()
            loop.exec()
            return bool(fired)

        origin = f"http://127.0.0.1:{web_main_ui.HTTP_PORT}"
        good = QWebSocket(origin)
        request = QNetworkRequest(QUrl(f"ws://127.0.0.1:{port}"))
        request.setRawHeader(
            b"Cookie",
            f"{web_main_ui.SESSION_COOKIE}={web_main_ui.SESSION_TOKEN}".encode("ascii"),
        )
        self.assertTrue(wait_for(good.connected, lambda: good.open(request)))
        app.processEvents()
        self.assertEqual(len(server._connections), 1)
        self.assertTrue(wait_for(good.disconnected, good.close))
        app.processEvents()
        self.assertEqual(len(server._connections), 0)

        bad = QWebSocket("https://evil.example")
        bad_request = QNetworkRequest(QUrl(f"ws://127.0.0.1:{port}"))
        bad_request.setRawHeader(
            b"Cookie",
            f"{web_main_ui.SESSION_COOKIE}={web_main_ui.SESSION_TOKEN}".encode("ascii"),
        )
        self.assertTrue(wait_for(bad.disconnected, lambda: bad.open(bad_request)))
        app.processEvents()
        self.assertEqual(len(server._connections), 0)
        server.close()

    def test_facade_blocks_unlisted_methods_and_config_is_not_broadcast(self):
        bridge = VueBridge()
        facade = web_main_ui.WebBridgeFacade(bridge)
        capabilities = json.loads(facade.getCapabilities())
        self.assertIn("getInitialConfig", capabilities["methods"])
        self.assertNotIn("requestInitialConfig", capabilities["methods"])

        legacy_settings_methods = {
            "getBackendRuntimeState",
            "runBackendRuntimeOperation",
            "getGenerationApiState",
            "runGenerationApiOperation",
            "selectBackendExtensionDirectory",
            "selectBackendInstallDirectory",
            "getForgeModelPaths",
            "selectForgeModelDirectory",
            "saveForgeModelPaths",
            "resetForgeModelPaths",
            "refreshForgeModelPaths",
        }
        self.assertTrue(
            legacy_settings_methods.isdisjoint(capabilities["methods"]),
            "웹은 redacted studio settings Interface만 사용해야 합니다.",
        )
        for method in legacy_settings_methods:
            reply = json.loads(facade.invoke(method, "[]"))
            self.assertFalse(reply["ok"], method)

        allowed = json.loads(facade.invoke("getAllWidgetValues", "[]"))
        blocked = json.loads(facade.invoke("set_action_handler", "[]"))
        self.assertTrue(allowed["ok"])
        self.assertFalse(blocked["ok"])

        broadcasts = []
        bridge.uiPrefsLoaded.connect(broadcasts.append)
        payload = json.loads(bridge.requestInitialConfig())
        self.assertIn("uiPrefs", payload)
        self.assertEqual(broadcasts, [])

    def test_frontend_slot_usage_is_covered_by_facade(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "ui" / "vue_bridge.py").read_text(encoding="utf-8")
        frontend = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "frontend" / "src").rglob("*")
            if path.suffix in {".vue", ".js", ".ts"}
        )
        slots = set(re.findall(
            r"(?:^[ \t]*@pyqtSlot[^\n]*\n)+^[ \t]*def\s+(\w+)",
            source,
            re.MULTILINE,
        ))
        used = {
            name for name in slots
            if re.search(r"\." + re.escape(name) + r"\b", frontend)
            or re.search(r"[\"']" + re.escape(name) + r"[\"']", frontend)
        }
        desktop_only = {
            "copyTextToClipboard",
            "requestInitialConfig",
            "getBackendRuntimeState",
            "runBackendRuntimeOperation",
            "getGenerationApiState",
            "runGenerationApiOperation",
            "selectBackendExtensionDirectory",
            "selectBackendInstallDirectory",
            "getForgeModelPaths",
            "selectForgeModelDirectory",
            "saveForgeModelPaths",
            "resetForgeModelPaths",
            "refreshForgeModelPaths",
        }
        missing = used - web_main_ui._WEB_METHODS - desktop_only
        self.assertEqual(missing, set())
        self.assertTrue(desktop_only.isdisjoint(web_main_ui._WEB_METHODS))
        self.assertTrue({
            "backendRuntimeEvent", "generationApiEvent",
        }.isdisjoint(web_main_ui._WEB_SIGNALS))
        self.assertTrue(all(callable(getattr(VueBridge, name, None)) for name in web_main_ui._WEB_METHODS))

    def test_frontend_events_are_covered_by_web_signals(self):
        """공용 프론트 이벤트는 웹에 공개하고, 네이티브 전용 이벤트는 차단한다.

        누락되면 웹 모드에서 그 이벤트만 조용히 사라진다(예전 searchResultsReady).
        로컬 설치 경로를 포함하는 모델 다운로드는 명시적인 데스크톱 전용 예외다.
        """
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "ui" / "vue_bridge.py").read_text(encoding="utf-8")
        frontend = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "frontend" / "src").rglob("*")
            if path.suffix in {".vue", ".js", ".ts"}
        )
        signals = set(re.findall(r"^[ \t]*(\w+)\s*=\s*pyqtSignal\(", source, re.MULTILINE))
        listened = set(re.findall(r"onBackendEvent\(\s*[\"'](\w+)[\"']", frontend))
        native_only_events = {"modelDownloadEvent", "comfyCompatibilityResult", "comfyWorkflowEvent", "relightEvent"}
        self.assertTrue(native_only_events <= signals,
                        "네이티브 전용 예외도 실제 VueBridge 시그널이어야 합니다.")
        self.assertTrue(native_only_events.isdisjoint(web_main_ui._WEB_SIGNALS),
                        "로컬 설치·설정·파일 처리 이벤트는 웹 클라이언트에 공개하면 안 됩니다.")
        missing = (listened & signals) - web_main_ui._WEB_SIGNALS - native_only_events
        self.assertEqual(missing, set())
        # 반대 방향: 화이트리스트에 실제 시그널이 아닌 이름(오타/사문)이 남지 않도록.
        self.assertEqual(web_main_ui._WEB_SIGNALS - signals, set())


if __name__ == "__main__":
    unittest.main()

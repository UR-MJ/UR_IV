# tabs/backend_ui_tab.py
"""백엔드 UI 확인 탭 — WebUI / ComfyUI 웹 인터페이스를 임베디드 웹뷰로 표시"""
import os
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit
)
from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage

from config import CURRENT_DIR
from utils.theme_manager import get_color


class _QuietPage(QWebEnginePage):
    """JS 콘솔 경고 억제 페이지"""
    def javaScriptConsoleMessage(self, level, message, line, source):
        pass


class BackendUITab(QWidget):
    """백엔드 UI 확인 탭"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_url = ""
        self._load_workflow_after = False
        self._workflow_retry_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 상단 바 ──
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 6, 8, 6)
        top_bar.setSpacing(6)

        btn_vue_home = QPushButton("← AI Studio")
        btn_vue_home.setFixedWidth(100)
        btn_vue_home.clicked.connect(self._go_vue_home)
        top_bar.addWidget(btn_vue_home)

        self._status_label = QLabel("백엔드 UI")
        self._status_label.setStyleSheet(
            f"color: {get_color('text_secondary')}; font-weight: bold; font-size: 13px;"
        )
        top_bar.addWidget(self._status_label)

        top_bar.addStretch()

        self._url_display = QLineEdit()
        self._url_display.setReadOnly(True)
        self._url_display.setStyleSheet(
            f"background: {get_color('bg_secondary')}; color: {get_color('text_muted')}; border: 1px solid {get_color('bg_button_hover')}; "
            "border-radius: 4px; padding: 3px 8px; font-size: 11px;"
        )
        self._url_display.setFixedWidth(300)
        top_bar.addWidget(self._url_display)

        btn_reload = QPushButton("🔄")
        btn_reload.setFixedSize(36, 32)
        btn_reload.setToolTip("새로고침")
        btn_reload.clicked.connect(self._reload)
        top_bar.addWidget(btn_reload)

        btn_open = QPushButton("🌐")
        btn_open.setFixedSize(36, 32)
        btn_open.setToolTip("외부 브라우저로 열기")
        btn_open.clicked.connect(self._open_external)
        top_bar.addWidget(btn_open)

        layout.addLayout(top_bar)

        # ── 웹뷰 ──
        self._web_view = QWebEngineView()

        # 프로필 설정
        self._profile = QWebEngineProfile("backend_ui", self)
        self._profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        cache_path = os.path.join(CURRENT_DIR, 'backend_ui_cache')
        self._profile.setCachePath(cache_path)
        self._profile.setPersistentStoragePath(cache_path)

        # 초기 페이지 생성
        self._page = _QuietPage(self._profile, self._web_view)
        self._web_view.setPage(self._page)
        self._apply_web_settings()

        # URL 변경 추적 (한 번만 연결)
        self._web_view.urlChanged.connect(self._on_url_changed)

        # 초기 빈 페이지
        self._web_view.setHtml(self._placeholder_html(), QUrl("about:blank"))
        layout.addWidget(self._web_view)

    def _on_url_changed(self, url: QUrl):
        """URL 변경 시 표시 업데이트"""
        self._url_display.setText(url.toString())

    def _apply_web_settings(self):
        """웹뷰 설정 적용"""
        settings = self._web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)

    def _recreate_page(self):
        """새 페이지를 생성하여 이전 SPA/JS 상태를 완전히 제거"""
        old_page = self._page

        new_page = _QuietPage(self._profile, self._web_view)
        self._web_view.setPage(new_page)
        self._page = new_page
        self._apply_web_settings()

        # 이전 페이지 정리
        if old_page is not None:
            try:
                old_page.deleteLater()
            except RuntimeError:
                pass

    # ── 공개 API ──

    def _go_vue_home(self):
        """Vue SPA로 복귀"""
        parent = self.parent()
        while parent:
            if hasattr(parent, '_main_stack'):
                parent._main_stack.setCurrentIndex(0)
                return
            parent = parent.parent()

    def load_backend_ui(self):
        """현재 백엔드에 맞는 UI를 로드"""
        from backends import get_backend, get_backend_type, BackendType

        backend = get_backend()
        backend_type = get_backend_type()

        if backend_type == BackendType.COMFYUI:
            url = backend.api_url
            self._status_label.setText("🟣 ComfyUI")
            self._load_url(url, load_workflow=True)
        else:
            url = backend.api_url
            self._status_label.setText("🟠 WebUI")
            self._load_url(url)

    def _load_url(self, url: str, load_workflow: bool = False):
        """URL을 웹뷰에 로드 (페이지를 새로 생성하여 이전 상태 완전 제거)"""
        self._current_url = url
        self._url_display.setText(url)
        self._load_workflow_after = load_workflow
        self._workflow_retry_count = 0

        # 페이지를 새로 생성하여 이전 JS/SPA 완전 제거
        self._recreate_page()

        # 로드 완료 시그널 연결
        self._page.loadFinished.connect(self._on_page_loaded)

        # URL 로드
        self._web_view.setUrl(QUrl(url))

    def _on_page_loaded(self, ok: bool):
        """페이지 로드 완료"""
        try:
            self._page.loadFinished.disconnect(self._on_page_loaded)
        except (TypeError, RuntimeError):
            pass

        if not ok:
            return

        # ComfyUI 모드: 워크플로우 자동 로드
        if self._load_workflow_after:
            self._load_workflow_after = False
            self._workflow_retry_count = 0
            # ComfyUI 프론트엔드 초기화 대기 후 워크플로우 주입
            QTimer.singleShot(2000, self._inject_comfyui_workflow)

    def _inject_comfyui_workflow(self):
        """ComfyUI 웹 인터페이스에 워크플로우 JSON을 주입"""
        import config
        workflow_path = getattr(config, 'COMFYUI_WORKFLOW_PATH', '')
        if not workflow_path or not os.path.exists(workflow_path):
            return

        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
        except Exception:
            return

        # JSON을 안전하게 이스케이프
        workflow_json_str = json.dumps(json.dumps(workflow_data, ensure_ascii=False))

        # ComfyUI app 객체를 확인하고 워크플로우 로드
        js_code = f"""
        (function() {{
            var workflowStr = {workflow_json_str};
            var workflow = JSON.parse(workflowStr);

            if (typeof app === 'undefined' || !app.graph) {{
                return 'NOT_READY';
            }}

            // API format 판별 (class_type 키가 있으면 API format)
            var isApiFormat = false;
            for (var key in workflow) {{
                if (workflow[key] && typeof workflow[key] === 'object' && workflow[key].class_type) {{
                    isApiFormat = true;
                    break;
                }}
            }}

            try {{
                if (isApiFormat && typeof app.loadApiJson === 'function') {{
                    app.loadApiJson(workflow);
                    return 'OK_API';
                }} else if (typeof app.loadGraphData === 'function') {{
                    app.loadGraphData(workflow);
                    return 'OK_GRAPH';
                }}
            }} catch(e) {{
                return 'ERROR:' + e.message;
            }}
            return 'NO_METHOD';
        }})();
        """
        self._page.runJavaScript(js_code, 0, self._on_workflow_inject_result)

    def _on_workflow_inject_result(self, result):
        """워크플로우 주입 결과 처리"""
        if result == 'NOT_READY':
            # ComfyUI 아직 초기화 안됨 — 재시도 (최대 10회)
            self._workflow_retry_count += 1
            if self._workflow_retry_count < 10:
                QTimer.singleShot(1000, self._inject_comfyui_workflow)

    def _reload(self):
        """현재 페이지 새로고침"""
        if self._current_url:
            self._web_view.reload()
        else:
            self.load_backend_ui()

    def _open_external(self):
        """외부 브라우저로 열기"""
        if self._current_url:
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(self._current_url))

    def _placeholder_html(self) -> str:
        return f"""
        <html>
        <body style="background:{get_color('bg_primary')}; color:{get_color('text_muted')}; display:flex;
                     align-items:center; justify-content:center; height:100vh;
                     font-family:sans-serif; margin:0;">
          <div style="text-align:center;">
            <div style="font-size:48px; margin-bottom:16px;">🖥️</div>
            <div style="font-size:16px;">백엔드에 연결되면 UI가 여기에 표시됩니다</div>
            <div style="font-size:13px; color:{get_color('border')}; margin-top:8px;">
              WebUI &nbsp;|&nbsp; ComfyUI
            </div>
          </div>
        </body>
        </html>
        """

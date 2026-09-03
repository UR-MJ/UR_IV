# ui/generator_webui.py
"""
API 연결 및 정보 로드 로직 (WebUI + ComfyUI 지원)
"""
import json
import os
import requests
from PyQt6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog,
    QFrame, QApplication
)
from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QPixmap

from backends import get_backend, set_backend, get_backend_type, BackendType
from workers.generation_worker import WebUIInfoWorker
from utils.theme_manager import get_color


class WebUIMixin:
    """API 연결 관련 로직을 담당하는 Mixin"""

    # ── 시작 시 백엔드 확인 ──

    def _startup_backend_check(self):
        """앱 시작 시 백엔드를 어떻게 고를지 정한다 (여기서는 아무것도 띄우지 않는다).

        **왜 모달을 안 띄우나**: 예전 순서는 '선택 모달 → 스플래시 → Vue 로드'라
        사용자가 앱 창을 보기도 전에 결정을 요구했다. 지금은 창을 먼저 띄우고 그 위에
        Vue 오버레이(게이트)를 얹는다 — 그래서 이 함수는 플래그만 세우고 즉시 돌아온다.
        실제 게이트 열기는 Vue 로드가 끝난 뒤 `_emit_backend_selection_required()`.

        **비상 경로는 그대로**: 아래 세 경우엔 예전처럼 QDialog(`_show_startup_selector`)
        를 쓴다. 오버레이를 그릴 수 있다는 보장이 없거나, 게이트가 어울리지 않는 맥락이다.
          - `_api_manager_mode` — 설정에서 연 API 관리자. 시작 게이트가 아니라 팝업이 맞다.
          - `web_mode` — 호스트 창에 QWebEngineView가 없다(브라우저가 프론트).
          - vue_bridge 부재 — 시그널을 보낼 곳이 없다.
        Vue 로드 자체가 실패(타임아웃)한 경우도 `_run_startup_sequence`가 이 selector로
        떨어뜨린다. 그 경로가 없으면 "Vue가 안 뜨면 백엔드를 영영 못 고른다"가 된다.
        """
        # 명시적으로 API 관리자 팝업을 연 경우에는 기존 URL selector를 그대로
        # 보여준다. 일반 startup만, 이미 설치된 active managed runtime의
        # auto-start가 켜진 managed runtime이 있을 때에 한해 modal을 생략한다.
        if not getattr(self, '_api_manager_mode', False):
            if self._try_managed_backend_autostart():
                return
            if self._can_use_backend_gate():
                self._backend_gate_pending = True
                self._backend_gate_awaiting = False
                self._backend_startup_result = 'gate_pending'
                return
        self._show_startup_selector()

    def _can_use_backend_gate(self) -> bool:
        """Vue 오버레이로 백엔드를 고를 수 있는 맥락인지."""
        if getattr(self, 'web_mode', False):
            return False
        if not hasattr(self, 'vue_bridge'):
            return False
        # setUrl 대상이 없으면 Vue가 아예 안 뜬다 → 오버레이도 못 그린다.
        return getattr(self, '_pending_vue_url', None) is not None

    def _try_managed_backend_autostart(self) -> bool:
        """설치된 auto-start managed runtime만 조용히 시작한다.

        start 전에 ``installed``를 확인하므로 이 경로는 다운로드·설치·업데이트를
        절대 유발하지 않는다. 실패해도 selector로 되돌아가 앱을 종료시키지 않고
        offline 상태로 이어간다.
        """
        if getattr(self, 'web_mode', False):
            # Web host는 로컬 파일/프로세스 mutator 권한이 없다.
            return False
        eligible = False
        try:
            from core.backend_runtime import get_backend_runtime_manager

            snapshot = get_backend_runtime_manager().snapshot()
            runtimes = snapshot.get('engines') if isinstance(snapshot, dict) else {}
            runtimes = runtimes if isinstance(runtimes, dict) else {}
            active = str(snapshot.get('activeEngine') or '') if isinstance(snapshot, dict) else ''
            if active == 'forge_neo':
                active = 'forge'
            auto_candidates = [
                engine for engine in ('forge', 'comfyui')
                if isinstance(runtimes.get(engine), dict)
                and bool(runtimes[engine].get('autoStart', False))
            ]
            kind = active if active in auto_candidates else (auto_candidates[0] if auto_candidates else '')
            runtime = runtimes.get(kind)
            runtime = runtime if isinstance(runtime, dict) else {}
            eligible = (
                kind in {'forge', 'comfyui'}
                and bool(runtime.get('installed', False))
            )
            if not eligible:
                return False

            ui_engine = kind
            self._backend_startup_result = 'managed_pending'
            self._managed_runtime_startup_inflight = True
            self._managed_runtime_startup_engine = ui_engine
            raw = self.vue_bridge.runBackendRuntimeOperation(
                ui_engine,
                'start',
                '{"startup": true}',
            )
            result = json.loads(raw or '{}')
            if result.get('accepted'):
                return True

            self._managed_runtime_startup_inflight = False
            self._backend_startup_result = 'managed_failed'
            self._managed_runtime_startup_error = str(
                result.get('error') or 'managed backend 시작 요청이 거부되었습니다'
            )
            return True
        except Exception as exc:
            if eligible:
                self._managed_runtime_startup_inflight = False
                self._backend_startup_result = 'managed_failed'
                self._managed_runtime_startup_error = str(exc)
                return True
            # core가 없거나 설정을 읽지 못한 경우에는 기존 selector가 안전한 폴백이다.
            print(f"[Runtime] managed auto-start 확인 실패(기존 selector 사용): {exc}")
            return False

    def _show_startup_selector(self):
        """앱 시작 화면 — 백엔드를 고르면 그것으로 확정한다.

        **왜 다시 그렸나**: 옛 화면은 카드마다 다른 색(WebUI 초록·ComfyUI 파랑)과
        이모지로 상태를 말했고, 버튼을 누르면 확인 상자가 한 번 더 떴다. 디자인
        시스템과 무관한 색이었고, 두 선택지가 서로 다른 색을 쓸 이유도 없었다.
        지금은 앱의 다른 화면과 같은 규칙이다 — 상자 대신 1px 헤어라인, 글자 크기
        16/13/12/11, 굵기 400·500·600, 간격은 4의 배수, 상태는 이모지가 아니라
        '연결됨'/'응답 없음' 같은 **글자**(색은 거들 뿐).

        **확인 상자를 없앤 이유**: 선택 자체가 확정이다. 대신 카드가 연결 상태를
        계속 보여주고, 연결된 쪽 버튼만 강조면(accent_fill)으로 칠해 어느 쪽이
        준비됐는지 눈으로도 알 수 있게 했다. 연결이 안 돼도 그대로 시작할 수 있는
        건 예전과 같다(오프라인 작업).

        색은 전부 get_color() 를 거친다 — 사용자가 고른 테마가 시작 화면에도 온다.
        """
        import config

        # 한 번만 읽어 아래 인라인 스타일에서 재사용 (다이얼로그가 떠 있는 동안 테마는 안 바뀐다)
        c_bg = get_color('bg_primary')
        c_text = get_color('text_primary')
        c_sub = get_color('text_secondary')
        c_muted = get_color('text_muted')
        c_rule = get_color('rule')
        c_edge = get_color('edge')
        c_border = get_color('border')
        c_input = get_color('bg_input')
        c_accent = get_color('accent')
        c_fill = get_color('accent_fill')
        c_fill_hover = get_color('accent_fill_hover')
        c_on_accent = get_color('on_accent')
        c_button = get_color('bg_button')
        c_button_hover = get_color('bg_button_hover')
        # 상태색은 배지 채움이 아니라 '글자'로 쓰므로 -fg 계열(get_color 의 success/error/warning).
        c_state_ok = get_color('success')
        c_state_alert = get_color('error')
        c_state_warn = get_color('warning')

        dialog = QDialog(self)
        dialog.setWindowTitle("백엔드 선택")
        dialog.setFixedSize(520, 540)
        dialog.setWindowFlags(
            dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {c_bg}; }}
            QLabel {{ color: {c_sub}; background: transparent; }}
            QLineEdit {{
                background: {c_input}; border: 1px solid {c_border}; border-radius: 4px;
                padding: 7px 10px; color: {c_text}; font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {c_accent}; }}
        """)

        # 간격은 addSpacing 으로 직접 준다 — setSpacing 을 쓰면 4의 배수 리듬이
        # 위젯마다 섞여서 눈에 보이는 간격이 제각각이 된다.
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(0)

        def hairline() -> QFrame:
            """섹션 구분 — 테두리 상자 대신 1px 선 하나."""
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background-color: {c_rule}; border: none;")
            return line

        def caption(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {c_muted}; font-size: 11px;")
            return lbl

        def make_header(name: str):
            """섹션 제목 + 상태 한 줄. (레이아웃, 상태 라벨)을 돌려준다."""
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            name_label = QLabel(name)
            name_label.setStyleSheet(f"color: {c_text}; font-size: 13px; font-weight: 500;")
            status = QLabel("확인 중")
            status.setStyleSheet(f"color: {c_muted}; font-size: 12px; font-weight: 500;")
            row.addWidget(name_label)
            row.addStretch()
            row.addWidget(status)
            return row, status

        def field_row(label_text: str, editor, trailing=None) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            label = caption(label_text)
            label.setFixedWidth(48)
            row.addWidget(label)
            row.addWidget(editor)
            if trailing is not None:
                row.addWidget(trailing)
            return row

        def set_status(label: QLabel, text: str, color: str):
            label.setText(text)
            label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 500;")

        def style_action(button: QPushButton, ready: bool):
            """연결된 쪽만 강조면으로. 색만으로 말하지 않도록 상태 글자와 함께 쓴다."""
            if ready:
                button.setStyleSheet(f"""
                    QPushButton {{
                        background: {c_fill}; color: {c_on_accent};
                        border: 1px solid {c_fill}; border-radius: 6px;
                        font-size: 13px; font-weight: 600;
                    }}
                    QPushButton:hover {{ background: {c_fill_hover}; border-color: {c_fill_hover}; }}
                """)
            else:
                button.setStyleSheet(f"""
                    QPushButton {{
                        background: {c_button}; color: {c_text};
                        border: 1px solid {c_border}; border-radius: 6px;
                        font-size: 13px; font-weight: 500;
                    }}
                    QPushButton:hover {{ background: {c_button_hover}; border-color: {c_edge}; }}
                """)

        # ── 헤더 ──
        # 전각 대문자 영문은 이 화면에서 여기 하나뿐. 나머지는 한국어.
        title = QLabel("AI STUDIO PRO")
        title.setStyleSheet(f"color: {c_text}; font-size: 16px; font-weight: 600;")
        # letter-spacing 은 QSS 에 없는 속성이라 QFont 로 준다.
        title_font = title.font()
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        title.setFont(title_font)
        layout.addWidget(title)

        layout.addSpacing(4)
        subtitle = QLabel("이미지 생성에 쓸 백엔드를 고르세요 (설정에서 변경 가능)")
        subtitle.setStyleSheet(f"color: {c_sub}; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(20)
        layout.addWidget(hairline())
        layout.addSpacing(20)

        webui_url = config.WEBUI_API_URL
        comfyui_url = getattr(config, 'COMFYUI_API_URL', 'http://127.0.0.1:8188')
        icon_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icons')

        # ── WebUI ──
        webui_header, webui_status = make_header("WebUI (A1111 / Forge)")
        layout.addLayout(webui_header)
        layout.addSpacing(12)

        webui_url_input = QLineEdit(webui_url)
        webui_url_input.setPlaceholderText("http://127.0.0.1:7860")
        layout.addLayout(field_row("주소", webui_url_input))
        layout.addSpacing(12)

        btn_select_webui = QPushButton("WebUI 로 시작")
        btn_select_webui.setFixedHeight(40)
        btn_select_webui.setCursor(Qt.CursorShape.PointingHandCursor)
        gradio_icon_path = os.path.join(icon_dir, 'gradio.png')
        if os.path.exists(gradio_icon_path):
            btn_select_webui.setIcon(QIcon(gradio_icon_path))
            btn_select_webui.setIconSize(QSize(20, 20))
        style_action(btn_select_webui, False)
        layout.addWidget(btn_select_webui)

        layout.addSpacing(20)
        layout.addWidget(hairline())
        layout.addSpacing(20)

        # ── ComfyUI ──
        comfyui_header, comfyui_status = make_header("ComfyUI")
        layout.addLayout(comfyui_header)
        layout.addSpacing(12)

        comfyui_url_input = QLineEdit(comfyui_url)
        comfyui_url_input.setPlaceholderText("http://127.0.0.1:8188")
        layout.addLayout(field_row("주소", comfyui_url_input))
        layout.addSpacing(8)

        workflow_input = QLineEdit(getattr(config, 'COMFYUI_WORKFLOW_PATH', ''))
        workflow_input.setPlaceholderText("JSON 파일 경로 (API Format)")
        btn_browse = QPushButton("찾아보기")
        btn_browse.setFixedHeight(32)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setStyleSheet(f"""
            QPushButton {{
                background: {c_button}; border: 1px solid {c_border}; border-radius: 4px;
                color: {c_sub}; font-size: 12px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: {c_button_hover}; color: {c_text}; }}
        """)
        layout.addLayout(field_row("워크플로", workflow_input, btn_browse))
        layout.addSpacing(8)

        # 워크플로 미리보기 — 파일을 열기 전에 뭐가 들었는지 알려 준다.
        startup_wf_preview = QLabel("")
        startup_wf_preview.setWordWrap(True)
        startup_wf_preview.setStyleSheet(f"color: {c_sub}; font-size: 11px;")
        startup_wf_preview.hide()
        layout.addWidget(startup_wf_preview)

        def update_startup_wf_preview(path: str):
            path = path.strip()
            if not path:
                startup_wf_preview.hide()
                return
            from backends.comfyui_backend import analyze_workflow
            info = analyze_workflow(path)
            if info.get('valid'):
                w, h = info.get('width', '?'), info.get('height', '?')
                cls = info.get('classification', 'unknown')
                cls_label = {
                    'native_checkpoint': 'Checkpoint',
                    'native_unet': 'UNet',
                    'locked_unknown': '커스텀',
                    'no_sampler': '샘플러 없음',
                    'unknown': '알 수 없음',
                }.get(cls, cls)
                # 모델 콤보가 잠기는지는 자물쇠 아이콘이 아니라 글자로 말한다.
                locked = info.get('is_locked')
                lock_label = '워크플로가 모델 고정' if locked else '모델 선택 가능'
                startup_wf_preview.setText(
                    f"{info['format'].upper()} · 노드 {info['node_count']}개 · "
                    f"{info.get('ksampler_type', '?')} · {w}×{h} · {cls_label} · {lock_label}"
                )
                startup_wf_preview.setStyleSheet(
                    f"color: {c_state_warn if locked else c_sub}; font-size: 11px;"
                )
            else:
                startup_wf_preview.setText(f"읽을 수 없음 — {info.get('error', '알 수 없는 오류')}")
                startup_wf_preview.setStyleSheet(f"color: {c_state_alert}; font-size: 11px;")
            startup_wf_preview.show()

        def browse_wf():
            path, _ = QFileDialog.getOpenFileName(
                dialog, "워크플로우 JSON 선택", "", "JSON Files (*.json);;All Files (*)"
            )
            if path:
                workflow_input.setText(path)
                update_startup_wf_preview(path)

        workflow_input.editingFinished.connect(lambda: update_startup_wf_preview(workflow_input.text()))
        btn_browse.clicked.connect(browse_wf)

        if workflow_input.text().strip():
            update_startup_wf_preview(workflow_input.text())

        layout.addSpacing(12)

        btn_select_comfyui = QPushButton("ComfyUI 로 시작")
        btn_select_comfyui.setFixedHeight(40)
        btn_select_comfyui.setCursor(Qt.CursorShape.PointingHandCursor)
        # 연결 전 기본 아이콘 — 감지가 끝나면 연결됨 아이콘으로 바뀐다.
        comfyui_icon_path = os.path.join(icon_dir, 'comfyui.png')
        if os.path.exists(comfyui_icon_path):
            btn_select_comfyui.setIcon(QIcon(comfyui_icon_path))
            btn_select_comfyui.setIconSize(QSize(20, 20))
        style_action(btn_select_comfyui, False)
        layout.addWidget(btn_select_comfyui)

        # ── 선택 = 확정 ──
        def choose_backend(backend_type: str):
            # 확정 절차 자체는 게이트(오버레이)와 공유한다 — 두 벌로 두면
            # 한쪽만 고쳐져 '고른 값과 설정 화면이 다른' 옛 버그가 돌아온다.
            self._commit_backend_choice(
                backend_type,
                webui_url_input.text().strip(),
                comfyui_url_input.text().strip(),
                workflow_input.text().strip(),
            )
            dialog.accept()

        btn_select_webui.clicked.connect(lambda: choose_backend('webui'))
        btn_select_comfyui.clicked.connect(lambda: choose_backend('comfyui'))

        # ── 자동 감지 (비동기 — UI 스레드를 막지 않는다) ──
        # _detect_version: URL 을 연달아 고치면 늦게 끝난 옛 검사가 새 결과를 덮어쓴다.
        import threading
        _detect_version = {'v': 0}

        def auto_detect():
            _detect_version['v'] += 1
            current_v = _detect_version['v']

            set_status(webui_status, "확인 중", c_muted)
            set_status(comfyui_status, "확인 중", c_muted)

            w_url = webui_url_input.text().strip()
            c_url = comfyui_url_input.text().strip()
            results = {'done': False}

            def _run():
                try:
                    results['w_ok'] = WebUIMixin._quick_test(w_url, '/sdapi/v1/samplers')
                    results['c_ok'] = WebUIMixin._quick_test(c_url, '/system_stats')
                except Exception:
                    results['w_ok'] = False
                    results['c_ok'] = False
                results['done'] = True

            def _poll():
                if current_v != _detect_version['v']:
                    return
                if not results['done']:
                    QTimer.singleShot(100, _poll)
                    return
                w_ok, c_ok = results['w_ok'], results['c_ok']
                set_status(webui_status, '연결됨' if w_ok else '응답 없음',
                           c_state_ok if w_ok else c_state_alert)
                set_status(comfyui_status, '연결됨' if c_ok else '응답 없음',
                           c_state_ok if c_ok else c_state_alert)
                style_action(btn_select_webui, w_ok)
                style_action(btn_select_comfyui, c_ok)
                # ComfyUI 아이콘: 연결 가능 → comfyui_icon.png, 연결 안됨 → comfyui.png
                icon_name = 'comfyui_icon.png' if c_ok else 'comfyui.png'
                new_icon_path = os.path.join(icon_dir, icon_name)
                if os.path.exists(new_icon_path):
                    btn_select_comfyui.setIcon(QIcon(new_icon_path))

            threading.Thread(target=_run, daemon=True).start()
            QTimer.singleShot(200, _poll)

        webui_url_input.editingFinished.connect(auto_detect)
        comfyui_url_input.editingFinished.connect(auto_detect)
        QTimer.singleShot(100, auto_detect)

        layout.addStretch()

        # ── 건너뛰기 ──
        layout.addSpacing(20)
        layout.addWidget(hairline())
        layout.addSpacing(16)

        btn_skip = QPushButton("백엔드 없이 시작")
        btn_skip.setToolTip("백엔드에 연결하지 않고 UI만 엽니다")
        btn_skip.setFixedHeight(32)
        btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_skip.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {c_muted};
                font-size: 12px; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {c_text}; }}
        """)

        skip_clicked = {'value': False}

        def on_skip():
            skip_clicked['value'] = True
            dialog.reject()

        btn_skip.clicked.connect(on_skip)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()
        btn_row.addWidget(btn_skip)
        layout.addLayout(btn_row)

        dialog.raise_()
        dialog.activateWindow()

        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            self._backend_startup_result = 'accepted'
        elif skip_clicked['value']:
            self._backend_startup_result = 'skipped'
        else:
            # X 버튼
            if getattr(self, '_api_manager_mode', False):
                # Settings에서 호출된 경우 — 취소만
                self._backend_startup_result = 'skipped'
            else:
                # 앱 시작 시 — 종료
                import sys
                sys.exit(0)

    # ── 시작 백엔드 게이트 (창 위의 Vue 오버레이) ──
    # QDialog 판과 같은 일을 하되, 결정 순간이 '앱을 보기 전'이 아니라
    # '앱을 본 다음'으로 옮겨졌을 뿐이다. 확정 절차(_commit_backend_choice)와
    # 감지(_quick_test)는 두 경로가 그대로 공유한다.

    def _commit_backend_choice(self, backend_type: str, webui_url: str,
                               comfy_url: str, workflow_path: str) -> None:
        """고른 백엔드를 backends·config·settings 탭에 한 번에 반영한다.

        set_backend()가 config.WEBUI_API_URL / COMFYUI_API_URL 을 이미 갱신하므로
        여기서 따로 대입하는 건 워크플로 경로뿐이다(set_backend가 모르는 값).
        settings 탭 동기화가 빠지면 "시작에서 고른 값과 설정 화면이 다르다"가 된다.
        """
        import config

        backend_type = 'comfyui' if backend_type == 'comfyui' else 'webui'
        webui_url = (webui_url or '').strip()
        comfy_url = (comfy_url or '').strip()
        workflow_path = (workflow_path or '').strip()

        if backend_type == 'comfyui':
            config.COMFYUI_WORKFLOW_PATH = workflow_path
            set_backend(BackendType.COMFYUI, comfy_url)
        else:
            set_backend(BackendType.WEBUI, webui_url)

        # settings 탭 동기화 — 고르지 않은 쪽 값도 같이 넣는다(설정 화면은 둘 다 보여준다).
        if hasattr(self, 'settings_tab'):
            st = self.settings_tab
            if hasattr(st, 'radio_webui'):
                st.radio_webui.setChecked(backend_type == 'webui')
                st.radio_comfyui.setChecked(backend_type == 'comfyui')
            if hasattr(st, 'api_input'):
                st.api_input.setText(webui_url)
            if hasattr(st, 'comfyui_api_input'):
                st.comfyui_api_input.setText(comfy_url)
            if hasattr(st, 'comfyui_workflow_input'):
                st.comfyui_workflow_input.setText(workflow_path)

    def _emit_backend_selection_required(self, attempt: int = 0) -> None:
        """게이트를 열라고 Vue에 알린다 — 짧게 몇 번 되풀이해서.

        **왜 되풀이하나**: loadFinished 는 '페이지가 떴다'까지만 보장한다.
        QWebChannel 핸드셰이크와 Vue 마운트는 그 뒤에 비동기로 끝나므로, 딱 한 번
        보내면 리스너가 붙기 전에 도착해 조용히 사라질 수 있다 — 그러면 게이트가
        영영 안 뜨고 앱이 백엔드 없이 멈춘 것처럼 보인다. 이 이벤트는 '게이트를
        열어라'라 여러 번 받아도 결과가 같으니(멱등) 재전송이 가장 싼 보험이다.
        사용자가 고르는 순간 `_backend_gate_pending` 이 내려가며 체인이 끊긴다.
        """
        if not getattr(self, '_backend_gate_pending', False):
            return  # 이미 골랐다 — 더 보낼 이유가 없다

        # 연결 시도 중이면 재전송을 건너뛴다(게이트의 '연결 중' 표시를 되돌리지 않게).
        if not getattr(self, '_backend_gate_awaiting', False):
            import config

            try:
                self.vue_bridge.backendSelectionRequired.emit(json.dumps({
                    'webuiUrl': getattr(config, 'WEBUI_API_URL', '') or '',
                    'comfyUrl': getattr(config, 'COMFYUI_API_URL', '') or 'http://127.0.0.1:8188',
                    'workflowPath': getattr(config, 'COMFYUI_WORKFLOW_PATH', '') or '',
                }))
            except Exception as exc:
                print(f"[Backend] 게이트 열기 신호 실패: {exc}")

        # 0.3s / 1.0s / 2.2s — Vue 마운트가 늦어도 세 번째 안에는 붙는다.
        retry_delays = (300, 700, 1200)
        if attempt < len(retry_delays):
            QTimer.singleShot(
                retry_delays[attempt],
                lambda: self._emit_backend_selection_required(attempt + 1),
            )

    def _probe_backends_async(self, webui_url: str, comfy_url: str) -> None:
        """두 백엔드 응답 여부를 백그라운드에서 확인하고 결과를 게이트로 보낸다.

        UI 스레드를 막지 않는다(HTTP 2초 × 2 = 최대 4초 프리징이 된다). 또 URL을
        연달아 고치면 늦게 끝난 옛 검사가 새 결과를 덮어쓰므로 세대 번호로 막는다 —
        QDialog 판의 auto_detect 와 같은 이유, 같은 방식이다.
        """
        import threading

        self._backend_probe_version = getattr(self, '_backend_probe_version', 0) + 1
        current_v = self._backend_probe_version
        results = {'done': False, 'w_ok': False, 'c_ok': False}

        def _run():
            try:
                results['w_ok'] = WebUIMixin._quick_test(webui_url, '/sdapi/v1/samplers')
                results['c_ok'] = WebUIMixin._quick_test(comfy_url, '/system_stats')
            except Exception:
                results['w_ok'] = False
                results['c_ok'] = False
            results['done'] = True

        def _poll():
            if current_v != getattr(self, '_backend_probe_version', 0):
                return  # 더 새로운 검사가 시작됐다 — 이 결과는 버린다
            if not results['done']:
                QTimer.singleShot(100, _poll)
                return
            try:
                self.vue_bridge.backendProbeResult.emit(json.dumps({
                    'webui': 'ok' if results['w_ok'] else 'fail',
                    'comfy': 'ok' if results['c_ok'] else 'fail',
                }))
            except Exception as exc:
                print(f"[Backend] 감지 결과 전송 실패: {exc}")

        threading.Thread(target=_run, daemon=True).start()
        QTimer.singleShot(200, _poll)

    def _pick_comfy_workflow(self) -> None:
        """워크플로 JSON 을 고르고, 내용 요약까지 함께 게이트로 보낸다.

        경로만 돌려주면 사용자는 '이 파일이 맞나'를 열어 보기 전엔 모른다.
        QDialog 판이 미리보기 한 줄을 보여줬던 이유와 같아서 analyze_workflow 를
        여기서 같이 돌린다(파일 파싱이라 게이트 쪽에서 다시 할 방법이 없다).
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "워크플로우 JSON 선택", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            from backends.comfyui_backend import analyze_workflow
            info = analyze_workflow(path)
        except Exception as exc:
            info = {'valid': False, 'error': str(exc)}
        try:
            self.vue_bridge.comfyWorkflowPicked.emit(json.dumps({
                'path': path, 'info': info,
            }))
        except Exception as exc:
            print(f"[Backend] 워크플로 선택 전송 실패: {exc}")

    def _select_backend_from_gate(self, payload: dict) -> None:
        """게이트에서 고른 백엔드로 확정하고 연결을 시작한다.

        연결 성공/실패는 여기서 알 수 없다 — info worker 가 스레드에서 돌기 때문.
        그래서 `_backend_gate_awaiting` 표식만 세우고, on_webui_info_loaded /
        on_webui_info_error 가 `_resolve_backend_gate()` 로 결론을 게이트에 돌려준다.
        (worker.start() 뒤에 시그널을 연결하면 빠른 로컬 백엔드에서 결과를 놓칠 수 있다.)
        """
        import config

        raw_type = str(payload.get('type') or 'webui').strip().lower()
        if raw_type in ('none', 'skip', 'offline', ''):
            # '백엔드 없이 시작' — 옛 QDialog 의 건너뛰기와 같은 결말. 연결을 시도할
            # 것이 없으니 info worker 를 기다리지 않고 바로 게이트를 걷는다.
            self._backend_gate_pending = False
            self._backend_gate_awaiting = False
            self._backend_startup_result = 'skipped'
            self._apply_backend_startup_result()
            self._emit_backend_selected(True)
            return

        backend_type = 'comfyui' if raw_type == 'comfyui' else 'webui'
        url = str(payload.get('url') or '').strip()
        workflow_path = str(payload.get('workflowPath') or '').strip()

        # 고르지 않은 쪽은 현재 설정값을 유지한다(게이트는 고른 쪽 URL만 보낸다).
        if backend_type == 'comfyui':
            comfy_url = url or getattr(config, 'COMFYUI_API_URL', '')
            webui_url = getattr(config, 'WEBUI_API_URL', '')
        else:
            webui_url = url or getattr(config, 'WEBUI_API_URL', '')
            comfy_url = getattr(config, 'COMFYUI_API_URL', '')

        try:
            self._commit_backend_choice(backend_type, webui_url, comfy_url, workflow_path)
        except Exception as exc:
            self._backend_gate_awaiting = False
            self._emit_backend_selected(False, f'백엔드 설정 실패: {exc}')
            return

        self._backend_gate_awaiting = True
        try:
            if hasattr(self, 'save_settings'):
                self.save_settings()
            self.load_webui_info()
        except Exception as exc:
            self._backend_gate_awaiting = False
            self._emit_backend_selected(False, str(exc))

    def _emit_backend_selected(self, ok: bool, error: str = '') -> None:
        payload = {'ok': bool(ok)}
        if not ok and error:
            payload['error'] = str(error)
        try:
            self.vue_bridge.backendSelected.emit(json.dumps(payload))
        except Exception as exc:
            print(f"[Backend] 게이트 결과 전송 실패: {exc}")

    # ── 하단 계기 스트립: 백엔드 · VRAM · 모델 중 '백엔드' 칸 ──
    # 게이트가 '고르기 전 한 번'이라면 이쪽은 앱이 사는 내내의 상태다.
    # 연결/실패/미연결이 모두 같은 채널로 가야 스트립이 한 값만 들고 있으면 된다.

    # 게이트 재전송과 같은 간격 — 이유도 같다(_emit_backend_status 주석 참고).
    _BACKEND_STATUS_RETRIES = (300, 700, 1200)

    @staticmethod
    def _backend_status_url() -> str:
        """지금 백엔드가 바라보는 주소. set_backend()가 config를 늘 갱신해 둔다."""
        import config

        if get_backend_type() == BackendType.COMFYUI:
            return str(getattr(config, 'COMFYUI_API_URL', '') or '')
        return str(getattr(config, 'WEBUI_API_URL', '') or '')

    def _remember_webui_label(self, info) -> None:
        """연결에 성공한 순간의 options 로 WebUI 계열의 표시 이름을 확정한다.

        **왜 options 인가**: Forge 계열은 자기 설정을 `forge_` 접두어로
        /sdapi/v1/options 에 등록한다 — 이 앱이 생성 페이로드에 이미 실어 보내는
        `forge_additional_modules` 가 그 중 하나다. A1111 에는 그런 키가 없다.
        반대로 'A1111 이다'라고 단정할 양성 표지는 어디에도 없다(reForge·SD.Next
        같은 포크도 같은 API 를 낸다). 그래서 표지가 보일 때만 'Forge' 라 부르고
        아니면 'WebUI' 로 둔다 — **틀린 이름은 모르는 것보다 나쁘다.**

        URL 을 함께 적어 두는 이유: 다른 주소로 갈아탄 뒤에도 이름이 남으면
        남의 서버를 Forge 라고 부르게 된다.
        """
        options = info.get('options') if isinstance(info, dict) else None
        label = 'WebUI'
        try:
            if isinstance(options, dict) and any(
                str(key).startswith('forge_') for key in options
            ):
                label = 'Forge'
        except Exception:
            pass
        self._webui_label = (self._backend_status_url(), label)

    def _emit_backend_status(self, connected: bool, error: str | None = None) -> None:
        """스트립이 읽을 백엔드 상태를 보내고, 짧게 몇 번 되풀이한다.

        **왜 되풀이하나**: 게이트(`_emit_backend_selection_required`)와 같은 이유다.
        loadFinished 는 '페이지가 떴다'까지만 보장하고 QWebChannel 핸드셰이크와 Vue
        마운트는 그 뒤에 비동기로 끝난다. 시작 직후의 첫 연결 결과를 한 번만 보내면
        리스너가 붙기 전에 도착해 조용히 사라지고, 스트립은 영영 빈 칸으로 남는다.
        전체 상태를 통째로 보내는 통보라 여러 번 받아도 결과가 같다(멱등).
        """
        is_comfy = get_backend_type() == BackendType.COMFYUI
        url = self._backend_status_url()
        if is_comfy:
            label = 'ComfyUI'
        else:
            # 이름의 근거는 연결됐을 때 본 options 뿐이다. 주소가 그때와 다르면
            # 그 근거는 남의 서버 것이므로 버리고 중립적인 'WebUI' 로 돌아간다.
            remembered = getattr(self, '_webui_label', None)
            label = (
                remembered[1]
                if isinstance(remembered, tuple) and remembered[0] == url
                else 'WebUI'
            )

        payload = {
            'kind': 'comfyui' if is_comfy else 'webui',
            'label': label,
            'url': url,
            'connected': bool(connected),
        }
        if not connected and error:
            payload['error'] = str(error)

        # 재전송은 '예약 당시'가 아니라 '지금'의 상태를 보내야 한다. payload 를 여기
        # 적어 두고 체인은 이 값을 읽는다 — 재전송 도중 연결이 바뀌었는데 옛 상태가
        # 되살아나면 스트립이 거짓말을 한다. 세대 번호로 낡은 체인은 끊는다.
        self._backend_status_payload = payload
        self._backend_status_gen = getattr(self, '_backend_status_gen', 0) + 1
        self._send_backend_status(self._backend_status_gen, 0)

    def _send_backend_status(self, generation: int, attempt: int) -> None:
        """현재 상태를 한 번 보내고, 세대가 그대로면 다음 재전송을 예약한다."""
        if generation != getattr(self, '_backend_status_gen', 0):
            return  # 더 새로운 상태가 나왔다 — 이 체인은 버린다
        payload = getattr(self, '_backend_status_payload', None)
        if not payload:
            return
        try:
            self.vue_bridge.backendStatus.emit(
                json.dumps(payload, ensure_ascii=False)
            )
        except Exception as exc:
            print(f"[Backend] 상태 전송 실패: {exc}")

        if attempt < len(self._BACKEND_STATUS_RETRIES):
            QTimer.singleShot(
                self._BACKEND_STATUS_RETRIES[attempt],
                lambda: self._send_backend_status(generation, attempt + 1),
            )

    def _resolve_backend_gate(self, ok: bool, error: str = '') -> bool:
        """게이트가 기다리던 연결 결과를 돌려준다. 처리했으면 True.

        실패해도 게이트는 **계속 떠 있어야 한다** — 그래야 주소를 고쳐 다시 시도할 수
        있다. 그래서 `_backend_gate_pending` 은 성공했을 때만 내린다.
        """
        if not getattr(self, '_backend_gate_awaiting', False):
            return False
        self._backend_gate_awaiting = False
        if ok:
            self._backend_gate_pending = False
            self._backend_startup_result = 'accepted'
        self._emit_backend_selected(ok, error)
        return True

    def _apply_backend_startup_result(self):
        """UI 생성 후 백엔드 선택 결과 적용"""
        result = getattr(self, '_backend_startup_result', None)
        if result == 'gate_pending':
            # 게이트가 뜬 상태 — 연결은 사용자가 고른 *뒤에* 돈다. 여기서 아무것도
            # 하지 않는 게 정상 경로다(시작 시퀀스 예외 폴백에서도 안전하게 통과).
            self._backend_connected = False
        elif result == 'accepted':
            if hasattr(self, 'save_settings'):
                self.save_settings()
            self.load_webui_info()
        elif result == 'skipped':
            self._backend_connected = False  # 폴링 안 함 (백엔드 버튼으로 연결 시 재개)
            self.viewer_label.setText(
                "백엔드에 연결되지 않았습니다.\n\n"
                "하단 도구 바의 '백엔드' 버튼으로 연결하세요."
            )
            # 이 경로는 info worker 를 아예 안 돌린다 — 여기서 안 알리면 스트립이
            # '아직 모름'과 '연결 안 함'을 구분하지 못한 채 영영 비어 있다.
            self._emit_backend_status(False, '백엔드에 연결하지 않고 시작했습니다')
        elif result == 'managed_pending':
            if not getattr(self, '_backend_connected', False):
                self.viewer_label.setText(
                    "앱 관리형 백엔드를 시작하는 중입니다…\n\n"
                    "설정에서 진행 상태를 확인할 수 있습니다."
                )
                self.btn_generate.setEnabled(False)
                # 아직 실패가 아니라 '시작 중'이라 error 는 붙이지 않는다 —
                # 곧 도착할 연결 성공/실패 통보가 이 값을 덮어쓴다.
                self._emit_backend_status(False)
        elif result == 'managed_connected':
            # runtime은 Vue보다 먼저 준비될 수 있다. 이 지점은 startup sequence가
            # Vue loadFinished를 기다린 뒤 호출되므로 초기 목록 push가 유실되지 않는다.
            self.load_webui_info()
        elif result == 'managed_failed':
            self._backend_connected = False
            error = str(getattr(self, '_managed_runtime_startup_error', '') or '')
            suffix = f"\n\n{error}" if error else ''
            self.viewer_label.setText(
                "앱 관리형 백엔드를 자동 시작하지 못했습니다.\n"
                "설정에서 다시 시작하거나 기존 API URL을 연결하세요."
                + suffix
            )
            # 자동 시작이 프로세스 단계에서 죽으면 info worker 가 돌지 않는다 —
            # on_webui_info_error 를 못 거치므로 실패를 여기서 직접 알린다.
            self._emit_backend_status(
                False, error or '앱 관리형 백엔드를 자동 시작하지 못했습니다'
            )

    @staticmethod
    def _quick_test(url: str, endpoint: str) -> bool:
        """빠른 연결 테스트 (타임아웃 2초)"""
        if not url:
            return False
        try:
            r = requests.get(f'{url.rstrip("/")}{endpoint}', timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def load_webui_info(self):
        """서버 정보 로드"""
        backend_name = "ComfyUI" if get_backend_type() == BackendType.COMFYUI else "WebUI"
        self.viewer_label.setText(f"{backend_name} 정보를 불러오는 중...")
        self.btn_generate.setEnabled(False)
        self.btn_random_prompt.setEnabled(False)

        # API 버튼: 연결 중 애니메이션
        if getattr(self, 'btn_api_manager', None):
            self.btn_api_manager.set_connecting(backend_name)

        # 이전 워커 정리
        if hasattr(self, 'info_worker') and self.info_worker is not None:
            try:
                self.info_worker.info_ready.disconnect()
                self.info_worker.error_occurred.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self.info_worker.isRunning():
                self.info_worker.quit()
                self.info_worker.wait(3000)

        self.info_worker = WebUIInfoWorker()
        self.info_worker.info_ready.connect(self.on_webui_info_loaded)
        self.info_worker.error_occurred.connect(self.on_webui_info_error)
        self.info_worker.start()

    def on_webui_info_loaded(self, info):
        """서버 정보 로드 완료"""
        self._managed_runtime_startup_inflight = False
        backend_name = "ComfyUI" if get_backend_type() == BackendType.COMFYUI else "WebUI"
        inventory_engine = "comfyui" if get_backend_type() == BackendType.COMFYUI else "forge"

        # 모델
        models = info.get('models', [])
        self.model_combo.clear()
        self.model_combo.addItems(models)
        # 값은 API가 받는 raw string 그대로 유지하고, 출처 구분은 별도 property로
        # 보낸다. 표시용 prefix를 모델명에 붙이면 실제 생성 요청이 깨진다.
        model_inventory = None
        try:
            from core.model_inventory import get_model_inventory

            model_inventory = get_model_inventory(active_engine=inventory_engine)
            model_option_groups = model_inventory.option_groups('checkpoints', models)
        except Exception as exc:
            print(f"[Models] 통합 인벤토리 로드 실패: {exc}")
            model_option_groups = []
        try:
            self.vue_bridge.pushWidgetProperty('model_combo', 'optionGroups', model_option_groups)
        except Exception:
            pass

        # 샘플러
        samplers = info.get('samplers', [])
        self.sampler_combo.clear()
        self.sampler_combo.addItems(samplers)

        # 스케줄러
        schedulers = info.get('schedulers', ['Automatic'])
        self.scheduler_combo.clear()
        self.scheduler_combo.addItems(schedulers)

        # 업스케일러
        upscalers = info.get('upscalers', [])
        self.upscaler_combo.clear()
        self.upscaler_combo.addItems(upscalers)

        # Hires Checkpoint / Sampler / Scheduler
        self.hires_checkpoint_combo.clear()
        self.hires_checkpoint_combo.addItems(["Use same checkpoint"] + models)
        self.hires_sampler_combo.clear()
        self.hires_sampler_combo.addItems(["Use same sampler"] + samplers)
        self.hires_scheduler_combo.clear()
        self.hires_scheduler_combo.addItems(["Use same scheduler"] + schedulers)

        # VAE
        vae_list = info.get('vae', ["Use same VAE"])
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['vae_combo'].clear()
            slot_widgets['vae_combo'].addItems(vae_list)

        # 메인 체크포인트 VAE / TE는 선택한 주 라이브러리 전체 + 보조 UI의
        # content-unique 파일을 사용한다. SAM3는 현재 Forge 전용 경로를 유지한다.
        try:
            from core.forge_modules import list_sam3_checkpoints

            vae_entries = model_inventory.entries('vae', backend_items=vae_list) if model_inventory else []
            te_entries = model_inventory.entries('text_encoders') if model_inventory else []
            disk_vae = [str(entry.get('runtimeName') or '') for entry in vae_entries]
            disk_te = [str(entry.get('runtimeName') or '') for entry in te_entries]
            disk_vae = [name for name in disk_vae if name]
            disk_te = [name for name in disk_te if name]
            disk_sam3 = list_sam3_checkpoints()
        except Exception:
            disk_vae, disk_te, disk_sam3 = [], [], []

        if disk_vae:
            main_vae_list = ["Use checkpoint default"] + disk_vae
        else:
            main_vae_list = ["Use checkpoint default"] + [
                v for v in vae_list if v not in ("Use same VAE", "Use checkpoint default")
            ]
        self.vae_main_combo.clear()
        self.vae_main_combo.addItems(main_vae_list)

        # SAM3 체크포인트 드롭다운 — models/sam3/sam3*.{pt,safetensors}
        if disk_sam3:
            sam3_ckpt_proxy = self.sam3_widgets.get('checkpoint') if hasattr(self, 'sam3_widgets') else None
            if sam3_ckpt_proxy is not None and hasattr(sam3_ckpt_proxy, 'clear'):
                try:
                    sam3_ckpt_proxy.clear()
                    sam3_ckpt_proxy.addItems(disk_sam3)
                except Exception:
                    pass

        # TE 파일 목록을 Vue로 전달 — 빈 목록도 보내야 설치/PRIMARY 전환 뒤
        # 이전 소스의 stale 항목이 남지 않는다.
        try:
            self.vue_bridge.pushWidgetProperty('te_main_input', 'items', disk_te)
        except Exception:
            pass

        # Checkpoint
        checkpoints = info.get('checkpoints', ["Use same checkpoint"])
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['checkpoint_combo'].clear()
            slot_widgets['checkpoint_combo'].addItems(checkpoints)

        # ADetailer 샘플러/스케줄러
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['sampler_combo'].clear()
            slot_widgets['sampler_combo'].addItems(["Use same sampler"] + samplers)
            slot_widgets['scheduler_combo'].clear()
            slot_widgets['scheduler_combo'].addItems(schedulers)

        # 저장된 설정 불러오기
        self.load_settings()

        # load_settings()는 저장된 TE chips를 다시 주입한다. 현재 통합
        # 인벤토리에 없는 파일은 생성 요청으로 흘러가지 않게 여기서 거른다.
        try:
            available_te = set(disk_te)
            current_te = [
                item.strip() for item in (self.te_main_input.text() or '').split(',')
                if item.strip()
            ]
            valid_te = [item for item in current_te if item in available_te]
            if valid_te != current_te:
                self.te_main_input.setText(', '.join(valid_te))
        except Exception:
            pass

        # ComfyUI: 워크플로우의 체크포인트를 자동 선택
        if get_backend_type() == BackendType.COMFYUI:
            self._auto_select_workflow_model(models)

        # UI 활성화 — 백엔드가 실제로 응답함 → 연결됨 표시(VRAM 폴링/LoRA 프리로드 재개)
        # 오프라인 상태에서 만들어진 merged LoRA 결과는 raw cache가 빈 배열인
        # 채로도 유효해 보일 수 있다. 연결 성공 경계에서 둘 다 무효화해 다음
        # 모달 오픈이 실제 백엔드 목록을 한 번 다시 읽게 한다.
        try:
            from widgets.lora_manager import LoraManagerDialog
            LoraManagerDialog._lora_cache = []
            self.vue_bridge._merged_lora_cache = None
        except Exception:
            pass
        self._backend_connected = True
        # 스트립에 '연결됨'을 알린다. 이름(Forge/WebUI)의 근거인 options 는 이
        # 순간에만 손에 있으므로 먼저 확정해 둔다 — 나중엔 다시 볼 수 없다.
        try:
            self._remember_webui_label(info)
            self._emit_backend_status(True)
        except Exception as exc:
            print(f"[Backend] 상태 통보 실패(무시): {exc}")
        self.btn_generate.setEnabled(True)
        self.viewer_label.setText(f"✅ {backend_name} 연결 완료!\n생성 버튼을 눌러 시작하세요.")
        self.show_status(
            f"✅ {backend_name} 연결 성공 | 모델: {len(models)}개 | 샘플러: {len(samplers)}개"
        )

        # API 버튼: 연결됨 애니메이션 (체크마크)
        if getattr(self, 'btn_api_manager', None):
            self.btn_api_manager.set_connected(backend_name)

        # 검색 기능 활성화
        if self.filtered_results:
            self.btn_random_prompt.setEnabled(True)

        # ComfyUI 모드일 때 미지원 기능 비활성화
        self._update_backend_ui_state()

        # Backend UI 탭은 여기서 **로드하지 않는다**. 예전엔 백엔드가 준비되는 순간
        # Forge/Comfy 웹 UI 전체를 숨은 웹뷰에 띄웠다 — 사용자는 앱 화면만 쓰는데
        # Gradio 페이지가 뒤에서 통째로 돌았다. 이제 탭을 실제로 열 때 로드한다
        # (generator_main `native_tab_switch`). 이미 열려 있던 페이지는 새 엔드포인트로
        # 갈아입힌다.
        if hasattr(self, 'backend_ui_tab'):
            self.backend_ui_tab.mark_backend_changed()

        # 시작 게이트는 여기서 걷힌다 — 목록이 다 채워진 뒤라 오버레이가 사라지는
        # 순간 빈 패널이 보이지 않는다.
        self._resolve_backend_gate(True)

    def on_webui_info_error(self, error_msg):
        """서버 정보 로드 실패"""
        managed_startup = bool(getattr(self, '_managed_runtime_startup_inflight', False))
        gate_awaiting = bool(getattr(self, '_backend_gate_awaiting', False))
        self._managed_runtime_startup_inflight = False
        self._backend_connected = False  # 폴링 중단 (다음 연결 성공 시 재개)
        backend_name = "ComfyUI" if get_backend_type() == BackendType.COMFYUI else "WebUI"
        api_url = get_backend().api_url

        # A runtime/source switch can fail after the previous backend populated
        # its model choices.  Clear values and grouping together so stale raw
        # names can never be sent to the newly selected backend.
        self.btn_generate.setEnabled(False)
        self.btn_random_prompt.setEnabled(False)
        self.model_combo.clear()
        self.hires_checkpoint_combo.clear()
        self.vae_main_combo.clear()
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['checkpoint_combo'].clear()
            slot_widgets['vae_combo'].clear()
        try:
            self.vue_bridge.pushWidgetProperty('model_combo', 'optionGroups', [])
            self.vue_bridge.pushWidgetProperty('te_main_input', 'items', [])
        except Exception:
            pass

        self.viewer_label.setText(
            f"❌ {backend_name} 연결 실패\n\n{error_msg}\n\n"
            f"현재 URL: {api_url}\n\n"
            f"설정 탭에서 API 주소를 확인하세요."
        )
        self.show_status(f"❌ {backend_name} 연결 실패: {error_msg}")

        # API 버튼: 실패 애니메이션 (흔들림 + X)
        if getattr(self, 'btn_api_manager', None):
            self.btn_api_manager.set_failed(backend_name)

        # 연결 실패 시에도 탭을 열면 그때 시도한다 (웹 인터페이스 직접 접근용)
        if hasattr(self, 'backend_ui_tab'):
            self.backend_ui_tab.mark_backend_changed()

        # 게이트가 기다리던 연결이면 결과를 오버레이로 돌려준다(게이트는 계속 떠 있다).
        self._resolve_backend_gate(False, error_msg)

        # 스트립에도 실패를 알린다 — 게이트를 이미 지난 뒤(연결 끊김·URL 변경)엔
        # 이 통보가 사용자가 상태를 알 수 있는 유일한 경로다.
        try:
            self._emit_backend_status(False, error_msg)
        except Exception as exc:
            print(f"[Backend] 상태 통보 실패(무시): {exc}")

        # startup auto-start 실패는 modal/종료 없이 offline UI로 폴백한다.
        # 게이트 경로도 마찬가지 — 오버레이가 이미 오류를 보여주는데 그 위에
        # QMessageBox 를 또 띄우면 사용자가 두 번 닫아야 다시 시도할 수 있다.
        if not managed_startup and not gate_awaiting:
            QMessageBox.critical(
                self, "연결 실패",
                f"{backend_name} API 연결에 실패했습니다.\n\n"
                f"오류: {error_msg}\n\n"
                f"현재 URL: {api_url}\n\n"
                f"1. {backend_name}가 실행 중인지 확인하세요.\n"
                f"2. API 주소가 올바른지 확인하세요.\n"
                f"3. 방화벽 설정을 확인하세요."
            )

    def retry_connection(self, new_url=None):
        """연결 재시도"""
        if new_url:
            backend_type = get_backend_type()
            set_backend(backend_type, new_url.strip())

        QTimer.singleShot(500, self.load_webui_info)

    def check_webui_connection(self):
        """연결 상태 확인"""
        try:
            return get_backend().test_connection()
        except Exception:
            return False

    def _update_backend_ui_state(self):
        """백엔드에 따라 UI 기능 활성화/비활성화"""
        is_comfyui = get_backend_type() == BackendType.COMFYUI
        comfyui_tip = "AI Studio Forge 호환 ComfyUI 워크플로우로 실행됩니다"

        # ComfyUI도 앱 소유 워크플로 컴파일러와 Forge 호환 custom node를
        # 사용하므로 같은 기능을 노출한다. 활성 옵션이 서버에 없으면 compiler가
        # 조용히 무시하지 않고 필요한 node 이름과 함께 명시적으로 실패한다.
        if hasattr(self, 'adetailer_group'):
            self.adetailer_group.setEnabled(True)
            self.adetailer_group.setToolTip(comfyui_tip if is_comfyui else "")

        if hasattr(self, 'sam3_group'):
            self.sam3_group.setEnabled(True)
            self.sam3_group.setToolTip(comfyui_tip if is_comfyui else "")

        if hasattr(self, 'negpip_group'):
            self.negpip_group.setEnabled(True)

        if hasattr(self, 'hires_options_group'):
            self.hires_options_group.setEnabled(True)
            self.hires_options_group.setToolTip(comfyui_tip if is_comfyui else "")

        # T2I/I2I/Inpaint/Upscale 모두 동일 compiler 경로를 사용한다.
        if hasattr(self, 'center_tabs'):
            generation_tabs = []
            if hasattr(self, 'i2i_tab'):
                generation_tabs.append(self.i2i_tab)
            if hasattr(self, 'inpaint_tab'):
                generation_tabs.append(self.inpaint_tab)
            if hasattr(self, 'upscale_tab'):
                generation_tabs.append(self.upscale_tab)

            for tab in generation_tabs:
                try:
                    idx = self.center_tabs.indexOf(tab)
                    if idx is not None and idx >= 0:
                        self.center_tabs.setTabEnabled(idx, True)
                except (TypeError, AttributeError):
                    pass  # Vue 모드에서는 center_tabs가 더미

    def _auto_select_workflow_model(self, available_models: list):
        """ComfyUI 워크플로우에 설정된 체크포인트를 모델 콤보박스에서 자동 선택.

        WorkflowInspector가 LOCKED_UNKNOWN으로 분류한 경우 (GGUF, NF4 등 커스텀 로더):
        - 모델 콤보 비활성화 (사용자가 잘못 바꾸지 못하게)
        - 자동 선택 안 함
        - 사용자에게 노티
        """
        import config
        wf_path = getattr(config, 'COMFYUI_WORKFLOW_PATH', '')
        if not wf_path:
            return

        from backends.comfyui_backend import analyze_workflow
        info = analyze_workflow(wf_path)

        # 3-state 분류 처리
        is_locked = info.get('is_locked', False)
        classification = info.get('classification', 'unknown')

        if is_locked:
            # 커스텀 로더 — 모델 선택 비활성화
            try:
                self.model_combo.setEnabled(False)
                self.model_combo.setToolTip(
                    f"이 워크플로우는 커스텀 모델 로더('{info.get('model_class', '?')}')를\n"
                    f"사용해서 UR_IV에서 모델을 바꿀 수 없습니다.\n"
                    f"워크플로우 JSON을 직접 편집해주세요."
                )
                # Vue로도 알림
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.showNotification.emit(
                        'warning',
                        f"커스텀 로더 감지: {info.get('model_class', '?')} — 모델 선택 비활성"
                    )
            except Exception:
                pass
            return

        # 표준 로더 — 콤보 활성화 + 자동 선택
        try:
            self.model_combo.setEnabled(True)
            self.model_combo.setToolTip("")
        except Exception:
            pass

        ckpt = info.get('checkpoint')
        if not ckpt:
            return

        # 정확히 일치하는 모델 찾기
        idx = self.model_combo.findText(ckpt)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
            return

        # 부분 일치 (파일명만 비교)
        ckpt_base = os.path.basename(ckpt).lower()
        for i in range(self.model_combo.count()):
            model_name = self.model_combo.itemText(i)
            if os.path.basename(model_name).lower() == ckpt_base:
                self.model_combo.setCurrentIndex(i)
                return

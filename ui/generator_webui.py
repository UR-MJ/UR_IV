# ui/generator_webui.py
"""
API 연결 및 정보 로드 로직 (WebUI + ComfyUI 지원)
"""
import os
import requests
from PyQt6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QGroupBox, QFileDialog,
    QButtonGroup, QFrame, QApplication
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
        """앱 시작 시 백엔드 선택 다이얼로그 표시"""
        self._show_startup_selector()

    def _show_startup_selector(self):
        import config

        dialog = QDialog(self)
        dialog.setWindowTitle("API 백엔드 선택")
        dialog.setFixedSize(560, 620)
        dialog.setWindowFlags(
            dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {get_color('bg_primary')}; color: {get_color('text_primary')}; }}
            QGroupBox {{
                border: 1px solid {get_color('border')}; border-radius: 8px;
                margin-top: 12px; padding: 16px; padding-top: 28px;
                font-weight: bold; color: {get_color('text_secondary')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 16px; padding: 0 8px;
            }}
            QLineEdit {{
                background: {get_color('bg_input')}; border: 1px solid {get_color('border')}; border-radius: 4px;
                padding: 6px 10px; color: {get_color('text_primary')};
            }}
            QLineEdit:focus {{ border: 1px solid {get_color('accent')}; }}
            QLabel {{ color: {get_color('text_secondary')}; }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 헤더
        header = QLabel("🚀 AI Studio Pro")
        header.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 18px; font-weight: bold;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        sub_header = QLabel("사용할 이미지 생성 백엔드를 선택하세요")
        sub_header.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 13px;")
        sub_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub_header)

        # URL 설정
        webui_url = config.WEBUI_API_URL
        comfyui_url = getattr(config, 'COMFYUI_API_URL', 'http://127.0.0.1:8188')

        # 선택 상태 저장
        selected_backend = {'type': None}

        # ── WebUI 카드 ──
        webui_group = QGroupBox("WebUI (A1111 / Forge)")
        wg_layout = QVBoxLayout(webui_group)

        webui_status = QLabel("⏳ 자동 감지 중...")
        webui_status.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 12px;")
        wg_layout.addWidget(webui_status)

        h_webui = QHBoxLayout()
        h_webui.addWidget(QLabel("URL:"))
        webui_url_input = QLineEdit(webui_url)
        webui_url_input.setPlaceholderText("http://127.0.0.1:7860")
        h_webui.addWidget(webui_url_input)
        wg_layout.addLayout(h_webui)

        # WebUI 선택 버튼
        btn_select_webui = QPushButton("  WebUI 사용하기")
        btn_select_webui.setFixedHeight(50)
        btn_select_webui.setCursor(Qt.CursorShape.PointingHandCursor)

        # Gradio 아이콘 로드
        icon_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icons')
        gradio_icon_path = os.path.join(icon_dir, 'gradio.png')
        if os.path.exists(gradio_icon_path):
            btn_select_webui.setIcon(QIcon(gradio_icon_path))
            btn_select_webui.setIconSize(QSize(28, 28))

        btn_select_webui.setStyleSheet("""
            QPushButton {
                background: #2d4a2d; border: 2px solid #4a9f4a; border-radius: 8px;
                color: #8eff8e; font-weight: bold; font-size: 14px;
                padding-left: 10px; text-align: left;
            }
            QPushButton:hover {
                background: #3d6a3d; border: 2px solid #6fbf6f;
            }
            QPushButton:pressed {
                background: #1d3a1d; border: 2px solid #3a8f3a;
            }
        """)
        wg_layout.addWidget(btn_select_webui)
        layout.addWidget(webui_group)

        # ── ComfyUI 카드 ──
        comfyui_group = QGroupBox("ComfyUI")
        cg_layout = QVBoxLayout(comfyui_group)

        comfyui_status = QLabel("⏳ 자동 감지 중...")
        comfyui_status.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 12px;")
        cg_layout.addWidget(comfyui_status)

        h_comfy_url = QHBoxLayout()
        h_comfy_url.addWidget(QLabel("URL:"))
        comfyui_url_input = QLineEdit(comfyui_url)
        comfyui_url_input.setPlaceholderText("http://127.0.0.1:8188")
        h_comfy_url.addWidget(comfyui_url_input)
        cg_layout.addLayout(h_comfy_url)

        h_wf = QHBoxLayout()
        h_wf.addWidget(QLabel("워크플로우:"))
        workflow_input = QLineEdit(getattr(config, 'COMFYUI_WORKFLOW_PATH', ''))
        workflow_input.setPlaceholderText("JSON 파일 경로 (API Format)")
        h_wf.addWidget(workflow_input)
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(36)
        btn_browse.setStyleSheet(f"""
            QPushButton {{
                background: {get_color('bg_button')}; border: 1px solid {get_color('border')}; border-radius: 4px; color: {get_color('text_primary')};
            }}
            QPushButton:hover {{ background: {get_color('bg_button_hover')}; }}
        """)
        h_wf.addWidget(btn_browse)
        cg_layout.addLayout(h_wf)

        # 워크플로우 미리보기
        startup_wf_preview = QLabel("")
        startup_wf_preview.setWordWrap(True)
        startup_wf_preview.setStyleSheet("font-size: 10px; padding: 4px;")
        startup_wf_preview.hide()
        cg_layout.addWidget(startup_wf_preview)

        def update_startup_wf_preview(path: str):
            path = path.strip()
            if not path:
                startup_wf_preview.hide()
                return
            from backends.comfyui_backend import analyze_workflow
            info = analyze_workflow(path)
            if info.get('valid'):
                w, h = info.get('width', '?'), info.get('height', '?')
                startup_wf_preview.setText(
                    f"✅ {info['format'].upper()} | 노드 {info['node_count']}개 | "
                    f"{info.get('ksampler_type', '?')} | {w}x{h}"
                )
                startup_wf_preview.setStyleSheet("font-size: 10px; padding: 4px; color: #4ade80;")
            else:
                startup_wf_preview.setText(f"❌ {info.get('error', '알 수 없는 오류')}")
                startup_wf_preview.setStyleSheet("font-size: 10px; padding: 4px; color: #f87171;")
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

        # ComfyUI 선택 버튼
        btn_select_comfyui = QPushButton("  ComfyUI 사용하기")
        btn_select_comfyui.setFixedHeight(50)
        btn_select_comfyui.setCursor(Qt.CursorShape.PointingHandCursor)

        # ComfyUI 아이콘 로드 (초기: 연결 전 기본 아이콘)
        comfyui_icon_path = os.path.join(icon_dir, 'comfyui.png')
        if os.path.exists(comfyui_icon_path):
            btn_select_comfyui.setIcon(QIcon(comfyui_icon_path))
            btn_select_comfyui.setIconSize(QSize(28, 28))

        btn_select_comfyui.setStyleSheet("""
            QPushButton {
                background: #2d3a5a; border: 2px solid #4a6f9f; border-radius: 8px;
                color: #8ec8ff; font-weight: bold; font-size: 14px;
                padding-left: 10px; text-align: left;
            }
            QPushButton:hover {
                background: #3d5a7a; border: 2px solid #6f9fbf;
            }
            QPushButton:pressed {
                background: #1d2a4a; border: 2px solid #3a5f8f;
            }
        """)
        cg_layout.addWidget(btn_select_comfyui)
        layout.addWidget(comfyui_group)

        # 연결 확인 다이얼로그
        def confirm_and_connect(backend_type: str):
            if backend_type == 'webui':
                url = webui_url_input.text().strip()
                name = "WebUI (A1111/Forge)"
                is_ok = self._quick_test(url, '/sdapi/v1/samplers')
            else:
                url = comfyui_url_input.text().strip()
                name = "ComfyUI"
                is_ok = self._quick_test(url, '/system_stats')

            # 확인 다이얼로그
            confirm = QMessageBox(dialog)
            confirm.setWindowTitle("연결 확인")
            confirm.setIcon(QMessageBox.Icon.Question)
            confirm.setWindowFlags(confirm.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

            status_text = "🟢 연결 가능" if is_ok else "🔴 연결되지 않음"
            confirm.setText(f"<b>{name}</b>에 연결하시겠습니까?")
            confirm.setInformativeText(f"URL: {url}\n상태: {status_text}")
            confirm.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            confirm.setDefaultButton(QMessageBox.StandardButton.Yes)

            # 버튼 스타일
            confirm.setStyleSheet(f"""
                QMessageBox {{ background-color: {get_color('bg_primary')}; color: {get_color('text_primary')}; }}
                QLabel {{ color: {get_color('text_primary')}; font-size: 13px; }}
                QPushButton {{
                    background: {get_color('bg_button')}; border: 1px solid {get_color('border')}; border-radius: 4px;
                    padding: 8px 20px; color: {get_color('text_primary')}; min-width: 80px;
                }}
                QPushButton:hover {{ background: {get_color('bg_button_hover')}; }}
                QPushButton:default {{
                    background: {get_color('accent')}; border: none; color: white;
                }}
            """)

            if confirm.exec() == QMessageBox.StandardButton.Yes:
                selected_backend['type'] = backend_type
                if backend_type == 'comfyui':
                    config.COMFYUI_API_URL = url
                    config.COMFYUI_WORKFLOW_PATH = workflow_input.text().strip()
                    set_backend(BackendType.COMFYUI, url)
                else:
                    set_backend(BackendType.WEBUI, url)

                # settings 탭 동기화
                if hasattr(self, 'settings_tab'):
                    st = self.settings_tab
                    if hasattr(st, 'radio_webui'):
                        st.radio_webui.setChecked(backend_type == 'webui')
                        st.radio_comfyui.setChecked(backend_type == 'comfyui')
                    if hasattr(st, 'api_input'):
                        st.api_input.setText(webui_url_input.text().strip())
                    if hasattr(st, 'comfyui_api_input'):
                        st.comfyui_api_input.setText(comfyui_url_input.text().strip())
                    if hasattr(st, 'comfyui_workflow_input'):
                        st.comfyui_workflow_input.setText(workflow_input.text().strip())

                dialog.accept()

        btn_select_webui.clicked.connect(lambda: confirm_and_connect('webui'))
        btn_select_comfyui.clicked.connect(lambda: confirm_and_connect('comfyui'))

        # 자동 감지 함수 (비동기 — UI 스레드 차단 방지)
        import threading
        _detect_version = {'v': 0}

        def auto_detect():
            _detect_version['v'] += 1
            current_v = _detect_version['v']

            webui_status.setText("⏳ 감지 중...")
            comfyui_status.setText("⏳ 감지 중...")

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
                webui_status.setText('🟢 연결 가능' if w_ok else '🔴 연결 안됨')
                webui_status.setStyleSheet(
                    f"color: {'#4ade80' if w_ok else '#f87171'}; font-weight: bold; font-size: 12px;"
                )
                comfyui_status.setText('🟢 연결 가능' if c_ok else '🔴 연결 안됨')
                comfyui_status.setStyleSheet(
                    f"color: {'#4ade80' if c_ok else '#f87171'}; font-weight: bold; font-size: 12px;"
                )
                # ComfyUI 아이콘: 연결 가능 → comfyui_icon.png, 연결 안됨 → comfyui.png
                icon_name = 'comfyui_icon.png' if c_ok else 'comfyui.png'
                new_icon_path = os.path.join(icon_dir, icon_name)
                if os.path.exists(new_icon_path):
                    btn_select_comfyui.setIcon(QIcon(new_icon_path))

            threading.Thread(target=_run, daemon=True).start()
            QTimer.singleShot(200, _poll)

        # URL 변경 시 자동 감지
        webui_url_input.editingFinished.connect(auto_detect)
        comfyui_url_input.editingFinished.connect(auto_detect)

        # 다이얼로그 표시 직후 자동 감지 실행
        QTimer.singleShot(100, auto_detect)

        layout.addStretch()

        # 하단 건너뛰기 버튼
        btn_row = QHBoxLayout()
        btn_skip = QPushButton("⏭️ 건너뛰기")
        btn_skip.setToolTip("백엔드 연결 없이 UI 시작")
        btn_skip.setStyleSheet(f"""
            QPushButton {{
                background: {get_color('bg_tertiary')}; border: 1px solid {get_color('border')}; border-radius: 6px;
                padding: 10px 24px; color: {get_color('text_muted')};
            }}
            QPushButton:hover {{ background: {get_color('bg_button')}; color: {get_color('text_secondary')}; }}
        """)

        # 건너뛰기 플래그
        skip_clicked = {'value': False}

        def on_skip():
            skip_clicked['value'] = True
            dialog.reject()

        btn_skip.clicked.connect(on_skip)
        btn_row.addStretch()
        btn_row.addWidget(btn_skip)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 다이얼로그 활성화
        dialog.raise_()
        dialog.activateWindow()

        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            self._backend_startup_result = 'accepted'
        elif skip_clicked['value']:
            self._backend_startup_result = 'skipped'
        else:
            # X 버튼 — 앱 종료
            import sys
            sys.exit(0)

    def _apply_backend_startup_result(self):
        """UI 생성 후 백엔드 선택 결과 적용"""
        result = getattr(self, '_backend_startup_result', None)
        if result == 'accepted':
            if hasattr(self, 'save_settings'):
                self.save_settings()
            self.load_webui_info()
        elif result == 'skipped':
            self.viewer_label.setText(
                "백엔드에 연결되지 않았습니다.\n\n"
                "하단 도구 바의 '백엔드' 버튼으로 연결하세요."
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
        backend_name = "ComfyUI" if get_backend_type() == BackendType.COMFYUI else "WebUI"

        # 모델
        models = info.get('models', [])
        self.model_combo.clear()
        self.model_combo.addItems(models)

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

        # ComfyUI: 워크플로우의 체크포인트를 자동 선택
        if get_backend_type() == BackendType.COMFYUI:
            self._auto_select_workflow_model(models)

        # UI 활성화
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

        # Backend UI 탭 로드
        if hasattr(self, 'backend_ui_tab'):
            self.backend_ui_tab.load_backend_ui()

    def on_webui_info_error(self, error_msg):
        """서버 정보 로드 실패"""
        backend_name = "ComfyUI" if get_backend_type() == BackendType.COMFYUI else "WebUI"
        api_url = get_backend().api_url

        self.viewer_label.setText(
            f"❌ {backend_name} 연결 실패\n\n{error_msg}\n\n"
            f"현재 URL: {api_url}\n\n"
            f"설정 탭에서 API 주소를 확인하세요."
        )
        self.show_status(f"❌ {backend_name} 연결 실패: {error_msg}")

        # API 버튼: 실패 애니메이션 (흔들림 + X)
        if getattr(self, 'btn_api_manager', None):
            self.btn_api_manager.set_failed(backend_name)

        # 연결 실패해도 Backend UI 탭은 전환 (웹 인터페이스 직접 접근용)
        if hasattr(self, 'backend_ui_tab'):
            self.backend_ui_tab.load_backend_ui()

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
        comfyui_tip = "ComfyUI에서는 워크플로우에서 직접 설정하세요"

        # ComfyUI에서 미지원 기능 비활성화
        if hasattr(self, 'adetailer_group'):
            self.adetailer_group.setEnabled(not is_comfyui)
            self.adetailer_group.setToolTip(comfyui_tip if is_comfyui else "")

        if hasattr(self, 'negpip_group'):
            self.negpip_group.setEnabled(not is_comfyui)

        if hasattr(self, 'hires_options_group'):
            self.hires_options_group.setEnabled(not is_comfyui)
            self.hires_options_group.setToolTip(comfyui_tip if is_comfyui else "")

        # I2I / Inpaint / Upscale 탭 비활성화 (ComfyUI 미지원)
        if hasattr(self, 'center_tabs'):
            unsupported_tabs = []
            if hasattr(self, 'i2i_tab'):
                unsupported_tabs.append(self.i2i_tab)
            if hasattr(self, 'inpaint_tab'):
                unsupported_tabs.append(self.inpaint_tab)
            if hasattr(self, 'upscale_tab'):
                unsupported_tabs.append(self.upscale_tab)

            for tab in unsupported_tabs:
                idx = self.center_tabs.indexOf(tab)
                if idx >= 0:
                    self.center_tabs.setTabEnabled(idx, not is_comfyui)
                    if is_comfyui:
                        self.center_tabs.setTabToolTip(idx, comfyui_tip)
                    else:
                        self.center_tabs.setTabToolTip(idx, "")

    def _auto_select_workflow_model(self, available_models: list):
        """ComfyUI 워크플로우에 설정된 체크포인트를 모델 콤보박스에서 자동 선택"""
        import config
        wf_path = getattr(config, 'COMFYUI_WORKFLOW_PATH', '')
        if not wf_path:
            return

        from backends.comfyui_backend import analyze_workflow
        info = analyze_workflow(wf_path)
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

    # ── API 관리 팝업 ──

    def _show_api_manager_popup(self):
        """API 백엔드 관리 팝업 표시"""
        import config

        dialog = QDialog(self)
        dialog.setWindowTitle("API 백엔드 관리")
        dialog.setMinimumWidth(480)
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')}; }}
            QGroupBox {{
                border: 1px solid {get_color('border')}; border-radius: 8px;
                margin-top: 14px; padding: 14px; padding-top: 28px;
                font-weight: bold; color: {get_color('text_secondary')}; font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 14px; padding: 0 8px;
            }}
            QGroupBox:!enabled {{
                border-color: {get_color('border')}; color: {get_color('disabled_text')};
            }}
            QLabel {{ color: {get_color('text_secondary')}; }}
            QLabel:disabled {{ color: {get_color('disabled_text')}; }}
            QLineEdit {{
                background: {get_color('bg_input')}; border: 1px solid {get_color('border')}; border-radius: 4px;
                padding: 6px 10px; color: {get_color('text_primary')}; font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {get_color('accent')}; }}
            QLineEdit:disabled {{ background: {get_color('disabled_bg')}; color: {get_color('disabled_text')}; border-color: {get_color('border')}; }}
            QRadioButton {{
                color: {get_color('text_secondary')}; spacing: 8px; font-size: 13px; padding: 6px 4px;
            }}
            QRadioButton::indicator {{
                width: 18px; height: 18px; border-radius: 9px;
                border: 2px solid {get_color('text_muted')}; background: {get_color('bg_input')};
            }}
            QRadioButton::indicator:hover {{
                border-color: {get_color('accent')};
            }}
            QRadioButton::indicator:checked {{
                border-color: {get_color('accent')}; background: {get_color('accent')};
            }}
            QRadioButton:hover {{ color: {get_color('text_primary')}; }}
            QPushButton {{
                background: {get_color('bg_button')}; border: 1px solid {get_color('border')}; border-radius: 5px;
                padding: 6px 16px; color: {get_color('text_primary')}; font-size: 12px;
            }}
            QPushButton:hover {{ background: {get_color('bg_button_hover')}; border-color: {get_color('text_muted')}; }}
            QPushButton:pressed {{ background: {get_color('bg_tertiary')}; }}
        """)
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 백엔드 선택
        select_group = QGroupBox("백엔드 선택")
        select_layout = QVBoxLayout(select_group)
        select_layout.setSpacing(4)

        btn_group = QButtonGroup(dialog)
        radio_webui = QRadioButton("WebUI (A1111 / Forge)")
        radio_comfyui = QRadioButton("ComfyUI")
        btn_group.addButton(radio_webui)
        btn_group.addButton(radio_comfyui)

        current_type = get_backend_type()
        radio_webui.setChecked(current_type == BackendType.WEBUI)
        radio_comfyui.setChecked(current_type == BackendType.COMFYUI)

        select_layout.addWidget(radio_webui)
        select_layout.addWidget(radio_comfyui)
        main_layout.addWidget(select_group)

        # WebUI 설정
        webui_group = QGroupBox("WebUI API")
        webui_layout = QHBoxLayout(webui_group)
        webui_url_input = QLineEdit(config.WEBUI_API_URL)
        webui_url_input.setPlaceholderText("http://127.0.0.1:7860")
        webui_layout.addWidget(QLabel("URL:"))
        webui_layout.addWidget(webui_url_input)
        main_layout.addWidget(webui_group)

        # ComfyUI 설정
        comfyui_group = QGroupBox("ComfyUI API")
        comfyui_layout = QVBoxLayout(comfyui_group)

        url_row = QHBoxLayout()
        comfyui_url_input = QLineEdit(getattr(config, 'COMFYUI_API_URL', 'http://127.0.0.1:8188'))
        comfyui_url_input.setPlaceholderText("http://127.0.0.1:8188")
        url_row.addWidget(QLabel("URL:"))
        url_row.addWidget(comfyui_url_input)
        comfyui_layout.addLayout(url_row)

        workflow_row = QHBoxLayout()
        workflow_input = QLineEdit(getattr(config, 'COMFYUI_WORKFLOW_PATH', ''))
        workflow_input.setPlaceholderText("워크플로우 JSON 파일 경로")
        btn_browse = QPushButton("찾아보기")

        # 워크플로우 미리보기 라벨
        wf_preview_label = QLabel("")
        wf_preview_label.setWordWrap(True)
        wf_preview_label.setStyleSheet(
            f"font-size: 11px; padding: 6px; background: {get_color('bg_input')}; "
            f"border: 1px solid {get_color('border')}; border-radius: 4px;"
        )
        wf_preview_label.hide()

        def update_workflow_preview(path: str):
            """워크플로우 파일 분석 후 미리보기 표시"""
            path = path.strip()
            if not path:
                wf_preview_label.hide()
                return
            from backends.comfyui_backend import analyze_workflow
            info = analyze_workflow(path)
            if info.get('error') and not info.get('valid'):
                wf_preview_label.setStyleSheet(
                    f"font-size: 11px; padding: 6px; background: {get_color('bg_input')}; "
                    f"border: 1px solid #f87171; border-radius: 4px; color: #f87171;"
                )
                wf_preview_label.setText(f"❌ {info['error']}")
            else:
                lines = []
                fmt = info.get('format', '?').upper()
                lines.append(f"✅ {fmt} 포맷 | 노드 {info['node_count']}개")
                if info.get('checkpoint'):
                    lines.append(f"📦 체크포인트: {info['checkpoint']}")
                if info.get('ksampler_type'):
                    lines.append(f"🎲 샘플러: {info['ksampler_type']}")
                if info.get('width') and info.get('height'):
                    lines.append(f"📐 해상도: {info['width']}x{info['height']}")
                if info.get('error'):
                    lines.append(f"⚠️ 경고: {info['error']}")
                wf_preview_label.setStyleSheet(
                    f"font-size: 11px; padding: 6px; background: {get_color('bg_input')}; "
                    f"border: 1px solid #4ade80; border-radius: 4px; color: #4ade80;"
                )
                wf_preview_label.setText("\n".join(lines))
            wf_preview_label.show()

        def browse_workflow():
            path, _ = QFileDialog.getOpenFileName(
                dialog, "워크플로우 JSON 선택", "",
                "JSON Files (*.json);;All Files (*)"
            )
            if path:
                workflow_input.setText(path)
                update_workflow_preview(path)

        # 경로 직접 입력 시에도 분석
        workflow_input.editingFinished.connect(
            lambda: update_workflow_preview(workflow_input.text())
        )

        btn_browse.clicked.connect(browse_workflow)
        workflow_row.addWidget(QLabel("워크플로우:"))
        workflow_row.addWidget(workflow_input)
        workflow_row.addWidget(btn_browse)
        comfyui_layout.addLayout(workflow_row)
        comfyui_layout.addWidget(wf_preview_label)

        comfyui_layout.addWidget(
            QLabel("※ ComfyUI에서 'Save (API Format)'으로 저장한 JSON 파일을 사용하세요.")
        )
        main_layout.addWidget(comfyui_group)

        # 초기 워크플로우 미리보기
        if workflow_input.text().strip():
            update_workflow_preview(workflow_input.text())

        # 라디오 버튼에 따라 그룹 활성화
        def on_radio_changed():
            is_comfy = radio_comfyui.isChecked()
            webui_group.setEnabled(not is_comfy)
            comfyui_group.setEnabled(is_comfy)

        radio_webui.toggled.connect(on_radio_changed)
        on_radio_changed()

        # 버튼
        btn_row = QHBoxLayout()

        btn_test = QPushButton("🔍 연결 확인")
        btn_test.setFixedHeight(35)

        def test_connection():
            try:
                if radio_comfyui.isChecked():
                    from backends.comfyui_backend import ComfyUIBackend
                    backend = ComfyUIBackend(comfyui_url_input.text().strip())
                else:
                    from backends.webui_backend import WebUIBackend
                    backend = WebUIBackend(webui_url_input.text().strip())

                if backend.test_connection():
                    QMessageBox.information(dialog, "성공", "연결에 성공했습니다!")
                else:
                    QMessageBox.warning(dialog, "실패", "서버에 연결할 수 없습니다.")
            except Exception as e:
                QMessageBox.critical(dialog, "오류", f"연결 테스트 실패: {e}")

        btn_test.clicked.connect(test_connection)

        btn_apply = QPushButton("✅ 적용")
        btn_apply.setFixedHeight(35)
        btn_apply.setStyleSheet(f"""
            QPushButton {{
                background: {get_color('accent')}; border: none; border-radius: 5px;
                color: white; font-weight: bold; font-size: 13px;
            }}
            QPushButton:hover {{ background: #6975FF; }}
            QPushButton:pressed {{ background: #4752C4; }}
        """)

        def apply_settings():
            if radio_comfyui.isChecked():
                url = comfyui_url_input.text().strip()
                config.COMFYUI_API_URL = url
                config.COMFYUI_WORKFLOW_PATH = workflow_input.text().strip()
                set_backend(BackendType.COMFYUI, url)
            else:
                url = webui_url_input.text().strip()
                set_backend(BackendType.WEBUI, url)

            # 설정 탭 UI 동기화
            if hasattr(self, 'settings_tab'):
                st = self.settings_tab
                if hasattr(st, 'radio_webui'):
                    st.radio_webui.setChecked(not radio_comfyui.isChecked())
                    st.radio_comfyui.setChecked(radio_comfyui.isChecked())
                if hasattr(st, 'api_input'):
                    st.api_input.setText(webui_url_input.text().strip())
                if hasattr(st, 'comfyui_api_input'):
                    st.comfyui_api_input.setText(comfyui_url_input.text().strip())
                if hasattr(st, 'comfyui_workflow_input'):
                    st.comfyui_workflow_input.setText(workflow_input.text().strip())

            dialog.accept()

            # 자동 저장
            if hasattr(self, 'save_settings'):
                self.save_settings()

            self.retry_connection()

        btn_apply.clicked.connect(apply_settings)

        btn_cancel = QPushButton("취소")
        btn_cancel.setFixedHeight(35)
        btn_cancel.clicked.connect(dialog.reject)

        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_cancel)
        main_layout.addLayout(btn_row)

        dialog.exec()

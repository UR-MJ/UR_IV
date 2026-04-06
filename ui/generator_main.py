# ui/generator_main.py
"""
GeneratorMainUI - 메인 윈도우 클래스
"""
from PyQt6.QtWidgets import QMessageBox, QLineEdit, QTextEdit, QApplication, QHBoxLayout, QWidget
from PyQt6.QtCore import QTimer, QEvent

from ui.generator_base import GeneratorBase
from ui.generator_ui_setup import UISetupMixin
from ui.generator_prompts import PromptHandlingMixin
from ui.generator_generation import GenerationMixin
from ui.generator_settings import SettingsMixin
from ui.generator_actions import ActionsMixin
from ui.generator_gallery import GalleryMixin
from ui.generator_webui import WebUIMixin
from ui.generator_search import SearchMixin
from widgets.queue_panel import QueuePanel
from widgets.queue_manager import QueueManager
from widgets.xyz_plot_dialog import XYZPlotDialog
from utils.prompt_cleaner import get_prompt_cleaner
from utils.theme_manager import get_theme_manager, get_color
from utils.tray_manager import TrayManager


class GeneratorMainUI(
    GeneratorBase,
    UISetupMixin,
    PromptHandlingMixin,
    GenerationMixin,
    SettingsMixin,
    ActionsMixin,
    GalleryMixin,
    WebUIMixin,
    SearchMixin
):
    _IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Studio Pro")
        self.setAcceptDrops(True)

        self.prompt_cleaner = get_prompt_cleaner()

        # 백엔드 선택 다이얼로그를 먼저 표시 (UI 생성 전 — 빠른 시작)
        self._startup_backend_check()

        self._setup_ui()
        self.apply_stylesheet()
        self.connect_signals()
        self.load_settings()

        # UI 생성 완료 후 백엔드 연결 결과 적용
        self._apply_backend_startup_result()
        
        # 초기화
        self.is_automating = False
        self.is_programmatic_change = False
        self.current_image_path = None
        self.generation_data = {}
        self.filtered_results = []
        self.random_resolutions = []
        
        # 자동화 상태 플래그
        self.is_automation_running = False
        self.current_repeat_count = 0
        self.max_repeat_count = 0
        
        # 대기열 설정
        self._setup_queue()

        # 시스템 트레이
        self._setup_tray()

        # VRAM 모니터링 타이머
        self._vram_timer = QTimer()
        self._vram_timer.setInterval(30000)  # 30초
        self._vram_timer.timeout.connect(self._update_vram_status)
        self._vram_timer.start()
        QTimer.singleShot(3000, self._update_vram_status)  # 시작 3초 후 첫 조회

        # 실시간 프롬프트 정리 디바운스 타이머
        self._clean_timer = QTimer()
        self._clean_timer.setSingleShot(True)
        self._clean_timer.setInterval(500)
        self._clean_timer.timeout.connect(self._deferred_clean_all)
        self._setup_realtime_cleaning()

        # UI 시작 시 최종 프롬프트 자동 채우기
        QTimer.singleShot(100, self.update_total_prompt_display)
    
    def _setup_realtime_cleaning(self):
        """프롬프트 변경 시 실시간 정리 연결 (디바운스)"""
        def _schedule_clean():
            if not self.is_programmatic_change:
                self._clean_timer.start()

        # QLineEdit
        for w in [self.char_count_input, self.character_input,
                  self.copyright_input, self.artist_input]:
            w.textChanged.connect(_schedule_clean)
        # QTextEdit
        for w in [self.prefix_prompt_text, self.main_prompt_text,
                  self.suffix_prompt_text, self.neg_prompt_text]:
            w.textChanged.connect(_schedule_clean)

    def _deferred_clean_all(self):
        """디바운스된 프롬프트 전체 정리"""
        if self.is_programmatic_change:
            return
        self.is_programmatic_change = True
        try:
            for w in [self.char_count_input, self.character_input,
                      self.copyright_input]:
                orig = w.text()
                if orig.strip():
                    cleaned = self.prompt_cleaner.clean(orig)
                    if orig != cleaned:
                        w.setText(cleaned)
            for w in [self.artist_input, self.prefix_prompt_text,
                      self.main_prompt_text,
                      self.suffix_prompt_text, self.neg_prompt_text]:
                orig = w.toPlainText()
                if orig.strip():
                    cleaned = self.prompt_cleaner.clean(orig)
                    if orig != cleaned:
                        w.setPlainText(cleaned)
        finally:
            self.is_programmatic_change = False

    def _clean_widget_text(self, widget):
        """위젯의 텍스트를 정리하는 헬퍼 메서드"""
        if self.is_programmatic_change:
            return

        if isinstance(widget, QLineEdit):
            original_text = widget.text()
        elif isinstance(widget, QTextEdit):
            original_text = widget.toPlainText()
        else:
            return

        if not original_text.strip():
            return

        cleaned_text = self.prompt_cleaner.clean(original_text)

        self.is_programmatic_change = True
        if original_text != cleaned_text:
            if isinstance(widget, QLineEdit):
                widget.setText(cleaned_text)
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(cleaned_text)
        self.is_programmatic_change = False

    def eventFilter(self, obj, event):
        """QTextEdit의 포커스 잃음 이벤트를 감지하기 위한 이벤트 필터"""
        text_edits_to_clean = [
            self.main_prompt_text,
            self.neg_prompt_text,
            self.s1_widgets['prompt'],
            self.s2_widgets['prompt'],
        ]

        if event.type() == QEvent.Type.FocusOut and obj in text_edits_to_clean:
            self._clean_widget_text(obj)
        
        return super().eventFilter(obj, event)

    def update_cleaner_options(self):
        """settings_tab에서 클리너 옵션을 가져와 업데이트합니다."""
        if hasattr(self, 'settings_tab') and hasattr(self, 'prompt_cleaner'):
            cleaning_options = self.settings_tab.get_cleaning_options()
            self.prompt_cleaner.set_options(**cleaning_options)

    def _setup_queue(self):
        """대기열 설정"""
        self.queue_panel = QueuePanel()
        self.queue_manager = QueueManager(self.queue_panel)

        # 하단 컨테이너에 대기열 + 상태 메시지 배치
        self._bottom_layout.addWidget(self.queue_panel)

        # 상태바 행: 상태 메시지 + VRAM 라벨
        status_row = QWidget()
        status_row.setFixedHeight(24)
        tm = get_theme_manager()
        c = tm.get_colors()
        status_row.setStyleSheet(f"background-color: {c['bg_secondary']}; border-top: 1px solid {c['border']};")
        status_row_layout = QHBoxLayout(status_row)
        status_row_layout.setContentsMargins(0, 0, 0, 0)
        status_row_layout.setSpacing(0)
        status_row_layout.addWidget(self.status_message_label, 1)
        status_row_layout.addWidget(self.vram_label, 0)
        self._bottom_layout.addWidget(status_row)

        # 시그널 연결
        self.queue_panel.btn_add_current.clicked.connect(self._add_current_to_queue)
        self.queue_manager.need_new_prompt.connect(self._on_need_new_prompt)
        self.queue_manager.generation_requested.connect(self._on_generation_requested)
        self.queue_manager.queue_completed.connect(self._on_queue_completed)
    
    # ========== 상태 메시지 ==========

    def show_status(self, message: str, timeout_ms: int = 5000):
        """상태 메시지 표시"""
        self.status_message_label.setText(message)
        if timeout_ms > 0:
            QTimer.singleShot(timeout_ms, lambda: self.status_message_label.clear())

    # ========== 대기열 관련 메서드 ==========

    def _add_current_to_queue(self):
        """현재 설정을 대기열에 추가"""
        payload = self._build_current_payload()
        repeat_count = self.automation_widget.get_settings().get('repeat_per_prompt', 1)
        self.queue_panel.add_items_as_group([payload], repeat_count)
        self.show_status(f"✅ 대기열에 {repeat_count}개 추가됨")
    
    def _on_need_new_prompt(self):
        """새 프롬프트 필요 시 (자동화용)"""
        if not self.is_automation_running:
            return
        
        if not self.filtered_results:
            self.stop_automation()
            QMessageBox.information(self, "완료", "검색 결과가 없어 자동화를 종료합니다.")
            return
        
        # 랜덤 프롬프트 적용 (기존 로직 재사용)
        self.apply_random_prompt()
        
        # payload 생성 후 대기열에 추가
        payload = self._build_current_payload()
        repeat_count = self.automation_widget.get_settings().get('repeat_per_prompt', 1)
        self.queue_manager.add_prompt_group(payload, repeat_count)
    
    def _on_generation_requested(self, item: dict):
        """생성 요청 (대기열에서)"""
        # _xyz_info 보존
        self._pending_xyz_info = item.get('_xyz_info')

        # payload를 UI에 적용
        self._apply_payload_to_ui(item)

        # 생성 시작 (기존 로직 재사용)
        self.start_generation()
    
    def _on_queue_completed(self, total_count: int):
        """대기열 완료"""
        self.is_automation_running = False
        # 창이 비활성이면 트레이 알림 + 소리 + 깜박임
        if not self.isActiveWindow():
            if hasattr(self, '_tray_manager'):
                self._tray_manager.notify("생성 완료", f"총 {total_count}장 생성 완료!")
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.FlashWindow(hwnd, True)
            except Exception:
                pass
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        # 배치 리포트 표시
        from widgets.batch_report_dialog import BatchReportDialog
        report = self.queue_manager.get_batch_report()
        if report.get('total', 0) > 0:
            dlg = BatchReportDialog(report, self)
            dlg.exec()
        else:
            QMessageBox.information(self, "완료", f"총 {total_count}장 생성 완료!")
    
    # ========== 자동화 제어 ==========
    
    def start_automation(self):
        """자동화 시작"""
        if not self.filtered_results:
            QMessageBox.warning(self, "알림", "검색 결과가 없습니다. 먼저 검색을 수행하세요.")
            return
        
        self.is_automation_running = True
        self.show_status("🚀 자동화 시작...")
        
        # 대기열 매니저 시작
        self.queue_manager.start()
    
    def stop_automation(self):
        """자동화 중지"""
        self.is_automation_running = False
        self.queue_manager.stop()
        self.show_status("⏹ 자동화 중지됨")
    
    # ========== Payload 관련 메서드 ==========
    
    def _build_current_payload(self) -> dict:
        """현재 UI 설정으로 payload 생성"""
        payload = {
            'prompt': self.total_prompt_display.toPlainText(),
            'negative_prompt': self.neg_prompt_text.toPlainText(),
            'steps': int(self.steps_input.text()),          # ← 수정!
            'cfg_scale': float(self.cfg_input.text()),      # ← 수정!
            'width': int(self.width_input.text()),          # ← 수정!
            'height': int(self.height_input.text()),        # ← 수정!
            'sampler_name': self.sampler_combo.currentText(),
            'scheduler': self.scheduler_combo.currentText(),
            'seed': int(self.seed_input.text()),            # ← 수정!
            
            # 번들 정보 (대기열 카드 표시용 + 나중에 재적용용)
            'general': self.main_prompt_text.toPlainText(),
            'character': self.character_input.text(),
            'copyright': self.copyright_input.text(),
            'artist': self.artist_input.toPlainText(),
            'person_count': self.char_count_input.text(),
        }
        
        # Hires.fix
        if hasattr(self, 'enable_hires') and self.enable_hires.isChecked():
            payload['enable_hr'] = True
            payload['hr_scale'] = self.hires_scale_input.value()
            payload['hr_upscaler'] = self.hires_upscaler_combo.currentText()
            payload['denoising_strength'] = self.hires_denoise_slider.value()
        
        return payload
    
    def _apply_payload_to_ui(self, payload: dict):
        """payload를 UI에 직접 적용"""
        self.is_programmatic_change = True
        
        try:
            # 1. 기존 값 비우기
            self.char_count_input.clear()
            self.character_input.clear()
            self.copyright_input.clear()
            if not self.btn_lock_artist.isChecked():
                self.artist_input.clear()
            self.main_prompt_text.clear()
            
            # 2. 새 값 설정
            if payload.get('person_count'):
                self.char_count_input.setText(payload['person_count'])
            
            if payload.get('character'):
                self.character_input.setText(payload['character'])
            
            if payload.get('copyright'):
                self.copyright_input.setText(payload['copyright'])
            
            if payload.get('artist') and not self.btn_lock_artist.isChecked():
                self.artist_input.setPlainText(payload['artist'])
            
            if payload.get('general'):
                self.main_prompt_text.setPlainText(payload['general'])
            
            # 3. 설정값 (setText 사용!)
            if 'steps' in payload:
                self.steps_input.setText(str(payload['steps']))
            if 'cfg_scale' in payload:
                self.cfg_input.setText(str(payload['cfg_scale']))
            if 'width' in payload:
                self.width_input.setText(str(payload['width']))
            if 'height' in payload:
                self.height_input.setText(str(payload['height']))
            if 'sampler_name' in payload:
                idx = self.sampler_combo.findText(payload['sampler_name'])
                if idx >= 0:
                    self.sampler_combo.setCurrentIndex(idx)
            if 'scheduler' in payload:
                idx = self.scheduler_combo.findText(payload['scheduler'])
                if idx >= 0:
                    self.scheduler_combo.setCurrentIndex(idx)
            if 'seed' in payload:
                self.seed_input.setText(str(payload['seed']))
            
            # 4. 최종 프롬프트 갱신
            self.update_total_prompt_display()
            
        finally:
            self.is_programmatic_change = False
            
    # ========== XYZ Plot ==========
    
    def _on_xyz_add_to_queue(self, payloads: list):
        """XYZ Plot 결과 대기열에 추가"""
        for payload in payloads:
            self.queue_panel.add_single_item(payload)
        self.show_status(f"✅ XYZ Plot: {len(payloads)}개 대기열에 추가됨")

    def _on_xyz_start_generation(self, payloads: list):
        """XYZ Plot 바로 생성 시작"""
        for payload in payloads:
            self.queue_panel.add_single_item(payload)
        self.show_status(f"XYZ Plot: {len(payloads)}개 생성 시작!")
        self.queue_manager.start()
    
    # ========== Vue 액션 핸들러 ==========

    def _switch_native_tab(self, tab_id: str):
        """PyQt 네이티브 탭 전환"""
        # 에디터 도구 패널 제거
        if self.editor_tools_scroll.parent():
            self.centralWidget().layout().removeWidget(self.editor_tools_scroll)
            self.editor_tools_scroll.setParent(None)

        tab_map = {'vue': 0, 'editor': 1, 'web': 2, 'backend': 3}
        idx = tab_map.get(tab_id, 0)
        self.center_tabs.setCurrentIndex(idx)

        if tab_id == 'editor':
            self.centralWidget().layout().insertWidget(0, self.editor_tools_scroll)
            self.editor_tools_scroll.show()

    def _handle_vue_action(self, action: str, payload: dict):
        """Vue에서 전달된 액션 처리"""
        if action == 'native_tab_switch':
            self._switch_native_tab(payload.get('tab', 'vue'))
        elif action == 'vue_tab_switch':
            self.center_tabs.setCurrentIndex(0)
            self._native_tab_bar.hide()
            self.editor_tools_scroll.hide()
        elif action == 'generate':
            if hasattr(self, 'on_generate_clicked'):
                self.on_generate_clicked()
        elif action == 'toggle_automation':
            checked = payload.get('checked', False)
            self.btn_auto_toggle.setChecked(checked)
        elif action == 'swap_resolution':
            if hasattr(self, '_swap_resolution'):
                self._swap_resolution()
        elif action == 'open_character_preset':
            if hasattr(self, '_open_character_preset'):
                self._open_character_preset()
        elif action == 'display_image':
            path = payload.get('path', '')
            if path:
                # 별도 뷰어 창으로 표시
                from widgets.image_viewer import FullScreenImageViewer
                viewer = FullScreenImageViewer(path, self)
                viewer.show()
        elif action == 'save_settings':
            if hasattr(self, 'save_settings'):
                self.save_settings()
        elif action == 'save_preset':
            if hasattr(self, '_save_prompt_preset'):
                self._save_prompt_preset()
        elif action == 'load_preset':
            if hasattr(self, '_load_prompt_preset'):
                self._load_prompt_preset()
        elif action == 'show_prompt_history':
            if hasattr(self, '_show_prompt_history'):
                self._show_prompt_history()
        elif action == 'show_api_manager':
            if hasattr(self, '_show_api_manager_popup'):
                self._show_api_manager_popup()
        elif action == 'open_lora_manager':
            if hasattr(self, '_open_lora_manager'):
                self._open_lora_manager()
        elif action == 'open_tag_weight_editor':
            if hasattr(self, '_open_tag_weight_editor'):
                self._open_tag_weight_editor()
        elif action == 'apply_search_result':
            # 검색 결과 프롬프트 적용
            if hasattr(self, 'apply_prompt_from_data'):
                self.apply_prompt_from_data(payload)
        elif action == 'open_png_info_file':
            from PyQt6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self, "이미지 선택", "", "Images (*.png *.jpg *.jpeg *.webp)")
            if path:
                import json as _json
                self.vue_bridge.imageGenerated.emit(
                    _json.dumps({'path': path.replace('\\', '/'), 'width': 0, 'height': 0, 'seed': 0})
                )
        elif action == 'generate_i2i':
            # Vue I2I → Python 백엔드로 전달
            self.show_status("I2I 생성 요청 수신")
        elif action == 'generate_inpaint':
            self.show_status("Inpaint 생성 요청 수신")
        elif action == 'search_events':
            self.show_status("이벤트 검색 요청 수신")
        elif action == 'start_xyz_plot':
            self.show_status("XYZ Plot 시작 요청 수신")
        elif action == 'start_batch':
            self.show_status("배치 처리 시작 요청 수신")
        elif action == 'start_upscale':
            self.show_status("업스케일 시작 요청 수신")
        elif action == 'open_batch_files' or action == 'open_upscale_files':
            from PyQt6.QtWidgets import QFileDialog
            paths, _ = QFileDialog.getOpenFileNames(
                self, "이미지 선택", "", "Images (*.png *.jpg *.jpeg *.webp)")
            # TODO: 파일 경로를 Vue로 전달

    # ========== 스타일시트 ==========
    
    def apply_stylesheet(self):
        """전역 스타일시트 적용"""
        tm = get_theme_manager()
        self.setStyleSheet(tm.get_stylesheet())

    def set_theme(self, theme_name: str):
        """테마 전환"""
        tm = get_theme_manager()
        self.setStyleSheet(tm.get_stylesheet(theme_name))
        
        # 탭 이름 업데이트 (이모지 포함 여부 등)
        if hasattr(self, '_update_tab_titles'):
            self._update_tab_titles()
            
        # 상태 메시지 라벨 등 특수 위젯 갱신
        if hasattr(self, 'status_message_label'):
            self.status_message_label.setStyleSheet(f"""
                #statusMessageLabel {{
                    background-color: {get_color('bg_status_bar')};
                    color: {get_color('success')};
                    padding-left: 10px;
                    font-size: 10pt;
                    border-top: 1px solid {get_color('border')};
                }}
            """)
    
    def _setup_tray(self):
        """시스템 트레이 초기화"""
        self._tray_manager = TrayManager(self)
        self._tray_manager.show_window_requested.connect(self._restore_from_tray)
        self._tray_manager.quit_requested.connect(self._quit_app)
        self._tray_manager.show()

    def _update_vram_status(self):
        """VRAM 상태 업데이트"""
        try:
            from backends import get_backend
            backend = get_backend()
            if backend is None:
                return
            stats = backend.get_system_stats()
            if stats and stats.get('vram_total', 0) > 0:
                used_gb = stats['vram_used'] / (1024**3)
                total_gb = stats['vram_total'] / (1024**3)
                pct = (stats['vram_used'] / stats['vram_total']) * 100
                self.vram_label.setText(f"VRAM: {used_gb:.1f}/{total_gb:.1f}GB ({pct:.0f}%)")
                if pct > 90:
                    self.vram_label.setStyleSheet(f"color: {get_color('error')}; font-size: 10px;")
                elif pct > 70:
                    self.vram_label.setStyleSheet(f"color: {get_color('warning')}; font-size: 10px;")
                else:
                    self.vram_label.setStyleSheet(f"color: {get_color('success')}; font-size: 10px;")
            else:
                self.vram_label.setText("")
        except Exception:
            pass

    def _restore_from_tray(self):
        """트레이에서 창 복원"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _cleanup_workers(self):
        """실행 중인 워커 스레드 정리"""
        # 타이머 정지
        if hasattr(self, '_vram_timer'):
            self._vram_timer.stop()
        if hasattr(self, '_clean_timer'):
            self._clean_timer.stop()

        # 자동화 중지
        if hasattr(self, 'queue_manager'):
            try:
                self.queue_manager.stop()
            except Exception:
                pass

        # 워커 스레드 quit 요청 (먼저 전부 보냄)
        workers_to_clean = []
        if hasattr(self, 'gen_worker') and self.gen_worker is not None:
            workers_to_clean.append(self.gen_worker)
        if hasattr(self, 'info_worker') and self.info_worker is not None:
            workers_to_clean.append(self.info_worker)
        if hasattr(self, 'gallery_tab'):
            for attr in ('_scan_worker', '_cache_worker'):
                w = getattr(self.gallery_tab, attr, None)
                if w is not None:
                    workers_to_clean.append(w)

        for w in workers_to_clean:
            try:
                if w.isRunning():
                    w.quit()
            except Exception:
                pass

        # 짧은 대기 (전체 합산 500ms)
        for w in workers_to_clean:
            try:
                if w.isRunning():
                    w.wait(500)
            except Exception:
                pass

    def _quit_app(self):
        """앱 완전 종료"""
        import os
        from utils.app_logger import get_logger
        try:
            self.save_settings()
        except Exception as e:
            get_logger('main').error(f"종료 시 설정 저장 실패: {e}")
        self._cleanup_workers()
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
            except Exception:
                pass
        if hasattr(self, '_tray_manager'):
            self._tray_manager.hide()
        os._exit(0)

    def tray_notify(self, title: str, message: str):
        """트레이 알림 (외부 호출용)"""
        if hasattr(self, '_tray_manager'):
            self._tray_manager.notify(title, message)

    # ========== 드래그 앤 드롭 → img2img ==========

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(self._IMAGE_EXTS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        """외부 이미지 드롭 → img2img 탭으로 전환"""
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(self._IMAGE_EXTS):
                if hasattr(self, 'i2i_tab') and hasattr(self.i2i_tab, '_load_image'):
                    self.i2i_tab._load_image(path)
                    idx = self.center_tabs.indexOf(self.i2i_tab)
                    if idx >= 0:
                        self.center_tabs.setCurrentIndex(idx)
                    self.show_status(f"📂 I2I에 이미지 로드: {path}")
                break

    def closeEvent(self, event):
        """앱 종료 시 트레이 최소화 / 종료 선택"""
        import os
        try:
            from utils.app_logger import get_logger

            msg = QMessageBox(self)
            msg.setWindowTitle("종료")
            msg.setText("AI Studio Pro를 어떻게 처리할까요?")
            btn_tray = msg.addButton("트레이로 최소화", QMessageBox.ButtonRole.AcceptRole)
            btn_quit = msg.addButton("완전 종료", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_cancel)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == btn_tray:
                event.ignore()
                self.hide()
                if hasattr(self, '_tray_manager'):
                    self._tray_manager.notify("AI Studio Pro", "트레이로 최소화되었습니다.")
                return
            elif clicked == btn_quit:
                try:
                    self.save_settings()
                except Exception as e:
                    get_logger('main').error(f"종료 시 설정 저장 실패: {e}")
                self._cleanup_workers()
                if hasattr(self, 'db') and self.db:
                    try:
                        self.db.close()
                    except Exception:
                        pass
                if hasattr(self, '_tray_manager'):
                    self._tray_manager.hide()
                event.accept()
                os._exit(0)
            else:
                event.ignore()
        except Exception:
            event.accept()
            os._exit(0)
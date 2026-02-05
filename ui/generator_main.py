# ui/generator_main.py
"""
GeneratorMainUI - 메인 윈도우 클래스
"""
from PyQt6.QtWidgets import QMessageBox, QLineEdit, QTextEdit
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
from utils.theme_manager import get_theme_manager


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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Studio Pro")
        
        self.prompt_cleaner = get_prompt_cleaner()
        
        self._setup_ui()
        self.apply_stylesheet()
        self.connect_signals()
        self.load_settings()
        self._startup_backend_check()
        
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

        # 메인 레이아웃 하단에 대기열 패널 추가
        self.centralWidget().layout().addWidget(self.queue_panel)

        # 상태 메시지 라벨을 큐 패널 아래에 배치
        self.centralWidget().layout().addWidget(self.status_message_label)

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
            'artist': self.artist_input.text(),
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
                self.artist_input.setText(payload['artist'])
            
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
    
    # ========== 스타일시트 ==========
    
    def apply_stylesheet(self):
        """전역 스타일시트 적용"""
        tm = get_theme_manager()
        self.setStyleSheet(tm.get_stylesheet())

    def set_theme(self, theme_name: str):
        """테마 전환"""
        tm = get_theme_manager()
        self.setStyleSheet(tm.get_stylesheet(theme_name))
    
    def _setup_connections(self):
        """시그널 연결"""
        # 즐겨찾기 버튼
        self.btn_add_favorite.clicked.connect(self.add_to_favorites)
        
        # 갤러리 새로고침
        if hasattr(self, 'btn_refresh_gallery'):
            self.btn_refresh_gallery.clicked.connect(self.refresh_gallery)

    def closeEvent(self, event):
        """앱 종료 시 설정 자동 저장"""
        from utils.app_logger import get_logger
        try:
            self.save_settings()
        except Exception as e:
            get_logger('main').error(f"종료 시 설정 저장 실패: {e}")
        super().closeEvent(event)
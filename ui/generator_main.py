# ui/generator_main.py
"""
GeneratorMainUI - 메인 윈도우 클래스 (데이터 연동 및 안정화 최종판)
"""
import sys
import traceback
import json
import os
import shutil
import subprocess

from PyQt6.QtWidgets import QMessageBox, QLineEdit, QTextEdit, QApplication, QHBoxLayout, QWidget, QFileDialog, QMenu
from PyQt6.QtCore import QTimer, QEvent, Qt, pyqtSlot

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
        try:
            super().__init__()
            print("[System] Initializing AI Studio Pro Engine...")
            self.setWindowTitle("AI Studio Pro")
            self.setAcceptDrops(True)

            # 1. 필수 속성 초기화
            self.s1_widgets = {'prompt': type('P',(),{'installEventFilter':lambda *a:None})()}
            self.s2_widgets = {'prompt': type('P',(),{'installEventFilter':lambda *a:None})()}
            self.is_programmatic_change = False
            self.is_automation_running = False
            self.generation_data = {}
            self.filtered_results = []

            # 2. 아이콘 설정
            from PyQt6.QtGui import QIcon
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icons', 'app_icon.svg')
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))

            self.prompt_cleaner = get_prompt_cleaner()

            # 3. UI 및 프록시 레이어 구축
            self._setup_ui()
            
            # 4. 시그널 및 설정 동기화
            self.connect_signals()
            self.load_settings()

            # 5. 백엔드 브릿지 가동
            self._startup_backend_check()
            self._apply_backend_startup_result()
            
            # 6. 대기열 및 시스템 트레이
            self._setup_queue()
            self._setup_tray()

            # 7. 타이머 가동
            self._vram_timer = QTimer()
            self._vram_timer.setInterval(30000)
            self._vram_timer.timeout.connect(self._update_vram_status)
            self._vram_timer.start()

            self._clean_timer = QTimer()
            self._clean_timer.setSingleShot(True)
            self._clean_timer.setInterval(500)
            self._clean_timer.timeout.connect(self._deferred_clean_all)
            self._setup_realtime_cleaning()

            # 8. 초기값 강제 업데이트
            QTimer.singleShot(500, self.update_total_prompt_display)
            print("[System] Engine Ready.")

        except Exception as e:
            print(f"\n[Fatal] Error during boot: {e}")
            traceback.print_exc()
            QMessageBox.critical(None, "Boot Error", f"Fatal initialization error:\n{e}")
            sys.exit(1)

    # ========== XYZ Plot 핸들러 ==========
    
    def _on_xyz_add_to_queue(self, payloads: list):
        if hasattr(self, 'queue_panel'):
            for p in payloads: self.queue_panel.add_single_item(p)
            self.show_status(f"Added {len(payloads)} XYZ combinations to queue.")

    def _on_xyz_start_generation(self, payloads: list):
        if hasattr(self, 'queue_panel'):
            for p in payloads: self.queue_panel.add_single_item(p)
            self.show_status("Starting XYZ generation.")
            if hasattr(self, 'queue_manager'): self.queue_manager.start()
            
    # ========== Vue Bridge Action Handler (The Core) ==========

    def _handle_vue_action(self, action: str, payload: dict):
        """[중요] Vue에서 날아온 모든 액션을 분석하고 백엔드 로직에 주입"""
        print(f"[Bridge] Action Received: {action} | Payload: {json.dumps(payload)[:100]}...")
        
        try:
            # 1. 워크스페이스 제어
            if action in ('switch_tab', 'native_tab_switch'):
                tab_id = payload.get('tab', 't2i')
                tab_map = {'web': 1, 'backend': 2}
                idx = tab_map.get(tab_id, 0)
                if hasattr(self, '_main_stack'): self._main_stack.setCurrentIndex(idx)
                self.show_status(f"Workspace Switched: {tab_id}")

            # 2. 이미지 생성 엔진
            elif action == 'generate':
                # Vue 데이터가 Store를 통해 Proxy에 이미 동기화되어 있어야 함
                self.on_generate_clicked()

            # 3. 탭 간 데이터 전송 (이미지 & 프롬프트)
            elif action in ('send_to_i2i', 'send_to_inpaint', 'send_to_editor'):
                path = payload.get('path', '')
                if not path: return
                clean_path = os.path.normpath(path.replace('file:///', ''))
                if not os.path.exists(clean_path): return

                if action == 'send_to_i2i':
                    self.vue_bridge.i2iImageLoaded.emit(clean_path.replace('\\', '/'))
                    self.vue_bridge.tabChanged.emit('i2i')
                elif action == 'send_to_inpaint':
                    self.vue_bridge.inpaintImageLoaded.emit(clean_path.replace('\\', '/'))
                    self.vue_bridge.tabChanged.emit('inpaint')
                elif action == 'send_to_editor':
                    self.vue_bridge.editorImageLoaded.emit(clean_path.replace('\\', '/'))
                    self.vue_bridge.tabChanged.emit('editor')
                self.show_status("Asset Transfer Successful.")

            # 4. 에디터 정밀 조작 (먹통 해결)
            elif action == 'editor_open_file':
                # 파일 다이얼로그 호출 (메인 스레드 보장)
                path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.webp)")
                if path: self.vue_bridge.editorImageLoaded.emit(path.replace('\\', '/'))
            
            elif action == 'editor_save':
                path = payload.get('path', '')
                if path:
                    src = os.path.normpath(path.replace('file:///', ''))
                    dst, _ = QFileDialog.getSaveFileName(self, "Export Edited Image", "", "PNG (*.png);;JPEG (*.jpg)")
                    if dst:
                        shutil.copy2(src, dst)
                        self.show_status(f"Exported to: {os.path.basename(dst)}")

            elif action == 'editor_change_tool':
                tool = payload.get('tool', 'box')
                if hasattr(self, 'mosaic_editor') and self.mosaic_editor.mosaic_panel:
                    panel = self.mosaic_editor.mosaic_panel
                    tool_map = {'box': 0, 'lasso': 1, 'brush': 2, 'eraser': 3}
                    btn_id = tool_map.get(tool, 0)
                    btn = panel.tool_group.button(btn_id)
                    if btn: btn.setChecked(True); panel.on_tool_group_clicked(btn)

            elif action == 'editor_apply_effect':
                if hasattr(self, 'mosaic_editor'): self.mosaic_editor._on_apply_effect()
            elif action == 'editor_apply_auto_censor':
                if hasattr(self, 'mosaic_editor'): self.mosaic_editor._on_auto_censor()
            elif action == 'editor_add_yolo_model':
                # QFileDialog를 메인 윈도우(self) 기준으로 열어야 QWebEngineView 앞에 표시됨
                from PyQt6.QtWidgets import QFileDialog as _QFD
                paths, _ = _QFD.getOpenFileNames(
                    self, "YOLO 모델 선택", "",
                    "YOLO Model (*.pt *.onnx);;All Files (*)"
                )
                if paths and hasattr(self, 'mosaic_editor') and self.mosaic_editor.mosaic_panel:
                    panel = self.mosaic_editor.mosaic_panel
                    for p in paths:
                        if p not in panel._yolo_model_paths:
                            panel._yolo_model_paths.append(p)
                    from tabs.editor.mosaic_panel import _save_yolo_model_paths
                    _save_yolo_model_paths(panel._yolo_model_paths)
                    panel._update_model_label()
                    # Vue에 모델 라벨 업데이트 전달
                    import os as _os2
                    names = [_os2.path.basename(p) for p in panel._yolo_model_paths]
                    label = ", ".join(names) if names else "No Model"
                    self.vue_bridge.yoloModelUpdated.emit(label)
                    self.show_status(f"YOLO Model loaded: {label}")

            # 5. 하이엔드 우클릭 메뉴
            elif action == 'context_menu':
                path = payload.get('path', '')
                if not path: return
                clean_path = os.path.normpath(path.replace('file:///', ''))
                if not os.path.exists(clean_path): return
                
                menu = QMenu(self)
                menu.setStyleSheet(f"QMenu {{ background: #121212; color: white; border: 1px solid #333; padding: 4px; }} QMenu::item:selected {{ background: {get_color('accent')}; color: black; }}")
                
                act_i2i = menu.addAction("🖼️ SEND TO I2I")
                act_inpaint = menu.addAction("🎨 SEND TO INPAINT")
                act_editor = menu.addAction("🎨 SEND TO EDITOR")
                menu.addSeparator()
                act_folder = menu.addAction("📁 SHOW IN EXPLORER")
                act_copy = menu.addAction("📋 COPY TO CLIPBOARD")
                act_del = menu.addAction("🗑️ DELETE TO TRASH")
                
                chosen = menu.exec(QApplication.desktop().cursor().pos())
                if chosen == act_i2i: self._handle_vue_action('send_to_i2i', {'path': clean_path})
                elif chosen == act_inpaint: self._handle_vue_action('send_to_inpaint', {'path': clean_path})
                elif chosen == act_editor: self._handle_vue_action('send_to_editor', {'path': clean_path})
                elif chosen == act_folder:
                    subprocess.run(['explorer', '/select,', clean_path])
                elif chosen == act_copy:
                    from PyQt6.QtGui import QPixmap
                    pix = QPixmap(clean_path)
                    if not pix.isNull(): QApplication.clipboard().setPixmap(pix); self.show_status("Copied.")
                elif chosen == act_del:
                    from core.image_utils import move_to_trash
                    move_to_trash(clean_path); self.show_status("Moved to Trash.")

            # 6. 기타 스튜디오 도구
            elif action == 'show_prompt_history': self._show_prompt_history()
            elif action == 'open_lora_manager': self._open_lora_manager()
            elif action == 'save_settings': self.save_settings()
            elif action == 'swap_resolution': self._swap_resolution()
            elif action == 'shuffle': self._shuffle_main_prompt()
            elif action == 'ab_test': self._open_ab_test()
            elif action == 'random_prompt': self.apply_random_prompt()

            # 7. 검색 결과 → 프롬프트 적용
            elif action == 'apply_search_result':
                self.apply_prompt_from_data(payload)
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.tabChanged.emit('t2i')
                self.show_status("Prompt applied from search result.")

            elif action == 'add_search_to_queue':
                # 검색 결과를 대기열에 추가
                classified = self.tag_classifier.classify_tags_for_event(
                    [t.strip() for t in payload.get('general', '').split(',') if t.strip()]
                )
                queue_payload = {
                    'prompt': payload.get('general', ''),
                    'negative_prompt': self.neg_prompt_text.toPlainText(),
                    'character': payload.get('character', ''),
                    'copyright': payload.get('copyright', ''),
                    'artist': payload.get('artist', ''),
                }
                if hasattr(self, 'queue_panel'):
                    self.queue_panel.add_single_item(queue_payload)
                    self.show_status("Added to queue.")

            # 8. 즐겨찾기
            elif action == 'add_favorite':
                path = payload.get('path', '')
                if path:
                    clean = os.path.normpath(path.replace('file:///', ''))
                    self._load_favorites_from_file()
                    if clean not in self.favorites_list:
                        self.favorites_list.append(clean)
                        self._save_favorites_to_file()
                    self.show_status("Added to favorites.")

            # artist lock
            elif action == 'set_artist_locked':
                locked = payload.get('locked', False)
                if hasattr(self, 'btn_lock_artist'):
                    self.btn_lock_artist.setChecked(locked)

            # 9. 이미지 삭제
            elif action == 'delete_image':
                path = payload.get('path', '')
                if path:
                    clean_path = os.path.normpath(path.replace('file:///', ''))
                    from core.image_utils import move_to_trash
                    move_to_trash(clean_path)
                    self.show_status("Moved to trash.")

            # 10. 프리셋
            elif action == 'save_preset': self._save_preset()
            elif action == 'load_preset': self._load_preset()

            # 11. I2I/Inpaint 생성
            elif action == 'generate_i2i':
                if hasattr(self, 'i2i_tab'):
                    self.i2i_tab.start_generation()
            elif action == 'generate_inpaint':
                if hasattr(self, 'inpaint_tab'):
                    self.inpaint_tab.start_generation()

            # 12. 배치/업스케일
            elif action == 'start_batch':
                if hasattr(self, 'batch_tab'):
                    self.batch_tab.start_batch()
            elif action == 'start_upscale':
                if hasattr(self, 'upscale_tab'):
                    self.upscale_tab.start_upscale()

            # PNG Info 파일 열기
            elif action == 'open_png_info_file':
                path, _ = QFileDialog.getOpenFileName(self, "PNG Info 이미지 선택", "", "Images (*.png *.jpg *.jpeg *.webp)")
                if path and hasattr(self, 'vue_bridge'):
                    self.vue_bridge.inpaintImageLoaded.emit(path.replace('\\', '/'))

            # 13. 에디터 워터마크 이미지 로드
            elif action == 'editor_load_watermark_image':
                path, _ = QFileDialog.getOpenFileName(self, "워터마크 이미지 선택", "", "Images (*.png *.jpg *.jpeg *.webp)")
                if path:
                    self.show_status(f"Watermark image: {os.path.basename(path)}")

            # 14. 갤러리 폴더 변경
            elif action == 'gallery_change_folder':
                folder = payload.get('folder', '')
                if folder and hasattr(self, 'gallery_tab'):
                    self.gallery_tab.load_folder(folder)

            # 15. Search parquet 저장/불러오기
            elif action == 'export_search_results':
                if hasattr(self, 'search_tab') and hasattr(self.search_tab, 'export_results'):
                    self.search_tab.export_results()
                else:
                    self.show_status("Export: search_tab not available")
            elif action == 'import_search_results':
                if hasattr(self, 'search_tab') and hasattr(self.search_tab, 'import_results'):
                    self.search_tab.import_results()

            # 16. 자동화 토글
            elif action == 'toggle_automation':
                checked = payload.get('checked', False)
                self.toggle_automation_ui(checked)

        except Exception as e:
            print(f"[Error] Action '{action}' failed: {e}")
            traceback.print_exc()

    # ========== 유틸리티 메서드 ==========

    def show_status(self, message: str, timeout_ms: int = 5000):
        if hasattr(self, 'status_message_label') and self.status_message_label:
            self.status_message_label.setText(message.upper())
            if timeout_ms > 0: QTimer.singleShot(timeout_ms, lambda: self.status_message_label.clear())

    def _setup_realtime_cleaning(self):
        def _schedule():
            if not self.is_programmatic_change: self._clean_timer.start()
        for w in [self.char_count_input, self.character_input, self.copyright_input, self.artist_input, self.prefix_prompt_text, self.main_prompt_text, self.suffix_prompt_text, self.neg_prompt_text]:
            if hasattr(w, 'textChanged'): w.textChanged.connect(_schedule)

    def _deferred_clean_all(self):
        if self.is_programmatic_change: return
        self.is_programmatic_change = True
        try:
            for w in [self.char_count_input, self.character_input, self.copyright_input]:
                cleaned = self.prompt_cleaner.clean(w.text())
                if w.text() != cleaned: w.setText(cleaned)
            for w in [self.artist_input, self.prefix_prompt_text, self.main_prompt_text, self.suffix_prompt_text, self.neg_prompt_text]:
                cleaned = self.prompt_cleaner.clean(w.toPlainText())
                if w.toPlainText() != cleaned: w.setPlainText(cleaned)
        finally: self.is_programmatic_change = False

    def _setup_queue(self):
        self.queue_panel = QueuePanel()
        self.queue_panel.setParent(None)
        self.queue_manager = QueueManager(self.queue_panel)
        self.queue_manager.generation_requested.connect(self._on_generation_requested)
        self.queue_manager.queue_completed.connect(self._on_queue_completed)

    def _on_generation_requested(self, item: dict):
        self._apply_payload_to_ui(item)
        self.start_generation()

    def _on_queue_completed(self, total_count: int):
        self.is_automation_running = False
        QMessageBox.information(self, "Task Complete", f"Successfully generated {total_count} images.")

    def _setup_tray(self):
        self._tray_manager = TrayManager(self)
        self._tray_manager.show_window_requested.connect(self.showNormal)
        self._tray_manager.quit_requested.connect(QApplication.quit)
        self._tray_manager.show()

    def _update_vram_status(self):
        try:
            from backends import get_backend
            backend = get_backend()
            if backend:
                stats = backend.get_system_stats()
                if stats and stats.get('vram_total', 0) > 0:
                    used = stats['vram_used'] / (1024**3)
                    total = stats['vram_total'] / (1024**3)
                    if hasattr(self, 'vram_label') and self.vram_label:
                        self.vram_label.setText(f"VRAM: {used:.1f}/{total:.1f}GB")
        except: pass

    def closeEvent(self, event): self._quit_app()

    def _quit_app(self):
        try: self.save_settings()
        except: pass
        os._exit(0)

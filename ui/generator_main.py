# ui/generator_main.py
"""
GeneratorMainUI - 메인 윈도우 클래스 (데이터 연동 및 안정화 최종판)
"""
import sys
import traceback
import json
import os
import random
import shutil
import subprocess
from urllib.parse import unquote

from PyQt6.QtWidgets import QMessageBox, QLineEdit, QTextEdit, QApplication, QHBoxLayout, QWidget, QFileDialog, QMenu
from PyQt6.QtCore import QTimer, QEvent, Qt, pyqtSlot


def _clean_path(path: str) -> str:
    """file:/// 프리픽스 제거 + OS 경로 정규화"""
    if not path:
        return ''
    clean_path = unquote(str(path)).replace('file:///', '').replace('file://', '')
    clean_path = clean_path.replace('/', os.sep)
    return clean_path

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
            self.generation_data = {}
            self.filtered_results = []

            # 1-A. UI 상태 영속화 매니저 — 창 크기/위치 자동 저장/복원
            from pathlib import Path
            from core.ui_state_manager import UIStateManager
            _save_dir = Path(__file__).resolve().parent.parent / "save"
            _save_dir.mkdir(exist_ok=True)
            self.ui_state = UIStateManager(_save_dir / "ui_state.json")
            self._register_ui_state_handlers()

            # 2. 아이콘 설정
            from PyQt6.QtGui import QIcon
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icons', 'app_icon.svg')
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))

            self.prompt_cleaner = get_prompt_cleaner()

            # 3. UI 및 프록시 레이어 구축
            self._setup_ui()

            # 에러 핸들러에 bridge 등록
            from core.error_handler import set_bridge
            set_bridge(self.vue_bridge)
            
            # 4. 시그널 및 설정 동기화
            self.connect_signals()
            self.load_settings()

            # 4-A. 검색 결과 덱 디스크 복원 — 자동화가 Search 탭 방문 없이도 즉시 사용 가능.
            #   기존엔 Vue SearchView onMounted에서만 loadLastSearchResults가 호출돼,
            #   앱이 다른 탭(T2I 등)에서 시작하면 shuffled_prompt_deck이 빈 채로 남아
            #   '자동화 종료 후 재시작 시 검색 import 안 됨 → 자동화 불가' 발생.
            #   여기서 동기 복원하면 어느 탭에서 시작하든 덱이 준비됨.
            try:
                if hasattr(self, 'vue_bridge') and hasattr(self.vue_bridge, 'loadLastSearchResults'):
                    self.vue_bridge.loadLastSearchResults()
            except Exception as e:
                print(f"[Search] 시작 시 덱 복원 실패: {e}")

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

            # 9. 조건식 + 기본값 로드
            QTimer.singleShot(1000, self._load_saved_configs)

            # 10. UI 상태 복원 (150ms 지연 — 위젯 레이아웃 자리 잡은 후)
            #     showMaximized() 등 다른 main의 호출과 충돌 회피 위해 약간 더 늦춤
            QTimer.singleShot(200, lambda: self.ui_state.restore_all_delayed(150))

            # 11. PR 9 — 모드별 자동화 설정 영속 (webui/comfyui 분리)
            #     백엔드 전환 시 자동 저장/복원, Vue로 자동 전파
            from core.mode_aware_automation import ModeAwareAutomationSettings
            self.automation_persistence = ModeAwareAutomationSettings(self)
            # vue_bridge가 준비되고 Vue가 시그널 받을 준비 끝난 후 (1.5초 후) 적용
            QTimer.singleShot(1500, self.automation_persistence.initialize)

            # 12. PR 2 — GenerationQueueV2 이벤트 브리지
            #     기존 queue_panel은 그대로, V2는 AppContext 서비스로 노출
            #     queue_panel.queue_changed → V2.publish → 다른 모듈 구독 가능
            self._setup_queue_v2_bridge()

            # 13. PR 1 — PromptPipeline 표준 훅 등록
            #     기존 처리 뒤에 호출되어 비파괴적 — 회귀 위험 없음
            try:
                from core.standard_hooks import register_standard_hooks
                register_standard_hooks()
            except Exception as e:
                print(f"[Warning] 표준 훅 등록 실패: {e}")

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
            if action == 'native_tab_switch':
                tab_id = payload.get('tab', 't2i')
                tab_map = {'web': 1, 'backend': 2}
                idx = tab_map.get(tab_id, 0)
                if hasattr(self, '_main_stack'): self._main_stack.setCurrentIndex(idx)
                self.show_status(f"Workspace Switched: {tab_id}")

            elif action == 'vue_tab_switch':
                # Vue SPA 내부 탭(T2I/I2I/Inpaint/Search 등) 전환 알림.
                # 라우팅 자체는 Vue Router가 처리하므로 Python은 스택을 SPA(0)로
                # 맞추고 tabChanged 시그널만 전달한다.
                tab_id = payload.get('tab', 't2i')
                if hasattr(self, '_main_stack'):
                    self._main_stack.setCurrentIndex(0)
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.tabChanged.emit(tab_id)
                self.show_status(f"Tab: {tab_id}")

            # 2. 이미지 생성 엔진
            elif action == 'generate':
                # Vue 데이터가 Store를 통해 Proxy에 이미 동기화되어 있어야 함
                self.on_generate_clicked()

            elif action == 'set_high_res_factor':
                # Vue 고해상도 토글 → 생성 시점에 width/height × factor 적용
                # generator_generation.py가 self._high_res_factor 읽음
                try:
                    enabled = bool(payload.get('enabled', False))
                    factor = float(payload.get('factor', 1.5))
                    if not enabled:
                        factor = 1.0
                    self._high_res_factor = max(1.0, min(4.0, factor))
                    self.show_status(f"고해상도: {'ON ' + str(round(self._high_res_factor, 2)) + 'x' if enabled else 'OFF'}")
                except Exception as e:
                    self.show_status(f"고해상도 설정 실패: {e}")

            elif action == 'cancel_generation':
                worker = getattr(self, 'gen_worker', None)
                if worker is not None and hasattr(worker, 'cancel') and worker.isRunning():
                    worker.cancel()
                    self.show_status("생성 취소됨")
                    # worker가 finished를 안 쏠 수 있으므로 버튼/타이틀 즉시 복구
                    if hasattr(self, '_restore_generate_button'):
                        self._restore_generate_button()
                else:
                    self.show_status("취소할 생성이 없습니다")
                    if hasattr(self, '_restore_generate_button'):
                        self._restore_generate_button()

            # 3. 탭 간 데이터 전송 (이미지 & 프롬프트)
            elif action in ('send_to_i2i', 'send_to_inpaint', 'send_to_editor'):
                path = payload.get('path', '')
                if not path: return
                # file:/// 제거 + 경로 정규화
                clean_path = _clean_path(path)
                if clean_path.startswith('/') and ':' in clean_path[1:3]:
                    clean_path = clean_path[1:]  # /C:/... → C:/...
                clean_path = os.path.normpath(clean_path)
                if not os.path.exists(clean_path):
                    print(f"[Send] File not found: {clean_path} (original: {path})")
                    return

                fwd_path = clean_path.replace('\\', '/')
                print(f"[Send] {action}: {fwd_path}")
                if action == 'send_to_i2i':
                    self.vue_bridge.tabChanged.emit('i2i')
                    QTimer.singleShot(100, lambda p=fwd_path: self.vue_bridge.i2iImageLoaded.emit(p))
                elif action == 'send_to_inpaint':
                    self.vue_bridge.tabChanged.emit('inpaint')
                    QTimer.singleShot(100, lambda p=fwd_path: self.vue_bridge.inpaintImageLoaded.emit(p))
                elif action == 'send_to_editor':
                    # 탭 전환 먼저 → 100ms 후 이미지 로드 (keep-alive 렌더링 대기)
                    self.vue_bridge.tabChanged.emit('editor')
                    QTimer.singleShot(100, lambda p=fwd_path: self.vue_bridge.editorImageLoaded.emit(p))
                self.show_status("Asset Transfer Successful.")
                tab_names = {'send_to_i2i': 'I2I', 'send_to_inpaint': 'Inpaint', 'send_to_editor': 'Editor'}
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.showNotification.emit('success', f'{tab_names.get(action, "")}로 전송됨')

            # 4. 에디터 정밀 조작 (먹통 해결)
            elif action == 'editor_open_file':
                # 파일 다이얼로그 호출 (메인 스레드 보장)
                path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.webp)")
                if path: self.vue_bridge.editorImageLoaded.emit(path.replace('\\', '/'))
            
            elif action == 'editor_save':
                # FIX: 원래는 다이얼로그 띄웠음. 이제는 원본 경로에 덮어쓰기.
                # 다른 이름으로 저장은 editor_save_as 따로 있음.
                path = payload.get('path', '')
                if path:
                    src = _clean_path(path)
                    # src가 임시 작업 파일이면 그 자리에 두고, 사용자에게는 알림만
                    # (실제로는 editor 작업 결과가 그 path에 이미 저장돼있음)
                    if os.path.exists(src):
                        self.vue_bridge.showNotification.emit('success', f'저장됨: {os.path.basename(src)}')
                    else:
                        self.vue_bridge.showNotification.emit('error', f'파일 없음: {src}')

            elif action == 'editor_save_as':
                path = payload.get('path', '')
                if path:
                    src = _clean_path(path)
                    # 기본 파일명 추천
                    base = os.path.splitext(os.path.basename(src))[0]
                    ext = os.path.splitext(src)[1].lstrip('.').lower() or 'png'
                    suggest = f"{base}_edited.{ext}"
                    dst, _ = QFileDialog.getSaveFileName(
                        self, "다른 이름으로 저장",
                        suggest,
                        "PNG (*.png);;JPEG (*.jpg);;WebP (*.webp);;All Files (*)"
                    )
                    if dst:
                        shutil.copy2(src, dst)
                        self.vue_bridge.showNotification.emit('success', f'저장됨: {os.path.basename(dst)}')
                        self.show_status(f"Exported to: {os.path.basename(dst)}")

            elif action == 'editor_add_yolo_model':
                from PyQt6.QtWidgets import QFileDialog as _QFD
                from tabs.editor.mosaic_panel import get_editor_models_dir
                models_dir = get_editor_models_dir()
                paths, _ = _QFD.getOpenFileNames(
                    self, "YOLO 모델 선택", models_dir,
                    "YOLO Model (*.pt *.onnx *.safetensors);;All Files (*)"
                )
                if paths and hasattr(self, 'mosaic_editor') and self.mosaic_editor.mosaic_panel:
                    panel = self.mosaic_editor.mosaic_panel
                    from tabs.editor.mosaic_panel import _save_yolo_model_paths, get_editor_models_dir
                    models_dir = get_editor_models_dir()
                    for p in paths:
                        # editor_models/ 외부 파일이면 복사
                        if not p.startswith(models_dir.replace('\\', '/')) and not p.startswith(models_dir):
                            dst = os.path.join(models_dir, os.path.basename(p))
                            if not os.path.exists(dst):
                                shutil.copy2(p, dst)
                                p = dst
                        if p not in panel._yolo_model_paths:
                            panel._yolo_model_paths.append(p)
                    _save_yolo_model_paths(panel._yolo_model_paths)
                    panel._update_model_label()
                    # Vue에 모델 라벨 업데이트 전달
                    import os as _os2
                    names = [_os2.path.basename(p) for p in panel._yolo_model_paths]
                    label = ", ".join(names) if names else "No Model"
                    self.vue_bridge.yoloModelUpdated.emit(label)
                    self.show_status(f"YOLO Model loaded: {label}")

            # 6. 기타 스튜디오 도구
            elif action == 'show_prompt_history': self._show_prompt_history()
            elif action == 'open_lora_manager': self._open_lora_manager()
            elif action == 'save_settings':
                self.save_settings()
                # 저장 후 즉시 재로드 (Vue에 반영)
                QTimer.singleShot(200, self.load_settings)
                # defaults도 동시 업데이트
                try:
                    defaults_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'tab_defaults.json')
                    if os.path.exists(defaults_path):
                        with open(defaults_path, 'r', encoding='utf-8') as f:
                            cur = json.load(f)
                        cur['steps'] = int(self.steps_input.text() or 20)
                        cur['cfg'] = float(self.cfg_input.text() or 7)
                        cur['width'] = int(self.width_input.text() or 1024)
                        cur['height'] = int(self.height_input.text() or 1024)
                        cur['seed'] = self.seed_input.text() or '-1'
                        with open(defaults_path, 'w', encoding='utf-8') as f:
                            json.dump(cur, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.showNotification.emit('success', '설정이 저장되었습니다')
            elif action == 'swap_resolution': self._swap_resolution()
            elif action == 'set_random_resolutions':
                lst = payload.get('list', [])
                self.random_resolutions = [(int(r[0]), int(r[1]), str(r[2])) for r in lst if len(r) >= 3]
            elif action == 'set_rating_filter':
                self._rating_filter = set(payload.get('ratings', ['g', 's', 'q', 'e']))
                # 현재 deck을 rating 필터로 재필터링
                if hasattr(self, 'filtered_results') and self.filtered_results:
                    self.shuffled_prompt_deck = [
                        r for r in self.filtered_results
                        if r.get('rating', 'g') in self._rating_filter
                    ]
                    import random as _rnd
                    _rnd.shuffle(self.shuffled_prompt_deck)
            elif action == 'update_prompt_deck':
                # Vue에서 필터링된 결과로 덱 업데이트
                deck = payload.get('results', [])
                if deck:
                    import random as _rnd
                    rating_filter = getattr(self, '_rating_filter', {'g', 's', 'q', 'e'})
                    self.filtered_results = deck
                    self.shuffled_prompt_deck = [
                        r for r in deck if r.get('rating', 'g') in rating_filter
                    ]
                    _rnd.shuffle(self.shuffled_prompt_deck)
                    # 필터 적용 결과를 디스크에 저장(단일 쓰기 경로) → 재시작 시 '필터링된' 덱 복원.
                    #   full은 갱신 안 함(새 검색 때만) → '필터 해제' 베이스(last_full)는 유지.
                    self._persist_search_results(deck)
                    if hasattr(self, '_save_deck_state'):
                        self._save_deck_state()
            elif action == 'run_adetailer_single':
                self._run_adetailer_single(payload)
            elif action == 'run_adetailer_batch':
                self._run_adetailer_batch(payload)
            elif action == 'stop_adetailer_batch':
                # BatchView '중지' 버튼 — 워커는 stop()/_stop_event 지원하나
                # 액션 핸들러가 없어 무동작이었음. 연결.
                _w = getattr(self, '_ad_batch_worker', None)
                if _w is not None and _w.isRunning():
                    _w.stop()
                    self.vue_bridge.showNotification.emit('info', 'ADetailer 배치 중지 요청됨')
            elif action == 'run_sam3_single':
                self._run_sam3_single(payload)
            elif action == 'run_sam3_batch':
                self._run_sam3_batch(payload)
            elif action == 'open_ad_files':
                paths, _ = QFileDialog.getOpenFileNames(self, "ADetailer 이미지 선택", "",
                    "Images (*.png *.jpg *.jpeg *.webp);;All Files (*)")
                if paths:
                    self.vue_bridge.batchFilesSelected.emit(
                        json.dumps([p.replace('\\', '/') for p in paths]))
            elif action == 'open_ad_folder':
                folder = QFileDialog.getExistingDirectory(self, "ADetailer 폴더 선택")
                if folder:
                    import glob
                    imgs = []
                    for ext in ('*.png', '*.jpg', '*.jpeg', '*.webp'):
                        imgs.extend(glob.glob(os.path.join(folder, ext)))
                    if imgs:
                        self.vue_bridge.batchFilesSelected.emit(
                            json.dumps([p.replace('\\', '/') for p in sorted(imgs)]))
                        self.vue_bridge.showNotification.emit('info', f'{len(imgs)}개 이미지 발견')
            elif action == 'random_prompt': self.apply_random_prompt()

            # 7. 검색 결과 → 프롬프트 적용
            elif action == 'apply_search_result':
                # Vue 검색 결과 필드명 → Python bundle 필드명 통일
                bundle = {
                    'character': payload.get('character', ''),
                    'copyright': payload.get('copyright', ''),
                    'artist': payload.get('artist', ''),
                    'general': payload.get('general', ''),
                }
                # nan 문자열 처리
                for k in bundle:
                    if str(bundle[k]).lower() == 'nan':
                        bundle[k] = ''

                self.is_programmatic_change = True
                try:
                    self.apply_prompt_from_data(bundle)
                finally:
                    self.is_programmatic_change = False

                # 조건부 프롬프트 적용
                cond_pos = payload.get('cond_positive', [])
                cond_neg = payload.get('cond_negative', [])
                if cond_pos or cond_neg:
                    self._apply_vue_conditional_rules(cond_pos, cond_neg)

                self.update_total_prompt_display()

                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.tabChanged.emit('t2i')
                    self.vue_bridge.showNotification.emit('success', '프롬프트가 적용되었습니다')

            elif action == 'add_search_to_queue':
                # 먼저 프롬프트 적용하여 UI 채우기
                bundle = {
                    'character': payload.get('character', ''),
                    'copyright': payload.get('copyright', ''),
                    'artist': payload.get('artist', ''),
                    'general': payload.get('general', ''),
                }
                for k in bundle:
                    if str(bundle[k]).lower() == 'nan': bundle[k] = ''
                self.is_programmatic_change = True
                try:
                    self.apply_prompt_from_data(bundle)
                finally:
                    self.is_programmatic_change = False
                self.update_total_prompt_display()

                # 현재 UI 상태에서 payload 구성
                queue_payload = {
                    'prompt': self.total_prompt_display.toPlainText(),
                    'negative_prompt': self.neg_prompt_text.toPlainText(),
                    'sampler_name': self.sampler_combo.currentText(),
                    'steps': int(self.steps_input.text() or 20),
                    'cfg_scale': float(self.cfg_input.text() or 7),
                    'seed': int(self.seed_input.text() or -1),
                    'width': int(self.width_input.text() or 1024),
                    'height': int(self.height_input.text() or 1024),
                }
                if hasattr(self, 'queue_panel'):
                    self.queue_panel.add_single_item(queue_payload)
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.showNotification.emit('success', '대기열에 추가되었습니다')

            # 8. 즐겨찾기
            elif action == 'add_favorite':
                path = payload.get('path', '')
                if path:
                    clean = _clean_path(path)
                    self._load_favorites_from_file()
                    if clean not in self.favorites_list:
                        self.favorites_list.append(clean)
                        self._save_favorites_to_file()
                    self.show_status("Added to favorites.")
                    if hasattr(self, 'vue_bridge'):
                        self.vue_bridge.showNotification.emit('success', '즐겨찾기에 추가됨')

            # artist lock
            elif action == 'set_artist_locked':
                locked = payload.get('locked', False)
                if hasattr(self, 'btn_lock_artist'):
                    self.btn_lock_artist.setChecked(locked)

            # 9. 이미지 삭제
            elif action == 'delete_image':
                path = payload.get('path', '')
                if path:
                    clean_path = _clean_path(path)
                    from core.image_utils import move_to_trash
                    move_to_trash(clean_path)
                    self.show_status("Moved to trash.")
                    if hasattr(self, 'vue_bridge'):
                        self.vue_bridge.showNotification.emit('info', '휴지통으로 이동됨')

            # 10. 프리셋
            elif action == 'save_preset_by_name':
                try:
                    name = payload.get('name', '')
                    if name:
                        preset = self._build_settings_dict()
                        preset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'presets')
                        os.makedirs(preset_dir, exist_ok=True)
                        with open(os.path.join(preset_dir, f"{name}.json"), 'w', encoding='utf-8') as f:
                            json.dump(preset, f, ensure_ascii=False, indent=2)
                        self.vue_bridge.showNotification.emit('success', f'프리셋 "{name}" 저장됨')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'저장 실패: {e}')

            elif action == 'load_preset_by_name':
                try:
                    name = payload.get('name', '')
                    if name:
                        fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'presets', f"{name}.json")
                        with open(fp, 'r', encoding='utf-8') as f:
                            preset = json.load(f)
                        self._apply_settings_dict(preset)
                        self.update_total_prompt_display()
                        self.vue_bridge.showNotification.emit('success', f'프리셋 "{name}" 로드됨')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'로드 실패: {e}')

            elif action == 'delete_preset':
                try:
                    name = payload.get('name', '')
                    fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'presets', f"{name}.json")
                    if os.path.exists(fp): os.remove(fp)
                    self.vue_bridge.showNotification.emit('success', f'프리셋 "{name}" 삭제됨')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'삭제 실패: {e}')

            elif action == 'save_preset':
                try:
                    name, ok = QMessageBox.question(self, "프리셋", ""), None
                    from PyQt6.QtWidgets import QInputDialog
                    name, ok = QInputDialog.getText(self, "프리셋 저장", "프리셋 이름:")
                    if ok and name:
                        preset = self._build_settings_dict()
                        preset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'presets')
                        os.makedirs(preset_dir, exist_ok=True)
                        path = os.path.join(preset_dir, f"{name}.json")
                        with open(path, 'w', encoding='utf-8') as f:
                            json.dump(preset, f, ensure_ascii=False, indent=2)
                        self.vue_bridge.showNotification.emit('success', f'프리셋 "{name}" 저장됨')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'프리셋 저장 실패: {e}')

            elif action == 'load_preset':
                try:
                    from PyQt6.QtWidgets import QInputDialog
                    preset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'presets')
                    os.makedirs(preset_dir, exist_ok=True)
                    files = [f.replace('.json', '') for f in os.listdir(preset_dir) if f.endswith('.json')]
                    if not files:
                        self.vue_bridge.showNotification.emit('info', '저장된 프리셋이 없습니다')
                        return
                    name, ok = QInputDialog.getItem(self, "프리셋 불러오기", "선택:", files, 0, False)
                    if ok and name:
                        path = os.path.join(preset_dir, f"{name}.json")
                        with open(path, 'r', encoding='utf-8') as f:
                            preset = json.load(f)
                        self.load_settings_from_dict(preset) if hasattr(self, 'load_settings_from_dict') else self._apply_settings_dict(preset)
                        self.vue_bridge.showNotification.emit('success', f'프리셋 "{name}" 로드됨')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'프리셋 로드 실패: {e}')

            # 11. I2I/Inpaint 생성 (Vue payload를 탭에 주입 후 실행)
            elif action == 'generate_i2i':
                if hasattr(self, 'i2i_tab'):
                    self.i2i_tab.main_window = self
                    self.i2i_tab.generate_from_payload(payload)
            elif action == 'generate_inpaint':
                if hasattr(self, 'inpaint_tab'):
                    self.inpaint_tab.main_window = self
                    self.inpaint_tab.generate_from_payload(payload)

            # 12. 배치/업스케일
            elif action == 'start_batch':
                if hasattr(self, 'batch_tab'):
                    self.batch_tab.main_window = self
                    self.batch_tab.start_from_payload(payload)
            elif action == 'start_upscale':
                if hasattr(self, 'upscale_tab'):
                    self.upscale_tab.main_window = self
                    self.upscale_tab.start_from_payload(payload)

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

            # 15. Search parquet 저장/불러오기
            elif action == 'export_search_results':
                # Vue에서 필터링된 결과를 직접 받아서 저장
                path, _ = QFileDialog.getSaveFileName(self, "검색 결과 저장", "", "Parquet Files (*.parquet)")
                if path:
                    try:
                        import pandas as pd
                        data = payload.get('data')
                        if data and isinstance(data, list):
                            df = pd.DataFrame(data)
                        elif hasattr(self, 'filtered_results') and self.filtered_results:
                            df = pd.DataFrame(self.filtered_results)
                        else:
                            self.show_status("Export: no results")
                            return
                        df.to_parquet(path)
                        self.show_status(f"Exported {len(df)} results")
                        if hasattr(self, 'vue_bridge'):
                            self.vue_bridge.showNotification.emit('success', f'{len(df)}건 내보내기 완료')
                    except Exception as e:
                        self.show_status(f"Export failed: {e}")
                        if hasattr(self, 'vue_bridge'):
                            self.vue_bridge.showNotification.emit('error', f'내보내기 실패: {e}')

            elif action == 'import_search_results':
                path, _ = QFileDialog.getOpenFileName(self, "검색 결과 불러오기", "", "Parquet Files (*.parquet)")
                if path:
                    try:
                        import pandas as pd
                        df = pd.read_parquet(path)
                        out = []
                        for _, row in df.iterrows():
                            out.append({
                                'copyright': str(row.get('tag_string_copyright', row.get('copyright', ''))),
                                'character': str(row.get('tag_string_character', row.get('character', ''))),
                                'artist': str(row.get('tag_string_artist', row.get('artist', ''))),
                                'general': str(row.get('tag_string_general', row.get('general', ''))),
                                'rating': str(row.get('rating', '')),
                            })
                        self._last_search_results = out
                        # Python filtered_results + shuffled_prompt_deck 업데이트
                        import random as _rnd
                        self.filtered_results = out
                        self.shuffled_prompt_deck = out.copy()
                        _rnd.shuffle(self.shuffled_prompt_deck)
                        if hasattr(self, '_save_deck_state'):
                            self._save_deck_state()
                        # Vue로 결과 전달
                        self.vue_bridge.searchResultsReady.emit(json.dumps(out))
                        self.show_status(f"Imported {len(out)} results")
                    except Exception as e:
                        self.show_status(f"Import failed: {e}")

            # 16. 자동화 설정/토글
            elif action == 'set_automation_settings':
                self._vue_automation_settings = {
                    'mode': str(payload.get('mode', 'count')),
                    'limit': payload.get('limit', 10),
                    'repeat': payload.get('repeat', 1),
                    'delay': payload.get('delay', 1.0),
                    'allowDupes': bool(payload.get('allowDupes', False)),
                    # PR 3: 재시도 설정 (기본 2회)
                    'maxRetries': int(payload.get('maxRetries', 2)),
                    # F2: 정기 cleanup 주기 (LoRA patches 누적 회피용, 0=비활성)
                    'cleanupEveryN': int(payload.get('cleanupEveryN', 0)),
                }
                # 생성 시 태그→자연어 자동 변환 (자동화 루프에서 nl_caption 적용)
                self._auto_nl_enabled = bool(payload.get('autoNl', False))
                self._auto_nl_url = str(payload.get('ollamaUrl', '') or 'http://localhost:11434')
                self._auto_nl_model = str(payload.get('ollamaModel', '') or '')
                # queue_manager에 즉시 반영
                try:
                    if hasattr(self, 'queue_manager'):
                        self.queue_manager.cleanup_every_n = int(payload.get('cleanupEveryN', 0))
                        delay_v = float(payload.get('delay', 1.0))
                        self.queue_manager.delay_seconds = max(0.0, delay_v)
                except Exception:
                    pass
                # PR 9: 모드별로 자동 저장
                if hasattr(self, 'automation_persistence'):
                    self.automation_persistence.save_mode_settings()

            elif action == 'toggle_automation':
                checked = payload.get('checked', False)
                if hasattr(self, 'btn_auto_toggle'):
                    self.btn_auto_toggle.setChecked(bool(checked))
                else:
                    self.toggle_automation_ui(bool(checked))
                # 자동화 모드 ON 시 덱 현황 즉시 전송 → '시작' 전에도 남은/사용 개수 표시
                # (자동화 종료 후·UI 재시작 후 복원된 덱 진행도를 바로 확인 가능)
                if checked and hasattr(self, '_emit_auto_status'):
                    self._emit_auto_status()
            elif action == 'stop_automation':
                if self.is_automating:
                    self._stop_automation("사용자가 자동화를 중지했습니다.")

            # ═══════ 워크플로우 프로파일 ═══════
            elif action == 'workflow_profile_list':
                self._send_workflow_profiles_list()
            elif action == 'workflow_profile_save':
                name = str(payload.get('name', '')).strip()
                if name:
                    from core.workflow_profiles import collect_from_host, save_profile
                    snap = collect_from_host(self)
                    ok = save_profile(name, snap['fields'], snap['lora_stack'])
                    if ok:
                        self._send_workflow_profiles_list()
                        if hasattr(self, 'vue_bridge'):
                            self.vue_bridge.showNotification.emit(
                                'success', f'프로파일 저장: {name}'
                            )
                    else:
                        if hasattr(self, 'vue_bridge'):
                            self.vue_bridge.showNotification.emit(
                                'error', f'프로파일 저장 실패: {name}'
                            )
            elif action == 'workflow_profile_load':
                name = str(payload.get('name', '')).strip()
                if name:
                    from core.workflow_profiles import load_profile, apply_profile_to_host
                    data = load_profile(name)
                    if data:
                        result = apply_profile_to_host(data, self)
                        # 전체 프롬프트 다시 업데이트
                        if hasattr(self, 'update_total_prompt_display'):
                            self.update_total_prompt_display()
                        if hasattr(self, 'vue_bridge'):
                            self.vue_bridge.showNotification.emit(
                                'success',
                                f'프로파일 적용: {name} '
                                f'({len(result["applied"])}개)'
                            )
                    else:
                        if hasattr(self, 'vue_bridge'):
                            self.vue_bridge.showNotification.emit(
                                'error', f'프로파일을 찾을 수 없음: {name}'
                            )
            elif action == 'workflow_profile_delete':
                name = str(payload.get('name', '')).strip()
                if name:
                    from core.workflow_profiles import delete_profile
                    delete_profile(name)
                    self._send_workflow_profiles_list()
            elif action == 'workflow_profile_rename':
                old = str(payload.get('old', '')).strip()
                new = str(payload.get('new', '')).strip()
                if old and new:
                    from core.workflow_profiles import rename_profile
                    if rename_profile(old, new):
                        self._send_workflow_profiles_list()

            # ═══════ 프롬프트 섹션 순서 (사용자 지정) ═══════
            elif action == 'prompt_order_list':
                self._send_prompt_order()
            elif action == 'prompt_order_save':
                new_order = payload.get('order', [])
                if isinstance(new_order, list):
                    from core.prompt_order import save_order
                    save_order([str(k) for k in new_order])
                    self._send_prompt_order()
                    self.update_total_prompt_display()  # 즉시 반영
            elif action == 'prompt_order_reset':
                from core.prompt_order import reset_to_default
                reset_to_default()
                self._send_prompt_order()
                self.update_total_prompt_display()

            # ═══════ PR 8: Instant Wildcards (JSON 인라인) ═══════
            elif action == 'instant_wildcards_list':
                self._send_instant_wildcards_list()
            elif action == 'instant_wildcards_save':
                name = str(payload.get('name', '')).strip()
                lines = payload.get('lines', [])
                if name and isinstance(lines, list):
                    iw = self._get_instant_wildcards()
                    iw.set(name, [str(l) for l in lines])
                    iw.save()
                    self._send_instant_wildcards_list()
            elif action == 'instant_wildcards_delete':
                name = str(payload.get('name', '')).strip()
                if name:
                    iw = self._get_instant_wildcards()
                    iw.delete(name)
                    iw.save()
                    self._send_instant_wildcards_list()

            # ═══════ 이벤트 생성 (EventGen) ═══════
            elif action == 'search_events':
                self._start_event_search(payload)
            elif action == 'export_event_results':
                self._export_event_results(payload)
            elif action == 'import_event_results':
                self._import_event_results()

            elif action == 'select_event':
                idx = payload.get('index', 0)
                if hasattr(self, 'event_gen_tab') and hasattr(self.event_gen_tab, 'result_list'):
                    if 0 <= idx < self.event_gen_tab.result_list.count():
                        self.event_gen_tab.result_list.setCurrentRow(idx)
                        self.event_gen_tab._on_result_clicked(idx)

            elif action == 'event_add_to_queue':
                if hasattr(self, 'event_gen_tab'):
                    scenarios = payload.get('scenarios', [])
                    if scenarios:
                        self.receive_event_scenarios(scenarios)
                    elif hasattr(self.event_gen_tab, '_build_scenarios'):
                        scenarios = self.event_gen_tab._build_scenarios()
                        self.receive_event_scenarios(scenarios)

            elif action == 'event_generate_now':
                if hasattr(self, 'event_gen_tab'):
                    if hasattr(self.event_gen_tab, '_build_scenarios'):
                        scenarios = self.event_gen_tab._build_scenarios()
                        self.receive_event_scenarios(scenarios)
                        if hasattr(self, 'queue_manager'):
                            self.queue_manager.start()

            # ═══════ PNG Info 전송/생성 ═══════
            elif action == 'pnginfo_send_prompt':
                prompt = payload.get('prompt', '')
                negative = payload.get('negative', '')
                self.handle_prompt_only_transfer(prompt, negative)

            elif action == 'pnginfo_generate':
                # EXIF 데이터에서 payload 구성하여 즉시 생성
                raw = payload.get('raw', payload.get('parameters', ''))
                if raw:
                    self._handle_immediate_generation_from_raw(raw)

            # ═══════ History 우클릭 — 프롬프트 당겨오기 ═══════
            elif action == 'pull_prompt_from_image':
                path = _clean_path(payload.get('path', ''))
                if path and os.path.exists(path):
                    try:
                        info = json.loads(self.vue_bridge.getImageExif(path))
                        prompt = info.get('prompt', '')
                        negative = info.get('negative', '')
                        if prompt or negative:
                            self.handle_prompt_only_transfer(prompt, negative)
                            self.vue_bridge.showNotification.emit('success', '프롬프트를 당겨왔습니다')
                        else:
                            self.vue_bridge.showNotification.emit('warning', '이 이미지에 프롬프트 정보가 없습니다')
                    except Exception as e:
                        self.vue_bridge.showNotification.emit('error', f'프롬프트 로드 실패: {e}')

            # ═══════ History 우클릭 — 다음 큐에 추가 ═══════
            elif action == 'add_image_to_queue':
                path = _clean_path(payload.get('path', ''))
                if path and os.path.exists(path):
                    try:
                        info = json.loads(self.vue_bridge.getImageExif(path))
                        qp = self._build_queue_payload_from_exif(info)
                        if qp and hasattr(self, 'queue_panel'):
                            self.queue_panel.add_single_item(qp)
                            self.vue_bridge.showNotification.emit('success', '다음 큐에 추가되었습니다')
                        else:
                            self.vue_bridge.showNotification.emit('warning', '이 이미지에 생성 정보가 없습니다')
                    except Exception as e:
                        self.vue_bridge.showNotification.emit('error', f'큐 추가 실패: {e}')

            # ═══════ XYZ Plot 실행 ═══════
            elif action == 'start_xyz_plot':
                axes = payload.get('axes', [])
                combinations = payload.get('combinations', [])
                if combinations and hasattr(self, 'queue_panel'):
                    for combo in combinations:
                        p = self._build_xyz_payload(combo)
                        self.queue_panel.add_single_item(p)
                    self.show_status(f"XYZ Plot: {len(combinations)} jobs queued.")
                    if hasattr(self, 'queue_manager'):
                        self.queue_manager.start()

            # ═══════ 배치 파일 열기 ═══════
            elif action in ('open_batch_files', 'open_upscale_files'):
                title = "배치 처리할 이미지 선택" if 'batch' in action else "업스케일할 이미지 선택"
                paths, _ = QFileDialog.getOpenFileNames(self, title, "", "Images (*.png *.jpg *.jpeg *.webp);;All Files (*)")
                if paths:
                    file_list = [p.replace('\\', '/') for p in paths]
                    self.vue_bridge.batchFilesSelected.emit(json.dumps(file_list))
                    self.show_status(f"{len(file_list)} files selected.")

            # ═══════ 캡션 대상 선택 (다중 파일 + 폴더) ═══════
            elif action == 'caption_pick_files':
                paths, _ = QFileDialog.getOpenFileNames(self, "캡션할 이미지 선택", "", "Images (*.png *.jpg *.jpeg *.webp);;All Files (*)")
                if paths:
                    self.vue_bridge.captionFilesSelected.emit(
                        json.dumps([p.replace('\\', '/') for p in paths]))
            elif action == 'caption_pick_folder':
                folder = QFileDialog.getExistingDirectory(self, "캡션할 폴더 선택")
                if folder:
                    import glob
                    imgs = []
                    for ext in ('*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp'):
                        imgs.extend(glob.glob(os.path.join(folder, ext)))
                        imgs.extend(glob.glob(os.path.join(folder, ext.upper())))
                    imgs = sorted(set(p.replace('\\', '/') for p in imgs))
                    if imgs:
                        self.vue_bridge.captionFilesSelected.emit(json.dumps(imgs))
                        self.vue_bridge.showNotification.emit('info', f'{len(imgs)}개 이미지 발견')
                    else:
                        self.vue_bridge.showNotification.emit('warning', '이미지가 없습니다')
            elif action == 'caption_pick_outdir':
                folder = QFileDialog.getExistingDirectory(self, "캡션 저장 폴더 선택")
                if folder:
                    self.vue_bridge.captionOutDirSelected.emit(folder.replace('\\', '/'))

            # ═══════ 클립보드 복사 ═══════
            elif action == 'copy_to_clipboard':
                path = payload.get('path', '')
                if path:
                    clean = _clean_path(path)
                    from PyQt6.QtGui import QPixmap
                    pix = QPixmap(clean)
                    if not pix.isNull():
                        QApplication.clipboard().setPixmap(pix)
                        self.show_status("Copied to clipboard.")

            # ═══════ YOLO 모델 초기화 ═══════
            elif action == 'editor_clear_yolo_models':
                if hasattr(self, 'mosaic_editor') and self.mosaic_editor.mosaic_panel:
                    panel = self.mosaic_editor.mosaic_panel
                    panel._yolo_model_paths.clear()
                    from tabs.editor.mosaic_panel import _save_yolo_model_paths
                    _save_yolo_model_paths([])
                    panel._update_model_label()
                    self.vue_bridge.yoloModelUpdated.emit("No Model Loaded")
                    self.show_status("YOLO models cleared.")

            # ═══════ Gallery EXIF → T2I ═══════
            elif action == 'gallery_send_exif_to_t2i':
                exif_raw = payload.get('exif', '')
                if exif_raw:
                    parts = exif_raw.split('\nNegative prompt: ')
                    prompt = parts[0].strip()
                    negative = ''
                    if len(parts) > 1:
                        sub = parts[1].split('\nSteps: ')
                        negative = sub[0].strip()
                    self.handle_prompt_only_transfer(prompt, negative)

            # ═══════ Gallery 폴더 열기 다이얼로그 ═══════
            elif action == 'gallery_open_folder':
                from config import OUTPUT_DIR
                last = self.vue_bridge.getLastGalleryFolder() or OUTPUT_DIR
                folder = QFileDialog.getExistingDirectory(self, "Gallery 폴더 선택", last)
                if folder:
                    self.vue_bridge._save_gallery_folder(folder)
                    self.vue_bridge.galleryFolderLoaded.emit(folder.replace('\\', '/'))

            # ═══════ 즐겨찾기 제거 ═══════
            elif action == 'remove_favorite':
                path = payload.get('path', '')
                if path:
                    clean = _clean_path(path)
                    self._load_favorites_from_file()
                    if clean in self.favorites_list:
                        self.favorites_list.remove(clean)
                        self._save_favorites_to_file()
                    self.show_status("Removed from favorites.")

            # ═══════ API 관리자 ═══════
            elif action == 'show_api_manager':
                try:
                    # Settings에서 호출 시 X버튼=종료 방지
                    self._api_manager_mode = True
                    self._startup_backend_check()
                    self._apply_backend_startup_result()
                    self._api_manager_mode = False
                    self.vue_bridge.showNotification.emit('success', 'API 연결 확인 완료')
                except SystemExit:
                    # X버튼으로 다이얼로그 닫힘 — 앱 종료 안 함
                    self._api_manager_mode = False
                    self.vue_bridge.showNotification.emit('info', 'API 설정 취소됨')
                except Exception as e:
                    self._api_manager_mode = False
                    self.vue_bridge.showNotification.emit('error', f'API 연결 실패: {e}')

            # ═══════ 탭 순서 설정 ═══════
            elif action == 'set_tab_order':
                order = payload.get('order', [])
                if order:
                    self.show_status(f"Tab order updated: {len(order)} tabs")

            # ═══════ 시드 탐색 (3x3 그리드) ═══════
            elif action == 'explore_seed':
                base_seed = int(payload.get('seed', -1))
                if base_seed < 0:
                    base_seed = random.randint(0, 2**32 - 1)
                # subseed_strength 0.05 단위로 9개 변형
                variations = []
                for i in range(9):
                    subseed = base_seed + i * 1000
                    strength = round(0.05 * (i % 5), 2) if i > 0 else 0
                    p = {
                        'prompt': self.total_prompt_display.toPlainText(),
                        'negative_prompt': self.neg_prompt_text.toPlainText(),
                        'sampler_name': self.sampler_combo.currentText(),
                        'steps': int(self.steps_input.text() or 20),
                        'cfg_scale': float(self.cfg_input.text() or 7),
                        'seed': base_seed,
                        'subseed': subseed,
                        'subseed_strength': strength,
                        'width': int(self.width_input.text() or 1024),
                        'height': int(self.height_input.text() or 1024),
                    }
                    variations.append(p)
                # 대기열에 추가
                if hasattr(self, 'queue_panel'):
                    for p in variations:
                        self.queue_panel.add_single_item(p)
                    if hasattr(self, 'queue_manager'):
                        self.queue_manager.start()
                self.vue_bridge.showNotification.emit('info', f'시드 탐색: {len(variations)}개 변형 생성 시작')

            # ═══════ 비교 이미지 ═══════
            elif action == 'open_compare_image':
                slot = payload.get('slot', 'before')
                path, _ = QFileDialog.getOpenFileName(self, "비교 이미지 선택", "", "Images (*.png *.jpg *.jpeg *.webp)")
                if path:
                    self.vue_bridge.compareImageLoaded.emit(json.dumps({'slot': slot, 'path': path.replace('\\', '/')}))

            elif action == 'open_url':
                url = payload.get('url', '')
                if url:
                    import webbrowser
                    webbrowser.open(url)

            elif action == 'send_to_compare':
                path = payload.get('path', '')
                slot = payload.get('slot', 'after')
                if path:
                    clean = _clean_path(path).replace('\\', '/')
                    if clean.startswith('/') and ':' in clean[1:3]: clean = clean[1:]
                    self.vue_bridge.tabChanged.emit('png')
                    QTimer.singleShot(100, lambda: self.vue_bridge.compareImageLoaded.emit(json.dumps({'slot': slot, 'path': clean})))

            # ═══════ UI 설정 저장 ═══════
            elif action == 'save_ui_prefs':
                try:
                    from core.config_migration import load_ui_prefs, save_ui_prefs
                    prefs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'ui_prefs.json')
                    prefs = load_ui_prefs(prefs_path)
                    for legacy_key in (
                        'hires_enabled',
                        'ad_enabled',
                        'sam3_enabled',
                        'ad_s1_enabled',
                        'ad_s2_enabled',
                        'negpip_enabled',
                    ):
                        prefs.pop(legacy_key, None)
                        payload.pop(legacy_key, None)
                    prefs.update(payload)
                    save_ui_prefs(prefs_path, prefs)
                    # FIX: Vue의 LOGIC 토글을 prompt_cleaner에 즉시 적용
                    # (이전에는 저장만 되고 효과 없었음)
                    self._apply_ui_prefs_to_cleaner(prefs)
                    # 재전송 하지 않음 — uiPrefsLoaded는 앱 시작 시에만 emit
                    # 재전송하면 watch → save → emit → watch 무한 루프 발생
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'UI 설정 저장 실패: {e}')

            # ═══════ 글로벌 가중치 저장 ═══════
            elif action == 'save_global_weights':
                try:
                    weights = payload.get('weights', [])
                    wpath = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'global_weights.json')
                    os.makedirs(os.path.dirname(wpath), exist_ok=True)
                    with open(wpath, 'w', encoding='utf-8') as f:
                        json.dump(weights, f, ensure_ascii=False, indent=2)
                    self.vue_bridge.showNotification.emit('success', '가중치가 저장되었습니다')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'가중치 저장 실패: {e}')

            # ═══════ LoRA 텍스트 설정 ═══════
            elif action == 'set_lora_text':
                lora_text = payload.get('lora_text', '')
                self._vue_lora_text = lora_text

            elif action == 'set_lora_stack':
                entries = payload.get('entries', [])
                self._vue_lora_entries = entries if isinstance(entries, list) else []
                # Python lora_active_panel도 동기화
                if hasattr(self, 'lora_active_panel') and hasattr(self.lora_active_panel, 'set_entries'):
                    self.lora_active_panel.set_entries(self._vue_lora_entries)

            # ═══════ 조건부 프롬프트 저장 ═══════
            elif action == 'save_cond_rules':
                try:
                    cond_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'cond_rules.json')
                    os.makedirs(os.path.dirname(cond_path), exist_ok=True)
                    with open(cond_path, 'w', encoding='utf-8') as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                    self.vue_bridge.showNotification.emit('success', '조건식이 저장되었습니다')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'조건식 저장 실패: {e}')

            # ═══════ 기본값 저장 ═══════
            elif action == 'save_tab_defaults':
                try:
                    defaults_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'tab_defaults.json')
                    os.makedirs(os.path.dirname(defaults_path), exist_ok=True)
                    with open(defaults_path, 'w', encoding='utf-8') as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                    self.vue_bridge.showNotification.emit('success', '기본값이 저장되었습니다')
                except Exception as e:
                    self.vue_bridge.showNotification.emit('error', f'기본값 저장 실패: {e}')

            # ═══════ 대기열 제어 ═══════
            elif action == 'start_queue':
                if hasattr(self, 'queue_manager'):
                    self.queue_manager.start()
                    self.show_status("Queue started.")
                    self._sync_queue_to_vue()

            elif action == 'stop_queue':
                if hasattr(self, 'queue_manager'):
                    self.queue_manager.stop()
                    self.show_status("Queue stopped.")
                    self._sync_queue_to_vue()

            elif action == 'unload_model_request':
                # VRAM 게이지 클릭으로 사용자가 수동 unload 요청 — 백엔드에 위임
                try:
                    backend = getattr(self, 'backend', None) or getattr(self, '_backend', None)
                    if backend and hasattr(backend, 'unload_models'):
                        backend.unload_models()
                        self.show_status("Model unload requested.")
                    elif backend and hasattr(backend, 'unload'):
                        backend.unload()
                        self.show_status("Model unload requested.")
                    else:
                        # 폴백: AppContext를 통한 통보
                        try:
                            from core.app_context import get_context
                            get_context().emit('model_unload_requested', {})
                        except Exception:
                            pass
                        self.show_status("Unload signal sent (no direct backend method).")
                except Exception as e:
                    self.show_status(f"Unload failed: {e}")

            elif action == 'pause_queue':
                if hasattr(self, 'queue_manager'):
                    self.queue_manager.pause()
                    self.show_status("Queue paused.")
                    self._sync_queue_to_vue()

            elif action == 'resume_queue':
                if hasattr(self, 'queue_manager'):
                    self.queue_manager.resume()
                    self.show_status("Queue resumed.")
                    self._sync_queue_to_vue()

            elif action == 'remove_queue_items':
                # payload: { item_ids: [str, ...] }  — 여러 항목 일괄 삭제
                if hasattr(self, 'queue_panel'):
                    ids = payload.get('item_ids', []) or []
                    n = self.queue_panel.remove_items_by_ids(ids)
                    self.show_status(f"{n}개 항목 삭제")
                    self._sync_queue_to_vue()

            elif action == 'move_queue_item':
                # payload: { item_id: str, direction: 'up' | 'down' }
                if hasattr(self, 'queue_panel'):
                    iid = payload.get('item_id', '')
                    direction = payload.get('direction', 'up')
                    moved = (self.queue_panel.move_item_up(iid) if direction == 'up'
                             else self.queue_panel.move_item_down(iid))
                    if moved:
                        self._sync_queue_to_vue()

            elif action == 'update_queue_item':
                # payload: { item_id: str, prompt?: str, negative_prompt?: str } — 큐 항목 편집
                if hasattr(self, 'queue_panel'):
                    iid = payload.get('item_id', '')
                    found = False
                    for it in self.queue_panel.queue_items:
                        if it.get('id') == iid:
                            if 'prompt' in payload:
                                it['prompt'] = payload.get('prompt', '')
                            if 'negative_prompt' in payload:
                                it['negative_prompt'] = payload.get('negative_prompt', '')
                            found = True
                            break
                    if found:
                        try:
                            self.queue_panel._refresh_display()
                            self.queue_panel._persist_to_disk()
                        except Exception:
                            pass
                        self.show_status("큐 항목 수정됨")
                        self._sync_queue_to_vue()

            elif action == 'clear_queue':
                # 전체 삭제 — 확인 다이얼로그 우회 (Vue 측에서 이미 확인 받음)
                if hasattr(self, 'queue_panel') and self.queue_panel.queue_items:
                    self.queue_panel.queue_items.clear()
                    self.queue_panel._refresh_display()
                    self.queue_panel.queue_changed.emit(0)
                    self.queue_panel._persist_to_disk()
                    self._sync_queue_to_vue()

            # ═══════ Toast 표시 ═══════
            elif action == 'show_toast':
                t = payload.get('type', 'info')
                m = payload.get('msg', '')
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.showNotification.emit(t, m)

            # ═══════ 미처리 액션 로그 ═══════
            else:
                print(f"[Bridge] Unhandled action: {action}")

        except Exception as e:
            from core.error_handler import handle_error
            handle_error('E010', f'Action: {action}', e)

    def _persist_search_results(self, active, full=None):
        """검색 결과 디스크 영속화 — 단일 쓰기 경로(중복 제거).
        디스크 = 영속 단일 소스. 메모리(filtered_results/shuffled_prompt_deck)는 런타임 캐시,
        Vue localStorage(slim ≤500)는 폴백.
          active: 표시/자동화 덱용(필터 적용) 셋 → last_search_results.json (항상)
          full  : '필터 해제' 베이스(전체) 셋 → last_full_results.json (새 검색 때만 전달)
        NOTE: os/json은 모듈 레벨 import — 여기서 지역 재import 금지(UnboundLocalError 회피)."""
        try:
            cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
            os.makedirs(cache_dir, exist_ok=True)
            with open(os.path.join(cache_dir, 'last_search_results.json'),
                      'w', encoding='utf-8') as f:
                json.dump(active, f, ensure_ascii=False)
            if full is not None:
                with open(os.path.join(cache_dir, 'last_full_results.json'),
                          'w', encoding='utf-8') as f:
                    json.dump(full, f, ensure_ascii=False)
        except Exception as e:
            print(f"[Search] 디스크 영속 실패: {e}")

    def _restore_runtime_prefs(self, prefs: dict):
        """ui_prefs.json(단일 소스)에서 런타임 상태를 직접 복원.
        Vue가 set_rating_filter / set_high_res_factor 를 아직 안 보낸 시점(예: 재시작 직후
        자동화 즉시 시작)에도 올바른 rating 필터/고해상도 배율로 동작하도록 한다."""
        try:
            rf = prefs.get('ratingFilter')
            if isinstance(rf, list) and len(rf) == 4:
                keys = ('g', 's', 'q', 'e')
                self._rating_filter = {keys[i] for i, on in enumerate(rf) if on}
        except Exception:
            pass
        try:
            if prefs.get('highResEnabled'):
                factor = float(prefs.get('highResFactor', 1.5) or 1.5)
                self._high_res_factor = max(1.0, min(4.0, factor))
            else:
                self._high_res_factor = 1.0
        except Exception:
            pass
        try:
            lora = prefs.get('loraStack')
            if isinstance(lora, list):
                # 생성이 읽는 런타임 미러 — Vue가 set_lora_stack/set_lora_text를 아직 안 보낸
                # 시점(재시작 직후 자동화 즉시 시작 등)에도 올바른 LoRA로 생성되도록 한다.
                self._vue_lora_entries = lora
                from core.lora_stack import build_lora_text
                self._vue_lora_text = build_lora_text(lora)  # generator_generation이 읽음
                if hasattr(self, 'lora_active_panel'):
                    try:
                        self.lora_active_panel.set_entries(lora)
                    except Exception:
                        pass
        except Exception:
            pass

    def _migrate_legacy_lora_stack(self, prefs: dict, prefs_path: str):
        """LoRA 스택 단일 소스(ui_prefs.loraStack) 통합 — ui_prefs에 loraStack이 없고
        옛 prompt_settings.active_loras가 있으면 1회 흡수(prefs를 제자리 수정 + 영속)."""
        try:
            if not isinstance(prefs, dict) or isinstance(prefs.get('loraStack'), list):
                return
            ps_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   'config', 'prompt_settings.json')
            if not os.path.exists(ps_path):
                return
            with open(ps_path, 'r', encoding='utf-8') as f:
                ps = json.load(f)
            legacy = ps.get('active_loras') if isinstance(ps, dict) else None
            if isinstance(legacy, list) and legacy:
                prefs['loraStack'] = legacy
                with open(prefs_path, 'w', encoding='utf-8') as f:
                    json.dump(prefs, f, ensure_ascii=False, indent=2)
                print(f"[Config] Legacy active_loras migrated → ui_prefs.loraStack ({len(legacy)})")
        except Exception as e:
            print(f"[Config] Legacy lora migration skipped: {e}")

    def _migrate_legacy_cond_rules(self, cond_path: str):
        """옛 전역 조건식(prompt_settings.cond_rules_json) → config/cond_rules.json 1회 이관.
        cond_rules.json이 아직 없을 때만 실행하여 레거시 cond_block_editor 데이터 유실을 방지한다."""
        try:
            ps_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   'config', 'prompt_settings.json')
            if not os.path.exists(ps_path):
                return
            with open(ps_path, 'r', encoding='utf-8') as f:
                ps = json.load(f)
            legacy = ps.get('cond_rules_json', '') if isinstance(ps, dict) else ''
            if not legacy:
                return
            from utils.condition_block import legacy_cond_rules_to_vue
            vue = legacy_cond_rules_to_vue(legacy)
            if not (vue.get('positive') or vue.get('negative')):
                return
            os.makedirs(os.path.dirname(cond_path), exist_ok=True)
            with open(cond_path, 'w', encoding='utf-8') as f:
                json.dump(vue, f, ensure_ascii=False, indent=2)
            print(f"[Config] Legacy cond rules migrated → cond_rules.json "
                  f"({len(vue['positive'])}P + {len(vue['negative'])}N)")
        except Exception as e:
            print(f"[Config] Legacy cond migration skipped: {e}")

    def _load_saved_configs(self):
        """앱 시작 시 조건식 + 기본값 로드"""
        try:
            # 조건식 로드 — config/cond_rules.json 단일 소스
            cond_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'cond_rules.json')
            if not os.path.exists(cond_path):
                # 레거시 1회 마이그레이션: 옛 prompt_settings.cond_rules_json → cond_rules.json
                self._migrate_legacy_cond_rules(cond_path)
            if os.path.exists(cond_path):
                with open(cond_path, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.condRulesLoaded.emit(json.dumps(rules))
                print(f"[Config] Conditional rules loaded: {len(rules.get('positive',[]))}P + {len(rules.get('negative',[]))}N")
        except Exception as e:
            print(f"[Config] Failed to load cond rules: {e}")
        try:
            # 기본값 로드 + 적용
            # FIX: 이전엔 prompt_settings.json 없을 때만 적용 → 사실상 첫 실행만.
            # 이제 처음 실행이면 모든 필드, 이후엔 빈 위젯만 채우기.
            defaults_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'tab_defaults.json')
            if os.path.exists(defaults_path):
                with open(defaults_path, 'r', encoding='utf-8') as f:
                    defaults = json.load(f)
                from config import PROMPT_SETTINGS_FILE
                first_run = not os.path.exists(PROMPT_SETTINGS_FILE)
                # 첫 실행이면 모든 defaults 적용
                if first_run:
                    if 'hires_enabled' in defaults:
                        self.hires_options_group.setChecked(bool(defaults.get('hires_enabled')))
                    if 'ad_enabled' in defaults:
                        self.adetailer_group.setChecked(bool(defaults.get('ad_enabled')))
                    if 'sam3_enabled' in defaults and hasattr(self, 'sam3_group'):
                        self.sam3_group.setChecked(bool(defaults.get('sam3_enabled')))
                    if 'ad_s1_enabled' in defaults and hasattr(self, 'ad_slot1_group'):
                        self.ad_slot1_group.setChecked(bool(defaults.get('ad_s1_enabled')))
                    if 'ad_s2_enabled' in defaults and hasattr(self, 'ad_slot2_group'):
                        self.ad_slot2_group.setChecked(bool(defaults.get('ad_s2_enabled')))
                    if 'negpip_enabled' in defaults:
                        self.negpip_group.setChecked(bool(defaults.get('negpip_enabled')))

                # 첫 실행이든 아니든 — 핵심 생성 파라미터를 위젯이 비어있을 때만 채움
                # (사용자가 저장한 값을 덮어쓰지 않음)
                self._apply_tab_defaults_to_empty_widgets(defaults, first_run=first_run)
                print(f"[Config] Tab defaults loaded ({'first run — full' if first_run else 'empty fields only'})")
        except Exception as e:
            print(f"[Config] Failed to load defaults: {e}")
        try:
            wpath = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'global_weights.json')
            if os.path.exists(wpath):
                with open(wpath, 'r', encoding='utf-8') as f:
                    weights = json.load(f)
                if hasattr(self, 'vue_bridge'):
                    self.vue_bridge.globalWeightsLoaded.emit(json.dumps(weights))
                print(f"[Config] Global weights loaded: {len(weights)} tags")
        except Exception as e:
            print(f"[Config] Failed to load weights: {e}")
        try:
            from core.config_migration import load_ui_prefs
            prefs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'ui_prefs.json')
            prefs = load_ui_prefs(prefs_path)
            # 레거시 흡수: ui_prefs에 loraStack이 없고 옛 prompt_settings.active_loras가 있으면 1회 이관
            self._migrate_legacy_lora_stack(prefs, prefs_path)
            if prefs and hasattr(self, 'vue_bridge'):
                self.vue_bridge.uiPrefsLoaded.emit(json.dumps(prefs))
                # FIX: 시작 시점에 LOGIC 토글을 prompt_cleaner에 적용
                self._apply_ui_prefs_to_cleaner(prefs)
                # 단일 소스(ui_prefs.json)에서 런타임 상태 직접 복원 —
                #   Vue가 set_rating_filter/set_high_res_factor를 아직 안 보낸 시점(자동화 즉시 시작 등)에도 올바른 값.
                self._restore_runtime_prefs(prefs)
                print(f"[Config] UI prefs loaded + LOGIC toggles applied")
        except Exception as e:
            print(f"[Config] Failed to load UI prefs: {e}")

    def _apply_vue_conditional_rules(self, pos_rules: list, neg_rules: list):
        """Vue에서 전달된 조건부 프롬프트 규칙 적용"""
        try:
            current_tags = set(t.strip().lower() for t in self.main_prompt_text.toPlainText().split(',') if t.strip())

            for rule in pos_rules:
                cond = rule.get('condition', '').strip().lower()
                exists = rule.get('exists', True)
                target = rule.get('target', '').strip()
                action = rule.get('action', 'add')
                location = rule.get('location', 'main')
                if not cond or not target: continue

                cond_met = (cond in current_tags) if exists else (cond not in current_tags)
                if not cond_met: continue

                widget_map = {
                    'main': self.main_prompt_text,
                    'prefix': self.prefix_prompt_text,
                    'suffix': self.suffix_prompt_text,
                }
                widget = widget_map.get(location, self.main_prompt_text)
                text = widget.toPlainText()

                if action == 'add':
                    if target.lower() not in text.lower():
                        widget.setPlainText((text + ', ' + target).strip(', '))
                elif action == 'remove':
                    tags = [t.strip() for t in text.split(',')]
                    tags = [t for t in tags if t.lower() != target.lower()]
                    widget.setPlainText(', '.join(tags))
                elif action == 'replace':
                    widget.setPlainText(text.replace(cond, target))

            for rule in neg_rules:
                cond = rule.get('condition', '').strip().lower()
                exists = rule.get('exists', True)
                target = rule.get('target', '').strip()
                action = rule.get('action', 'add')
                if not cond or not target: continue

                cond_met = (cond in current_tags) if exists else (cond not in current_tags)
                if not cond_met: continue

                neg_text = self.neg_prompt_text.toPlainText()
                if action == 'add':
                    if target.lower() not in neg_text.lower():
                        self.neg_prompt_text.setPlainText((neg_text + ', ' + target).strip(', '))
                elif action == 'remove':
                    tags = [t.strip() for t in neg_text.split(',')]
                    tags = [t for t in tags if t.lower() != target.lower()]
                    self.neg_prompt_text.setPlainText(', '.join(tags))
        except Exception as e:
            print(f"[Error] Conditional rules: {e}")

    def _apply_settings_dict(self, settings: dict):
        """프리셋 딕셔너리를 UI에 적용"""
        try:
            if hasattr(self, 'vue_bridge'):
                self.vue_bridge.beginBatchUpdate()
            mapping = {
                'char_count': self.char_count_input,
                'character': self.character_input,
                'copyright': self.copyright_input,
                'main_prompt': self.main_prompt_text,
                'prefix_prompt': self.prefix_prompt_text,
                'suffix_prompt': self.suffix_prompt_text,
                'negative_prompt': self.neg_prompt_text,
                'steps': self.steps_input,
                'cfg': self.cfg_input,
                'seed': self.seed_input,
                'width': self.width_input,
                'height': self.height_input,
            }
            for key, widget in mapping.items():
                if key in settings:
                    val = str(settings[key])
                    if hasattr(widget, 'setPlainText'):
                        widget.setPlainText(val)
                    elif hasattr(widget, 'setText'):
                        widget.setText(val)
            if 'artist' in settings:
                self.artist_input.setPlainText(str(settings['artist']))
            if 'model' in settings and settings['model']:
                self.model_combo.setCurrentText(str(settings['model']))
            if 'sampler' in settings and settings['sampler']:
                self.sampler_combo.setCurrentText(str(settings['sampler']))
            # LoRA 스택: ui_prefs.json(loraStack) 단일 소스로 이관 — 여기서 active_loras를 읽지 않는다.
            #   (_restore_runtime_prefs가 ui_prefs.loraStack에서 _vue_lora_entries를 채우고 패널/Vue에 복원)
            if hasattr(self, 'vue_bridge'):
                self.vue_bridge.endBatchUpdate()
            self.update_total_prompt_display()
        except Exception as e:
            print(f"[Error] Apply settings dict: {e}")

    # ========== PNG Info → 즉시 생성 ==========

    def _handle_immediate_generation_from_raw(self, raw: str):
        """PNG Info raw 텍스트에서 payload 구성하여 즉시 생성"""
        try:
            parts = raw.split('\nNegative prompt: ')
            prompt = parts[0].strip()
            negative = ''
            params = {}
            if len(parts) > 1:
                sub = parts[1].split('\nSteps: ')
                negative = sub[0].strip()
                if len(sub) > 1:
                    for kv in ('Steps: ' + sub[1]).split(', '):
                        if ':' in kv:
                            k, v = kv.split(':', 1)
                            params[k.strip().lower().replace(' ', '_')] = v.strip()
            # 프롬프트 설정
            self.main_prompt_text.setPlainText(prompt)
            self.neg_prompt_text.setPlainText(negative)
            if 'steps' in params: self.steps_input.setText(params['steps'])
            if 'cfg_scale' in params: self.cfg_input.setText(params['cfg_scale'])
            if 'seed' in params: self.seed_input.setText(params['seed'])
            if 'size' in params:
                wh = params['size'].split('x')
                if len(wh) == 2:
                    self.width_input.setText(wh[0].strip())
                    self.height_input.setText(wh[1].strip())
            self.update_total_prompt_display()
            self.start_generation()
        except Exception as e:
            print(f"[Error] Immediate generation from raw: {e}")

    def _build_queue_payload_from_exif(self, info: dict):
        """getImageExif 결과(dict)에서 큐 아이템 payload 구성.

        이미지의 프롬프트/샘플러/steps/cfg/해상도는 EXIF에서 그대로 가져오고,
        seed는 -1(새 변형)로 둔다 — 동일 시드 재생성은 같은 이미지라 무의미하므로
        '비슷한 걸 더 생성'이 자연스러운 기본값. 프롬프트 없으면 None 반환.
        """
        raw = info.get('raw', '') or ''
        prompt = info.get('prompt', '') or (raw.split('\nNegative prompt:')[0].strip() if raw else '')
        negative = info.get('negative', '') or ''
        if not prompt:
            return None
        # raw의 'Steps: ...' 파라미터 라인을 key→value로 파싱
        params = {}
        if 'Steps:' in raw:
            tail = raw.split('Steps:', 1)[1]
            for kv in ('Steps:' + tail).split(', '):
                if ':' in kv:
                    k, v = kv.split(':', 1)
                    params[k.strip().lower().replace(' ', '_')] = v.strip()

        def _to_int(v, d):
            try: return int(float(v))
            except (TypeError, ValueError): return d
        def _to_float(v, d):
            try: return float(v)
            except (TypeError, ValueError): return d

        qp = {
            'prompt': prompt,
            'negative_prompt': negative,
            'sampler_name': params.get('sampler') or self.sampler_combo.currentText(),
            'scheduler': params.get('schedule_type') or self.scheduler_combo.currentText(),
            'steps': _to_int(params.get('steps'), int(self.steps_input.text() or 20)),
            'cfg_scale': _to_float(params.get('cfg_scale'), float(self.cfg_input.text() or 7)),
            'seed': -1,  # 새 변형 (동일 시드 재생성은 무의미)
            'width': int(self.width_input.text() or 1024),
            'height': int(self.height_input.text() or 1024),
        }
        if 'size' in params:
            wh = params['size'].split('x')
            if len(wh) == 2:
                qp['width'] = _to_int(wh[0], qp['width'])
                qp['height'] = _to_int(wh[1], qp['height'])
        return qp

    def _build_xyz_payload(self, combo: dict) -> dict:
        """XYZ 조합에서 생성 payload 구성"""
        payload = {
            'prompt': self.total_prompt_display.toPlainText(),
            'negative_prompt': self.neg_prompt_text.toPlainText(),
            'sampler_name': self.sampler_combo.currentText(),
            'scheduler': self.scheduler_combo.currentText(),
            'steps': int(self.steps_input.text() or 20),
            'cfg_scale': float(self.cfg_input.text() or 7),
            'seed': int(self.seed_input.text() or -1),
            'width': int(self.width_input.text() or 1024),
            'height': int(self.height_input.text() or 1024),
        }
        # XYZ 축 값 오버라이드
        for key, val in combo.items():
            if key == 'Steps': payload['steps'] = int(val)
            elif key == 'CFG Scale': payload['cfg_scale'] = float(val)
            elif key == 'Seed': payload['seed'] = int(val)
            elif key == 'Width': payload['width'] = int(val)
            elif key == 'Height': payload['height'] = int(val)
            elif key == 'Sampler': payload['sampler_name'] = val
            elif key == 'Scheduler': payload['scheduler'] = val
            elif key == 'Denoising': payload['denoising_strength'] = float(val)
            elif key == 'Prompt S/R':
                if ',' in val:
                    search, replace = val.split(',', 1)
                    payload['prompt'] = payload['prompt'].replace(search.strip(), replace.strip())
            elif key == 'Negative S/R':
                if ',' in val:
                    search, replace = val.split(',', 1)
                    payload['negative_prompt'] = payload['negative_prompt'].replace(search.strip(), replace.strip())
        return payload

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
        # 일시정지 상태 변경 시 Vue 동기화 (▶/⏸ 토글)
        if hasattr(self.queue_manager, 'paused_changed'):
            self.queue_manager.paused_changed.connect(lambda _p: self._sync_queue_to_vue())
        # 대기열 변경 (추가/삭제/순서변경) 시 Vue 동기화
        if hasattr(self.queue_panel, 'queue_changed'):
            self.queue_panel.queue_changed.connect(lambda _n: self._sync_queue_to_vue())
        if hasattr(self.queue_panel, 'item_added'):
            self.queue_panel.item_added.connect(self._sync_queue_to_vue)
        # add_single_item 래핑으로 Vue 동기화
        _orig_add = self.queue_panel.add_single_item
        def _wrapped_add(item):
            _orig_add(item)
            # 실제 생성된 항목(id 포함)을 전달 — 원본 item엔 id가 없어 Vue 중복 방지가
            # 동작하지 않던 문제 방지
            try:
                actual = self.queue_panel.queue_items[-1] if self.queue_panel.queue_items else item
            except Exception:
                actual = item
            self._sync_queue_item_added(actual)
        self.queue_panel.add_single_item = _wrapped_add

    def _sync_queue_item_added(self, item: dict):
        """대기열에 아이템 추가 시 Vue로 전달"""
        if hasattr(self, 'vue_bridge'):
            safe = {k: str(v)[:200] for k, v in item.items() if isinstance(v, (str, int, float, bool))}
            self.vue_bridge.queueItemAdded.emit(json.dumps(safe))

    def _sync_queue_to_vue(self):
        """전체 대기열 상태를 Vue로 전달. queue_items(list)를 그대로 직렬화."""
        if not (hasattr(self, 'vue_bridge') and hasattr(self, 'queue_panel')):
            return
        try:
            # 안전 직렬화 — 원시 타입만 통과시키되, prompt는 200자로 제한
            def _safe(d):
                out = {}
                for k, v in d.items():
                    if isinstance(v, str):
                        out[k] = v[:4000] if k in ('prompt', 'negative_prompt') else v[:500]
                    elif isinstance(v, (int, float, bool)):
                        out[k] = v
                return out
            items = [_safe(it) for it in self.queue_panel.queue_items]
            qm = getattr(self, 'queue_manager', None)
            running = bool(qm and getattr(qm, 'is_running', False))
            paused = bool(qm and getattr(qm, 'is_paused', False))
            # 현재 실행 중 인덱스 — 0번이 실행 중인 항목 (queue_manager는 첫 항목을 꺼내며 처리)
            current_index = 0 if (running and items) else -1
            state = {
                'items': items,
                'running': running,
                'paused': paused,
                'current_index': current_index,
                'completed': getattr(self, '_queue_completed_count', 0),
            }
            self.vue_bridge.queueUpdated.emit(json.dumps(state))
        except Exception as e:
            try:
                self.show_status(f"queue sync error: {e}")
            except Exception:
                pass

    def _apply_payload_to_ui(self, item: dict):
        """큐 아이템(payload dict)을 생성 UI에 적용 — 생성 직전 호출.

        큐 아이템의 'prompt'는 이미 완성된 '전체' 프롬프트이므로 total_prompt_display에
        직접 넣는다(start_generation이 total_prompt_display를 그대로 사용, 재계산 안 함).
        ★ 이 메서드가 이전 리팩터에서 누락돼 _on_generation_requested가 미정의 메서드를
        호출 → 큐 항목이 '직전 UI(선행 고정만)'로 생성되던 버그(⑦)의 원인이었음.
        """
        if not isinstance(item, dict):
            return
        self.is_programmatic_change = True
        try:
            if item.get('prompt') is not None:
                self.total_prompt_display.setPlainText(str(item.get('prompt') or ''))
            if item.get('negative_prompt') is not None:
                self.neg_prompt_text.setPlainText(str(item.get('negative_prompt') or ''))
            if item.get('sampler_name'):
                self.sampler_combo.setText(str(item['sampler_name']))
            if item.get('scheduler'):
                self.scheduler_combo.setText(str(item['scheduler']))
            if item.get('steps') is not None:
                self.steps_input.setText(str(item.get('steps')))
            if item.get('cfg_scale') is not None:
                self.cfg_input.setText(str(item.get('cfg_scale')))
            if item.get('seed') is not None:
                self.seed_input.setText(str(item.get('seed')))
            if item.get('width'):
                self.width_input.setText(str(item.get('width')))
            if item.get('height'):
                self.height_input.setText(str(item.get('height')))
        except Exception as e:
            print(f"[Queue] _apply_payload_to_ui 실패: {e}")
        finally:
            self.is_programmatic_change = False

    def _on_generation_requested(self, item: dict):
        self._apply_payload_to_ui(item)
        self.start_generation()

    def _on_queue_completed(self, total_count: int):
        self._queue_completed_count = total_count
        if hasattr(self, 'vue_bridge'):
            self.vue_bridge.queueCompleted.emit(json.dumps({'total': total_count}))
            self.vue_bridge.showNotification.emit('success', f'{total_count}장 생성 완료')
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
                    pct = int(used / total * 100) if total > 0 else 0
                    if hasattr(self, 'vue_bridge'):
                        self.vue_bridge.vramUpdated.emit(json.dumps({
                            'used': round(used, 1), 'total': round(total, 1), 'pct': pct
                        }))
        except Exception:
            pass  # VRAM 모니터링은 비핵심 — GPU 미탑재 환경에서 실패 가능

    def closeEvent(self, event):
        from PyQt6.QtWidgets import QMessageBox as _QMB
        msg = _QMB(self)
        msg.setWindowTitle("AI Studio Pro")
        msg.setText("앱을 종료하시겠습니까?")
        msg.setInformativeText("설정이 자동 저장됩니다.")
        msg.setStandardButtons(_QMB.StandardButton.Yes | _QMB.StandardButton.No)
        msg.setDefaultButton(_QMB.StandardButton.No)
        msg.setStyleSheet("""
            QMessageBox { background: #0D0D0D; color: #E8E8E8; }
            QLabel { color: #E8E8E8; font-size: 13px; }
            QPushButton { background: #1E1E1E; color: #E8E8E8; border: 1px solid #333;
                          border-radius: 6px; padding: 6px 20px; font-weight: 600; }
            QPushButton:hover { background: #333; }
            QPushButton:default { background: #FACC15; color: #000; border: none; }
        """)
        if msg.exec() == _QMB.StandardButton.Yes:
            self._quit_app()
        else:
            event.ignore()

    # ── 이벤트 검색 (비동기) ──

    def _start_event_search(self, payload):
        """이벤트 검색을 비동기 워커로 실행 (진행도 포함)"""
        loader = getattr(self.event_gen_tab, 'event_loader', None) if hasattr(self, 'event_gen_tab') else None

        if loader is None:
            # 데이터 자동 로드 후 검색
            self._pending_event_payload = payload
            self._auto_load_event_data(payload.get('ratings', ['g']))
            return

        self._run_event_search_worker(loader, payload)

    def _auto_load_event_data(self, ratings):
        """이벤트 데이터 자동 로드 (Vue 진행도 표시)"""
        from tabs.event_gen_tab import EventDataLoadWorker
        from config import EVENT_PARQUET_DIR

        self.vue_bridge.searchStatus.emit('데이터 로딩 중...')

        self._event_load_worker = EventDataLoadWorker(EVENT_PARQUET_DIR, ratings)
        self._event_load_worker.progress.connect(
            lambda msg: self.vue_bridge.searchStatus.emit(msg))
        self._event_load_worker.finished.connect(self._on_event_data_loaded)
        self._event_load_worker.start()

    def _on_event_data_loaded(self, result):
        """데이터 로드 완료 → 검색 시작"""
        if isinstance(result, str):
            self.vue_bridge.eventSearchResults.emit(json.dumps({'error': result}))
            return

        if hasattr(self, 'event_gen_tab'):
            self.event_gen_tab.event_loader = result

        payload = getattr(self, '_pending_event_payload', {})
        if payload:
            self._run_event_search_worker(result, payload)
            self._pending_event_payload = {}

    def _export_event_results(self, payload):
        """이벤트 검색 결과를 .parquet로 내보내기"""
        events = payload.get('events', [])
        if not events:
            self.vue_bridge.showNotification.emit('error', '내보낼 이벤트가 없습니다')
            return
        path, _ = QFileDialog.getSaveFileName(self, "이벤트 내보내기", "event_results.parquet", "Parquet (*.parquet);;JSON (*.json)")
        if not path:
            return
        try:
            import pandas as pd
            if path.endswith('.parquet'):
                df = pd.DataFrame(events)
                # steps 컬럼은 JSON 문자열로 저장
                if 'steps' in df.columns:
                    df['steps'] = df['steps'].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, list) else x)
                df.to_parquet(path, index=False)
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(events, f, ensure_ascii=False, indent=2)
            self.vue_bridge.showNotification.emit('success', f'이벤트 {len(events)}건 내보내기 완료')
        except Exception as e:
            self.vue_bridge.showNotification.emit('error', f'내보내기 실패: {e}')

    def _import_event_results(self):
        """이벤트 결과 .parquet/.json 불러오기"""
        path, _ = QFileDialog.getOpenFileName(self, "이벤트 불러오기", "", "Parquet/JSON (*.parquet *.json)")
        if not path:
            return
        try:
            import pandas as pd
            if path.endswith('.parquet'):
                df = pd.read_parquet(path)
                events = df.to_dict('records')
                # steps 컬럼 JSON 파싱
                for ev in events:
                    if 'steps' in ev and isinstance(ev['steps'], str):
                        try:
                            ev['steps'] = json.loads(ev['steps'])
                        except Exception:
                            pass
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    events = json.load(f)
            self.vue_bridge.eventImportResults.emit(json.dumps(events, ensure_ascii=False))
        except Exception as e:
            self.vue_bridge.showNotification.emit('error', f'불러오기 실패: {e}')

    def _run_event_search_worker(self, loader, payload):
        """검색 워커 실행"""
        from workers.event_search_worker import EventSearchWorker
        self._event_search_worker = EventSearchWorker(loader, payload, self)
        self._event_search_worker.progress.connect(
            lambda cur, total: self.vue_bridge.eventSearchProgress.emit(cur, total))
        self._event_search_worker.finished.connect(
            lambda r: self.vue_bridge.eventSearchResults.emit(r))
        self._event_search_worker.start()
        self.show_status("이벤트 검색 시작...")

    # ── ADetailer 단독 실행 ──

    def _run_adetailer_single(self, payload):
        """단일 이미지에 ADetailer 적용"""
        from workers.adetailer_worker import ADetailerSingleWorker
        path = payload.get('path', '')
        settings = payload.get('settings', {})
        if not path:
            self.vue_bridge.showNotification.emit('error', '이미지 경로가 없습니다')
            return
        self._ad_worker = ADetailerSingleWorker(path, settings, self)
        self._ad_worker.finished.connect(lambda r: self.vue_bridge.adetailerResult.emit(r))
        self._ad_worker.start()
        self.vue_bridge.showNotification.emit('info', 'ADetailer 처리 중...')

    def _run_adetailer_batch(self, payload):
        """배치 이미지에 ADetailer 적용"""
        from workers.adetailer_worker import ADetailerBatchWorker
        paths = payload.get('paths', [])
        settings = payload.get('settings', {})
        if not paths:
            self.vue_bridge.showNotification.emit('error', '이미지가 없습니다')
            return
        self._ad_batch_worker = ADetailerBatchWorker(paths, settings, self)
        self._ad_batch_worker.progress.connect(
            lambda cur, tot: self.vue_bridge.adetailerProgress.emit(cur, tot))
        self._ad_batch_worker.single_done.connect(
            lambda r: self.vue_bridge.adetailerResult.emit(r))
        self._ad_batch_worker.all_done.connect(
            lambda: self.vue_bridge.showNotification.emit('success', f'ADetailer 배치 완료 ({len(paths)}장)'))
        self._ad_batch_worker.start()
        self.vue_bridge.showNotification.emit('info', f'ADetailer 배치 시작 ({len(paths)}장)')

    def _run_sam3_single(self, payload):
        """단일 이미지에 SAM3 적용"""
        from workers.sam3_worker import Sam3SingleWorker
        path = payload.get('path', '')
        settings = payload.get('settings', {})
        if not path:
            self.vue_bridge.showNotification.emit('error', '이미지 경로가 없습니다')
            return
        self._sam3_worker = Sam3SingleWorker(path, settings, self)
        self._sam3_worker.finished.connect(lambda r: self.vue_bridge.sam3Result.emit(r))
        self._sam3_worker.start()
        self.vue_bridge.showNotification.emit('info', 'SAM3 처리 중...')

    def _run_sam3_batch(self, payload):
        """배치 이미지에 SAM3 적용"""
        from workers.sam3_worker import Sam3BatchWorker
        paths = payload.get('paths', [])
        settings = payload.get('settings', {})
        if not paths:
            self.vue_bridge.showNotification.emit('error', '이미지가 없습니다')
            return
        self._sam3_batch_worker = Sam3BatchWorker(paths, settings, self)
        self._sam3_batch_worker.progress.connect(
            lambda cur, tot: self.vue_bridge.sam3Progress.emit(cur, tot))
        self._sam3_batch_worker.single_done.connect(
            lambda r: self.vue_bridge.sam3Result.emit(r))
        self._sam3_batch_worker.all_done.connect(
            lambda: self.vue_bridge.showNotification.emit('success', f'SAM3 배치 완료 ({len(paths)}장)'))
        self._sam3_batch_worker.start()
        self.vue_bridge.showNotification.emit('info', f'SAM3 배치 시작 ({len(paths)}장)')

    # ── DEFAULTS 탭 (Vue) → 위젯 적용 ──────────────────────
    def _apply_tab_defaults_to_empty_widgets(self, defaults: dict, first_run: bool = False) -> None:
        """tab_defaults.json의 값을 적절한 위젯에 적용.

        :param first_run: True면 모든 필드 적용 (덮어쓰기 포함).
                          False면 위젯이 비어있거나 "기본 placeholder"일 때만.
        """
        # (widget_id, defaults_key, type_converter) 매핑
        FIELD_MAP = [
            ("steps_input", "steps", str),
            ("cfg_input", "cfg", str),
            ("width_input", "width", str),
            ("height_input", "height", str),
            ("seed_input", "seed", str),
            ("sampler_combo", "sampler", str),
            ("scheduler_combo", "scheduler", str),
        ]
        for widget_id, key, conv in FIELD_MAP:
            if key not in defaults:
                continue
            widget = getattr(self, widget_id, None)
            if widget is None:
                continue
            new_val = conv(defaults[key])
            if not new_val or new_val == "":
                continue
            try:
                if first_run:
                    if hasattr(widget, "setText"):
                        widget.setText(new_val)
                    elif hasattr(widget, "setCurrentText"):
                        widget.setCurrentText(new_val)
                else:
                    # 위젯이 비었거나 placeholder 같으면 채움
                    current = ""
                    if hasattr(widget, "currentText"):
                        current = widget.currentText() or ""
                    elif hasattr(widget, "text"):
                        current = widget.text() or ""
                    if not current.strip():
                        if hasattr(widget, "setText"):
                            widget.setText(new_val)
                        elif hasattr(widget, "setCurrentText"):
                            widget.setCurrentText(new_val)
            except Exception as e:
                print(f"[Warning] DEFAULTS {key} 적용 실패: {e}")

    # ── LOGIC 탭 (Vue) → prompt_cleaner 연결 ──────────────
    def _apply_ui_prefs_to_cleaner(self, prefs: dict) -> None:
        """Vue Settings → LOGIC 토글 값을 prompt_cleaner에 반영.

        Vue 키 → cleaner 속성:
        - cleanDuplicates → remove_duplicates
        - cleanSpaces     → auto_space
        - cleanUnderscore → underscore_to_space

        호출 시점:
        - 앱 시작 시 (저장된 ui_prefs.json 적용)
        - save_ui_prefs 액션 받을 때마다 (변경 즉시 반영)
        """
        cleaner = getattr(self, "prompt_cleaner", None)
        if cleaner is None:
            return
        try:
            if "cleanDuplicates" in prefs:
                cleaner.remove_duplicates = bool(prefs["cleanDuplicates"])
            if "cleanSpaces" in prefs:
                cleaner.auto_space = bool(prefs["cleanSpaces"])
            if "cleanUnderscore" in prefs:
                cleaner.underscore_to_space = bool(prefs["cleanUnderscore"])
        except Exception as e:
            print(f"[Warning] LOGIC 토글 적용 실패: {e}")

    # ── 워크플로우 프로파일 ────────────────────────────────
    def _send_workflow_profiles_list(self):
        """현재 프로파일 목록을 Vue로 전송."""
        import json as _json
        try:
            from core.workflow_profiles import list_profiles
            self.vue_bridge.workflowProfilesList.emit(
                _json.dumps(list_profiles())
            )
        except Exception:
            pass

    # ── 프롬프트 섹션 순서 (사용자 지정) ──────────────────
    def _send_prompt_order(self):
        """현재 prompt_order.json 내용 + 라벨을 Vue로 전송."""
        import json as _json
        try:
            from core.prompt_order import order_with_labels
            self.vue_bridge.promptOrderLoaded.emit(
                _json.dumps(order_with_labels())
            )
        except Exception:
            pass

    # ── PR 2: Queue v2 이벤트 브리지 ───────────────────────
    def _setup_queue_v2_bridge(self) -> None:
        """기존 queue_panel과 GenerationQueueV2 사이의 이벤트 브리지.

        설계:
        - V2를 실제 작업 처리에 쓰지 않음 (기존 queue_panel + workers가 담당)
        - V2는 AppContext "queue_v2" 서비스로 노출 — 다른 모듈이 queue 상태를
          구조화된 형태로 조회 / 이벤트 구독 가능
        - queue_panel.queue_changed 시그널 → V2를 미러링 + AppContext 이벤트 발행
        """
        try:
            from core.generation_queue_v2 import GenerationQueueV2, QueueEvents
            from core.app_context import get_context

            # V2 인스턴스 — processor는 사용 안 함 (no-op), 워커도 시작 안 함
            qv2 = GenerationQueueV2(
                processor=lambda payload: None,
                publish_events=True,
            )
            get_context().register_service("queue_v2", qv2)
            self._queue_v2 = qv2

            qp = getattr(self, "queue_panel", None)
            if qp is None or not hasattr(qp, "queue_changed"):
                return

            def _sync_to_v2(count: int) -> None:
                """queue_panel 상태를 V2에 미러링 + 이벤트 발행."""
                try:
                    # V2 비우기
                    qv2.clear_pending()
                    # queue_panel 아이템을 우선순위 순으로 enqueue (인덱스가 priority)
                    items = getattr(qp, "queue_items", []) or []
                    for idx, item in enumerate(items):
                        qv2.enqueue(
                            payload=dict(item),
                            priority=idx,
                            label=item.get("id", f"item-{idx}"),
                        )
                except Exception:
                    pass

            qp.queue_changed.connect(_sync_to_v2)
            # 초기 1회 동기화
            _sync_to_v2(len(getattr(qp, "queue_items", []) or []))
        except Exception as e:
            print(f"[Warning] queue v2 bridge setup 실패: {e}")

    # ── PR 8: Instant Wildcards ────────────────────────────
    def _get_instant_wildcards(self):
        """싱글톤 InstantWildcards 인스턴스 — 게으른 초기화 + PromptPipeline 훅 등록."""
        if not hasattr(self, '_instant_wildcards'):
            from pathlib import Path
            from core.instant_wildcards import InstantWildcards
            store = Path(__file__).resolve().parent.parent / "save" / "instant_wildcards.json"
            self._instant_wildcards = InstantWildcards(store_path=store)
            # PromptPipeline에 자동 등록 — 와일드카드 확장 단계에 추가
            try:
                from core.prompt_pipeline import get_pipeline, HookPoint
                get_pipeline().register(
                    HookPoint.POST_PROCESSING,
                    self._instant_wildcards.make_hook(),
                    priority=80,
                    name="instant_wildcards",
                )
            except Exception:
                pass
        return self._instant_wildcards

    def _send_instant_wildcards_list(self):
        """현재 인스턴트 와일드카드 목록을 Vue로 푸시."""
        import json as _json
        iw = self._get_instant_wildcards()
        items = [{"name": n, "lines": iw.get(n)} for n in iw.names()]
        try:
            self.vue_bridge.instantWildcardsList.emit(_json.dumps(items))
        except Exception:
            pass

    def _register_ui_state_handlers(self) -> None:
        """UIStateManager에 메인 윈도우 기하/상태 등록.

        다른 모듈(스플리터 등)이 자기 상태를 더 등록할 수 있음 — register는 멱등.
        """
        def _get_main_geometry() -> dict:
            return {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
                "maximized": self.isMaximized(),
                "full_screen": self.isFullScreen(),
            }

        def _set_main_geometry(state: dict) -> None:
            """저장된 윈도우 기하 복원 — 타이틀바가 가려지지 않도록 보정."""
            if not isinstance(state, dict):
                return
            try:
                from PyQt6.QtGui import QGuiApplication

                # 1) 최대화/풀스크린 상태면 setGeometry 건너뛰기
                #    main.py가 이미 showMaximized 호출했으므로 중복 호출하면 깜빡임
                if state.get("maximized"):
                    if not self.isMaximized():
                        self.showMaximized()
                    return
                if state.get("full_screen"):
                    if not self.isFullScreen():
                        self.showFullScreen()
                    return

                # 2) 일반 윈도우 — 현재 최대화돼있으면 먼저 normal로 풀기
                if self.isMaximized() or self.isFullScreen():
                    self.showNormal()

                # 3) 기하 + 화면 영역 보정 (타이틀바 가림 방지)
                w = max(int(state.get("width", 1280)), 600)
                h = max(int(state.get("height", 720)), 400)
                x = int(state.get("x", 100))
                y = int(state.get("y", 100))

                # 어느 모니터인지 — 중심점 기준
                target_screen = QGuiApplication.primaryScreen()
                for sc in QGuiApplication.screens():
                    if sc.geometry().contains(x + w // 2, y + h // 2):
                        target_screen = sc
                        break

                avail = target_screen.availableGeometry()
                # x: 좌측 이상, 우측에서 폭 빼고 이하
                # y: 상단 이상 — ★ 타이틀바 보임 보장
                x = max(avail.left(), min(x, avail.right() - w))
                y = max(avail.top(), min(y, avail.bottom() - h))

                self.setGeometry(x, y, w, h)
            except Exception as e:
                print(f"[Warning] UI 상태 복원 실패: {e}")

        self.ui_state.register("main_window", _get_main_geometry, _set_main_geometry)

    def _quit_app(self):
        try:
            self.save_settings()
        except Exception as e:
            print(f"[Warning] 종료 시 설정 저장 실패: {e}")
        try:
            # UI 상태 (창 크기/위치/스플리터 등) 저장
            if hasattr(self, "ui_state"):
                self.ui_state.save_all()
        except Exception as e:
            print(f"[Warning] UI 상태 저장 실패: {e}")
        os._exit(0)

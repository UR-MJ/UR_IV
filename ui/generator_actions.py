# ui/generator_actions.py
"""
UI 액션 및 이벤트 처리 로직
"""
import os
from PyQt6.QtWidgets import QListWidgetItem, QMessageBox
from PyQt6.QtCore import Qt

from config import OUTPUT_DIR
from utils.theme_manager import get_color
from utils.app_logger import get_logger
from ui.generator_generation import _gen_btn_style, _gen_btn_default_color

_logger = get_logger('actions')

class ActionsMixin:
    """UI 액션 관련 로직을 담당하는 Mixin"""
    
    def connect_signals(self):
        """시그널 연결"""
        # 생성 버튼
        self.btn_generate.clicked.connect(self.on_generate_clicked)
        self.btn_random_prompt.clicked.connect(self.apply_random_prompt)
        self.btn_save_settings.clicked.connect(self.save_settings)
        
        # 텍스트 변경 시 업데이트
        text_inputs = [
            self.char_count_input, self.character_input, 
            self.copyright_input, self.artist_input
        ]
        for inp in text_inputs:
            inp.textChanged.connect(self.on_input_changed)
        
        text_edits = [
            self.prefix_prompt_text, self.main_prompt_text, 
            self.suffix_prompt_text
        ]
        for edit in text_edits:
            edit.textChanged.connect(self.on_input_changed)
        
        # 베이스 프롬프트 변경 감지
        self.prefix_prompt_text.textChanged.connect(self.on_base_prompts_changed)
        self.suffix_prompt_text.textChanged.connect(self.on_base_prompts_changed)
        self.neg_prompt_text.textChanged.connect(self.on_base_prompts_changed)
        
        # 포커스 아웃 시 정리 (eventFilter로 처리, 디바운스 타이머의 보완)
        text_edits_to_clean = [
            self.prefix_prompt_text,
            self.main_prompt_text,
            self.suffix_prompt_text,
            self.neg_prompt_text,
            self.exclude_prompt_local_input,
            self.s1_widgets['prompt'],
            self.s2_widgets['prompt'],
        ]
        for widget in text_edits_to_clean:
            widget.installEventFilter(self)

        # 토글 버튼
        self.prefix_toggle_button.toggled.connect(
            lambda checked: self.prefix_prompt_text.setVisible(checked)
        )
        self.suffix_toggle_button.toggled.connect(
            lambda checked: self.suffix_prompt_text.setVisible(checked)
        )
        self.neg_toggle_button.toggled.connect(
            lambda checked: self.neg_prompt_text.setVisible(checked)
        )
        
        # ADetailer 토글
        self.ad_toggle_button.toggled.connect(
            lambda checked: self.ad_settings_container.setVisible(checked)
        )
        if hasattr(self, 'sam3_toggle_button'):
            self.sam3_toggle_button.toggled.connect(
                lambda checked: self.sam3_settings_container.setVisible(checked)
            )
        
        # ADetailer 슬롯 체크박스
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['use_inpaint_size_check'].toggled.connect(
                lambda checked, w=slot_widgets: 
                    w['inpaint_size_container'].setVisible(checked)
            )
            slot_widgets['use_steps_check'].toggled.connect(
                lambda checked, w=slot_widgets: 
                    w['steps'].setVisible(checked)
            )
            slot_widgets['use_cfg_check'].toggled.connect(
                lambda checked, w=slot_widgets: 
                    w['cfg'].setVisible(checked)
            )
            slot_widgets['use_checkpoint_check'].toggled.connect(
                lambda checked, w=slot_widgets: 
                    w['checkpoint_combo'].setVisible(checked)
            )
            slot_widgets['use_vae_check'].toggled.connect(
                lambda checked, w=slot_widgets: 
                    w['vae_combo'].setVisible(checked)
            )
            slot_widgets['use_sampler_check'].toggled.connect(
                lambda checked, w=slot_widgets: 
                    w['sampler_container'].setVisible(checked)
            )
        if hasattr(self, 'sam3_widgets'):
            self.sam3_widgets['use_inpaint_size_check'].toggled.connect(
                lambda checked: self.sam3_widgets['inpaint_size_container'].setVisible(checked)
            )
            self.sam3_widgets['use_steps_check'].toggled.connect(
                lambda checked: self.sam3_widgets['steps'].setVisible(checked)
            )
            self.sam3_widgets['use_cfg_check'].toggled.connect(
                lambda checked: self.sam3_widgets['cfg'].setVisible(checked)
            )
            self.sam3_widgets['use_sampler_check'].toggled.connect(
                lambda checked: self.sam3_widgets['sampler_container'].setVisible(checked)
            )
            self.sam3_widgets['use_noise_multiplier_check'].toggled.connect(
                lambda checked: self.sam3_widgets['noise_multiplier'].setVisible(checked)
            )
        
        # 랜덤 해상도
        self.random_res_check.toggled.connect(self.toggle_random_resolution_editor)
        self.btn_add_res.clicked.connect(self.add_resolution_item)
        
        # 즐겨찾기
        self.btn_add_favorite.clicked.connect(self.add_to_favorites)
        if hasattr(self, 'btn_fav_refresh'):
            self.btn_fav_refresh.clicked.connect(self.refresh_favorites)
        if hasattr(self, 'btn_fav_clear'):
            self.btn_fav_clear.clicked.connect(self.clear_all_favorites)        
        
        # 이벤트 탭 시그널 연결
        if hasattr(self, 'event_gen_tab'):
            if hasattr(self.event_gen_tab, 'btn_load_base'):
                self.event_gen_tab.btn_load_base.clicked.connect(
                    self.load_base_prompt_to_event
                )
            if hasattr(self.event_gen_tab, 'send_to_queue_signal'):
                self.event_gen_tab.send_to_queue_signal.connect(
                    self.receive_event_scenarios
                )
        
        # PNG Info 시그널 연결
        if hasattr(self, 'png_info_tab'):
            self.png_info_tab.generate_signal.connect(
                lambda payload: self.handle_immediate_generation(payload)
            )
            self.png_info_tab.send_prompt_signal.connect(
                lambda p, n: self.handle_prompt_only_transfer(p, n)
            )
            # I2I/Inpaint 전송 시그널
            if hasattr(self.png_info_tab, 'send_to_i2i_signal') and hasattr(self, 'i2i_tab'):
                self.png_info_tab.send_to_i2i_signal.connect(
                    lambda payload: self._handle_send_to_i2i(payload)
                )
            if hasattr(self.png_info_tab, 'send_to_inpaint_signal') and hasattr(self, 'inpaint_tab'):
                self.png_info_tab.send_to_inpaint_signal.connect(
                    lambda payload: self._handle_send_to_inpaint(payload)
                )
            if hasattr(self.png_info_tab, 'send_to_queue_signal'):
                self.png_info_tab.send_to_queue_signal.connect(self._gallery_send_to_queue)

        # Gallery 시그널 연결
        if hasattr(self, 'gallery_tab'):
            self.gallery_tab.send_prompt_signal.connect(
                lambda p, n: self.handle_prompt_only_transfer(p, n)
            )
            self.gallery_tab.generate_signal.connect(
                lambda payload: self.handle_immediate_generation(payload)
            )
            self.gallery_tab.open_in_editor.connect(self._gallery_send_to_editor)
            self.gallery_tab.send_to_i2i.connect(self._gallery_send_to_i2i)
            self.gallery_tab.send_to_inpaint.connect(self._gallery_send_to_inpaint)
            self.gallery_tab.send_to_upscale.connect(self._gallery_send_to_upscale)
            self.gallery_tab.send_to_queue_signal.connect(self._gallery_send_to_queue)
            if hasattr(self.gallery_tab, 'send_to_compare'):
                self.gallery_tab.send_to_compare.connect(self._gallery_send_to_compare)

        if hasattr(self, 'xyz_plot_tab'):
            self.xyz_plot_tab.add_to_queue_requested.connect(self._on_xyz_add_to_queue)
            self.xyz_plot_tab.start_generation_requested.connect(self._on_xyz_start_generation)

        # T2I 뷰어 우클릭 메뉴
        self.setup_viewer_context_menu()
    
    def on_generate_clicked(self):
        """생성 버튼 클릭 (일반 생성 또는 자동화 시작/중지)"""
        # 자동화 모드가 켜져 있으면
        if self.btn_auto_toggle.isChecked():
            if self.is_automating:
                # 자동화 중지
                self._stop_automation("사용자가 자동화를 중지했습니다.")
            else:
                # 자동화 시작
                self._start_automation()
        else:
            # 일반 이미지 생성
            self.start_generation()
    
    def on_input_changed(self):
        """입력 변경 시 최종 프롬프트 업데이트"""
        if not self.is_programmatic_change:
            self.update_total_prompt_display()
    
    def toggle_automation_ui(self, checked):
        """자동화 모드 토글 (ON/OFF만 — 패널 표시는 별도 접이식)"""
        # 생성 중이면 토글 무시
        if hasattr(self, 'gen_worker') and self.gen_worker and self.gen_worker.isRunning():
            self.btn_auto_toggle.setChecked(not checked)
            QMessageBox.warning(self, "알림", "이미지 생성 중에는 자동화 모드를 변경할 수 없습니다.")
            return

        if checked:
            self.btn_auto_toggle.setText("AUTOMATION: ON")
            self.btn_auto_toggle.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color('success')}; color: black;
                    border: none; border-radius: 5px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {get_color('success')}; }}
            """)
            self.btn_generate.setText("자동화 시작")
        else:
            if self.is_automating:
                self._stop_automation("자동화가 중지되었습니다.")
            self.btn_auto_toggle.setText("AUTOMATION: OFF")
            self.btn_auto_toggle.setStyleSheet("")  # 테마 기본 스타일 복원
            self.btn_generate.setText("이미지 생성")
            
    def toggle_random_resolution_editor(self, checked):
        """랜덤 해상도 편집기 토글"""
        if checked:
            self.resolution_editor_container.show()
            self._update_resolution_list()
            self._update_random_res_label()
        else:
            self.resolution_editor_container.hide()
            self.random_res_label.clear()
    
    def add_resolution_item(self):
        """해상도 추가 (이름 자동 생성: WxH)"""
        try:
            width = int(self.res_width_input.text())
            height = int(self.res_height_input.text())

            desc = f"{width}x{height}"
            self.random_resolutions.append((width, height, desc))
            self._update_resolution_list()

            self.res_width_input.clear()
            self.res_height_input.clear()

        except ValueError:
            QMessageBox.warning(self, "오류", "올바른 숫자를 입력해주세요.")
    
    def _update_resolution_list(self):
        """해상도 리스트 업데이트 (Vue SPA에서는 프록시이므로 스킵)"""
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        # LWProxy인 경우 (Vue 모드) — PyQt UI 업데이트 불필요
        if not isinstance(self.resolution_list_widget, QListWidget):
            return
        self.resolution_list_widget.clear()
        for i, (w, h, desc) in enumerate(self.random_resolutions):
            from widgets.common_widgets import ResolutionItemWidget
            item_widget = ResolutionItemWidget(w, h, desc, i)
            item_widget.delete_requested.connect(self.delete_resolution_item)
            item = QListWidgetItem(self.resolution_list_widget)
            item.setSizeHint(item_widget.sizeHint())
            self.resolution_list_widget.addItem(item)
            self.resolution_list_widget.setItemWidget(item, item_widget)
    
    def delete_resolution_item(self, index):
        """해상도 삭제"""
        if 0 <= index < len(self.random_resolutions):
            del self.random_resolutions[index]
            self._update_resolution_list()
    
    def _update_random_res_label(self):
        """랜덤 해상도 라벨 업데이트"""
        if self.random_resolutions:
            res_list = ", ".join([
                f"{desc}({w}x{h})" 
                for w, h, desc in self.random_resolutions
            ])
            self.random_res_label.setText(f"등록된 해상도: {res_list}")
        else:
            self.random_res_label.setText("등록된 해상도가 없습니다.")
    
    def _apply_next_automation_prompt(self) -> bool:
        """자동화용 다음 프롬프트 적용 (apply_random_prompt와 동일한 로직 사용)"""
        import random
        
        settings = self.auto_settings
        
        # 덱이 비었으면 리필
        if not self.shuffled_prompt_deck:
            if settings.get('allow_duplicates', False) or settings.get('auto_reset_deck', False):
                # 중복 허용 / 덱 소진 시 자동 초기화: 덱 리필
                self.shuffled_prompt_deck = self.filtered_results.copy()
                random.shuffle(self.shuffled_prompt_deck)
                self.show_status("🔄 덱을 다시 섞었습니다.")
                self._save_deck_state()
            else:
                # 중복 불허: 종료
                return False

        # 덱에서 프롬프트 가져오기
        if settings.get('allow_duplicates', False):
            # 중복 허용: 랜덤 선택 (덱에서 제거 안 함)
            bundle = random.choice(self.shuffled_prompt_deck)
        else:
            # 중복 불허: 덱에서 제거
            bundle = self.shuffled_prompt_deck.pop()
            remaining = len(self.shuffled_prompt_deck)
            self.btn_random_prompt.setText(f"🎲 랜덤 프롬프트 ({remaining})")
            self._save_deck_state()  # 진행도 저장 (재시작 시 복원)
        
        # ★★★ 핵심: apply_prompt_from_data 호출 ★★★
        # 이게 UI 업데이트 + 토글 적용 + 필터링 전부 처리함
        self.apply_prompt_from_data(bundle)

        return True

    # ── 덱 진행도 영속 (재시작 시 '얼마나 뽑았는지' 복원) ────────────────
    def _deck_state_path(self):
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, 'config', 'last_deck.json')

    def _save_deck_state(self):
        """남은 덱을 filtered_results 인덱스 리스트로 저장.
        풀(filtered_results)은 last_search_results.json으로 따로 복원되므로,
        덱은 인덱스만 저장하면 충분(대용량에도 컴팩트). 소비/리필 때마다 호출."""
        try:
            import os, json
            fr = getattr(self, 'filtered_results', None) or []
            deck = getattr(self, 'shuffled_prompt_deck', None)
            if not fr or deck is None:
                return
            # id→index 맵 캐시 (filtered_results 객체가 교체되면 재생성)
            if getattr(self, '_deck_idmap_for', None) is not id(fr):
                self._deck_idmap = {id(b): i for i, b in enumerate(fr)}
                self._deck_idmap_for = id(fr)
            idmap = self._deck_idmap
            idx = [idmap[id(b)] for b in deck if id(b) in idmap]
            path = self._deck_state_path()
            from utils.atomic_json import atomic_write_json
            atomic_write_json(path, {'pool_size': len(fr), 'remaining': idx}, indent=None)
        except Exception as e:
            print(f"[Deck] save 실패: {e}")

    def _restore_deck_state(self) -> bool:
        """저장된 인덱스로 남은 덱을 재구성. 성공 시 True(호출자는 새 셔플 생략).
        풀 크기가 다르면(새 검색 등) False → 호출자가 새로 셔플."""
        try:
            import os, json
            fr = getattr(self, 'filtered_results', None) or []
            if not fr:
                return False
            path = self._deck_state_path()
            if not os.path.exists(path):
                return False
            with open(path, encoding='utf-8') as f:
                st = json.load(f)
            if st.get('pool_size') != len(fr):
                return False  # 풀이 바뀜 → 복원 불가
            n = len(fr)
            self.shuffled_prompt_deck = [fr[i] for i in st.get('remaining', [])
                                         if isinstance(i, int) and 0 <= i < n]
            print(f"[Deck] 복원: 남은 {len(self.shuffled_prompt_deck):,} / 전체 {n:,}")
            return True
        except Exception as e:
            print(f"[Deck] restore 실패: {e}")
            return False

    def _start_automation(self):
        """자동화 시작"""
        if not self.filtered_results:
            QMessageBox.warning(self, "알림", "먼저 검색을 수행하세요.")
            return
        
        import time
        import random
        
        self.is_automating = True
        self.auto_gen_count = 0
        self.auto_current_repeat = 1

        settings = self.automation_widget.get_settings()
        self.auto_settings = settings
        self._emit_auto_status()
        
        # 시간 제한 모드면 시작 시간 기록
        if settings['termination_mode'] == 'timer':
            self.auto_start_time = time.time()
        
        # 덱 초기화 — 이미 남은 덱이 있으면(부분 소비 포함) 유지하여 진행도 보존.
        # 비었을 때만(검색 직후/소진 후) 새로 셔플 → 자동화 멈췄다 재시작해도 이어서 진행.
        if not self.shuffled_prompt_deck:
            self.shuffled_prompt_deck = self.filtered_results.copy()
            random.shuffle(self.shuffled_prompt_deck)
            self._save_deck_state()
        self.btn_random_prompt.setText(f"🎲 랜덤 프롬프트 ({len(self.shuffled_prompt_deck)})")
        
        # 버튼 상태 변경
        self.btn_generate.setText("⏸️ 자동화 중지")
        self.btn_generate.setStyleSheet(_gen_btn_style('#e74c3c'))
        
        self.show_status("🔄 자동화 시작...")

        # PR 3: 시작 이벤트 발행
        try:
            from core.app_context import get_context
            from core.automation_controller import AutomationEvents
            get_context().publish(AutomationEvents.STARTED, {
                'mode': settings.get('termination_mode', 'count'),
                'limit': settings.get('termination_limit', 0),
                'delay': settings.get('delay', 1.0),
                'max_retries': settings.get('max_retries', 0),
            })
        except Exception:
            pass

        # ★★★ 첫 번째 프롬프트 적용 (apply_random_prompt 사용!) ★★★
        self.apply_random_prompt()

        # 첫 생성 시작
        from PyQt6.QtCore import QTimer
        delay_ms = int(settings['delay'] * 1000)
        QTimer.singleShot(delay_ms, self.start_generation)


    def _run_automation_cycle(self):
        """자동화 사이클"""
        if not self.is_automating:
            return

        import time
        from PyQt6.QtCore import QTimer

        settings = self.auto_settings

        # 종료 조건 확인 (PR 3: 'unlimited' 모드 추가 — 종료 조건 없음)
        mode = settings.get('termination_mode', 'count')
        if mode == 'unlimited':
            pass  # 사용자가 중지할 때까지 계속
        elif mode == 'count':
            if self.auto_gen_count >= settings['termination_limit']:
                self._stop_automation(f"✅ 자동화 완료: {self.auto_gen_count}장 생성")
                return
        else:  # timer
            elapsed = time.time() - self.auto_start_time
            if elapsed >= settings['termination_limit']:
                self._stop_automation(f"✅ 시간 종료: {self.auto_gen_count}장 생성")
                return
        
        # 반복 횟수 확인
        if self.auto_current_repeat >= settings['repeat_per_prompt']:
            self.auto_current_repeat = 0
            
            # ★★★ 새 프롬프트 적용 (apply_random_prompt 사용!) ★★★
            # 덱이 비었는지 확인
            if not self.shuffled_prompt_deck and not settings.get('allow_duplicates', False):
                if settings.get('auto_reset_deck', False):
                    # 한 바퀴 완료 → 덱 자동 초기화(재셔플)하고 계속 (무한·공평: 모두 1회씩 후 다시)
                    import random as _rnd
                    rf = getattr(self, '_rating_filter', {'g', 's', 'q', 'e'})
                    self.shuffled_prompt_deck = [r for r in (self.filtered_results or []) if r.get('rating', 'g') in rf]
                    _rnd.shuffle(self.shuffled_prompt_deck)
                    self.show_status(f"🔄 덱 소진 → 자동 초기화 ({len(self.shuffled_prompt_deck)})")
                    if hasattr(self, '_save_deck_state'):
                        self._save_deck_state()
                else:
                    self._stop_automation("✅ 모든 프롬프트 처리 완료!")
                    return
            
            self.apply_random_prompt()
        
        # 대기 후 생성 — 대기 동안 카운트다운 타이머로 남은 시간 표시 (Search % 느낌)
        import time
        delay_ms = int(settings['delay'] * 1000)
        if delay_ms > 0:
            self._wait_total_ms = delay_ms
            self._wait_end_time = time.time() + (delay_ms / 1000.0)
            self._ensure_wait_timer()
            self._wait_timer.start(100)  # 100ms마다 남은 시간 갱신
            self._emit_auto_status(waiting=True)
        else:
            self._wait_total_ms = 0
            self._wait_end_time = 0
            self._emit_auto_status(waiting=False)
            QTimer.singleShot(0, self._automation_generate)


    def _automation_generate(self):
        """자동화 이미지 생성"""
        if not self.is_automating:
            return

        # 대기 타이머 정지 (생성 들어가면 카운트다운 종료)
        if getattr(self, '_wait_timer', None):
            self._wait_timer.stop()
        self._wait_end_time = 0

        self.auto_current_repeat += 1

        # 생성 시 태그→자연어 자동 변환 (비동기 worker — UI 안 멈춤).
        # 이미 변환된 프롬프트(반복 생성 등)는 문자열 비교로 건너뜀 → 누적 방지.
        # 큐 우선 항목은 _automation_generate를 거치지 않으므로 자연스럽게 제외됨.
        if getattr(self, '_auto_nl_enabled', False) and not getattr(self, '_auto_processing_queue', False):
            cur = self.main_prompt_text.toPlainText().strip()
            if cur and cur != getattr(self, '_auto_nl_last_output', None):
                if self._start_auto_nl_then_generate(cur):
                    return   # worker 완료 콜백에서 start_generation 호출
        self.start_generation()

    def _start_auto_nl_then_generate(self, base_tags: str) -> bool:
        """태그→nl_caption 변환을 비동기로 시작. 성공 시 True(호출자는 start_generation 생략)."""
        try:
            from workers.ollama_worker import OllamaWorker
            url = getattr(self, '_auto_nl_url', '') or 'http://localhost:11434'
            model = getattr(self, '_auto_nl_model', '') or ''
            # 모델 검증 (미설치/별칭 문제 방지) — list_models는 빠른 로컬 호출
            try:
                from core.ollama_client import OllamaClient
                installed = OllamaClient(base_url=url).list_models()
                if installed:
                    def _b(s): return (s or '').split(':')[0].lower()
                    if not (model and any(m == model or _b(m) == _b(model) for m in installed)):
                        model = installed[0]
            except Exception:
                pass
            if not model:
                model = 'gemma3:4b'
            self._auto_nl_base = base_tags
            w = OllamaWorker(url, model, base_tags, 'nl_caption', '', self)
            w.finished.connect(self._on_auto_nl_done)
            w.error.connect(self._on_auto_nl_error)
            self._auto_nl_worker = w
            if hasattr(self, 'show_status'):
                self.show_status("🅣→🅝 자연어 변환 중…")
            w.start()
            return True
        except Exception as e:
            print(f"[AutoNL] 변환 시작 실패(태그로 생성): {e}")
            return False

    def _on_auto_nl_done(self, result: str):
        """변환 완료 → 태그 뒤에 자연어 추가 → 생성 (UI 스레드에서 실행됨)."""
        try:
            import json as _json
            d = _json.loads(result)
            nl = (d.get('tags') or '').strip()
            base = getattr(self, '_auto_nl_base', '') or ''
            if nl:
                combined = (base + ', ' + nl) if base else nl
                self._auto_nl_last_output = combined
                self.main_prompt_text.setPlainText(combined)
                if hasattr(self, 'update_total_prompt_display'):
                    self.update_total_prompt_display()
        except Exception as e:
            print(f"[AutoNL] 결과 처리 실패: {e}")
        if self.is_automating:
            self.start_generation()

    def _on_auto_nl_error(self, err: str):
        """변환 실패 → 원본 태그 그대로 생성."""
        print(f"[AutoNL] 변환 실패(태그로 생성): {err}")
        if self.is_automating:
            self.start_generation()

    def _ensure_wait_timer(self):
        """자동화 대기 카운트다운 타이머 보장 (100ms 간격)."""
        if getattr(self, '_wait_timer', None) is None:
            from PyQt6.QtCore import QTimer
            self._wait_timer = QTimer(self)
            self._wait_timer.setInterval(100)
            self._wait_timer.timeout.connect(self._on_wait_tick)

    def _on_wait_tick(self):
        """대기 중 남은 시간 갱신 → 0이 되면 생성 시작."""
        import time
        if not self.is_automating:
            if getattr(self, '_wait_timer', None):
                self._wait_timer.stop()
            return
        remaining = getattr(self, '_wait_end_time', 0) - time.time()
        if remaining <= 0:
            # _automation_generate가 타이머 정지 처리
            self._automation_generate()
            return
        self._emit_auto_status(waiting=True)


    def _continue_automation(self):
        """자동화 계속 (on_generation_finished에서 호출).

        큐 우선: 자동화 중 큐에 대기 항목이 있으면 자동화 덱보다 '먼저' 생성한다.
        - 큐 항목은 _automation_generate를 거치지 않으므로 반복 카운터(auto_current_repeat)
          가 보존됨 → 큐 처리 후 남은 반복을 그대로 이어감.
        - 큐 항목은 자동화 종료 횟수(auto_gen_count)에 미포함 (on_generation_finished가
          올린 +1을 여기서 되돌림).
        - 큐 항목이 UI 프롬프트를 바꾸므로, 큐가 비면 현재 자동화 프롬프트로 복원.
        """
        if not self.is_automating:
            return
        qp = getattr(self, 'queue_panel', None)

        # 1) 직전 생성이 '큐 우선' 항목이었으면 정리: 자동화 카운트 제외 + 큐에서 제거
        if getattr(self, '_auto_processing_queue', False):
            self._auto_processing_queue = False
            self.auto_gen_count = max(0, getattr(self, 'auto_gen_count', 0) - 1)
            if qp is not None:
                try:
                    qp.remove_first_item()
                except Exception:
                    pass

        # 2) 큐 우선 처리: 대기 항목이 있으면 다음 큐 항목 생성 (반복 상태 건드리지 않음)
        if qp is not None:
            try:
                item = qp.get_first_item()
            except Exception:
                item = None
            if item:
                self._auto_processing_queue = True
                self._queue_dirtied_prompt = True
                try:
                    qp.set_processing(True, item.get('id'))
                except Exception:
                    pass
                self.is_programmatic_change = True
                try:
                    self._apply_payload_to_ui(item)
                finally:
                    self.is_programmatic_change = False
                self.show_status("📋 큐 우선 처리 중...")
                self.start_generation()
                return

        # 3) 큐 비었음 → 자동화 덱 계속. 큐가 UI 프롬프트를 바꿨으면 현재 자동화 프롬프트 복원.
        if getattr(self, '_queue_dirtied_prompt', False):
            self._queue_dirtied_prompt = False
            b = getattr(self, '_current_auto_bundle', None)
            if b is not None:
                self.is_programmatic_change = True
                try:
                    self.apply_prompt_from_data(b)
                    self.update_total_prompt_display()
                finally:
                    self.is_programmatic_change = False

        self._run_automation_cycle()
            

    def _emit_auto_status(self, waiting=False):
        """Vue에 자동화 상태 전송 + AppContext 이벤트 발행."""
        if hasattr(self, 'vue_bridge'):
            import json
            # 덱 현황 — 남은/전체/사용. 중복 허용 모드는 덱을 소모 안 하므로
            # remaining==total로 유지됨(무한). UI에서 그 경우 구분 표시 가능.
            _deck = getattr(self, 'shuffled_prompt_deck', None) or []
            _pool = getattr(self, 'filtered_results', None) or []
            _remaining = len(_deck)
            _total = len(_pool)
            _used = max(0, _total - _remaining)
            # 대기 카운트다운 (다음 생성까지 남은 시간) — Search % 바 느낌
            import time as _t
            _wait_total = int(getattr(self, '_wait_total_ms', 0) or 0)
            _wait_remaining = 0
            if waiting:
                _wait_remaining = max(0, int((getattr(self, '_wait_end_time', 0) - _t.time()) * 1000))
            self.vue_bridge.automationStatus.emit(json.dumps({
                'running': self.is_automating,
                'count': getattr(self, 'auto_gen_count', 0),
                'waiting': waiting,
                'wait_remaining_ms': _wait_remaining,
                'wait_total_ms': _wait_total,
                'deck_remaining': _remaining,
                'deck_total': _total,
                'deck_used': _used,
                'allow_duplicates': bool(getattr(self, 'auto_settings', {}).get('allow_duplicates', False)),
            }))
        # PR 3: AppContext에도 발행 (다른 모듈이 구독 가능 — 큐, 통계 등)
        try:
            from core.app_context import get_context
            from core.automation_controller import AutomationEvents
            get_context().publish(AutomationEvents.ITERATION_END, {
                'iter': getattr(self, 'auto_gen_count', 0),
                'waiting': waiting,
                'running': self.is_automating,
            })
        except Exception:
            pass

    def _stop_automation(self, message=None):
        """자동화 중지"""
        was_running = self.is_automating
        self.is_automating = False
        # 진행 중 생성도 실제로 중단 (cancel → 백엔드 interrupt).
        # 사이클 사이에 불리면 워커가 없어 no-op.
        worker = getattr(self, 'gen_worker', None)
        if worker is not None and hasattr(worker, 'cancel') and worker.isRunning():
            try:
                worker.cancel()
            except Exception:
                pass
        # 대기 카운트다운 정지
        if getattr(self, '_wait_timer', None):
            self._wait_timer.stop()
        self._wait_end_time = 0
        self._wait_total_ms = 0
        self._emit_auto_status()
        # PR 3: 중지 이벤트 발행
        if was_running:
            try:
                from core.app_context import get_context
                from core.automation_controller import AutomationEvents
                get_context().publish(AutomationEvents.STOPPED, {
                    'reason': message or 'user_stop',
                    'completed': getattr(self, 'auto_gen_count', 0),
                })
            except Exception:
                pass
        
        # 버튼 상태 복구 (자동화 모드는 유지)
        if self.btn_auto_toggle.isChecked():
            self.btn_generate.setText("🚀 자동화 시작")
            self.btn_generate.setStyleSheet(_gen_btn_style('#27ae60'))
        else:
            self.btn_generate.setText("✨ 이미지 생성")
            self.btn_generate.setStyleSheet(_gen_btn_style(_gen_btn_default_color()))

        self.btn_generate.setEnabled(True)
        
        if message:
            self.show_status(message)
            QMessageBox.information(self, "자동화", message)
        else:
            self.show_status(f"✅ 자동화 완료: {self.auto_gen_count}장 생성됨")
            
    def receive_event_scenarios(self, scenarios):
        """이벤트 시나리오를 대기열에 추가"""
        added_count = 0
        for scenario in scenarios:
            payload = scenario.get('payload', {})

            if not payload or 'prompt' not in payload:
                _logger.warning(f"잘못된 시나리오: {scenario}")
                continue

            self.queue_panel.add_single_item(payload)
            added_count += 1

        self.show_status(f"✅ {added_count}개의 이벤트가 대기열에 추가됨")
        QMessageBox.information(
            self, "전송 완료",
            f"{added_count}개의 이벤트가 대기열에 추가되었습니다."
        )

    def _on_center_tab_changed(self, index):
        """중앙 탭 전환 시 처리"""
        if not hasattr(self, 'center_tabs'):
            return
        current_widget = self.center_tabs.widget(index)

        # 탭에 따라 왼쪽 패널 전환
        if hasattr(self, 'left_stack'):
            if hasattr(self, 'mosaic_editor') and current_widget == self.mosaic_editor:
                self.left_stack.setFixedWidth(460)
                self.left_stack.setCurrentIndex(1)  # 에디터 도구
            else:
                # Vue 탭이면 _handle_vue_action에서 처리
                pass

        # 즐겨찾기 탭으로 전환 시 자동 새로고침
        if hasattr(self, 'fav_tab') and current_widget == self.fav_tab:
            self.refresh_favorites()

        # Gallery 탭 전환 시 저장된 폴더 자동 로드
        if hasattr(self, 'gallery_tab') and current_widget == self.gallery_tab:
            if not self.gallery_tab._all_paths and self.gallery_tab._current_folder:
                self.gallery_tab.load_folder(self.gallery_tab._current_folder)
                
    def _greedy_merge_words(self, words):
        """공백 구분 단어들을 알려진 다중단어 태그로 greedy 결합 (최장 우선).
        예: [tokyo, afterschool, summoners] → [tokyo afterschool summoners].
        DB에 없는 조합은 단일 단어로 유지."""
        try:
            from core.tag_intelligence import get_tag_intelligence
            ti = get_tag_intelligence()
        except Exception:
            return list(words)
        out, i, n = [], 0, len(words)
        while i < n:
            took = 1
            for j in range(min(5, n - i), 1, -1):   # 5..2 단어 조합을 길이순으로
                cand = ' '.join(words[i:i + j])
                if ti.is_known(cand) or ti.is_character(cand) or ti.is_copyright(cand):
                    out.append(cand)
                    took = j
                    break
            else:
                out.append(words[i])
            i += took
        return out

    def handle_prompt_only_transfer(self, prompt, negative):
        """PNG Info/Gallery에서 프롬프트만 전송"""
        import re
        # ② LoRA/LyCO/hypernet 토큰 제거 — main에 들어가면 LoRA STACK과 충돌
        def _strip_lora(s):
            s = re.sub(r'<(?:lora|lyco|lycoris|hypernet|lokr|loha|ip-?adapter):[^>]*>', '',
                       s or '', flags=re.IGNORECASE)
            return re.sub(r'\s*,\s*,\s*', ', ', s).strip().strip(',').strip()
        prompt = _strip_lora(prompt)
        negative = _strip_lora(negative)
        # ① 스마트 토큰화: 콤마 있으면 콤마, 없으면 공백(언더스코어→공백) 기준으로 각 태그를
        #    개별 분류 (공백 구분 프롬프트가 통째로 1덩어리→general(main)로 새던 버그 수정)
        raw = (prompt or '').strip()
        if ',' in raw:
            tokens = [t.strip() for t in raw.split(',') if t.strip()]
        else:
            words = [w for w in raw.split() if w.strip()]
            if any('_' in w for w in words):
                # 언더스코어 태그가 공백 구분 (white_hair blue_eyes) → 그대로 변환
                tokens = [w.replace('_', ' ').strip() for w in words]
            else:
                # 순수 공백 구분 단어 → 알려진 다중단어 태그로 greedy 결합
                # (tokyo afterschool summoners 가 3개로 쪼개지던 버그 수정)
                tokens = self._greedy_merge_words(words)
        classified = self.tag_classifier.classify_tags_for_event(tokens)
        # 분류 보강: wiki 분류기(265k)가 못 잡은 캐릭터/작품을 저장된 캐릭터 프리셋 +
        # tag_intelligence(character_profiles 34k)로 재분류 → general(main) 누수 방지
        try:
            from core.tag_intelligence import get_tag_intelligence
            from utils.character_presets import list_character_presets
            ti = get_tag_intelligence()
            saved = set(list_character_presets() or [])

            def _n(t):
                return t.strip().lower().replace("_", " ").replace(r"\(", "(").replace(r"\)", ")")
            leftover = []
            for t in classified.get("general", []):
                n = _n(t)
                if n in saved or ti.is_character(t):
                    classified["character"].append(t)
                elif ti.is_copyright(t):
                    classified["copyright"].append(t)
                else:
                    leftover.append(t)
            classified["general"] = leftover
        except Exception:
            pass
        bundle = {
            # count(인물수)를 general 앞에 포함 → apply_prompt_from_data가 인물수
            # 섹션(char_count_input)으로 분리. (과거엔 count를 빼서 1girl/2boys 등이
            # 당겨오기 시 통째로 누락됐음.)
            'general': ', '.join(classified.get("count", []) + classified["costume"] + classified["appearance"] + classified["expression"] + classified["action"] + classified["background"] + classified["composition"] + classified["effect"] + classified["objects"] + classified["general"]),
            'character': ', '.join(classified["character"]),
            'copyright': ', '.join(classified["copyright"]),
            'artist': ''
        }
        # preserve_locked=True → 선행/후행/작가 칸은 덮어쓰지 않고, 그 칸들과 겹치는
        # 태그는 당겨오지 않음 (인물수/캐릭터/main은 그대로 override)
        # comma_only=True → 당겨오기는 항상 콤마 구분이므로, 단일 다중단어 태그
        # ('genshin impact')가 공백으로 쪼개지지(망가지지) 않게 함
        self.apply_prompt_from_data(bundle, preserve_locked=True, comma_only=True)
        self.neg_prompt_text.setPlainText(negative)
        # Vue에서 T2I 탭으로 전환 유도
        if hasattr(self, 'vue_bridge'):
            self.vue_bridge.tabChanged.emit('t2i')
        self.show_status("✅ 프롬프트 전송 완료")

    def _handle_send_to_i2i(self, payload):
        """I2I 탭으로 전송 (Vue 호환)"""
        if hasattr(self, 'i2i_tab'):
            self.i2i_tab.load_from_payload(payload)
            if hasattr(self, 'vue_bridge'):
                self.vue_bridge.tabChanged.emit('i2i')
            self.show_status("✅ I2I 탭으로 전송 완료")

    def _handle_send_to_inpaint(self, payload):
        """Inpaint 탭으로 전송 (Vue 호환)"""
        if hasattr(self, 'inpaint_tab'):
            self.inpaint_tab.load_from_payload(payload)
            if hasattr(self, 'vue_bridge'):
                self.vue_bridge.tabChanged.emit('inpaint')
            self.show_status("✅ Inpaint 탭으로 전송 완료")

    def _gallery_send_to_editor(self, path: str):
        """에디터 탭으로 이미지 전송 (Vue 호환)"""
        if hasattr(self, 'vue_bridge'):
            self.vue_bridge.editorImageLoaded.emit(path.replace('\\', '/'))
            self.vue_bridge.tabChanged.emit('editor')
            self.show_status(f"✅ 에디터로 전송: {os.path.basename(path)}")

    def _gallery_send_to_i2i(self, path: str):
        """I2I 탭으로 이미지 전송 (Vue 호환)"""
        if hasattr(self, 'i2i_tab') and hasattr(self.i2i_tab, '_load_image'):
            self.i2i_tab._load_image(path)
            if hasattr(self, 'vue_bridge'):
                self.vue_bridge.tabChanged.emit('i2i')
            self.show_status(f"✅ I2I로 전송: {os.path.basename(path)}")

    def _gallery_send_to_inpaint(self, path: str):
        """Inpaint 탭으로 이미지 전송 (Vue 호환)"""
        if hasattr(self, 'inpaint_tab') and hasattr(self.inpaint_tab, '_load_image'):
            self.inpaint_tab._load_image(path)
            if hasattr(self, 'vue_bridge'):
                self.vue_bridge.tabChanged.emit('inpaint')
            self.show_status(f"✅ Inpaint로 전송: {os.path.basename(path)}")

    def _gallery_send_to_upscale(self, path: str):
        """Gallery에서 Upscale 탭으로 이미지 전송"""
        if hasattr(self, 'upscale_tab') and hasattr(self.upscale_tab, '_add_file'):
            self.upscale_tab._add_file(path)
            idx = self.center_tabs.indexOf(self.upscale_tab)
            if idx >= 0:
                self.center_tabs.setCurrentIndex(idx)
            self.show_status(f"✅ Upscale로 전송: {os.path.basename(path)}")

    def _gallery_send_to_queue(self, payload: dict):
        """Gallery/Favorites에서 대기열에 추가"""
        if hasattr(self, 'queue_panel'):
            self.queue_panel.add_single_item(payload)
            self.show_status("📋 대기열에 추가되었습니다.")

    def _gallery_send_to_compare(self, path_a: str, path_b: str):
        """Gallery에서 두 이미지를 PNG Info 비교 탭으로 전송"""
        if hasattr(self, 'png_info_tab'):
            self.png_info_tab.load_compare_images(path_a, path_b)
            idx = self.center_tabs.indexOf(self.png_info_tab)
            if idx >= 0:
                self.center_tabs.setCurrentIndex(idx)
            self.show_status(
                f"🔍 이미지 비교: {os.path.basename(path_a)} vs {os.path.basename(path_b)}"
            )

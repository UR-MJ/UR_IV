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
        # 생성 중이면 토글 무시하고 되돌린다.
        # 되돌리는 setChecked 는 toggled 를 다시 쏘고 그게 곧 이 함수다 — 시그널을 막지 않으면
        # 되돌림 → 이 함수 → 되돌림 … 재귀가 한도까지 쌓였다가 풀리며 경고창이 수백 번 떴고,
        # 생성이 끝난 뒤에도 계속 떠서 강제 종료해야 했다. 경고도 모달 대신 토스트 한 번.
        if hasattr(self, 'gen_worker') and self.gen_worker and self.gen_worker.isRunning():
            btn = self.btn_auto_toggle
            was_blocked = btn.blockSignals(True)
            try:
                btn.setChecked(not checked)
            finally:
                btn.blockSignals(was_blocked)
            self._notify_automation_locked()
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
            
    def _notify_automation_locked(self):
        """'생성 중엔 못 바꾼다' 알림 — 토스트 한 번, 1.5초 안엔 반복하지 않는다."""
        import time as _t
        now = _t.monotonic()
        if now - float(getattr(self, '_auto_lock_notified_at', 0.0) or 0.0) < 1.5:
            return
        self._auto_lock_notified_at = now
        message = "이미지 생성 중에는 자동화 모드를 바꿀 수 없습니다"
        bridge = getattr(self, 'vue_bridge', None)
        if bridge is not None and hasattr(bridge, 'showNotification'):
            bridge.showNotification.emit('warning', message)
        else:
            QMessageBox.warning(self, "알림", message)

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
    
    # ── 덱 진행도 영속 (재시작 시 '얼마나 뽑았는지' 복원) ────────────────
    def _deck_state_path(self):
        from core.storage_paths import cache_file
        return str(cache_file(
            'search/last_deck.json',
            legacy_paths='config/last_deck.json',
        ))

    def _save_deck_state(self):
        """남은 덱을 filtered_results 인덱스 리스트로 저장.
        풀(filtered_results)은 last_search_results.json으로 따로 복원되므로,
        덱은 인덱스만 저장하면 충분(대용량에도 컴팩트). 소비/리필 때마다 호출."""
        try:
            import os, json
            fr = getattr(self, 'filtered_results', None) or []
            deck = getattr(self, 'shuffled_prompt_deck', None)
            snapshot_id = getattr(self, '_search_snapshot_id', None)
            if (
                deck is None
                or not isinstance(snapshot_id, str)
                or len(snapshot_id) != 32
                or any(ch not in '0123456789abcdefABCDEF' for ch in snapshot_id)
            ):
                return
            # id→index 맵 캐시 (filtered_results 객체가 교체되면 재생성)
            if getattr(self, '_deck_idmap_for', None) != id(fr):
                self._deck_idmap = {id(b): i for i, b in enumerate(fr)}
                self._deck_idmap_for = id(fr)
            idmap = self._deck_idmap
            idx = [idmap[id(b)] for b in deck if id(b) in idmap]
            path = self._deck_state_path()
            from utils.atomic_json import atomic_write_json
            atomic_write_json(
                path,
                {
                    'schema_version': 1,
                    'snapshot_id': snapshot_id,
                    'pool_size': len(fr),
                    'remaining': idx,
                },
                indent=None,
            )
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
            if st.get('schema_version') != 1:
                return False
            if st.get('snapshot_id') != getattr(self, '_search_snapshot_id', None):
                return False
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
        # 일시정지 · 일회성 덮어쓰기 상태를 새 회차에 물려주지 않는다.
        # (직전 자동화에서 멈춘 채 끝났으면 새로 시작하자마자 또 멈춰 버린다)
        self._auto_paused = False
        self._auto_resume_pending = ''
        self._wait_paused_remaining_ms = None
        self._auto_prompt_override = ''
        self._auto_override_used = False

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
            from core.app_context import Events, get_context
            get_context().publish(Events.AUTOMATION_STARTED, {
                'mode': settings.get('termination_mode', 'count'),
                'limit': settings.get('termination_limit', 0),
                'delay': settings.get('delay', 1.0),
                'max_retries': settings.get('max_retries', 0),
            })
        except Exception:
            pass

        # ★★★ 첫 번째 프롬프트 적용 (apply_random_prompt 사용!) ★★★
        self.apply_random_prompt()
        # 위 호출이 총 프롬프트 상자를 다시 채운 '뒤'에 한 번 더 보낸다 —
        # 위쪽 첫 emit 은 아직 직전 회차의 프롬프트를 담고 있어 화면이 한 박자 어긋난다.
        self._emit_auto_status()

        # 첫 생성 시작 — 자동화 경로의 생성은 전부 _automation_start_generation 을 거친다
        # (일시정지 확인 + 일회성 덮어쓰기 소비가 여기 한 곳에만 있어야 새는 경로가 없다)
        from PyQt6.QtCore import QTimer
        delay_ms = int(settings['delay'] * 1000)
        QTimer.singleShot(delay_ms, self._automation_start_generation)


    def _run_automation_cycle(self):
        """자동화 사이클"""
        if not self.is_automating:
            return

        import time
        from PyQt6.QtCore import QTimer

        # 일시정지 — 덱·카운트·반복 상태를 건드리지 않고 그대로 선다.
        if getattr(self, '_auto_paused', False):
            self._auto_resume_pending = 'cycle'
            self._emit_auto_status()
            return

        # 직전 회차에서 일회성 덮어쓰기를 썼다면 총 프롬프트 상자를 섹션에서 다시 조립한다.
        # 반복 생성(repeat_per_prompt>1) 회차는 새 프롬프트를 안 뽑아 상자를 갱신하지
        # 않으므로, 여기서 되돌리지 않으면 덮어쓴 값이 다음 장까지 따라간다 —
        # 사용자가 정한 '이번만' 이 깨지는 유일한 구멍이었다.
        if getattr(self, '_auto_override_used', False):
            self._auto_override_used = False
            try:
                self.update_total_prompt_display()
            except Exception:
                pass

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

    # ── 일시정지 / 재개 · 일회성 프롬프트 덮어쓰기 ───────────────────────
    def _auto_is_waiting(self) -> bool:
        """지금이 '사이 간격 대기' 중인가.

        카운트다운 타이머가 돌고 있거나, 일시정지로 남은 시간을 얼려 둔 상태면 대기다.
        (_emit_auto_status 를 대기 여부를 모르는 곳 — 액션 핸들러 — 에서 부를 때 쓴다)
        """
        if getattr(self, '_wait_paused_remaining_ms', None) is not None:
            return True
        t = getattr(self, '_wait_timer', None)
        return bool(t is not None and t.isActive())

    def _set_prompt_override(self, text: str):
        """다음 '한 장'에만 쓸 프롬프트 전문을 걸어 둔다. 빈 문자열이면 덮어쓰기 취소.

        Vue 는 추가/제거를 따로 추적하지 않고 편집 결과를 전문으로 보낸다 — 그래야
        와일드카드가 이미 풀린 문자열을 사람이 그대로 손볼 수 있다.
        걸자마자 총 프롬프트 상자에 반영하는 이유: 그 상자가 곧 API 로 나갈 문자열이고
        (_build_generation_payload 가 그대로 읽는다), 사용자가 방금 고친 게 화면에
        남아 있어야 '보이는 대로 나간다'가 성립한다.
        """
        text = (text or '').strip()
        self._auto_prompt_override = text
        try:
            if text:
                self.total_prompt_display.setPlainText(text)
            else:
                # 취소 → 섹션 위젯에서 원래 프롬프트를 다시 조립한다.
                self.update_total_prompt_display()
        except Exception:
            pass
        self._emit_auto_status(waiting=self._auto_is_waiting())

    def _consume_prompt_override(self):
        """걸린 덮어쓰기를 총 프롬프트 상자에 밀어 넣고 '즉시' 비운다.

        덱에는 손대지 않는다 — 덱 pop 은 _run_automation_cycle → apply_random_prompt
        가 따로 하므로, 이번 장을 손봤다고 덱 진행이 어긋나지 않는다.
        (큐 우선 항목도 같은 방식으로 총 프롬프트 상자에 직접 넣는다 — 검증된 경로)
        """
        ov = getattr(self, '_auto_prompt_override', '') or ''
        if not ov:
            return
        self._auto_prompt_override = ''      # '이번만' — 쓰는 순간 사라진다
        self._auto_override_used = True      # 다음 사이클에서 상자를 되돌리라는 표시
        try:
            self.total_prompt_display.setPlainText(ov)
        except Exception:
            pass

    def _automation_start_generation(self):
        """자동화 경로의 유일한 생성 진입점 — 일시정지 확인 + 덮어쓰기 소비 후 생성."""
        if not self.is_automating:
            return
        if getattr(self, '_auto_paused', False):
            # 반복 카운터·자연어 변환은 이미 끝난 지점이라 재개 시 여기로 되돌아온다.
            self._auto_resume_pending = 'start'
            self._emit_auto_status()
            return
        self._consume_prompt_override()
        self.start_generation()

    def _pause_automation(self):
        """자동화 일시정지 — 덱·카운트·반복 상태를 모두 유지한다(_stop_automation 과 다름).

        진행 중인 생성은 중단하지 않는다. 이 화면에서 '멈춤'은 다음 장을 내보내기 전에
        프롬프트를 손보려는 것이라, 이미 GPU 에 넘어간 장을 버릴 이유가 없다.
        대기 시간 처리: 남은 시간을 그 자리에서 '얼린다'(흘려보내지 않는다). 사이 간격은
        API 호출 사이의 최소 간격이라 사람이 잠깐 세웠다고 건너뛰면 설정이 무의미해지고,
        얼려 봐야 재개 후 최대 delay 한 번(보통 1초)이라 체감 비용이 없다.
        """
        if not self.is_automating or getattr(self, '_auto_paused', False):
            return
        self._auto_paused = True
        t = getattr(self, '_wait_timer', None)
        if t is not None and t.isActive():
            import time as _t
            self._wait_paused_remaining_ms = max(
                0, int((getattr(self, '_wait_end_time', 0) - _t.time()) * 1000))
            t.stop()
            self._wait_end_time = 0
        self.show_status("⏸ 자동화 일시정지 — 덱·카운트는 그대로")
        self._emit_auto_status(waiting=self._auto_is_waiting())

    def _resume_automation(self):
        """멈춘 지점부터 잇는다 — 어디서 섰는지에 따라 되돌아갈 곳이 다르다."""
        if not self.is_automating or not getattr(self, '_auto_paused', False):
            return
        self._auto_paused = False
        from PyQt6.QtCore import QTimer

        # 1) 대기 중에 멈췄다 → 얼려 둔 잔여 시간부터 다시 센다.
        rem = getattr(self, '_wait_paused_remaining_ms', None)
        if rem is not None:
            import time as _t
            self._wait_paused_remaining_ms = None
            self._wait_end_time = _t.time() + (max(0, int(rem)) / 1000.0)
            self._ensure_wait_timer()
            self._wait_timer.start(100)
            self.show_status("▶ 자동화 재개")
            self._emit_auto_status(waiting=True)
            return

        # 2) 그 외 — 멈춘 단계로 되돌아간다.
        #    generate : 대기가 끝난 직후(반복 카운터 올리기 전)
        #    start    : 반복 카운터·자연어 변환까지 끝난 직후
        #    continue : 생성이 끝난 뒤(큐 우선 → 덱 순서를 그대로 잇는다)
        #    cycle    : 사이클 진입 직전
        pending = getattr(self, '_auto_resume_pending', '') or ''
        self._auto_resume_pending = ''
        self.show_status("▶ 자동화 재개")
        self._emit_auto_status()
        target = {
            'generate': getattr(self, '_automation_generate', None),
            'start': getattr(self, '_automation_start_generation', None),
            'continue': getattr(self, '_continue_automation', None),
            'cycle': getattr(self, '_run_automation_cycle', None),
        }.get(pending)
        if target is not None:
            QTimer.singleShot(0, target)
        # pending 이 비어 있으면 생성이 아직 진행 중이라는 뜻 —
        # 그 생성이 끝나면 _continue_automation 이 평소대로 이어간다.


    def _automation_generate(self):
        """자동화 이미지 생성"""
        if not self.is_automating:
            return

        # 대기 타이머 정지 (생성 들어가면 카운트다운 종료)
        if getattr(self, '_wait_timer', None):
            self._wait_timer.stop()
        self._wait_end_time = 0

        # 대기가 끝난 바로 이 지점이 '대기와 생성 사이'다 — 일시정지는 여기서 선다.
        # 반복 카운터를 올리기 전이라, 재개하면 이 함수로 되돌아와 그대로 이어간다.
        if getattr(self, '_auto_paused', False):
            self._wait_paused_remaining_ms = None   # 대기는 이미 다 흘렀다
            self._auto_resume_pending = 'generate'
            self._emit_auto_status()
            return

        self.auto_current_repeat += 1

        # 생성 시 태그→자연어 자동 변환 (비동기 worker — UI 안 멈춤).
        # 이미 변환된 프롬프트(반복 생성 등)는 문자열 비교로 건너뜀 → 누적 방지.
        # 큐 우선 항목은 _automation_generate를 거치지 않으므로 자연스럽게 제외됨.
        # 사용자가 이번 장 프롬프트를 직접 고쳤으면(덮어쓰기) 변환을 건너뛴다 —
        # 고친 전문이 그대로 나가야 화면에 보인 것과 API 로 나간 것이 같아진다.
        if (getattr(self, '_auto_nl_enabled', False)
                and not getattr(self, '_auto_processing_queue', False)
                and not (getattr(self, '_auto_prompt_override', '') or '')):
            cur = self.main_prompt_text.toPlainText().strip()
            if cur and cur != getattr(self, '_auto_nl_last_output', None):
                if self._start_auto_nl_then_generate(cur):
                    return   # worker 완료 콜백에서 생성 호출
        self._automation_start_generation()

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
            w = OllamaWorker(
                url, model, base_tags, 'nl_caption', '', self, instruction_feature='auto_nl',
            )
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
            # 변환이 update_total_prompt_display 로 상자를 다시 채웠으므로,
            # 덮어쓰기 소비는 반드시 그 '뒤'인 여기서 일어나야 한다.
            self._automation_start_generation()

    def _on_auto_nl_error(self, err: str):
        """변환 실패 → 원본 태그 그대로 생성."""
        print(f"[AutoNL] 변환 실패(태그로 생성): {err}")
        if self.is_automating:
            self._automation_start_generation()

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
        if not self.is_automating or getattr(self, '_auto_paused', False):
            # 일시정지는 _pause_automation 이 이미 타이머를 세웠다 — 여기는 방어선.
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

        # 1.5) 일시정지 — 방금 끝난 생성의 뒷정리까지만 하고 선다. 새 생성은 시작하지 않는다.
        #      재개하면 이 함수 처음부터 다시 들어온다(위 1단계는 _auto_processing_queue 가
        #      이미 False 라 무해) → 큐 우선 → 프롬프트 복원 → 덱 순서가 그대로 이어진다.
        if getattr(self, '_auto_paused', False):
            self._auto_resume_pending = 'continue'
            self._emit_auto_status()
            return

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
            _frozen = getattr(self, '_wait_paused_remaining_ms', None)
            if _frozen is not None:
                # 일시정지가 대기 중에 걸렸다 — 얼려 둔 잔여 시간을 그대로 비춘다.
                waiting = True
                _wait_remaining = max(0, int(_frozen))
            elif waiting:
                _wait_remaining = max(0, int((getattr(self, '_wait_end_time', 0) - _t.time()) * 1000))
            # 다음 생성에 나갈 프롬프트.
            #   total_prompt_display 는 _build_generation_payload 가 '그대로 읽어' API 로
            #   보내는 바로 그 문자열이다. 덱에서 뽑는 순간(apply_prompt_from_data)에
            #   제외 프롬프트 · 캐릭터 특징 · 조건식(1·2차) · 와일드카드 치환까지 모두
            #   끝나 이 상자에 들어오므로, 대기 중에도 이미 확정된 값을 보낼 수 있다.
            #   아직 반영되지 않는 것 = 생성 직전에야 붙는 3가지:
            #     · run_pipeline_on_text 훅(인스턴트 와일드카드 $$name$$, 중복 제거)
            #     · LoRA 스택 텍스트(<lora:...>) 꼬리
            #     · 태그→자연어 자동 변환(켰을 때만, 생성 직전 비동기)
            #   이 셋은 여기서 미리 계산할 수 없다(훅·와일드카드는 매 호출 결과가 달라져
            #   미리 돌리면 실제로 나갈 값과 어긋난다). 그래서 '지금 알 수 있는 가장
            #   가까운 값'인 이 상자를 보낸다 — 사람이 손볼 대상도 이 문자열이다.
            # 덮어쓰기가 걸려 있으면 그 값이 우선 — 방금 고친 게 그대로 보여야 한다.
            _override = getattr(self, '_auto_prompt_override', '') or ''
            _prompt = _override
            if not _prompt:
                try:
                    _prompt = self.total_prompt_display.toPlainText()
                except Exception:
                    _prompt = ''
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
                'paused': bool(getattr(self, '_auto_paused', False)),
                'prompt': _prompt or '',
            }))
        # PR 3: AppContext에도 발행 (다른 모듈이 구독 가능 — 큐, 통계 등)
        try:
            from core.app_context import Events, get_context
            get_context().publish(Events.AUTOMATION_ITERATION_END, {
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
        # 일시정지·일회성 덮어쓰기는 자동화 한 회차짜리 상태다 — 중지와 함께 사라진다.
        # (남겨 두면 다음 '시작'이 멈춘 채로 뜨거나 남의 프롬프트로 첫 장이 나간다)
        self._auto_paused = False
        self._auto_resume_pending = ''
        self._wait_paused_remaining_ms = None
        if getattr(self, '_auto_prompt_override', '') or getattr(self, '_auto_override_used', False):
            self._auto_prompt_override = ''
            self._auto_override_used = False
            try:
                self.update_total_prompt_display()   # 덮어쓴 상자를 원래대로
            except Exception:
                pass
        self._emit_auto_status()
        # PR 3: 중지 이벤트 발행
        if was_running:
            try:
                from core.app_context import Events, get_context
                get_context().publish(Events.AUTOMATION_STOPPED, {
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

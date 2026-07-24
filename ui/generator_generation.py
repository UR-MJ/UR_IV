# ui/generator_generation.py
"""
이미지 생성 및 자동화 관련 로직
"""
import os
import time
import random
import json
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from config import OUTPUT_DIR
from workers.generation_worker import GenerationFlowWorker
from utils.file_wildcard import resolve_file_wildcards
from utils.wildcard import process_wildcards
from utils.app_logger import get_logger
from utils.theme_manager import get_theme_manager


def _widget_text(w, fallback: str = '') -> str:
    """위젯에서 텍스트 값을 얻는다. proxy/LineEdit/ComboBox/PlainTextEdit 모두 대응.

    우선순위: .text() → _fallback_text → .toPlainText() → .currentText()
    """
    v = w.text() if hasattr(w, 'text') else ''
    if not v and hasattr(w, '_fallback_text'):
        v = w._fallback_text
    if not v and hasattr(w, 'toPlainText'):
        v = w.toPlainText()
    if not v and hasattr(w, 'currentText'):
        v = w.currentText()
    return v or fallback


def _widget_float(w, fallback: float) -> float:
    try:
        v = _widget_text(w)
        return float(v) if v else fallback
    except (ValueError, TypeError):
        return fallback


def _widget_int(w, fallback: int) -> int:
    try:
        v = _widget_text(w)
        return int(float(v)) if v else fallback
    except (ValueError, TypeError):
        return fallback


def _gen_btn_default_color() -> str:
    """생성 버튼 기본 색상"""
    return '#4A90E2'


def _gen_btn_style(bg_color: str) -> str:
    """생성 버튼 스타일"""
    return (
        f"QPushButton {{ font-size: 15px; font-weight: bold; "
        f"background-color: {bg_color}; color: white; "
        f"border: none; border-radius: 20px; padding: 4px; }}"
    )

_logger = get_logger('generation')


class GenerationMixin:
    """이미지 생성 관련 로직을 담당하는 Mixin"""
    
    def _maybe_unload_ollama(self):
        """생성 직전 Ollama LLM 언로드 (ui_prefs.ollamaUnloadOnGen 켜진 경우) → VRAM 양보.
        best-effort 비동기 — Ollama 미실행/미설정이면 조용히 무시. 자동화·수동 공통 경로."""
        try:
            import json as _json
            import threading as _th
            prefs_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'ui_prefs.json')
            if not os.path.exists(prefs_path):
                return
            with open(prefs_path, 'r', encoding='utf-8') as f:
                prefs = _json.load(f)
            if not prefs.get('ollamaUnloadOnGen'):
                return
            model = (prefs.get('ollamaModel') or '').strip()
            if not model:
                return
            url = prefs.get('ollamaUrl') or 'http://localhost:11434'

            def _do():
                try:
                    from core.ollama_client import OllamaClient
                    OllamaClient(url, model).unload()
                except Exception:
                    pass
            _th.Thread(target=_do, daemon=True).start()
        except Exception:
            pass

    def start_generation(self):
        """이미지 생성 시작"""
        # 1) 입력 파싱 + payload 구성 + 검증 — UI를 '생성 중'으로 전환하기 *전에* 수행.
        #    (검증 실패 시 버튼/Vue 스피너가 '생성 중'으로 영구 잔류하던 버그 방지)
        try:
            payload, err = self._build_generation_payload()
        except Exception as e:
            _logger.exception("payload 구성 실패")
            payload, err = None, str(e)
        if payload is None:
            self._abort_generation(err or '생성 준비 실패')
            return

        self._maybe_unload_ollama()
        self._gen_start_time = time.time()
        # 상태 표시 업데이트
        self.setWindowTitle("AI Studio - Pro [생성 중...]")
        self.btn_generate.setText("⏳ 생성 중...")
        self.btn_generate.setEnabled(False)
        self.btn_generate.setStyleSheet(_gen_btn_style('#e67e22'))

        # 상태바 업데이트
        self.show_status("🎨 이미지 생성 중...")

        # 뷰어에 로딩 표시
        if hasattr(self, 'vue_bridge'):
            self.vue_bridge.send_start()
        self.viewer_label.setText("🎨 이미지 생성 중...\n\n잠시만 기다려주세요.")
        c = get_theme_manager().get_colors()
        self.viewer_label.setStyleSheet(f"""
            QLabel {{
                background-color: {c['bg_secondary']};
                border-radius: 8px;
                color: #e67e22;
                font-size: 16px;
                font-weight: bold;
            }}
        """)

        _logger.info("Sending Payload to WebUI API")
        _logger.debug(f"프롬프트: {payload['prompt'][:100]}...")

        selected_model = self.model_combo.currentText()
        self._cleanup_gen_worker()
        self.gen_worker = GenerationFlowWorker(selected_model, payload)
        self.gen_worker.finished.connect(self.on_generation_finished)
        self.gen_worker.progress.connect(self._on_generation_progress)

        # 프로그레스 바 초기화
        self.gen_progress_bar.setValue(0)
        self.gen_progress_bar.setRange(0, 100)
        self.gen_progress_bar.setFormat("생성 준비 중...")
        self.gen_progress_bar.show()

        self.gen_worker.start()

    def _abort_generation(self, msg: str):
        """생성 시작 실패 — UI 복구 + 에러 통지 + 자동화 명시적 중지.
        (기존엔 bare return으로 스피너 잔류 + 자동화가 조용히 멈췄음)"""
        _logger.error("generation aborted: %s", msg)
        try:
            self._restore_generate_button()
        except Exception:
            pass
        try:
            self.gen_progress_bar.hide()
        except Exception:
            pass
        self.show_status(f"설정 오류: {msg}", 5000)
        if hasattr(self, 'vue_bridge'):
            # generationError → App.vue가 에러 토스트 + isGenerating(스피너) 리셋
            self.vue_bridge.generationError.emit(f'설정 오류: {msg}')
        # 자동화 중 검증 실패는 다음 사이클도 같은 이유(설정 문제)로 실패 →
        # 무한 루프/조용한 정지 대신 사유를 보여주며 중지
        if getattr(self, 'is_automating', False):
            try:
                self._stop_automation(f"설정 오류로 자동화 중지: {msg}")
            except Exception:
                self.is_automating = False

    def _build_generation_payload(self):
        """입력 위젯 → 검증된 payload. 성공 시 (payload, None), 실패 시 (None, 사유).
        UI 상태는 건드리지 않음 — start_generation이 검증 통과 후에만 busy 전환."""
        # 해상도 결정
        if self.random_res_check.isChecked() and self.random_resolutions:
            width, height, _ = random.choice(self.random_resolutions)
            self.width_input.setText(str(width))
            self.height_input.setText(str(height))
        else:
            width = _widget_int(self.width_input, 1024)
            height = _widget_int(self.height_input, 1024)

        # 고해상도/자동해상도 + 설정 가능한 ANIMA 면적/한변 캡 — 순수 함수로 분리.
        # 동작/테스트: core/resolution_guard.py, tests/test_resolution_guard.py
        hr_factor = getattr(self, '_high_res_factor', 1.0) or 1.0
        _auto_res = bool(getattr(self, 'auto_res_check', None)
                         and self.auto_res_check.isChecked())
        from core.resolution_guard import (
            ANIMA_MAX_AREA, ANIMA_MAX_SIDE, apply_anima_resolution,
        )
        _guard_enabled = bool(getattr(self, '_anima_guard_enabled', True))
        _guard_area = int(getattr(self, '_anima_guard_max_area', ANIMA_MAX_AREA))
        _guard_side = int(getattr(self, '_anima_guard_max_side', ANIMA_MAX_SIDE))
        _bw, _bh = width, height
        width, height = apply_anima_resolution(
            _bw, _bh, hr_factor, _auto_res,
            max_area=_guard_area, max_side=_guard_side,
            enabled=_guard_enabled,
        )
        if (width, height) != (_bw, _bh):
            _guard_desc = (f"area≤{_guard_area:,}, side≤{_guard_side}"
                           if _guard_enabled else "OFF")
            print(f"[HighRes] base {_bw}x{_bh} (hr={hr_factor}, auto={_auto_res}) "
                  f"→ {width}x{height} (Anima Guard {_guard_desc})")
        
        combined_neg_prompt = self.neg_prompt_text.toPlainText().strip()

        # 와일드카드 치환
        final_prompt = self.total_prompt_display.toPlainText()
        wc_enabled = (hasattr(self, 'settings_tab') and
                      hasattr(self.settings_tab, 'chk_wildcard_enabled') and
                      self.settings_tab.chk_wildcard_enabled.isChecked())
        if wc_enabled:
            final_prompt = resolve_file_wildcards(final_prompt)
            final_prompt = process_wildcards(final_prompt)
            combined_neg_prompt = resolve_file_wildcards(combined_neg_prompt)
            combined_neg_prompt = process_wildcards(combined_neg_prompt)

        # PR 1: PromptPipeline 컨버전스 — 등록된 모든 훅을 final_prompt에 적용
        # 기존 처리 *뒤*에 호출되므로 비파괴적. instant_wildcards($$name$$),
        # standard_dedupe, 사용자 추가 훅 등이 여기서 동작.
        try:
            from core.standard_hooks import run_pipeline_on_text
            final_prompt = run_pipeline_on_text(final_prompt)
            combined_neg_prompt = run_pipeline_on_text(combined_neg_prompt)
        except Exception as e:
            _logger.warning(f"pipeline 실행 실패 (원본 유지): {e}")

        # LoRA 합침 (Vue LoRA Stack 우선, 없으면 Python panel)
        lora_text = getattr(self, '_vue_lora_text', '')
        if not lora_text and hasattr(self, 'lora_active_panel'):
            lora_text = self.lora_active_panel.get_active_lora_text()
        if lora_text:
            # 프롬프트에 이미 <lora:NAME...>이 있으면(큐 항목의 EXIF 로라 등) 스택의 같은
            # LoRA는 제외 — 동일 LoRA 이중 적용 방지.
            import re as _re
            existing = {n.strip().lower()
                        for n in _re.findall(r'<lora:([^:>]+)', final_prompt or '', flags=_re.IGNORECASE)}
            if existing:
                kept = []
                for seg in lora_text.split(','):
                    s = seg.strip()
                    m = _re.match(r'<lora:([^:>]+)', s, flags=_re.IGNORECASE)
                    if m and m.group(1).strip().lower() in existing:
                        continue
                    if s:
                        kept.append(s)
                lora_text = ', '.join(kept)
            if lora_text:
                final_prompt = f"{final_prompt}, {lora_text}" if final_prompt else lora_text

        # Payload 생성
        payload = {
            "prompt": final_prompt,
            "negative_prompt": combined_neg_prompt,
            "sampler_name": self.sampler_combo.currentText(),
            "scheduler": self.scheduler_combo.currentText(),
            "steps": _widget_int(self.steps_input, 28),
            "cfg_scale": _widget_float(self.cfg_input, 7.0),
            "seed": _widget_int(self.seed_input, -1),
            "width": width,
            "height": height,
            "send_images": True,
            "save_images": True,
            "alwayson_scripts": {}
        }

        # 메인 VAE / TE → Forge Neo의 forge_additional_modules로 통합 전달
        # (override_settings.sd_vae와 병행 시 Forge processing._vae_override 충돌)
        extra_modules = self._build_vae_te_override()
        if extra_modules:
            payload["forge_additional_modules"] = extra_modules

        # Shift (Distilled CFG Scale)
        shift_val = _widget_float(self.shift_input, 0.0)
        if shift_val > 0:
            payload["distilled_cfg_scale"] = shift_val

        # Hires.fix
        if self.hires_options_group.isChecked():
            hr_scale = _widget_float(self.hires_scale_input, 2.0)
            if hr_scale <= 0:
                hr_scale = 2.0
            # Hires 패스에서 모듈 처리:
            # - 베이스에 forge_additional_modules가 있으면 "Use same choices"로 reload 회피
            #   (실제 리스트를 넘기면 Forge processing.py:1404 modules_change가 True를
            #    반환해 forge_model_reload() 호출 → BufferError 발생)
            # - 없으면 빈 리스트 (Built-in)
            if payload.get("forge_additional_modules"):
                hr_modules = ["Use same choices"]
            else:
                hr_modules = []
            hr_payload = {
                "enable_hr": True,
                "hr_upscaler": self.upscaler_combo.currentText(),
                "hr_second_pass_steps": _widget_int(self.hires_steps_input, 0),
                "denoising_strength": _widget_float(self.hires_denoising_input, 0.5),
                "hr_scale": hr_scale,
                "hr_additional_modules": hr_modules,
            }
            hr_cfg = _widget_float(self.hires_cfg_input, 0.0)
            if hr_cfg > 0:
                hr_payload["hr_cfg"] = hr_cfg

            # Hires Checkpoint
            hr_ckpt = self.hires_checkpoint_combo.currentText()
            if hr_ckpt and hr_ckpt != "Use same checkpoint":
                hr_payload["hr_checkpoint_name"] = hr_ckpt

            # Hires Sampler
            hr_sampler = self.hires_sampler_combo.currentText()
            if hr_sampler and hr_sampler != "Use same sampler":
                hr_payload["hr_sampler_name"] = hr_sampler

            # Hires Scheduler
            hr_scheduler = self.hires_scheduler_combo.currentText()
            if hr_scheduler and hr_scheduler != "Use same scheduler":
                hr_payload["hr_scheduler"] = hr_scheduler

            # Hires Prompt / Negative Prompt
            hr_prompt = self.hires_prompt_text.toPlainText().strip()
            if hr_prompt:
                hr_payload["hr_prompt"] = hr_prompt
            hr_neg = self.hires_neg_prompt_text.toPlainText().strip()
            if hr_neg:
                hr_payload["hr_negative_prompt"] = hr_neg

            payload.update(hr_payload)

        # NegPiP
        if hasattr(self, 'negpip_group') and self.negpip_group.isChecked():
            payload["alwayson_scripts"]["NegPiP"] = {"args": [True]}

        self._apply_postprocess_chain(payload)

        # payload 사전 검증 — 잘못된 값은 API 호출 전에 사용자에게 안내
        from core.payload_validator import PayloadValidator
        vr = PayloadValidator.validate(payload)
        for w in vr.warnings:
            _logger.warning("payload warning: %s", w)
        if not vr.ok:
            msg = " / ".join(vr.errors)
            _logger.error("payload invalid: %s", msg)
            return None, msg

        return payload, None

    def _build_vae_te_override(self) -> list:
        """메인 VAE + TE 파일들을 Forge Neo의 ``forge_additional_modules``
        포맷(파일명 리스트)으로 합쳐서 반환.

        VAE와 TE 모두 비어있으면 빈 리스트 반환.

        주의: ``override_settings.sd_vae``를 같이 보내면 Forge processing.py에서
        ``_vae_override`` 튜플 언팩 에러가 발생하므로, VAE도 이 리스트로만 전달한다.
        Forge가 파일명을 ``models/VAE/`` 또는 ``models/text_encoder/``에서 자동 매칭.
        """
        modules: list[str] = []

        vae = ''
        try:
            vae = (self.vae_main_combo.currentText() or '').strip()
        except Exception:
            pass
        if vae and vae not in ("Use checkpoint default", "Use same VAE", ""):
            modules.append(vae)

        te_raw = ''
        try:
            te_raw = (self.te_main_input.text() or '').strip()
        except Exception:
            pass
        if te_raw:
            modules.extend(t.strip() for t in te_raw.split(',') if t.strip())

        return modules

    def _cleanup_gen_worker(self):
        """이전 생성 워커 정리 — 시그널을 시그널별로 분리 해제하여 부분 실패 시에도 누수 방지."""
        worker = getattr(self, 'gen_worker', None)
        if worker is None:
            return
        for sig_name in ('finished', 'progress'):
            try:
                sig = getattr(worker, sig_name, None)
                if sig is not None:
                    sig.disconnect()
            except (TypeError, RuntimeError):
                # 이미 연결 해제됐거나 C++ 객체가 삭제된 경우
                pass
        try:
            if worker.isRunning():
                # cancel() = 취소 플래그 + 백엔드 interrupt → 블로킹 HTTP가 곧 반환되어
                # run()이 자연 종료됨. terminate(스레드 강제 종료, 락 잡은 채 죽을 수
                # 있음)는 최후 수단으로만.
                if hasattr(worker, 'cancel'):
                    worker.cancel()
                worker.quit()
                if not worker.wait(5000):
                    _logger.warning("gen_worker wait timeout — terminate 호출")
                    worker.terminate()
                    worker.wait(500)
        except RuntimeError:
            pass
        self.gen_worker = None

    def _on_generation_progress(self, step: int, total: int, preview):
        """생성 진행률 업데이트"""
        if total <= 0:
            return

        self.gen_progress_bar.setRange(0, total)
        self.gen_progress_bar.setValue(step)

        # ETA 계산 — worker._start_time 기준 경과시간으로 남은 시간 추정
        eta_str = ""
        try:
            import time
            start_time = getattr(self.gen_worker, '_start_time', None)
            if start_time and step > 0:
                elapsed = time.monotonic() - start_time
                per_step = elapsed / step
                remaining = max(0.0, per_step * (total - step))
                if remaining >= 60:
                    eta_str = f" · ETA {int(remaining // 60)}m{int(remaining % 60):02d}s"
                else:
                    eta_str = f" · ETA {remaining:.0f}s"
        except Exception:
            eta_str = ""

        self.gen_progress_bar.setFormat(f"{step} / {total} steps{eta_str}")

        pct = int(step / total * 100)
        self.setWindowTitle(f"AI Studio - Pro [{step}/{total} steps · {pct}%{eta_str}]")
        self.viewer_label.setText(
            f"🎨 이미지 생성 중...\n\n"
            f"{step} / {total} steps ({pct}%){eta_str}"
        )
        self.show_status(f"🎨 생성 중... {step}/{total} steps ({pct}%){eta_str}")

        # Vue에 진행률 전달
        if hasattr(self, 'vue_bridge'):
            self.vue_bridge.generationProgress.emit(step, total)

    def _restore_generate_button(self):
        """생성 버튼/타이틀을 idle 상태로 복구 (완료/취소 공용)."""
        if self.btn_auto_toggle.isChecked():
            if self.is_automating:
                self.btn_generate.setText("⏸️ 자동화 중지")
                self.btn_generate.setStyleSheet(_gen_btn_style('#e74c3c'))
            else:
                self.btn_generate.setText("🚀 자동화 시작")
                self.btn_generate.setStyleSheet(_gen_btn_style('#27ae60'))
        else:
            self.btn_generate.setText("✨ 이미지 생성")
            self.btn_generate.setStyleSheet(_gen_btn_style(_gen_btn_default_color()))
        self.btn_generate.setEnabled(True)
        self.setWindowTitle("AI Studio - Pro")

    def on_generation_finished(self, result, gen_info):
        """생성 완료 처리"""
        # 버튼/타이틀 복구 (자동화 모드에 따라 다르게)
        self._restore_generate_button()

        # 프로그레스 바 숨김
        self.gen_progress_bar.hide()
        self.gen_progress_bar.setValue(0)

        # 뷰어 스타일 복구
        c = get_theme_manager().get_colors()
        self.viewer_label.setStyleSheet(f"""
            QLabel {{
                background-color: {c['bg_secondary']};
                border-radius: 8px;
                color: {c['text_muted']};
            }}
        """)
        
        # 취소 분기 — 에러(E020)/실패 통계/자동화 재시도로 처리하지 않음
        if isinstance(gen_info, dict) and gen_info.get('cancelled'):
            self.viewer_label.setText("⏹ 생성 취소됨")
            self.show_status("⏹ 생성 취소됨", 3000)
            if hasattr(self, 'vue_bridge'):
                # Vue 스피너 리셋 (✕로 이미 리셋된 경우 무해)
                self.vue_bridge.generationError.emit('생성 취소됨')
            if hasattr(self, 'queue_manager') and self.queue_manager.is_running:
                self.queue_manager.on_generation_completed(False)
            return

        if isinstance(result, bytes):
            self._auto_retry_count = 0   # 성공 — 자동화 재시도 카운터 리셋
            self._process_new_image(result, gen_info)
            self.show_status("✅ 이미지 생성 완료!")

            # 프롬프트 히스토리 기록
            try:
                from utils.prompt_history import add_entry
                add_entry(
                    self.total_prompt_display.toPlainText(),
                    self.neg_prompt_text.toPlainText()
                )
            except Exception:
                pass

            # 생성 통계 기록
            try:
                from core.gen_stats import get_gen_stats
                duration = round(time.time() - getattr(self, '_gen_start_time', time.time()), 1)
                get_gen_stats().record({
                    'success': True,
                    'duration_sec': duration,
                    'model': self.model_combo.currentText() if hasattr(self, 'model_combo') else '',
                    'seed': gen_info.get('seed', 0) if isinstance(gen_info, dict) else 0,
                    'width': int(self.width_input.text()) if hasattr(self, 'width_input') else 0,
                    'height': int(self.height_input.text()) if hasattr(self, 'height_input') else 0,
                })
            except Exception:
                pass

            # 비활성 창이면 알림 (단일 생성, 비자동화)
            if not self.is_automating and not self.isActiveWindow():
                self._notify_generation_done()

            # 자동화 중이면 카운트 증가
            if self.is_automating:
                self.auto_gen_count += 1
                self.show_status(
                    f"🔄 자동 생성 중... ({self.auto_gen_count}장 완료)"
                )
        else:
            error_msg = f"[E020] 생성 실패: {result}"
            # 실패 통계 기록
            try:
                from core.gen_stats import get_gen_stats
                duration = round(time.time() - getattr(self, '_gen_start_time', time.time()), 1)
                get_gen_stats().record({
                    'success': False,
                    'duration_sec': duration,
                    'model': self.model_combo.currentText() if hasattr(self, 'model_combo') else '',
                })
            except Exception:
                pass
            self.viewer_label.setText(f"❌ {error_msg}")
            self.show_status(error_msg, 5000)
            print(f"\n[E020] Generation Failed: {result}")
            if hasattr(self, 'vue_bridge'):
                # generationError → App.vue가 에러 토스트 + isGenerating(스피너) 리셋
                # (단일 생성 실패 시 스피너가 안 풀리던 버그 수정)
                self.vue_bridge.generationError.emit(error_msg)
            # 자동화 실패 재시도 (max_retries + 지수 백오프) — 라이브 경로에 접목
            # (기존엔 dead 메서드에만 있어 max_retries가 실제로 동작 안 했음)
            if self.is_automating:
                if not hasattr(self, '_auto_retry_count'):
                    self._auto_retry_count = 0
                max_retries = int((getattr(self, 'auto_settings', {}) or {}).get('max_retries', 0))
                if self._auto_retry_count < max_retries:
                    self._auto_retry_count += 1
                    backoff = min(2.0 ** self._auto_retry_count, 30.0)
                    self.show_status(
                        f"⚠️ 생성 실패 — {backoff:.1f}초 후 재시도 "
                        f"({self._auto_retry_count}/{max_retries})")
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(int(backoff * 1000), self._automation_generate)
                    return   # 큐 진행/다음 사이클 스킵 — 재시도가 이어받음
                self._auto_retry_count = 0   # 재시도 소진

        # 대기열 매니저에 생성 완료 알림
        if hasattr(self, 'queue_manager') and self.queue_manager.is_running:
            self.queue_manager.on_generation_completed(isinstance(result, bytes))

        # ★★★ 자동화 계속 (generator_actions.py의 메서드 호출) ★★★
        if self.is_automating:
            self._continue_automation()
        
    def _process_new_image(self, image_data, gen_info):
        """새 이미지 처리"""
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        self.viewer_label.setPixmap(
            pixmap.scaled(
                self.viewer_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
        )
        
        filename = f"generated_{int(time.time())}_{random.randint(100,999)}.png"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(image_data)
        
        self.current_image_path = filepath

        # Vue 뷰어에 이미지 전달
        if hasattr(self, 'vue_bridge'):
            w = pixmap.width()
            h = pixmap.height()
            seed = gen_info.get('seed', 0) if isinstance(gen_info, dict) else 0
            self.vue_bridge.send_image(filepath, w, h, seed)

        # _xyz_info 주입
        if hasattr(self, '_pending_xyz_info') and self._pending_xyz_info:
            if isinstance(gen_info, dict):
                gen_info['_xyz_info'] = self._pending_xyz_info
            else:
                gen_info = {'_xyz_info': self._pending_xyz_info, '_raw': gen_info}
            self._pending_xyz_info = None
        self.generation_data[filepath] = gen_info
        
        from core.image_utils import exif_for_display
        self.exif_display.setPlainText(exif_for_display(gen_info))

        # 뷰어 정보 바 업데이트 (모던 UI)
        if hasattr(self, 'viewer_info_bar') and isinstance(gen_info, dict):
            w = gen_info.get('width', 0)
            h = gen_info.get('height', 0)
            seed = gen_info.get('seed', '')
            info_parts = []
            if w and h:
                info_parts.append(f"해상도 {w}×{h}")
            if seed:
                info_parts.append(f"시드 {seed}")
            if info_parts:
                self.viewer_info_bar.setText("  |  ".join(info_parts))
                self.viewer_info_bar.show()

        # XYZ Plot 결과 전달
        xyz_info = gen_info.get('_xyz_info') if isinstance(gen_info, dict) else None
        if not xyz_info and hasattr(self, 'generation_data'):
            # generation_data에서 _xyz_info 확인
            last_gen = self.generation_data.get(filepath)
            if isinstance(last_gen, dict):
                xyz_info = last_gen.get('_xyz_info')
        if xyz_info and hasattr(self, 'xyz_plot_tab'):
            self.xyz_plot_tab.add_result_image(filepath, xyz_info)

        self._create_thumbnail(filepath)
        self.add_image_to_gallery(filepath)
    
    def handle_immediate_generation(self, payload):
        """PNG Info에서 온 즉시 생성 요청"""
        self.center_tabs.setCurrentIndex(0)
        
        # ★★★ 먼저 alwayson_scripts 확인/생성 ★★★
        if "alwayson_scripts" not in payload:
            payload["alwayson_scripts"] = {}
        
        # NegPiP 적용
        if hasattr(self, 'negpip_group') and self.negpip_group.isChecked():
            payload["alwayson_scripts"]["NegPiP"] = {"args": [True]}

        self._apply_postprocess_chain(payload)
        
        selected_model = self.model_combo.currentText()
        
        _logger.info("Immediate Generation from EXIF")
        self.btn_generate.setText("생성 중...")
        self.btn_generate.setEnabled(False)
        self.viewer_label.setText("EXIF 설정으로 생성 중...")
        
        self._cleanup_gen_worker()
        self.gen_worker = GenerationFlowWorker(selected_model, payload)
        self.gen_worker.finished.connect(self.on_generation_finished)
        self.gen_worker.progress.connect(self._on_generation_progress)

        self.gen_progress_bar.setValue(0)
        self.gen_progress_bar.setRange(0, 100)
        self.gen_progress_bar.setFormat("생성 준비 중...")
        self.gen_progress_bar.show()

        self.gen_worker.start()

    def _build_adetailer_args(self):
        """활성화된 ADetailer 슬롯 args 생성"""
        args = [True, False]

        if self.ad_slot1_group.isChecked():
            args.append(self._build_adetailer_slot(self.s1_widgets))

        if self.ad_slot2_group.isChecked():
            args.append(self._build_adetailer_slot(self.s2_widgets))

        return args if len(args) > 2 else None

    def apply_alwayson_extensions(self, payload):
        """확장 전체(NegPiP + ADetailer + SAM3 + Anima)를 payload에 적용.

        t2i 뿐 아니라 **img2img / inpaint 경로에서도 쓰는 단일 진입점**이다.
        확장의 `show()`가 `AlwaysVisible`이라 img2img에서도 그대로 동작하므로,
        Forge Neo UI에서 i2i 탭에 SAM3/ADetailer 아코디언이 보이는 것과 결과가 같아진다.
        (CLAUDE.md '확장기능은 Forge Neo와 동일한 alwayson_scripts 방식' 원칙)

        예전에는 i2i/inpaint가 `"alwayson_scripts": {}`를 빈 채로 보내서
        같은 설정인데도 t2i와 결과가 달랐다.
        """
        if not isinstance(payload, dict):
            return payload
        payload.setdefault("alwayson_scripts", {})
        if hasattr(self, 'negpip_group') and self.negpip_group.isChecked():
            payload["alwayson_scripts"].setdefault("NegPiP", {"args": [True]})
        self._apply_postprocess_chain(payload)
        return payload

    def _apply_postprocess_chain(self, payload):
        """Forge Neo와 동일: ADetailer + SAM3 + Anima Guidance 모두 alwayson_scripts로 적용"""
        payload.setdefault("alwayson_scripts", {})

        # ADetailer: Forge Neo와 동일하게 alwayson_scripts로 직접 적용
        if self.adetailer_group.isChecked():
            adetailer_args = self._build_adetailer_args()
            if adetailer_args:
                payload["alwayson_scripts"]["ADetailer"] = {"args": adetailer_args}
                _logger.info("ADetailer alwayson_scripts 적용됨 (Forge Neo 방식)")

        # SAM3: Forge Neo와 동일하게 alwayson_scripts로 직접 적용.
        # state dict 구성은 core/sam3_args로 일원화 — 배치/Refine 경로와 동일 로직.
        sam3_group = getattr(self, "sam3_group", None)
        if sam3_group is not None and sam3_group.isChecked() and hasattr(self, "_build_sam3_settings"):
            sam3_settings = self._build_sam3_settings(payload)
            if sam3_settings:
                from core import sam3_args
                sam3_args.apply_to_payload(payload, sam3_settings)
                _logger.info("SAM3 alwayson_scripts 적용됨 (Forge Neo 방식)")

        # Anima Guidance Suite: PAG/SEG/SLG · APG/CWM/SMC · Skimmed CFG ·
        # DCW/DAVE/CNS · Modulation · Detail Daemon.
        # 전부 꺼져 있으면 아무것도 넣지 않는다 (확장을 건드리지 않아야 결과가 동일).
        try:
            from core import anima_guidance
            anima_settings = self._build_anima_settings()
            anima_guidance.apply_to_payload(payload, anima_settings)
            summary = anima_guidance.describe_active(anima_settings)
            if summary:
                _logger.info("Anima Guidance 적용됨: %s", summary)
        except Exception as e:
            # guidance는 부가 기능 — 실패해도 생성 자체는 진행되어야 한다
            _logger.warning("Anima Guidance 적용 실패 (무시하고 생성 진행): %s", e)

    def _build_adetailer_slot(self, widgets):
        """ADetailer 슬롯 딕셔너리 생성 (공식 REST API 스펙 준수)

        widgets dict에서 proxy를 통해 읽되,
        proxy 값이 비어있으면 bridge._proxies에서 직접 읽기를 시도한다.
        """
        _txt, _float, _int = _widget_text, _widget_float, _widget_int

        model_name = _txt(widgets['model'], 'face_yolov8n.pt')
        if model_name == 'None' or not model_name.strip():
            model_name = 'face_yolov8n.pt'

        confidence = _float(widgets['confidence'], 0.3)
        denoise = _float(widgets['denoise'], 0.4)
        mask_blur = _int(widgets['mask_blur'], 4)
        padding = _int(widgets['padding'], 32)
        prompt = widgets['prompt'].toPlainText() if hasattr(widgets['prompt'], 'toPlainText') else ''

        _logger.debug(f"AD Slot: model={model_name}, confidence={confidence}, "
                      f"denoise={denoise}, mask_blur={mask_blur}, prompt='{prompt[:30]}'")

        neg_prompt = widgets['neg_prompt'].toPlainText() if hasattr(widgets['neg_prompt'], 'toPlainText') else ''
        dilate_erode = _int(widgets.get('dilate_erode', type('', (), {'text': lambda s: '4'})()), 4) if 'dilate_erode' in widgets else 4
        mask_merge = _txt(widgets.get('mask_merge_invert', type('', (), {'text': lambda s: 'None', 'currentText': lambda s: 'None'})()), 'None') if 'mask_merge_invert' in widgets else 'None'

        slot = {
            "ad_model": model_name,
            "ad_model_classes": "",
            "ad_tab_enable": True,
            "ad_prompt": prompt,
            "ad_negative_prompt": neg_prompt,
            "ad_confidence": confidence,
            "ad_mask_filter_method": "Area",
            "ad_mask_k": 0,
            "ad_mask_min_ratio": 0.0,
            "ad_mask_max_ratio": 1.0,
            "ad_dilate_erode": dilate_erode,
            "ad_x_offset": 0,
            "ad_y_offset": 0,
            "ad_mask_merge_invert": mask_merge,
            "ad_mask_blur": mask_blur,
            "ad_denoising_strength": denoise,
            "ad_inpaint_only_masked": True,
            "ad_inpaint_only_masked_padding": padding,
            "ad_use_inpaint_width_height": widgets['use_inpaint_size_check'].isChecked(),
            "ad_inpaint_width": _int(widgets['inpaint_width'], 512),
            "ad_inpaint_height": _int(widgets['inpaint_height'], 512),
            "ad_use_steps": widgets['use_steps_check'].isChecked(),
            "ad_steps": _int(widgets['steps'], 28),
            "ad_use_cfg_scale": widgets['use_cfg_check'].isChecked(),
            "ad_cfg_scale": _float(widgets['cfg'], 7.0),
            "ad_use_checkpoint": widgets['use_checkpoint_check'].isChecked(),
            "ad_checkpoint": None,
            "ad_use_vae": widgets['use_vae_check'].isChecked(),
            "ad_vae": None,
            "ad_use_sampler": widgets['use_sampler_check'].isChecked(),
            "ad_sampler": "DPM++ 2M Karras",
            "ad_scheduler": "Use same scheduler",
            "ad_use_noise_multiplier": False,
            "ad_noise_multiplier": 1.0,
            "ad_use_clip_skip": False,
            "ad_clip_skip": 1,
            "ad_restore_face": False,
            "ad_controlnet_model": "None",
            "ad_controlnet_module": "None",
            "ad_controlnet_weight": 1.0,
            "ad_controlnet_guidance_start": 0.0,
            "ad_controlnet_guidance_end": 1.0,
        }
        # use_* 가 켜져있을 때만 값을 오버라이드
        if widgets['use_checkpoint_check'].isChecked():
            ckpt = _txt(widgets['checkpoint_combo'])
            if ckpt:
                slot["ad_checkpoint"] = ckpt
        if widgets['use_vae_check'].isChecked():
            vae = _txt(widgets['vae_combo'])
            if vae:
                slot["ad_vae"] = vae
        if widgets['use_sampler_check'].isChecked():
            slot["ad_sampler"] = _txt(widgets['sampler_combo'], "DPM++ 2M Karras")
            slot["ad_scheduler"] = _txt(widgets['scheduler_combo'], "Use same scheduler")

        return slot
    
    def _notify_generation_done(self):
        """생성 완료 알림 (비활성 창일 때)"""
        # 트레이 알림
        if hasattr(self, '_tray_manager'):
            self._tray_manager.notify("생성 완료", "이미지 생성이 완료되었습니다!")

        # 작업 표시줄 깜박임 (Windows)
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.FlashWindow(hwnd, True)
        except Exception:
            pass

        # 사운드 알림
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def _build_empty_adetailer_slot(self):
        """빈 ADetailer 슬롯"""
        return {
            "ad_cfg_scale": 7,
            "ad_checkpoint": "Use same checkpoint",
            "ad_clip_skip": 1,
            "ad_confidence": 0.3,
            "ad_controlnet_guidance_end": 1,
            "ad_controlnet_guidance_start": 0,
            "ad_controlnet_model": "None",
            "ad_controlnet_module": "None",
            "ad_controlnet_weight": 1,
            "ad_denoising_strength": 0.4,
            "ad_dilate_erode": 4,
            "ad_inpaint_height": 512,
            "ad_inpaint_only_masked": True,
            "ad_inpaint_only_masked_padding": 32,
            "ad_inpaint_width": 512,
            "ad_mask_blur": 4,
            "ad_mask_filter_method": "Area",
            "ad_mask_k": 0,
            "ad_mask_max_ratio": 1,
            "ad_mask_merge_invert": "None",
            "ad_mask_min_ratio": 0,
            "ad_model": "None",
            "ad_model_classes": "",
            "ad_negative_prompt": "",
            "ad_noise_multiplier": 1,
            "ad_prompt": "",
            "ad_restore_face": False,
            "ad_sampler": "DPM++ 2M",
            "ad_scheduler": "Use same scheduler",
            "ad_steps": 28,
            "ad_tab_enable": False,
            "ad_use_cfg_scale": False,
            "ad_use_checkpoint": False,
            "ad_use_clip_skip": False,
            "ad_use_inpaint_width_height": False,
            "ad_use_noise_multiplier": False,
            "ad_use_sampler": False,
            "ad_use_steps": False,
            "ad_use_vae": False,
            "ad_vae": "Use same VAE",
            "ad_x_offset": 0,
            "ad_y_offset": 0,
            "is_api": []
        }

    def _build_sam3_settings(self, payload):
        """SAM3 설정 딕셔너리 생성"""
        widgets = getattr(self, 'sam3_widgets', None)
        if not widgets:
            return None

        # SAM3 sampler/scheduler 결정 — 사용자 기대대로:
        # '별도 Sampler/Scheduler' 체크박스가 켜져있어도 콤보가 'Use same X'면
        # use_X=False로 강제하여 base의 ER SDE/Beta57 등이 상속되게.
        # Forge 확장 v0.6.0+는 sampler/scheduler 토글이 분리됨.
        _sampler_v = _widget_text(widgets['sampler'], 'Use same sampler')
        _scheduler_v = _widget_text(widgets['scheduler'], 'Use same scheduler')
        _use_sampler = (widgets['use_sampler_check'].isChecked()
                        and _sampler_v not in ('', 'Use same sampler'))
        _use_scheduler = (widgets['use_scheduler_check'].isChecked()
                          and _scheduler_v not in ('', 'Use same scheduler'))

        _txt, _float, _int = _widget_text, _widget_float, _widget_int

        def _plain(w):
            return w.toPlainText() if hasattr(w, 'toPlainText') else _txt(w, '')

        detect_prompt = _txt(widgets['detect_prompt'], 'face').strip() or 'face'
        return {
            "sam3_mode": _txt(widgets['mode'], 'Inpaint'),
            "sam3_mask_mode": _txt(widgets['mask_mode'], 'Individual'),
            "sam3_prompt": detect_prompt,
            "sam3_exclude_prompt": _plain(widgets['exclude_prompt']),
            "sam3_inpaint_prompt": _plain(widgets['inpaint_prompt']),
            "sam3_negative_prompt": _plain(widgets['neg_prompt']),
            "sam3_threshold": _float(widgets['threshold'], 0.4),
            "sam3_mask_dilation": _int(widgets['mask_dilation'], 0),
            "sam3_mask_hull": widgets['mask_hull'].isChecked(),
            "sam3_mask_outline_px": _int(widgets['mask_outline_px'], 0),
            "sam3_checkpoint": _txt(widgets['checkpoint'], 'sam3.pt'),
            "sam3_device": _txt(widgets['device'], 'cuda') or 'cuda',
            "sam3_mask_blur": _int(widgets['mask_blur'], 4),
            "sam3_denoising_strength": _float(widgets['denoise'], 0.4),
            "sam3_inpainting_fill": _txt(widgets['inpainting_fill'], 'original') or 'original',
            "sam3_inpaint_only_masked": widgets['inpaint_only_masked'].isChecked(),
            "sam3_inpaint_only_masked_padding": _int(widgets['padding'], 32),
            "sam3_use_inpaint_width_height": widgets['use_inpaint_size_check'].isChecked(),
            "sam3_inpaint_width": _int(widgets['inpaint_width'], 1024),
            "sam3_inpaint_height": _int(widgets['inpaint_height'], 1024),
            "sam3_use_steps": widgets['use_steps_check'].isChecked(),
            "sam3_steps": _int(widgets['steps'], 28),
            "sam3_use_cfg_scale": widgets['use_cfg_check'].isChecked(),
            "sam3_cfg_scale": _float(widgets['cfg'], 7.0),
            # sampler/scheduler 분리 — 위에서 계산한 _use_sampler / _use_scheduler
            "sam3_use_sampler": _use_sampler,
            "sam3_sampler": _sampler_v if _use_sampler else 'Use same sampler',
            "sam3_use_scheduler": _use_scheduler,
            "sam3_scheduler": _scheduler_v if _use_scheduler else 'Use same scheduler',
            "sam3_use_seed": widgets['use_seed_check'].isChecked(),
            "sam3_seed": _int(widgets['seed'], -1),
            "sam3_use_noise_multiplier": widgets['use_noise_multiplier_check'].isChecked(),
            "sam3_noise_multiplier": _float(widgets['noise_multiplier'], 1.0),
            "sam3_restore_face": widgets['restore_face'].isChecked(),
            "sam3_preview_overlay": widgets['preview_overlay'].isChecked(),
            "sam3_save_artifacts": widgets['save_artifacts'].isChecked(),
            # 검출 직후 SAM3(~3.5GB) VRAM 회수 — 16GB GPU 인페인트 OOM 방지.
            # UI 토글로 노출 (기본 ON). 끄면 인페인트 내내 상주 → 빠르지만 VRAM↑
            "sam3_unload_after": widgets['unload_after'].isChecked(),
            # ── ControlNet 주입 (확장의 SAM3 > ControlNet 아코디언)
            "sam3_cn_enable": widgets['cn_enable'].isChecked(),
            "sam3_cn_override_external": widgets['cn_override_external'].isChecked(),
            "sam3_cn_model": _txt(widgets['cn_model'], 'None') or 'None',
            "sam3_cn_module": _txt(widgets['cn_module'], 'inpaint_only') or 'inpaint_only',
            "sam3_cn_weight": _float(widgets['cn_weight'], 1.0),
            "sam3_cn_guidance_start": _float(widgets['cn_guidance_start'], 0.0),
            "sam3_cn_guidance_end": _float(widgets['cn_guidance_end'], 1.0),
            "sam3_cn_pixel_perfect": widgets['cn_pixel_perfect'].isChecked(),
            "sam3_cn_control_mode": _txt(widgets['cn_control_mode'], 'Balanced') or 'Balanced',
            "sam3_cn_resize_mode": (_txt(widgets['cn_resize_mode'], 'Crop and Resize')
                                    or 'Crop and Resize'),
            "sam3_cn_processor_res": _int(widgets['cn_processor_res'], 512),
            "sam3_cn_threshold_a": _float(widgets['cn_threshold_a'], -1.0),
            "sam3_cn_threshold_b": _float(widgets['cn_threshold_b'], -1.0),
        }

    def _build_anima_settings(self) -> dict:
        """Anima Guidance Suite 설정 dict — 프록시 값을 그대로 모은다.

        타입 강제/범위 클램프는 core/anima_guidance.build_args가 담당하므로
        여기서는 문자열 원본만 넘긴다 (변환을 두 군데서 하면 어긋난다).
        """
        widgets = getattr(self, 'anima_guidance_widgets', None) or {}
        return {key: _widget_text(proxy, '') for key, proxy in widgets.items()}

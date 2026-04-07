# ui/generator_generation.py
"""
이미지 생성 및 자동화 관련 로직
"""
import os
import time
import random
import json
from PIL import Image
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from config import OUTPUT_DIR
from workers.generation_worker import GenerationFlowWorker
from utils.file_wildcard import resolve_file_wildcards
from utils.wildcard import process_wildcards
from utils.app_logger import get_logger
from utils.theme_manager import get_theme_manager


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
    
    def start_generation(self):
        """이미지 생성 시작"""
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
        
        # 해상도 결정
        if self.random_res_check.isChecked() and self.random_resolutions:
            width, height, _ = random.choice(self.random_resolutions)
            self.width_input.setText(str(width))
            self.height_input.setText(str(height))
        else:
            width, height = (
                int(self.width_input.text()), 
                int(self.height_input.text())
            )
        
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

        # LoRA 패널 활성 항목 합침
        if hasattr(self, 'lora_active_panel'):
            lora_text = self.lora_active_panel.get_active_lora_text()
            if lora_text:
                final_prompt = f"{final_prompt}, {lora_text}" if final_prompt else lora_text

        # Payload 생성
        payload = {
            "prompt": final_prompt,
            "negative_prompt": combined_neg_prompt,
            "sampler_name": self.sampler_combo.currentText(), 
            "scheduler": self.scheduler_combo.currentText(),
            "steps": int(self.steps_input.text()), 
            "cfg_scale": float(self.cfg_input.text()),
            "seed": int(self.seed_input.text()), 
            "width": width, 
            "height": height,
            "send_images": True,
            "save_images": True,
            "alwayson_scripts": {}
        }

        # Hires.fix
        if self.hires_options_group.isChecked():
            hr_payload = {
                "enable_hr": True,
                "hr_upscaler": self.upscaler_combo.currentText(),
                "hr_second_pass_steps": int(self.hires_steps_input.text()),
                "denoising_strength": float(self.hires_denoising_input.text()),
                "hr_scale": float(self.hires_scale_input.text()),
                "hr_additional_modules": [],
            }
            hr_cfg = float(self.hires_cfg_input.text())
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

        # ADetailer
        if self.adetailer_group.isChecked():
            adetailer_args = [True, False]
            
            if self.ad_slot1_group.isChecked():
                adetailer_args.append(self._build_adetailer_slot(self.s1_widgets, True))
            else:
                adetailer_args.append(self._build_empty_adetailer_slot())
            
            if self.ad_slot2_group.isChecked():
                adetailer_args.append(self._build_adetailer_slot(self.s2_widgets, True))
            else:
                adetailer_args.append(self._build_empty_adetailer_slot())
            
            for _ in range(4):
                adetailer_args.append(self._build_empty_adetailer_slot())
            
            payload["alwayson_scripts"]["ADetailer"] = {"args": adetailer_args}
            
            _logger.info("ADetailer 적용됨")

        _logger.info("Sending Payload to WebUI API")
        _logger.debug(f"프롬프트: {payload['prompt'][:100]}...")
        
        selected_model = self.model_combo.currentText()
        self.gen_worker = GenerationFlowWorker(selected_model, payload)
        self.gen_worker.finished.connect(self.on_generation_finished)
        self.gen_worker.progress.connect(self._on_generation_progress)

        # 프로그레스 바 초기화
        self.gen_progress_bar.setValue(0)
        self.gen_progress_bar.setRange(0, 100)
        self.gen_progress_bar.setFormat("생성 준비 중...")
        self.gen_progress_bar.show()

        self.gen_worker.start()

    def _on_generation_progress(self, step: int, total: int, preview):
        """생성 진행률 업데이트"""
        if total <= 0:
            return

        self.gen_progress_bar.setRange(0, total)
        self.gen_progress_bar.setValue(step)
        self.gen_progress_bar.setFormat(f"{step} / {total} steps")

        pct = int(step / total * 100)
        self.setWindowTitle(f"AI Studio - Pro [{step}/{total} steps · {pct}%]")
        self.viewer_label.setText(
            f"🎨 이미지 생성 중...\n\n"
            f"{step} / {total} steps ({pct}%)"
        )
        self.show_status(f"🎨 생성 중... {step}/{total} steps ({pct}%)")

        # Vue에 진행률 전달
        if hasattr(self, 'vue_bridge'):
            self.vue_bridge.generationProgress.emit(step, total)

    def on_generation_finished(self, result, gen_info):
        """생성 완료 처리"""
        # 버튼 복구 (자동화 모드에 따라 다르게)
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

        # 타이틀 복구
        self.setWindowTitle("AI Studio - Pro")

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
        
        if isinstance(result, bytes):
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
            self.viewer_label.setText(f"❌ 생성 실패\n\n{result}")
            self.show_status(f"❌ 생성 실패: {result}", 5000)
        
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
        
        # ADetailer 적용
        if self.adetailer_group.isChecked():
            adetailer_args = [True, False]
            
            if self.ad_slot1_group.isChecked():
                adetailer_args.append(self._build_adetailer_slot(self.s1_widgets, True))
            else:
                adetailer_args.append(self._build_empty_adetailer_slot())
            
            if self.ad_slot2_group.isChecked():
                adetailer_args.append(self._build_adetailer_slot(self.s2_widgets, True))
            else:
                adetailer_args.append(self._build_empty_adetailer_slot())
            
            for _ in range(4):
                adetailer_args.append(self._build_empty_adetailer_slot())
            
            payload["alwayson_scripts"]["ADetailer"] = {"args": adetailer_args}
        
        selected_model = self.model_combo.currentText()
        
        _logger.info("Immediate Generation from EXIF")
        self.btn_generate.setText("생성 중...")
        self.btn_generate.setEnabled(False)
        self.viewer_label.setText("EXIF 설정으로 생성 중...")
        
        self.gen_worker = GenerationFlowWorker(selected_model, payload)
        self.gen_worker.finished.connect(self.on_generation_finished)
        self.gen_worker.progress.connect(self._on_generation_progress)

        self.gen_progress_bar.setValue(0)
        self.gen_progress_bar.setRange(0, 100)
        self.gen_progress_bar.setFormat("생성 준비 중...")
        self.gen_progress_bar.show()

        self.gen_worker.start()

    def _build_adetailer_slot(self, widgets, is_enabled=True):
        """ADetailer 슬롯 딕셔너리 생성"""
        return {
            "ad_cfg_scale": float(widgets['cfg'].text()) if widgets['use_cfg_check'].isChecked() else 7,
            "ad_checkpoint": widgets['checkpoint_combo'].currentText() if widgets['use_checkpoint_check'].isChecked() else "Use same checkpoint",
            "ad_clip_skip": 1,
            "ad_confidence": float(widgets['confidence'].text()),
            "ad_controlnet_guidance_end": 1,
            "ad_controlnet_guidance_start": 0,
            "ad_controlnet_model": "None",
            "ad_controlnet_module": "None",
            "ad_controlnet_weight": 1,
            "ad_denoising_strength": float(widgets['denoise'].text()),
            "ad_dilate_erode": 4,
            "ad_inpaint_height": int(widgets['inpaint_height'].text()) if widgets['use_inpaint_size_check'].isChecked() else 512,
            "ad_inpaint_only_masked": True,
            "ad_inpaint_only_masked_padding": int(widgets['padding'].text()),
            "ad_inpaint_width": int(widgets['inpaint_width'].text()) if widgets['use_inpaint_size_check'].isChecked() else 512,
            "ad_mask_blur": int(widgets['mask_blur'].text()),
            "ad_mask_filter_method": "Area",
            "ad_mask_k": 0,
            "ad_mask_max_ratio": 1,
            "ad_mask_merge_invert": "None",
            "ad_mask_min_ratio": 0,
            "ad_model": widgets['model'].text() if is_enabled else "None",
            "ad_model_classes": "",
            "ad_negative_prompt": "",
            "ad_noise_multiplier": 1,
            "ad_prompt": widgets['prompt'].toPlainText(),
            "ad_restore_face": False,
            "ad_sampler": widgets['sampler_combo'].currentText() if widgets['use_sampler_check'].isChecked() else "Use same sampler",
            "ad_scheduler": widgets['scheduler_combo'].currentText() if widgets['use_sampler_check'].isChecked() else "Use same scheduler",
            "ad_steps": int(widgets['steps'].text()) if widgets['use_steps_check'].isChecked() else 28,
            "ad_tab_enable": is_enabled,
            "ad_use_cfg_scale": widgets['use_cfg_check'].isChecked(),
            "ad_use_checkpoint": widgets['use_checkpoint_check'].isChecked(),
            "ad_use_clip_skip": False,
            "ad_use_inpaint_width_height": widgets['use_inpaint_size_check'].isChecked(),
            "ad_use_noise_multiplier": False,
            "ad_use_sampler": widgets['use_sampler_check'].isChecked(),
            "ad_use_steps": widgets['use_steps_check'].isChecked(),
            "ad_use_vae": widgets['use_vae_check'].isChecked(),
            "ad_vae": widgets['vae_combo'].currentText() if widgets['use_vae_check'].isChecked() else "Use same VAE",
            "ad_x_offset": 0,
            "ad_y_offset": 0,
            "is_api": []
        }
    
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
# workers/upscale_worker.py
import os
import base64
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from config import WEBUI_API_URL

_HEADERS = {"accept": "application/json", "Content-Type": "application/json"}
_TIMEOUT = 600


def _build_empty_adetailer_slot() -> dict:
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


def _build_adetailer_slot(model: str, confidence: float, denoise: float, prompt: str) -> dict:
    """ADetailer 슬롯 딕셔너리 생성"""
    slot = _build_empty_adetailer_slot()
    slot.update({
        "ad_model": model,
        "ad_confidence": confidence,
        "ad_denoising_strength": denoise,
        "ad_prompt": prompt,
        "ad_tab_enable": True,
    })
    return slot


def _image_to_base64(image_path: str) -> str:
    """이미지 파일을 base64 문자열로 변환"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _save_base64_image(b64_data: str, output_path: str):
    """base64 데이터를 이미지 파일로 저장"""
    img_bytes = base64.b64decode(b64_data)
    with open(output_path, "wb") as f:
        f.write(img_bytes)


class BatchUpscaleWorker(QThread):
    """배치 업스케일/ADetailer 워커"""
    single_finished = pyqtSignal(int, bool, str)  # index, success, message
    all_finished = pyqtSignal()
    progress = pyqtSignal(int, int)  # current, total

    def __init__(self, image_paths: list, settings: dict):
        """
        settings = {
            'mode': 'upscale_only' | 'adetailer_only' | 'both',
            'upscaler_name': str,
            'scale_mode': 'factor' | 'size',
            'scale_factor': float,
            'target_width': int,
            'target_height': int,
            'ad_model': str,
            'ad_confidence': float,
            'ad_denoise': float,
            'ad_prompt': str,
            'output_folder': str,
        }
        """
        super().__init__()
        self.image_paths = image_paths
        self.settings = settings
        self._stop_requested = False

    def run(self):
        """배치 처리 실행"""
        total = len(self.image_paths)

        for i, path in enumerate(self.image_paths):
            if self._stop_requested:
                break

            self.progress.emit(i, total)
            try:
                b64_image = _image_to_base64(path)
                result_b64 = b64_image
                mode = self.settings['mode']

                # 업스케일
                if mode in ('upscale_only', 'both'):
                    result_b64 = self._do_upscale(result_b64)

                # ADetailer
                if mode in ('adetailer_only', 'both'):
                    result_b64 = self._do_adetailer(result_b64)

                # 저장
                output_folder = self.settings['output_folder']
                basename = os.path.splitext(os.path.basename(path))[0]
                suffix = "_upscaled" if mode == 'upscale_only' else "_ad" if mode == 'adetailer_only' else "_upscaled_ad"
                output_path = os.path.join(output_folder, f"{basename}{suffix}.png")
                _save_base64_image(result_b64, output_path)

                self.single_finished.emit(i, True, os.path.basename(output_path))

            except Exception as e:
                self.single_finished.emit(i, False, str(e))

        self.progress.emit(total, total)
        self.all_finished.emit()

    def request_stop(self):
        """처리 중지 요청"""
        self._stop_requested = True

    def _do_upscale(self, b64_image: str) -> str:
        """extra-single-image API로 업스케일"""
        payload = {
            "image": b64_image,
            "resize_mode": 0 if self.settings['scale_mode'] == 'factor' else 1,
            "upscaling_resize": self.settings.get('scale_factor', 2),
            "upscaling_resize_w": self.settings.get('target_width', 1024),
            "upscaling_resize_h": self.settings.get('target_height', 1024),
            "upscaler_1": self.settings['upscaler_name'],
        }

        response = requests.post(
            f'{WEBUI_API_URL}/sdapi/v1/extra-single-image',
            json=payload, headers=_HEADERS, timeout=_TIMEOUT
        )
        response.raise_for_status()
        r = response.json()

        if 'image' in r and r['image']:
            return r['image']
        raise RuntimeError("업스케일 API 응답에 이미지가 없습니다.")

    def _do_adetailer(self, b64_image: str) -> str:
        """img2img + ADetailer로 디테일 보정"""
        ad_slot = _build_adetailer_slot(
            model=self.settings.get('ad_model', 'face_yolov8s.pt'),
            confidence=self.settings.get('ad_confidence', 0.3),
            denoise=self.settings.get('ad_denoise', 0.25),
            prompt=self.settings.get('ad_prompt', ''),
        )
        empty_slots = [_build_empty_adetailer_slot() for _ in range(5)]

        payload = {
            "init_images": [b64_image],
            "denoising_strength": 0.1,
            "width": -1,
            "height": -1,
            "resize_mode": 0,
            "prompt": self.settings.get('ad_prompt', ''),
            "negative_prompt": "",
            "sampler_name": "DPM++ 2M",
            "steps": 20,
            "cfg_scale": 7,
            "send_images": True,
            "save_images": False,
            "alwayson_scripts": {
                "ADetailer": {
                    "args": [True, False, ad_slot] + empty_slots
                }
            }
        }

        response = requests.post(
            f'{WEBUI_API_URL}/sdapi/v1/img2img',
            json=payload, headers=_HEADERS, timeout=_TIMEOUT
        )
        response.raise_for_status()
        r = response.json()

        if 'images' in r and r['images']:
            return r['images'][0]
        raise RuntimeError("ADetailer API 응답에 이미지가 없습니다.")

# backends/webui_backend.py
"""WebUI (A1111/Forge) 백엔드 구현"""
import base64
import json
import threading
import time
import requests
from typing import Dict, Optional

from backends.base import (
    AbstractBackend, BackendInfo, GenerationResult, ProgressCallback
)

_HEADERS = {"accept": "application/json", "Content-Type": "application/json"}


class WebUIBackend(AbstractBackend):
    """Stable Diffusion WebUI API 백엔드"""

    def get_backend_type(self) -> str:
        return "webui"

    def test_connection(self) -> bool:
        """WebUI 연결 상태 확인"""
        try:
            r = requests.get(
                f'{self.api_url}/sdapi/v1/options',
                timeout=3
            )
            r.raise_for_status()
            return True
        except Exception:
            return False

    def get_info(self) -> BackendInfo:
        """WebUI API에서 모델, 샘플러 등 정보 가져오기"""
        headers = {"accept": "application/json"}
        timeout = 5
        info = BackendInfo()

        # 모델 목록 (필수)
        res = requests.get(
            f'{self.api_url}/sdapi/v1/sd-models',
            headers=headers, timeout=timeout
        )
        res.raise_for_status()
        sd_models = res.json()
        if isinstance(sd_models, list):
            info.models = [m.get('title', '') for m in sd_models]
            info.checkpoints = ["Use same checkpoint"] + [
                m.get('model_name', '') for m in sd_models
            ]

        # 샘플러
        try:
            r = requests.get(
                f'{self.api_url}/sdapi/v1/samplers',
                headers=headers, timeout=timeout
            ).json()
            info.samplers = [s.get('name', '') for s in r] if isinstance(r, list) else []
        except Exception:
            pass

        # 스케줄러
        try:
            r = requests.get(
                f'{self.api_url}/sdapi/v1/schedulers',
                headers=headers, timeout=timeout
            ).json()
            info.schedulers = (
                [s.get('name', '') for s in r] if isinstance(r, list) else ["Automatic"]
            )
        except Exception:
            pass

        # 업스케일러
        try:
            r = requests.get(
                f'{self.api_url}/sdapi/v1/upscalers',
                headers=headers, timeout=timeout
            ).json()
            info.upscalers = [u.get('name', '') for u in r] if isinstance(r, list) else []
        except Exception:
            pass

        # VAE
        try:
            r = requests.get(
                f'{self.api_url}/sdapi/v1/sd-vae',
                headers=headers, timeout=timeout
            ).json()
            if isinstance(r, list):
                info.vae = ["Use same VAE"] + [v.get('model_name', '') for v in r]
        except Exception:
            pass

        # 옵션
        try:
            info.options = requests.get(
                f'{self.api_url}/sdapi/v1/options',
                headers=headers, timeout=timeout
            ).json()
        except Exception:
            pass

        return info

    def _switch_model_if_needed(self, model_name: str):
        """필요 시 모델 전환"""
        if not model_name:
            return
        current_options = requests.get(
            url=f'{self.api_url}/sdapi/v1/options',
            headers=_HEADERS, timeout=10
        ).json()

        if current_options.get('sd_model_checkpoint') != model_name:
            requests.post(
                url=f'{self.api_url}/sdapi/v1/options',
                json={'sd_model_checkpoint': model_name},
                headers=_HEADERS, timeout=60
            )

    def _start_progress_polling(self, callback: Optional[ProgressCallback],
                                stop_event: threading.Event):
        """별도 스레드에서 /sdapi/v1/progress 폴링"""
        if callback is None:
            return
        while not stop_event.is_set():
            try:
                r = requests.get(
                    f'{self.api_url}/sdapi/v1/progress',
                    timeout=3
                ).json()
                step = r.get('state', {}).get('sampling_step', 0)
                total = r.get('state', {}).get('sampling_steps', 0)
                progress_val = r.get('progress', 0)
                if total > 0:
                    callback(step, total, None)
                elif progress_val > 0:
                    callback(int(progress_val * 100), 100, None)
            except Exception:
                pass
            stop_event.wait(0.5)

    def _generate(self, endpoint: str, model_name: str, payload: Dict,
                  progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """txt2img / img2img 공통 생성 로직"""
        try:
            self._switch_model_if_needed(model_name)

            # 진행률 폴링 시작
            stop_event = threading.Event()
            if progress_callback:
                poll_thread = threading.Thread(
                    target=self._start_progress_polling,
                    args=(progress_callback, stop_event),
                    daemon=True
                )
                poll_thread.start()

            try:
                response = requests.post(
                    url=f'{self.api_url}{endpoint}',
                    json=payload, headers=_HEADERS, timeout=600
                )
                response.raise_for_status()
            finally:
                stop_event.set()

            r = response.json()
            if 'images' in r and r['images']:
                image_data = base64.b64decode(r['images'][0])
                generation_info = json.loads(r.get('info', '{}'))
                return GenerationResult(
                    success=True,
                    image_data=image_data,
                    info=generation_info
                )
            else:
                return GenerationResult(
                    success=False,
                    error=f"API 응답에 이미지가 없습니다: {r.get('detail', '알 수 없는 오류')}"
                )

        except requests.exceptions.RequestException as e:
            return GenerationResult(success=False, error=f"API 요청 실패: {e}")
        except Exception as e:
            return GenerationResult(success=False, error=f"생성 중 오류: {e}")

    def txt2img(self, model_name: str, payload: Dict,
                progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """텍스트→이미지 생성"""
        return self._generate('/sdapi/v1/txt2img', model_name, payload, progress_callback)

    def img2img(self, model_name: str, payload: Dict,
                progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """이미지→이미지 생성"""
        return self._generate('/sdapi/v1/img2img', model_name, payload, progress_callback)

    def upscale(self, image_b64: str, settings: Dict) -> str:
        """extra-single-image API로 업스케일"""
        payload = {
            "image": image_b64,
            "resize_mode": 0 if settings.get('scale_mode') == 'factor' else 1,
            "upscaling_resize": settings.get('scale_factor', 2),
            "upscaling_resize_w": settings.get('target_width', 1024),
            "upscaling_resize_h": settings.get('target_height', 1024),
            "upscaler_1": settings.get('upscaler_name', 'Lanczos'),
        }
        response = requests.post(
            f'{self.api_url}/sdapi/v1/extra-single-image',
            json=payload, headers=_HEADERS, timeout=600
        )
        response.raise_for_status()
        r = response.json()
        if 'image' in r and r['image']:
            return r['image']
        raise RuntimeError("업스케일 API 응답에 이미지가 없습니다.")

    def adetailer(self, image_b64: str, settings: Dict) -> str:
        """img2img + ADetailer로 디테일 보정"""
        from workers.upscale_worker import _build_adetailer_slot, _build_empty_adetailer_slot

        ad_slot = _build_adetailer_slot(
            model=settings.get('ad_model', 'face_yolov8s.pt'),
            confidence=settings.get('ad_confidence', 0.3),
            denoise=settings.get('ad_denoise', 0.25),
            prompt=settings.get('ad_prompt', ''),
        )
        empty_slots = [_build_empty_adetailer_slot() for _ in range(5)]

        payload = {
            "init_images": [image_b64],
            "denoising_strength": 0.1,
            "width": -1,
            "height": -1,
            "resize_mode": 0,
            "prompt": settings.get('ad_prompt', ''),
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
            f'{self.api_url}/sdapi/v1/img2img',
            json=payload, headers=_HEADERS, timeout=600
        )
        response.raise_for_status()
        r = response.json()
        if 'images' in r and r['images']:
            return r['images'][0]
        raise RuntimeError("ADetailer API 응답에 이미지가 없습니다.")

# backends/webui_backend.py
"""WebUI (A1111/Forge) 백엔드 구현"""
import base64
import copy
import io
import json
import logging
import threading
import time
import requests
from typing import Dict, Optional
from PIL import Image

from backends.base import (
    AbstractBackend, BackendInfo, GenerationResult, ProgressCallback
)
from core.http_retry import get_with_retry

logger = logging.getLogger(__name__)

_HEADERS = {"accept": "application/json", "Content-Type": "application/json"}


class WebUIBackend(AbstractBackend):
    """Stable Diffusion WebUI API 백엔드"""

    @staticmethod
    def _build_postprocess_payload(image_b64: str, settings: Dict, *, prompt: str, negative_prompt: str) -> Dict:
        base_payload = copy.deepcopy(settings.get('_postprocess_base_payload', {}))
        passthrough_scripts = copy.deepcopy(base_payload.pop('alwayson_scripts', {}))
        for key in (
            "images",
            "image",
            "mask",
            "mask_blur",
            "init_images",
            "include_init_images",
            "infotext",
            "enable_hr",
            "hr_upscaler",
            "hr_second_pass_steps",
            "hr_scale",
            "hr_cfg",
            "hr_additional_modules",
            "hr_checkpoint_name",
            "hr_sampler_name",
            "hr_scheduler",
            "hr_prompt",
            "hr_negative_prompt",
        ):
            base_payload.pop(key, None)

        image_bytes = base64.b64decode(image_b64)
        with Image.open(io.BytesIO(image_bytes)) as init_image:
            init_width, init_height = init_image.size

        payload = base_payload
        payload.update({
            "init_images": [image_b64],
            "resize_mode": int(payload.get("resize_mode", 0)),
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "send_images": True,
            "save_images": False,
            "width": init_width,
            "height": init_height,
        })
        payload.setdefault("denoising_strength", float(settings.get('denoising_strength', payload.get('denoising_strength', 0.1))))
        payload["alwayson_scripts"] = passthrough_scripts
        return payload

    @staticmethod
    def _build_sam3_script_state(settings: Dict) -> Dict:
        detect_prompt = str(settings.get('sam3_prompt', 'face') or 'face').strip() or 'face'
        return {
            "sam3_enable": True,
            "enabled": True,
            "sam3_mode": settings.get('sam3_mode', 'Inpaint'),
            "sam3_mask_mode": settings.get('sam3_mask_mode', 'Individual'),
            "sam3_prompt": detect_prompt,
            "sam3_exclude_prompt": settings.get('sam3_exclude_prompt', ''),
            "sam3_inpaint_prompt": settings.get('sam3_inpaint_prompt', settings.get('prompt', '')),
            "sam3_negative_prompt": settings.get('sam3_negative_prompt', settings.get('negative_prompt', '')),
            "sam3_threshold": float(settings.get('sam3_threshold', 0.4)),
            "sam3_mask_dilation": int(settings.get('sam3_mask_dilation', 0)),
            "sam3_mask_hull": bool(settings.get('sam3_mask_hull', False)),
            "sam3_mask_outline_px": int(settings.get('sam3_mask_outline_px', 0)),
            "sam3_checkpoint": settings.get('sam3_checkpoint', 'sam3.pt'),
            "sam3_device": settings.get('sam3_device', 'cuda'),
            "sam3_mask_blur": int(settings.get('sam3_mask_blur', 4)),
            "sam3_denoising_strength": float(settings.get('sam3_denoising_strength', settings.get('denoising_strength', 0.4))),
            "sam3_inpainting_fill": settings.get('sam3_inpainting_fill', 'original'),
            "sam3_inpaint_only_masked": bool(settings.get('sam3_inpaint_only_masked', True)),
            "sam3_inpaint_only_masked_padding": int(settings.get('sam3_inpaint_only_masked_padding', 32)),
            "sam3_use_inpaint_width_height": bool(settings.get('sam3_use_inpaint_width_height', False)),
            "sam3_inpaint_width": int(settings.get('sam3_inpaint_width', 512)),
            "sam3_inpaint_height": int(settings.get('sam3_inpaint_height', 512)),
            "sam3_use_steps": bool(settings.get('sam3_use_steps', False)),
            "sam3_steps": int(settings.get('sam3_steps', 28)),
            "sam3_use_cfg_scale": bool(settings.get('sam3_use_cfg_scale', False)),
            "sam3_cfg_scale": float(settings.get('sam3_cfg_scale', 7.0)),
            "sam3_use_sampler": bool(settings.get('sam3_use_sampler', False)),
            "sam3_sampler": settings.get('sam3_sampler', 'Use same sampler'),
            "sam3_use_scheduler": bool(settings.get('sam3_use_scheduler', False)),
            "sam3_scheduler": settings.get('sam3_scheduler', 'Use same scheduler'),
            "sam3_use_seed": bool(settings.get('sam3_use_seed', False)),
            "sam3_seed": int(settings.get('sam3_seed', -1)),
            "sam3_use_noise_multiplier": bool(settings.get('sam3_use_noise_multiplier', False)),
            "sam3_noise_multiplier": float(settings.get('sam3_noise_multiplier', 1.0)),
            "sam3_restore_face": bool(settings.get('sam3_restore_face', False)),
            "sam3_preview_overlay": bool(settings.get('sam3_preview_overlay', False)),
            "sam3_save_artifacts": bool(settings.get('sam3_save_artifacts', True)),
            # ★ 핵심: 검출 직후 SAM3(~3.5GB)를 VRAM에서 내림.
            # sam-extra UI 기본값은 True지만 API 경로 _xyz_or("sam3_unload_after", False)
            # 라서 우리가 명시 안 보내면 False로 처리 → 인페인트 내내 SAM3 상주 →
            # ANIMA(~8GB)+SAM3(3.5GB)+Forge(~3GB) > 16GB → OOM/lowvram.
            # 한 사이클 내 재로딩 0회, 다음 검출 때만 ~3-5s 추가.
            "sam3_unload_after": bool(settings.get('sam3_unload_after', True)),
        }

    def _run_img2img_postprocess(self, image_b64: str, payload: Dict) -> str:
        response = requests.post(
            f'{self.api_url}/sdapi/v1/img2img',
            json=payload, headers=_HEADERS, timeout=600
        )
        response.raise_for_status()
        r = response.json()
        if 'images' in r and r['images']:
            return r['images'][-1]
        raise RuntimeError("img2img 후처리 API 응답에 이미지가 없습니다.")

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
        from concurrent.futures import ThreadPoolExecutor, as_completed
        headers = {"accept": "application/json"}
        timeout = 5
        info = BackendInfo()

        # 모델 목록 (필수 - 재시도 포함 동기 호출)
        res = get_with_retry(
            f'{self.api_url}/sdapi/v1/sd-models',
            headers=headers, timeout=timeout, retries=3,
        )
        res.raise_for_status()
        sd_models = res.json()
        if isinstance(sd_models, list):
            info.models = [m.get('title', '') for m in sd_models]
            info.checkpoints = ["Use same checkpoint"] + [
                m.get('model_name', '') for m in sd_models
            ]

        def _fetch(endpoint):
            return get_with_retry(
                f'{self.api_url}{endpoint}',
                headers=headers, timeout=timeout, retries=2,
            ).json()

        # 나머지 5개 병렬 호출
        tasks = {
            'samplers': '/sdapi/v1/samplers',
            'schedulers': '/sdapi/v1/schedulers',
            'upscalers': '/sdapi/v1/upscalers',
            'vae': '/sdapi/v1/sd-vae',
            'options': '/sdapi/v1/options',
        }

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_fetch, ep): name for name, ep in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    r = future.result()
                    if name == 'samplers' and isinstance(r, list):
                        info.samplers = [s.get('name', '') for s in r]
                    elif name == 'schedulers' and isinstance(r, list):
                        info.schedulers = [s.get('name', '') for s in r] or ["Automatic"]
                    elif name == 'upscalers' and isinstance(r, list):
                        info.upscalers = [u.get('name', '') for u in r]
                    elif name == 'vae' and isinstance(r, list):
                        info.vae = ["Use same VAE"] + [v.get('model_name', '') for v in r]
                    elif name == 'options':
                        info.options = r
                except Exception as e:
                    logger.warning("get_info endpoint '%s' failed: %s", name, e)

        return info

    def get_system_stats(self) -> dict:
        """GPU/VRAM 상태 조회"""
        try:
            r = requests.get(f'{self.api_url}/sdapi/v1/memory', timeout=3)
            if r.status_code == 200:
                data = r.json()
                cuda = data.get('cuda', {})
                sys_info = cuda.get('system', {})
                return {
                    'vram_used': sys_info.get('used', 0),
                    'vram_total': sys_info.get('total', 0),
                    'vram_free': sys_info.get('free', 0),
                }
        except Exception as e:
            logger.warning("get_system_stats failed: %s", e)
        return {}

    def get_loras(self) -> list:
        """WebUI LoRA 목록 반환 (트리거 워드 포함)"""
        try:
            r = requests.get(
                f'{self.api_url}/sdapi/v1/loras',
                headers=_HEADERS, timeout=10
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                result = []
                for item in data:
                    lora = {
                        'name': item.get('name', ''),
                        'alias': item.get('alias', item.get('name', '')),
                        'path': item.get('path', ''),
                        'trigger_words': [],
                    }
                    metadata = item.get('metadata', {})
                    if metadata:
                        # Method 1: activation text (CivitAI / user-defined)
                        act_text = (metadata.get('activation text', '')
                                    or metadata.get('ss_activation_text', ''))
                        if act_text:
                            lora['trigger_words'] = [
                                t.strip() for t in act_text.split(',') if t.strip()
                            ][:8]
                        # Method 2: ss_tag_frequency (trained tags — fallback)
                        if not lora['trigger_words']:
                            tag_freq = metadata.get('ss_tag_frequency', {})
                            if isinstance(tag_freq, str):
                                try:
                                    import json as _json
                                    tag_freq = _json.loads(tag_freq)
                                except Exception:
                                    tag_freq = {}
                            if isinstance(tag_freq, dict):
                                all_tags = {}
                                for ds_tags in tag_freq.values():
                                    if isinstance(ds_tags, dict):
                                        all_tags.update(ds_tags)
                                if all_tags:
                                    sorted_tags = sorted(
                                        all_tags.items(),
                                        key=lambda x: x[1], reverse=True
                                    )
                                    lora['trigger_words'] = [
                                        t[0] for t in sorted_tags[:5]
                                    ]
                    result.append(lora)
                return result
        except Exception as e:
            logger.warning("get_loras failed: %s", e)
        return []

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

    def cleanup_models(self, full_reload: bool = False) -> bool:
        """LoRA patches + 캐시 정리.
        Forge/A1111의 API 호출 누적으로 patches가 쌓일 때 호출.

        :param full_reload: True면 checkpoint unload+reload (확실하지만 느림 ~10s)
                            False면 LoRA 리프레시만 (빠르지만 patches 일부 남을 수도)
        :return: 성공 여부
        """
        try:
            if full_reload:
                # 가장 확실한 cleanup — checkpoint unload → 다음 generation 시 자동 reload
                # patches 완전 초기화, VRAM 회수
                try:
                    requests.post(
                        url=f'{self.api_url}/sdapi/v1/unload-checkpoint',
                        headers=_HEADERS, timeout=30
                    )
                    logger.info("[cleanup] checkpoint unloaded — fresh state on next gen")
                except requests.exceptions.RequestException:
                    pass  # 엔드포인트 없는 버전 — 무시
            # LoRA 캐시 리프레시 (가벼움)
            try:
                requests.post(
                    url=f'{self.api_url}/sdapi/v1/refresh-loras',
                    headers=_HEADERS, timeout=20
                )
            except requests.exceptions.RequestException:
                pass
            # Forge: gc/cache clear 트리거 (있다면)
            try:
                requests.post(
                    url=f'{self.api_url}/sdapi/v1/options',
                    json={'memmon_poll_rate': 8},  # no-op 같은 옵션 set로 forge gc 유발
                    headers=_HEADERS, timeout=10
                )
            except requests.exceptions.RequestException:
                pass
            return True
        except Exception as e:
            logger.warning("cleanup_models failed: %s", e)
            return False

    # 기존 코드와의 호환 — D6에서 vram-bar 클릭 핸들러가 unload_models() 찾음
    def unload_models(self):
        return self.cleanup_models(full_reload=True)

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
            except Exception as e:
                # 진행률 폴링은 반복 호출 — 노이즈 방지 위해 debug 로그만
                logger.debug("progress poll failed: %s", e)
            stop_event.wait(0.5)

    def _generate(self, endpoint: str, model_name: str, payload: Dict,
                  progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """txt2img / img2img 공통 생성 로직"""
        try:
            self._switch_model_if_needed(model_name)

            # NOTE: 이전에 SAM3+LoRA 감지 시 사전 unload-checkpoint 호출 했었음.
            # 그러나 sam3_unload_after=True 추가로 sam-extra가 검출 후 알아서
            # 정리하므로 사전 unload는 불필요 + 메모리 단편화로 가용 VRAM
            # 4GB 정도 손실시킴 (사용자 로그 비교로 확인). 제거.

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
        adetailer_args = settings.get('adetailer_args')
        if not adetailer_args:
            from workers.upscale_worker import _build_adetailer_slot

            ad_slot = _build_adetailer_slot(
                model=settings.get('ad_model', 'face_yolov8s.pt'),
                confidence=settings.get('ad_confidence', 0.3),
                denoise=settings.get('ad_denoise', 0.25),
                prompt=settings.get('ad_prompt', ''),
            )
            if settings.get('ad_negative'):
                ad_slot['ad_negative_prompt'] = settings['ad_negative']
            adetailer_args = [True, False, ad_slot]

        payload = self._build_postprocess_payload(
            image_b64,
            settings,
            prompt=settings.get('ad_prompt', ''),
            negative_prompt=settings.get('ad_negative', ''),
        )
        payload["alwayson_scripts"]["ADetailer"] = {"args": adetailer_args}
        return self._run_img2img_postprocess(image_b64, payload)

    def sam3(self, image_b64: str, settings: Dict) -> str:
        """img2img + SAM3 확장으로 마스킹/인페인트"""
        sam3_state = self._build_sam3_script_state(settings)
        payload = self._build_postprocess_payload(
            image_b64,
            settings,
            prompt=sam3_state.get('sam3_inpaint_prompt', '') or settings.get('prompt', ''),
            negative_prompt=sam3_state.get('sam3_negative_prompt', '') or settings.get('negative_prompt', ''),
        )
        payload["alwayson_scripts"]["SAM3 Mask"] = {"args": [sam3_state]}
        return self._run_img2img_postprocess(image_b64, payload)

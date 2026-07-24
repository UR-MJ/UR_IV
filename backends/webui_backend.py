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
        """SAM3 alwayson state — core/sam3_args로 일원화 (t2i 경로와 동일 로직).

        예전에는 이 함수와 ui/generator_generation.py에 거의 같은 dict가 복사돼 있어
        한쪽만 고치면 t2i와 배치 결과가 갈렸다. 기본값·범위·ControlNet 필드는 전부
        core/sam3_args.SAM3_SPEC 한 곳에서 관리한다.

        ★ sam3_unload_after: 확장 UI 기본은 True지만 API 경로는 `_xyz_or(..., False)`라
          명시하지 않으면 인페인트 내내 SAM3(~3.5GB)가 상주해 16GB GPU에서 OOM 난다.
          SAM3_SPEC의 기본값이 True이므로 명시 전송된다.
        """
        from core import sam3_args
        # 예전 호출자가 denoising_strength만 넘기던 경우 호환
        if 'sam3_denoising_strength' not in settings and 'denoising_strength' in settings:
            settings = dict(settings)
            settings['sam3_denoising_strength'] = settings['denoising_strength']
        return sam3_args.build_state(
            settings,
            prompt=str(settings.get('prompt', '') or ''),
            negative_prompt=str(settings.get('negative_prompt', '') or ''),
        )

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

    def get_lora_manager_url(self) -> Dict:
        """sam-extra의 임베드된 LoRA Manager 주소를 얻는다.

        확장이 Forge FastAPI에 등록해 둔 라우트(`sam3ext/lora_manager_core.py`):
            GET /sam3-lora/spawn  → {"url", "port", "status", "message"}
        서버가 안 떠 있으면 이 호출이 띄운다(lazy spawn). 확장이 없으면 404 → 안내 메시지.

        반환: {'url': str, 'status': str, 'message': str}
        """
        try:
            r = requests.get(f'{self.api_url}/sam3-lora/spawn',
                             headers=_HEADERS, timeout=20)
            if r.status_code == 404:
                return {'url': '', 'status': 'missing',
                        'message': 'sam-extra 확장의 LoRA Manager를 찾을 수 없습니다 '
                                   '(확장 미설치이거나 v0.9.0 미만)'}
            r.raise_for_status()
            data = r.json()
            return {
                'url': str(data.get('url') or ''),
                'status': str(data.get('status') or ''),
                'message': str(data.get('message') or ''),
            }
        except Exception as e:
            logger.warning("LoRA Manager URL 조회 실패: %s", e)
            return {'url': '', 'status': 'error', 'message': str(e)}

    def get_backend_type(self) -> str:
        return "webui"

    def interrupt(self):
        """진행 중 생성 중단 — POST /sdapi/v1/interrupt (best-effort, 실패 무시).
        호출되면 진행 중이던 txt2img/img2img requests.post가 부분 결과로 곧 반환된다."""
        try:
            requests.post(f'{self.api_url}/sdapi/v1/interrupt',
                          headers=_HEADERS, timeout=5)
            logger.info("interrupt 요청 전송")
        except Exception as e:
            logger.debug(f"interrupt 실패(무시): {e}")

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

    def refine(self, image_b64: str, settings: Dict) -> str:
        """SAM3 Refine — 기존 이미지를 Target/Replacement로 재손질.

        sam-extra 워크플로 2를 앱에서 구현한 것. 확장의 Refine 패널은 Gradio 전용이라
        HTTP로 부를 수 없어서, 같은 결과가 나오도록 여기서 payload를 만든다.

        `sam3()` 와의 차이 (이게 핵심):
          · sam3()는 `_build_postprocess_payload`를 쓰는데 denoising_strength가 0.1로
            고정돼 **이미지 전체가 한 번 재확산**된다. Refine은 마스크 영역만 건드려야
            하므로 부모 i2i는 denoise 0으로 통과시키고 SAM3 인페인트만 일하게 한다.
          · steps/cfg/sampler/seed를 명시해 Forge 현재 UI 값에 좌우되지 않게 한다.
        """
        from core.refine_prompt import build_refine_prompts

        prompts = build_refine_prompts(
            main_prompt=settings.get('main_prompt', ''),
            main_negative=settings.get('main_negative', ''),
            target=settings.get('target', ''),
            replacement=settings.get('replacement', ''),
            negative=settings.get('negative', ''),
            inherit_main=bool(settings.get('inherit_main', True)),
            inherit_negative=bool(settings.get('inherit_negative', True)),
        )

        sam3_settings = dict(settings)
        sam3_settings['sam3_prompt'] = settings.get('target') or 'face'
        sam3_settings['sam3_inpaint_prompt'] = prompts['prompt']
        sam3_settings['sam3_negative_prompt'] = prompts['negative_prompt']
        sam3_settings['sam3_mode'] = 'Inpaint'
        sam3_state = self._build_sam3_script_state(sam3_settings)

        image_bytes = base64.b64decode(image_b64)
        with Image.open(io.BytesIO(image_bytes)) as init_image:
            init_width, init_height = init_image.size

        payload = {
            "init_images": [image_b64],
            "prompt": prompts['prompt'],
            "negative_prompt": prompts['negative_prompt'],
            # 부모 i2i는 아무것도 바꾸지 않게 — 실제 작업은 SAM3 인페인트 패스가 한다
            "denoising_strength": 0.0,
            "resize_mode": 0,
            "width": init_width,
            "height": init_height,
            "steps": int(settings.get('steps', 28)),
            "cfg_scale": float(settings.get('cfg_scale', 7.0)),
            "seed": int(settings.get('seed', -1)),
            "send_images": True,
            "save_images": False,
            "alwayson_scripts": {"SAM3 Mask": {"args": [sam3_state]}},
        }
        sampler = str(settings.get('sampler') or '').strip()
        if sampler and sampler != 'Use same sampler':
            payload["sampler_name"] = sampler
        scheduler = str(settings.get('scheduler') or '').strip()
        if scheduler and scheduler != 'Use same scheduler':
            payload["scheduler"] = scheduler

        logger.info("Refine: target=%r → prompt=%r", settings.get('target'), prompts['prompt'])
        return self._run_img2img_postprocess(image_b64, payload)

    def sam3(self, image_b64: str, settings: Dict) -> str:
        """img2img + SAM3 확장으로 마스킹/인페인트 (배치/단독 실행 경로).

        예전에는 `_build_postprocess_payload`를 썼는데 거기 기본 denoising_strength가
        0.1이라 **이미지 전체가 한 번 재확산**됐다. Forge의 SAM3는 마스크 영역만
        건드리므로 결과가 달라지고, 전역 디테일 드리프트 + 낭비되는 시간까지 붙었다.
        `_postprocess_base_payload`를 채우는 호출자도 없어 steps/cfg/sampler가 전부
        Forge 현재 UI 값에 좌우돼 재현도 안 됐다.

        이제 부모 i2i는 denoise 0으로 통과시키고, 실제 작업은 SAM3 인페인트 패스가
        전담한다. 샘플링 파라미터도 명시 전송한다.
        """
        sam3_state = self._build_sam3_script_state(settings)

        image_bytes = base64.b64decode(image_b64)
        with Image.open(io.BytesIO(image_bytes)) as init_image:
            init_width, init_height = init_image.size

        prompt = sam3_state.get('sam3_inpaint_prompt', '') or settings.get('prompt', '')
        negative = sam3_state.get('sam3_negative_prompt', '') or settings.get('negative_prompt', '')

        payload = {
            "init_images": [image_b64],
            "prompt": prompt,
            "negative_prompt": negative,
            "denoising_strength": 0.0,
            "resize_mode": 0,
            "width": init_width,
            "height": init_height,
            "steps": int(settings.get('steps', 28)),
            "cfg_scale": float(settings.get('cfg_scale', 7.0)),
            "seed": int(settings.get('seed', -1)),
            "send_images": True,
            "save_images": False,
            "alwayson_scripts": {"SAM3 Mask": {"args": [sam3_state]}},
        }
        sampler = str(settings.get('sampler') or '').strip()
        if sampler and sampler != 'Use same sampler':
            payload["sampler_name"] = sampler
        scheduler = str(settings.get('scheduler') or '').strip()
        if scheduler and scheduler != 'Use same scheduler':
            payload["scheduler"] = scheduler
        return self._run_img2img_postprocess(image_b64, payload)

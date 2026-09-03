# backends/comfyui_backend.py
"""ComfyUI 백엔드 구현"""
import base64
import binascii
import copy
import io
import json
import mimetypes
import uuid
import random
import threading
import requests
import websocket
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from PIL import Image

from backends.base import (
    AbstractBackend, BackendInfo, GenerationResult, MediaArtifact,
    ProgressCallback,
)
from backends.comfyui_progress import ProgressTracker

import config
from utils.app_logger import get_logger

_logger = get_logger('comfyui')

_MEDIA_OUTPUT_FIELDS = {
    'images': 'image',
    'animated': 'animated',
    'gifs': 'animated',
    'videos': 'video',
    'audio': 'audio',
    'files': None,
}
_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
_ANIMATED_EXTENSIONS = {'.gif', '.apng'}
_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv', '.avi', '.m4v'}
_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aac', '.opus'}
_UPLOAD_IMAGE_FORMATS = {
    'PNG': ('png', 'image/png'),
    'JPEG': ('jpg', 'image/jpeg'),
    'WEBP': ('webp', 'image/webp'),
    'BMP': ('bmp', 'image/bmp'),
    'TIFF': ('tiff', 'image/tiff'),
}
_MAX_RESULT_ARTIFACTS = 64
_MAX_RESULT_BYTES = 256 * 1024 * 1024


def _int_or(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float_or(value, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed and parsed not in (float('inf'), float('-inf')) else default


def _read_bounded_media(response, remaining_bytes: int) -> bytes:
    headers = getattr(response, 'headers', {}) or {}
    try:
        declared_length = int(headers.get('Content-Length', '0') or 0)
    except (TypeError, ValueError):
        declared_length = 0
    if declared_length > remaining_bytes:
        raise ValueError("ComfyUI 미디어 결과 총 용량이 256MiB를 초과합니다.")
    iterator = getattr(response, 'iter_content', None)
    if not callable(iterator):
        data = bytes(getattr(response, 'content', b''))
        if len(data) > remaining_bytes:
            raise ValueError("ComfyUI 미디어 결과 총 용량이 256MiB를 초과합니다.")
        return data
    data = bytearray()
    for chunk in iterator(chunk_size=1024 * 1024):
        if not chunk:
            continue
        if len(data) + len(chunk) > remaining_bytes:
            raise ValueError("ComfyUI 미디어 결과 총 용량이 256MiB를 초과합니다.")
        data.extend(chunk)
    return bytes(data)


def analyze_workflow(file_path: str) -> dict:
    """워크플로우 JSON을 분석하여 요약 정보 반환

    Returns:
        {
            'valid': bool,
            'error': str | None,
            'format': 'api' | 'web',
            'node_count': int,
            'checkpoint': str | None,
            'ksampler_type': str | None,
            'has_positive_clip': bool,
            'has_negative_clip': bool,
            'has_save_node': bool,
            'width': int | None,
            'height': int | None,
            'nodes_summary': list[str],
        }
    """
    import os
    result = {
        'valid': False, 'error': None, 'format': None,
        'node_count': 0, 'checkpoint': None, 'ksampler_type': None,
        'has_positive_clip': False, 'has_negative_clip': False,
        'has_save_node': False, 'width': None, 'height': None,
        'nodes_summary': [],
    }

    if not file_path or not os.path.exists(file_path):
        result['error'] = "파일을 찾을 수 없습니다."
        return result

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result['error'] = f"JSON 파싱 오류: {e}"
        return result
    except Exception as e:
        result['error'] = f"파일 읽기 오류: {e}"
        return result

    # 포맷 감지
    if 'nodes' in data and isinstance(data['nodes'], list):
        result['format'] = 'web'
        nodes_by_type = {}
        for node in data.get('nodes', []):
            nt = node.get('type', 'Unknown')
            nodes_by_type[nt] = nodes_by_type.get(nt, 0) + 1

            wv = node.get('widgets_values', [])
            if nt == 'CheckpointLoaderSimple' and wv:
                result['checkpoint'] = str(wv[0])
            elif nt in ('KSampler', 'KSamplerAdvanced', 'SamplerCustom'):
                result['ksampler_type'] = nt
            elif nt == 'EmptyLatentImage' and len(wv) >= 2:
                try:
                    result['width'] = int(wv[0])
                    result['height'] = int(wv[1])
                except (ValueError, TypeError):
                    pass
            elif nt in ('SaveImage', 'PreviewImage'):
                result['has_save_node'] = True
            elif nt in ('CLIPTextEncode', 'CLIPTextEncodeSDXL'):
                result['has_positive_clip'] = True

        result['node_count'] = len(data.get('nodes', []))
        result['nodes_summary'] = [f"{t} x{c}" for t, c in sorted(nodes_by_type.items())]
    else:
        result['format'] = 'api'
        nodes_by_type = {}
        for node_id, node in data.items():
            if not isinstance(node, dict):
                continue
            cls = node.get('class_type', 'Unknown')
            nodes_by_type[cls] = nodes_by_type.get(cls, 0) + 1
            inputs = node.get('inputs', {})

            if cls == 'CheckpointLoaderSimple':
                result['checkpoint'] = inputs.get('ckpt_name')
            elif cls in ('KSampler', 'KSamplerAdvanced', 'SamplerCustom'):
                result['ksampler_type'] = cls
            elif cls == 'EmptyLatentImage':
                try:
                    result['width'] = int(inputs.get('width', 0))
                    result['height'] = int(inputs.get('height', 0))
                except (ValueError, TypeError):
                    pass
            elif cls in ('SaveImage', 'PreviewImage'):
                result['has_save_node'] = True
            elif cls in ('CLIPTextEncode', 'CLIPTextEncodeSDXL'):
                result['has_positive_clip'] = True

        result['node_count'] = len([k for k, v in data.items() if isinstance(v, dict)])
        result['nodes_summary'] = [f"{t} x{c}" for t, c in sorted(nodes_by_type.items())]

    # 3-state 분류 (API 포맷에서만 동작 — Web 포맷은 기본값)
    # 모델 콤보 활성/잠금 결정에 사용
    result['classification'] = 'unknown'
    result['is_locked'] = False
    result['model_node_id'] = None
    result['model_class'] = ''
    result['model_param'] = ''
    result['patch_chain'] = []
    if result['format'] == 'api':
        try:
            from backends.comfyui_workflow_inspector import inspect_workflow
            ins = inspect_workflow(data)
            result['classification'] = ins.classification.value
            result['is_locked'] = ins.is_locked
            result['model_node_id'] = ins.model_node_id
            result['model_class'] = ins.model_class
            result['model_param'] = ins.model_param
            result['patch_chain'] = list(ins.patch_chain)
            if ins.notes:
                result.setdefault('inspector_notes', []).extend(ins.notes)
        except Exception as e:
            _logger.warning(f"workflow inspector 실패: {e}")

    # 유효성 검사
    errors = []
    if not result['ksampler_type']:
        errors.append("KSampler 노드 없음")
    if not result['has_positive_clip']:
        errors.append("CLIPTextEncode 노드 없음")
    if not result['has_save_node']:
        errors.append("SaveImage/PreviewImage 노드 없음")

    if errors:
        result['error'] = ", ".join(errors)
    else:
        result['valid'] = True

    return result


class ComfyUIBackend(AbstractBackend):
    """ComfyUI API 백엔드"""

    def __init__(self, api_url: str, *, workflow_path: Optional[str] = None,
                 img2img_workflow_path: Optional[str] = None):
        super().__init__(api_url)
        # ``None`` means follow the process-wide legacy config. An explicit
        # string (including an empty one) belongs to this backend/profile only.
        self._workflow_path_override = workflow_path
        self._img2img_workflow_path_override = img2img_workflow_path
        self._prompt_lock = threading.Lock()
        self._current_prompt_id = None
        self._node_pack_preflight_done = False
        self._last_generation_context: Optional[dict] = None

    def _configured_workflow_path(self, mode: str) -> str:
        if mode == 'img2img':
            if self._img2img_workflow_path_override is not None:
                return self._img2img_workflow_path_override
            return getattr(config, 'COMFYUI_WORKFLOW_IMG2IMG_PATH', '')
        if self._workflow_path_override is not None:
            return self._workflow_path_override
        return getattr(config, 'COMFYUI_WORKFLOW_PATH', '')

    def get_backend_type(self) -> str:
        return "comfyui"

    def interrupt(self):
        """Cancel only this adapter's prompt without interrupting another client."""
        with self._prompt_lock:
            pid = self._current_prompt_id
        if pid:
            self._cancel_prompt(pid)

    def _cancel_prompt(self, pid: str) -> None:
        """Cancel a prompt after proving whether it is running or pending."""
        try:
            queue_response = requests.get(f'{self.api_url}/queue', timeout=5)
            queue_response.raise_for_status()
            queue_state = queue_response.json()

            def prompt_ids(key):
                entries = queue_state.get(key, []) if isinstance(queue_state, dict) else []
                return {
                    str(entry[1])
                    for entry in entries
                    if isinstance(entry, (list, tuple)) and len(entry) > 1
                }

            if pid in prompt_ids('queue_running'):
                response = requests.post(f'{self.api_url}/interrupt', timeout=5)
                response.raise_for_status()
                _logger.info("현재 ComfyUI prompt interrupt 요청 전송: %s", pid)
            else:
                # Pending or already-finished prompts can be removed without a
                # global interrupt that would affect another ComfyUI client.
                response = requests.post(
                    f'{self.api_url}/queue', json={'delete': [pid]}, timeout=5
                )
                response.raise_for_status()
                _logger.info("ComfyUI 대기 prompt 삭제 요청 전송: %s", pid)
        except Exception as e:
            _logger.debug(f"interrupt 실패(무시): {e}")

    def test_connection(self) -> bool:
        """ComfyUI 연결 상태 확인"""
        try:
            r = requests.get(f'{self.api_url}/system_stats', timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def get_info(self) -> BackendInfo:
        """ComfyUI /object_info에서 모델/샘플러/스케줄러 추출"""
        info = BackendInfo()

        obj_info = self.get_object_info()

        # 체크포인트 모델
        ckpt_node = obj_info.get('CheckpointLoaderSimple', {})
        ckpt_input = ckpt_node.get('input', {}).get('required', {})
        models = ckpt_input.get('ckpt_name', [[]])[0]
        if isinstance(models, list):
            info.models = list(models)
            info.checkpoints = ["Use same checkpoint"] + models

        # Native diffusion-model workflows (Anima/Krea/etc.) use UNETLoader
        # rather than CheckpointLoaderSimple.  Expose both without duplicates so
        # the same main model selector remains useful for app-owned workflows.
        unet_node = obj_info.get('UNETLoader', {})
        unet_input = unet_node.get('input', {}).get('required', {})
        unets = unet_input.get('unet_name', [[]])[0]
        if isinstance(unets, list):
            seen = {str(item).replace('\\', '/').casefold() for item in info.models}
            for item in unets:
                marker = str(item).replace('\\', '/').casefold()
                if marker not in seen:
                    seen.add(marker)
                    info.models.append(item)

        # 샘플러
        ksampler_node = obj_info.get('KSampler', {})
        ksampler_input = ksampler_node.get('input', {}).get('required', {})
        samplers = ksampler_input.get('sampler_name', [[]])[0]
        if isinstance(samplers, list):
            info.samplers = samplers

        # 스케줄러
        schedulers = ksampler_input.get('scheduler', [[]])[0]
        if isinstance(schedulers, list):
            info.schedulers = schedulers

        # 업스케일러
        try:
            upscale_node = obj_info.get('UpscaleModelLoader', {})
            upscale_input = upscale_node.get('input', {}).get('required', {})
            upscalers = upscale_input.get('model_name', [[]])[0]
            if isinstance(upscalers, list):
                info.upscalers = upscalers
        except Exception:
            pass

        # VAE
        try:
            vae_node = obj_info.get('VAELoader', {})
            vae_input = vae_node.get('input', {}).get('required', {})
            vae_list = vae_input.get('vae_name', [[]])[0]
            if isinstance(vae_list, list):
                info.vae = ["Use same VAE"] + vae_list
        except Exception:
            pass

        return info

    def get_object_info(self) -> dict:
        """Return the complete ComfyUI node/resource capability document.

        Model-family workflow runners use the full schema both to fail before
        queueing missing nodes and to resolve server-native model path choices.
        """
        from core.http_retry import get_with_retry

        data = get_with_retry(
            f'{self.api_url}/object_info', timeout=15, retries=3,
        ).json()
        if not isinstance(data, dict):
            raise RuntimeError("ComfyUI /object_info 응답이 객체가 아닙니다")
        return data

    @staticmethod
    def _is_loopback_url(value: str) -> bool:
        try:
            host = (urlparse(value).hostname or '').strip('[]').casefold()
        except (TypeError, ValueError):
            return False
        return host in {'127.0.0.1', 'localhost', '::1'}

    @staticmethod
    def _same_local_endpoint(left: str, right: str) -> bool:
        try:
            a, b = urlparse(left), urlparse(right)
            a_port = a.port or (443 if a.scheme == 'https' else 80)
            b_port = b.port or (443 if b.scheme == 'https' else 80)
            return a_port == b_port
        except (TypeError, ValueError):
            return False

    def _preflight_bundled_node_pack(self) -> None:
        """Install app-owned nodes only into the matching configured local runtime."""
        if self._node_pack_preflight_done or not self._is_loopback_url(self.api_url):
            return
        from core.backend_runtime import get_backend_runtime_manager
        from core.comfy_node_pack import install_bundled_node_pack

        manager = get_backend_runtime_manager()
        snapshot = manager.snapshot()
        engine = (snapshot.get('engines') or {}).get('comfyui') or {}
        extension_dir = str(engine.get('extensionDir') or '').strip()
        runtime_url = str(engine.get('apiUrl') or '').strip()
        if not extension_dir or (runtime_url and not self._same_local_endpoint(self.api_url, runtime_url)):
            # A different user-run local ComfyUI must not receive files by accident.
            _logger.info(
                "번들 노드 자동 설치 건너뜀: 현재 API와 설정된 ComfyUI 런타임이 다름 (%s / %s)",
                self.api_url, runtime_url or '미설정',
            )
            self._node_pack_preflight_done = True
            return
        if not bool(engine.get('extensionWritable')):
            # An auto-detected external custom_nodes directory is intentionally
            # read-only until the user explicitly approves it in Settings.  A
            # previously installed pack can still be used because live schema
            # validation below is read-only.
            _logger.info(
                "번들 노드 자동 설치 건너뜀: ComfyUI 확장 폴더 쓰기가 승인되지 않음 (%s)",
                extension_dir,
            )
            self._node_pack_preflight_done = True
            return
        result = install_bundled_node_pack(extension_dir)
        if result.changed:
            _logger.info("AI Studio ComfyUI 노드 팩 설치/갱신: %s", result.target)
            if bool(engine.get('owned')) and bool(engine.get('running')):
                # Comfy imports custom nodes only during startup.  Restart only
                # the process owned by this runtime manager; an external
                # user.bat process is never stopped implicitly.
                manager.execute('comfyui', 'stop')
                started = manager.execute(
                    'comfyui', 'start', {'installIfMissing': False},
                )
                restarted_url = str(started.get('apiUrl') or '').strip()
                if restarted_url:
                    self.api_url = restarted_url.rstrip('/')
                _logger.info("관리형 ComfyUI 재시작으로 번들 노드 팩 적용 완료")
            else:
                raise RuntimeError(
                    "AI Studio ComfyUI 노드 팩을 설치/갱신했습니다. "
                    "현재 ComfyUI는 앱이 시작한 프로세스가 아니므로 외부 ComfyUI를 "
                    "한 번 재시작한 뒤 다시 생성하세요."
                )
        self._node_pack_preflight_done = True

    def _workflow_compiler(self):
        """Run the local install preflight, then bind compilation to live capabilities."""
        from core.comfy_workflow_compiler import ComfyWorkflowCompiler

        self._preflight_bundled_node_pack()
        return ComfyWorkflowCompiler(self.get_object_info())

    def get_system_stats(self) -> dict:
        """GPU/VRAM 상태 조회"""
        try:
            r = requests.get(f'{self.api_url}/system_stats', timeout=3)
            if r.status_code == 200:
                data = r.json()
                devices = data.get('devices', [])
                if devices:
                    dev = devices[0]
                    return {
                        'vram_used': dev.get('vram_total', 0) - dev.get('vram_free', 0),
                        'vram_total': dev.get('vram_total', 0),
                        'vram_free': dev.get('vram_free', 0),
                    }
        except Exception:
            pass
        return {}

    def get_loras(self) -> list:
        """ComfyUI LoRA 목록 반환"""
        try:
            resp = requests.get(
                f'{self.api_url}/object_info/LoraLoader', timeout=10
            )
            resp.raise_for_status()
            obj_info = resp.json()
            lora_node = obj_info.get('LoraLoader', {})
            lora_input = lora_node.get('input', {}).get('required', {})
            names = lora_input.get('lora_name', [[]])[0]
            if isinstance(names, list):
                return [
                    {'name': n, 'alias': n, 'path': '', 'trigger_words': []}
                    for n in names
                ]
        except Exception as e:
            _logger.warning(f"ComfyUI LoRA 목록 로드 실패: {e}")
        return []

    # ── 워크플로우 포맷 감지 및 변환 ──

    def _load_configured_workflow(self, mode: str) -> Optional[dict]:
        """Load an optional advanced workflow; no path means use the app graph."""
        workflow_path = self._configured_workflow_path(mode)
        if not workflow_path:
            return None
        from core.path_safety import safe_config_file, UnsafePathError
        try:
            safe_path = safe_config_file(workflow_path, must_exist=True)
        except UnsafePathError as exc:
            raise RuntimeError(f"워크플로우 파일 경로가 유효하지 않습니다: {exc}") from exc
        with open(safe_path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        if 'nodes' in data and isinstance(data['nodes'], list):
            _logger.info("웹 포맷 워크플로우 감지 → API 포맷으로 변환")
            data = self._convert_web_to_api(data)
        if not isinstance(data, dict):
            raise RuntimeError("ComfyUI 워크플로우 최상위 값은 JSON 객체여야 합니다.")
        _logger.info("고급 ComfyUI 워크플로우 로드 (노드 %d개)", len(data))
        return data

    def _load_workflow(self) -> dict:
        """사용자 워크플로우 JSON 로드 (API/웹 포맷 자동 감지)"""
        workflow = self._load_configured_workflow('txt2img')
        if workflow is None:
            raise RuntimeError(
                "ComfyUI 워크플로우 파일이 설정되지 않았습니다.\n"
                "API 관리에서 워크플로우 JSON 파일을 선택해주세요."
            )
        return workflow

    def _convert_web_to_api(self, web_data: dict) -> dict:
        """ComfyUI 웹 포맷 → API 포맷 변환"""
        nodes = web_data.get('nodes', [])
        links = web_data.get('links', [])

        # 링크 맵 구성: link_id → (source_node_id, source_slot)
        link_map = {}
        for link in links:
            # link = [link_id, source_node_id, source_slot, dest_node_id, dest_slot, type]
            if len(link) >= 6:
                link_id = link[0]
                source_node_id = link[1]
                source_slot = link[2]
                link_map[link_id] = (source_node_id, source_slot)

        api_workflow = {}

        for node in nodes:
            node_id = str(node.get('id', ''))
            node_type = node.get('type', '')
            if not node_id or not node_type:
                continue

            api_node = {
                'class_type': node_type,
                'inputs': {}
            }

            # 위젯 값을 inputs에 매핑
            widget_values = node.get('widgets_values', [])
            node_inputs = node.get('inputs', [])

            # 입력 슬롯 처리 (링크 연결)
            for inp in node_inputs:
                inp_name = inp.get('name', '')
                inp_link = inp.get('link')
                if inp_link is not None and inp_link in link_map:
                    src_id, src_slot = link_map[inp_link]
                    api_node['inputs'][inp_name] = [str(src_id), src_slot]

            # 위젯 값 매핑 (노드 타입별)
            self._map_widget_values(api_node, node_type, widget_values)

            api_workflow[node_id] = api_node

        _logger.info(f"웹→API 변환 완료 (노드 {len(api_workflow)}개)")
        return api_workflow

    def _map_widget_values(self, api_node: dict, node_type: str, values: list):
        """노드 타입별 위젯 값을 inputs에 매핑"""
        inputs = api_node['inputs']

        if not values:
            return

        try:
            if node_type in ('KSampler',):
                # KSampler: seed, control_after_generate, steps, cfg, sampler_name, scheduler, denoise
                if len(values) >= 7:
                    inputs.setdefault('seed', values[0])
                    # values[1] = control_after_generate (skip)
                    inputs.setdefault('steps', values[2])
                    inputs.setdefault('cfg', values[3])
                    inputs.setdefault('sampler_name', values[4])
                    inputs.setdefault('scheduler', values[5])
                    inputs.setdefault('denoise', values[6])

            elif node_type == 'KSamplerAdvanced':
                # add_noise, noise_seed, control_after_generate, steps, cfg, sampler_name, scheduler,
                # start_at_step, end_at_step, return_with_leftover_noise
                if len(values) >= 10:
                    inputs.setdefault('add_noise', values[0])
                    inputs.setdefault('noise_seed', values[1])
                    inputs.setdefault('steps', values[3])
                    inputs.setdefault('cfg', values[4])
                    inputs.setdefault('sampler_name', values[5])
                    inputs.setdefault('scheduler', values[6])
                    inputs.setdefault('start_at_step', values[7])
                    inputs.setdefault('end_at_step', values[8])
                    inputs.setdefault('return_with_leftover_noise', values[9])

            elif node_type == 'CLIPTextEncode':
                if len(values) >= 1:
                    inputs.setdefault('text', values[0])

            elif node_type == 'CheckpointLoaderSimple':
                if len(values) >= 1:
                    inputs.setdefault('ckpt_name', values[0])

            elif node_type == 'EmptyLatentImage':
                if len(values) >= 3:
                    inputs.setdefault('width', values[0])
                    inputs.setdefault('height', values[1])
                    inputs.setdefault('batch_size', values[2])

            elif node_type == 'SaveImage':
                if len(values) >= 1:
                    inputs.setdefault('filename_prefix', values[0])

            elif node_type == 'VAELoader':
                if len(values) >= 1:
                    inputs.setdefault('vae_name', values[0])

        except (IndexError, TypeError):
            pass

    # ── 노드 탐색 ──

    def _find_ksampler_node(self, workflow: dict) -> Tuple[str, dict]:
        """KSampler 계열 노드 찾기"""
        sampler_types = (
            'KSampler', 'KSamplerAdvanced',
            'SamplerCustom', 'SamplerCustomAdvanced',
        )
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            cls = node.get('class_type', '')
            if cls in sampler_types:
                return node_id, node

        raise RuntimeError(
            "워크플로우에서 KSampler 노드를 찾을 수 없습니다.\n"
            f"지원되는 노드: {', '.join(sampler_types)}"
        )

    def _find_clip_encode_node(self, workflow: dict, start_node_id: str,
                                max_depth: int = 5) -> Optional[str]:
        """링크를 따라가며 CLIPTextEncode 노드를 찾기 (다단계 추적)"""
        clip_types = ('CLIPTextEncode', 'CLIPTextEncodeSDXL')
        visited = set()

        def trace(node_id: str, depth: int) -> Optional[str]:
            if depth > max_depth or node_id in visited:
                return None
            visited.add(node_id)

            node = workflow.get(node_id)
            if not node or not isinstance(node, dict):
                return None

            if node.get('class_type', '') in clip_types:
                return node_id

            # 이 노드의 입력을 추적하여 CLIPTextEncode 찾기
            inputs = node.get('inputs', {})
            for key, val in inputs.items():
                if isinstance(val, list) and len(val) >= 1:
                    linked_id = str(val[0])
                    result = trace(linked_id, depth + 1)
                    if result:
                        return result
            return None

        return trace(start_node_id, 0)

    def _trace_clip_nodes(self, workflow: dict, ksampler_node: dict) -> Tuple[Optional[str], Optional[str]]:
        """KSampler의 positive/negative 입력에서 CLIPTextEncode 노드 ID 찾기"""
        inputs = ksampler_node.get('inputs', {})

        positive_id = None
        negative_id = None

        # positive 입력 추적 (다단계)
        pos_input = inputs.get('positive')
        if isinstance(pos_input, list) and len(pos_input) >= 1:
            start_id = str(pos_input[0])
            positive_id = self._find_clip_encode_node(workflow, start_id)

        # negative 입력 추적 (다단계)
        neg_input = inputs.get('negative')
        if isinstance(neg_input, list) and len(neg_input) >= 1:
            start_id = str(neg_input[0])
            negative_id = self._find_clip_encode_node(workflow, start_id)

        return positive_id, negative_id

    def _apply_params(self, workflow: dict, model_name: str, payload: dict):
        """워크플로우 노드에 UI 파라미터 매핑"""
        ksampler_id, ksampler_node = self._find_ksampler_node(workflow)
        inputs = ksampler_node.get('inputs', {})
        cls = ksampler_node.get('class_type', '')

        _logger.info(f"KSampler 노드: ID={ksampler_id}, type={cls}")

        # KSampler 파라미터
        seed = payload.get('seed', -1)
        if seed == -1:
            seed = random.randint(0, 2**32 - 1)

        if cls == 'KSamplerAdvanced':
            inputs['noise_seed'] = seed
        else:
            inputs['seed'] = seed

        inputs['steps'] = payload.get('steps', 20)
        inputs['cfg'] = payload.get('cfg_scale', 7.0)
        inputs['sampler_name'] = payload.get('sampler_name', 'euler')
        inputs['scheduler'] = payload.get('scheduler', 'normal')
        inputs['denoise'] = payload.get('denoising_strength', 1.0)

        # CLIP Text Encode (positive/negative) — 다단계 추적
        pos_id, neg_id = self._trace_clip_nodes(workflow, ksampler_node)
        _logger.info(f"CLIPTextEncode: positive={pos_id}, negative={neg_id}")

        if pos_id and pos_id in workflow:
            pos_node = workflow[pos_id]
            pos_cls = pos_node.get('class_type', '')
            if pos_cls == 'CLIPTextEncode':
                pos_node['inputs']['text'] = payload.get('prompt', '')
            elif pos_cls == 'CLIPTextEncodeSDXL':
                # SDXL: text_g와 text_l 모두 설정
                prompt_text = payload.get('prompt', '')
                pos_node['inputs']['text_g'] = prompt_text
                pos_node['inputs']['text_l'] = prompt_text

        if neg_id and neg_id in workflow:
            neg_node = workflow[neg_id]
            neg_cls = neg_node.get('class_type', '')
            if neg_cls == 'CLIPTextEncode':
                neg_node['inputs']['text'] = payload.get('negative_prompt', '')
            elif neg_cls == 'CLIPTextEncodeSDXL':
                neg_text = payload.get('negative_prompt', '')
                neg_node['inputs']['text_g'] = neg_text
                neg_node['inputs']['text_l'] = neg_text

        # CheckpointLoaderSimple
        if model_name:
            for node_id, node in workflow.items():
                if not isinstance(node, dict):
                    continue
                if node.get('class_type') == 'CheckpointLoaderSimple':
                    node['inputs']['ckpt_name'] = model_name
                    break

        # EmptyLatentImage
        def positive_int(value, default=1):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return default
            return parsed if parsed > 0 else default

        batch_size = positive_int(payload.get('batch_size', 1))
        batch_count = max(
            positive_int(payload.get('n_iter', 1)),
            positive_int(payload.get('batch_count', 1)),
        )
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get('class_type') == 'EmptyLatentImage':
                node['inputs']['width'] = payload.get('width', 512)
                node['inputs']['height'] = payload.get('height', 512)
                node['inputs']['batch_size'] = batch_size * batch_count
                break

        _logger.info("워크플로우 파라미터 매핑 완료")

    # ── 생성 및 결과 수신 ──

    def _queue_and_wait(self, workflow: dict,
                        progress_callback: Optional[ProgressCallback] = None,
                        cancel_check: Optional[Callable[[], bool]] = None) -> GenerationResult:
        """워크플로우를 큐에 넣고 WebSocket으로 결과 대기"""
        ws = None
        try:
            if cancel_check and cancel_check():
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")
            # ★ 요청마다 고유 client_id 생성
            client_id = str(uuid.uuid4())

            # ★ WebSocket 먼저 연결 (프롬프트 제출 전에 연결해야 메시지를 놓치지 않음)
            ws_url = self.api_url.replace('http://', 'ws://').replace('https://', 'wss://')
            _logger.info(f"WebSocket 연결: {ws_url}/ws?clientId={client_id}")
            # WSS일 때만 인증서 검증(로컬 루프백은 http/ws라 해당 없음).
            ws_kwargs = {'timeout': 600}
            if ws_url.startswith('wss://'):
                import ssl
                try:
                    import certifi
                    ws_kwargs['sslopt'] = {
                        'cert_reqs': ssl.CERT_REQUIRED,
                        'ca_certs': certifi.where(),
                        'check_hostname': True,
                    }
                except ImportError:
                    ws_kwargs['sslopt'] = {
                        'cert_reqs': ssl.CERT_REQUIRED,
                        'check_hostname': True,
                    }
            ws = websocket.create_connection(
                f'{ws_url}/ws?clientId={client_id}',
                **ws_kwargs,
            )

            # 프롬프트 제출
            if cancel_check and cancel_check():
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")
            _logger.info("프롬프트 제출 중...")
            prompt_response = requests.post(
                f'{self.api_url}/prompt',
                json={'prompt': workflow, 'client_id': client_id},
                timeout=30
            )

            if prompt_response.status_code != 200:
                error_text = prompt_response.text
                try:
                    error_data = prompt_response.json()
                    # ComfyUI 에러 응답 파싱
                    error_info = error_data.get('error', {})
                    error_msg = error_info.get('message', error_text)

                    # 노드별 에러 상세
                    node_errors = error_data.get('node_errors', {})
                    if node_errors:
                        details = []
                        for nid, nerr in node_errors.items():
                            for e in nerr.get('errors', []):
                                details.append(f"  노드 {nid}: {e.get('message', str(e))}")
                        if details:
                            error_msg += "\n\n노드 에러:\n" + "\n".join(details)
                except Exception:
                    error_msg = error_text

                from core.error_handler import sanitize_for_ui
                _logger.error(f"프롬프트 제출 실패: {error_msg}")
                return GenerationResult(
                    success=False,
                    error=f"ComfyUI 큐 등록 실패 (HTTP {prompt_response.status_code}): {sanitize_for_ui(error_msg)}"
                )

            resp_data = prompt_response.json()
            prompt_id = resp_data.get('prompt_id')
            if not prompt_id:
                return GenerationResult(success=False, error="prompt_id를 받지 못했습니다.")

            # 노드 에러 확인 (200이어도 에러가 있을 수 있음)
            node_errors = resp_data.get('node_errors', {})
            if node_errors:
                details = []
                for nid, nerr in node_errors.items():
                    for e in nerr.get('errors', []):
                        details.append(f"  노드 {nid}: {e.get('message', str(e))}")
                if details:
                    _logger.warning(f"노드 경고: {details}")

            _logger.info(f"프롬프트 등록 완료: {prompt_id}")
            with self._prompt_lock:
                self._current_prompt_id = prompt_id
            if cancel_check and cancel_check():
                self._cancel_prompt(prompt_id)
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")

            # 결과 대기. 워크플로우 전체를 아는 순수 tracker가 노드별 이벤트를
            # 기존 3인자 progress callback 형식의 단조 증가 퍼센트로 변환한다.
            tracker = ProgressTracker(workflow)
            if cancel_check is None:
                return self._wait_for_result(
                    ws, prompt_id, progress_callback, tracker=tracker
                )
            return self._wait_for_result(
                ws, prompt_id, progress_callback, tracker=tracker,
                cancel_check=cancel_check,
            )

        except requests.exceptions.RequestException as e:
            _logger.error(f"API 요청 실패: {e}")
            return GenerationResult(success=False, error=f"ComfyUI API 요청 실패: {e}")
        except websocket.WebSocketException as e:
            _logger.error(f"WebSocket 오류: {e}")
            return GenerationResult(success=False, error=f"ComfyUI WebSocket 오류: {e}")
        except Exception as e:
            _logger.error(f"생성 오류: {e}", exc_info=True)
            return GenerationResult(success=False, error=f"ComfyUI 생성 오류: {e}")
        finally:
            prompt_id_value = locals().get('prompt_id')
            if prompt_id_value:
                with self._prompt_lock:
                    if self._current_prompt_id == prompt_id_value:
                        self._current_prompt_id = None
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

    def _wait_for_result(self, ws, prompt_id: str,
                         progress_callback: Optional[ProgressCallback],
                         tracker: Optional[ProgressTracker] = None,
                         cancel_check: Optional[Callable[[], bool]] = None) -> GenerationResult:
        """WebSocket 메시지를 수신하며 결과 대기"""
        _logger.info(f"결과 대기 중... (prompt_id={prompt_id})")
        tracker = tracker or ProgressTracker({})

        while True:
            if cancel_check and cancel_check():
                self._cancel_prompt(prompt_id)
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")
            msg = ws.recv()
            if isinstance(msg, bytes):
                continue  # 바이너리 메시지 (프리뷰 이미지) 스킵

            data = json.loads(msg)
            msg_type = data.get('type', '')
            event_data = data.get('data', {})

            # status는 전역 큐 이벤트지만 실행 이벤트는 prompt_id가 붙는다.
            # 같은 client websocket에 섞인 다른 작업의 이벤트는 무시한다.
            event_prompt_id = (
                event_data.get('prompt_id')
                if isinstance(event_data, dict) else None
            )
            if event_prompt_id and event_prompt_id != prompt_id:
                continue

            progress_update = tracker.consume(data)
            if progress_update is not None and progress_callback:
                progress_callback(
                    progress_update.step, progress_update.total, None
                )

            if msg_type == 'status':
                # 큐 상태 업데이트
                continue

            elif msg_type == 'progress':
                continue

            elif msg_type == 'executing':
                d = data.get('data', {})
                if d.get('node') is None:
                    # 실행 완료 (node=None은 전체 완료를 의미)
                    _logger.info("실행 완료")
                    break

            elif msg_type == 'execution_error':
                d = data.get('data', {})
                error_msg = d.get('exception_message', '알 수 없는 오류')
                traceback_lines = d.get('traceback', [])
                if traceback_lines:
                    error_msg += "\n" + "".join(traceback_lines[-3:])
                _logger.error(f"실행 오류: {error_msg}")
                return GenerationResult(success=False, error=f"ComfyUI 실행 오류:\n{error_msg}")

            elif msg_type == 'execution_interrupted':
                # interrupt() 호출로 서버가 실행을 중단함
                _logger.info("실행 중단됨 (interrupt)")
                return GenerationResult(success=False, error="생성 취소됨")

            elif msg_type == 'execution_cached':
                # 캐시된 노드 알림
                continue

        # 히스토리의 모든 미디어 결과 가져오기
        return self._fetch_result_artifacts(prompt_id)

    @staticmethod
    def _media_kind(output_field: str, filename: str,
                    mime: Optional[str] = None) -> Optional[str]:
        """Infer a stable artifact kind from Comfy's field and file metadata."""
        extension = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if mime:
            clean_mime = mime.split(';', 1)[0].strip().lower()
            if clean_mime.startswith('video/'):
                return 'video'
            if clean_mime.startswith('audio/'):
                return 'audio'
            if clean_mime in ('image/gif', 'image/apng'):
                return 'animated'

        if extension in _VIDEO_EXTENSIONS:
            return 'video'
        if extension in _AUDIO_EXTENSIONS:
            return 'audio'
        if extension in _ANIMATED_EXTENSIONS:
            return 'animated'
        if output_field in ('animated', 'gifs'):
            return 'animated'
        if extension in _IMAGE_EXTENSIONS:
            return 'image'
        return _MEDIA_OUTPUT_FIELDS.get(output_field)

    @staticmethod
    def _response_mime(response, filename: str) -> Optional[str]:
        headers = getattr(response, 'headers', {}) or {}
        content_type = headers.get('Content-Type') or headers.get('content-type')
        if content_type:
            return content_type.split(';', 1)[0].strip().lower()
        guessed, _encoding = mimetypes.guess_type(filename)
        return guessed

    def _fetch_result_artifacts(self, prompt_id: str) -> GenerationResult:
        """Download every image, animation, video, and audio history output."""
        _logger.info(f"결과 미디어 다운로드 중... (prompt_id={prompt_id})")

        history_response = requests.get(
            f'{self.api_url}/history/{prompt_id}', timeout=10
        )
        history_response.raise_for_status()
        history = history_response.json()

        prompt_history = history.get(prompt_id, {})
        outputs = prompt_history.get('outputs', {})

        if not outputs:
            _logger.error("히스토리에 출력 데이터 없음")
            return GenerationResult(
                success=False,
                error="ComfyUI 히스토리에서 출력을 찾을 수 없습니다.\n"
                      "워크플로우에 미디어 저장 노드가 있는지 확인하세요."
            )

        artifacts: List[MediaArtifact] = []
        seen: set = set()
        failed_downloads: List[str] = []
        total_bytes = 0

        for raw_node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            node_id = str(raw_node_id)
            # Known Comfy fields are handled explicitly by ``_media_kind``;
            # custom nodes with a different field name still work when their
            # file extension identifies a supported media type.
            for raw_output_field, raw_items in node_output.items():
                if not isinstance(raw_items, list):
                    continue
                output_field = str(raw_output_field)
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    filename = str(item.get('filename', '')).strip()
                    if not filename:
                        continue
                    initial_kind = self._media_kind(output_field, filename)
                    if initial_kind is None:
                        continue

                    subfolder = str(item.get('subfolder', ''))
                    storage_type = str(item.get('type', 'output'))
                    identity = (storage_type, subfolder, filename)
                    if identity in seen:
                        continue
                    if len(seen) >= _MAX_RESULT_ARTIFACTS:
                        return GenerationResult(
                            success=False,
                            error=f"ComfyUI 미디어 결과는 최대 {_MAX_RESULT_ARTIFACTS}개까지 허용됩니다.",
                        )
                    seen.add(identity)

                    media_response = None
                    try:
                        media_response = requests.get(
                            f'{self.api_url}/view',
                            params={
                                'filename': filename,
                                'subfolder': subfolder,
                                'type': storage_type,
                            },
                            timeout=60,
                            stream=True,
                        )
                        media_response.raise_for_status()
                        media_data = _read_bounded_media(
                            media_response, _MAX_RESULT_BYTES - total_bytes
                        )
                        total_bytes += len(media_data)
                    except ValueError as exc:
                        return GenerationResult(success=False, error=str(exc))
                    except requests.exceptions.RequestException as exc:
                        _logger.warning(f"미디어 다운로드 실패 ({filename}): {exc}")
                        failed_downloads.append(filename)
                        continue
                    finally:
                        close_response = getattr(media_response, 'close', None)
                        if callable(close_response):
                            close_response()

                    mime = self._response_mime(media_response, filename)
                    kind = self._media_kind(output_field, filename, mime) or initial_kind
                    metadata = {
                        key: value for key, value in item.items()
                        if key != 'filename'
                    }
                    metadata.update({
                        'node_id': node_id,
                        'output_field': output_field,
                        'subfolder': subfolder,
                        'storage_type': storage_type,
                    })
                    artifacts.append(MediaArtifact(
                        kind=kind,
                        data=media_data,
                        filename=filename,
                        mime=mime,
                        metadata=metadata,
                    ))

        if not artifacts:
            _logger.error("출력 노드에 지원되는 미디어 없음")
            detail = ""
            if failed_downloads:
                detail = "\n다운로드 실패: " + ", ".join(failed_downloads)
            return GenerationResult(
                success=False,
                error="ComfyUI 출력에서 지원되는 미디어를 찾을 수 없습니다.\n"
                      "이미지, 애니메이션, 영상 또는 오디오 저장 노드를 확인하세요."
                      + detail,
            )

        primary = next(
            (artifact for artifact in artifacts if artifact.kind == 'image'),
            None,
        ) or next(
            (artifact for artifact in artifacts if artifact.kind == 'animated'),
            None,
        )
        gen_info = {
            'prompt_id': prompt_id,
            'filename': primary.filename if primary else artifacts[0].filename,
            'artifact_count': len(artifacts),
            'artifact_filenames': [artifact.filename for artifact in artifacts],
        }
        if failed_downloads:
            gen_info['artifact_download_errors'] = failed_downloads

        _logger.info(f"미디어 {len(artifacts)}개 수신 완료")
        return GenerationResult(
            success=True,
            image_data=primary.data if primary else None,
            info=gen_info,
            artifacts=artifacts,
        )

    # ── 공개 API ──

    def run_workflow(self, workflow: Dict,
                     progress_callback: Optional[ProgressCallback] = None,
                     cancel_check: Optional[Callable[[], bool]] = None) -> GenerationResult:
        """Run an already prepared API-format workflow.

        Model-specific workflow packs can use this seam without depending on
        websocket, history, progress, or media-download implementation details.
        """
        if not isinstance(workflow, dict) or not any(
            isinstance(node, dict) and node.get('class_type')
            for node in workflow.values()
        ):
            return GenerationResult(
                success=False,
                error="ComfyUI API 형식의 워크플로우가 필요합니다.",
            )
        if cancel_check is None:
            return self._queue_and_wait(workflow, progress_callback)
        return self._queue_and_wait(workflow, progress_callback, cancel_check)

    def generate_workflow(self, mode: str, workflow: Dict, model_name: str,
                          payload: Dict,
                          progress_callback: Optional[ProgressCallback] = None,
                          cancel_check: Optional[Callable[[], bool]] = None,
                          ) -> GenerationResult:
        """Generate from a caller-approved workflow without mutating caller data.

        ``mode`` accepts the normalized API names and their short UI aliases.
        The supplied workflow may be ComfyUI API format or exported web format.
        For img2img, the first ``init_images`` entry is uploaded and assigned to
        the workflow's ``LoadImage`` node before the normal parameter mapping and
        queue/result path are used.
        """
        mode_aliases = {
            'txt2img': 'txt2img',
            't2i': 'txt2img',
            'img2img': 'img2img',
            'i2i': 'img2img',
        }
        normalized_mode = mode_aliases.get(str(mode or '').strip().lower())
        if normalized_mode is None:
            return GenerationResult(
                success=False,
                error="mode는 txt2img(t2i) 또는 img2img(i2i)여야 합니다.",
            )
        if not isinstance(workflow, dict):
            return GenerationResult(
                success=False,
                error="ComfyUI 워크플로우는 JSON 객체여야 합니다.",
            )
        if not isinstance(payload, dict):
            return GenerationResult(
                success=False,
                error="생성 payload는 JSON 객체여야 합니다.",
            )

        try:
            if cancel_check and cancel_check():
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")
            prepared = copy.deepcopy(workflow)
            prepared_payload = copy.deepcopy(payload)
            if 'nodes' in prepared and isinstance(prepared['nodes'], list):
                prepared = self._convert_web_to_api(prepared)

            if normalized_mode == 'img2img':
                init_images = prepared_payload.get('init_images', [])
                if not isinstance(init_images, list) or not init_images:
                    return GenerationResult(
                        success=False,
                        error="입력 이미지가 없습니다.",
                    )
                load_image_id = self._find_load_image_node(prepared)
                if load_image_id is None:
                    return GenerationResult(
                        success=False,
                        error="img2img 워크플로우에 LoadImage 노드가 없습니다.",
                    )
                uploaded_filename = (
                    self._upload_image(init_images[0])
                    if cancel_check is None
                    else self._upload_image(init_images[0], cancel_check)
                )
                prepared[load_image_id].setdefault('inputs', {})['image'] = uploaded_filename
                prepared_payload.setdefault('denoising_strength', 0.75)

            if cancel_check and cancel_check():
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")
            self._apply_params(prepared, model_name, prepared_payload)
            if cancel_check is None:
                return self.run_workflow(prepared, progress_callback)
            return self.run_workflow(prepared, progress_callback, cancel_check)
        except Exception as exc:
            _logger.error("외부 워크플로우 생성 오류: %s", exc, exc_info=True)
            return GenerationResult(
                success=False,
                error=f"ComfyUI 워크플로우 생성 오류: {exc}",
            )

    def upload_media(self, data: bytes, filename: str,
                     mime: str = 'application/octet-stream',
                     overwrite: bool = True,
                     cancel_check: Optional[Callable[[], bool]] = None) -> str:
        """Upload one input artifact and return its ComfyUI input name."""
        clean_filename = str(filename or '').strip()
        if (
            not clean_filename
            or clean_filename in ('.', '..')
            or '/' in clean_filename
            or '\\' in clean_filename
        ):
            raise ValueError("filename은 경로가 아닌 안전한 파일명이어야 합니다.")
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data는 bytes 계열이어야 합니다.")

        if cancel_check and cancel_check():
            raise RuntimeError("사용자가 작업을 취소했습니다.")
        response = requests.post(
            f'{self.api_url}/upload/image',
            files={'image': (clean_filename, bytes(data), mime)},
            data={'overwrite': 'true' if overwrite else 'false'},
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        stored_name = str(result.get('name', '')).strip()
        if not stored_name:
            raise RuntimeError("업로드 응답에 파일명이 없습니다.")
        subfolder = str(result.get('subfolder', '')).strip('/\\')
        remote_name = f"{subfolder}/{stored_name}" if subfolder else stored_name
        _logger.info(f"미디어 업로드 완료: {remote_name}")
        return remote_name

    def txt2img(self, model_name: str, payload: Dict,
                progress_callback: Optional[ProgressCallback] = None,
                cancel_check: Optional[Callable[[], bool]] = None) -> GenerationResult:
        """텍스트→이미지 생성 (설정 workflow 또는 앱 소유 기본 graph)."""
        try:
            if cancel_check and cancel_check():
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")
            _logger.info(f"=== ComfyUI txt2img 시작 ===")
            _logger.info(f"모델: {model_name}")
            _logger.info(f"워크플로우 경로: {self._configured_workflow_path('txt2img') or '(미설정)'}")
            compiler = self._workflow_compiler()
            custom_workflow = self._load_configured_workflow('txt2img')
            workflow = compiler.compile(
                'txt2img', model_name, payload, workflow=custom_workflow,
            )
            self._last_generation_context = {
                'model_name': model_name, 'payload': copy.deepcopy(dict(payload)),
            }
            if cancel_check is None:
                return self._queue_and_wait(workflow, progress_callback)
            return self._queue_and_wait(workflow, progress_callback, cancel_check)

        except FileNotFoundError as e:
            _logger.error(f"워크플로우 파일 없음: {e}")
            return GenerationResult(success=False, error=f"워크플로우 파일을 찾을 수 없습니다:\n{e}")
        except json.JSONDecodeError as e:
            _logger.error(f"워크플로우 JSON 파싱 실패: {e}")
            return GenerationResult(success=False, error=f"워크플로우 JSON 파싱 실패:\n{e}")
        except RuntimeError as e:
            _logger.error(f"워크플로우 처리 오류: {e}")
            return GenerationResult(success=False, error=str(e))
        except Exception as e:
            _logger.error(f"예기치 못한 오류: {e}", exc_info=True)
            return GenerationResult(success=False, error=f"ComfyUI 생성 오류: {e}")

    def _load_img2img_workflow(self) -> dict:
        """img2img 워크플로우 JSON 로드"""
        workflow = self._load_configured_workflow('img2img')
        if workflow is None:
            raise RuntimeError(
                "ComfyUI img2img 워크플로우 파일이 설정되지 않았습니다.\n"
                "설정에서 img2img 워크플로우 JSON 파일을 선택해주세요."
            )
        return workflow

    def _upload_image(self, image_b64: str,
                      cancel_check: Optional[Callable[[], bool]] = None) -> str:
        """ComfyUI에 이미지 업로드 → 파일명 반환"""
        if not isinstance(image_b64, str) or not image_b64.strip():
            raise ValueError("입력 이미지는 base64 문자열이어야 합니다.")

        encoded = image_b64.strip()
        if encoded[:5].lower() == 'data:':
            header, separator, encoded = encoded.partition(',')
            if not separator or ';base64' not in header.lower():
                raise ValueError("입력 이미지 data URI가 올바르지 않습니다.")

        compact = ''.join(encoded.split())
        compact += '=' * (-len(compact) % 4)
        try:
            image_bytes = base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("입력 이미지 base64가 올바르지 않습니다.") from exc
        if not image_bytes:
            raise ValueError("입력 이미지가 비어 있습니다.")

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image_format = str(image.format or '').upper()
                image.verify()
        except (OSError, ValueError) as exc:
            raise ValueError("지원되는 입력 이미지 파일이 아닙니다.") from exc

        format_info = _UPLOAD_IMAGE_FORMATS.get(image_format)
        if format_info is None:
            raise ValueError("입력 이미지는 PNG/JPEG/WebP/BMP/TIFF만 지원합니다.")
        extension, mime = format_info
        filename = f'input_{uuid.uuid4().hex}.{extension}'
        if cancel_check is None:
            return self.upload_media(image_bytes, filename, mime)
        return self.upload_media(
            image_bytes, filename, mime, cancel_check=cancel_check
        )

    def _find_load_image_node(self, workflow: dict) -> Optional[str]:
        """LoadImage 노드 ID 찾기"""
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get('class_type') == 'LoadImage':
                return node_id
        return None

    def img2img(self, model_name: str, payload: Dict,
                progress_callback: Optional[ProgressCallback] = None,
                cancel_check: Optional[Callable[[], bool]] = None) -> GenerationResult:
        """이미지→이미지/인페인트 생성 (custom workflow가 없어도 동작)."""
        try:
            if cancel_check and cancel_check():
                return GenerationResult(success=False, error="사용자가 작업을 취소했습니다.")
            _logger.info("=== ComfyUI img2img 시작 ===")
            init_images = payload.get('init_images', [])
            if not isinstance(init_images, list) or not init_images:
                return GenerationResult(success=False, error="입력 이미지가 없습니다.")
            uploaded_filename = (
                self._upload_image(init_images[0])
                if cancel_check is None
                else self._upload_image(init_images[0], cancel_check)
            )
            mask_value = next((
                payload.get(key) for key in ('mask', 'mask_image', 'mask_base64')
                if isinstance(payload.get(key), str) and payload.get(key).strip()
            ), '')
            uploaded_mask = ''
            if mask_value:
                uploaded_mask = (
                    self._upload_image(mask_value)
                    if cancel_check is None
                    else self._upload_image(mask_value, cancel_check)
                )
            mode = 'inpaint' if mask_value or payload.get('use_image_alpha_as_mask') else 'img2img'
            compiler = self._workflow_compiler()
            custom_workflow = self._load_configured_workflow('img2img')
            workflow = compiler.compile(
                mode, model_name, payload, workflow=custom_workflow,
                uploaded_image=uploaded_filename, uploaded_mask=uploaded_mask,
            )
            self._last_generation_context = {
                'model_name': model_name, 'payload': copy.deepcopy(dict(payload)),
            }

            if cancel_check is None:
                return self._queue_and_wait(workflow, progress_callback)
            return self._queue_and_wait(workflow, progress_callback, cancel_check)

        except RuntimeError as e:
            _logger.error(f"img2img 오류: {e}")
            return GenerationResult(success=False, error=str(e))
        except Exception as e:
            _logger.error(f"img2img 예외: {e}", exc_info=True)
            return GenerationResult(success=False, error=f"ComfyUI img2img 오류: {e}")

    @staticmethod
    def _result_as_base64(
        result: GenerationResult, operation: str, *, prefer_last: bool = False,
    ) -> str:
        if not result.success:
            raise RuntimeError(result.error or f"ComfyUI {operation} 실패")
        if prefer_last:
            image_artifacts = [
                artifact for artifact in (result.artifacts or [])
                if artifact.kind in {'image', 'animated'} and artifact.data
            ]
            if image_artifacts:
                return base64.b64encode(image_artifacts[-1].data).decode('ascii')
        if not result.image_data:
            raise RuntimeError(f"ComfyUI {operation} 결과에 이미지가 없습니다.")
        return base64.b64encode(result.image_data).decode('ascii')

    def _saved_generation_context(self, settings: Dict) -> Tuple[str, dict]:
        """Resolve a model context for standalone detail operations."""
        if self._last_generation_context:
            base = copy.deepcopy(self._last_generation_context)
            model_name = str(settings.get('model') or base.get('model_name') or '').strip()
            payload = dict(base.get('payload') or {})
        else:
            saved = {}
            try:
                with open(config.PROMPT_SETTINGS_FILE, 'r', encoding='utf-8') as handle:
                    loaded = json.load(handle)
                    if isinstance(loaded, dict):
                        saved = loaded
            except (OSError, ValueError, TypeError) as exc:
                _logger.warning("저장된 생성 설정 읽기 실패: %s", exc)
            model_name = str(settings.get('model') or saved.get('model') or '').strip()
            modules = []
            vae_name = str(saved.get('vae_main') or '').strip()
            if vae_name:
                modules.append(vae_name)
            te_value = saved.get('te_main') or ''
            if isinstance(te_value, str):
                modules.extend(item.strip() for item in te_value.split(',') if item.strip())
            elif isinstance(te_value, list):
                modules.extend(str(item).strip() for item in te_value if str(item).strip())
            payload = {
                'prompt': str(saved.get('main_prompt') or ''),
                'negative_prompt': str(saved.get('negative_prompt') or ''),
                'sampler_name': str(saved.get('sampler') or 'euler'),
                'scheduler': str(saved.get('scheduler') or 'normal'),
                'steps': _int_or(saved.get('steps'), 28),
                'cfg_scale': _float_or(saved.get('cfg'), 7.0),
                'seed': _int_or(saved.get('seed'), -1),
            }
            if modules:
                payload['forge_additional_modules'] = modules
        if not model_name:
            raise RuntimeError(
                "단독 ComfyUI 후처리에 사용할 생성 모델이 없습니다. "
                "먼저 모델을 선택해 생성하거나 settings.model을 지정하세요."
            )
        payload.update({key: value for key, value in settings.items() if key in {
            'forge_additional_modules', 'weight_dtype', 'clip_type', 'comfy_clip_type',
            'clip_device', 'sampler_name', 'scheduler', 'steps', 'cfg_scale', 'seed',
        }})
        return model_name, payload

    def _standalone_detail(self, image_b64: str, settings: Dict, kind: str) -> str:
        model_name, payload = self._saved_generation_context(settings)
        try:
            encoded = str(image_b64 or '').strip()
            if encoded[:5].casefold() == 'data:':
                header, separator, encoded = encoded.partition(',')
                if not separator or ';base64' not in header.casefold():
                    raise ValueError("invalid data URI")
            compact = ''.join(encoded.split())
            compact += '=' * (-len(compact) % 4)
            raw = base64.b64decode(compact, validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                width, height = image.size
        except (binascii.Error, OSError, ValueError) as exc:
            raise ValueError("후처리 입력 이미지가 올바르지 않습니다.") from exc
        payload.update({
            'init_images': [image_b64], 'width': width, 'height': height,
            'denoising_strength': 0.0,
            'prompt': str(settings.get('prompt') or settings.get('ad_prompt') or payload.get('prompt') or ''),
            'negative_prompt': str(settings.get('negative_prompt') or settings.get('ad_negative') or payload.get('negative_prompt') or ''),
            'alwayson_scripts': {},
        })
        if kind == 'adetailer':
            args = settings.get('adetailer_args')
            if not isinstance(args, list):
                slot = {
                    'ad_tab_enable': True,
                    'ad_model': str(settings.get('ad_model') or 'face_yolov8n.pt'),
                    'ad_prompt': str(settings.get('ad_prompt') or ''),
                    'ad_negative_prompt': str(settings.get('ad_negative') or ''),
                    'ad_confidence': _float_or(settings.get('ad_confidence'), 0.3),
                    'ad_denoising_strength': _float_or(settings.get('ad_denoise'), 0.4),
                    'ad_dilate_erode': _int_or(settings.get('ad_dilate_erode'), 4),
                    'ad_mask_blur': _int_or(settings.get('ad_mask_blur'), 4),
                    'ad_inpaint_only_masked': True,
                    'ad_inpaint_only_masked_padding': _int_or(settings.get('ad_padding'), 32),
                    'ad_use_steps': False, 'ad_steps': _int_or(settings.get('steps'), 28),
                    'ad_use_cfg_scale': False, 'ad_cfg_scale': _float_or(settings.get('cfg_scale'), 7.0),
                    'ad_use_sampler': False,
                }
                args = [True, False, slot]
            payload['alwayson_scripts']['ADetailer'] = {'args': args}
        else:
            from core import sam3_args
            state = sam3_args.build_state(
                settings,
                prompt=str(payload.get('prompt') or ''),
                negative_prompt=str(payload.get('negative_prompt') or ''),
            )
            payload['alwayson_scripts'][sam3_args.SCRIPT_SAM3] = {'args': [state]}
        uploaded = self._upload_image(image_b64)
        compiler = self._workflow_compiler()
        workflow = compiler.compile_postprocess(
            model_name, payload, uploaded_image=uploaded,
            sam3_detailer_class=(
                'ForgeNeoSAM3Refine' if kind == 'refine'
                else 'ForgeNeoSAM3Detailer'
            ),
        )
        return self._result_as_base64(
            self._queue_and_wait(workflow), kind, prefer_last=(kind == 'refine'),
        )

    def upscale(self, image_b64: str, settings: Dict) -> str:
        """Run a standalone ComfyUI pixel/model upscale graph."""
        uploaded = self._upload_image(image_b64)
        workflow = self._workflow_compiler().compile_upscale(uploaded, settings)
        return self._result_as_base64(self._queue_and_wait(workflow), '업스케일')

    def adetailer(self, image_b64: str, settings: Dict) -> str:
        """Run the bundled Forge-compatible ADetailer node."""
        return self._standalone_detail(image_b64, settings, 'adetailer')

    def sam3(self, image_b64: str, settings: Dict) -> str:
        """Run the bundled SAM3 mask/detailer nodes."""
        if str(settings.get('sam3_mode') or 'Inpaint').strip().casefold() == 'mask only':
            from core import sam3_args

            state = sam3_args.build_state(settings)
            payload = {
                'alwayson_scripts': {sam3_args.SCRIPT_SAM3: {'args': [state]}},
            }
            uploaded = self._upload_image(image_b64)
            workflow = self._workflow_compiler().compile_sam3_mask_only(
                payload, uploaded_image=uploaded,
            )
            return self._result_as_base64(self._queue_and_wait(workflow), 'sam3 mask')
        return self._standalone_detail(image_b64, settings, 'sam3')

    def refine(self, image_b64: str, settings: Dict) -> str:
        """Run Forge SAM3 Refine semantics through the shared Comfy detailer."""
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
        prepared = dict(settings)
        prepared.update({
            'sam3_mode': 'Inpaint',
            'sam3_prompt': str(settings.get('target') or 'face'),
            'sam3_inpaint_prompt': prompts['prompt'],
            'sam3_negative_prompt': prompts['negative_prompt'],
            'prompt': prompts['prompt'],
            'negative_prompt': prompts['negative_prompt'],
        })
        return self._standalone_detail(image_b64, prepared, 'refine')

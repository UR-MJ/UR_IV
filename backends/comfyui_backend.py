# backends/comfyui_backend.py
"""ComfyUI 백엔드 구현"""
import json
import mimetypes
import uuid
import random
import requests
import websocket
from typing import Dict, List, Optional, Tuple

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

    def __init__(self, api_url: str):
        super().__init__(api_url)

    def get_backend_type(self) -> str:
        return "comfyui"

    def interrupt(self):
        """진행 중 생성 중단 — POST /interrupt + 대기 큐에서 항목 삭제 (best-effort)."""
        try:
            requests.post(f'{self.api_url}/interrupt', timeout=5)
            pid = getattr(self, '_current_prompt_id', None)
            if pid:
                # 아직 실행 전(큐 대기)이면 큐에서 제거
                requests.post(f'{self.api_url}/queue', json={'delete': [pid]}, timeout=5)
            _logger.info("interrupt 요청 전송")
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
            info.models = models
            info.checkpoints = ["Use same checkpoint"] + models

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

    def _load_workflow(self) -> dict:
        """사용자 워크플로우 JSON 로드 (API/웹 포맷 자동 감지)"""
        workflow_path = getattr(config, 'COMFYUI_WORKFLOW_PATH', '')
        if not workflow_path:
            raise RuntimeError(
                "ComfyUI 워크플로우 파일이 설정되지 않았습니다.\n"
                "API 관리에서 워크플로우 JSON 파일을 선택해주세요."
            )

        from core.path_safety import safe_config_file, UnsafePathError
        try:
            safe_path = safe_config_file(workflow_path, must_exist=True)
        except UnsafePathError as e:
            raise RuntimeError(f"워크플로우 파일 경로가 유효하지 않습니다: {e}") from e

        with open(safe_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 포맷 감지: 웹 포맷은 'nodes' 키가 있음
        if 'nodes' in data and isinstance(data['nodes'], list):
            _logger.info("웹 포맷 워크플로우 감지 → API 포맷으로 변환")
            return self._convert_web_to_api(data)

        # API 포맷: 최상위 키가 노드 ID
        _logger.info(f"API 포맷 워크플로우 로드 (노드 {len(data)}개)")
        return data

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
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get('class_type') == 'EmptyLatentImage':
                node['inputs']['width'] = payload.get('width', 512)
                node['inputs']['height'] = payload.get('height', 512)
                node['inputs']['batch_size'] = 1
                break

        _logger.info("워크플로우 파라미터 매핑 완료")

    # ── 생성 및 결과 수신 ──

    def _queue_and_wait(self, workflow: dict,
                        progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """워크플로우를 큐에 넣고 WebSocket으로 결과 대기"""
        ws = None
        try:
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
            self._current_prompt_id = prompt_id   # interrupt()의 큐 삭제용

            # 결과 대기. 워크플로우 전체를 아는 순수 tracker가 노드별 이벤트를
            # 기존 3인자 progress callback 형식의 단조 증가 퍼센트로 변환한다.
            tracker = ProgressTracker(workflow)
            return self._wait_for_result(
                ws, prompt_id, progress_callback, tracker=tracker
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
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

    def _wait_for_result(self, ws, prompt_id: str,
                         progress_callback: Optional[ProgressCallback],
                         tracker: Optional[ProgressTracker] = None) -> GenerationResult:
        """WebSocket 메시지를 수신하며 결과 대기"""
        _logger.info(f"결과 대기 중... (prompt_id={prompt_id})")
        tracker = tracker or ProgressTracker({})

        while True:
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
                    seen.add(identity)

                    try:
                        media_response = requests.get(
                            f'{self.api_url}/view',
                            params={
                                'filename': filename,
                                'subfolder': subfolder,
                                'type': storage_type,
                            },
                            timeout=60,
                        )
                        media_response.raise_for_status()
                    except requests.exceptions.RequestException as exc:
                        _logger.warning(f"미디어 다운로드 실패 ({filename}): {exc}")
                        failed_downloads.append(filename)
                        continue

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
                        data=media_response.content,
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

    def _fetch_result_image(self, prompt_id: str) -> GenerationResult:
        """이전 private 호출부 호환용 별칭."""
        return self._fetch_result_artifacts(prompt_id)

    # ── 공개 API ──

    def run_workflow(self, workflow: Dict,
                     progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
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
        return self._queue_and_wait(workflow, progress_callback)

    def upload_media(self, data: bytes, filename: str,
                     mime: str = 'application/octet-stream',
                     overwrite: bool = True) -> str:
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
                progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """텍스트→이미지 생성"""
        try:
            _logger.info(f"=== ComfyUI txt2img 시작 ===")
            _logger.info(f"모델: {model_name}")
            _logger.info(f"워크플로우 경로: {getattr(config, 'COMFYUI_WORKFLOW_PATH', '(미설정)')}")

            workflow = self._load_workflow()
            self._apply_params(workflow, model_name, payload)
            return self._queue_and_wait(workflow, progress_callback)

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
        import os
        workflow_path = getattr(config, 'COMFYUI_WORKFLOW_IMG2IMG_PATH', '')
        if not workflow_path:
            raise RuntimeError(
                "ComfyUI img2img 워크플로우 파일이 설정되지 않았습니다.\n"
                "설정에서 img2img 워크플로우 JSON 파일을 선택해주세요."
            )
        if not os.path.exists(workflow_path):
            raise RuntimeError(
                f"img2img 워크플로우 파일을 찾을 수 없습니다:\n{workflow_path}"
            )
        with open(workflow_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'nodes' in data and isinstance(data['nodes'], list):
            return self._convert_web_to_api(data)
        return data

    def _upload_image(self, image_b64: str) -> str:
        """ComfyUI에 이미지 업로드 → 파일명 반환"""
        import base64
        image_bytes = base64.b64decode(image_b64)
        return self.upload_media(image_bytes, 'input.png', 'image/png')

    def _find_load_image_node(self, workflow: dict) -> Optional[str]:
        """LoadImage 노드 ID 찾기"""
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get('class_type') == 'LoadImage':
                return node_id
        return None

    def img2img(self, model_name: str, payload: Dict,
                progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """이미지→이미지 생성"""
        try:
            _logger.info("=== ComfyUI img2img 시작 ===")

            workflow = self._load_img2img_workflow()

            # 입력 이미지 업로드
            init_images = payload.get('init_images', [])
            if not init_images:
                return GenerationResult(success=False, error="입력 이미지가 없습니다.")

            uploaded_filename = self._upload_image(init_images[0])

            # LoadImage 노드에 파일명 설정
            load_img_id = self._find_load_image_node(workflow)
            if load_img_id and load_img_id in workflow:
                workflow[load_img_id]['inputs']['image'] = uploaded_filename
            else:
                _logger.warning("LoadImage 노드를 찾을 수 없습니다. 이미지가 적용되지 않을 수 있습니다.")

            # 파라미터 적용
            self._apply_params(workflow, model_name, payload)

            # denoise 설정 (img2img에서 중요)
            try:
                ks_id, ks_node = self._find_ksampler_node(workflow)
                ks_node['inputs']['denoise'] = payload.get('denoising_strength', 0.75)
            except RuntimeError:
                pass

            return self._queue_and_wait(workflow, progress_callback)

        except RuntimeError as e:
            _logger.error(f"img2img 오류: {e}")
            return GenerationResult(success=False, error=str(e))
        except Exception as e:
            _logger.error(f"img2img 예외: {e}", exc_info=True)
            return GenerationResult(success=False, error=f"ComfyUI img2img 오류: {e}")

    def upscale(self, image_b64: str, settings: Dict) -> str:
        """업스케일 (추후 구현)"""
        raise NotImplementedError(
            "ComfyUI 업스케일은 아직 지원되지 않습니다.\n"
            "워크플로우에 업스케일 노드를 추가하여 사용하세요."
        )

    def adetailer(self, image_b64: str, settings: Dict) -> str:
        """ADetailer (ComfyUI에서는 지원하지 않음)"""
        raise NotImplementedError(
            "ComfyUI에서는 ADetailer가 지원되지 않습니다.\n"
            "워크플로우에 디테일러 노드를 추가하여 사용하세요."
        )

    def sam3(self, image_b64: str, settings: Dict) -> str:
        """SAM3 (ComfyUI에서는 지원하지 않음)"""
        raise NotImplementedError(
            "ComfyUI에서는 Forge SAM3 확장이 지원되지 않습니다.\n"
            "Forge Neo WebUI 백엔드에서 사용하세요."
        )

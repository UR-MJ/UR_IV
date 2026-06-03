# workers/sam3_worker.py
"""SAM3 단독 실행 워커 — 이미지 경로 → SAM3 적용 → 결과 저장"""
import os
import json
import base64
import logging
import threading
from PyQt6.QtCore import QThread, pyqtSignal

from core.error_handler import sanitize_for_ui

logger = logging.getLogger(__name__)


def _read_exif_prompts(image_path: str):
    """이미지 메타데이터에서 positive/negative prompt 추출.

    우선순위:
    1) PIL info 'parameters' (WebUI 포맷)
    2) PNG 텍스트 청크 (Comfy/기타)
    3) JSON 형태 메타데이터 (info['prompt'] or info['workflow'])
    실패 시 ('', '')
    """
    try:
        from PIL import Image
        img = Image.open(image_path)
        info = img.info or {}

        # 1) WebUI parameters
        raw = info.get('parameters', '')
        if raw and 'Steps:' in raw:
            parts = raw.split('\nNegative prompt: ')
            prompt = parts[0].strip()
            negative = ''
            if len(parts) > 1:
                sub = parts[1].split('\nSteps: ')
                negative = sub[0].strip()
            return prompt, negative

        # 2) PNG 텍스트 청크 (getattr로 보호)
        text_chunks = getattr(img, 'text', None) or {}
        for key in ('parameters', 'prompt', 'Description'):
            val = text_chunks.get(key) if isinstance(text_chunks, dict) else None
            if val and 'Steps:' in val:
                parts = val.split('\nNegative prompt: ')
                prompt = parts[0].strip()
                negative = ''
                if len(parts) > 1:
                    sub = parts[1].split('\nSteps: ')
                    negative = sub[0].strip()
                return prompt, negative

        # 3) JSON 메타데이터 (Comfy 워크플로우 등)
        for key in ('prompt', 'workflow'):
            val = info.get(key)
            if not val:
                continue
            try:
                parsed = json.loads(val) if isinstance(val, str) else val
            except (ValueError, TypeError):
                continue
            # Comfy 워크플로우에서 CLIPTextEncode 노드의 text 추출 (best-effort)
            if isinstance(parsed, dict):
                positive_texts, negative_texts = [], []
                for node in parsed.values():
                    if not isinstance(node, dict):
                        continue
                    inputs = node.get('inputs') or {}
                    text = inputs.get('text')
                    if not isinstance(text, str):
                        continue
                    title = (node.get('_meta') or {}).get('title', '').lower()
                    if 'negative' in title:
                        negative_texts.append(text)
                    elif 'positive' in title or 'prompt' in title:
                        positive_texts.append(text)
                if positive_texts or negative_texts:
                    return ', '.join(positive_texts), ', '.join(negative_texts)
    except Exception as e:
        logger.warning("EXIF read failed (%s): %s", os.path.basename(image_path), e)
    return '', ''


def _get_output_path(src_path: str, output_folder: str = '') -> str:
    """SAM3 결과 저장 경로 생성"""
    d = os.path.dirname(src_path)
    name, ext = os.path.splitext(os.path.basename(src_path))
    output_dir = output_folder or os.path.join(d, 'sam3')
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{name}_sam3{ext}")


def _to_posix(path: str) -> str:
    return path.replace('\\', '/')


def _prepare_settings(settings: dict, image_path: str) -> dict:
    """EXIF 프롬프트 적용"""
    settings = dict(settings)
    settings.setdefault('sam3_mode', 'Inpaint')
    settings.setdefault('sam3_mask_mode', 'Individual')
    settings.setdefault('sam3_prompt', 'face')
    if settings.get('use_exif_prompt'):
        prompt, negative = _read_exif_prompts(image_path)
        if prompt and not settings.get('sam3_inpaint_prompt'):
            settings['sam3_inpaint_prompt'] = prompt
        if negative and not settings.get('sam3_negative_prompt'):
            settings['sam3_negative_prompt'] = negative
    return settings


class Sam3SingleWorker(QThread):
    """단일 이미지 SAM3 처리"""
    finished = pyqtSignal(str)

    def __init__(self, image_path: str, settings: dict, parent=None):
        super().__init__(parent)
        self._path = image_path
        self._settings = settings

    def run(self):
        try:
            from backends import get_backend
            backend = get_backend()
            if not backend:
                self.finished.emit(json.dumps({'error': '백엔드 연결 없음'}))
                return

            settings = _prepare_settings(self._settings, self._path)

            with open(self._path, 'rb') as f:
                image_b64 = base64.b64encode(f.read()).decode()

            result_b64 = backend.sam3(image_b64, settings)

            output_path = _get_output_path(self._path, settings.get('output_folder', ''))
            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(result_b64))

            self.finished.emit(json.dumps({
                'before': _to_posix(self._path),
                'after': _to_posix(output_path),
                'output_path': _to_posix(output_path),
            }))
        except Exception as e:
            logger.exception("Sam3SingleWorker failed")
            self.finished.emit(json.dumps({'error': sanitize_for_ui(e)}))


class Sam3BatchWorker(QThread):
    """배치 이미지 SAM3 처리"""
    progress = pyqtSignal(int, int)
    single_done = pyqtSignal(str)
    all_done = pyqtSignal()

    def __init__(self, paths: list, settings: dict, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._settings = settings
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        from backends import get_backend
        backend = get_backend()
        if not backend:
            self.single_done.emit(json.dumps({'error': '백엔드 연결 없음'}))
            return

        total = len(self._paths)
        for i, path in enumerate(self._paths):
            if self._stop_event.is_set():
                break
            try:
                settings = _prepare_settings(self._settings, path)

                with open(path, 'rb') as f:
                    image_b64 = base64.b64encode(f.read()).decode()

                result_b64 = backend.sam3(image_b64, settings)
                output_path = _get_output_path(path, settings.get('output_folder', ''))
                with open(output_path, 'wb') as f:
                    f.write(base64.b64decode(result_b64))

                self.single_done.emit(json.dumps({
                    'before': _to_posix(path),
                    'after': _to_posix(output_path),
                    'output_path': _to_posix(output_path),
                    'index': i,
                }))
            except Exception as e:
                logger.exception("Sam3BatchWorker failed for %s", os.path.basename(path))
                self.single_done.emit(json.dumps({
                    'error': sanitize_for_ui(e),
                    'path': _to_posix(path),
                    'index': i,
                }))

            self.progress.emit(i + 1, total)

        self.all_done.emit()

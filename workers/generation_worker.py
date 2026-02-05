# workers/generation_worker.py
import json
from PyQt6.QtCore import QThread, pyqtSignal
from backends import get_backend


class WebUIInfoWorker(QThread):
    """서버 정보 로드 워커"""
    info_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def run(self):
        """백엔드 API에서 모델, 샘플러 등 정보 가져오기"""
        try:
            backend = get_backend()
            info = backend.get_info()
            self.info_ready.emit({
                'models': info.models,
                'samplers': info.samplers,
                'schedulers': info.schedulers,
                'upscalers': info.upscalers,
                'options': info.options,
                'vae': info.vae,
                'checkpoints': info.checkpoints,
            })
        except Exception as e:
            self.error_occurred.emit(str(e))


class GenerationFlowWorker(QThread):
    """이미지 생성 워커"""
    finished = pyqtSignal(object, dict)
    progress = pyqtSignal(int, int, object)  # step, total_steps, preview_bytes|None

    def __init__(self, model_name: str, payload: dict):
        super().__init__()
        self.model_name = model_name
        self.payload = payload

    def run(self):
        """모델 변경 후 이미지 생성"""
        try:
            backend = get_backend()

            def on_progress(step: int, total: int, preview):
                self.progress.emit(step, total, preview)

            result = backend.txt2img(self.model_name, self.payload, progress_callback=on_progress)

            if result.success:
                self.finished.emit(result.image_data, result.info)
            else:
                self.finished.emit(result.error, {})

        except Exception as e:
            self.finished.emit(f"이미지 생성 중 오류: {e}", {})


class Img2ImgFlowWorker(QThread):
    """img2img / inpaint 생성 워커"""
    finished = pyqtSignal(object, dict)
    progress = pyqtSignal(int, int, object)  # step, total_steps, preview_bytes|None

    def __init__(self, model_name: str, payload: dict):
        super().__init__()
        self.model_name = model_name
        self.payload = payload

    def run(self):
        try:
            backend = get_backend()

            def on_progress(step: int, total: int, preview):
                self.progress.emit(step, total, preview)

            result = backend.img2img(self.model_name, self.payload, progress_callback=on_progress)

            if result.success:
                self.finished.emit(result.image_data, result.info)
            else:
                self.finished.emit(result.error, {})

        except Exception as e:
            self.finished.emit(f"img2img 생성 중 오류: {e}", {})

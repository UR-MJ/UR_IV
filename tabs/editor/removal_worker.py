# tabs/editor/removal_worker.py
"""rembg를 사용한 배경 제거 워커 스레드"""
import numpy as np
import cv2
from PyQt6.QtCore import QThread, pyqtSignal


class RemovalWorker(QThread):
    """배경 제거 워커 — rembg 사용"""
    finished = pyqtSignal(object)   # BGRA numpy array
    error = pyqtSignal(str)

    def __init__(self, cv_image: np.ndarray, model_name: str = "u2net", parent=None):
        super().__init__(parent)
        self._cv_image = cv_image
        self._model_name = model_name

    def run(self):
        try:
            from rembg import remove, new_session
            from PIL import Image

            # BGR → RGB → PIL
            rgb = cv2.cvtColor(self._cv_image, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)

            # 선택한 모델로 세션 생성 후 배경 제거
            session = new_session(self._model_name)
            result_pil = remove(pil_img, session=session)
            result_rgba = np.array(result_pil)

            # RGBA → BGRA (OpenCV 형식)
            bgra = cv2.cvtColor(result_rgba, cv2.COLOR_RGBA2BGRA)

            self.finished.emit(bgra)
        except ImportError:
            self.error.emit(
                "rembg 라이브러리가 설치되지 않았습니다.\n"
                "pip install rembg 로 설치해주세요."
            )
        except Exception as e:
            self.error.emit(f"배경 제거 중 오류 발생:\n{e}")

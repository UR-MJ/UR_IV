# tabs/editor/batch_worker.py
"""일괄 처리 워커 스레드"""
import os
import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from tabs.editor.color_panel import ColorAdjustPanel


class BatchWorker(QThread):
    """일괄 처리 워커 — 리사이즈/포맷변환/워터마크/필터"""

    progress = pyqtSignal(int, int)       # current, total
    file_done = pyqtSignal(str, bool)     # filename, success
    all_done = pyqtSignal(int, int)       # success_count, fail_count
    error = pyqtSignal(str)

    def __init__(self, file_list: list, operation: str, config: dict,
                 output_dir: str, parent=None):
        super().__init__(parent)
        self.file_list = file_list
        self.operation = operation
        self.config = config
        self.output_dir = output_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.file_list)
        success = 0
        fail = 0

        os.makedirs(self.output_dir, exist_ok=True)

        for i, filepath in enumerate(self.file_list):
            if self._cancelled:
                break

            self.progress.emit(i + 1, total)
            try:
                ok = self._process_file(filepath)
                if ok:
                    success += 1
                    self.file_done.emit(os.path.basename(filepath), True)
                else:
                    fail += 1
                    self.file_done.emit(os.path.basename(filepath), False)
            except Exception as e:
                fail += 1
                self.file_done.emit(f"{os.path.basename(filepath)}: {e}", False)

        self.all_done.emit(success, fail)

    def _process_file(self, filepath: str) -> bool:
        """파일 하나 처리"""
        img = cv2.imdecode(
            np.fromfile(filepath, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if img is None:
            return False

        basename = os.path.splitext(os.path.basename(filepath))[0]

        if self.operation == 'resize':
            img = self._do_resize(img)
            ext = os.path.splitext(filepath)[1]
        elif self.operation == 'format':
            ext = self.config.get('target_format', '.png')
        elif self.operation == 'filter':
            filter_name = self.config.get('filter_name', 'grayscale')
            img = ColorAdjustPanel.apply_filter(img, filter_name)
            ext = os.path.splitext(filepath)[1]
        elif self.operation == 'watermark':
            img = self._do_watermark(img)
            ext = os.path.splitext(filepath)[1]
        else:
            return False

        # 저장
        out_path = os.path.join(self.output_dir, f"{basename}{ext}")
        if self.operation == 'format' and ext == '.jpg':
            quality = self.config.get('quality', 95)
            params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            result, buf = cv2.imencode(ext, img, params)
        elif self.operation == 'format' and ext == '.webp':
            quality = self.config.get('quality', 95)
            params = [cv2.IMWRITE_WEBP_QUALITY, quality]
            result, buf = cv2.imencode(ext, img, params)
        else:
            result, buf = cv2.imencode(ext if ext else '.png', img)

        if result:
            buf.tofile(out_path)
            return True
        return False

    def _do_resize(self, img: np.ndarray) -> np.ndarray:
        """리사이즈 처리"""
        mode = self.config.get('mode', 'fixed')
        h, w = img.shape[:2]

        if mode == 'fixed':
            new_w = self.config.get('width', w)
            new_h = self.config.get('height', h)
        elif mode == 'percent':
            pct = self.config.get('percent', 100) / 100.0
            new_w = max(1, int(w * pct))
            new_h = max(1, int(h * pct))
        elif mode == 'longest':
            target = self.config.get('longest', max(w, h))
            if w >= h:
                new_w = target
                new_h = max(1, int(h * target / w))
            else:
                new_h = target
                new_w = max(1, int(w * target / h))
        else:
            return img

        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    def _do_watermark(self, img: np.ndarray) -> np.ndarray:
        """워터마크 적용"""
        from tabs.editor.watermark_panel import WatermarkPanel

        wm_config = self.config.get('watermark_config', {})
        wm_type = wm_config.get('type', 'text')

        if wm_type == 'text':
            return WatermarkPanel.render_text_watermark(img, wm_config)
        elif wm_type == 'image':
            return WatermarkPanel.render_image_watermark(img, wm_config)
        return img

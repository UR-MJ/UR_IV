# workers/gallery_worker.py
import os
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtCore import QThread, pyqtSignal
from PIL import Image, PngImagePlugin

try:
    import exifread
except ImportError:
    exifread = None


def _normalize_path(path: str) -> str:
    """경로 정규화"""
    return Path(path).resolve().as_posix()


def _get_thumb_path(image_path: str, thumb_dir: str) -> str:
    """썸네일 경로 생성"""
    h = hashlib.sha1(_normalize_path(image_path).encode('utf-8')).hexdigest()
    return os.path.join(thumb_dir, f"{h}.jpg")


def _read_exif(path: str) -> str:
    """이미지 EXIF/메타데이터 읽기"""
    ext = os.path.splitext(path)[-1].lower()
    try:
        if ext == ".png":
            img = Image.open(path)
            return "\n".join([f"{k}: {v}" for k, v in img.info.items() if isinstance(v, str)])
        elif ext in (".jpg", ".jpeg"):
            if exifread is None:
                return ""
            with open(path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
            return "\n".join([f"{k}: {tags[k]}" for k in tags
                              if k not in ("JPEGThumbnail", "TIFFThumbnail")])
        else:
            return ""
    except Exception as e:
        print(f"[EXIF] READ ERROR {path}: {e}")
        return ""


def _process_single(path: str, thumb_dir: str) -> tuple:
    """단일 이미지 처리: 썸네일 생성 + EXIF 읽기 (스레드풀용)"""
    norm_path = _normalize_path(path)
    thumb_path = _get_thumb_path(path, thumb_dir)

    # 썸네일 생성 (이미 있으면 건너뜀)
    if not os.path.exists(thumb_path):
        try:
            img = Image.open(path)
            img.thumbnail((200, 200), Image.LANCZOS)
            img.convert("RGB").save(thumb_path, "JPEG", quality=85)
        except Exception:
            pass

    # EXIF 읽기
    exif = ""
    try:
        exif = _read_exif(path)
    except Exception:
        pass

    return (norm_path, exif)


IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')


class GalleryScanWorker(QThread):
    """폴더 재귀 스캔 워커 - 이미지 경로 수집"""
    paths_found = pyqtSignal(list)
    finished = pyqtSignal()

    def __init__(self, folder: str):
        super().__init__()
        self.folder = folder
        self._stop_requested = False

    def run(self):
        batch = []
        for root, _, files in os.walk(self.folder):
            if self._stop_requested:
                break
            for file in files:
                if self._stop_requested:
                    break
                if file.lower().endswith(IMAGE_EXTENSIONS):
                    batch.append(os.path.join(root, file))
                    if len(batch) >= 500:
                        self.paths_found.emit(batch)
                        batch = []
        if batch:
            self.paths_found.emit(batch)
        self.finished.emit()

    def request_stop(self):
        self._stop_requested = True


class GalleryCacheWorker(QThread):
    """썸네일 생성 + EXIF 캐싱 워커 (ThreadPoolExecutor 병렬 처리)"""
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal()

    MAX_WORKERS = 8

    def __init__(self, image_paths: list, db_manager, thumb_dir: str):
        super().__init__()
        self.image_paths = image_paths
        self.db = db_manager
        self.thumb_dir = thumb_dir
        self._stop_requested = False

    def run(self):
        total = len(self.image_paths)
        if total == 0:
            self.finished.emit()
            return

        # 이미 캐싱된 파일 필터링
        to_process = []
        for path in self.image_paths:
            thumb_path = _get_thumb_path(path, self.thumb_dir)
            if os.path.exists(thumb_path):
                # 썸네일은 있지만 DB에 EXIF가 없을 수 있으므로 체크
                norm = _normalize_path(path)
                data = self.db.get_image_data(norm)
                if data and data[0]:  # exif 필드가 있으면 건너뜀
                    continue
            to_process.append(path)

        skipped = total - len(to_process)
        if skipped > 0:
            self.progress.emit(skipped, total)

        if not to_process:
            self.progress.emit(total, total)
            self.finished.emit()
            return

        # 병렬 처리
        done_count = skipped
        batch_results = []

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {
                executor.submit(_process_single, path, self.thumb_dir): path
                for path in to_process
            }
            for future in as_completed(futures):
                if self._stop_requested:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    norm_path, exif = future.result()
                    batch_results.append((norm_path, exif))
                except Exception:
                    pass

                done_count += 1

                # 배치 DB 커밋 (100개씩)
                if len(batch_results) >= 100:
                    self._flush_to_db(batch_results)
                    batch_results.clear()

                if done_count % 20 == 0 or done_count == total:
                    self.progress.emit(done_count, total)

        # 잔여 배치 커밋
        if batch_results:
            self._flush_to_db(batch_results)

        self.progress.emit(total, total)
        self.finished.emit()

    def _flush_to_db(self, batch: list):
        """배치로 DB에 EXIF 저장"""
        for norm_path, exif in batch:
            try:
                self.db.add_or_update_exif(norm_path, exif)
            except Exception:
                pass

    def request_stop(self):
        self._stop_requested = True

"""Qt worker for loading Event Gen parquet data outside the legacy tab."""

from PyQt6.QtCore import QThread, pyqtSignal

from core.event_data_loader import EventDataLoader


class EventDataLoadWorker(QThread):
    """Load selected Event Gen rating shards without blocking the UI thread."""

    finished = pyqtSignal(object)  # EventDataLoader or a user-facing error string
    progress = pyqtSignal(str)

    def __init__(self, parquet_dir, ratings, parent=None):
        super().__init__(parent)
        self.parquet_dir = parquet_dir
        self.ratings = ratings

    def run(self):
        try:
            self.progress.emit("데이터 로딩 중...")
            loader = EventDataLoader(self.parquet_dir)
            loader.load_parquets_by_rating(
                self.ratings,
                progress_callback=lambda cur, total, name: self.progress.emit(
                    f"로딩 중... ({cur}/{total}) {name}"
                ),
            )
            self.finished.emit(loader)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            self.finished.emit(f"오류: {exc}")

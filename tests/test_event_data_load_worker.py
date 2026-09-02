"""Event data loading worker contract tests."""

from __future__ import annotations

import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from workers.event_data_load_worker import EventDataLoadWorker


class _Loader:
    def __init__(self, parquet_dir):
        self.parquet_dir = parquet_dir
        self.loaded_ratings = None

    def load_parquets_by_rating(self, ratings, progress_callback):
        self.loaded_ratings = ratings
        progress_callback(1, 2, "g")
        progress_callback(2, 2, "s")


class EventDataLoadWorkerTests(unittest.TestCase):
    @patch("workers.event_data_load_worker.EventDataLoader", _Loader)
    def test_worker_emits_progress_and_loaded_domain_object(self):
        worker = EventDataLoadWorker("parquets", ("g", "s"))
        progress = []
        finished = []
        worker.progress.connect(progress.append)
        worker.finished.connect(finished.append)

        worker.run()

        self.assertEqual(
            progress,
            [
                "데이터 로딩 중...",
                "로딩 중... (1/2) g",
                "로딩 중... (2/2) s",
            ],
        )
        self.assertEqual(len(finished), 1)
        self.assertIsInstance(finished[0], _Loader)
        self.assertEqual(finished[0].parquet_dir, "parquets")
        self.assertEqual(finished[0].loaded_ratings, ("g", "s"))

    def test_worker_converts_loader_failure_to_existing_error_contract(self):
        class _BrokenLoader:
            def __init__(self, _parquet_dir):
                raise RuntimeError("broken shard")

        worker = EventDataLoadWorker("parquets", ("g",))
        finished = []
        worker.finished.connect(finished.append)

        with patch(
            "workers.event_data_load_worker.EventDataLoader",
            _BrokenLoader,
        ), redirect_stderr(StringIO()):
            worker.run()

        self.assertEqual(finished, ["오류: broken shard"])


if __name__ == "__main__":
    unittest.main()

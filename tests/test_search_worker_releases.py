from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from workers.search_worker import PandasSearchWorker


class SearchWorkerReleaseTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._temp_dir.name)
        self._reset_cache()

    def tearDown(self):
        self._reset_cache()
        self._temp_dir.cleanup()

    @staticmethod
    def _reset_cache():
        PandasSearchWorker.cached_df = None
        PandasSearchWorker.cached_col_lower.clear()
        PandasSearchWorker.loaded_ratings = set()
        PandasSearchWorker.loaded_year = ""
        if hasattr(PandasSearchWorker, "loaded_file_signature"):
            PandasSearchWorker.loaded_file_signature = ()

    def _write_release(
        self,
        year: str,
        rating: str,
        general: str,
        *,
        drop_columns=(),
        **overrides,
    ):
        row = {
            "rating": rating,
            "general": general,
            "character": "release_tester",
            "copyright": "search_contract",
            "artist": "test_artist",
            "meta": "",
            "image_width": 1024,
            "image_height": 1024,
        }
        row.update(overrides)
        for column in drop_columns:
            row.pop(column, None)
        pd.DataFrame([row]).to_parquet(
            self.data_dir / f"danbooru_{year}_{rating}.parquet",
            index=False,
        )

    def _run(self, *, year=None, ratings=("g",)):
        emissions = []
        worker = PandasSearchWorker(
            str(self.data_dir),
            ratings,
            queries={},
            dataset_year=year,
        )
        worker.results_ready.connect(
            lambda rows, total: emissions.append((rows, total))
        )
        worker.run()
        self.assertEqual(len(emissions), 1)
        return worker, emissions[0]

    def test_default_release_prefers_2026_07_when_present(self):
        self._write_release("2026_07", "g", "new_release_tag")
        self._write_release("2026_06", "g", "previous_release_tag")

        worker, (rows, total) = self._run()

        self.assertEqual(worker.dataset_year, "2026_07")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["general"], "new_release_tag")

    def test_missing_latest_release_falls_back_to_2026_06(self):
        self._write_release("2026_06", "g", "fallback_release_tag")

        worker, (rows, total) = self._run(year="2026_07")

        self.assertEqual(worker.dataset_year, "2026_06")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["general"], "fallback_release_tag")

    def test_fallback_uses_one_complete_release_for_all_ratings(self):
        self._write_release("2026_07", "g", "partial_latest_tag")
        self._write_release("2026_06", "g", "fallback_general_tag")
        self._write_release("2026_06", "s", "fallback_sensitive_tag")

        worker, (rows, total) = self._run(
            year="2026_07",
            ratings=("g", "s"),
        )

        self.assertEqual(worker.dataset_year, "2026_06")
        self.assertEqual(total, 2)
        self.assertEqual(
            {row["general"] for row in rows},
            {"fallback_general_tag", "fallback_sensitive_tag"},
        )

    def test_fallback_reaches_2025_and_keeps_metadata_compatibility(self):
        self._write_release(
            "2025",
            "g",
            "legacy_release_tag",
            drop_columns=("meta", "image_width", "image_height"),
            metadata="legacy_metadata",
        )

        worker, (rows, total) = self._run(year="2026_07")

        self.assertEqual(worker.dataset_year, "2025")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["general"], "legacy_release_tag")
        self.assertEqual(rows[0]["image_width"], "")
        self.assertEqual(rows[0]["image_height"], "")

    def test_fallback_uses_2026_before_2025(self):
        self._write_release("2026", "g", "full_release_tag")
        self._write_release("2025", "g", "oldest_release_tag")

        worker, (rows, total) = self._run(year="2026_07")

        self.assertEqual(worker.dataset_year, "2026")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["general"], "full_release_tag")

    def test_release_missing_required_schema_falls_back_as_a_whole(self):
        self._write_release(
            "2026_07",
            "g",
            "invalid_latest_tag",
            drop_columns=("artist",),
        )
        self._write_release("2026_06", "g", "valid_fallback_tag")

        worker, (rows, total) = self._run(year="2026_07")

        self.assertEqual(worker.dataset_year, "2026_06")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["general"], "valid_fallback_tag")

    def test_replacing_a_release_file_invalidates_the_dataframe_cache(self):
        self._write_release("2026_07", "g", "before_update")
        _, (first_rows, _) = self._run(year="2026_07")
        path = self.data_dir / "danbooru_2026_07_g.parquet"
        previous_mtime = path.stat().st_mtime_ns

        self._write_release("2026_07", "g", "after_update")
        os.utime(
            path,
            ns=(path.stat().st_atime_ns, previous_mtime + 2_000_000_000),
        )
        _, (second_rows, _) = self._run(year="2026_07")

        self.assertEqual(first_rows[0]["general"], "before_update")
        self.assertEqual(second_rows[0]["general"], "after_update")

    def test_no_compatible_release_emits_a_terminal_empty_result(self):
        self._write_release(
            "2026_07",
            "g",
            "invalid_release_tag",
            drop_columns=("copyright",),
        )

        _, (rows, total) = self._run(year="2026_07")

        self.assertEqual(rows, [])
        self.assertEqual(total, 0)


if __name__ == "__main__":
    unittest.main()

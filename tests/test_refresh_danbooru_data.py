"""Regression tests for the Search/Event dataset refresh transaction."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from tools.refresh_danbooru_data import EVENT_COLUMNS, SEARCH_COLUMNS, main, validate_manifest


def _post(post_id: int, rating: str, parent_id=None) -> dict:
    return {
        "id": post_id,
        "parent_id": parent_id,
        "rating": rating,
        "image_width": 1024,
        "image_height": 768,
        "score": post_id,
        "fav_count": post_id // 2,
        "tag_string_general": f"post_{post_id}",
        "tag_string_character": "test_character",
        "tag_string_copyright": "test_series",
        "tag_string_artist": "test_artist",
        "tag_string_meta": "",
        "has_children": parent_id is None,
        "has_visible_children": parent_id is None,
    }


class DanbooruDatasetRefreshTests(unittest.TestCase):
    def test_builds_search_and_cross_rating_complete_event_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "posts.parquet"
            output = root / "runtime"
            frame = pd.DataFrame(
                [
                    _post(1, "g"),
                    _post(2, "s", 1),
                    _post(3, "q"),
                    _post(4, "q", 3),
                    _post(5, "e"),
                    _post(6, "e", 5),
                    _post(7, "g", 1),
                ]
            )
            frame["parent_id"] = frame["parent_id"].astype("Int64")
            frame.to_parquet(source, index=False)

            with redirect_stdout(StringIO()):
                result = main(
                    [
                        "posts",
                        "--source",
                        str(source),
                        "--output-dir",
                        str(output),
                        "--dataset-label",
                        "test_release",
                        "--source-url",
                        "https://example.test/posts.parquet",
                        "--source-revision",
                        "immutable-test-revision",
                        "--snapshot-at",
                        "2026-07-13T00:00:00Z",
                        "--batch-rows",
                        "3",
                        "--row-group-rows",
                        "2",
                    ]
                )
            self.assertEqual(result, 0)

            manifest_path = output / "dataset_manifest.json"
            manifest = validate_manifest(manifest_path, output)
            self.assertEqual(len(manifest["artifacts"]), 8)
            self.assertEqual(manifest["source"]["revision"], "immutable-test-revision")

            search_s = pq.read_table(output / "danbooru_test_release_s.parquet")
            self.assertEqual(tuple(search_s.column_names), SEARCH_COLUMNS)
            self.assertEqual(search_s.num_rows, 1)

            event_s = pq.read_table(output / "danbooru_sorted" / "danbooru_s.parquet")
            self.assertEqual(tuple(event_s.column_names), EVENT_COLUMNS)
            self.assertEqual(set(event_s["id"].to_pylist()), {1, 2})
            self.assertEqual(
                set(event_s["parent_id"].drop_null().to_pylist()),
                {1},
            )

            stored = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(stored["build"]["cross_rating_parent_duplication"])


if __name__ == "__main__":
    unittest.main()

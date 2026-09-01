"""Event Gen parquet shard regression tests."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

from core.event_data_loader import EventDataLoader


def _event_row(post_id: int, *, parent_id=None, rating: str = "g") -> dict:
    return {
        "id": post_id,
        "parent_id": parent_id,
        "has_children": parent_id is None,
        "has_visible_children": parent_id is None,
        "tag_string_general": f"event_{post_id}",
        "tag_string_character": "",
        "tag_string_copyright": "",
        "tag_string_artist": "",
        "tag_string_meta": "",
        "rating": rating,
        "score": post_id,
        "fav_count": 0,
        "image_width": 1024,
        "image_height": 1024,
    }


class EventDataLoaderTests(unittest.TestCase):
    def test_cross_rating_parent_copies_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = _event_row(10)
            pd.DataFrame([parent, _event_row(11, parent_id=10, rating="g")]).to_parquet(
                root / "danbooru_g.parquet", index=False
            )
            pd.DataFrame([parent, _event_row(12, parent_id=10, rating="s")]).to_parquet(
                root / "danbooru_s.parquet", index=False
            )

            loader = EventDataLoader(str(root))
            with redirect_stdout(StringIO()):
                frame = loader.load_parquets_by_rating(["g", "s"])

            self.assertEqual(len(frame), 3)
            self.assertEqual(frame["id"].nunique(), 3)
            self.assertEqual(set(loader.parents_df["id"]), {10})
            self.assertEqual(set(loader.parent_child_map[10]), {11, 12})


if __name__ == "__main__":
    unittest.main()

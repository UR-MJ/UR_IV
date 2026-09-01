"""Pure merge checks for the Danbooru tag asset updater."""

from __future__ import annotations

import unittest

from tools.refresh_danbooru_tag_assets import (
    Relationship,
    TagRecord,
    _merge_tags,
    _resolved_alias_map,
)


class DanbooruTagAssetRefreshTests(unittest.TestCase):
    def test_official_alias_chains_resolve_to_one_canonical_tag(self):
        relations = [
            Relationship(2, "old_name", "middle_name", "2026-09-01"),
            Relationship(1, "middle_name", "canonical_name", "2026-09-01"),
        ]

        self.assertEqual(
            _resolved_alias_map(relations),
            {
                "middle_name": "canonical_name",
                "old_name": "canonical_name",
            },
        )

    def test_daily_counts_overlay_pyu_and_official_aliases_remove_old_rows(self):
        pyu = {
            "canonical_name": TagRecord(0, 10, {"informal_name"}),
            "old_name": TagRecord(0, 9, set()),
        }
        daily = {
            "canonical_name": TagRecord(4, 25, {"fresh_alias"}),
            "daily_only": TagRecord(5, 7, set()),
        }

        merged, stats = _merge_tags(
            pyu,
            daily,
            {"old_name": "canonical_name"},
        )

        self.assertNotIn("old_name", merged)
        self.assertEqual(merged["canonical_name"].category, 4)
        self.assertEqual(merged["canonical_name"].count, 25)
        self.assertEqual(
            merged["canonical_name"].aliases,
            {"informal_name", "fresh_alias", "old_name"},
        )
        self.assertIn("daily_only", merged)
        self.assertEqual(stats["daily_only_tags_added"], 1)


if __name__ == "__main__":
    unittest.main()

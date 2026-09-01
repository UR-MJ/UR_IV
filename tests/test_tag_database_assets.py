"""Regression checks for the bundled, cleaned tag database."""

from __future__ import annotations

import re
import unittest

from core.tag_database import TagAsset, get_tag_database


class BundledTagDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = get_tag_database()

    def test_manifest_and_every_registered_asset_are_valid(self):
        self.assertEqual(self.database.validate_assets(), [])

    def test_data_paths_use_readable_lowercase_snake_case_names(self):
        for path in self.database.root.rglob("*"):
            if not path.is_file() or path.name == "README.md":
                continue
            self.assertRegex(path.name, r"^[a-z0-9_]+\.[a-z0-9]+$")

        root_files = {path.name for path in self.database.root.iterdir() if path.is_file()}
        self.assertEqual(root_files, {"README.md", "manifest.json"})

    def test_consolidated_groups_are_unique_and_scrape_artifact_free(self):
        frame = self.database.read_parquet(TagAsset.TAG_GROUPS)

        self.assertEqual(len(frame), 13_921)
        self.assertEqual(len(frame), len(frame.drop_duplicates(["group", "tag"])))
        artifact_pattern = re.compile(
            r"(?i)(?:^/|https?://|^howto:|^list_of_|^tn$|wiki_pages|media_assets)"
        )
        self.assertFalse(frame["tag"].astype(str).str.contains(artifact_pattern).any())

    def test_implications_contain_only_unique_active_runtime_pairs(self):
        frame = self.database.read_parquet(TagAsset.TAG_IMPLICATIONS)

        self.assertEqual(len(frame), 24_831)
        self.assertEqual(len(frame), len(frame.drop_duplicates()))
        self.assertFalse((frame["antecedent"] == frame["consequent"]).any())

    def test_character_migrations_preserve_expected_records(self):
        profiles = self.database.read_json(TagAsset.CHARACTER_PROFILES)
        features = self.database.read_parquet(TagAsset.CHARACTER_FEATURES)
        prompt_tags = self.database.read_parquet(TagAsset.CHARACTER_PROMPT_TAGS)
        extended_series = self.database.read_parquet(TagAsset.EXTENDED_CHARACTER_SERIES)

        self.assertEqual(len(profiles), 34_014)
        self.assertEqual(len(features), 28_836)
        self.assertEqual(len(prompt_tags), 98_809)
        self.assertEqual(prompt_tags["character"].nunique(), 98_809)
        self.assertTrue(prompt_tags["description"].astype(str).str.strip().ne("").all())
        self.assertEqual(len(extended_series), 120_901)
        self.assertEqual(extended_series["character"].nunique(), 120_901)

    def test_character_tag_lists_are_order_preserving_and_duplicate_free(self):
        profiles = self.database.read_json(TagAsset.CHARACTER_PROFILES)
        features = self.database.read_parquet(TagAsset.CHARACTER_FEATURES)
        prompt_tags = self.database.read_parquet(TagAsset.CHARACTER_PROMPT_TAGS)

        def assert_unique(values, label):
            normalized = [str(value).strip().casefold() for value in values if str(value).strip()]
            self.assertEqual(len(normalized), len(set(normalized)), label)

        for entry in profiles:
            assert_unique(entry.get("core_tags") or [], entry.get("tag", "profile"))
        for character, value in features[["character", "features"]].itertuples(
            index=False, name=None
        ):
            assert_unique(str(value).split(","), character)
        for character, value in prompt_tags[["character", "description"]].itertuples(
            index=False, name=None
        ):
            assert_unique(str(value).split(","), character)

    def test_lexicons_have_no_exact_duplicate_lines(self):
        assets = (
            TagAsset.APPEARANCE_TAGS_CURATED,
            TagAsset.APPEARANCE_TAGS_EXTENDED,
            TagAsset.CLOTHING_TAGS_CURATED,
            TagAsset.CLOTHING_TAGS_EXTENDED,
            TagAsset.COLOR_TERMS_CURATED,
            TagAsset.COLOR_TERMS_EXTENDED,
        )
        for asset in assets:
            values = self.database.read_lines(asset)
            normalized = [value.casefold() for value in values]
            self.assertEqual(len(normalized), len(set(normalized)), asset.value)


if __name__ == "__main__":
    unittest.main()

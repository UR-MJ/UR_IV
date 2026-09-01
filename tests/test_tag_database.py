from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.tag_database import (
    DEFAULT_TAG_DATABASE,
    TagAsset,
    TagDatabase,
    get_tag_database,
)


class TagDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_manifest(self, assets):
        (self.root / "manifest.json").write_text(
            json.dumps({"version": 1, "assets": assets}, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def descriptor(path: str, asset_format: str, *, columns=None):
        value = {
            "path": path,
            "format": asset_format,
            "description": f"Fixture for {path}",
        }
        if columns is not None:
            value["columns"] = columns
        return value

    def test_construction_is_lazy_and_custom_getter_is_isolated(self):
        database = TagDatabase(self.root / "not-created")

        self.assertEqual(database.root, (self.root / "not-created").resolve())
        self.assertIs(get_tag_database(), DEFAULT_TAG_DATABASE)
        self.assertIsNot(get_tag_database(self.root), DEFAULT_TAG_DATABASE)

        with self.assertRaises(FileNotFoundError):
            database.path(TagAsset.META_TAGS)

    def test_reads_json_lines_and_projected_parquet_through_manifest(self):
        (self.root / "data").mkdir()
        (self.root / "data" / "meta.json").write_text(
            json.dumps({"tags": ["highres", "translated"]}),
            encoding="utf-8",
        )
        (self.root / "data" / "colors.txt").write_text(
            " red \n\nblue\n",
            encoding="utf-8",
        )
        pd.DataFrame(
            {"tag": ["alpha", "beta"], "translation": ["알파", "베타"]}
        ).to_parquet(self.root / "data" / "korean.parquet", index=False)
        self.write_manifest(
            {
                TagAsset.META_TAGS.value: self.descriptor("data/meta.json", "json"),
                TagAsset.COLOR_TERMS_CURATED.value: self.descriptor(
                    "data/colors.txt", "text"
                ),
                TagAsset.KOREAN_TAG_CATALOG.value: self.descriptor(
                    "data/korean.parquet",
                    "parquet",
                    columns=["tag", "translation"],
                ),
            }
        )
        database = TagDatabase(self.root)

        self.assertEqual(
            database.read_json(TagAsset.META_TAGS),
            {"tags": ["highres", "translated"]},
        )
        self.assertEqual(
            database.read_lines(TagAsset.COLOR_TERMS_CURATED),
            ["red", "blue"],
        )
        frame = database.read_parquet(
            TagAsset.KOREAN_TAG_CATALOG,
            columns=["translation"],
        )
        self.assertEqual(frame.columns.tolist(), ["translation"])
        self.assertEqual(frame["translation"].tolist(), ["알파", "베타"])

    def test_rejects_unknown_assets_wrong_readers_and_path_traversal(self):
        self.write_manifest(
            {
                TagAsset.META_TAGS.value: self.descriptor("../secret.json", "json"),
                TagAsset.OBJECT_TAGS.value: self.descriptor("objects.json", "json"),
            }
        )
        database = TagDatabase(self.root)

        with self.assertRaisesRegex(ValueError, "unknown tag asset"):
            database.path("not_an_asset")
        with self.assertRaisesRegex(ValueError, "unsafe asset path"):
            database.path(TagAsset.META_TAGS)
        with self.assertRaisesRegex(ValueError, "expected format"):
            database.read_lines(TagAsset.OBJECT_TAGS)

    def test_loads_group_and_implication_indexes(self):
        pd.DataFrame(
            {
                "group": ["hair", "hair", "hair", "pose", None, ""],
                "tag": ["long_hair", "short_hair", "long_hair", "standing", "x", "y"],
            }
        ).to_parquet(self.root / "groups.parquet", index=False)
        pd.DataFrame(
            {
                "antecedent": ["smile", "smile", "grin", "smile", None],
                "consequent": ["happy", "mouth", "smile", "happy", "ignored"],
            }
        ).to_parquet(self.root / "implications.parquet", index=False)
        self.write_manifest(
            {
                TagAsset.TAG_GROUPS.value: self.descriptor(
                    "groups.parquet", "parquet", columns=["group", "tag"]
                ),
                TagAsset.TAG_IMPLICATIONS.value: self.descriptor(
                    "implications.parquet",
                    "parquet",
                    columns=["antecedent", "consequent"],
                ),
            }
        )
        database = TagDatabase(self.root)

        self.assertEqual(
            database.load_tag_groups(),
            {
                "hair": {"long_hair", "short_hair"},
                "pose": {"standing"},
            },
        )
        self.assertEqual(
            database.load_active_implications(),
            {
                "smile": {"happy", "mouth"},
                "grin": {"smile"},
            },
        )
        self.assertEqual(
            database.all_group_tags(),
            {"long_hair", "short_hair", "standing"},
        )

    def test_validate_assets_accepts_complete_fixture(self):
        pd.DataFrame({"group": ["body"], "tag": ["eyes"]}).to_parquet(
            self.root / "groups.parquet", index=False
        )
        pd.DataFrame({"antecedent": ["wink"], "consequent": ["one_eye_closed"]}).to_parquet(
            self.root / "implications.parquet", index=False
        )
        (self.root / "generic.json").write_text("{}", encoding="utf-8")

        assets = {
            asset.value: self.descriptor("generic.json", "json")
            for asset in TagAsset
        }
        assets[TagAsset.TAG_GROUPS.value] = self.descriptor(
            "groups.parquet", "parquet", columns=["group", "tag"]
        )
        assets[TagAsset.TAG_IMPLICATIONS.value] = self.descriptor(
            "implications.parquet",
            "parquet",
            columns=["antecedent", "consequent"],
        )
        self.write_manifest(assets)

        self.assertEqual(TagDatabase(self.root).validate_assets(), [])

    def test_validate_assets_reports_manifest_file_and_schema_problems(self):
        pd.DataFrame({"wrong": ["value"]}).to_parquet(
            self.root / "groups.parquet", index=False
        )
        self.write_manifest(
            {
                TagAsset.TAG_GROUPS.value: self.descriptor(
                    "groups.parquet", "parquet", columns=["group", "tag"]
                ),
                TagAsset.META_TAGS.value: {
                    "path": "missing.json",
                    "format": "json",
                    "description": "",
                    "columns": "not-a-list",
                },
                "retired_asset": self.descriptor("retired.json", "json"),
            }
        )

        errors = TagDatabase(self.root).validate_assets()

        self.assertTrue(any("manifest entry is missing" in error for error in errors))
        self.assertIn("retired_asset: unknown asset identifier", errors)
        self.assertTrue(any("description must be" in error for error in errors))
        self.assertTrue(any("columns must be" in error for error in errors))
        self.assertTrue(any("file does not exist" in error for error in errors))
        self.assertTrue(
            any("tag_groups: missing columns" in error for error in errors)
        )

    def test_validate_assets_returns_manifest_error_instead_of_raising(self):
        self.write_manifest({})
        (self.root / "manifest.json").write_text(
            json.dumps({"version": 999, "assets": {}}),
            encoding="utf-8",
        )

        errors = TagDatabase(self.root).validate_assets()

        self.assertEqual(len(errors), 1)
        self.assertIn("unsupported manifest version", errors[0])


if __name__ == "__main__":
    unittest.main()

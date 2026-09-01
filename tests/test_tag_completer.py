from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from utils.tag_completer import TagCompleter


class TagCompleterManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "autocomplete").mkdir()
        (self.root / "taxonomy").mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_fixture(self, *, include_manifest_aliases: bool) -> None:
        catalog = self.root / "autocomplete" / "catalog.csv"
        catalog.write_text(
            "\n".join(
                (
                    "shared zeta,0,1,",
                    "shared alpha,4,999,",
                    "shared beta,3,999,",
                    "shared aaa,1,999,",
                    "shared gamma,5,999,",
                    "rank alpha,0,1,",
                    "rank zeta,0,1000,",
                    'space tag,0,50,"legacy name"',
                    'wrong target,0,2,"primary alias"',
                )
            ),
            encoding="utf-8",
        )
        assets = {
            "autocomplete_catalog": {
                "path": "autocomplete/catalog.csv",
                "format": "csv",
                "description": "completion fixture",
                "columns": ["tag", "category", "count", "aliases"],
                "header": False,
            }
        }
        if include_manifest_aliases:
            pd.DataFrame(
                {"alias": ["primary alias"], "canonical": ["space tag"]}
            ).to_parquet(self.root / "taxonomy" / "aliases.parquet", index=False)
            assets["tag_aliases"] = {
                "path": "taxonomy/aliases.parquet",
                "format": "parquet",
                "description": "alias fixture",
                "columns": ["alias", "canonical"],
            }
        (self.root / "manifest.json").write_text(
            json.dumps({"version": 1, "assets": assets}),
            encoding="utf-8",
        )

    def make_completer(self) -> TagCompleter:
        unloaded = SimpleNamespace(is_loaded=False)
        with patch("utils.tag_data.get_tag_data", return_value=unloaded):
            return TagCompleter(str(self.root))

    def test_manifest_aliases_categories_counts_and_spaces_are_normalised(self):
        self.write_fixture(include_manifest_aliases=True)

        completer = self.make_completer()

        self.assertEqual(
            completer.get_suggestions("shared", max_count=5),
            [
                "shared_zeta",
                "shared_alpha",
                "shared_beta",
                "shared_aaa",
                "shared_gamma",
            ],
        )
        self.assertEqual(
            completer.get_suggestions("rank", max_count=2),
            ["rank_zeta", "rank_alpha"],
        )
        self.assertEqual(
            completer.get_suggestions("primary alias"),
            ["space_tag"],
        )
        self.assertTrue(completer.is_valid_tag("space tag"))
        self.assertTrue(completer.is_valid_tag("space_tag"))

    def test_old_manifest_falls_back_to_csv_aliases(self):
        self.write_fixture(include_manifest_aliases=False)

        completer = self.make_completer()

        self.assertEqual(
            completer.get_suggestions("legacy name"),
            ["space_tag"],
        )


if __name__ == "__main__":
    unittest.main()

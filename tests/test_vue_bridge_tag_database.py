from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import pandas as pd

from ui.vue_bridge import VueBridge


class _DatabaseFixture:
    def read_lines(self, _asset):
        return []

    def read_parquet(self, _asset, columns=None):
        frame = pd.DataFrame({"tag": ["1girl", "abandoned"]})
        return frame if columns is None else frame[list(columns)]

    def all_group_tags(self):
        return set()


class _ClassifierFixture:
    tag_to_category = {}
    characters = set()
    copyrights = set()
    artists = set()


class VueBridgeTagDatabaseTests(unittest.TestCase):
    def test_exclude_preview_keeps_general_korean_catalog_tags(self):
        with (
            patch(
                "core.tag_database.get_tag_database",
                return_value=_DatabaseFixture(),
            ),
            patch(
                "core.tag_classifier.TagClassifier",
                return_value=_ClassifierFixture(),
            ),
        ):
            bridge = VueBridge()
            matches = json.loads(bridge.getExcludeMatches("*1girl"))

        self.assertEqual(matches, ["1girl"])


if __name__ == "__main__":
    unittest.main()

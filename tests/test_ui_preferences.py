"""UI 설정의 저장 기본값과 허용값 계약."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.config_migration import load_ui_prefs, save_ui_prefs


class IconAnimationPreferenceTests(unittest.TestCase):
    def test_missing_setting_defaults_to_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui_prefs.json"

            prefs = load_ui_prefs(str(path))

            self.assertEqual(prefs["iconAnimationStyle"], "none")

    def test_supported_styles_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui_prefs.json"

            for style in ("none", "claude", "gpt"):
                with self.subTest(style=style):
                    save_ui_prefs(
                        str(path),
                        {"iconAnimationStyle": style, "keepMe": "preserved"},
                    )
                    prefs = load_ui_prefs(str(path))
                    self.assertEqual(prefs["iconAnimationStyle"], style)
                    self.assertEqual(prefs["keepMe"], "preserved")

    def test_unknown_style_fails_closed_to_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui_prefs.json"
            path.write_text(
                json.dumps(
                    {"schema_version": 1, "iconAnimationStyle": "surprise"}
                ),
                encoding="utf-8",
            )

            prefs = load_ui_prefs(str(path))

            self.assertEqual(prefs["iconAnimationStyle"], "none")


if __name__ == "__main__":
    unittest.main()

"""회귀 방지: Vue로 대체된 숨은 PyQt 탭을 다시 만들지 않는다."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LegacyUiRetirementTests(unittest.TestCase):
    def test_search_tab_is_fully_retired(self):
        setup = (ROOT / "ui" / "generator_ui_setup.py").read_text(encoding="utf-8")
        settings = (ROOT / "ui" / "generator_settings.py").read_text(encoding="utf-8")
        tabs_init = (ROOT / "tabs" / "__init__.py").read_text(encoding="utf-8")

        self.assertFalse((ROOT / "tabs" / "search_tab.py").exists())
        self.assertNotIn("from tabs.search_tab import SearchTab", setup)
        self.assertNotIn("self.search_tab", setup)
        self.assertNotIn("self.search_tab", settings)
        self.assertNotIn("search_criteria", settings)
        self.assertNotIn("SearchTab", tabs_init)

    def test_unused_automation_controller_is_retired(self):
        actions = (ROOT / "ui" / "generator_actions.py").read_text(encoding="utf-8")

        self.assertFalse((ROOT / "core" / "automation_controller.py").exists())
        self.assertNotIn("core.automation_controller", actions)

    def test_noop_queue_v2_mirror_is_retired(self):
        main = (ROOT / "ui" / "generator_main.py").read_text(encoding="utf-8")

        self.assertFalse((ROOT / "core" / "generation_queue_v2.py").exists())
        self.assertNotIn("_setup_queue_v2_bridge", main)
        self.assertNotIn('register_service("queue_v2"', main)


if __name__ == "__main__":
    unittest.main()

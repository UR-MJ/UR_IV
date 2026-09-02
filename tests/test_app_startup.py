from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from core.app_startup import prepare_application


ROOT = Path(__file__).resolve().parents[1]


class AppStartupTests(unittest.TestCase):
    def test_prepare_stops_before_data_when_requirements_fail(self) -> None:
        with (
            patch("core.check_requirements.main", return_value=7),
            patch("core.fetch_data.ensure_data") as fetch,
        ):
            self.assertEqual(7, prepare_application())
        fetch.assert_not_called()

    def test_prepare_checks_requirements_then_data(self) -> None:
        order: list[str] = []
        with (
            patch("core.check_requirements.main", side_effect=lambda: order.append("deps") or 0),
            patch("core.fetch_data.ensure_data", side_effect=lambda: order.append("data") or 0),
        ):
            self.assertEqual(0, prepare_application())
        self.assertEqual(["deps", "data"], order)

    def test_launchers_delegate_preparation_after_instance_registration(self) -> None:
        for entrypoint in ("new_main_ui.py", "web_main_ui.py"):
            source = (ROOT / entrypoint).read_text(encoding="utf-8")
            with self.subTest(entrypoint=entrypoint):
                self.assertLess(
                    source.index("register_app_instance"),
                    source.index("prepare_application"),
                )
                self.assertLess(
                    source.index("prepare_application"),
                    source.index("from config import"),
                )

        for launcher in ("new_run_main_ui.bat", "run_gui.bat", "run_WEB_gui.bat"):
            source = (ROOT / launcher).read_text(encoding="utf-8")
            with self.subTest(launcher=launcher):
                self.assertNotIn("core\\check_requirements.py", source)
                self.assertNotIn("core\\fetch_data.py", source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from unittest import mock

from core.mode_aware_mixin import ModeAwareMixin


class _ExampleModeSettings(ModeAwareMixin):
    settings_base_filename = "example"

    def collect_current_settings(self) -> dict:
        return {}

    def apply_settings(self, settings: dict) -> None:
        self.applied = settings


class ModeAwareStorageTests(unittest.TestCase):
    def test_load_returns_false_when_legacy_migration_path_is_unavailable(self) -> None:
        subject = _ExampleModeSettings()
        with mock.patch(
            "core.storage_paths.config_file",
            side_effect=OSError("migration denied"),
        ):
            self.assertFalse(subject.load_mode_settings("webui"))


if __name__ == "__main__":
    unittest.main()

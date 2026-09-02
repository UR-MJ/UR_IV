from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.storage_paths import (
    StorageMigrationError,
    StoragePathError,
    StoragePaths,
)


class StoragePathsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(self._temporary.name).resolve()
        self.paths = StoragePaths(self.project_root)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_each_storage_class_resolves_under_its_boundary(self) -> None:
        cases = (
            (self.paths.config_file, "config", "ui/prefs.json"),
            (self.paths.user_data_file, "user_data", "presets/character.json"),
            (self.paths.cache_file, "cache", "search/results.json"),
            (self.paths.log_file, "logs", "crash/latest.log"),
        )

        for resolver, directory, name in cases:
            with self.subTest(directory=directory):
                actual = resolver(name)
                expected = self.project_root / directory / Path(name)
                self.assertEqual(actual, expected)
                self.assertTrue(actual.parent.is_dir())

    def test_all_storage_classes_reject_traversal_and_absolute_names(self) -> None:
        resolvers = (
            self.paths.config_file,
            self.paths.user_data_file,
            self.paths.cache_file,
            self.paths.log_file,
        )
        invalid_names = (
            "",
            ".",
            "../outside.json",
            "nested/../../outside.json",
            r"nested\..\outside.json",
            str((self.project_root / "absolute.json").resolve()),
            r"C:drive-relative.json",
            r"C:\absolute.json",
        )

        for resolver in resolvers:
            for name in invalid_names:
                with self.subTest(resolver=resolver.__name__, name=name):
                    with self.assertRaises(StoragePathError):
                        resolver(name)

    def test_migrates_first_existing_legacy_file_and_is_idempotent(self) -> None:
        legacy = self.project_root / "legacy" / "ui_prefs.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"theme":"dark"}', encoding="utf-8")

        destination = self.paths.config_file(
            "ui_prefs.json",
            legacy_paths=("missing.json", legacy),
        )

        self.assertEqual(destination.read_text(encoding="utf-8"), '{"theme":"dark"}')
        self.assertFalse(legacy.exists())
        self.assertEqual(
            self.paths.config_file("ui_prefs.json", legacy_paths=legacy),
            destination,
        )

    def test_existing_destination_wins_without_touching_legacy(self) -> None:
        destination = self.paths.user_data_file("presets.json")
        destination.write_text("destination", encoding="utf-8")
        legacy = self.project_root / "presets.json"
        legacy.write_text("legacy", encoding="utf-8")

        resolved = self.paths.user_data_file("presets.json", legacy_paths=legacy)

        self.assertEqual(resolved.read_text(encoding="utf-8"), "destination")
        self.assertEqual(legacy.read_text(encoding="utf-8"), "legacy")

    def test_existing_directory_cannot_masquerade_as_a_storage_file(self) -> None:
        directory = self.project_root / "config" / "settings.json"
        directory.mkdir(parents=True)

        with self.assertRaises(StoragePathError):
            self.paths.config_file("settings.json")

    def test_failed_migration_preserves_source_and_leaves_no_partial_file(self) -> None:
        legacy = self.project_root / "old-settings.json"
        legacy.write_text("important", encoding="utf-8")
        destination = self.project_root / "config" / "settings.json"

        with mock.patch("core.storage_paths.os.replace", side_effect=OSError("blocked")):
            with self.assertRaises(StorageMigrationError):
                self.paths.config_file("settings.json", legacy_paths=legacy)

        self.assertEqual(legacy.read_text(encoding="utf-8"), "important")
        self.assertFalse(destination.exists())
        self.assertEqual(list(destination.parent.glob(".settings.json.migrating-*")), [])

    def test_legacy_source_outside_project_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "settings.json"
            outside.write_text("external", encoding="utf-8")

            with self.assertRaises(StoragePathError):
                self.paths.config_file("settings.json", legacy_paths=outside)

            self.assertTrue(outside.exists())
            self.assertFalse((self.project_root / "config" / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()

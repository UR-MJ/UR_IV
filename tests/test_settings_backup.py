from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core.settings_backup import (
    SettingsBackupError,
    export_settings_archive,
    import_settings_archive,
    resolve_import_target,
)
from tabs.settings_tab import SettingsTab
from ui.generator_main import GeneratorMainUI


class SettingsBackupTests(unittest.TestCase):
    def test_round_trip_includes_config_and_nested_creator_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            (root / "config").mkdir(parents=True)
            (root / "user_data/creator").mkdir(parents=True)
            prompt = root / "config/prompt_settings.json"
            comic = root / "user_data/creator/comic_studio.json"
            prompt.write_text('{"steps": 24}', encoding="utf-8")
            comic.write_text('{"title": "test"}', encoding="utf-8")
            archive = Path(temporary) / "settings.zip"

            self.assertEqual(export_settings_archive(archive, project_root=root), 2)
            prompt.unlink()
            comic.unlink()

            self.assertEqual(import_settings_archive(archive, project_root=root), 2)
            self.assertEqual(prompt.read_text(encoding="utf-8"), '{"steps": 24}')
            self.assertEqual(comic.read_text(encoding="utf-8"), '{"title": "test"}')

    def test_traversal_and_windows_alternate_stream_names_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(SettingsBackupError):
                resolve_import_target(root, "wildcards/../outside.txt")
            with self.assertRaises(SettingsBackupError):
                resolve_import_target(root, "wildcards/file:stream.txt")

    def test_import_rejects_entries_over_the_size_limit_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            archive = Path(temporary) / "oversized.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("config/ui_prefs.json", b"1234")

            with mock.patch("core.settings_backup.MAX_BACKUP_FILE_BYTES", 3):
                with self.assertRaises(SettingsBackupError):
                    import_settings_archive(archive, project_root=root)
            self.assertFalse((root / "config/ui_prefs.json").exists())

    def test_import_rejects_a_symlink_escape_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            external = base / "external"
            (root / "wildcards").mkdir(parents=True)
            external.mkdir()
            link = root / "wildcards/link"
            try:
                os.symlink(external, link, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")
            archive = base / "escape.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("wildcards/link/victim.txt", "unsafe")

            with self.assertRaises(SettingsBackupError):
                import_settings_archive(archive, project_root=root)
            self.assertFalse((external / "victim.txt").exists())

    def test_imported_settings_skip_the_next_shutdown_autosave(self) -> None:
        subject = SimpleNamespace(
            _preserve_imported_settings_on_quit=True,
            save_settings=mock.Mock(),
            ui_state=SimpleNamespace(save_all=mock.Mock()),
        )

        self.assertFalse(GeneratorMainUI._save_shutdown_state(subject))
        subject.save_settings.assert_not_called()
        subject.ui_state.save_all.assert_not_called()

    def test_imported_settings_skip_restart_button_autosave(self) -> None:
        subject = SimpleNamespace(
            parent_ui=SimpleNamespace(_preserve_imported_settings_on_quit=True),
            save_all_settings=mock.Mock(),
        )

        self.assertFalse(SettingsTab._save_before_restart(subject))
        subject.save_all_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()

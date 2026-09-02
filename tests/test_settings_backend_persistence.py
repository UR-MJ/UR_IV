from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from backends import BackendType
from ui.generator_settings import SettingsMixin, migrate_legacy_gallery_folder


class SettingsBackendPersistenceTests(unittest.TestCase):
    def test_legacy_gallery_path_moves_only_when_ui_prefs_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompt_path = root / "prompt_settings.json"
            prefs_path = root / "ui_prefs.json"
            settings = {"gallery_folder": r"D:\legacy-gallery", "steps": 20}
            prompt_path.write_text(json.dumps(settings), encoding="utf-8")

            selected = migrate_legacy_gallery_folder(
                settings,
                prompt_settings_path=str(prompt_path),
                ui_prefs_path=str(prefs_path),
            )

            self.assertEqual(selected, r"D:\legacy-gallery")
            self.assertEqual(
                json.loads(prefs_path.read_text(encoding="utf-8"))["galleryFolder"],
                r"D:\legacy-gallery",
            )
            self.assertNotIn(
                "gallery_folder",
                json.loads(prompt_path.read_text(encoding="utf-8")),
            )

    def test_current_gallery_path_wins_over_legacy_prompt_setting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompt_path = root / "prompt_settings.json"
            prefs_path = root / "ui_prefs.json"
            settings = {"gallery_folder": r"D:\legacy-gallery", "steps": 20}
            prompt_path.write_text(json.dumps(settings), encoding="utf-8")
            prefs_path.write_text(
                json.dumps({"schema_version": 1, "galleryFolder": r"E:\current"}),
                encoding="utf-8",
            )

            selected = migrate_legacy_gallery_folder(
                settings,
                prompt_settings_path=str(prompt_path),
                ui_prefs_path=str(prefs_path),
            )

            self.assertEqual(selected, r"E:\current")
            self.assertEqual(
                json.loads(prefs_path.read_text(encoding="utf-8"))["galleryFolder"],
                r"E:\current",
            )
            self.assertNotIn(
                "gallery_folder",
                json.loads(prompt_path.read_text(encoding="utf-8")),
            )

    def test_webui_and_comfy_paths_round_trip_through_helpers(self) -> None:
        mixin = object.__new__(SettingsMixin)
        with (
            mock.patch.object(config, "WEBUI_API_URL", "http://forge.test:7860"),
            mock.patch.object(config, "COMFYUI_API_URL", "http://comfy.test:8188"),
            mock.patch.object(config, "COMFYUI_WORKFLOW_PATH", r"C:\flows\t2i.json"),
            mock.patch.object(
                config,
                "COMFYUI_WORKFLOW_IMG2IMG_PATH",
                r"C:\flows\i2i.json",
            ),
        ):
            self.assertEqual(mixin._get_webui_url(), "http://forge.test:7860")
            self.assertEqual(mixin._get_comfyui_url(), "http://comfy.test:8188")
            self.assertEqual(
                mixin._get_comfyui_workflow_path(),
                r"C:\flows\t2i.json",
            )
            self.assertEqual(
                mixin._get_comfyui_workflow_img2img_path(),
                r"C:\flows\i2i.json",
            )

    def test_restore_webui_preserves_all_backend_path_settings(self) -> None:
        mixin = object.__new__(SettingsMixin)
        settings = {
            "backend_type": "webui",
            "webui_url": "http://forge.custom:7788",
            "comfyui_url": "http://comfy.custom:8199",
            "comfyui_workflow_path": r"D:\flows\txt2img.json",
            "comfyui_workflow_img2img_path": r"D:\flows\img2img.json",
        }

        with (
            mock.patch("backends.set_backend") as set_backend,
            mock.patch.object(config, "WEBUI_API_URL", "http://old-forge"),
            mock.patch.object(config, "COMFYUI_API_URL", "http://old-comfy"),
            mock.patch.object(config, "COMFYUI_WORKFLOW_PATH", "old-t2i"),
            mock.patch.object(config, "COMFYUI_WORKFLOW_IMG2IMG_PATH", "old-i2i"),
        ):
            mixin._restore_backend_settings(settings)

            self.assertEqual(config.WEBUI_API_URL, settings["webui_url"])
            self.assertEqual(config.COMFYUI_API_URL, settings["comfyui_url"])
            self.assertEqual(
                config.COMFYUI_WORKFLOW_PATH,
                settings["comfyui_workflow_path"],
            )
            self.assertEqual(
                config.COMFYUI_WORKFLOW_IMG2IMG_PATH,
                settings["comfyui_workflow_img2img_path"],
            )
            set_backend.assert_called_once_with(
                BackendType.WEBUI,
                settings["webui_url"],
            )

    def test_restore_comfy_uses_comfy_endpoint(self) -> None:
        mixin = object.__new__(SettingsMixin)
        settings = {
            "backend_type": "comfyui",
            "webui_url": "http://forge.custom:7788",
            "comfyui_url": "http://comfy.custom:8199",
            "comfyui_workflow_path": r"D:\flows\txt2img.json",
            "comfyui_workflow_img2img_path": r"D:\flows\img2img.json",
        }

        with mock.patch("backends.set_backend") as set_backend:
            mixin._restore_backend_settings(settings)

        set_backend.assert_called_once_with(
            BackendType.COMFYUI,
            settings["comfyui_url"],
        )


if __name__ == "__main__":
    unittest.main()

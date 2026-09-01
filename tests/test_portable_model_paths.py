import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tabs.editor import mosaic_panel


class TestPortableYoloModelPaths(unittest.TestCase):
    def _patched_paths(self, root: Path):
        models = root / "Editor_models"
        return patch.multiple(
            mosaic_panel,
            _PROJECT_ROOT=str(root),
            _EDITOR_MODELS_DIR=str(models),
            _YOLO_CONFIG_PATH=str(models / "yolo_config.json"),
        )

    def test_relative_config_resolves_on_current_project(self):
        with tempfile.TemporaryDirectory() as temp, self._patched_paths(Path(temp)):
            root = Path(temp)
            models = root / "Editor_models"
            models.mkdir()
            model = models / "detector.pt"
            model.write_bytes(b"model")
            (models / "yolo_config.json").write_text(
                json.dumps({"model_paths": ["Editor_models/detector.pt"]}),
                encoding="utf-8",
            )

            self.assertEqual(mosaic_panel._load_yolo_model_paths(), [str(model)])

    def test_old_absolute_path_migrates_by_filename(self):
        with tempfile.TemporaryDirectory() as temp, self._patched_paths(Path(temp)):
            root = Path(temp)
            models = root / "Editor_models"
            models.mkdir()
            model = models / "detector.pt"
            model.write_bytes(b"model")
            (models / "yolo_config.json").write_text(
                json.dumps({"model_paths": [r"X:\Users\Legacy\App\Editor_models\detector.pt"]}),
                encoding="utf-8",
            )

            self.assertEqual(mosaic_panel._load_yolo_model_paths(), [str(model)])

    def test_project_model_is_saved_as_forward_slash_relative_path(self):
        with tempfile.TemporaryDirectory() as temp, self._patched_paths(Path(temp)):
            root = Path(temp)
            models = root / "Editor_models"
            models.mkdir()
            model = models / "detector.pt"
            model.write_bytes(b"model")

            mosaic_panel._save_yolo_model_paths([str(model)])

            saved = json.loads((models / "yolo_config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["model_paths"], ["Editor_models/detector.pt"])


if __name__ == "__main__":
    unittest.main()

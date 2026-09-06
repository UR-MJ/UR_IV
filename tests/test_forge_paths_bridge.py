import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QObject

from core import forge_modules
from ui.vue_bridge import VueBridge
from ui.widget_proxies import ComboBoxProxy, LineEditProxy


class _WebParent(QObject):
    def __init__(self):
        super().__init__()
        self.web_mode = True


class TestForgePathsBridge(unittest.TestCase):
    def _payload(self, root: Path) -> dict[str, str]:
        payload = {}
        for key in forge_modules.FORGE_PATH_KEYS:
            path = root / key
            path.mkdir()
            payload[key] = str(path)
        (root / "checkpoint_dir" / "model.safetensors").write_bytes(b"")
        (root / "lora_dir" / "style.safetensors").write_bytes(b"")
        (root / "vae_dir" / "vae.safetensors").write_bytes(b"")
        (root / "text_encoder_dir" / "clip.safetensors").write_bytes(b"")
        return payload

    def test_save_get_and_reset_return_structured_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "forge_model_paths.json"
            payload = self._payload(root)
            bridge = VueBridge()

            with patch.object(forge_modules, "FORGE_PATHS_FILE", config):
                saved = json.loads(bridge.saveForgeModelPaths(json.dumps(payload)))
                loaded = json.loads(bridge.getForgeModelPaths())
                reset = json.loads(bridge.resetForgeModelPaths())

            self.assertTrue(saved["ok"])
            self.assertEqual(saved["paths"], payload)
            self.assertEqual(
                {key: saved["entries"][key]["count"] for key in forge_modules.FORGE_PATH_KEYS},
                {key: 1 for key in forge_modules.FORGE_PATH_KEYS},
            )
            self.assertTrue(loaded["ok"])
            self.assertFalse(config.exists())
            self.assertTrue(reset["ok"])

    def test_invalid_payload_reports_field_errors_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "forge_model_paths.json"
            bridge = VueBridge()

            with patch.object(forge_modules, "FORGE_PATHS_FILE", config):
                response = json.loads(bridge.saveForgeModelPaths(json.dumps({
                    "checkpoint_dir": "relative/path",
                })))

            self.assertFalse(response["ok"])
            self.assertIn("checkpoint_dir", response["errors"])
            self.assertFalse(config.exists())

    def test_invalid_directory_picker_key_is_rejected(self):
        response = json.loads(VueBridge().selectForgeModelDirectory("not-a-forge-key"))
        self.assertFalse(response["ok"])
        self.assertIn("지원하지 않는", response["error"])

    def test_web_mode_rejects_all_legacy_model_path_slots_without_side_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "forge_model_paths.json"
            original_root = root / "original"
            replacement_root = root / "replacement"
            original_root.mkdir()
            replacement_root.mkdir()
            original = self._payload(original_root)
            replacement = self._payload(replacement_root)
            forge_modules.save_forge_paths(original, config_path=config, environ={})
            original_config = config.read_bytes()
            parent = _WebParent()
            bridge = VueBridge(parent)

            with (
                patch.object(forge_modules, "FORGE_PATHS_FILE", config),
                patch(
                    "ui.native_dialogs.select_directory",
                    return_value=str(root / "picked"),
                ) as picker,
                patch.object(bridge, "_refresh_forge_module_widgets") as refresh,
            ):
                replies = {
                    "get": json.loads(bridge.getForgeModelPaths()),
                    "select": json.loads(
                        bridge.selectForgeModelDirectory("checkpoint_dir")
                    ),
                    "save": json.loads(
                        bridge.saveForgeModelPaths(json.dumps(replacement))
                    ),
                    "reset": json.loads(bridge.resetForgeModelPaths()),
                    "refresh": json.loads(bridge.refreshForgeModelPaths()),
                }

            for name, reply in replies.items():
                self.assertFalse(reply["ok"], name)
                self.assertIn("웹 모드", reply["error"], name)
                self.assertNotIn("paths", reply, name)
            self.assertTrue(config.exists())
            self.assertEqual(config.read_bytes(), original_config)
            picker.assert_not_called()
            refresh.assert_not_called()

    def test_refresh_replaces_removed_vae_selection_with_default(self):
        bridge = VueBridge()
        proxy = ComboBoxProxy(bridge, "vae_main_combo")
        te_proxy = LineEditProxy(bridge, "te_main_input")
        proxy.addItems(["Use checkpoint default", "old.safetensors"])
        proxy.setCurrentText("old.safetensors")
        te_proxy.setText("old-clip.safetensors")
        pushed = []
        bridge.widgetValueChanged.connect(lambda widget_id, value: pushed.append((widget_id, value)))

        with (
            patch.object(forge_modules, "list_vae_files", return_value=["new.safetensors"]),
            patch.object(forge_modules, "list_te_files", return_value=[]),
        ):
            bridge._refresh_forge_module_widgets()

        self.assertEqual(proxy.currentText(), "Use checkpoint default")
        self.assertEqual(te_proxy.text(), "")
        self.assertIn(("vae_main_combo", "Use checkpoint default"), pushed)
        self.assertIn(("te_main_input", ""), pushed)


if __name__ == "__main__":
    unittest.main()

"""Metadata-to-UI action contracts using tiny local fixtures, never generation."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, PngImagePlugin

from tests.test_image_metadata import graph_fixture
from ui.generator_main import GeneratorMainUI
from ui.model_download_actions import ModelDownloadActionsMixin
from ui.vue_bridge import VueBridge


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _Widget:
    def __init__(self, value):
        self.value = str(value)

    def text(self):
        return self.value

    toPlainText = text
    currentText = text

    def setText(self, value):
        self.value = str(value)

    setPlainText = setText
    setCurrentText = setText


class _Bridge:
    getImageExif = VueBridge.getImageExif
    _parse_params_line = VueBridge._parse_params_line

    def __init__(self):
        self.showNotification = _Signal()


class _Harness(ModelDownloadActionsMixin):
    _handle_vue_action = GeneratorMainUI._handle_vue_action
    _handle_immediate_generation_from_raw = GeneratorMainUI._handle_immediate_generation_from_raw
    _build_queue_payload_from_exif = GeneratorMainUI._build_queue_payload_from_exif
    _apply_payload_to_ui = GeneratorMainUI._apply_payload_to_ui

    def __init__(self):
        self.vue_bridge = _Bridge()
        self.started = []
        self.transferred = []
        self.queued = []
        self.queue_panel = SimpleNamespace(add_single_item=self.queued.append)
        for name, value in {
            "main_prompt_text": "existing positive", "total_prompt_display": "existing positive",
            "neg_prompt_text": "existing negative", "steps_input": 20, "cfg_input": 7,
            "seed_input": -1, "width_input": 1024, "height_input": 1024,
            "sampler_combo": "old sampler", "scheduler_combo": "old scheduler",
            "model_combo": "keep-model.safetensors",
        }.items():
            setattr(self, name, _Widget(value))
        self._vue_lora_entries = [{"name": "keep-lora", "weight": 0.75}]

    def _handle_chat_action(self, _action, _payload):
        return False

    def _handle_creator_action(self, _action, _payload):
        return False

    def handle_prompt_only_transfer(self, prompt, negative):
        self.transferred.append((prompt, negative))

    def update_total_prompt_display(self):
        self.total_prompt_display.setPlainText(self.main_prompt_text.toPlainText())

    def start_generation(self):
        self.started.append({
            "prompt": self.total_prompt_display.toPlainText(),
            "negative": self.neg_prompt_text.toPlainText(),
            "steps": self.steps_input.text(), "cfg": self.cfg_input.text(),
            "seed": self.seed_input.text(), "width": self.width_input.text(),
            "height": self.height_input.text(), "sampler": self.sampler_combo.currentText(),
            "scheduler": self.scheduler_combo.currentText(),
            "model": self.model_combo.currentText(), "loras": list(self._vue_lora_entries),
        })


class ComfyMetadataActionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "metadata.png"
        self.host = _Harness()

    def metadata(self, graph=None, **chunks):
        if graph is not None:
            chunks["prompt"] = json.dumps(graph, ensure_ascii=False)
        metadata = PngImagePlugin.PngInfo()
        for key, value in chunks.items():
            metadata.add_text(key, value)
        Image.new("RGB", (8, 8), "blue").save(self.path, pnginfo=metadata)
        return json.loads(self.host.vue_bridge.getImageExif(str(self.path)))

    def test_comfy_immediate_generation_keeps_parameters_out_of_negative_and_preserves_current_model_loras(self):
        info = self.metadata(graph_fixture())
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.host._handle_vue_action("pnginfo_generate", info)
        self.assertEqual(self.host.started, [{
            "prompt": "a blue bird", "negative": "bad anatomy", "steps": "28", "cfg": "6.5",
            "seed": "42", "width": "640", "height": "832", "sampler": "euler",
            "scheduler": "normal", "model": "keep-model.safetensors",
            "loras": [{"name": "keep-lora", "weight": 0.75}],
        }])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_ambiguous_comfy_metadata_does_not_apply_even_a_known_negative_branch(self):
        graph = graph_fixture()
        graph["7"] = {"class_type": "UnknownPromptEncoder", "inputs": {"text": "do not guess"}}
        info = self.metadata(graph)
        self.assertFalse(info["can_apply"])
        self.assertEqual(info["negative"], "bad anatomy")
        for action, payload in (
            ("pnginfo_send_prompt", info),
            ("pnginfo_generate", info),
            ("pull_prompt_from_image", {"path": str(self.path)}),
            ("add_image_to_queue", {"path": str(self.path)}),
            ("gallery_send_exif_to_t2i", {"metadata": info, "exif": info["raw"], "path": str(self.path)}),
        ):
            with self.subTest(action=action):
                host = _Harness()
                host._handle_vue_action(action, payload)
                self.assertEqual(host.transferred, [])
                self.assertEqual(host.started, [])
                self.assertEqual(host.queued, [])
                self.assertTrue(host.vue_bridge.showNotification.calls)

    def test_gallery_path_legacy_payload_never_treats_comfy_graph_json_as_prompt(self):
        info = self.metadata(graph_fixture())
        self.host._handle_vue_action("gallery_send_exif_to_t2i", {
            "path": str(self.path), "exif": info["raw"],
        })
        self.assertEqual(self.host.transferred, [("a blue bird", "bad anatomy")])

    def test_queue_uses_typed_common_parameters_without_requiring_steps(self):
        graph = graph_fixture()
        graph["13"] = {"class_type": "KSampler", "inputs": {**graph["3"]["inputs"], "steps": 12, "seed": 43}}
        graph["19"] = {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0]}}
        graph["20"] = {"class_type": "SaveImage", "inputs": {"images": ["19", 0]}}
        info = self.metadata(graph)
        self.assertTrue(info["can_apply"])
        self.assertNotIn("Steps", info["parameters"])
        self.host._handle_vue_action("add_image_to_queue", {"path": str(self.path)})
        self.assertEqual(self.host.queued, [{
            "prompt": "a blue bird", "negative_prompt": "bad anatomy", "sampler_name": "euler",
            "scheduler": "normal", "steps": 20, "cfg_scale": 6.5, "seed": -1,
            "width": 640, "height": 832,
        }])

    def test_empty_comfy_positive_never_becomes_a_parameters_line_prompt(self):
        graph = graph_fixture()
        graph["7"]["inputs"]["text"] = ""
        self.metadata(graph)
        self.host._handle_vue_action("add_image_to_queue", {"path": str(self.path)})
        self.assertEqual(self.host.queued, [])

    def test_comfy_immediate_preserves_multiline_text_and_large_integer_seed(self):
        graph = graph_fixture()
        graph["7"]["inputs"]["text"] = "caption\nNegative prompt: printed on a sign\nSteps: the staircase"
        graph["3"]["inputs"]["seed"] = 18446744073709551615
        info = self.metadata(graph)
        self.host._handle_vue_action("pnginfo_generate", info)
        self.assertEqual(self.host.started[0]["prompt"], "caption\nNegative prompt: printed on a sign\nSteps: the staircase")
        self.assertEqual(self.host.started[0]["negative"], "bad anatomy")
        self.assertEqual(self.host.started[0]["seed"], "18446744073709551615")

    def test_bridge_preserves_raw_workflow_and_marks_malformed_graph_non_applicable(self):
        workflow = '{"nodes": [], "links": [], "extra": {"title": "keep"}}'
        malformed = '{"3": {not json'
        info = self.metadata(prompt=malformed, workflow=workflow)
        self.assertEqual(info["source"], "comfyui")
        self.assertEqual(info["raw_prompt"], malformed)
        self.assertEqual(info["raw_workflow"], workflow)
        self.assertEqual(info["prompt"], "")
        self.assertFalse(info["can_apply"])
        self.host._handle_vue_action("pnginfo_generate", info)
        self.assertEqual(self.host.started, [])

    def test_webui_metadata_priority_and_generation_remain_compatible_with_comfy_chunks(self):
        info = self.metadata(graph_fixture(), parameters=(
            "a WebUI cat\nNegative prompt: low quality\n"
            "Steps: 22, Sampler: Euler, CFG scale: 4.5, Seed: 17, Size: 768x512"
        ))
        self.assertEqual(info["source"], "webui")
        self.assertTrue(info["raw_prompt"])
        self.host._handle_vue_action("pnginfo_generate", info)
        generated = self.host.started[0]
        self.assertEqual((generated["prompt"], generated["negative"]), ("a WebUI cat", "low quality"))
        self.assertEqual((generated["steps"], generated["cfg"], generated["seed"]), ("22", "4.5", "17"))
        self.assertEqual((generated["width"], generated["height"]), ("768", "512"))


if __name__ == "__main__":
    unittest.main()

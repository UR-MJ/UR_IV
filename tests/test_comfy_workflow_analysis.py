"""The workflow picker must recognise the graphs produced by our compiler."""
import json
import unittest
from unittest import mock

from backends.comfyui_backend import analyze_workflow
from core import anima38
from core.comfy_workflow_compiler import ComfyWorkflowCompiler
from tests.test_comfy_anima38_compiler import _anima_capabilities, _modules, V2_MODEL
from tests.test_comfy_workflow_compiler import _capabilities


def _analyze(graph):
    with mock.patch("os.path.exists", return_value=True), mock.patch(
        "builtins.open", mock.mock_open(read_data=json.dumps(graph)),
    ):
        return analyze_workflow("in-memory-workflow.json")


class TestComfyWorkflowAnalysis(unittest.TestCase):
    def test_bundled_anima_graph_with_two_semantic_encoders(self):
        graph = ComfyWorkflowCompiler(_anima_capabilities()).compile("txt2img", V2_MODEL, {
            "prompt": "portrait", "negative_prompt": "bad",
            "forge_additional_modules": _modules(), "width": 768, "height": 512,
            "distilled_cfg_scale": 3,
            "alwayson_scripts": {anima38.SCRIPT_NAME: {"args": [{"negative": True}]}},
        })
        result = _analyze(graph)
        self.assertTrue(result["valid"], result["error"])
        self.assertEqual(result["ksampler_type"], "ForgeNeoKSamplerCNS")
        self.assertEqual(result["checkpoint"], V2_MODEL)
        self.assertEqual(result["classification"], "native_unet")
        self.assertFalse(result["is_locked"])
        self.assertEqual(result["model_param"], "model_name")
        self.assertEqual((result["width"], result["height"]), (768, 512))

    def test_default_checkpoint_graph_is_still_valid(self):
        graph = ComfyWorkflowCompiler(_capabilities()).compile(
            "txt2img", "checkpoint.safetensors", {"prompt": "cat"},
        )
        result = _analyze(graph)
        self.assertTrue(result["valid"], result["error"])
        self.assertEqual(result["classification"], "native_checkpoint")

    def test_web_graph_recognises_bundled_sampler_prompt_and_latent(self):
        result = _analyze({"nodes": [
            {"id": 1, "type": "ForgeNeoAnima38V2Loader", "widgets_values": [V2_MODEL]},
            {"id": 2, "type": "ForgeNeoAnima38V2Prompt", "widgets_values": ["portrait"]},
            {"id": 3, "type": "ForgeNeoLatentInput", "widgets_values": ["txt2img", 768, 512, 1]},
            {"id": 4, "type": "ForgeNeoKSamplerCNS", "widgets_values": []},
            {"id": 5, "type": "SaveImage", "widgets_values": []},
        ]})
        self.assertTrue(result["valid"], result["error"])
        self.assertEqual(result["checkpoint"], V2_MODEL)
        self.assertEqual((result["width"], result["height"]), (768, 512))

    def test_missing_sampler_is_not_made_valid(self):
        result = _analyze({"1": {"class_type": "SaveImage", "inputs": {}}})
        self.assertFalse(result["valid"])
        self.assertIn("KSampler", result["error"])

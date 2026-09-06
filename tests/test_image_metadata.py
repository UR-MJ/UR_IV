"""Image metadata contracts exercised through tiny PNG files, never model execution."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, PngImagePlugin

from core.image_metadata import extract_from_file


def graph_fixture():
    return {
        "99": {"class_type": "CLIPTextEncode", "inputs": {"text": "unused decoy"}},
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "shared/model.safetensors"}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad anatomy", "clip": ["1", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "a blue bird", "clip": ["1", 1]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 640, "height": 832, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["7", 0], "negative": ["8", 0], "latent_image": ["5", 0], "seed": 42, "steps": 28, "cfg": 6.5, "sampler_name": "euler", "scheduler": "normal", "denoise": 1}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0]}},
    }


class ImageMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.png"

    def png(self, **metadata):
        info = PngImagePlugin.PngInfo()
        for key, value in metadata.items():
            info.add_text(key, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        Image.new("RGB", (8, 8), "blue").save(self.path, pnginfo=info)
        return self.path

    def test_comfy_api_follows_sampler_links_not_node_order_and_preserves_source(self):
        graph = graph_fixture()
        workflow = {"nodes": [], "links": [], "extra": {"label": "keep me"}}
        self.png(prompt=graph, workflow=workflow)
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        meta = extract_from_file(self.path)
        self.assertEqual(meta.prompt, "a blue bird")
        self.assertEqual(meta.negative_prompt, "bad anatomy")
        self.assertEqual(meta.parameters["Seed"], 42)
        self.assertEqual(meta.parameters["Size"], "640x832")
        self.assertEqual(meta.parameters["Model"], "shared/model.safetensors")
        self.assertEqual(meta.prompt_graph, graph)
        self.assertEqual(meta.workflow, workflow)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_multiple_sampler_prompts_are_separate_not_arbitrarily_selected(self):
        graph = graph_fixture()
        graph["17"] = {"class_type": "CLIPTextEncode", "inputs": {"text": "a red cat"}}
        graph["13"] = {"class_type": "KSampler", "inputs": {**graph["3"]["inputs"], "positive": ["17", 0], "seed": 43}}
        graph["19"] = {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0]}}
        graph["20"] = {"class_type": "SaveImage", "inputs": {"images": ["19", 0]}}
        self.png(prompt=graph)
        meta = extract_from_file(self.path)
        self.assertEqual(meta.prompt, "")
        self.assertEqual(meta.negative_prompt, "bad anatomy")
        self.assertNotIn("Seed", meta.parameters)
        self.assertEqual({item["prompt"] for item in meta.prompt_candidates}, {"a blue bird", "a red cat"})
        self.assertTrue(meta.metadata_warnings)

    def test_sdxl_distinct_encoders_and_conditioning_zero_are_not_merged(self):
        graph = graph_fixture()
        graph["7"] = {"class_type": "CLIPTextEncodeSDXL", "inputs": {"text_g": "global scene", "text_l": "local detail"}}
        graph["6"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["8", 0]}}
        graph["3"]["inputs"]["negative"] = ["6", 0]
        self.png(prompt=graph)
        meta = extract_from_file(self.path)
        self.assertEqual(meta.prompt, "")
        self.assertEqual(meta.negative_prompt, "")
        candidate = meta.prompt_candidates[0]
        self.assertEqual([part["text"] for part in candidate["positive_parts"]], ["global scene", "local detail"])
        self.assertFalse(candidate["positive_known"])
        self.assertTrue(candidate["negative_known"])
        self.assertTrue(meta.metadata_warnings)

    def test_sampler_custom_advanced_uses_guider_roles_and_noise_scheduler(self):
        graph = graph_fixture()
        graph["21"] = {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["7", 0], "negative": ["8", 0], "cfg": 4}}
        graph["22"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 99}}
        graph["23"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "dpmpp_2m"}}
        graph["24"] = {"class_type": "BasicScheduler", "inputs": {"steps": 18, "scheduler": "karras", "denoise": 0.7}}
        graph["3"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["21", 0], "noise": ["22", 0], "sampler": ["23", 0], "sigmas": ["24", 0], "latent_image": ["5", 0]}}
        self.png(prompt=graph)
        meta = extract_from_file(self.path)
        self.assertEqual((meta.prompt, meta.negative_prompt), ("a blue bird", "bad anatomy"))
        self.assertEqual(meta.parameters["Seed"], 99)
        self.assertEqual(meta.parameters["Steps"], 18)
        self.assertEqual(meta.parameters["CFG scale"], 4)

    def test_workflow_only_png_reads_links_and_known_widget_layouts(self):
        nodes = [
            {"id": 1, "type": "CLIPTextEncode", "widgets_values": ["workflow positive"], "inputs": []},
            {"id": 2, "type": "CLIPTextEncode", "widgets_values": ["workflow negative"], "inputs": []},
            {"id": 3, "type": "KSampler", "widgets_values": [314, "randomize", 24, 7, "euler", "normal", 1],
             "inputs": [{"name": "positive", "link": 11}, {"name": "negative", "link": 12}]},
            {"id": 4, "type": "VAEDecode", "inputs": [{"name": "samples", "link": 13}]},
            {"id": 5, "type": "SaveImage", "inputs": [{"name": "images", "link": 14}]},
        ]
        workflow = {"nodes": nodes, "links": [[11, 1, 0, 3, 0, "CONDITIONING"], [12, 2, 0, 3, 1, "CONDITIONING"], [13, 3, 0, 4, 0, "LATENT"], [14, 4, 0, 5, 0, "IMAGE"]]}
        self.png(workflow=workflow)
        meta = extract_from_file(self.path)
        self.assertEqual((meta.prompt, meta.negative_prompt), ("workflow positive", "workflow negative"))
        self.assertEqual(meta.parameters["Seed"], 314)
        self.assertEqual(meta.parameters["Steps"], 24)
        self.assertEqual(meta.workflow, workflow)

    def test_ui_contract_keeps_raw_graphs_and_normalized_fields_separate(self):
        from core.image_metadata import read_metadata_for_ui
        graph = graph_fixture()
        self.png(prompt=graph, workflow={"nodes": [], "extra": {"keep": True}})
        data = read_metadata_for_ui(self.path)
        self.assertEqual(data["prompt"], "a blue bird")
        self.assertEqual(data["negative"], "bad anatomy")
        self.assertEqual(data["source"], "comfyui")
        self.assertEqual(data["parameters"]["Seed"], 42)
        self.assertIn("Steps: 28", data["params_line"])
        self.assertEqual(json.loads(data["raw_prompt"]), graph)
        self.assertTrue(data["raw_workflow"])
        self.assertTrue(data["can_apply"])

    def test_webui_priority_preserves_comfy_raw_and_negative_free_parameters(self):
        raw = "a WebUI cat\nSteps: 20, Sampler: Euler, CFG scale: 7, Seed: 12"
        graph = graph_fixture()
        self.png(parameters=raw, prompt=graph)
        meta = extract_from_file(self.path)
        self.assertEqual(meta.prompt, "a WebUI cat")
        self.assertEqual(meta.parameters["Seed"], 12)
        self.assertEqual(meta.source, "webui")
        self.assertEqual(json.loads(meta.raw_prompt), graph)

    def test_controlnet_output_roles_and_linked_text_are_followed(self):
        graph = graph_fixture()
        graph["30"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "linked\npositive"}}
        graph["7"]["inputs"]["text"] = ["30", 0]
        graph["31"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": ["7", 0], "negative": ["8", 0]}}
        graph["3"]["inputs"].update(positive=["31", 0], negative=["31", 1])
        self.png(prompt=graph)
        meta = extract_from_file(self.path)
        self.assertEqual(meta.prompt, "linked\npositive")
        self.assertEqual(meta.negative_prompt, "bad anatomy")

    def test_unknown_custom_encoder_and_cycles_fail_closed(self):
        from core.image_metadata import read_metadata_for_ui
        for encoder in (
            {"class_type": "MysteryPromptExpansion", "inputs": {"text": "must not guess this", "conditioning": ["99", 0]}},
            {"class_type": "ConditioningSetArea", "inputs": {"conditioning": ["7", 0]}},
        ):
            graph = graph_fixture()
            graph["7"] = encoder
            self.png(prompt=graph)
            data = read_metadata_for_ui(self.path)
            self.assertEqual(data["prompt"], "")
            self.assertFalse(data["can_apply"])
            self.assertTrue(data["metadata_warnings"])
            self.assertEqual(json.loads(data["raw_prompt"]), graph)

    def test_malformed_graph_json_is_still_available_as_raw(self):
        from core.image_metadata import read_metadata_for_ui
        raw = '{"1": broken JSON'
        self.png(prompt=raw)
        data = read_metadata_for_ui(self.path)
        self.assertEqual(data["raw_prompt"], raw)
        self.assertEqual(data["prompt"], "")
        self.assertFalse(data["can_apply"])
        self.assertTrue(data["metadata_warnings"])

    def test_anima_semantic_nodes_preserve_positive_and_negative_roles(self):
        graph = graph_fixture()
        graph["7"] = {"class_type": "ForgeNeoAnima38V2Prompt", "inputs": {"prompt": "Anima positive"}}
        graph["8"] = {"class_type": "ForgeNeoAnimaQwen35Prompt", "inputs": {"prompt": "Anima negative"}}
        self.png(prompt=graph)
        meta = extract_from_file(self.path)
        self.assertEqual((meta.prompt, meta.negative_prompt), ("Anima positive", "Anima negative"))

    def test_sdxl_matching_encoder_text_can_be_applied_without_duplication(self):
        from core.image_metadata import read_metadata_for_ui
        graph = graph_fixture()
        graph["7"] = {"class_type": "CLIPTextEncodeSDXL", "inputs": {"text_g": "same scene", "text_l": "same scene"}}
        self.png(prompt=graph)
        data = read_metadata_for_ui(self.path)
        self.assertEqual(data["prompt"], "same scene")
        self.assertTrue(data["can_apply"])

    def test_comfy_transplant_keeps_original_graph_format_without_inventing_webui(self):
        from core.image_metadata import transplant
        graph = graph_fixture()
        self.png(prompt=graph)
        output = self.path.with_name("copy.png")
        self.assertTrue(transplant(self.path, self.path, output))
        meta = extract_from_file(output)
        self.assertEqual(meta.source, "comfyui")
        self.assertEqual(meta.prompt_graph, graph)
        self.assertEqual(meta.prompt, "a blue bird")

    def test_jpeg_webp_nested_exif_usercomment_remains_readable(self):
        raw = "EXIF positive\nNegative prompt: EXIF negative\nSteps: 30, Seed: 111"
        for suffix in (".jpg", ".webp"):
            path = self.path.with_suffix(suffix)
            exif = Image.Exif()
            exif[0x8769] = {0x9286: b"UNICODE\x00" + raw.encode("utf-16-be")}
            Image.new("RGB", (8, 8)).save(path, exif=exif)
            before = path.read_bytes()
            meta = extract_from_file(path)
            self.assertEqual((meta.prompt, meta.negative_prompt), ("EXIF positive", "EXIF negative"))
            self.assertEqual(meta.parameters["Seed"], 111)
            self.assertEqual(path.read_bytes(), before)

    def test_empty_webui_negative_does_not_swallow_parameter_line(self):
        self.png(parameters="a cat\nNegative prompt: \nSteps: 21, Seed: 222")
        meta = extract_from_file(self.path)
        self.assertEqual(meta.negative_prompt, "")
        self.assertEqual(meta.parameters["Seed"], 222)

    def test_basic_guider_h3_cache_node_fails_closed_without_opening_cache(self):
        from core.image_metadata import read_metadata_for_ui
        graph = graph_fixture()
        graph["6"] = {"class_type": "ForgeNeoH3ConditioningCacheLoad", "inputs": {"descriptor": '{"path":"C:/private/cache"}'}}
        graph["21"] = {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["6", 0]}}
        graph["3"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["21", 0]}}
        self.png(prompt=graph)
        data = read_metadata_for_ui(self.path)
        self.assertFalse(data["can_apply"])
        self.assertTrue(data["metadata_warnings"])

    def test_many_shared_conditioning_branches_obey_budget(self):
        from core.image_metadata import read_metadata_for_ui
        graph = graph_fixture()
        for number in range(100, 124):
            previous = str(number - 1) if number > 100 else "7"
            graph[str(number)] = {"class_type": "ConditioningCombine", "inputs": {"conditioning_1": [previous, 0], "conditioning_2": [previous, 0]}}
        graph["3"]["inputs"]["positive"] = ["123", 0]
        self.png(prompt=graph)
        data = read_metadata_for_ui(self.path)
        self.assertFalse(data["can_apply"])
        self.assertTrue(any("너무 많아" in warning for warning in data["metadata_warnings"]))

    def test_sampler_candidate_limit_cannot_turn_partial_read_into_safe_apply(self):
        from core.image_metadata import read_metadata_for_ui
        graph = graph_fixture()
        graph.pop("9")
        graph.pop("10")
        for number in range(1000, 1129):
            graph[str(number)] = {"class_type": "KSampler", "inputs": dict(graph["3"]["inputs"])}
        self.png(prompt=graph)
        data = read_metadata_for_ui(self.path)
        self.assertEqual(len(data["prompt_candidates"]), 128)
        self.assertFalse(data["can_apply"])
        self.assertTrue(data["metadata_ambiguous"])


if __name__ == "__main__":
    unittest.main()

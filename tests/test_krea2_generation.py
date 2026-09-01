import base64
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from backends.base import GenerationResult
from core.krea2_generation import run_krea2_generation


def _png_b64(color=(120, 40, 200)) -> str:
    output = BytesIO()
    Image.new("RGB", (2, 2), color).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _choice(*values):
    return [list(values)]


def _object_info() -> dict:
    node_types = {
        "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode",
        "ConditioningZeroOut", "EmptyLatentImage", "EmptySD3LatentImage",
        "KSampler", "VAEDecode", "SaveImage", "ImageCrop", "LoadImage",
        "VAEEncode", "LoraLoaderModelOnly", "Krea2EditGroundedEncode",
        "Krea2EditModelPatch",
    }
    result = {name: {"input": {"required": {}, "optional": {}}} for name in node_types}
    result["UNETLoader"]["input"]["required"] = {
        "unet_name": _choice(r"models\krea2_turbo_int8_convrot.safetensors"),
        "weight_dtype": _choice("default"),
    }
    result["CLIPLoader"]["input"]["required"] = {
        "clip_name": _choice(r"encoders\qwen3vl_4b_fp8_scaled.safetensors"),
        "type": _choice("stable_diffusion", "krea2"),
        "device": _choice("default", "cpu"),
    }
    result["VAELoader"]["input"]["required"] = {
        "vae_name": _choice(r"vae\qwen_image_vae.safetensors"),
    }
    result["LoraLoaderModelOnly"]["input"]["required"] = {
        "lora_name": _choice(
            r"Krea2\krea2_identity_edit_v1_2.safetensors",
            r"Krea2\Krea2_TextFusion_Refusal_Reduction.safetensors",
        ),
    }
    result["KSampler"]["input"]["required"] = {
        "sampler_name": _choice("euler", "heun", "dpmpp_sde", "dpmpp_2m_sde"),
        "scheduler": _choice("simple"),
    }
    return result


class _FakeComfy:
    def __init__(self, object_info=None):
        self.object_info = object_info or _object_info()
        self.uploads = []
        self.workflow = None
        self.progress_calls = []

    def get_backend_type(self):
        return "comfyui"

    def get_object_info(self):
        return self.object_info

    def upload_media(self, data, filename, mime):
        self.uploads.append((bytes(data), filename, mime))
        return f"uploads/{filename}"

    def run_workflow(self, workflow, progress_callback=None):
        self.workflow = workflow
        if progress_callback:
            progress_callback(4, 8, None)
            self.progress_calls.append((4, 8))
        return GenerationResult(
            success=True,
            image_data=b"generated-image",
            info={"prompt_id": "fake-prompt"},
        )


class Krea2GenerationTests(unittest.TestCase):
    def test_t2i_runs_official_graph_and_merges_metadata(self):
        backend = _FakeComfy()
        progress = []
        result = run_krea2_generation(
            backend,
            "t2i",
            {
                "prompt": "portrait, <lora:standard_only:1>, studio light",
                "negative_prompt": "watermark",
                "width": 1024,
                "height": 768,
                "steps": 8,
                "cfg_scale": 1,
                "seed": 42,
                "sampler_name": "Euler a",
            },
            lambda step, total, preview: progress.append((step, total, preview)),
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(backend.uploads, [])
        self.assertEqual(backend.workflow["4"]["inputs"]["text"], "portrait, studio light")
        self.assertEqual(
            backend.workflow["1"]["inputs"]["unet_name"],
            r"models\krea2_turbo_int8_convrot.safetensors",
        )
        self.assertEqual(backend.workflow["8"]["inputs"]["steps"], 8)
        self.assertEqual(backend.workflow["8"]["inputs"]["cfg"], 1)
        self.assertEqual(progress, [(4, 8, None)])
        self.assertEqual(result.info["mode"], "krea2_t2i")
        self.assertEqual(result.info["seed"], 42)
        self.assertEqual(result.info["width"], 1024)
        self.assertEqual(result.info["height"], 768)
        self.assertFalse(result.info["negative_prompt_applied"])

    def test_i2i_uploads_source_and_optional_reference_separately(self):
        backend = _FakeComfy()
        result = run_krea2_generation(
            backend,
            "i2i",
            {
                "prompt": "change the coat to blue",
                "init_images": [_png_b64((255, 0, 0))],
                "krea2_reference_image": "data:image/png;base64," + _png_b64((0, 0, 255)),
                "krea2_fidelity": 6.5,
                "width": 1000,
                "height": 760,
                "steps": 15,
                "cfg_scale": 1,
                "seed": 7,
            },
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(len(backend.uploads), 2)
        self.assertNotEqual(backend.uploads[0][1], backend.uploads[1][1])
        self.assertTrue(backend.uploads[0][1].startswith("krea2_source_"))
        self.assertTrue(backend.uploads[1][1].startswith("krea2_reference_"))
        self.assertEqual(backend.workflow["5"]["inputs"]["image"], f"uploads/{backend.uploads[0][1]}")
        self.assertEqual(backend.workflow["16"]["inputs"]["image"], f"uploads/{backend.uploads[1][1]}")
        self.assertEqual(backend.workflow["10"]["inputs"]["ref_boost"], 6.5)
        self.assertTrue(result.info["uses_reference_image"])

    def test_i2i_accepts_source_only_and_randomises_negative_seed(self):
        backend = _FakeComfy()
        with patch("core.krea2_generation.secrets.randbits", return_value=123456) as random_seed:
            result = run_krea2_generation(
                backend,
                "i2i",
                {
                    "prompt": "soft studio background",
                    "init_images": [_png_b64()],
                    "width": 1024,
                    "height": 1024,
                    "seed": -1,
                },
            )
        self.assertTrue(result.success, result.error)
        self.assertEqual(len(backend.uploads), 1)
        self.assertNotIn("16", backend.workflow)
        self.assertEqual(result.info["seed"], 123456)
        self.assertEqual(result.info["cfg_scale"], 1)
        self.assertFalse(result.info["uses_reference_image"])
        random_seed.assert_called_once_with(32)

    def test_seed_outside_app_replay_range_is_rejected(self):
        backend = _FakeComfy()
        result = run_krea2_generation(
            backend,
            "t2i",
            {"prompt": "test", "seed": 0x1_0000_0000},
        )
        self.assertFalse(result.success)
        self.assertIn("0~4294967295", result.error)
        self.assertIsNone(backend.workflow)

    def test_missing_custom_node_fails_before_queue(self):
        object_info = _object_info()
        object_info.pop("Krea2EditModelPatch")
        backend = _FakeComfy(object_info)
        result = run_krea2_generation(
            backend,
            "i2i",
            {"prompt": "edit", "init_images": [_png_b64()], "seed": 1},
        )
        self.assertFalse(result.success)
        self.assertIn("Krea2EditModelPatch", result.error)
        self.assertIsNone(backend.workflow)

    def test_missing_model_choice_has_specific_error(self):
        object_info = _object_info()
        object_info["UNETLoader"]["input"]["required"]["unet_name"] = _choice("other.safetensors")
        backend = _FakeComfy(object_info)
        result = run_krea2_generation(
            backend,
            "t2i",
            {"prompt": "test", "seed": 1},
        )
        self.assertFalse(result.success)
        self.assertIn("UNETLoader.unet_name", result.error)
        self.assertIsNone(backend.workflow)

    def test_non_comfy_backend_is_rejected_clearly(self):
        backend = _FakeComfy()
        backend.get_backend_type = lambda: "webui"
        result = run_krea2_generation(backend, "t2i", {"prompt": "test", "seed": 1})
        self.assertFalse(result.success)
        self.assertIn("ComfyUI 백엔드가 필요", result.error)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from ui.creator_actions import CreatorActionsMixin


class _UploadBackend:
    def __init__(self):
        self.uploads = []

    def upload_media(self, data, filename, mime):
        self.uploads.append((data, filename, mime))
        return f"studio/{filename}"


class CreatorActionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.actions = CreatorActionsMixin()

    def test_v2v_payload_uploads_video_and_identity_to_distinct_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "motion.mp4"
            identity = Path(tmp) / "face.png"
            video.write_bytes(b"video")
            identity.write_bytes(b"image")
            backend = _UploadBackend()

            params = self.actions._creator_prepare_params(
                backend,
                {
                    "mode": "h3_v2v",
                    "sourcePath": str(video),
                    "identityPath": str(identity),
                    "prompt": "walk forward",
                    "negative": "flicker",
                    "audioPrompt": "rain and footsteps",
                    "dialogue": "hello",
                    "seed": -1,
                    "includeAudio": True,
                },
            )

        self.assertEqual(params["input_video"], "studio/motion.mp4")
        self.assertEqual(params["input_image"], "studio/face.png")
        self.assertGreaterEqual(params["seed"], 0)
        self.assertTrue(params["generate_audio"])
        self.assertTrue(params["include_reference_audio"])
        self.assertIn("<Picture 1>", params["prompt"])
        self.assertIn("<Video 1>", params["prompt"])
        self.assertIn("<Audio 1>", params["prompt"])
        self.assertIn("Overall soundscape: rain and footsteps", params["prompt"])
        self.assertIn("Dialogue: hello", params["prompt"])
        self.assertIn("Avoid: flicker", params["prompt"])

    def test_krea_payload_keeps_source_and_reference_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jpg"
            reference = Path(tmp) / "identity.webp"
            source.write_bytes(b"source")
            reference.write_bytes(b"reference")
            backend = _UploadBackend()
            params = self.actions._creator_prepare_params(
                backend,
                {
                    "mode": "krea2",
                    "sourcePath": str(source),
                    "referencePath": str(reference),
                    "prompt": "change clothing",
                    "seed": 7,
                },
            )

        self.assertEqual(params["input_image"], "studio/source.jpg")
        self.assertEqual(params["reference_image"], "studio/identity.webp")
        self.assertEqual(params["seed"], 7)

    def test_required_node_check_reports_only_missing_types(self):
        with self.assertRaisesRegex(RuntimeError, "MissingNode"):
            self.actions._creator_check_nodes(
                {"required_node_types": ["LoadImage", "MissingNode"]},
                {"LoadImage"},
            )

    def test_comfy_combo_paths_are_replaced_with_server_native_separator(self):
        built = {
            "workflow": {
                "4": {
                    "class_type": "LoraLoaderModelOnly",
                    "inputs": {"lora_name": "Krea2/identity.safetensors"},
                }
            }
        }
        object_info = {
            "LoraLoaderModelOnly": {
                "input": {
                    "required": {
                        "lora_name": [["Krea2\\identity.safetensors"], {}]
                    }
                }
            }
        }
        self.actions._creator_resolve_comfy_choices(built, object_info)
        self.assertEqual(
            built["workflow"]["4"]["inputs"]["lora_name"],
            "Krea2\\identity.safetensors",
        )

    def test_comfy_model_choice_can_match_same_stem_packaging_variant(self):
        built = {
            "workflow": {
                "7": {
                    "class_type": "UpscaleModelLoader",
                    "inputs": {"model_name": "RealESRGAN_x4plus.safetensors"},
                }
            }
        }
        object_info = {
            "UpscaleModelLoader": {
                "input": {
                    "required": {
                        "model_name": [["RealESRGAN_x4plus.pth"], {}]
                    }
                }
            }
        }
        self.actions._creator_resolve_comfy_choices(built, object_info)
        self.assertEqual(
            built["workflow"]["7"]["inputs"]["model_name"],
            "RealESRGAN_x4plus.pth",
        )


if __name__ == "__main__":
    unittest.main()

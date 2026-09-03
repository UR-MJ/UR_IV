from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from comfy_custom_nodes.ai_studio_forge_parity import anima38_nodes


ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "comfy_custom_nodes" / "ai_studio_forge_parity"
VENDOR_ROOT = PACK_ROOT / "vendor" / "comfyui_anima_3_8b"

EXPECTED_VENDOR_SHA256 = {
    "__init__.py": "d4509cbd4a3eb386ca5997c7f894a96184330791e10c327790a0c97dd623bc93",
    "bundle_v2.py": "e870b6de094f01a1699c8418b92cf120ece767a8d7d5ec1e549d9288a890e8ae",
    "loader.py": "d3edaa86f3139fcedb85b2bbd6f6bda46b492c47b86301e19c492f8bdb9dbe26",
    "patches.py": "bae67382cfc91ae70d6f9168f4f8677aece66819933ef1d2c089fa9a276105f1",
    "progressive_cross_adapter.py": "aa35354ede00ee0ac7873c4b61568cac01bfe65282f21c4602dd7981ec71a57d",
    "prompt.py": "bb93e602d2311af2271d5780f1012b048ea3224e0fca398e55df0121f7d57d86",
    "semantic_connector_v2.py": "2647ea4e480ae1be8ac33344f2337de5c3ac4b420f65bfa03a563e2e2c64bda3",
    "semantic_v2_runtime.py": "548561f961351b0cc49d2b326f078c4e8d8565b3134e6c2888ef53b73403d89d",
    "v2.py": "edba33618664dfaa15005efa8b6be00cbc21a0cbbb4197bc20babf6fef5b5120",
    "text_encoder/__init__.py": "17f6136fde1806350597640006c2eac35a43e964f817bacf6fbbb86ea22630b0",
    "text_encoder/clip.py": "64ccb9d6cd5590a23c22b96b1bdb123feb66940a9c57d3a5d62e797d2419101c",
    "text_encoder/layers.py": "dd8977bce23d9ef95b5c835da52735551f1e7ca513281f21c2c861b4359bfdb4",
    "text_encoder/model.py": "210005c6f17d55f32211c6436c466a1afde3e8965dd3cf4815687771b91d2f50",
    "text_encoder/tokenizer.py": "b3d6c74c100e4734c363fa0055bfc932749928d5f1a3f67e6940af2e002d2e9e",
    "qwen35_tokenizer/tokenizer.json": "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42",
    "qwen35_tokenizer/tokenizer_config.json": "316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_lf_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class TestAnima38Vendoring(unittest.TestCase):
    def test_runtime_and_tokenizers_match_pinned_upstream_hashes(self):
        copied_runtime_files = {
            path.relative_to(VENDOR_ROOT).as_posix()
            for path in VENDOR_ROOT.rglob("*")
            if path.is_file() and path.suffix.casefold() in {".py", ".json"}
        }
        self.assertEqual(copied_runtime_files, set(EXPECTED_VENDOR_SHA256))
        actual = {
            relative: _sha256(VENDOR_ROOT / relative)
            for relative in EXPECTED_VENDOR_SHA256
        }
        self.assertEqual(actual, EXPECTED_VENDOR_SHA256)

    def test_required_license_texts_are_present_and_pinned(self):
        self.assertEqual(
            _sha256_lf_text(
                PACK_ROOT / "LICENSES" / "comfyui-anima-3-8B-MIT.txt"
            ),
            "8f5eca1d2d11b1812b80f2c28c1d0d9ed94e347f7e03411767729f86f86656a2",
        )
        self.assertEqual(
            _sha256_lf_text(
                PACK_ROOT / "LICENSES" / "Qwen3.5-Apache-2.0.txt"
            ),
            "50cbab8a892c5f2993b8c7351a99182507472def3b1374558308605d99b86b32",
        )
        notice = (PACK_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("381c13af328b958febf86c155d2f4b007cd0f55b", notice)
        self.assertIn("851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a", notice)

    def test_no_model_weight_is_vendored(self):
        weight_suffixes = {
            ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"
        }
        weights = [
            path.relative_to(VENDOR_ROOT).as_posix()
            for path in VENDOR_ROOT.rglob("*")
            if path.is_file() and path.suffix.casefold() in weight_suffixes
        ]
        self.assertEqual(weights, [])


class TestAnima38LazyWrappers(unittest.TestCase):
    def test_clean_process_import_does_not_load_heavy_runtime(self):
        program = """
import json
import sys
from comfy_custom_nodes.ai_studio_forge_parity import anima38_nodes
names = ("comfy", "folder_paths", "torch", "transformers", "safetensors")
print(json.dumps({
    "runtime_loaded": anima38_nodes._RUNTIME is not None,
    "heavy_modules": [name for name in names if name in sys.modules],
}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        state = json.loads(completed.stdout)
        self.assertEqual(state, {"runtime_loaded": False, "heavy_modules": []})

    def test_comfy_import_installs_only_lightweight_52_block_detection(self):
        program = """
import json
import sys
import types

comfy = types.ModuleType("comfy")
comfy.__path__ = []
model_detection = types.ModuleType("comfy.model_detection")
model_detection.detect_unet_config = (
    lambda state_dict, key_prefix, metadata=None:
    {"image_model": "anima", "num_blocks": 28}
)
folder_paths = types.ModuleType("folder_paths")
sys.modules["comfy"] = comfy
sys.modules["comfy.model_detection"] = model_detection
sys.modules["folder_paths"] = folder_paths

from comfy_custom_nodes.ai_studio_forge_parity import anima38_nodes

config = model_detection.detect_unet_config(
    {"net.blocks.51.attn.weight": object()}, "net."
)
vendor_prefix = anima38_nodes._VENDOR_MODULE
print(json.dumps({
    "detected_blocks": config["num_blocks"],
    "patch_marker": bool(getattr(
        model_detection.detect_unet_config,
        "_anima_qwen35_pro52_patch",
        False,
    )),
    "runtime_loaded": anima38_nodes._RUNTIME is not None,
    "vendor_loaded": any(
        name == vendor_prefix or name.startswith(vendor_prefix + ".")
        for name in sys.modules
    ),
    "heavy_modules": [
        name for name in ("torch", "transformers", "safetensors")
        if name in sys.modules
    ],
}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        state = json.loads(completed.stdout)
        self.assertEqual(state, {
            "detected_blocks": 52,
            "patch_marker": True,
            "runtime_loaded": False,
            "vendor_loaded": False,
            "heavy_modules": [],
        })

    def test_node_ids_and_static_io_contracts_are_exact(self):
        self.assertEqual(
            set(anima38_nodes.NODE_CLASS_MAPPINGS),
            {
                "ForgeNeoAnimaQwen35Loader",
                "ForgeNeoAnimaQwen35Prompt",
                "ForgeNeoAnima38V2Loader",
                "ForgeNeoAnima38V2Prompt",
            },
        )
        expected = {
            anima38_nodes.ForgeNeoAnimaQwen35Loader: (
                ("CLIP",), None, "load_clip", ("self", "qwen35_model")
            ),
            anima38_nodes.ForgeNeoAnimaQwen35Prompt: (
                ("CONDITIONING", "CONDITIONING"),
                ("expanded", "native"),
                "encode",
                (
                    "self", "model", "native_clip", "qwen35_clip",
                    "adapter_name", "prompt", "adapter_strength",
                ),
            ),
            anima38_nodes.ForgeNeoAnima38V2Loader: (
                ("MODEL",), None, "load_model", ("self", "model_name")
            ),
            anima38_nodes.ForgeNeoAnima38V2Prompt: (
                ("CONDITIONING", "CONDITIONING"),
                ("expanded", "native"),
                "encode",
                ("self", "model", "native_clip", "qwen35_clip", "prompt"),
            ),
        }
        for node, (return_types, return_names, function, parameters) in expected.items():
            with self.subTest(node=node.__name__):
                self.assertEqual(node.RETURN_TYPES, return_types)
                self.assertEqual(getattr(node, "RETURN_NAMES", None), return_names)
                self.assertEqual(node.FUNCTION, function)
                self.assertEqual(
                    tuple(inspect.signature(getattr(node, function)).parameters),
                    parameters,
                )

    def test_input_types_and_execution_delegate_to_exact_upstream_providers(self):
        calls = []

        class Loader:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"qwen35_model": (["qwen35.safetensors"],)}}

            def load_clip(self, qwen35_model):
                calls.append(("loader", qwen35_model))
                return ("qwen35-clip",)

        class Prompt:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {name: (kind,) for name, kind in (
                    ("model", "MODEL"), ("native_clip", "CLIP"),
                    ("qwen35_clip", "CLIP"), ("adapter_name", "COMBO"),
                    ("prompt", "STRING"), ("adapter_strength", "FLOAT"),
                )}}

            def encode(self, *args):
                calls.append(("prompt", args))
                return ("expanded", "native")

        class V2Loader:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"model_name": (["anima-v2.safetensors"],)}}

            def load_model(self, model_name):
                calls.append(("v2-loader", model_name))
                return ("model",)

        class V2Prompt:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {name: (kind,) for name, kind in (
                    ("model", "MODEL"), ("native_clip", "CLIP"),
                    ("qwen35_clip", "CLIP"), ("prompt", "STRING"),
                )}}

            def encode(self, *args):
                calls.append(("v2-prompt", args))
                return ("expanded-v2", "native-v2")

        runtime = SimpleNamespace(NODE_CLASS_MAPPINGS={
            "AnimaQwen35Loader": Loader,
            "AnimaQwen35UnifiedPrompt": Prompt,
            "Anima38BV2Loader": V2Loader,
            "Anima38BV2Prompt": V2Prompt,
        })
        with mock.patch.object(
            anima38_nodes, "ensure_anima38_runtime", return_value=runtime
        ):
            self.assertEqual(
                set(anima38_nodes.ForgeNeoAnimaQwen35Loader.INPUT_TYPES()["required"]),
                {"qwen35_model"},
            )
            self.assertEqual(
                set(anima38_nodes.ForgeNeoAnimaQwen35Prompt.INPUT_TYPES()["required"]),
                {
                    "model", "native_clip", "qwen35_clip", "adapter_name",
                    "prompt", "adapter_strength",
                },
            )
            self.assertEqual(
                set(anima38_nodes.ForgeNeoAnima38V2Loader.INPUT_TYPES()["required"]),
                {"model_name"},
            )
            self.assertEqual(
                set(anima38_nodes.ForgeNeoAnima38V2Prompt.INPUT_TYPES()["required"]),
                {"model", "native_clip", "qwen35_clip", "prompt"},
            )
            self.assertEqual(
                anima38_nodes.ForgeNeoAnimaQwen35Loader().load_clip("qwen35"),
                ("qwen35-clip",),
            )
            self.assertEqual(
                anima38_nodes.ForgeNeoAnimaQwen35Prompt().encode(
                    "model", "native", "qwen", "adapter", "prompt", 1.0
                ),
                ("expanded", "native"),
            )
            self.assertEqual(
                anima38_nodes.ForgeNeoAnima38V2Loader().load_model("bundle"),
                ("model",),
            )
            self.assertEqual(
                anima38_nodes.ForgeNeoAnima38V2Prompt().encode(
                    "model", "native", "qwen", "prompt"
                ),
                ("expanded-v2", "native-v2"),
            )
        self.assertEqual(
            [call[0] for call in calls],
            ["loader", "prompt", "v2-loader", "v2-prompt"],
        )

    def test_runtime_bootstrap_installs_patches_before_returning_provider(self):
        events = []
        model_detection = SimpleNamespace(
            detect_unet_config=lambda state_dict, key_prefix, metadata=None: {
                "image_model": "anima", "num_blocks": 28
            }
        )
        runtime = SimpleNamespace(
            NODE_CLASS_MAPPINGS={"Anima38BV2Loader": type("Provider", (), {})},
            install_pro52_model_detection=lambda: events.append("detect-52"),
        )
        semantic_runtime = SimpleNamespace(
            install_timestep_support=lambda: events.append("timestep-v2")
        )

        def import_module(name):
            events.append(f"import:{name}")
            if name == "comfy.model_detection":
                return model_detection
            if name == "folder_paths":
                return SimpleNamespace()
            if name == anima38_nodes._VENDOR_MODULE:
                return runtime
            if name == f"{anima38_nodes._VENDOR_MODULE}.semantic_v2_runtime":
                return semantic_runtime
            raise AssertionError(f"unexpected import: {name}")

        with mock.patch.object(anima38_nodes, "_RUNTIME", None), mock.patch.object(
            anima38_nodes.importlib, "import_module", side_effect=import_module
        ):
            provider = anima38_nodes._provider_class("Anima38BV2Loader")

        self.assertIs(provider, runtime.NODE_CLASS_MAPPINGS["Anima38BV2Loader"])
        self.assertEqual(
            events,
            [
                "import:comfy.model_detection",
                "import:folder_paths",
                "import:comfy.model_detection",
                f"import:{anima38_nodes._VENDOR_MODULE}",
                "detect-52",
                f"import:{anima38_nodes._VENDOR_MODULE}.semantic_v2_runtime",
                "timestep-v2",
            ],
        )
        self.assertTrue(getattr(
            model_detection.detect_unet_config,
            "_anima_qwen35_pro52_patch",
            False,
        ))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import gc
import copy
import importlib.util
import sys
import types
import unittest
import weakref
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from comfy_custom_nodes.ai_studio_forge_parity import anima38_nodes


VENDOR = (
    Path(__file__).resolve().parents[1]
    / "comfy_custom_nodes/ai_studio_forge_parity/vendor/comfyui_anima_3_8b"
)


class _Tensor:
    """Only the host tensor operations used by the conditioning protocol."""

    dtype = "float32"
    device = "cpu"

    def __init__(self, data=None, shape=(1, 3, 1024)):
        self.data = data
        self.shape = shape

    def to(self, *args, **kwargs):
        return self

    def reshape(self, *shape):
        if shape == (-1,) and isinstance(self.data, list):
            return _Tensor([value for row in self.data for value in row])
        return self

    def __getitem__(self, index):
        if isinstance(index, int):
            return self.data[index]
        return self


class _Adapter:
    _anima_v2_model_managed = True

    def __call__(self, source, *args, **kwargs):
        return source


class _NativeAdapter:
    embed = types.SimpleNamespace(weight=_Tensor())


class TestAnima38ConditioningCache(unittest.TestCase):
    """Run the pinned emit/forward protocol with a tiny CPU-only Comfy host."""

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        modules = {}
        for name in (
            "torch", "torch.nn", "torch.nn.functional", "safetensors",
            "safetensors.torch", "comfy", "comfy.model_management", "comfy.ops",
            "comfy.conds", "comfy.model_base", "comfy.ldm", "comfy.ldm.anima",
            "comfy.ldm.anima.model",
        ):
            module = types.ModuleType(name)
            module.__path__ = []
            modules[name] = module
            if "." in name:
                parent, child = name.rsplit(".", 1)
                setattr(modules[parent], child, module)

        torch = modules["torch"]
        torch.Tensor = _Tensor
        torch.tensor = lambda data, **kwargs: _Tensor(data)
        torch.as_tensor = lambda data, **kwargs: _Tensor(data)
        torch.long = "int64"
        torch.bool = "bool"
        modules["torch.nn.functional"].pad = lambda context, *args: context
        modules["comfy.model_management"].intermediate_device = lambda: "cpu"

        class BaseModel:
            def extra_conds(self, **kwargs):
                return {}

        class BaseAnima(BaseModel):
            pass

        class Anima:
            anima_v2_connector = _Adapter()
            llm_adapter = _NativeAdapter()

            def forward(self, x, timesteps, context, **kwargs):
                return context

        modules["comfy.model_base"].BaseModel = BaseModel
        modules["comfy.model_base"].Anima = BaseAnima
        modules["comfy.ldm.anima.model"].Anima = Anima
        self.anima_class = Anima
        self.stack.enter_context(mock.patch.dict(sys.modules, modules))
        self.semantic = self._load_runtime(anima38_nodes._VENDOR_MODULE)
        self.original_register = self.semantic._register_run
        runtime = types.SimpleNamespace(install_pro52_model_detection=lambda: None)
        self.stack.enter_context(mock.patch.object(anima38_nodes, "_RUNTIME", runtime))
        anima38_nodes.ensure_anima38_runtime()

    def _load_runtime(self, package):
        connector = types.ModuleType(f"{package}.semantic_connector_v2")
        connector.QualityAnchoredSemanticConnectorV2 = _Adapter
        self.stack.enter_context(mock.patch.dict(sys.modules, {connector.__name__: connector}))
        name = f"{package}.semantic_v2_runtime"
        spec = importlib.util.spec_from_file_location(name, VENDOR / "semantic_v2_runtime.py")
        module = importlib.util.module_from_spec(spec)
        self.stack.enter_context(mock.patch.dict(sys.modules, {name: module}))
        spec.loader.exec_module(module)
        self.stack.enter_context(mock.patch.object(module.logger, "info"))
        return module

    def _conditioning(self, semantic=None, source=None):
        semantic = semantic or self.semantic
        native = [[source or _Tensor(), {"t5xxl_ids": [1, 2, 3]}]]
        return semantic.emit_conditioning(
            expanded_adapter=self.anima_class.anima_v2_connector,
            native_adapter=self.anima_class.llm_adapter,
            native=native,
            native_source=native[0][0],
            native_metadata=native[0][1],
            semantic_states=[_Tensor(shape=(1, 3, 2560)) for _ in range(4)],
            semantic_mask=_Tensor(shape=(1, 3)),
            adapter_strength=1.0,
            checkpoint_path="test-bundle.safetensors",
            architecture="anima_qwen35_quality_anchored_semantic_connector_v2",
        )[0]

    def _sample(self, conditioning):
        context, metadata = conditioning[0]
        return self.anima_class().forward(
            None, None, context,
            qwen35_gated_run=_Tensor([[metadata["qwen35_gated_run"]]]),
            t5xxl_ids=metadata["t5xxl_ids"],
            qwen35_semantic_mask=metadata["qwen35_semantic_mask"],
            **{
                f"qwen35_semantic_{index}": state
                for index, state in enumerate(metadata["qwen35_semantic_states"])
            },
        )

    def test_cached_negative_remains_usable_after_128_changed_positives(self):
        negative = self._conditioning()
        for _ in range(128):
            positive = self._conditioning()
            self.assertIs(self._sample(positive), positive[0][0])
        self.assertIs(self._sample(negative), negative[0][0])

    def test_discarded_conditionings_release_runs_while_metadata_copies_keep_them(self):
        cached = self._conditioning()
        cached_copy = copy.deepcopy(cached)
        registry = self.anima_class._qwen35_gated_runs
        run_id = cached[0][1]["qwen35_gated_run"]
        run_ref = weakref.ref(registry[run_id])
        del cached
        gc.collect()
        for _ in range(256):
            self._sample(self._conditioning())
        gc.collect()
        self.assertEqual(len(registry), 1)
        self.assertIs(self._sample(cached_copy), cached_copy[0][0])
        self.assertIsNotNone(run_ref())
        del cached_copy
        gc.collect()
        self.assertEqual(len(registry), 0)
        self.assertIsNone(run_ref())

    def test_failed_emitter_releases_a_registered_but_unreturned_run(self):
        registry = self.anima_class._qwen35_gated_runs
        with self.assertRaises(TypeError):
            self._conditioning(source=_Tensor(shape=None))
        gc.collect()
        self.assertEqual(len(registry), 0)

    def test_old_fifo_pruning_cannot_evict_owned_conditionings(self):
        cached = self._conditioning()
        registry = self.anima_class._qwen35_gated_runs
        for _ in range(128):
            self.original_register(_Adapter())
        self.assertIs(self._sample(cached), cached[0][0])
        self.assertLessEqual(len(registry), 65)

    def test_existing_provider_alias_is_patched_and_repeated_install_is_idempotent(self):
        old_runtime = self._load_runtime("review_existing_anima")
        consumer = types.ModuleType("review_existing_anima.v2")
        consumer.emit_conditioning = old_runtime.emit_conditioning
        self.stack.enter_context(mock.patch.dict(sys.modules, {consumer.__name__: consumer}))
        anima38_nodes.ensure_anima38_runtime()
        emitter = old_runtime.emit_conditioning
        registry = self.anima_class._qwen35_gated_runs
        anima38_nodes.ensure_anima38_runtime()
        self.assertIs(old_runtime.emit_conditioning, emitter)
        self.assertIs(consumer.emit_conditioning, emitter)
        self.assertIs(self.anima_class._qwen35_gated_runs, registry)
        cached = self._conditioning(old_runtime)
        for _ in range(128):
            self._conditioning()
        self.assertIs(self._sample(cached), cached[0][0])
        self.assertEqual(len(registry), 1)

    def test_runtime_reload_preserves_conditionings_owned_by_previous_import(self):
        cached = self._conditioning()
        registry = self.anima_class._qwen35_gated_runs
        self.semantic = self._load_runtime(anima38_nodes._VENDOR_MODULE)
        anima38_nodes.ensure_anima38_runtime()
        for _ in range(128):
            self._conditioning()
        self.assertIs(self.anima_class._qwen35_gated_runs, registry)
        self.assertIs(self._sample(cached), cached[0][0])
        self.assertEqual(len(registry), 1)


if __name__ == "__main__":
    unittest.main()

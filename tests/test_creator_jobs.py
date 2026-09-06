"""Creator requests keep their identity through progress, rejection and cancel."""
import json
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from backends import BackendType
from core.creator_workflows import build
from ui.creator_actions import CreatorActionsMixin


class _Signal:
    def __init__(self):
        self.values = []
        self.ready = threading.Event()

    def emit(self, text):
        item = json.loads(text)
        self.values.append(item)
        if item.get("status") == "ready":
            self.ready.set()


class _Backend:
    api_url = "http://synthetic.invalid"

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.interrupts = 0

    def run_workflow(self, graph, progress, **kwargs):
        progress(1, 10)
        self.entered.set()
        self.release.wait(3)
        return SimpleNamespace(success=True, artifacts=[], info={})

    def interrupt(self):
        self.interrupts += 1
        self.release.set()


class _StageBackend(_Backend):
    def __init__(self, *, receipt=True, on_free=None):
        super().__init__()
        self.phases = []
        self.receipt = receipt
        self.on_free = on_free

    def run_workflow(self, graph, progress, **kwargs):
        kinds = {node["class_type"] for node in graph.values()}
        encode = "ForgeNeoH3ConditioningCachePrepare" in kinds
        self.phases.append("encode" if encode else "sample")
        if encode:
            if not kwargs.get("allow_empty_outputs"):
                return SimpleNamespace(success=False, error="encode did not allow UI-only output")
            if self.receipt:
                self.phases.append("unload_completed")
                if self.on_free:
                    self.on_free()
            info = {"node_outputs": {"90": {"h3_conditioning_cache": [
                {"ready": True, "key": "a" * 64, "hit": True, "models_unloaded": True}
            ]}}} if self.receipt else {}
            return SimpleNamespace(success=True, artifacts=[], info=info)
        if "CLIPLoader" in kinds or self.phases != ["encode", "unload_completed", "sample"]:
            return SimpleNamespace(success=False, error="sampling retained TE or skipped free")
        if graph["6"]["inputs"].get("expected_key") != "a" * 64:
            return SimpleNamespace(success=False, error="cache identity receipt was not pinned")
        self.sample_kinds = kinds
        artifact = SimpleNamespace(kind="video", path="synthetic/video.mp4", data=None,
                                   filename="video.mp4", mime="video/mp4", metadata={})
        return SimpleNamespace(success=True, artifacts=[artifact], info={})

    def free_memory(self, unload_models=True):
        raise AssertionError("Asynchronous /free ACK is not an unload completion barrier")


class CreatorJobTests(unittest.TestCase):
    def test_cache_descriptors_use_resolved_nested_server_model_names(self):
        from comfy_custom_nodes.ai_studio_forge_parity.h3_cache_nodes import conditioning_identity
        built = build("h3_t2v", {"prompt": "synthetic", "conditioning_cache": True})
        fields = {"UNETLoader": "unet_name", "CLIPLoader": "clip_name", "VAELoader": "vae_name"}
        names = {}
        for stage in built["stages"]:
            for node in stage["workflow"].values():
                field = fields.get(node["class_type"])
                if field:
                    names.setdefault(node["class_type"], set()).add("shared\\" + node["inputs"][field])
        info = {kind: {"input": {"required": {fields[kind]: [sorted(values)]}}} for kind, values in names.items()}
        CreatorActionsMixin._creator_resolve_comfy_choices(built, info)
        descriptors = [node["inputs"]["descriptor"] for stage in built["stages"]
                       for node in stage["workflow"].values()
                       if node["class_type"].startswith("ForgeNeoH3ConditioningCache")]
        self.assertEqual(len(set(descriptors)), 1)
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "synthetic"
            model.write_bytes(b"no real model")
            def resolve(_category, name):
                if not name.startswith("shared\\"):
                    raise FileNotFoundError(name)
                return model
            self.assertEqual(len(conditioning_identity(descriptors[0], resolve, lambda _: None)), 64)

    def test_duplicate_request_never_finishes_the_active_job(self):
        actions = CreatorActionsMixin()
        actions.vue_bridge = SimpleNamespace(creatorProgress=_Signal(), creatorResult=_Signal(), creatorStateChanged=_Signal())
        backend = _Backend()
        info = {name: {} for name in build("krea2_t2i", {"prompt": "synthetic"})["required_node_types"]}
        request = {"mode": "krea2_t2i", "prompt": "synthetic", "requestId": "same-id"}
        with (mock.patch("backends.get_backend", return_value=backend),
              mock.patch("backends.get_backend_type", return_value=BackendType.COMFYUI),
              mock.patch("requests.get", return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: info)),
              mock.patch.object(actions, "_creator_prefs", return_value={})):
            actions._handle_creator_action("creator_generate", request)
            try:
                self.assertTrue(backend.entered.wait(3))
                actions._handle_creator_action("creator_generate", request)
                self.assertEqual(actions.vue_bridge.creatorResult.values, [])
            finally:
                actions._handle_creator_action("creator_cancel", {"requestId": "same-id"})
                backend.release.set()
                actions.vue_bridge.creatorStateChanged.ready.wait(3)

    def test_repeated_cancel_remains_responsive_during_backend_interrupt(self):
        actions = CreatorActionsMixin()
        actions.vue_bridge = SimpleNamespace(creatorProgress=_Signal(), creatorResult=_Signal(), creatorStateChanged=_Signal())
        backend = _Backend()
        interrupt_entered, finish_interrupt = threading.Event(), threading.Event()
        def slow_interrupt():
            backend.interrupts += 1
            interrupt_entered.set()
            finish_interrupt.wait(3)
            backend.release.set()
        backend.interrupt = slow_interrupt
        info = {name: {} for name in build("krea2_t2i", {"prompt": "synthetic"})["required_node_types"]}
        with (mock.patch("backends.get_backend", return_value=backend),
              mock.patch("backends.get_backend_type", return_value=BackendType.COMFYUI),
              mock.patch("requests.get", return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: info)),
              mock.patch.object(actions, "_creator_prefs", return_value={})):
            actions._handle_creator_action("creator_generate", {"mode": "krea2_t2i", "prompt": "synthetic", "requestId": "owned"})
            try:
                self.assertTrue(backend.entered.wait(3))
                actions._handle_creator_action("creator_cancel", {"requestId": "owned"})
                self.assertTrue(interrupt_entered.wait(3))
                cancel_returned = threading.Event()
                def again():
                    actions._handle_creator_action("creator_cancel", {"requestId": "owned"})
                    cancel_returned.set()
                another = threading.Thread(target=again)
                another.start()
                self.assertTrue(cancel_returned.wait(0.5), "repeated cancel blocked on network interrupt")
            finally:
                finish_interrupt.set()
                backend.release.set()
                actions.vue_bridge.creatorStateChanged.ready.wait(3)
        self.assertEqual(backend.interrupts, 1)

    def test_busy_rejection_and_progress_belong_to_their_request(self):
        actions = CreatorActionsMixin()
        actions.vue_bridge = SimpleNamespace(
            creatorProgress=_Signal(), creatorResult=_Signal(), creatorStateChanged=_Signal()
        )
        backend = _Backend()
        info = {name: {} for name in build("krea2_t2i", {"prompt": "synthetic"})["required_node_types"]}
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: info)
        with (
            mock.patch("backends.get_backend", return_value=backend),
            mock.patch("backends.get_backend_type", return_value=BackendType.COMFYUI),
            mock.patch("requests.get", return_value=response),
            mock.patch.object(actions, "_creator_prefs", return_value={}),
        ):
            actions._handle_creator_action("creator_generate", {
                "mode": "krea2_t2i", "prompt": "synthetic", "requestId": "accepted"
            })
            try:
                self.assertTrue(backend.entered.wait(3))
                actions._handle_creator_action("creator_generate", {
                    "mode": "krea2_t2i", "prompt": "synthetic", "requestId": "rejected"
                })
                self.assertEqual(actions.vue_bridge.creatorResult.values[-1].get("requestId"), "rejected")
                self.assertEqual(actions.vue_bridge.creatorProgress.values[-1].get("requestId"), "accepted")
            finally:
                actions._handle_creator_action("creator_cancel", {"requestId": "accepted"})
                backend.release.set()
                actions.vue_bridge.creatorStateChanged.ready.wait(3)

    def _stage_request(self, backend, before=None, params=None, extra_nodes=()):
        actions = CreatorActionsMixin()
        actions.vue_bridge = SimpleNamespace(
            creatorProgress=_Signal(), creatorResult=_Signal(), creatorStateChanged=_Signal()
        )
        info = {name: {} for name in build("h3_t2v", {"prompt": "synthetic",
            "conditioning_cache": True, **(params or {})})["required_node_types"]}
        info.update({name: {} for name in extra_nodes})
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: info)
        with (mock.patch("backends.get_backend", return_value=backend),
              mock.patch("backends.get_backend_type", return_value=BackendType.COMFYUI),
              mock.patch("requests.get", return_value=response),
              mock.patch.object(actions, "_creator_prefs", return_value={})):
            if before:
                before(actions)
            actions._handle_creator_action("creator_generate", {
                "mode": "h3_t2v", "prompt": "synthetic", "requestId": "h3-job", **(params or {})
            })
            self.assertTrue(actions.vue_bridge.creatorStateChanged.ready.wait(3))
        return actions.vue_bridge.creatorResult.values[-1]

    def test_h3_result_follows_confirmed_encode_free_and_model_only_sample(self):
        backend = _StageBackend()
        result = self._stage_request(backend)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["requestId"], "h3-job")
        self.assertEqual(result["mediaType"], "video")
        self.assertEqual(backend.phases, ["encode", "unload_completed", "sample"])

    def test_quality_mode_does_not_enable_turbo_block_cache_from_server_capabilities(self):
        backend = _StageBackend()
        result = self._stage_request(backend, params={"quality": "quality"}, extra_nodes=["MiniMaxH3BlockCacheT8"])
        self.assertTrue(result["ok"], result)
        self.assertNotIn("MiniMaxH3BlockCacheT8", backend.sample_kinds)
        self.assertIn("KSamplerSelect", backend.sample_kinds)

    def test_missing_encode_receipt_does_not_start_sampling(self):
        backend = _StageBackend(receipt=False)
        result = self._stage_request(backend)
        self.assertFalse(result["ok"])
        self.assertEqual(backend.phases, ["encode"])

    def test_cancel_between_encode_and_sample_never_reports_complete(self):
        backend = _StageBackend()
        result = self._stage_request(backend, lambda actions: setattr(backend, "on_free",
            lambda: actions._handle_creator_action("creator_cancel", {"requestId": "h3-job"})))
        self.assertFalse(result["ok"])
        self.assertTrue(result["canceled"])
        self.assertEqual(backend.phases, ["encode", "unload_completed"])

    def test_wrong_request_cancel_never_interrupts_the_owned_backend(self):
        actions = CreatorActionsMixin()
        actions.vue_bridge = SimpleNamespace(creatorProgress=_Signal(), creatorResult=_Signal(), creatorStateChanged=_Signal())
        backend, replacement = _Backend(), _Backend()
        info = {name: {} for name in build("krea2_t2i", {"prompt": "synthetic"})["required_node_types"]}
        with (mock.patch("backends.get_backend", return_value=backend) as selected,
              mock.patch("backends.get_backend_type", return_value=BackendType.COMFYUI),
              mock.patch("requests.get", return_value=SimpleNamespace(raise_for_status=lambda: None, json=lambda: info)),
              mock.patch.object(actions, "_creator_prefs", return_value={})):
            actions._handle_creator_action("creator_generate", {"mode": "krea2_t2i", "prompt": "synthetic", "requestId": "owned"})
            self.assertTrue(backend.entered.wait(3))
            selected.return_value = replacement
            actions._handle_creator_action("creator_cancel", {"requestId": "other"})
            self.assertEqual(backend.interrupts, 0)
            actions._handle_creator_action("creator_cancel", {"requestId": "owned"})
            self.assertTrue(actions.vue_bridge.creatorStateChanged.ready.wait(3))
        self.assertEqual(backend.interrupts, 1)
        self.assertEqual(replacement.interrupts, 0)


if __name__ == "__main__":
    unittest.main()

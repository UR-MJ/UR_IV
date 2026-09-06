"""Exercise the native bridge through public actions with tiny offline fixtures."""
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.model_downloads import ModelArtifact, ModelDownloadManager, ModelPack
from core.storage_paths import StoragePaths
from tests.test_model_downloads import DATA, FakeHTTP
from ui.model_download_actions import ModelDownloadActionsMixin


class Signal:
    def __init__(self):
        self.events = []
        self.condition = threading.Condition()

    def emit(self, raw):
        with self.condition:
            self.events.append(json.loads(raw))
            self.condition.notify_all()

    def wait_for(self, predicate, timeout=3):
        with self.condition:
            if not self.condition.wait_for(lambda: any(predicate(event) for event in self.events), timeout):
                raise AssertionError(f"Expected event not received: {self.events}")
            return next(event for event in self.events if predicate(event))


class ModelDownloadActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        artifact = ModelArtifact("test-model", "테스트", "vae", "tiny.safetensors", len(DATA),
                                 hashlib.sha256(DATA).hexdigest(), "https://huggingface.co/test/model/resolve/pinned/tiny.safetensors")
        pack = ModelPack("test-pack", "테스트", "offline", (artifact.id,))
        self.signal = Signal()
        self.http = FakeHTTP()
        self.host = ModelDownloadActionsMixin()
        self.host.vue_bridge = SimpleNamespace(modelDownloadEvent=self.signal)
        self.host._model_download_manager_factory = lambda **kwargs: ModelDownloadManager(
            artifacts=[artifact], packs=[pack], storage=StoragePaths(self.root),
            snapshot_provider=lambda: {}, http=self.http, **kwargs)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.host._shutdown_model_downloads()
        manager = getattr(self.host, "_model_download_manager", None)
        if manager:
            manager.wait(3)
        dispatcher = getattr(self.host, "_model_download_dispatcher", None)
        if dispatcher:
            dispatcher.join(3)
        self.temp.cleanup()

    def test_status_start_verify_and_shutdown_public_bridge(self):
        self.assertFalse(self.host._handle_model_download_action("not-ours", {}))
        self.assertTrue(self.host._handle_model_download_action("model_download_status", {}))
        initial = self.signal.wait_for(lambda event: bool(event.get("packs")))
        self.assertEqual(initial["files"][0]["status"], "missing")
        self.host._handle_model_download_action("model_download_start", {"packIds": ["test-pack"], "url": "http://evil.invalid/ignored"})
        done = self.signal.wait_for(lambda event: event.get("state") == "complete")
        self.assertEqual(Path(done["files"][0]["path"]).read_bytes(), DATA)
        self.assertEqual(len(self.http.requests), 1)
        self.host._model_download_manager.wait(3)
        self.host._handle_model_download_action("model_download_verify", {"packIds": ["test-pack"]})
        self.host._model_download_requests.join()
        self.host._model_download_manager.wait(3)
        self.assertEqual(len(self.http.requests), 1)
        self.host._shutdown_model_downloads()
        self.assertTrue(self.host._handle_model_download_action("model_download_start", {"packIds": ["test-pack"]}))

    def test_web_mode_never_initializes_or_discloses_local_paths(self):
        self.host.web_mode = True
        for action in ("model_download_status", "model_download_start", "model_download_cancel", "model_download_verify"):
            self.assertTrue(self.host._handle_model_download_action(action, {"packIds": ["test-pack"]}))
        self.assertFalse(hasattr(self.host, "_model_download_requests"))
        self.assertEqual(self.signal.events, [])
        self.assertEqual(self.http.requests, [])

    def test_invalid_ids_report_action_error_without_starting_network(self):
        self.host._handle_model_download_action("model_download_start", {"packIds": [{"url": "http://evil.invalid"}]})
        result = self.signal.wait_for(lambda event: bool(event.get("actionError")))
        self.assertFalse(result["busy"])
        self.assertEqual(self.http.requests, [])


if __name__ == "__main__":
    unittest.main()

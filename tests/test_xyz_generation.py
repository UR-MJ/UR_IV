import unittest
from types import SimpleNamespace
from unittest import mock

from workers.generation_worker import GenerationFlowWorker


class XYZGenerationTests(unittest.TestCase):
    def test_xyz_queue_validation_failure_pauses_without_rebuilding_from_ui(self):
        from ui.generator_main import GeneratorMainUI
        paused, errors = [], []
        host = SimpleNamespace(
            queue_manager=SimpleNamespace(pause=lambda: paused.append(True)),
            _xyz_prepare_queue_generation=lambda _: (_ for _ in ()).throw(ValueError("백엔드 변경")),
            _abort_generation=lambda message: errors.append(message),
            _apply_payload_to_ui=mock.Mock(), start_generation=mock.Mock())
        GeneratorMainUI._on_generation_requested(host, {"_xyz_backend_id": "old"})
        self.assertEqual(paused, [True])
        self.assertEqual(errors, ["백엔드 변경"])
        host._apply_payload_to_ui.assert_not_called()
        host.start_generation.assert_not_called()

    def test_generation_worker_submits_exact_snapshot_to_captured_backend(self):
        calls, results = [], []
        backend = SimpleNamespace(txt2img=lambda model, payload, **_: calls.append((model, payload)) or
            SimpleNamespace(success=True, image_data=b"synthetic", info={}))
        payload = {"prompt": "blue hair", "steps": 30, "alwayson_scripts": {"SAM3": {"args": [True]}},
                   "_xyz_info": {"label": "Steps=30", "requestId": "plot"}}
        with mock.patch("workers.generation_worker.get_backend", return_value=backend):
            worker = GenerationFlowWorker("queued-model", payload, backend=backend)
            worker.finished.connect(lambda image, info: results.append((image, info)))
            payload["steps"] = 99
            worker.run()
        self.assertEqual(calls[0][0], "queued-model")
        self.assertEqual(calls[0][1]["steps"], 30)
        self.assertNotIn("_xyz_info", calls[0][1])
        self.assertEqual(results[0][1]["_xyz_info"]["label"], "Steps=30")

    def test_switched_backend_rejects_owned_worker_without_sending_generation(self):
        backend = SimpleNamespace(txt2img=mock.Mock())
        replacement = SimpleNamespace(txt2img=mock.Mock())
        worker = GenerationFlowWorker("queued-model", {"prompt": "synthetic"}, backend=backend)
        results = []
        worker.finished.connect(lambda image, info: results.append((image, info)))
        with mock.patch("workers.generation_worker.get_backend", return_value=replacement):
            worker.run()
        backend.txt2img.assert_not_called()
        replacement.txt2img.assert_not_called()
        self.assertIn("백엔드", results[0][0])


if __name__ == "__main__":
    unittest.main()

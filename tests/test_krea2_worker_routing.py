import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backends.base import GenerationResult
from workers.generation_worker import GenerationFlowWorker, Img2ImgFlowWorker


class _Coordinator:
    @contextmanager
    def reserve(self, *args, **kwargs):
        yield


class _Backend:
    def __init__(self):
        self.txt_payload = None
        self.i2i_payload = None

    def txt2img(self, model, payload, progress_callback=None):
        self.txt_payload = dict(payload)
        return GenerationResult(success=True, image_data=b"standard-t2i", info={})

    def img2img(self, model, payload, progress_callback=None):
        self.i2i_payload = dict(payload)
        return GenerationResult(success=True, image_data=b"standard-i2i", info={})


class Krea2WorkerRoutingTests(unittest.TestCase):
    def _run_worker(self, worker):
        emitted = []
        worker.finished.connect(lambda result, info: emitted.append((result, info)))
        worker.run()
        self.assertEqual(len(emitted), 1)
        return emitted[0]

    def test_standard_marker_is_consumed_before_txt2img_backend(self):
        backend = _Backend()
        worker = GenerationFlowWorker(
            "checkpoint.safetensors",
            {"prompt": "test", "_generation_family": "standard"},
        )
        with (
            patch("workers.generation_worker.get_backend", return_value=backend),
            patch("workers.generation_worker.get_generation_coordinator", return_value=_Coordinator()),
        ):
            result, _info = self._run_worker(worker)
        self.assertEqual(result, b"standard-t2i")
        self.assertNotIn("_generation_family", backend.txt_payload)

    def test_krea_t2i_routes_to_family_runner(self):
        backend = _Backend()
        calls = []

        def _run(adapter, operation, payload, progress_callback=None):
            calls.append((adapter, operation, dict(payload)))
            return GenerationResult(success=True, image_data=b"krea-t2i", info={"seed": 1})

        worker = GenerationFlowWorker(
            "ignored-checkpoint",
            {
                "prompt": "test",
                "_generation_family": "krea2",
                "_postprocess_chain": [{"type": "sam3", "settings": {}}],
            },
        )
        with (
            patch("workers.generation_worker.get_backend", return_value=backend),
            patch("workers.generation_worker.get_generation_coordinator", return_value=_Coordinator()),
            patch("core.krea2_generation.run_krea2_generation", side_effect=_run),
        ):
            result, info = self._run_worker(worker)
        self.assertEqual(result, b"krea-t2i")
        self.assertEqual(info["seed"], 1)
        self.assertEqual(calls[0][1], "t2i")
        self.assertNotIn("_generation_family", calls[0][2])
        self.assertNotIn("_postprocess_chain", calls[0][2])
        self.assertIsNone(backend.txt_payload)

    def test_krea_i2i_routes_to_family_runner(self):
        backend = _Backend()
        calls = []

        def _run(adapter, operation, payload, progress_callback=None):
            calls.append((adapter, operation, dict(payload)))
            return GenerationResult(success=True, image_data=b"krea-i2i", info={})

        worker = Img2ImgFlowWorker(
            "ignored-checkpoint",
            {"init_images": ["abc"], "_generation_family": "krea2"},
        )
        with (
            patch("workers.generation_worker.get_backend", return_value=backend),
            patch("workers.generation_worker.get_generation_coordinator", return_value=_Coordinator()),
            patch("core.krea2_generation.run_krea2_generation", side_effect=_run),
        ):
            result, _info = self._run_worker(worker)
        self.assertEqual(result, b"krea-i2i")
        self.assertEqual(calls[0][1], "i2i")
        self.assertIsNone(backend.i2i_payload)


if __name__ == "__main__":
    unittest.main()

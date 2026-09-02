"""VueBridge의 Batch/Caption 경계 회귀 테스트."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from PIL import Image

from core.image_captioning import TORIIGATE_BF16_MODEL, CaptionResult, TagPrediction
from ui.vue_bridge import VueBridge


def _image(path: Path, color: str = "navy") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path)
    return path


class _ImmediateThread:
    """startCaptionBatch의 작업을 현재 테스트 스레드에서 즉시 실행한다."""

    def __init__(self, *, target, **_kwargs):
        self._target = target

    def start(self):
        self._target()


class _FailingThread(_ImmediateThread):
    def start(self):
        raise RuntimeError("thread start failed")


class _TrackingCoordinator:
    """Record whether cleanup happens while the shared generation lease is held."""

    def __init__(self):
        self.active = False

    @contextmanager
    def reserve(self, *_args, **_kwargs):
        self.active = True
        try:
            yield
        finally:
            self.active = False


class VueBridgeCaptionPayloadTests(unittest.TestCase):
    def setUp(self):
        self.bridge = VueBridge()

    def test_legacy_payload_defaults_to_ollama(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            payload, files = self.bridge._prepare_caption_payload(
                {"path": str(image), "model": "vision:latest", "save": False},
                batch=False,
            )

        self.assertEqual(payload["engine"], "ollama")
        self.assertEqual(payload["model"], "vision:latest")
        self.assertEqual(files, [str(image.resolve())])

    def test_caformer_does_not_require_an_ollama_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            payload, _ = self.bridge._prepare_caption_payload(
                {"files": [str(image)], "engine": "caformer", "save": False},
                batch=True,
            )

        self.assertEqual(payload["model"], "")
        self.assertEqual(payload["engine"], "caformer")

    def test_torii_mode_rejects_a_text_only_model_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            with self.assertRaisesRegex(ValueError, "ToriiGate"):
                self.bridge._prepare_caption_payload(
                    {
                        "files": [str(image)],
                        "engine": "torii",
                        "model": "qwen3:8b",
                        "save": False,
                    },
                    batch=True,
                )

    def test_shared_output_folder_rejects_duplicate_basenames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _image(root / "a" / "same.png")
            second = _image(root / "b" / "same.png")
            out_dir = root / "captions"
            with self.assertRaisesRegex(ValueError, "동명 이미지"):
                self.bridge._prepare_caption_payload(
                    {
                        "files": [str(first), str(second)],
                        "engine": "caformer",
                        "outDir": str(out_dir),
                        "save": True,
                    },
                    batch=True,
                )

    def test_side_by_side_output_rejects_same_stem_different_extensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            png = _image(root / "same.png")
            jpg = _image(root / "same.jpg")
            with self.assertRaisesRegex(ValueError, "동명 이미지"):
                self.bridge._prepare_caption_payload(
                    {
                        "files": [str(png), str(jpg)],
                        "engine": "caformer",
                        "save": True,
                    },
                    batch=True,
                )

    def test_caformer_options_match_frontend_payload(self):
        options = self.bridge._caption_caformer_options(
            {
                "includeCharacters": False,
                "includeRating": True,
                "useBestThresholds": False,
                "generalThreshold": 0.31,
                "characterThreshold": 0.44,
                "ratingThreshold": 0.55,
            }
        )
        self.assertEqual(options["thresholdMode"], "category")
        self.assertFalse(options["includeCharacters"])
        self.assertTrue(options["includeRating"])
        self.assertEqual(options["ratingThreshold"], 0.55)

    def test_payload_normalizes_client_job_ids_booleans_and_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            payload, _ = self.bridge._prepare_caption_payload(
                {
                    "files": [str(image)],
                    "engine": "caformer",
                    "clientToken": "client token!",
                    "jobId": "job/id",
                    "save": "false",
                    "includeCharacters": "false",
                    "generalThreshold": "0.31",
                },
                batch=True,
            )

        self.assertEqual(payload["clientToken"], "clienttoken")
        self.assertEqual(payload["jobId"], "jobid")
        self.assertFalse(payload["save"])
        self.assertFalse(payload["includeCharacters"])
        self.assertEqual(payload["generalThreshold"], 0.31)

    def test_invalid_threshold_is_rejected_before_worker_start(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            with self.assertRaisesRegex(ValueError, "generalThreshold"):
                self.bridge._prepare_caption_payload(
                    {
                        "files": [str(image)],
                        "engine": "caformer",
                        "save": False,
                        "generalThreshold": 2,
                    },
                    batch=True,
                )

    def test_runtime_snapshot_echoes_client_and_request_identity(self):
        with (
            mock.patch(
                "core.image_captioning.discover_caformer_model",
                return_value=Path("C:/models/caformer"),
            ),
            mock.patch("importlib.util.find_spec", return_value=object()),
            mock.patch(
                "core.ollama_client.OllamaClient.list_models",
                return_value=[TORIIGATE_BF16_MODEL],
            ),
        ):
            result = json.loads(
                self.bridge._caption_runtime_snapshot(
                    {
                        "clientToken": "client-a",
                        "requestId": 17,
                        "toriiModel": TORIIGATE_BF16_MODEL,
                    }
                )
            )

        self.assertEqual(result["clientToken"], "client-a")
        self.assertEqual(result["requestId"], 17)
        self.assertTrue(result["caformer"]["available"])
        self.assertTrue(result["torii"]["available"])


class VueBridgeCaptionSidecarTests(unittest.TestCase):
    def setUp(self):
        self.bridge = VueBridge()

    def test_save_and_load_use_selected_output_folder_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = _image(root / "images" / "sample.png")
            out_dir = root / "captions"
            saved = json.loads(
                self.bridge.saveCaption(
                    json.dumps(
                        {"path": str(image), "caption": "1girl, solo", "outDir": str(out_dir)}
                    )
                )
            )
            loaded = json.loads(
                self.bridge.loadCaption(
                    json.dumps({"path": str(image), "outDir": str(out_dir)})
                )
            )

            target = out_dir / "sample.txt"
            self.assertTrue(saved["ok"])
            self.assertEqual(loaded["caption"], "1girl, solo")
            self.assertEqual(loaded["txtPath"], target.as_posix())
            self.assertEqual(target.read_text(encoding="utf-8"), "1girl, solo")
            self.assertFalse(Path(str(target) + ".tmp").exists())

    def test_blank_existing_sidecar_is_regenerated(self):
        result = CaptionResult(
            "caformer",
            tags=(TagPrediction("solo", 0.9, "general"),),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = _image(root / "image.png")
            sidecar = root / "image.txt"
            sidecar.write_text("   ", encoding="utf-8")
            progress: list[dict] = []
            completed: list[dict] = []
            self.bridge.captionProgress.connect(lambda value: progress.append(json.loads(value)))
            self.bridge.captionDone.connect(lambda value: completed.append(json.loads(value)))

            with (
                mock.patch("ui.vue_bridge.threading.Thread", _ImmediateThread),
                mock.patch.object(self.bridge, "_create_caption_engine", return_value=object()),
                mock.patch.object(self.bridge, "_run_caption_inference", return_value=result) as infer,
            ):
                started = json.loads(
                    self.bridge.startCaptionBatch(
                        json.dumps(
                            {
                                "files": [str(image)],
                                "engine": "caformer",
                                "save": True,
                                "overwrite": False,
                            }
                        )
                    )
                )

            self.assertTrue(started["started"])
            infer.assert_called_once()
            self.assertEqual(sidecar.read_text(encoding="utf-8"), "solo")
            self.assertFalse(progress[0].get("skipped", False))
            self.assertEqual(completed[0]["ok"], 1)
            self.assertEqual(completed[0]["failed"], 0)

    def test_manual_save_is_rejected_while_caption_job_owns_sidecars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = _image(root / "image.png")
            self.assertTrue(self.bridge._caption_job_lock.acquire(blocking=False))
            try:
                response = json.loads(
                    self.bridge.saveCaption(
                        json.dumps({"path": str(image), "caption": "must not write"})
                    )
                )
            finally:
                self.bridge._caption_job_lock.release()

            self.assertIn("error", response)
            self.assertFalse((root / "image.txt").exists())


class VueBridgeCaptionJobTests(unittest.TestCase):
    def setUp(self):
        self.bridge = VueBridge()

    def _start_immediately(self, image: Path, inference):
        progress: list[dict] = []
        completed: list[dict] = []
        self.bridge.captionProgress.connect(lambda value: progress.append(json.loads(value)))
        self.bridge.captionDone.connect(lambda value: completed.append(json.loads(value)))
        with (
            mock.patch("ui.vue_bridge.threading.Thread", _ImmediateThread),
            mock.patch.object(self.bridge, "_create_caption_engine", return_value=object()),
            mock.patch.object(self.bridge, "_run_caption_inference", side_effect=inference),
        ):
            started = json.loads(
                self.bridge.startCaptionBatch(
                    json.dumps(
                        {
                            "files": [str(image)],
                            "engine": "caformer",
                            "save": False,
                            "clientToken": "client-a",
                            "jobId": "job-a",
                        }
                    )
                )
            )
        return started, progress, completed

    def test_job_identity_is_echoed_and_done_state_recovers_missed_signals(self):
        result = CaptionResult(
            "caformer", tags=(TagPrediction("solo", 0.9, "general"),)
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            started, progress, completed = self._start_immediately(image, lambda *_: result)

        self.assertEqual(started["clientToken"], "client-a")
        self.assertEqual(started["jobId"], "job-a")
        self.assertEqual(progress[0]["clientToken"], "client-a")
        self.assertEqual(progress[0]["jobId"], "job-a")
        self.assertEqual(completed[0]["succeeded"], 1)
        status = json.loads(
            self.bridge.getCaptionJobStatus(
                json.dumps({"clientToken": "client-a", "jobId": "job-a"})
            )
        )
        self.assertEqual(status["status"], "done")
        self.assertEqual(status["processed"], 1)
        self.assertEqual(status["items"][0]["caption"], "solo")

    def test_saved_progress_and_recovery_include_exact_sidecar_path(self):
        result = CaptionResult(
            "caformer", tags=(TagPrediction("solo", 0.9, "general"),)
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = _image(root / "images" / "image.png")
            out_dir = root / "captions"
            progress: list[dict] = []
            self.bridge.captionProgress.connect(lambda value: progress.append(json.loads(value)))
            with (
                mock.patch("ui.vue_bridge.threading.Thread", _ImmediateThread),
                mock.patch.object(self.bridge, "_create_caption_engine", return_value=object()),
                mock.patch.object(self.bridge, "_run_caption_inference", return_value=result),
            ):
                response = json.loads(
                    self.bridge.startCaptionBatch(
                        json.dumps(
                            {
                                "files": [str(image)],
                                "engine": "caformer",
                                "save": True,
                                "outDir": str(out_dir),
                                "clientToken": "client-sidecar",
                                "jobId": "job-sidecar",
                            }
                        )
                    )
                )

            status = json.loads(
                self.bridge.getCaptionJobStatus(
                    json.dumps(
                        {"clientToken": response["clientToken"], "jobId": response["jobId"]}
                    )
                )
            )
            expected = (out_dir / "image.txt").as_posix()
            self.assertEqual(progress[0]["txtPath"], expected)
            self.assertEqual(status["items"][0]["txtPath"], expected)

    def test_batch_unloads_torii_inside_lease_but_not_caformer(self):
        result = CaptionResult("torii", natural_caption="A visible subject.")
        coordinator = _TrackingCoordinator()
        unload_lease_states: list[bool] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            with (
                mock.patch("ui.vue_bridge.threading.Thread", _ImmediateThread),
                mock.patch(
                    "core.resource_coordinator.get_generation_coordinator",
                    return_value=coordinator,
                ),
                mock.patch.object(self.bridge, "_create_caption_engine", return_value=object()),
                mock.patch.object(self.bridge, "_run_caption_inference", return_value=result),
                mock.patch(
                    "core.ollama_client.OllamaClient.unload",
                    autospec=True,
                    side_effect=lambda _client: unload_lease_states.append(coordinator.active),
                ),
            ):
                torii_response = json.loads(
                    self.bridge.startCaptionBatch(
                        json.dumps(
                            {
                                "files": [str(image)],
                                "engine": "torii",
                                "model": TORIIGATE_BF16_MODEL,
                                "save": False,
                                "clientToken": "client-lease",
                                "jobId": "job-lease",
                            }
                        )
                    )
                )
                self.bridge._run_caption_inference.return_value = CaptionResult(
                    "caformer", tags=(TagPrediction("solo", 0.9, "general"),)
                )
                caformer_response = json.loads(
                    self.bridge.startCaptionBatch(
                        json.dumps(
                            {
                                "files": [str(image)],
                                "engine": "caformer",
                                "save": False,
                                "unloadAfter": True,
                                "clientToken": "client-caformer",
                                "jobId": "job-caformer",
                            }
                        )
                    )
                )

        self.assertTrue(torii_response["started"])
        self.assertTrue(caformer_response["started"])
        self.assertEqual(unload_lease_states, [True])

    def test_single_caption_api_unloads_torii_inside_lease_but_not_caformer(self):
        coordinator = _TrackingCoordinator()
        unload_lease_states: list[bool] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            with (
                mock.patch(
                    "core.resource_coordinator.get_generation_coordinator",
                    return_value=coordinator,
                ),
                mock.patch.object(self.bridge, "_create_caption_engine", return_value=object()),
                mock.patch.object(
                    self.bridge,
                    "_run_caption_inference",
                    return_value=CaptionResult("torii", natural_caption="A visible subject."),
                ),
                mock.patch(
                    "core.ollama_client.OllamaClient.unload",
                    autospec=True,
                    side_effect=lambda _client: unload_lease_states.append(coordinator.active),
                ) as unload,
            ):
                torii = json.loads(
                    self.bridge.captionImage(
                        json.dumps(
                            {
                                "path": str(image),
                                "engine": "torii",
                                "model": TORIIGATE_BF16_MODEL,
                                "save": False,
                            }
                        )
                    )
                )

                self.bridge._run_caption_inference.return_value = CaptionResult(
                    "caformer", tags=(TagPrediction("solo", 0.9, "general"),)
                )
                caformer = json.loads(
                    self.bridge.captionImage(
                        json.dumps(
                            {
                                "path": str(image),
                                "engine": "caformer",
                                "save": False,
                                "unloadAfter": True,
                            }
                        )
                    )
                )

        self.assertEqual(torii["caption"], "A visible subject.")
        self.assertEqual(caformer["caption"], "solo")
        self.assertEqual(unload_lease_states, [True])
        unload.assert_called_once()

    def test_all_item_failures_report_first_error_and_consistent_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            _, progress, completed = self._start_immediately(
                image, lambda *_: (_ for _ in ()).throw(RuntimeError("inference boom"))
            )

        self.assertEqual(progress[0]["error"], "inference boom")
        done = completed[0]
        self.assertEqual(done["ok"], 0)
        self.assertEqual(done["succeeded"], 0)
        self.assertEqual(done["failed"], 1)
        self.assertEqual(done["processed"], 1)
        self.assertEqual(done["error"], "inference boom")
        self.assertEqual(done["ok"] + done["failed"], done["total"])

    def test_thread_start_failure_releases_job_lock_and_journals_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = _image(Path(temp_dir) / "image.png")
            with mock.patch("ui.vue_bridge.threading.Thread", _FailingThread):
                response = json.loads(
                    self.bridge.startCaptionBatch(
                        json.dumps(
                            {
                                "files": [str(image)],
                                "engine": "caformer",
                                "save": False,
                                "clientToken": "client-a",
                                "jobId": "job-start-fail",
                            }
                        )
                    )
                )

            self.assertIn("thread start failed", response["error"])
            self.assertTrue(self.bridge._caption_job_lock.acquire(blocking=False))
            self.bridge._caption_job_lock.release()
            status = json.loads(
                self.bridge.getCaptionJobStatus(
                    json.dumps({"clientToken": "client-a", "jobId": "job-start-fail"})
                )
            )
            self.assertEqual(status["status"], "done")
            self.assertIn("thread start failed", status["error"])
            self.assertEqual(status["failed"], 1)
            self.assertEqual(status["processed"], 1)
            self.assertIn("thread start failed", status["items"][0]["error"])

    def test_unknown_job_status_does_not_leak_another_clients_results(self):
        status = json.loads(
            self.bridge.getCaptionJobStatus(
                json.dumps({"clientToken": "client-b", "jobId": "unknown"})
            )
        )
        self.assertEqual(status["status"], "idle")
        self.assertEqual(status["clientToken"], "client-b")


if __name__ == "__main__":
    unittest.main()

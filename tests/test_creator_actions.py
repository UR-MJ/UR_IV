import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from core.comic_studio import ComicRevisionConflict
from ui.creator_actions import CreatorActionsMixin


class _UploadBackend:
    def __init__(self):
        self.uploads = []

    def upload_media(self, data, filename, mime):
        self.uploads.append((data, filename, mime))
        return f"studio/{filename}"


class _Signal:
    def __init__(self):
        self.values = []

    def emit(self, value):
        self.values.append(json.loads(value))


class _Bridge:
    def __init__(self):
        self.comicDocumentChanged = _Signal()


class _Document:
    def __init__(self, revision=3, title="saved"):
        self.revision = revision
        self.title = title

    def to_dict(self):
        return {
            "title": self.title,
            "revision": self.revision,
            "contentHash": "a" * 64,
            "panels": [{"id": "panel-1", "prompt": "ok"}],
        }


class _ImmediateThread:
    def __init__(self, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


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

    def test_comic_save_forwards_expected_revision_and_returns_ack_metadata(self):
        bridge = _Bridge()
        self.actions.vue_bridge = bridge
        studio = mock.Mock()
        studio.save.return_value = _Document(revision=8)
        self.actions._comic_studio = lambda: studio

        self.actions._comic_save(
            {
                "document": {"title": "edit", "panels": [{}]},
                "expectedRevision": 7,
                "requestId": "save-42",
            }
        )

        studio.save.assert_called_once_with(
            {"title": "edit", "panels": [{}]}, expected_revision=7
        )
        emitted = bridge.comicDocumentChanged.values[-1]
        self.assertEqual(emitted["document"]["revision"], 8)
        self.assertEqual(emitted["persistence"]["status"], "saved")
        self.assertEqual(emitted["persistence"]["requestId"], "save-42")

    def test_comic_save_conflict_returns_authoritative_document(self):
        bridge = _Bridge()
        self.actions.vue_bridge = bridge
        studio = mock.Mock()
        studio.save.side_effect = ComicRevisionConflict(2, 3, _Document(revision=3, title="newer"))
        self.actions._comic_studio = lambda: studio

        self.actions._comic_save(
            {
                "document": {"title": "stale", "panels": [{}]},
                "expectedRevision": 2,
                "requestId": "save-stale",
            }
        )

        emitted = bridge.comicDocumentChanged.values[-1]
        self.assertEqual(emitted["document"]["title"], "newer")
        self.assertEqual(emitted["persistence"]["status"], "conflict")
        self.assertEqual(emitted["persistence"]["actualRevision"], 3)

    def test_creator_state_reconciles_frontend_recovery_before_emitting_document(self):
        bridge = _Bridge()
        bridge.creatorStateChanged = _Signal()
        self.actions.vue_bridge = bridge
        self.actions._creator_running = False
        self.actions._creator_mode = ""
        recovery = {"schema": 2, "documentJson": "{}"}
        studio = mock.Mock()
        studio.reconcile.return_value = SimpleNamespace(
            document=_Document(revision=5),
            status="recovered",
            conflict_path="",
        )
        self.actions._comic_studio = lambda: studio

        with (
            mock.patch("ui.creator_actions.threading.Thread", _ImmediateThread),
            mock.patch("backends.get_backend"),
            mock.patch("backends.get_backend_type") as get_backend_type,
        ):
            get_backend_type.return_value.value = "forge"
            self.actions._creator_request_state({"comicRecovery": recovery})

        studio.reconcile.assert_called_once_with(recovery)
        emitted = bridge.comicDocumentChanged.values[-1]
        self.assertEqual(emitted["document"]["revision"], 5)
        self.assertEqual(emitted["persistence"]["status"], "recovered")


class CreatorOllamaUnloadTests(unittest.TestCase):
    """Ollama 미실행을 '언로드 실패'로 오인하면 Creator 생성이 시작조차 못 한다.

    ResourceCoordinator.reserve 는 unload_llm 이 False 를 돌려주면 하드 abort 하므로,
    "언로드할 게 없음"과 "언로드 실패"를 여기서 구분해야 한다.
    ui/generator_generation.py 의 _maybe_unload_ollama 와 같은 의미론.
    """

    def setUp(self):
        self.actions = CreatorActionsMixin()
        self.actions._creator_ollama_config = lambda: ("http://localhost:11434", "qwen3:8b")

    def test_unreachable_ollama_counts_as_unloaded(self):
        with mock.patch("core.ollama_client.OllamaClient") as client_cls:
            client = client_cls.return_value
            client.test_connection.return_value = False
            self.assertTrue(self.actions._creator_unload_ollama())
            client.unload.assert_not_called()

    def test_running_ollama_is_actually_unloaded(self):
        with mock.patch("core.ollama_client.OllamaClient") as client_cls:
            client = client_cls.return_value
            client.test_connection.return_value = True
            client.unload.return_value = True
            self.assertTrue(self.actions._creator_unload_ollama())
            client.unload.assert_called_once_with()

    def test_real_unload_failure_is_still_reported(self):
        with mock.patch("core.ollama_client.OllamaClient") as client_cls:
            client = client_cls.return_value
            client.test_connection.return_value = True
            client.unload.return_value = False
            self.assertFalse(self.actions._creator_unload_ollama())

    def test_no_model_configured_is_a_noop(self):
        self.actions._creator_ollama_config = lambda: ("http://localhost:11434", "")
        self.assertTrue(self.actions._creator_unload_ollama())


if __name__ == "__main__":
    unittest.main()

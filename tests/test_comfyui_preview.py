"""CPU-only protocol fixtures and complete websocket-to-callback preview tests."""
from __future__ import annotations

import base64
import io
import json
import struct
import unittest
from unittest import mock

from PIL import Image

from backends.base import GenerationResult
from backends.comfyui_backend import ComfyUIBackend
from backends.comfyui_preview import PreviewStream, decode_preview
from backends.comfyui_progress import ProgressTracker


def image_bytes(format="PNG", color="red"):
    output = io.BytesIO()
    Image.new("RGB", (16, 12), color).save(output, format=format)
    return output.getvalue()


def legacy(image=None, image_type=2):
    return struct.pack(">II", 1, image_type) + (image if image is not None else image_bytes())


def annotated(metadata=None, image=None):
    if metadata is None:
        metadata = {"image_type": "image/png", "prompt_id": "ours", "node_id": "3"}
    encoded = json.dumps(metadata).encode()
    return struct.pack(">II", 4, len(encoded)) + encoded + (image if image is not None else image_bytes())


def event(kind="executing", identity="ours", **data):
    return {"type": kind, "data": {"prompt_id": identity, **data}}


class PreviewProtocolTests(unittest.TestCase):
    def test_jpeg_and_png_round_trip_without_reencoding(self):
        for format, image_type, mime in [("PNG", 2, "image/png"), ("JPEG", 1, "image/jpeg")]:
            with self.subTest(format=format):
                raw = image_bytes(format)
                decoded = decode_preview(legacy(raw, image_type))
                self.assertEqual(decoded.image, raw)
                self.assertEqual(decoded.mime, mime)
                self.assertIsNone(decoded.prompt_id)

    def test_metadata_frame_preserves_prompt_identity(self):
        raw = image_bytes()
        decoded = decode_preview(annotated(image=raw))
        self.assertEqual(decoded.prompt_id, "ours")
        self.assertEqual(decoded.image, raw)

    def test_metadata_webp_supported_but_animation_is_not(self):
        raw = image_bytes("WEBP")
        decoded = decode_preview(annotated({"image_type": "image/webp", "prompt_id": "ours"}, raw))
        self.assertEqual(decoded.mime, "image/webp")
        output = io.BytesIO()
        Image.new("RGB", (16, 12), "red").save(
            output, format="WEBP", save_all=True,
            append_images=[Image.new("RGB", (16, 12), "blue")], duration=100,
        )
        self.assertIsNone(decode_preview(annotated({"image_type": "image/webp"}, output.getvalue())))

    def test_unknown_truncated_and_invalid_json_frames_are_ignored(self):
        for frame in [b"", b"12345678", struct.pack(">II", 8, 2) + image_bytes(),
                      struct.pack(">II", 1, 99) + image_bytes(),
                      struct.pack(">II", 4, 9999) + b"{}",
                      struct.pack(">II", 4, 1) + b"\xff" + image_bytes(),
                      struct.pack(">II", 4, 1) + b"[" + image_bytes(),
                      annotated([]), annotated(None, b"not an image")]:
            with self.subTest(frame=frame[:16]):
                self.assertIsNone(decode_preview(frame))

    def test_mime_and_image_signature_must_agree(self):
        for mime in ["text/html", "image/svg+xml", "image/jpeg", [], None]:
            self.assertIsNone(decode_preview(annotated({"image_type": mime})))
        self.assertIsNone(decode_preview(legacy(b"\x89PNG\r\n\x1a\nbroken")))
        self.assertIsNone(decode_preview(legacy(image_bytes("JPEG")[:-2], 1)))

    def test_invalid_present_prompt_id_does_not_become_anonymous(self):
        for identity in [None, "", {}, 123, "x" * 257]:
            self.assertIsNone(decode_preview(annotated({"image_type": "image/png", "prompt_id": identity})))

    def test_limits_apply_before_display(self):
        with mock.patch("backends.comfyui_preview.MAX_PREVIEW_BYTES", 10):
            self.assertIsNone(decode_preview(legacy()))
        with mock.patch("backends.comfyui_preview.MAX_METADATA_BYTES", 4):
            self.assertIsNone(decode_preview(annotated()))
        with mock.patch("backends.comfyui_preview.MAX_PREVIEW_PIXELS", 100):
            self.assertIsNone(decode_preview(legacy()))


class PreviewStreamTests(unittest.TestCase):
    def test_anonymous_frame_requires_observed_own_execution(self):
        stream = PreviewStream("ours")
        self.assertIsNone(stream.consume(legacy()))
        stream.observe(event("execution_start", "theirs"))
        self.assertIsNone(stream.consume(legacy()))
        stream.observe(event(node="3"))
        self.assertEqual(base64.b64decode(stream.consume(legacy())), image_bytes())

    def test_metadata_frame_is_strictly_prompt_scoped(self):
        stream = PreviewStream("ours")
        self.assertIsNone(stream.consume(annotated({"prompt_id": "theirs", "image_type": "image/png"})))
        # A matching metadata identity is safe even before its text event arrives.
        self.assertIsInstance(stream.consume(annotated()), str)

    def test_foreign_execution_suspends_anonymous_frames(self):
        stream = PreviewStream("ours", interval=0)
        stream.observe(event(node="3"))
        stream.observe(event(node="9", identity="theirs"))
        self.assertIsNone(stream.consume(legacy()))
        stream.observe(event("progress", node="3", value=1, max=10))
        self.assertIsNotNone(stream.consume(legacy()))

    def test_throttle_dedup_and_latest_frame_resume(self):
        clock = mock.Mock(return_value=0.0)
        stream = PreviewStream("ours", clock=clock)
        stream.observe(event("execution_start"))
        self.assertIsNotNone(stream.consume(legacy()))
        clock.return_value = 0.1
        self.assertIsNone(stream.consume(legacy(image_bytes(color="blue"))))
        clock.return_value = 0.25
        self.assertIsNone(stream.consume(legacy()))  # repeated pixels
        latest = image_bytes(color="green")
        self.assertEqual(base64.b64decode(stream.consume(legacy(latest))), latest)

    def test_terminal_events_prevent_late_preview_even_with_matching_metadata(self):
        for kind in ["execution_error", "execution_interrupted", "execution_success", "executing"]:
            stream = PreviewStream("ours")
            stream.observe(event("execution_start"))
            stream.observe(event(kind, node=None))
            self.assertIsNone(stream.consume(annotated()))
            stream.observe(event("progress", value=2, max=3))
            self.assertIsNone(stream.consume(annotated()))

    def test_foreign_terminal_event_does_not_stop_our_preview(self):
        stream = PreviewStream("ours")
        stream.observe(event("execution_start"))
        stream.observe(event("execution_interrupted", identity="theirs"))
        self.assertIsNotNone(stream.consume(legacy()))


class PreviewBackendTests(unittest.TestCase):
    workflow = {"3": {"class_type": "KSampler", "inputs": {}}}

    def test_websocket_frame_reaches_existing_base64_callback_and_final_is_fetched(self):
        frames = [
            legacy(),  # unrelated preview while this job was queued
            json.dumps(event(node="3")),
            json.dumps(event("progress", node="3", value=2, max=10)),
            annotated({"prompt_id": "theirs", "image_type": "image/png"}),
            annotated(),
            json.dumps(event(node=None)),
        ]
        ws = mock.Mock()
        ws.recv.side_effect = frames
        backend = ComfyUIBackend("http://127.0.0.1:8188")
        callback = mock.Mock()
        expected = GenerationResult(success=True, image_data=image_bytes())
        with mock.patch.object(backend, "_fetch_result_artifacts", return_value=expected) as fetch:
            result = backend._wait_for_result(ws, "ours", callback, tracker=ProgressTracker(self.workflow))
        self.assertIs(result, expected)
        fetch.assert_called_once_with("ours")
        previews = [call.args for call in callback.call_args_list if call.args[2] is not None]
        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0][:2], (20, 100))
        self.assertEqual(base64.b64decode(previews[0][2]), image_bytes())
        self.assertFalse(previews[0][2].startswith("data:"))
        self.assertEqual(callback.call_args.args, (100, 100, None))

    def test_submission_negotiates_metadata_and_requests_only_per_job_previews(self):
        backend = ComfyUIBackend("http://127.0.0.1:8188")
        ws = mock.Mock()
        response = mock.Mock(status_code=200)
        response.json.return_value = {"prompt_id": "ours"}
        result = GenerationResult(success=True)
        with mock.patch("backends.comfyui_backend.websocket.create_connection", return_value=ws), \
                mock.patch("backends.comfyui_backend.requests.post", return_value=response) as post, \
                mock.patch.object(backend, "_wait_for_result", return_value=result):
            actual = backend.run_workflow(self.workflow, progress_callback=mock.Mock())
        self.assertIs(actual, result)
        self.assertEqual(json.loads(ws.send.call_args.args[0]), {
            "type": "feature_flags", "data": {"supports_preview_metadata": True},
        })
        self.assertEqual(post.call_count, 1)
        self.assertTrue(post.call_args.args[0].endswith("/prompt"))
        self.assertEqual(post.call_args.kwargs["json"]["extra_data"], {"preview_method": "auto"})
        ws.close.assert_called_once()
        self.assertIsNone(backend._current_prompt_id)

    def test_cancel_before_receive_has_no_preview_or_result_fetch(self):
        backend = ComfyUIBackend("http://127.0.0.1:8188")
        ws, callback = mock.Mock(), mock.Mock()
        with mock.patch.object(backend, "_cancel_prompt") as cancel, \
                mock.patch.object(backend, "_fetch_result_artifacts") as fetch:
            result = backend._wait_for_result(ws, "ours", callback, cancel_check=lambda: True)
        self.assertFalse(result.success)
        cancel.assert_called_once_with("ours")
        fetch.assert_not_called()
        callback.assert_not_called()
        ws.recv.assert_not_called()


if __name__ == "__main__":
    unittest.main()

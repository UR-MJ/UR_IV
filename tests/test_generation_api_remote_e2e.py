import base64
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.generation_api import GenerationApiManager
from core.resource_coordinator import GenerationResourceCoordinator


def _png_bytes(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color).save(output, format="PNG")
    return output.getvalue()


class _RecordingA1111Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, first_image: bytes, second_image: bytes):
        super().__init__(("127.0.0.1", 0), _RecordingA1111Handler)
        self.current_model = "initial-model.safetensors"
        self.model_switch_status = 200
        self.first_image = first_image
        self.second_image = second_image
        self.calls = []
        self.calls_lock = threading.Lock()

    def record(self, method: str, path: str, payload=None) -> None:
        with self.calls_lock:
            self.calls.append({
                "method": method,
                "path": path,
                "payload": payload,
                "active_model": self.current_model,
            })


class _RecordingA1111Handler(BaseHTTPRequestHandler):
    server: _RecordingA1111Server

    def log_message(self, _format, *_args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/sdapi/v1/options":
            self.server.record("GET", self.path)
            self._send_json(200, {"sd_model_checkpoint": self.server.current_model})
            return
        if self.path == "/sdapi/v1/progress":
            self._send_json(200, {
                "progress": 0.5,
                "state": {"sampling_step": 1, "sampling_steps": 2},
            })
            return
        self._send_json(404, {"detail": "not found"})

    def do_POST(self):
        payload = self._read_json()
        if self.path == "/sdapi/v1/options":
            if 200 <= self.server.model_switch_status < 300:
                self.server.current_model = payload.get(
                    "sd_model_checkpoint", self.server.current_model
                )
            self.server.record("POST", self.path, payload)
            self._send_json(
                self.server.model_switch_status,
                {} if self.server.model_switch_status < 300 else {"error": "model switch failed"},
            )
            return
        if self.path == "/sdapi/v1/txt2img":
            self.server.record("POST", self.path, payload)
            first = base64.b64encode(self.server.first_image).decode("ascii")
            second = base64.b64encode(self.server.second_image).decode("ascii")
            self._send_json(200, {
                "images": [f"data:image/png;base64,{first}", second],
                "info": json.dumps({"seed": 4242}),
            })
            return
        self._send_json(404, {"detail": "not found"})


class GenerationApiRemoteWebUiE2ETests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.first_image = _png_bytes("red")
        self.second_image = _png_bytes("blue")
        self.remote = _RecordingA1111Server(self.first_image, self.second_image)
        self.remote_thread = threading.Thread(
            target=self.remote.serve_forever,
            name="fake-a1111-server",
            daemon=True,
        )
        self.remote_thread.start()

        root = Path(self.temp.name)
        self.manager = GenerationApiManager(
            config_path=root / "generation_api.json",
            storage_root=root / "results",
            coordinator=GenerationResourceCoordinator(),
        )

    def tearDown(self):
        self.manager.shutdown()
        self.remote.shutdown()
        self.remote.server_close()
        self.remote_thread.join(2)
        self.temp.cleanup()

    def test_named_webui_target_relays_t2i_model_override_and_all_images(self):
        remote_root = f"http://127.0.0.1:{self.remote.server_address[1]}"
        self.manager.save_config({
            "defaultTarget": "studio-forge",
            "targets": [{
                "id": "studio-forge",
                "name": "Studio Forge",
                "engine": "webui",
                "url": remote_root,
                "enabled": True,
            }],
        })

        submitted = self.manager.submit({
            "target": "studio-forge",
            "mode": "txt2img",
            "model": "requested-model.safetensors",
            "payload": {
                "prompt": "a red kite above a blue sea",
                "negative_prompt": "text, watermark",
                "steps": 7,
                "width": 512,
                "height": 512,
            },
        })
        completed = self.manager.wait(submitted["id"], timeout=5)

        self.assertEqual(completed["state"], "completed", completed)
        options_posts = [
            call for call in self.remote.calls
            if call["method"] == "POST" and call["path"] == "/sdapi/v1/options"
        ]
        self.assertEqual(options_posts, [{
            "method": "POST",
            "path": "/sdapi/v1/options",
            "payload": {"sd_model_checkpoint": "requested-model.safetensors"},
            "active_model": "requested-model.safetensors",
        }])

        generation_calls = [
            call for call in self.remote.calls
            if call["method"] == "POST" and call["path"] == "/sdapi/v1/txt2img"
        ]
        self.assertEqual(len(generation_calls), 1)
        generation = generation_calls[0]
        self.assertEqual(generation["active_model"], "requested-model.safetensors")
        self.assertEqual(generation["payload"]["prompt"], "a red kite above a blue sea")
        self.assertEqual(generation["payload"]["negative_prompt"], "text, watermark")
        self.assertEqual(generation["payload"]["steps"], 7)

        self.assertEqual(completed["info"]["seed"], 4242)
        self.assertEqual(completed["info"]["artifact_count"], 2)
        self.assertEqual(
            [(item["filename"], item["mime"]) for item in completed["artifacts"]],
            [("image_001.png", "image/png"), ("image_002.png", "image/png")],
        )
        first_data, first_mime, _first_name = self.manager.artifact(submitted["id"], 0)
        second_data, second_mime, _second_name = self.manager.artifact(submitted["id"], 1)
        self.assertEqual((first_data, first_mime), (self.first_image, "image/png"))
        self.assertEqual((second_data, second_mime), (self.second_image, "image/png"))

    def test_model_switch_failure_fails_job_without_txt2img_dispatch(self):
        self.remote.model_switch_status = 500
        remote_root = f"http://127.0.0.1:{self.remote.server_address[1]}"
        self.manager.save_config({
            "defaultTarget": "studio-forge",
            "targets": [{
                "id": "studio-forge",
                "name": "Studio Forge",
                "engine": "webui",
                "url": remote_root,
                "enabled": True,
            }],
        })

        submitted = self.manager.submit({
            "target": "studio-forge",
            "mode": "txt2img",
            "model": "broken-model.safetensors",
            "payload": {"prompt": "must not be dispatched"},
        })
        failed = self.manager.wait(submitted["id"], timeout=5)

        self.assertEqual(failed["state"], "failed", failed)
        options_posts = [
            call for call in self.remote.calls
            if call["method"] == "POST" and call["path"] == "/sdapi/v1/options"
        ]
        generation_posts = [
            call for call in self.remote.calls
            if call["method"] == "POST" and call["path"] == "/sdapi/v1/txt2img"
        ]
        self.assertEqual(len(options_posts), 1)
        self.assertEqual(generation_posts, [])
        self.assertEqual(self.remote.current_model, "initial-model.safetensors")


if __name__ == "__main__":
    unittest.main()

"""Forge classic 은 요청 본문의 forge_additional_modules 를 읽지 않는다 — 옵션으로 동기화해야 한다."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from backends.webui_backend import WebUIBackend


class _Resp:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


FORGE_OPTS = {
    "sd_model_checkpoint": "krea2_raw_bf16.safetensors",
    "forge_additional_modules": [],
}
ANIMA_MODULES = [
    "qwenImage_qwenImageVAE.safetensors",
    "Anima-3.8B-expanded_adapter.safetensors",
    "qwen35_4b.safetensors",
    "qwen_3_06b_base.safetensors",
]


class ForgeModuleSyncTests(unittest.TestCase):
    def setUp(self):
        self.backend = WebUIBackend("http://127.0.0.1:17860")

    def _run(self, options, model, modules):
        with patch("backends.webui_backend.requests.get", return_value=_Resp(options)), \
             patch("backends.webui_backend.requests.post", return_value=_Resp({})) as post:
            self.backend._switch_model_if_needed(model, modules)
        return post

    def test_anima_switch_sends_modules_and_checkpoint_in_one_post(self):
        """예전엔 체크포인트만 바꿔 Anima 가 VAE 없이 로드됐다 — 'You do not have VAE state dict!'."""
        post = self._run(FORGE_OPTS, "Anima-3.8B-v1.1.safetensors", ANIMA_MODULES)
        self.assertEqual(post.call_count, 1)
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["sd_model_checkpoint"], "Anima-3.8B-v1.1.safetensors")
        self.assertEqual(body["forge_additional_modules"], sorted(ANIMA_MODULES))
        self.assertEqual(list(body), ["forge_additional_modules", "sd_model_checkpoint"], "모듈이 체크포인트보다 먼저")

    def test_same_modules_by_basename_do_not_repost(self):
        """옵션엔 전체 경로가, 요청엔 파일명이 온다 — 파일명이 같으면 다시 보내지 않는다(재로딩 방지)."""
        opts = dict(FORGE_OPTS, sd_model_checkpoint="Anima-3.8B-v1.1.safetensors",
                    forge_additional_modules=[f"C:\\\\sd-webui-forge-classic\\\\models\\\\text_encoder\\\\{n}" for n in ANIMA_MODULES])
        post = self._run(opts, "Anima-3.8B-v1.1.safetensors", list(reversed(ANIMA_MODULES)))
        self.assertEqual(post.call_count, 0)

    def test_empty_request_clears_leftover_modules(self):
        """모듈이 필요 없는 체크포인트로 가면 남아 있던 Anima 모듈을 비운다."""
        opts = dict(FORGE_OPTS, forge_additional_modules=["C:/x/models/VAE/qwen_image_vae.safetensors"])
        post = self._run(opts, "krea2_raw_bf16.safetensors", [])
        self.assertEqual(post.call_args.kwargs["json"], {"forge_additional_modules": []})

    def test_a1111_without_the_option_only_switches_checkpoint(self):
        post = self._run({"sd_model_checkpoint": "a.safetensors"}, "b.safetensors", ANIMA_MODULES)
        self.assertEqual(post.call_args.kwargs["json"], {"sd_model_checkpoint": "b.safetensors"})

    def test_no_modules_key_leaves_modules_alone(self):
        opts = dict(FORGE_OPTS, forge_additional_modules=["C:/x/vae.safetensors"])
        post = self._run(opts, "krea2_raw_bf16.safetensors", None)
        self.assertEqual(post.call_count, 0)

    def test_generate_passes_payload_modules(self):
        """_generate 가 본문의 모듈을 동기화 함수로 넘긴다 — 여기서 끊기면 위 테스트가 다 헛것이다."""
        seen = {}
        with patch.object(self.backend, "_switch_model_if_needed", side_effect=lambda m, mods=None: seen.update(model=m, modules=mods)), \
             patch("backends.webui_backend.requests.post", side_effect=RuntimeError("stop here")):
            result = self.backend._generate("/sdapi/v1/txt2img", "Anima-3.8B-v1.1.safetensors",
                                            {"prompt": "x", "forge_additional_modules": ANIMA_MODULES})
        self.assertFalse(result.success)
        self.assertEqual(seen, {"model": "Anima-3.8B-v1.1.safetensors", "modules": ANIMA_MODULES})


class ProgressPreviewTests(unittest.TestCase):
    """/progress 의 current_image 는 접두사 없는 base64 로, 없으면 None 으로."""

    def test_plain_and_data_url_forms(self):
        b64 = "A" * 100
        self.assertEqual(WebUIBackend._progress_preview({"current_image": b64}), b64)
        self.assertEqual(WebUIBackend._progress_preview({"current_image": "data:image/png;base64," + b64}), b64)

    def test_missing_or_tiny_is_none(self):
        self.assertIsNone(WebUIBackend._progress_preview({"current_image": None}))
        self.assertIsNone(WebUIBackend._progress_preview({"current_image": ""}))
        self.assertIsNone(WebUIBackend._progress_preview({"current_image": "short"}))
        self.assertIsNone(WebUIBackend._progress_preview("not a dict"))

    def test_polling_forwards_a_preview_only_when_it_changes(self):
        import threading
        backend = WebUIBackend("http://127.0.0.1:17860")
        b64 = "B" * 100
        responses = [
            {"state": {"sampling_step": 1, "sampling_steps": 4}, "current_image": b64},
            {"state": {"sampling_step": 2, "sampling_steps": 4}, "current_image": b64},
            {"state": {"sampling_step": 3, "sampling_steps": 4}, "current_image": "C" * 100},
        ]
        seen = []
        stop = threading.Event()

        def fake_get(url, timeout=3):
            data = responses.pop(0)
            if not responses:
                stop.set()
            return _Resp(data)

        with patch("backends.webui_backend.requests.get", side_effect=fake_get):
            backend._start_progress_polling(lambda step, total, preview: seen.append((step, preview)), stop)
        self.assertEqual(seen, [(1, b64), (2, None), (3, "C" * 100)])


if __name__ == "__main__":
    unittest.main()

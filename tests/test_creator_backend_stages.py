"""CPU-only contracts for explicit non-media Creator workflow completion."""
import unittest
from unittest import mock

import requests

from backends.base import GenerationResult
from backends.comfyui_backend import ComfyUIBackend


def response(data):
    result = mock.Mock()
    result.json.return_value = data
    result.raise_for_status.return_value = None
    return result


class CreatorBackendStageTests(unittest.TestCase):
    def setUp(self):
        self.backend = ComfyUIBackend("http://127.0.0.1:8188")

    def fetch(self, entry, **kwargs):
        with mock.patch("backends.comfyui_backend.requests.get", return_value=response({"ours": entry})):
            return self.backend._fetch_result_artifacts("ours", **kwargs)

    def test_encoding_pass_exposes_cache_metadata_without_media(self):
        outputs = {"17": {"aistudio_cache": [{"key": "a" * 64, "hit": True}]}}
        result = self.fetch({"outputs": outputs, "status": {"completed": True, "status_str": "success"}}, allow_empty_outputs=True)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.info["node_outputs"], outputs)
        self.assertEqual(result.info["artifact_count"], 0)
        self.assertEqual(result.artifacts, [])

    def test_non_media_success_requires_explicit_opt_in(self):
        result = self.fetch({"outputs": {}, "status": {"completed": True, "status_str": "success"}})
        self.assertFalse(result.success)

    def test_encoding_never_treats_missing_running_failed_or_malformed_as_success(self):
        for entry in ({}, None, [], {"outputs": None}, {"status": None},
                      {"status": {"completed": False, "status_str": "success"}},
                      {"status": {"completed": True, "status_str": "error"}}):
            with self.subTest(entry=entry):
                self.assertFalse(self.fetch(entry, allow_empty_outputs=True).success)

    def test_opt_in_does_not_mask_failed_real_media_download(self):
        entry = {"outputs": {"1": {"images": [{"filename": "missing.png"}]}},
                 "status": {"completed": True, "status_str": "success"}}
        with mock.patch("backends.comfyui_backend.requests.get", side_effect=[
            response({"ours": entry}), requests.ConnectionError("offline")
        ]):
            result = self.backend._fetch_result_artifacts("ours", allow_empty_outputs=True)
        self.assertFalse(result.success)
        self.assertIn("missing.png", result.error)

    def test_runner_propagates_encoding_opt_in_and_cancellation(self):
        workflow = {"1": {"class_type": "ForgeNeoH3ConditioningCachePrepare", "inputs": {}}}
        callback, cancel = mock.Mock(), mock.Mock(return_value=False)
        expected = GenerationResult(success=True)
        with mock.patch.object(self.backend, "_queue_and_wait", return_value=expected) as run:
            result = self.backend.run_workflow(workflow, callback, cancel, allow_empty_outputs=True)
        self.assertIs(result, expected)
        run.assert_called_once_with(workflow, callback, cancel, allow_empty_outputs=True)


if __name__ == "__main__":
    unittest.main()

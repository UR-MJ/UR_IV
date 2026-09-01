"""ComfyUI multi-media result and workflow progress regression tests."""
from __future__ import annotations

import json
import unittest
from unittest import mock

import requests

from backends.base import GenerationResult, MediaArtifact
from backends.comfyui_backend import ComfyUIBackend
from backends.comfyui_progress import ProgressTracker


class _FakeResponse:
    def __init__(self, *, payload=None, content=b'', content_type=None):
        self._payload = payload
        self.content = content
        self.headers = {}
        if content_type:
            self.headers['Content-Type'] = content_type

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeWebSocket:
    def __init__(self, messages):
        self._messages = iter(messages)

    def recv(self):
        return json.dumps(next(self._messages))


class TestMediaResultContract(unittest.TestCase):
    def test_artifact_image_backfills_legacy_image_data(self):
        artifact = MediaArtifact(
            kind='image', data=b'png', filename='result.png', mime='image/png'
        )

        result = GenerationResult(success=True, artifacts=[artifact])

        self.assertEqual(result.image_data, b'png')
        self.assertEqual(result.artifacts, [artifact])

    def test_explicit_legacy_image_data_remains_authoritative(self):
        result = GenerationResult(
            success=True,
            image_data=b'legacy',
            artifacts=[MediaArtifact(kind='image', data=b'new')],
        )

        self.assertEqual(result.image_data, b'legacy')


class TestComfyMediaFetch(unittest.TestCase):
    def setUp(self):
        self.backend = ComfyUIBackend('http://127.0.0.1:8188')

    def test_collects_all_supported_media_and_deduplicates(self):
        history = {
            'prompt-1': {
                'outputs': {
                    '10': {
                        'images': [
                            {'filename': 'still.png', 'subfolder': 'a', 'type': 'output'},
                            {'filename': 'still.png', 'subfolder': 'a', 'type': 'output'},
                        ],
                    },
                    '20': {
                        # Video Combine commonly exposes mp4 files under "gifs".
                        'gifs': [
                            {'filename': 'loop.webp', 'type': 'output'},
                            {'filename': 'clip.mp4', 'type': 'output'},
                        ],
                    },
                    '30': {
                        'audio': [{'filename': 'sound.wav', 'type': 'output'}],
                    },
                    '40': {
                        'files': [{'filename': 'preview.gif', 'type': 'output'}],
                    },
                    '50': {
                        'custom_media': [{'filename': 'custom.jpg', 'type': 'output'}],
                    },
                },
            },
        }
        media = {
            'still.png': (b'png', 'image/png'),
            'loop.webp': (b'webp', 'image/webp'),
            'clip.mp4': (b'mp4', 'video/mp4'),
            'sound.wav': (b'wav', 'audio/wav'),
            'preview.gif': (b'gif', 'image/gif'),
            'custom.jpg': (b'jpg', 'image/jpeg'),
        }

        def fake_get(url, **kwargs):
            if '/history/' in url:
                return _FakeResponse(payload=history)
            filename = kwargs['params']['filename']
            content, mime = media[filename]
            return _FakeResponse(content=content, content_type=mime)

        with mock.patch('backends.comfyui_backend.requests.get', side_effect=fake_get):
            result = self.backend._fetch_result_artifacts('prompt-1')

        self.assertTrue(result.success)
        self.assertEqual(
            [artifact.kind for artifact in result.artifacts],
            ['image', 'animated', 'video', 'audio', 'animated', 'image'],
        )
        self.assertEqual(result.image_data, b'png')
        self.assertEqual(result.info['artifact_count'], 6)
        self.assertEqual(result.info['filename'], 'still.png')
        self.assertEqual(result.artifacts[0].metadata['node_id'], '10')
        self.assertEqual(result.artifacts[0].metadata['subfolder'], 'a')

    def test_video_only_result_succeeds_without_legacy_image(self):
        history = {
            'video-job': {
                'outputs': {
                    '7': {
                        'videos': [{'filename': 'movie.webm', 'type': 'output'}],
                    },
                },
            },
        }

        def fake_get(url, **_kwargs):
            if '/history/' in url:
                return _FakeResponse(payload=history)
            return _FakeResponse(content=b'video', content_type='video/webm')

        with mock.patch('backends.comfyui_backend.requests.get', side_effect=fake_get):
            result = self.backend._fetch_result_artifacts('video-job')

        self.assertTrue(result.success)
        self.assertIsNone(result.image_data)
        self.assertEqual(result.artifacts[0].kind, 'video')
        self.assertEqual(result.artifacts[0].data, b'video')

    def test_one_failed_download_does_not_discard_other_artifacts(self):
        history = {
            'partial': {
                'outputs': {
                    '1': {
                        'images': [
                            {'filename': 'missing.png'},
                            {'filename': 'ok.png'},
                        ],
                    },
                },
            },
        }

        def fake_get(url, **kwargs):
            if '/history/' in url:
                return _FakeResponse(payload=history)
            if kwargs['params']['filename'] == 'missing.png':
                raise requests.ConnectionError('offline')
            return _FakeResponse(content=b'ok', content_type='image/png')

        with mock.patch('backends.comfyui_backend.requests.get', side_effect=fake_get):
            result = self.backend._fetch_result_artifacts('partial')

        self.assertTrue(result.success)
        self.assertEqual(result.image_data, b'ok')
        self.assertEqual(result.info['artifact_download_errors'], ['missing.png'])

    def test_artifact_count_limit_rejects_extra_media(self):
        history = {
            'limited-count': {
                'outputs': {
                    '1': {
                        'images': [
                            {'filename': 'first.png'},
                            {'filename': 'second.png'},
                        ],
                    },
                },
            },
        }
        viewed = []

        def fake_get(url, **kwargs):
            if '/history/' in url:
                return _FakeResponse(payload=history)
            viewed.append(kwargs['params']['filename'])
            return _FakeResponse(content=b'png', content_type='image/png')

        with mock.patch(
            'backends.comfyui_backend._MAX_RESULT_ARTIFACTS', 1
        ), mock.patch(
            'backends.comfyui_backend.requests.get', side_effect=fake_get
        ):
            result = self.backend._fetch_result_artifacts('limited-count')

        self.assertFalse(result.success)
        self.assertIn('최대 1개', result.error)
        self.assertEqual(result.artifacts, [])
        self.assertEqual(viewed, ['first.png'])

    def test_artifact_total_size_limit_rejects_oversized_media(self):
        history = {
            'limited-size': {
                'outputs': {
                    '1': {'images': [{'filename': 'large.png'}]},
                },
            },
        }

        def fake_get(url, **_kwargs):
            if '/history/' in url:
                return _FakeResponse(payload=history)
            return _FakeResponse(content=b'12345', content_type='image/png')

        with mock.patch(
            'backends.comfyui_backend._MAX_RESULT_BYTES', 4
        ), mock.patch(
            'backends.comfyui_backend.requests.get', side_effect=fake_get
        ):
            result = self.backend._fetch_result_artifacts('limited-size')

        self.assertFalse(result.success)
        self.assertIn('총 용량', result.error)
        self.assertEqual(result.artifacts, [])

    def test_public_workflow_seam_delegates_to_generic_runner(self):
        workflow = {'1': {'class_type': 'SaveImage', 'inputs': {}}}
        expected = GenerationResult(success=True)
        callback = mock.Mock()

        with mock.patch.object(
            self.backend, '_queue_and_wait', return_value=expected
        ) as queue:
            result = self.backend.run_workflow(workflow, callback)

        self.assertIs(result, expected)
        queue.assert_called_once_with(workflow, callback)

    def test_public_workflow_seam_rejects_non_api_workflow(self):
        with mock.patch.object(self.backend, '_queue_and_wait') as queue:
            result = self.backend.run_workflow({'nodes': []})

        self.assertFalse(result.success)
        self.assertIn('API', result.error)
        queue.assert_not_called()

    def test_upload_media_returns_comfy_input_name(self):
        response = _FakeResponse(payload={'name': 'source.png', 'subfolder': 'studio'})

        with mock.patch(
            'backends.comfyui_backend.requests.post', return_value=response
        ) as post:
            name = self.backend.upload_media(
                b'input', 'source.png', 'image/png', overwrite=False
            )

        self.assertEqual(name, 'studio/source.png')
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['files']['image'], ('source.png', b'input', 'image/png'))
        self.assertEqual(kwargs['data'], {'overwrite': 'false'})

    def test_upload_media_rejects_paths(self):
        with self.assertRaises(ValueError):
            self.backend.upload_media(b'input', '../source.png')


class TestProgressTracker(unittest.TestCase):
    def setUp(self):
        self.workflow = {
            '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {}},
            '2': {'class_type': 'CLIPTextEncode', 'inputs': {}},
            '3': {'class_type': 'KSampler', 'inputs': {}},
            '4': {'class_type': 'VAEDecode', 'inputs': {}},
            '5': {'class_type': 'SaveImage', 'inputs': {}},
        }

    def test_cached_and_fractional_events_are_monotonic(self):
        tracker = ProgressTracker(self.workflow)
        messages = [
            {'type': 'status', 'data': {'status': {}}},
            {'type': 'execution_cached', 'data': {'nodes': ['1', '2']}},
            {'type': 'executing', 'data': {'node': '3'}},
            {'type': 'progress', 'data': {'node': '3', 'value': 7, 'max': 10}},
            # A stale/reordered sampler update must not move backwards.
            {'type': 'progress', 'data': {'node': '3', 'value': 4, 'max': 10}},
            {'type': 'executing', 'data': {'node': '4'}},
            {'type': 'executing', 'data': {'node': None}},
        ]

        updates = [tracker.consume(message) for message in messages]
        steps = [update.step for update in updates if update is not None]

        self.assertEqual(steps[0], 0)
        self.assertEqual(steps[-1], 100)
        self.assertEqual(steps, sorted(steps))
        self.assertEqual(steps[3], steps[4])
        self.assertEqual(updates[2].node_class, 'KSampler')

    def test_sampler_fraction_has_more_weight_than_loader_completion(self):
        tracker = ProgressTracker(self.workflow)
        loader = tracker.consume(
            {'type': 'execution_cached', 'data': {'nodes': ['1']}}
        )
        tracker.consume({'type': 'executing', 'data': {'node': '3'}})
        sampler_half = tracker.consume(
            {'type': 'progress', 'data': {'node': '3', 'value': 1, 'max': 2}}
        )

        self.assertGreater(sampler_half.step - loader.step, loader.step)

    def test_unknown_events_do_not_change_interface(self):
        tracker = ProgressTracker(self.workflow)
        self.assertIsNone(tracker.consume({'type': 'unrelated', 'data': {}}))

    def test_backend_wait_preserves_three_argument_callback(self):
        ws = _FakeWebSocket([
            {'type': 'status', 'data': {'status': {}}},
            {
                'type': 'progress',
                'data': {'prompt_id': 'someone-else', 'node': '3', 'value': 9, 'max': 10},
            },
            {'type': 'execution_cached', 'data': {'prompt_id': 'ours', 'nodes': ['1']}},
            {'type': 'executing', 'data': {'prompt_id': 'ours', 'node': '3'}},
            {
                'type': 'progress',
                'data': {'prompt_id': 'ours', 'node': '3', 'value': 5, 'max': 10},
            },
            {'type': 'executing', 'data': {'prompt_id': 'ours', 'node': None}},
        ])
        backend = ComfyUIBackend('http://127.0.0.1:8188')
        callback_calls = []
        fetched = GenerationResult(
            success=True,
            artifacts=[MediaArtifact(kind='video', data=b'video')],
        )

        with mock.patch.object(
            backend, '_fetch_result_artifacts', return_value=fetched
        ) as fetch:
            result = backend._wait_for_result(
                ws,
                'ours',
                lambda step, total, preview: callback_calls.append(
                    (step, total, preview)
                ),
                tracker=ProgressTracker(self.workflow),
            )

        self.assertIs(result, fetched)
        fetch.assert_called_once_with('ours')
        self.assertTrue(callback_calls)
        self.assertEqual([call[0] for call in callback_calls], sorted(
            call[0] for call in callback_calls
        ))
        self.assertEqual(callback_calls[-1], (100, 100, None))
        self.assertTrue(all(len(call) == 3 for call in callback_calls))


if __name__ == '__main__':
    unittest.main()

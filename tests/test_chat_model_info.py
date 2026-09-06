import unittest
import json
import threading
import time
from unittest.mock import Mock, patch

from core.ollama_client import OllamaClient, summarize_model_info


class ChatModelInfoTests(unittest.TestCase):
    def test_thinking_level_survives_stream_payload_without_boolean_coercion(self):
        from tests.test_chat_feature import _FakeResponse, _chunks
        with patch('core.ollama_client.requests.post', return_value=_FakeResponse(_chunks('ok'))) as post:
            OllamaClient(model='custom-gptoss').chat_stream([], think='low')
        self.assertEqual(post.call_args.kwargs['json']['think'], 'low')

    def test_rejected_explicit_thinking_level_does_not_silently_fall_back(self):
        from tests.test_chat_feature import _FakeResponse
        refused = _FakeResponse([], status=400, error_json={'error': 'unsupported think level'})
        with patch('core.ollama_client.requests.post', return_value=refused) as post:
            with self.assertRaisesRegex(RuntimeError, 'unsupported think level'):
                OllamaClient().chat_stream([], think='high')
        self.assertEqual(post.call_count, 1)

    def test_rejected_boolean_setting_does_not_silently_enable_model_defaults(self):
        from tests.test_chat_feature import _FakeResponse, _chunks
        for think, error in ((False, 'thinking only supports levels'),
                             (False, 'invalid think value'),
                             (True, '"m" does not support thinking')):
            with self.subTest(think=think, error=error):
                refused = _FakeResponse([], status=400, error_json={'error': error})
                with patch('core.ollama_client.requests.post',
                           side_effect=[refused, _FakeResponse(_chunks('silent fallback'))]) as post:
                    with self.assertRaises(RuntimeError):
                        OllamaClient(model='m').chat_stream([], think=think)
                self.assertEqual(post.call_count, 1)

    def test_moe_expert_metadata_is_read_only_and_thinking_is_independent(self):
        response = Mock()
        response.json.return_value = {'details': {'family': 'qwen3moe', 'parameter_size': '30B'},
            'capabilities': ['completion', 'thinking'], 'model_info': {
                'general.architecture': 'qwen3moe', 'qwen3moe.expert_count': 128,
                'qwen3moe.expert_used_count': 8, 'qwen3moe.context_length': 40960}}
        with patch('core.ollama_client.requests.post', return_value=response) as post:
            info = OllamaClient(model='my-renamed-model').get_model_info()
        self.assertEqual((info['moe'], info['experts'], info['activeExperts']), (True, 128, 8))
        self.assertEqual(info['thinkingMode'], 'boolean')
        self.assertEqual(info['contextLength'], 40960)
        self.assertFalse(info['vision'])
        self.assertEqual(post.call_args.args[0], 'http://localhost:11434/api/show')
        self.assertEqual(post.call_args.kwargs['json'], {'model': 'my-renamed-model', 'verbose': False})

    def test_missing_metadata_never_guesses_moe_or_capabilities(self):
        info = summarize_model_info({'details': {'family': 'some-moe-looking-name'}})
        self.assertIsNone(info['moe'])
        self.assertIsNone(info['vision'])
        self.assertEqual(info['thinkingMode'], 'unknown')

    def test_gptoss_levels_come_from_architecture_not_model_filename(self):
        info = summarize_model_info({'model_info': {'general.architecture': 'gptoss'},
                                     'capabilities': ['completion', 'thinking']})
        self.assertEqual(info['thinkingMode'], 'levels')
        self.assertEqual(summarize_model_info({'capabilities': ['completion']})['thinkingMode'], 'none')

    def test_metadata_action_coalesces_rapid_selection_without_blocking_ui(self):
        from PyQt6.QtCore import QCoreApplication, pyqtSignal
        from tests.test_chat_generation_actions import Host, Bridge
        class ModelBridge(Bridge):
            chatModelInfo = pyqtSignal(str)
        app = QCoreApplication.instance() or QCoreApplication([])
        host = Host()
        host.vue_bridge = ModelBridge(host)
        events, calls = [], []
        entered, release = threading.Event(), threading.Event()
        host.vue_bridge.chatModelInfo.connect(lambda raw: events.append(json.loads(raw)))
        def model_info(client):
            calls.append((client.model, threading.get_ident()))
            if client.model == 'first':
                entered.set()
                release.wait(2)
            return {'architecture': client.model}
        with patch.object(OllamaClient, 'get_model_info', model_info):
            try:
                host._handle_chat_action('chat_model_info', {'id': 'a', 'model': 'first'})
                self.assertTrue(entered.wait(1))
                host._handle_chat_action('chat_model_info', {'id': 'b', 'model': 'second'})
                host._handle_chat_action('chat_model_info', {'id': 'c', 'model': 'third'})
                release.set()
                end = time.monotonic() + 2
                while len(events) < 2 and time.monotonic() < end:
                    app.processEvents()
                    time.sleep(.002)
                self.assertEqual([call[0] for call in calls], ['first', 'third'])
                self.assertTrue(all(call[1] != threading.get_ident() for call in calls))
                self.assertEqual([event['id'] for event in events], ['a', 'c'])
                self.assertTrue(all(event['ok'] for event in events))
            finally:
                release.set()


if __name__ == '__main__':
    unittest.main()

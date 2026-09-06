"""Offline regressions for visible UI feedback; no GPU jobs or real clipboard writes."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ui.generator_main import GeneratorMainUI
from ui.vue_bridge import VueBridge


class UIFeedbackTests(unittest.TestCase):
    def test_existing_runtime_paths_open_picker_and_cancel_without_mutation(self):
        snapshot = {'engines': {
            'forge': {'existingRoot': 'C:/existing-forge', 'extensionDir': 'C:/existing-forge/extensions'},
            'comfyui': {'existingRoot': 'C:/existing-comfy', 'extensionDir': 'C:/existing-comfy/custom_nodes'},
        }}
        host = SimpleNamespace(_backend_runtime_is_web_mode=lambda: False,
                               _backend_runtime_engine=lambda engine: (engine, engine),
                               _backend_runtime_public_snapshot=lambda: snapshot, parent=lambda: None)
        for engine in snapshot['engines']:
            for method, key in ((VueBridge.selectBackendInstallDirectory, 'existingRoot'),
                                (VueBridge.selectBackendExtensionDirectory, 'extensionDir')):
                with self.subTest(engine=engine, key=key), patch('ui.native_dialogs.select_directory', return_value=None) as picker:
                    reply = json.loads(method(host, engine))
                    self.assertTrue(reply['cancelled'])
                    self.assertFalse(reply['ok'])
                    self.assertEqual(picker.call_args.args[2], snapshot['engines'][engine][key])

    def test_forge_model_picker_uses_configured_path_and_returns_selection(self):
        host = SimpleNamespace(_backend_runtime_is_web_mode=lambda: False, parent=lambda: None)
        with patch('core.forge_modules.get_forge_paths', return_value={'checkpoint_dir': Path('C:/existing-models')}), \
             patch('ui.native_dialogs.select_directory', return_value='C:/chosen-models') as picker:
            reply = json.loads(VueBridge.selectForgeModelDirectory(host, 'checkpoint_dir'))
        self.assertEqual(reply, {'ok': True, 'key': 'checkpoint_dir', 'path': 'C:/chosen-models'})
        self.assertEqual(picker.call_args.args[2], str(Path('C:/existing-models')))

    def test_vram_poll_does_not_overlap_slow_reads_and_recovers_after_error(self):
        started = []
        def thread_factory(*, target, daemon):
            return SimpleNamespace(start=lambda: started.append(target))
        host = SimpleNamespace(vue_bridge=SimpleNamespace(vramUpdated=Mock()))
        with patch('threading.Thread', side_effect=thread_factory):
            GeneratorMainUI._update_vram_status(host)
            GeneratorMainUI._update_vram_status(host)
            self.assertEqual(len(started), 1, '1-second polls must not pile up slow workers')
            with patch('core.gpu_stats.read_vram', side_effect=RuntimeError('offline')):
                started.pop()()
            GeneratorMainUI._update_vram_status(host)
            self.assertEqual(len(started), 1)
            with patch('core.gpu_stats.read_vram', return_value={'vram_used': 2**30, 'vram_total': 8 * 2**30, 'source': 'fake'}):
                started.pop()()
        data = json.loads(host.vue_bridge.vramUpdated.emit.call_args.args[0])
        self.assertEqual(data['used'], 1)
        self.assertEqual(data['total'], 8)

    def test_desktop_text_clipboard_reports_success_only_after_write(self):
        host = SimpleNamespace(_backend_runtime_is_web_mode=lambda: False)
        clipboard = Mock()
        clipboard.text.return_value = 'prompt\nnegative'
        with patch('PyQt6.QtWidgets.QApplication.clipboard', return_value=clipboard):
            self.assertTrue(VueBridge.copyTextToClipboard(host, 'prompt\nnegative'))
        clipboard.setText.assert_called_once_with('prompt\nnegative')

    def test_remote_web_cannot_touch_host_clipboard(self):
        host = SimpleNamespace(_backend_runtime_is_web_mode=lambda: True)
        with patch('PyQt6.QtWidgets.QApplication.clipboard') as clipboard:
            self.assertFalse(VueBridge.copyTextToClipboard(host, 'remote text'))
        clipboard.assert_not_called()

    def test_failed_clipboard_write_is_not_reported_as_success(self):
        host = SimpleNamespace(_backend_runtime_is_web_mode=lambda: False)
        clipboard = Mock()
        clipboard.text.return_value = 'unchanged'
        with patch('PyQt6.QtWidgets.QApplication.clipboard', return_value=clipboard):
            self.assertFalse(VueBridge.copyTextToClipboard(host, 'new text'))


if __name__ == '__main__':
    unittest.main()

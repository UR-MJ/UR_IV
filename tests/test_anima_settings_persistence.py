"""ANIMA 설정 저장/복원 회귀 테스트."""

from pathlib import Path
import unittest

from core.anima_guidance import default_settings
from ui.generator_settings import SettingsMixin


class _Proxy:
    def __init__(self, value=''):
        self.value = str(value)

    def text(self):
        return self.value

    def setText(self, value):
        self.value = value


class TestAnimaSettingsPersistence(unittest.TestCase):
    def setUp(self):
        self.mixin = SettingsMixin()

    def test_collects_every_anima_widget_value(self):
        widgets = {
            key: _Proxy(f'value-{index}')
            for index, key in enumerate(default_settings())
        }
        saved = self.mixin._get_anima_guidance_settings(widgets)
        self.assertEqual(len(saved), 82)
        self.assertEqual(saved['guid_smc_preset'], widgets['guid_smc_preset'].text())
        self.assertEqual(saved['guid_rdc_tau'], widgets['guid_rdc_tau'].text())

    def test_old_saved_settings_gain_new_forge_defaults(self):
        widgets = {key: _Proxy('stale') for key in default_settings()}
        self.mixin._set_anima_guidance_settings(widgets, {'guid_enabled': True})
        self.assertEqual(widgets['guid_enabled'].text(), 'true')
        self.assertEqual(widgets['guid_smc_preset'].text(), 'Auto')
        self.assertEqual(widgets['guid_smc_master_enabled'].text(), 'false')
        self.assertEqual(widgets['guid_rdc_tau'].text(), '0.15')
        self.assertEqual(widgets['guid_rdc_alpha_ll'].text(), '0.03')

    def test_save_and_load_paths_include_anima_settings(self):
        source = (Path(__file__).resolve().parents[1] / 'ui' / 'generator_settings.py').read_text(
            encoding='utf-8'
        )
        self.assertGreaterEqual(source.count('"anima_guidance_settings"'), 3)


if __name__ == '__main__':
    unittest.main()

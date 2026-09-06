import copy
import unittest

from core.spectrum_settings import spectrum_payload_from_prefs, validate_spectrum_payload
from comfy_custom_nodes.ai_studio_forge_parity.spectrum_isolation import (
    copy_option_containers, isolated_sampler_model,
)


class SpectrumSettingsTests(unittest.TestCase):
    def test_off_is_zero_effect(self):
        for prefs in ({}, {"comfySpectrum": {"enabled": False}}, {"comfySpectrum": {"enabled": "false"}}):
            self.assertEqual(spectrum_payload_from_prefs(prefs), {})

    def test_enabled_uses_bounded_defaults(self):
        payload = spectrum_payload_from_prefs({"comfySpectrum": {"enabled": True}})
        self.assertTrue(payload["spectrum_one_sampler_only"])
        validate_spectrum_payload({**payload, "steps": 28}, {"DiTSpectrumPatch": {}})

    def test_nonfinite_fractional_boolean_rejected(self):
        for value in (float('nan'), float('inf'), True, 1.5, -1, 10000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                spectrum_payload_from_prefs({"comfySpectrum": {"enabled": True, "warmup_steps": value}})

    def test_missing_provider_and_no_cache_steps_rejected(self):
        for payload, info in (({"steps": 28}, {}), ({"steps": 9}, {"DiTSpectrumPatch": {}}),
                              ({"steps": 28, "speed_enabled": True}, {"DiTSpectrumPatch": {}})):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_spectrum_payload({"spectrum_enabled": True, **payload}, info)

    def test_container_copy_preserves_gpu_resources_and_cycles(self):
        class Resource:
            def __deepcopy__(self, memo):
                raise AssertionError('GPU/backend resource must not be deep-copied')
        resource = Resource()
        source = {"nested": [{"tensor": resource}]}
        source["cycle"] = source
        target = copy_option_containers(source)
        self.assertIs(target["nested"][0]["tensor"], resource)
        self.assertIs(target["cycle"], target)
        target["nested"][0]["run"] = 1
        self.assertNotIn("run", source["nested"][0])

    def test_each_sampler_has_fresh_options(self):
        class Model:
            model_options = {"transformer_options": {"state": []}}
            def clone(self):
                return copy.copy(self)
        original = Model()
        first = isolated_sampler_model(original)
        first.model_options["transformer_options"]["state"].append(1)
        second = isolated_sampler_model(original)
        self.assertEqual(second.model_options["transformer_options"]["state"], [])
        self.assertEqual(original.model_options["transformer_options"]["state"], [])


if __name__ == '__main__':
    unittest.main()

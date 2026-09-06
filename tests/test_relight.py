import unittest
from unittest.mock import Mock, patch
import numpy as np

from comfy_custom_nodes.ai_studio_forge_parity.relight import AIStudioRelight, relight_image, settings_from


class RelightTests(unittest.TestCase):
    def setUp(self):
        yy, xx = np.mgrid[:48, :64].astype(np.float32)
        self.depth = np.exp(-((xx - 32)**2 + (yy - 24)**2) / 170.)
        self.image = np.stack((.25 + xx / 200, .2 + yy / 150, np.full_like(xx, .4)), -1)

    def test_zero_strength_is_pixel_identical(self):
        result = relight_image(self.image, depth=self.depth, settings={"strength": 0})
        np.testing.assert_array_equal(result['image'], self.image)

    def test_input_not_mutated_and_deterministic(self):
        original = self.image.copy()
        first = relight_image(self.image, depth=self.depth)
        second = relight_image(self.image, depth=self.depth)
        np.testing.assert_array_equal(self.image, original)
        np.testing.assert_array_equal(first['image'], second['image'])
        self.assertGreater(np.max(np.abs(first['image'] - original)), .01)
        self.assertEqual(first['geometry'], 'depth')

    def test_mask_and_alpha_are_preserved(self):
        mask = np.zeros(self.image.shape[:2], np.float32)
        mask[:, 32:] = 1
        rgba = np.concatenate((self.image, np.full((*mask.shape, 1), .5)), -1).astype(np.float32)
        result = relight_image(rgba, depth=self.depth, mask=mask)['image']
        np.testing.assert_array_equal(result[:, :32], rgba[:, :32])
        np.testing.assert_array_equal(result[..., 3], rgba[..., 3])

    def test_direction_changes_result_and_no_nan(self):
        left = relight_image(self.image, depth=self.depth, settings={"azimuth": -90})
        right = relight_image(self.image, depth=self.depth, settings={"azimuth": 90})
        self.assertGreater(np.max(np.abs(left['image'] - right['image'])), .02)
        for value in (left['image'], left['normals'], left['shadow']):
            self.assertTrue(np.isfinite(value).all())
            self.assertGreaterEqual(float(value.min()), 0)
            self.assertLessEqual(float(value.max()), 1)

    def test_brightness_approximation_does_not_invent_cast_shadow(self):
        result = relight_image(self.image)
        self.assertEqual(result['geometry'], 'luminance-approximation')
        self.assertEqual(np.count_nonzero(result['shadow']), 0)

    def test_normal_map_is_used(self):
        normal = np.zeros_like(self.image)
        normal[..., 0] = 1
        normal[..., 1:] = .5
        first = relight_image(self.image, normals=normal, settings={"azimuth": 90})
        second = relight_image(self.image, normals=normal, settings={"azimuth": -90})
        self.assertGreater(float(first['image'].mean()), float(second['image'].mean()))
        self.assertEqual(first['geometry'], 'normal')

    def test_invalid_images_maps_settings_fail(self):
        for value in (np.full_like(self.image, np.nan), self.image * -1, np.zeros((1, 1, 3))):
            with self.assertRaises(ValueError): relight_image(value)
        with self.assertRaises(ValueError): relight_image(self.image, depth=np.zeros((8, 8)))
        for raw in ({"strength": float('inf')}, {"strength": True}, {"shadow_length": 5000}):
            with self.assertRaises(ValueError): settings_from(raw)

    def test_comfy_batch_limit_rejects_before_tensor_allocation(self):
        image = Mock(ndim=4, shape=(5, 1024, 1024, 3))
        with patch.dict('sys.modules', {'torch': Mock()}):
            with self.assertRaisesRegex(ValueError, '4 MP'):
                AIStudioRelight().apply(image)
        image.detach.assert_not_called()


if __name__ == '__main__': unittest.main()

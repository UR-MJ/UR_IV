"""톤 커브 LUT 회귀 테스트.

프론트가 그리는 곡선과 백엔드가 적용하는 곡선은 **정의가 같아야** 한다
(둘 다 정렬된 제어점 사이 선형보간). 여기서 백엔드 쪽 정의를 못박는다.
"""

from __future__ import annotations

import unittest

import numpy as np

from core.curves import (
    IDENTITY_POINTS,
    apply_curves,
    build_lut,
    channel_luts,
    is_identity,
    normalize_points,
)

RAMP = np.arange(256, dtype=np.uint8)


class BuildLutTests(unittest.TestCase):
    def test_identity_points_give_ramp(self):
        self.assertTrue(np.array_equal(build_lut(IDENTITY_POINTS), RAMP))

    def test_missing_points_fall_back_to_identity(self):
        for bad in (None, [], [(0.0, 0.0)], "nonsense", [(None, 1)]):
            self.assertTrue(np.array_equal(build_lut(bad), RAMP), bad)

    def test_endpoints_are_exact(self):
        lut = build_lut([(0.0, 0.25), (1.0, 0.75)])
        self.assertEqual(int(lut[0]), 64)
        self.assertEqual(int(lut[255]), 191)

    def test_unsorted_points_are_sorted_not_dropped(self):
        """제어점이 x 순으로 오지 않아도 같은 곡선이어야 한다.

        np.interp 는 xs 가 오름차순이 아니면 조용히 엉뚱한 값을 낸다.
        """
        forward = build_lut([(0.0, 0.0), (0.5, 0.9), (1.0, 1.0)])
        shuffled = build_lut([(1.0, 1.0), (0.0, 0.0), (0.5, 0.9)])
        self.assertTrue(np.array_equal(forward, shuffled))

    def test_out_of_range_points_are_clamped(self):
        lut = build_lut([(-3.0, -1.0), (2.0, 5.0)])
        self.assertTrue(np.array_equal(lut, RAMP))

    def test_midpoint_lift_is_monotonic_and_brighter(self):
        lut = build_lut([(0.0, 0.0), (0.5, 0.7), (1.0, 1.0)])
        self.assertTrue(np.all(np.diff(lut.astype(int)) >= 0))
        self.assertGreater(int(lut[128]), 128)

    def test_normalize_keeps_order_and_range(self):
        pts = normalize_points([(0.9, 2.0), (0.1, -1.0)])
        self.assertEqual(pts, [(0.1, 0.0), (0.9, 1.0)])


class ChannelLutTests(unittest.TestCase):
    def test_all_identity_gives_ramps(self):
        for lut in channel_luts({}):
            self.assertTrue(np.array_equal(lut, RAMP))

    def test_master_curve_applies_to_every_channel(self):
        curves = {'rgb': [(0.0, 0.0), (0.5, 0.7), (1.0, 1.0)]}
        expected = build_lut(curves['rgb'])
        for lut in channel_luts(curves):
            self.assertTrue(np.array_equal(lut, expected))

    def test_master_is_composed_on_top_of_channel_curve(self):
        """채널 커브를 먼저 태우고 그 결과를 마스터에 통과시킨다.

        순서를 뒤집으면 같은 설정이 다른 그림을 낸다 — PyQt 판과 같은 순서를 지킨다.
        """
        curves = {
            'rgb': [(0.0, 0.0), (0.5, 0.7), (1.0, 1.0)],
            'r': [(0.0, 0.0), (0.5, 0.3), (1.0, 1.0)],
        }
        lut_r, lut_g, lut_b = channel_luts(curves)
        master = build_lut(curves['rgb'])
        channel = build_lut(curves['r'])
        self.assertTrue(np.array_equal(lut_r, master[channel]))
        # 순서가 반대였다면 이것과 달라야 한다 (두 커브가 교환 가능하지 않음을 확인)
        self.assertFalse(np.array_equal(master[channel], channel[master]))
        # 손대지 않은 채널은 마스터만 탄다
        self.assertTrue(np.array_equal(lut_g, master))
        self.assertTrue(np.array_equal(lut_b, master))


class IdentityTests(unittest.TestCase):
    def test_empty_and_default_curves_are_identity(self):
        self.assertTrue(is_identity(None))
        self.assertTrue(is_identity({}))
        self.assertTrue(is_identity({ch: IDENTITY_POINTS for ch in ('rgb', 'r', 'g', 'b')}))

    def test_extra_points_on_the_diagonal_are_still_identity(self):
        """점을 찍었다가 대각선으로 되돌린 경우도 항등이다.

        점 개수만 세면 이걸 '변경됨'으로 보고 쓸데없는 프리뷰를 왕복한다.
        """
        self.assertTrue(is_identity({'rgb': [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]}))

    def test_moved_point_is_not_identity(self):
        self.assertFalse(is_identity({'b': [(0.0, 0.0), (0.5, 0.6), (1.0, 1.0)]}))


class ApplyCurvesTests(unittest.TestCase):
    def test_identity_curve_leaves_pixels_alone(self):
        img = np.random.randint(0, 256, (4, 5, 3), dtype=np.uint8)
        self.assertTrue(np.array_equal(apply_curves(img, {}), img))

    def test_master_curve_maps_every_channel_through_lut(self):
        img = np.random.randint(0, 256, (4, 5, 3), dtype=np.uint8)
        curves = {'rgb': [(0.0, 0.0), (0.5, 0.7), (1.0, 1.0)]}
        lut = build_lut(curves['rgb'])
        self.assertTrue(np.array_equal(apply_curves(img, curves), lut[img]))

    def test_channel_curve_touches_only_that_channel(self):
        """BGR 순서를 틀리면 빨강 커브가 파랑에 적용된다 — 흔한 실수라 못박는다."""
        img = np.full((2, 2, 3), 100, dtype=np.uint8)
        out = apply_curves(img, {'r': [(0.0, 0.0), (0.5, 0.9), (1.0, 1.0)]})
        self.assertEqual(int(out[0, 0, 0]), 100)   # B 그대로
        self.assertEqual(int(out[0, 0, 1]), 100)   # G 그대로
        self.assertGreater(int(out[0, 0, 2]), 100)  # R 만 밝아짐


class AdvColorIntegrationTests(unittest.TestCase):
    def test_adv_color_accepts_curves_and_preserves_alpha(self):
        from core.editor_ops import adv_color

        rgba = np.dstack([
            np.full((3, 3), 100, dtype=np.uint8),
            np.full((3, 3), 100, dtype=np.uint8),
            np.full((3, 3), 100, dtype=np.uint8),
            np.full((3, 3), 77, dtype=np.uint8),
        ])
        out = adv_color(rgba, curves={'rgb': [(0.0, 0.0), (0.5, 0.9), (1.0, 1.0)]})
        self.assertEqual(out.shape[2], 4)
        self.assertTrue(np.all(out[:, :, 3] == 77), "알파가 보존되지 않았다")
        self.assertGreater(int(out[0, 0, 0]), 100)

    def test_curves_survive_the_json_wire_format(self):
        """프론트는 `[[x, y], ...]` 를 JSON 으로 보낸다 — 튜플이 아니라 리스트다.

        테스트가 파이썬 튜플로만 돌면 실제 페이로드 모양을 한 번도 안 거치게 된다.
        """
        import json

        from core.editor_ops import adv_color

        payload = json.loads(json.dumps({
            'blackPoint': 0, 'whitePoint': 255, 'gamma': 1.0,
            'temperature': 0, 'tint': 0,
            'curves': {
                'rgb': [[0, 0], [0.25, 0.55], [1, 1]],
                'r': [[0, 0], [1, 1]],
                'g': [[0, 0], [1, 1]],
                'b': [[0, 0], [1, 1]],
            },
        }))
        self.assertFalse(is_identity(payload['curves']))

        img = np.full((2, 2, 3), 64, dtype=np.uint8)
        out = adv_color(
            img,
            black_point=payload['blackPoint'],
            white_point=payload['whitePoint'],
            gamma=payload['gamma'],
            temperature=payload['temperature'],
            tint=payload['tint'],
            curves=payload['curves'],
        )
        # 64/255 ≈ 0.251 → 커브가 0.55 근처로 올린다
        self.assertGreater(int(out[0, 0, 0]), 130)

    def test_adv_color_without_curves_is_unchanged(self):
        """커브 인자를 안 주면 예전 동작 그대로여야 한다."""
        from core.editor_ops import adv_color

        img = np.random.randint(0, 256, (4, 4, 3), dtype=np.uint8)
        self.assertTrue(np.array_equal(
            adv_color(img, black_point=20, white_point=200, gamma=1.4),
            adv_color(img, black_point=20, white_point=200, gamma=1.4, curves=None),
        ))


if __name__ == "__main__":
    unittest.main()

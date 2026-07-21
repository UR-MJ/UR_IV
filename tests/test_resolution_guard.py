"""ANIMA 해상도 가드 테스트 — 고해상도 모드에서 1536² 면적캡이 도는지.
(이번에 고친 '고해상도인데 2048×2048로 나가던' 버그의 회귀 방지)"""
import unittest
from core.resolution_guard import (
    ANIMA_MAX_AREA,
    apply_anima_resolution,
    normalize_anima_guard_prefs,
)


class TestAnimaResolution(unittest.TestCase):
    def test_highres_2x_square_capped(self):
        # 사용자 버그: 1024×1024 × 2.0 → 1536×1536 으로 캡되어야 함
        self.assertEqual(apply_anima_resolution(1024, 1024, 2.0, auto_res=False), (1536, 1536))

    def test_highres_15x_square_capped(self):
        self.assertEqual(apply_anima_resolution(1024, 1024, 1.5, auto_res=False), (1536, 1536))

    def test_under_cap_unchanged(self):
        # 768×768 × 1.5 = 1152×1152 (한도 이하 → 그대로)
        self.assertEqual(apply_anima_resolution(768, 768, 1.5, auto_res=False), (1152, 1152))

    def test_manual_large_without_highres_not_capped(self):
        # 고해상도 OFF(=1.0) + 수동 큰 해상도 → 사용자 의도 존중(캡 X)
        self.assertEqual(apply_anima_resolution(2048, 2048, 1.0, auto_res=False), (2048, 2048))

    def test_ratio_preserved_within_area(self):
        w, h = apply_anima_resolution(832, 1216, 1.5, auto_res=False)
        self.assertEqual((w, h), (1248, 1824))
        self.assertLessEqual(w * h, ANIMA_MAX_AREA)

    def test_area_never_exceeds_in_highres(self):
        for bw, bh, f in [(1024, 1024, 2.0), (1216, 832, 1.8), (1536, 1536, 1.5), (1024, 1536, 2.0)]:
            w, h = apply_anima_resolution(bw, bh, f, auto_res=False)
            self.assertLessEqual(w * h, ANIMA_MAX_AREA, f"{bw}x{bh} x{f} → {w}x{h}")

    def test_outputs_multiple_of_8(self):
        for bw, bh, f in [(1000, 1000, 1.5), (833, 1211, 1.7)]:
            w, h = apply_anima_resolution(bw, bh, f)
            self.assertEqual(w % 8, 0)
            self.assertEqual(h % 8, 0)

    def test_side_cap_preserves_ratio(self):
        # 한 변(3000)이 max_side(2048) 초과, 면적은 한도 이내 → 비율 유지하며 양쪽 축소
        w, h = apply_anima_resolution(3000, 500, auto_res=True)
        self.assertLessEqual(max(w, h), 2048)
        self.assertAlmostEqual(w / h, 6.0, delta=0.3)   # 6:1 비율 유지
        self.assertEqual(w % 8, 0)
        self.assertEqual(h % 8, 0)

    def test_side_2048_within_area_kept(self):
        # 1024×2048 (긴 변 2048, 면적 2.1M < 캡) → 그대로 (실측 안전 케이스)
        self.assertEqual(apply_anima_resolution(1024, 2048, auto_res=True), (1024, 2048))

    def test_big_square_auto_capped_to_1536(self):
        # 2048×2048 자동해상도 → 면적캡으로 1536×1536
        self.assertEqual(apply_anima_resolution(2048, 2048, auto_res=True), (1536, 1536))

    def test_custom_area_limit(self):
        self.assertEqual(
            apply_anima_resolution(2048, 2048, auto_res=True,
                                   max_area=1024 * 1024),
            (1024, 1024),
        )

    def test_custom_side_limit(self):
        w, h = apply_anima_resolution(
            3000, 500, auto_res=True, max_area=4096 * 4096, max_side=1024)
        self.assertLessEqual(max(w, h), 1024)
        self.assertAlmostEqual(w / h, 6.0, delta=0.3)

    def test_disabled_guard_keeps_highres_scaling_without_cap(self):
        self.assertEqual(
            apply_anima_resolution(1536, 1536, 2.0, enabled=False),
            (3072, 3072),
        )

    def test_guard_prefs_are_normalized(self):
        self.assertEqual(normalize_anima_guard_prefs({
            'animaGuardEnabled': 'false',
            'animaGuardMaxAreaSide': 1501,
            'animaGuardMaxSide': 99999,
        }), {
            'animaGuardEnabled': False,
            'animaGuardMaxAreaSide': 1496,
            'animaGuardMaxSide': 8192,
        })


if __name__ == "__main__":
    unittest.main()

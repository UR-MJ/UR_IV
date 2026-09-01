"""캐릭터 특징 분류 테스트 — 핵심(색+신체) / 보조(목록) / 기타(목록 밖) 구분.
(외견 4분류 기능의 회귀 방지)"""
import unittest
from utils.character_features import (
    is_core_appearance_tag, is_aux_feature_tag,
    is_hair_color_tag, is_eye_color_tag,
)


class TestCoreClassifier(unittest.TestCase):
    def test_hair_color_is_core(self):
        for t in ["blue hair", "blonde hair", "white hair", "multicolored hair"]:
            self.assertTrue(is_core_appearance_tag(t), t)

    def test_eye_color_is_core(self):
        for t in ["purple eyes", "yellow eyes", "heterochromia"]:
            self.assertTrue(is_core_appearance_tag(t), t)

    def test_physical_features_are_core(self):
        for t in ["pointy ears", "goat horns", "elf", "cat tail",
                  "cross-shaped pupils", "sharp teeth", "dark skin"]:
            self.assertTrue(is_core_appearance_tag(t), t)

    def test_hairstyle_and_body_not_core(self):
        for t in ["long hair", "twintails", "ahoge", "large breasts", "hair between eyes"]:
            self.assertFalse(is_core_appearance_tag(t), t)

    def test_pose_expression_not_core(self):
        for t in ["standing", "smile", "holding", "bishounen", "hand up"]:
            self.assertFalse(is_core_appearance_tag(t), t)


class TestAuxClassifier(unittest.TestCase):
    def test_listed_appearance_is_aux(self):
        # 수동 선별 외형 목록에 있는 특성 → 보조
        for t in ["ahoge", "twintails", "long hair"]:
            self.assertTrue(is_aux_feature_tag(t), t)

    def test_pose_not_aux(self):
        # 목록 밖(포즈/표정/동작) → 기타 (보조 아님)
        for t in ["standing", "smile", "holding", "bishounen"]:
            self.assertFalse(is_aux_feature_tag(t), t)


class TestColorHelpers(unittest.TestCase):
    def test_hair_length_is_not_color(self):
        self.assertFalse(is_hair_color_tag("long hair"))
        self.assertTrue(is_hair_color_tag("blue hair"))

    def test_eye_state_is_not_color(self):
        self.assertFalse(is_eye_color_tag("closed eyes"))
        self.assertTrue(is_eye_color_tag("red eyes"))


if __name__ == "__main__":
    unittest.main()

"""LoRA 스택 → 생성 텍스트 변환 테스트.
(단일 소스 통합: 시작 시 ui_prefs.loraStack에서 _vue_lora_text 복원이 App.vue 포맷과 일치하는지)"""
import unittest
from core.lora_stack import build_lora_text


class TestBuildLoraText(unittest.TestCase):
    def test_basic_format_weight_percent_to_decimal(self):
        # weight는 정수%로 저장 → /100, 소수 2자리 (App.vue doGenerate와 동일)
        out = build_lora_text([{"name": "styleA", "weight": 80, "enabled": True}])
        self.assertEqual(out, "<lora:styleA:0.80>")

    def test_multiple_joined_by_comma(self):
        out = build_lora_text([
            {"name": "a", "weight": 100, "enabled": True},
            {"name": "b", "weight": 65, "enabled": True},
        ])
        self.assertEqual(out, "<lora:a:1.00>, <lora:b:0.65>")

    def test_disabled_excluded(self):
        out = build_lora_text([
            {"name": "a", "weight": 100, "enabled": False},
            {"name": "b", "weight": 50, "enabled": True},
        ])
        self.assertEqual(out, "<lora:b:0.50>")

    def test_missing_name_skipped(self):
        out = build_lora_text([{"name": "", "weight": 100, "enabled": True}])
        self.assertEqual(out, "")

    def test_enabled_defaults_true(self):
        # enabled 키 없으면 활성으로 간주
        out = build_lora_text([{"name": "a", "weight": 90}])
        self.assertEqual(out, "<lora:a:0.90>")

    def test_empty_and_garbage_inputs(self):
        self.assertEqual(build_lora_text([]), "")
        self.assertEqual(build_lora_text(None), "")
        self.assertEqual(build_lora_text(["not a dict", 5]), "")

    def test_bad_weight_falls_back(self):
        out = build_lora_text([{"name": "a", "weight": "xx", "enabled": True}])
        self.assertEqual(out, "<lora:a:1.00>")


if __name__ == "__main__":
    unittest.main()

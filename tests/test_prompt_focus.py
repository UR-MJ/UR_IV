"""프롬프트 토큰 집중(광범위 태그 제거) 테스트."""
import unittest
from core.prompt_focus import focus_tags, focus_prompt


class TestPromptFocus(unittest.TestCase):
    def test_user_example(self):
        # 사용자 명시 예: muscular ⊂ muscular male, dress ⊂ blue/frill dress 제거
        inp = ["muscular", "muscular male", "blue dress", "dress", "frill dress"]
        self.assertEqual(focus_tags(inp), ["muscular male", "blue dress", "frill dress"])

    def test_prompt_string(self):
        s = "muscular, muscular male, blue dress, dress, frill dress"
        self.assertEqual(focus_prompt(s), "muscular male, blue dress, frill dress")

    def test_unrelated_kept(self):
        # 서로 포함관계 아닌 태그는 모두 유지
        inp = ["blue eyes", "blue hair", "smile", "open mouth"]
        self.assertEqual(focus_tags(inp), inp)

    def test_underscore_normalized(self):
        # 언더스코어 형식도 동일하게 인식 (long_hair ⊂ very_long_hair)
        inp = ["long_hair", "very_long_hair"]
        self.assertEqual(focus_tags(inp), ["very_long_hair"])

    def test_exact_duplicate_removed(self):
        inp = ["1girl", "solo", "1girl"]
        self.assertEqual(focus_tags(inp), ["1girl", "solo"])

    def test_single_word_substring_not_removed(self):
        # 단어 자체가 다르면(부분문자열일 뿐) 제거 안 함: cat ⊄ cats
        inp = ["cat", "cats"]
        self.assertEqual(focus_tags(inp), ["cat", "cats"])

    def test_order_preserved(self):
        inp = ["frill dress", "dress", "blue dress"]
        self.assertEqual(focus_tags(inp), ["frill dress", "blue dress"])

    def test_empty_passthrough(self):
        self.assertEqual(focus_prompt(""), "")
        self.assertEqual(focus_prompt("   "), "   ")

    def test_lora_and_weight_preserved(self):
        # <lora:..>, (tag:1.2) 는 단어집합이 달라 보존
        s = "<lora:foo:0.8>, muscular, muscular male, (blush:1.1)"
        out = focus_prompt(s)
        self.assertIn("<lora:foo:0.8>", out)
        self.assertIn("(blush:1.1)", out)
        self.assertIn("muscular male", out)
        self.assertNotIn(", muscular,", ", " + out + ",")  # 단독 muscular 제거됨


if __name__ == "__main__":
    unittest.main()

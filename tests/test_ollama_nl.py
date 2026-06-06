"""자연어 캡션 누출 제거 테스트 — 추론/체크리스트/메타 문장을 떼고 캡션만 남기는지.
(작은 GGUF/채팅 모델이 사고과정을 뱉던 문제의 회귀 방지)"""
import unittest
from core.ollama_client import _extract_final_nl, _enforce_nl_style, _is_meta_sentence


class TestNLLeakRemoval(unittest.TestCase):
    def test_revised_again_marker(self):
        t = ("Let's check for commas... none. Capital start? Yes. Revised again: "
             "A man with short black hair stands tall. He holds a sword.")
        out = _extract_final_nl(t)
        self.assertTrue(out.startswith("A man with short black hair"))
        self.assertNotIn("Revised", out)
        self.assertNotIn("Capital start", out)

    def test_naming_meta_stripped(self):
        t = ("Since there is no name in the input I will refer to him as the man. "
             "A man with black hair stands in a field.")
        out = _extract_final_nl(t)
        self.assertFalse(out.lower().startswith("since"))
        self.assertIn("A man with black hair", out)

    def test_ill_focus_as_requested_stripped(self):
        t = "I'll focus on the primary subject as requested. A woman with red hair smiles softly."
        out = _extract_final_nl(t)
        self.assertTrue(out.startswith("A woman with red hair"))

    def test_clean_caption_passthrough(self):
        t = "A knight in golden armor kneels before a throne. Banners hang from the stone walls."
        self.assertEqual(_extract_final_nl(t), t)

    def test_legit_no_sentence_preserved(self):
        # 'No background is visible' 는 정상 묘사 문장 — 메타로 오인해 지우면 안 됨
        t = "A girl with blue hair stands alone. No background is visible."
        out = _extract_final_nl(t)
        self.assertIn("No background is visible", out)

    def test_enforce_style_removes_commas_and_formats(self):
        out = _enforce_nl_style("a man, tall, holding a sword")
        self.assertNotIn(",", out)
        self.assertTrue(out[0].isupper())
        self.assertTrue(out.endswith("."))

    def test_meta_sentence_detection(self):
        self.assertTrue(_is_meta_sentence("Let's check for commas."))
        self.assertTrue(_is_meta_sentence("I'll focus on the subject."))
        self.assertTrue(_is_meta_sentence("Revised again: the scene."))
        # 진짜 캡션 문장은 메타 아님
        self.assertFalse(_is_meta_sentence("A man with black hair stands tall."))
        self.assertFalse(_is_meta_sentence("No shoes are visible."))
        self.assertFalse(_is_meta_sentence("Illuminated by moonlight a castle rises."))


if __name__ == "__main__":
    unittest.main()

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

    def test_full_scratchpad_leak_revised_draft(self):
        # 모델이 Input tags/Task/Constraint 불릿 + 초안 + *Revised draft:* + *Checking* + 태그리스트를
        # 통째로 뱉는 심한 누출 — *Revised draft:* 뒤 ~ 첫 '*'(Checking) 사이의 최종 캡션만 남겨야.
        t = ("Input tags: 1girl solo blue hair smile. "
             "* Task: Rewrite as a flowing English caption. "
             "* Character/Series: No specific name provided. I will refer to her as \"a girl\". "
             "* Constraint (a): Name character explicitly. * Constraint (c): NO commas. "
             "A girl with blue hair smiles brightly. "
             "* No commas? Checked. Wait the prompt asks to name the character. "
             "*Revised draft:* A girl with blue hair stands in a bright room. "
             "She smiles warmly at the viewer. "
             "*Checking for commas:* \"A girl with blue hair stands in a bright room.\" (No comma) "
             "*Wait let me double check the tags:* blue hair - included. smile - included.")
        out = _extract_final_nl(t)
        self.assertIn("A girl with blue hair stands in a bright room", out)
        self.assertIn("She smiles warmly at the viewer", out)
        self.assertNotIn("Task", out)
        self.assertNotIn("Constraint", out)
        self.assertNotIn("Revised", out)
        self.assertNotIn("Checking", out)
        self.assertNotIn("included", out)
        self.assertNotIn("*", out)
        self.assertNotIn("Input tags", out)

    def test_decomposition_multi_draft_leak(self):
        # Goal:/* Subject:/* Hair colors:/*Refining the Scene:*/*Draft:*/*Constraint Check:* 구조 —
        # 마지막 *Draft:* 뒤 ~ 첫 '*'(Constraint Check) 사이의 최종 캡션만 남겨야.
        t = ("Goal: Rewrite into a flowing English caption. "
             "* Constraints: 1. Name character. *Correction*: Wait if no name how do I name them. "
             "* Subject: A male character. * Hair colors: black white green. "
             "Wait the tags are contradictory. "
             "*Refining the Scene:* A man stands before a cloudy sky. He has many scars. "
             "*Check Constraints:* No commas? Yes. *Wait* let me look at the hair again. "
             "*Draft:* A man with multi-colored hair stands before a cloudy sky. "
             "He has visible scars across his eye. The man is seen from behind with crossed arms. "
             "*Constraint Check:* No commas. Separate sentences.")
        out = _extract_final_nl(t)
        self.assertIn("A man with multi-colored hair stands before a cloudy sky", out)
        self.assertIn("crossed arms", out)
        for bad in ("Goal", "Subject", "Refining", "Draft", "Constraint", "Wait", "*"):
            self.assertNotIn(bad, out)

    def test_bullet_label_meta_sentence_detection(self):
        # 불릿/라벨 문장은 메타로 인식 (선두/후미 제거용)
        self.assertTrue(_is_meta_sentence("* Task: Rewrite the caption."))
        self.assertTrue(_is_meta_sentence("* Constraint (a): Name character."))
        self.assertTrue(_is_meta_sentence("Input tags: blue hair smile."))
        self.assertTrue(_is_meta_sentence("* Setting: a bright room."))
        # 캡션 문장은 그대로
        self.assertFalse(_is_meta_sentence("A girl with blue hair stands in a bright room."))

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

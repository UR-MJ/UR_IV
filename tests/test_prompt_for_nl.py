"""core/prompt_for_nl.clean_tags_for_nl — nl_caption LLM 입력 정리 테스트."""
import unittest
from core.prompt_for_nl import clean_tags_for_nl


class TestCleanTagsForNl(unittest.TestCase):
    def _tags(self, s):
        return [t.strip() for t in clean_tags_for_nl(s).split(',') if t.strip()]

    def test_removes_negative_weight_group_with_inner_commas(self):
        s = "1girl, (lips, tareme, very big eyes, censored:-1.1), blue hair"
        out = self._tags(s)
        self.assertIn('1girl', out)
        self.assertIn('blue hair', out)
        for bad in ('lips', 'tareme', 'very big eyes', 'censored'):
            self.assertNotIn(bad, out)

    def test_removes_quality_score_year_meta(self):
        s = ("masterpiece, best quality, score_9, score_8_up, highres, absurdres, "
             "newest, year2025, 1boy, brown hair")
        out = self._tags(s)
        self.assertEqual(out, ['1boy', 'brown hair'])

    def test_removes_lora_and_at_triggers(self):
        s = "1girl, @enast, @o6nine, <lora:ANIMAV10:0.9>, school uniform"
        out = self._tags(s)
        self.assertEqual(out, ['1girl', 'school uniform'])

    def test_keeps_character_series_parens(self):
        # 'alex (stardew valley)' 의 괄호는 weight가 아니므로 보존
        s = "1boy, alex (stardew valley), stardew valley, muscular male"
        out = self._tags(s)
        self.assertIn('alex (stardew valley)', out)
        self.assertIn('stardew valley', out)
        self.assertIn('muscular male', out)

    def test_unwraps_positive_weight(self):
        self.assertEqual(self._tags("(detailed face:1.3), 1girl"), ['detailed face', '1girl'])

    def test_keeps_escaped_parens_tag(self):
        s = "1boy, solo, i've never seen this tbh \\(meme\\), bulge"
        out = self._tags(s)
        self.assertIn("i've never seen this tbh \\(meme\\)", out)
        self.assertIn('bulge', out)

    def test_full_realistic_prompt(self):
        s = ("masterpiece, best quality, score_9, score_8, score_7, highres, absurdres, "
             "newest, year2025, 1boy, alex (stardew valley), stardew valley, @enast, @o6nine, "
             "(eyelashes, skinny, slim arms, simple background:-1.0), "
             "(lips, tareme, censored:-1.1), brown hair, muscular male, bulge, large pectorals, solo")
        out = self._tags(s)
        # 유지: 인물수/캐릭터/작품/메인
        for keep in ('1boy', 'alex (stardew valley)', 'stardew valley', 'brown hair',
                     'muscular male', 'bulge', 'large pectorals', 'solo'):
            self.assertIn(keep, out)
        # 제거: 품질/score/year/lora트리거/네거티브
        for bad in ('masterpiece', 'score_9', 'highres', 'newest', 'year2025',
                    '@enast', '@o6nine', 'eyelashes', 'skinny', 'lips', 'censored'):
            self.assertNotIn(bad, out)

    def test_nested_negative_weight_leaves_no_stray_parens(self):
        # ((tag:-1.2)) — 안쪽 제거 후 바깥 빈 괄호가 남던 버그 회귀 방지
        s = "1girl, ((bad hands, extra fingers:-1.2)), blue hair"
        out = self._tags(s)
        self.assertEqual(out, ['1girl', 'blue hair'])
        self.assertNotIn('(', clean_tags_for_nl(s))  # 이 입력엔 캐릭터 괄호 없음 → 괄호 0
        self.assertNotIn(')', clean_tags_for_nl(s))

    def test_nested_does_not_break_character_parens(self):
        # 중첩 네거티브 정리가 정상 캐릭터 괄호를 깨면 안 됨
        s = "1boy, alex (stardew valley), ((censored:-1.1)), brown hair"
        out = self._tags(s)
        self.assertIn('alex (stardew valley)', out)
        self.assertNotIn('censored', out)

    def test_empty(self):
        self.assertEqual(clean_tags_for_nl(''), '')
        self.assertEqual(clean_tags_for_nl(None), '')


if __name__ == '__main__':
    unittest.main()

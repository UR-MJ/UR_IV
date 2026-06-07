"""조건부 v2 — 다중조건(AND) + after_condition 삽입 순수 로직 회귀."""
import unittest
from utils.condition_block import norm_tag, multi_cond_met, insert_after


class TestMultiCondMet(unittest.TestCase):
    def test_single(self):
        self.assertTrue(multi_cond_met("fiery horns", {"fiery horns"}, True))
        self.assertFalse(multi_cond_met("fiery horns", {"other"}, True))

    def test_and_all_present(self):
        tags = {"tamamura gunzo", "fiery horns", "1boy"}
        self.assertTrue(multi_cond_met("tamamura gunzo, fiery horns", tags, True))

    def test_and_one_missing(self):
        tags = {"tamamura gunzo", "1boy"}
        self.assertFalse(multi_cond_met("tamamura gunzo, fiery horns", tags, True))

    def test_underscore_input_normalized(self):
        # 입력이 언더스코어여도 정규화돼 매칭
        self.assertTrue(multi_cond_met("tamamura_gunzo", {"tamamura gunzo"}, True))

    def test_not_exists(self):
        # exists=False → AND 조건이 충족 안 될 때 True
        self.assertTrue(multi_cond_met("x, y", {"x"}, False))        # 하나 빠짐
        self.assertFalse(multi_cond_met("x, y", {"x", "y"}, False))  # 다 있음

    def test_empty_condition(self):
        self.assertFalse(multi_cond_met("", {"a"}, True))


class TestInsertAfter(unittest.TestCase):
    def test_insert_after_anchor(self):
        tags = ["tamamura gunzo", "1boy", "fiery horns"]
        out = insert_after(tags, "tamamura gunzo", "wakan tanka")
        self.assertEqual(out, ["tamamura gunzo", "wakan tanka", "1boy", "fiery horns"])

    def test_already_present_no_change(self):
        tags = ["tamamura gunzo", "wakan tanka"]
        self.assertEqual(insert_after(tags, "tamamura gunzo", "wakan tanka"), tags)

    def test_anchor_missing_returns_none(self):
        self.assertIsNone(insert_after(["1boy", "smile"], "tamamura gunzo", "wakan tanka"))

    def test_underscore_data_matches(self):
        # 데이터 태그가 언더스코어여도 anchor(공백 정규화)와 매칭
        tags = ["tamamura_gunzo", "1boy"]
        out = insert_after(tags, "tamamura gunzo", "wakan tanka")
        self.assertEqual(out, ["tamamura_gunzo", "wakan tanka", "1boy"])

    def test_norm_tag(self):
        self.assertEqual(norm_tag(" Tamamura_Gunzo "), "tamamura gunzo")


if __name__ == "__main__":
    unittest.main()

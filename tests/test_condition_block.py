"""조건식(조건부 프롬프트) 테스트 — IF 조건 → add/remove/replace.
(자동화에서 조건식이 안 먹던 버그의 회귀 방지)"""
import unittest
from utils.condition_block import apply_rules, ConditionRule


def _rule(cond, tags, action="add", location="main", exists=True, enabled=True):
    return ConditionRule(
        condition_tag=cond, condition_exists=exists,
        target_tags=tags if isinstance(tags, list) else [tags],
        location=location, action=action, enabled=enabled,
    )


class TestConditionRules(unittest.TestCase):
    def test_remove_when_condition_present(self):
        # IF bishounen 있으면 → bishounen 제거 (본문)
        r = _rule("bishounen", ["bishounen"], action="remove")
        res = apply_rules([r], {"bishounen", "1boy", "blue eyes"})
        self.assertIn("bishounen", res["_remove_main"])

    def test_no_remove_when_condition_absent(self):
        r = _rule("bishounen", ["bishounen"], action="remove")
        res = apply_rules([r], {"1girl", "blue eyes"})  # bishounen 없음 → 발동 안 함
        self.assertEqual(res["_remove_main"], [])

    def test_add_when_condition_present(self):
        r = _rule("cat ears", ["animal ear fluff"], action="add")
        res = apply_rules([r], {"cat ears"})
        self.assertIn("animal ear fluff", res["main"])

    def test_exists_false_triggers_when_absent(self):
        # '없으면' → 발동
        r = _rule("hat", ["bare head"], action="add", exists=False)
        res = apply_rules([r], {"1girl"})  # hat 없음 → 발동
        self.assertIn("bare head", res["main"])

    def test_exists_false_no_trigger_when_present(self):
        r = _rule("hat", ["bare head"], action="add", exists=False)
        res = apply_rules([r], {"hat", "1girl"})  # hat 있음 → 발동 안 함
        self.assertEqual(res["main"], [])

    def test_disabled_rule_ignored(self):
        r = _rule("bishounen", ["bishounen"], action="remove", enabled=False)
        res = apply_rules([r], {"bishounen"})
        self.assertEqual(res["_remove_main"], [])


if __name__ == "__main__":
    unittest.main()

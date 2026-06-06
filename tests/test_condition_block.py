"""조건식(조건부 프롬프트) 테스트 — IF 조건 → add/remove/replace.
(자동화에서 조건식이 안 먹던 버그의 회귀 방지)"""
import json
import unittest
from utils.condition_block import (
    apply_rules, ConditionRule, rules_to_json, legacy_cond_rules_to_vue,
)


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


class TestLegacyCondMigration(unittest.TestCase):
    """단일 소스 통합: 옛 prompt_settings.cond_rules_json → Vue cond_rules.json 변환 회귀."""

    def test_pos_rule_tags_list_to_target_string(self):
        # 레거시 저장 포맷(tags=리스트) → Vue 포맷(target=콤마 문자열)
        legacy = rules_to_json([_rule("cat ears", ["animal ear fluff", "tail"], action="add")])
        vue = legacy_cond_rules_to_vue(legacy)
        self.assertEqual(len(vue["positive"]), 1)
        self.assertEqual(vue["negative"], [])
        rule = vue["positive"][0]
        self.assertEqual(rule["condition"], "cat ears")
        self.assertEqual(rule["target"], "animal ear fluff, tail")
        self.assertEqual(rule["action"], "add")
        self.assertEqual(rule["location"], "main")
        self.assertTrue(rule["exists"])
        self.assertTrue(vue["enabled"])

    def test_neg_location_goes_to_negative_bucket(self):
        legacy = rules_to_json([_rule("nsfw", ["rating: explicit"], location="neg")])
        vue = legacy_cond_rules_to_vue(legacy)
        self.assertEqual(vue["positive"], [])
        self.assertEqual(len(vue["negative"]), 1)
        self.assertEqual(vue["negative"][0]["target"], "rating: explicit")

    def test_after_condition_normalized_to_main(self):
        legacy = rules_to_json([_rule("x", ["y"], location="after_condition")])
        vue = legacy_cond_rules_to_vue(legacy)
        self.assertEqual(vue["positive"][0]["location"], "main")

    def test_remove_action_preserved(self):
        legacy = rules_to_json([_rule("bishounen", ["bishounen"], action="remove")])
        vue = legacy_cond_rules_to_vue(legacy)
        self.assertEqual(vue["positive"][0]["action"], "remove")

    def test_empty_or_invalid_yields_empty_buckets(self):
        self.assertEqual(legacy_cond_rules_to_vue("")["positive"], [])
        self.assertEqual(legacy_cond_rules_to_vue("not json")["negative"], [])
        # 조건/대상 비면 스킵
        legacy = json.dumps([{"condition": "", "tags": ["a"]}, {"condition": "c", "tags": []}])
        vue = legacy_cond_rules_to_vue(legacy)
        self.assertEqual(vue["positive"], [])

    def test_migrated_rules_apply_correctly(self):
        # 마이그레이션 결과가 실제 적용(apply_rules)에서도 동작하는지 왕복 검증
        legacy = rules_to_json([_rule("bishounen", ["bishounen"], action="remove")])
        vue = legacy_cond_rules_to_vue(legacy)
        # Vue 포맷 → ConditionRule 재구성 후 적용
        back = [ConditionRule.from_dict({
            "condition": r["condition"], "exists": r["exists"],
            "tags": [t.strip() for t in r["target"].split(",")],
            "location": r["location"], "action": r["action"], "enabled": r["enabled"],
        }) for r in vue["positive"]]
        res = apply_rules(back, {"bishounen", "1boy"})
        self.assertIn("bishounen", res["_remove_main"])


if __name__ == "__main__":
    unittest.main()

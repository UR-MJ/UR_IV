# utils/condition_block.py
"""
블록 기반 조건부 프롬프트 — 데이터 모델 + 적용 로직
"""
import json
import random
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class ConditionRule:
    """조건부 프롬프트 규칙 하나"""
    condition_tag: str = ""          # 조건 태그
    condition_exists: bool = True    # True=있다, False=없다
    target_tags: List[str] = field(default_factory=list)  # 대상 태그들
    location: str = "main"           # main/prefix/suffix/neg/after_condition/random
    action: str = "add"              # add/remove/replace
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "condition": self.condition_tag,
            "exists": self.condition_exists,
            "tags": self.target_tags,
            "location": self.location,
            "action": self.action,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConditionRule":
        return cls(
            condition_tag=d.get("condition", ""),
            condition_exists=d.get("exists", True),
            target_tags=d.get("tags", []),
            location=d.get("location", "main"),
            action=d.get("action", "add"),
            enabled=d.get("enabled", True),
        )


def rules_to_json(rules: List[ConditionRule]) -> str:
    """규칙 리스트 → JSON 문자열"""
    return json.dumps([r.to_dict() for r in rules], ensure_ascii=False, indent=2)


def rules_from_json(text: str) -> List[ConditionRule]:
    """JSON 문자열 → 규칙 리스트"""
    if not text or not text.strip():
        return []
    try:
        data = json.loads(text)
        return [ConditionRule.from_dict(d) for d in data]
    except (json.JSONDecodeError, TypeError):
        return []


def migrate_old_rules(text: str) -> List[ConditionRule]:
    """기존 텍스트 문법 → ConditionRule 리스트로 변환
    기존 형식: (condition):/location+=tags  또는  (condition)+=neg_tags
    """
    rules: List[ConditionRule] = []
    if not text or not text.strip():
        return rules

    # 이미 JSON이면 그대로 파싱
    stripped = text.strip()
    if stripped.startswith("["):
        return rules_from_json(text)

    location_map = {
        "/main": "main", "/m": "main",
        "/prefix": "prefix", "/p": "prefix",
        "/suffix": "suffix", "/s": "suffix",
        "/neg": "neg", "/n": "neg", "/negative": "neg",
    }

    # 일반 규칙: (condition):/location+=tags
    rule_re = re.compile(r'\(([^)]+)\)\s*:\s*(/\w+)\s*\+\s*=\s*(.+)')
    # 네거티브 규칙: (condition)+=tags
    neg_re = re.compile(r'\(([^)]+)\)\s*\+\s*=\s*(.+)')

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = rule_re.match(line)
        if m:
            condition = m.group(1).strip()
            loc_raw = m.group(2).strip().lower()
            tags_str = m.group(3).strip()
            location = location_map.get(loc_raw, "main")
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            rules.append(ConditionRule(
                condition_tag=condition,
                condition_exists=True,
                target_tags=tags,
                location=location,
                action="add",
            ))
            continue

        m = neg_re.match(line)
        if m:
            condition = m.group(1).strip()
            tags_str = m.group(2).strip()
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            rules.append(ConditionRule(
                condition_tag=condition,
                condition_exists=True,
                target_tags=tags,
                location="neg",
                action="add",
            ))

    return rules


def apply_rules(
    rules: List[ConditionRule],
    all_tags: set[str],
    current_by_location: dict[str, list[str]] | None = None,
    prevent_dupe: bool = True,
) -> dict[str, list[str]]:
    """규칙 적용.
    Args:
        rules: 적용할 규칙 리스트
        all_tags: 현재 프롬프트의 모든 태그 (정규화, lowercase)
        current_by_location: 위치별 현재 태그 리스트 (remove/replace용)
        prevent_dupe: 중복 방지
    Returns:
        {location: [추가/제거할 태그들]}
        action=add → 해당 위치에 추가
        action=remove → result["_remove_{location}"] 에 제거할 태그
        action=replace → result["_replace"] 에 (old, new) 튜플
    """
    result: dict[str, list] = {
        "main": [], "prefix": [], "suffix": [], "neg": [],
        "_remove_main": [], "_remove_prefix": [], "_remove_suffix": [], "_remove_neg": [],
        "_replace": [],
    }
    added_tags: set[str] = set()

    for rule in rules:
        if not rule.enabled or not rule.condition_tag or not rule.target_tags:
            continue

        cond_norm = rule.condition_tag.strip().lower().replace("_", " ")
        cond_matched = cond_norm in all_tags

        # 조건 확인
        if rule.condition_exists and not cond_matched:
            continue
        if not rule.condition_exists and cond_matched:
            continue

        # 동작 실행
        if rule.action == "add":
            location = rule.location
            if location == "after_condition":
                location = "main"  # 추후 위치 세부 처리
            elif location == "random":
                location = "main"  # 랜덤 삽입은 main에 추가 후 셔플

            for tag in rule.target_tags:
                tag_norm = tag.strip().lower().replace("_", " ")
                if prevent_dupe and (tag_norm in all_tags or tag_norm in added_tags):
                    continue
                result[location].append(tag)
                added_tags.add(tag_norm)

        elif rule.action == "remove":
            loc = rule.location
            if loc in ("after_condition", "random"):
                loc = "main"
            for tag in rule.target_tags:
                result[f"_remove_{loc}"].append(tag)

        elif rule.action == "replace":
            # 조건 태그를 대상 태그로 교체
            for tag in rule.target_tags:
                result["_replace"].append((rule.condition_tag, tag))

    return result

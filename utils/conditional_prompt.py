# utils/conditional_prompt.py
"""조건부 프롬프트 규칙 파서 및 적용"""
import re

# 위치 별칭 매핑
_LOCATION_MAP = {
    "/main": "main", "/m": "main",
    "/prefix": "prefix", "/p": "prefix",
    "/suffix": "suffix", "/s": "suffix",
    "/neg": "neg", "/n": "neg",
    "/negative": "neg",
}

# 규칙 파싱 정규식: (조건):/위치+=태그들
_RULE_RE = re.compile(
    r'\(([^)]+)\)\s*:\s*(/\w+)\s*\+\s*=\s*(.+)'
)

# 네거티브 전용: (조건)+=태그들
_NEG_RULE_RE = re.compile(
    r'\(([^)]+)\)\s*\+\s*=\s*(.+)'
)


def parse_rules(text: str) -> list[tuple[str, str, list[str]]]:
    """조건부 규칙 파싱.
    Returns: [(condition, location, [tag1, tag2, ...]), ...]
    """
    rules = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = _RULE_RE.match(line)
        if m:
            condition = m.group(1).strip().lower().replace("_", " ")
            location_raw = m.group(2).strip().lower()
            location = _LOCATION_MAP.get(location_raw, "main")
            tags = [t.strip() for t in m.group(3).split(",") if t.strip()]
            if condition and tags:
                rules.append((condition, location, tags))
    return rules


def parse_neg_rules(text: str) -> list[tuple[str, list[str]]]:
    """조건부 네거티브 규칙 파싱.
    Returns: [(condition, [tag1, tag2, ...]), ...]
    """
    rules = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = _NEG_RULE_RE.match(line)
        if m:
            condition = m.group(1).strip().lower().replace("_", " ")
            tags = [t.strip() for t in m.group(2).split(",") if t.strip()]
            if condition and tags:
                rules.append((condition, tags))
    return rules


def apply_conditional_rules(
    rules: list[tuple[str, str, list[str]]],
    all_tags: set[str],
    prevent_dupe: bool = True,
    existing_by_location: dict[str, set[str]] | None = None,
) -> dict[str, list[str]]:
    """조건부 규칙 적용.
    Args:
        rules: parse_rules() 결과
        all_tags: 현재 전체 태그 (정규화됨, 조건 매칭용)
        prevent_dupe: 중복 태그 방지
        existing_by_location: {location: set(정규화된 기존 태그)}
    Returns: {location: [추가할 태그들]}
    """
    if existing_by_location is None:
        existing_by_location = {}

    result: dict[str, list[str]] = {}

    for condition, location, tags in rules:
        # 조건 매칭: all_tags에 condition이 포함되어 있는지
        if condition not in all_tags:
            continue

        if location not in result:
            result[location] = []

        existing = existing_by_location.get(location, set())
        for tag in tags:
            norm = tag.strip().lower().replace("_", " ")
            if prevent_dupe and (norm in all_tags or norm in existing):
                continue
            result[location].append(tag)
            existing.add(norm)

    return result


def apply_neg_rules(
    rules: list[tuple[str, list[str]]],
    all_tags: set[str],
    existing_neg: set[str] | None = None,
    prevent_dupe: bool = True,
) -> list[str]:
    """조건부 네거티브 규칙 적용.
    Returns: [추가할 네거티브 태그들]
    """
    if existing_neg is None:
        existing_neg = set()

    result: list[str] = []
    for condition, tags in rules:
        if condition not in all_tags:
            continue
        for tag in tags:
            norm = tag.strip().lower().replace("_", " ")
            if prevent_dupe and norm in existing_neg:
                continue
            result.append(tag)
            existing_neg.add(norm)

    return result

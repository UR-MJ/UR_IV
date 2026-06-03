"""
Search Operators — 멀티 그룹 검색 연산자 파서 + 평가기.

NAIA 1.5 ``NAIA_search.py``의 멀티-그룹 처리 패턴 + 기존 9종 제외 문법과 통합.

연산자
------
태그 단위로 다음 prefix를 지원:

- ``tag``                  : 포함 (substring match) — 기본
- ``*tag``                 : 완전 일치
- ``~tag``                 : 제외 (substring 미포함)
- ``~*tag`` 또는 ``~!tag`` : 제외 (완전 일치 부재)
- ``{a, b, c}``            : OR 그룹 — a 또는 b 또는 c 중 하나라도 매치
- ``{*a, *b}``             : OR 그룹 내 완전 일치 가능
- ``{~a, ~b}``             : OR 그룹 내 제외 가능 (모두 제외돼야 그룹 매치)
- 콤마 구분 = AND          : ``a, b, c`` = a AND b AND c

복합 예
-------
``1girl, *blue hair, {long hair, short hair}, ~bad anatomy``

= ``1girl 포함 AND blue hair 정확 AND (long OR short hair) AND bad anatomy 부재``

사용 예
-------
>>> query = parse_query("1girl, *blue hair, ~lowres")
>>> matches(["1girl", "blue hair", "masterpiece"], query)  # True
>>> matches(["1boy", "blue hair"], query)                  # False (1girl 없음)
>>>
>>> # 큰 컬렉션에서 필터
>>> filtered = [tags for tags in all_items if matches(tags, query)]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from utils.app_logger import get_logger

_logger = get_logger("search_op")


class OpKind(Enum):
    INCLUDE_SUB = "include_sub"           # substring 포함
    INCLUDE_EXACT = "include_exact"       # 완전 일치
    EXCLUDE_SUB = "exclude_sub"           # substring 부재
    EXCLUDE_EXACT = "exclude_exact"       # 완전 일치 부재
    OR_GROUP = "or_group"                 # OR 그룹 (term들 중 하나라도 매치)


@dataclass
class Term:
    """단일 검색 term."""
    kind: OpKind = OpKind.INCLUDE_SUB
    value: str = ""
    # OR_GROUP일 때 sub-terms (OR_GROUP 자체는 ``value``를 안 씀)
    children: list["Term"] = field(default_factory=list)


@dataclass
class Query:
    """파싱된 쿼리 — AND 결합된 term들."""
    terms: list[Term] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.terms

    def __len__(self) -> int:
        return len(self.terms)


# ─────────────────────────────────────────────
# 파서
# ─────────────────────────────────────────────

def _strip_prefixes(token: str) -> tuple[OpKind, str]:
    """``*``/``~``/``~*``/``~!`` prefix → ``(kind, clean_value)``."""
    t = token.strip()
    if not t:
        return OpKind.INCLUDE_SUB, ""
    # 제외 prefix 먼저 (~* 와 ~! 우선 처리)
    if t.startswith("~*") or t.startswith("~!"):
        return OpKind.EXCLUDE_EXACT, t[2:].strip()
    if t.startswith("~"):
        return OpKind.EXCLUDE_SUB, t[1:].strip()
    if t.startswith("*"):
        return OpKind.INCLUDE_EXACT, t[1:].strip()
    return OpKind.INCLUDE_SUB, t


def _split_top_level(text: str) -> list[str]:
    """``{...}`` 중첩을 보호하면서 콤마로 split."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
            buf.append(ch)
        elif ch == "}":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            piece = "".join(buf).strip()
            if piece:
                parts.append(piece)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_query(query_text: str) -> Query:
    """텍스트 쿼리 파싱."""
    if not query_text or not query_text.strip():
        return Query()

    q = Query()
    for piece in _split_top_level(query_text):
        piece = piece.strip()
        if not piece:
            continue

        # OR 그룹: {a, b, c}
        if piece.startswith("{") and piece.endswith("}"):
            inner = piece[1:-1].strip()
            children: list[Term] = []
            for sub in _split_top_level(inner):
                kind, val = _strip_prefixes(sub)
                if val:
                    children.append(Term(kind=kind, value=val))
            if children:
                q.terms.append(Term(kind=OpKind.OR_GROUP, children=children))
            continue

        kind, val = _strip_prefixes(piece)
        if val:
            q.terms.append(Term(kind=kind, value=val))
    return q


# ─────────────────────────────────────────────
# 평가
# ─────────────────────────────────────────────

def _eval_term(term: Term, tags: list[str]) -> bool:
    if term.kind == OpKind.OR_GROUP:
        return any(_eval_term(c, tags) for c in term.children)

    val = term.value
    if term.kind == OpKind.INCLUDE_SUB:
        return any(val in t for t in tags)
    if term.kind == OpKind.INCLUDE_EXACT:
        return val in tags
    if term.kind == OpKind.EXCLUDE_SUB:
        return not any(val in t for t in tags)
    if term.kind == OpKind.EXCLUDE_EXACT:
        return val not in tags
    return True


def matches(tags: Iterable[str], query: Query) -> bool:
    """tags가 query를 만족하면 True. 모든 top-level term은 AND 결합."""
    if query.is_empty():
        return True
    tag_list = list(tags) if not isinstance(tags, list) else tags
    return all(_eval_term(t, tag_list) for t in query.terms)


def matches_text(tags: Iterable[str], query_text: str) -> bool:
    """텍스트 쿼리 즉시 평가 — 편의 함수."""
    return matches(tags, parse_query(query_text))


# ─────────────────────────────────────────────
# 컬렉션 필터
# ─────────────────────────────────────────────

def filter_items(items: Iterable, query: Query,
                 tags_of=lambda item: item) -> list:
    """``items`` 중 query 만족하는 것만.

    :param tags_of: 각 item에서 태그 리스트를 추출하는 함수. 기본은 item 자체.
    """
    if query.is_empty():
        return list(items)
    return [it for it in items if matches(tags_of(it), query)]


def explain(query: Query) -> str:
    """디버깅 — 쿼리를 사람이 읽기 쉬운 문자열로."""
    if query.is_empty():
        return "<empty>"
    out: list[str] = []
    for t in query.terms:
        out.append(_explain_term(t))
    return " AND ".join(out)


def _explain_term(t: Term) -> str:
    if t.kind == OpKind.OR_GROUP:
        return "(" + " OR ".join(_explain_term(c) for c in t.children) + ")"
    if t.kind == OpKind.INCLUDE_SUB:
        return f"contains '{t.value}'"
    if t.kind == OpKind.INCLUDE_EXACT:
        return f"exact '{t.value}'"
    if t.kind == OpKind.EXCLUDE_SUB:
        return f"not contains '{t.value}'"
    if t.kind == OpKind.EXCLUDE_EXACT:
        return f"not exact '{t.value}'"
    return "<?>"

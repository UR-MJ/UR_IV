"""프롬프트 토큰 집중 — 더 구체적인 태그에 포함되는 '광범위한' 태그를 제거.

규칙: 어떤 태그 T의 단어집합이 다른 태그 S의 단어집합의 '진부분집합'이면 T는 광범위 → 제거.
예) muscular, muscular male, blue dress, dress, frill dress
 -> muscular male, blue dress, frill dress
 (muscular ⊂ muscular male,  dress ⊂ blue dress / frill dress 이므로 muscular·dress 제거)

순수 로직(Qt 비의존) — tests/test_prompt_focus.py 회귀.
"""
from __future__ import annotations

from typing import List


def _words(tag: str) -> frozenset:
    """비교용 단어집합 — 소문자 + 언더스코어를 공백으로 보고 토큰화."""
    return frozenset(tag.strip().lower().replace('_', ' ').split())


def focus_tags(tags: List[str]) -> List[str]:
    """광범위(다른 더 구체적인 태그의 단어집합 진부분집합) 태그 제거. 순서/원형 보존 + 동일 중복 제거."""
    norm = [(t, _words(t)) for t in tags]
    out: List[str] = []
    seen = set()
    for i, (t, ws) in enumerate(norm):
        if not ws:                       # 빈 토큰은 그대로 통과(가중치/특수구문 보존 차원)
            out.append(t)
            continue
        # 다른 태그 S의 단어집합이 ws를 '진부분집합'으로 포함 → t는 광범위 → 제거
        if any(j != i and ws < ows for j, (_, ows) in enumerate(norm)):
            continue
        if ws in seen:                   # 동일 단어집합 중복(순서 무관)은 첫 번째만
            continue
        seen.add(ws)
        out.append(t)
    return out


def focus_prompt(prompt: str) -> str:
    """콤마 구분 프롬프트 문자열에 focus_tags 적용. <lora:..>·(tag:1.2) 등은 단어집합이 달라 보존됨."""
    if not prompt or not prompt.strip():
        return prompt
    tags = [p.strip() for p in prompt.split(',') if p.strip()]
    return ', '.join(focus_tags(tags))

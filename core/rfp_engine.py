"""
RFP Engine — NAIA 1.5의 RFP(Random Function Process)에서
범용적인 프롬프트 처리 알고리즘만 슬림 추출.

NAI 전용 부분 제외:
- ``{tag}=1.05`` / ``[tag]=1/1.05`` NAI 가중치 문법
- ``<|>_<|>`` 같은 NAI 페이스 이모지 변환
- NAI Director Tools 분기
- NAIA-specific ``qe_word`` / ``bag_of_tags`` / ``prompt_freq`` 사전 (호출자가 주입)

설계
----
모든 함수는 **순수 함수** (전역 상태 없음, 입력 → 출력).
태그는 ``list[str]`` 형태로 전달. 변경된 결과를 반환.
PyQt/Vue 의존성 없음 — ``core/`` 다른 모듈과 독립.

PromptPipeline 통합
-------------------
파일 끝의 ``make_*_hook()`` 팩토리로 훅 콜백 생성 → ``get_pipeline().register()``로 등록.

조건부 명령 문법 (``apply_conditional_commands``)
-------------------------------------------------
형식: ``(condition):command``

조건 (``&``, ``|`` 결합 가능):
- ``g`` / ``s`` / ``q`` / ``e``     — rating 일치 (general/sensitive/questionable/explicit)
- ``~g``                            — rating 불일치
- ``*tag``                          — 정확히 ``tag``가 있음
- ``~!tag``                         — 정확히 ``tag``가 없음
- ``~tag``                          — 어떤 element에도 ``tag`` 미포함
- ``tag``                           — 어떤 element에 ``tag`` 포함 (substring)

명령:
- ``keyword+=addition``             — ``keyword`` 뒤에 ``addition`` 삽입 (``^`` 로 다중 태그 구분)
- ``keyword=replacement``           — ``keyword``를 ``replacement``로 치환
- ``prompt``/``prefix``/``postfix`` — 매직 키워드 (해당 리스트에 추가)
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Optional

from utils.app_logger import get_logger

_logger = get_logger("rfp_engine")


# ─────────────────────────────────────────────────────────────────
# 1) 정규화 / 중복 제거
# ─────────────────────────────────────────────────────────────────

def split_tags(text: str) -> list[str]:
    """쉼표로 split + strip + 빈 문자열 제거."""
    return [t.strip() for t in text.split(",") if t.strip()]


def join_tags(tags: Iterable[str]) -> str:
    """리스트를 쉼표+공백으로 join."""
    return ", ".join(t for t in tags if t)


def dedupe(tags: list[str]) -> list[str]:
    """순서 보존 중복 제거."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def remove_collisions(main_tags: list[str],
                      prefix_tags: list[str],
                      postfix_tags: list[str]) -> list[str]:
    """main_tags에서 prefix/postfix와 충돌하는 태그 제거.

    NAIA 원본의 ``general = [item for item in general if item not in prompt_duplicate_check]``
    동작. 비교는 ``{}[]`` 가중치 마커 제거 후 수행.
    """
    strip_marks = str.maketrans("", "", "{}[]")
    blocked = set()
    for t in list(prefix_tags) + list(postfix_tags):
        blocked.add(t.translate(strip_marks).strip())
    return [t for t in main_tags if t not in blocked]


# ─────────────────────────────────────────────────────────────────
# 2) 카테고리 기반 필터링 (NSFW / 위치 / 색상 / 의상 등)
# ─────────────────────────────────────────────────────────────────

def filter_contains(tags: list[str],
                    needles: Iterable[str]) -> tuple[list[str], list[str]]:
    """태그 문자열에 ``needles`` 중 하나라도 substring으로 포함되면 제거.

    예: ``filter_contains(tags, [" eye"])`` → " eye"가 들어간 태그 제거 ("blue eyes" 등)

    :returns: ``(kept, removed)``
    """
    needle_list = list(needles)
    kept: list[str] = []
    removed: list[str] = []
    for t in tags:
        if any(n in t for n in needle_list):
            removed.append(t)
        else:
            kept.append(t)
    return kept, removed


# ─────────────────────────────────────────────────────────────────
# 5) 조건부 명령 (conditional commands)
# ─────────────────────────────────────────────────────────────────

_COND_RE = re.compile(r"\((.*?)\)\:(.*)", re.DOTALL)


def parse_conditional_command(command: str) -> tuple[str, str]:
    """``(condition):command`` 형태에서 조건과 명령 분리.

    형식이 아니면 ``("", command)`` 반환 (무조건 실행 명령).
    """
    m = _COND_RE.match(command.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", command.strip()


def evaluate_condition(condition: str,
                       prompts: list[str],
                       rating: Optional[str] = None) -> bool:
    """조건 문자열 평가.

    문법은 모듈 docstring 참조. 빈 조건은 항상 True.
    """
    if not condition:
        return True

    # ")&(" 로 최상위 그룹 분리
    sub_conditions = re.split(r"\)\s*&\s*\(", condition)
    sub_conditions = [re.sub(r"^\(|\)$", "", c).strip() for c in sub_conditions]

    results: list[bool] = []
    for sub in sub_conditions:
        if "&" in sub:
            results.append(all(
                evaluate_condition(c.strip(), prompts, rating)
                for c in sub.split("&")
            ))
        elif "|" in sub:
            results.append(any(
                evaluate_condition(c.strip(), prompts, rating)
                for c in sub.split("|")
            ))
        else:
            results.append(_eval_atom(sub, prompts, rating))
    return all(results)


def _eval_atom(atom: str, prompts: list[str], rating: Optional[str]) -> bool:
    """단일 조건 atom 평가."""
    atom = atom.strip()
    # rating 일치 (g/s/q/e)
    if atom in ("g", "s", "q", "e"):
        return rating == atom
    if atom in ("~g", "~s", "~q", "~e"):
        return rating != atom[1:]
    # 정확 일치
    if atom.startswith("*"):
        return atom[1:] in prompts
    # 정확 부재
    if atom.startswith("~!"):
        return atom[2:] not in prompts
    # 어떤 element에도 substring 미포함
    if atom.startswith("~"):
        needle = atom[1:]
        return all(needle not in t for t in prompts)
    # 기본: 어떤 element에든 substring 포함
    return any(atom in t for t in prompts)


def execute_command(prompts: list[str],
                    command: str,
                    prefix: list[str],
                    postfix: list[str]) -> list[str]:
    """단일 명령 실행. ``prompts`` 변경 후 반환.

    ``+=`` : ``keyword+=addition`` — ``keyword`` 뒤에 삽입 (``^`` 로 다중 태그 구분)
    ``=``  : ``keyword=replacement`` — 치환
    매직 키워드 ``prompt`` / ``prefix`` / ``postfix`` — 해당 리스트 끝에 추가
    """
    if "+=" in command:
        keyword, addition = command.split("+=", 1)
        addition = addition.replace("^", ", ")
        return _insert_after_keyword(prompts, keyword.strip(), addition.strip(), prefix, postfix)
    if "=" in command:
        keyword, replacement = command.split("=", 1)
        keyword = keyword.strip()
        replacement = replacement.replace("^", ", ").strip()
        if keyword in prompts:
            idx = prompts.index(keyword)
            prompts[idx] = replacement
    return prompts


def _insert_after_keyword(prompts: list[str],
                          keyword: str,
                          addition: str,
                          prefix: list[str],
                          postfix: list[str]) -> list[str]:
    """매직 키워드 처리 + 일반 키워드 뒤 삽입."""
    if keyword == "prompt":
        prompts.append(addition)
    elif keyword == "prefix":
        prefix.append(addition)
    elif keyword == "postfix":
        postfix.append(addition)
    elif keyword in prompts:
        idx = prompts.index(keyword) + 1
        prompts.insert(idx, addition)
    return prompts


# ─────────────────────────────────────────────────────────────────
# 6) PromptPipeline 훅 팩토리
# ─────────────────────────────────────────────────────────────────

def make_dedupe_hook() -> Callable:
    """main_tags 중복 제거 + prefix/postfix 충돌 제거 훅.

    POST_PROCESSING 또는 AFTER_WILDCARD 단계에 등록 권장.
    """
    def hook(ctx) -> None:
        ctx.main_tags = remove_collisions(
            dedupe(ctx.main_tags), ctx.prefix_tags, ctx.postfix_tags
        )
    return hook

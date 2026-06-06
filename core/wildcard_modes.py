"""
Wildcard Modes — 파일 와일드카드의 3가지 선택 모드 + 가중치 문법.

NAIA 2.0의 ``core/wildcard_processor.py`` 패턴을 참고. NAI 전용 부분 없음.

문법
----
- ``__name__``               — **랜덤** (가중치 적용)
- ``__*name__``              — **순차** (호출마다 다음 줄로 진행, 끝 도달 시 처음으로)
- ``__$master:slave__``      — **종속** (master 와일드카드가 N번째 줄을 골랐으면
                                slave 와일드카드도 N번째 줄 선택)

라인 가중치 (랜덤 모드에서만):
- ``tag`` (가중치 없음)       — 기본 가중치 1
- ``{100}:tag``               — 가중치 100 (100배 자주 뽑힘)
- ``{0.5}:tag``               — 가중치 0.5 (실수 OK)

주석 / 빈 줄:
- ``#``로 시작하는 줄, 공백 줄은 무시.

파일
----
``wildcards/<name>.txt`` — UTF-8, 줄당 하나의 후보.
"""
from __future__ import annotations

import random
import re
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

from utils.app_logger import get_logger

_logger = get_logger("wildcard_modes")


class WildcardMode(Enum):
    RANDOM = "random"
    SEQUENTIAL = "sequential"
    DEPENDENT = "dependent"


# 패턴: __NAME__ / __*NAME__ / __$MASTER:SLAVE__
# 이름 허용 문자: 영숫자/언더스코어/하이픈/슬래시(서브폴더)/점
_NAME_RE = r"[\w\-/.]+"
_PATTERN_RE = re.compile(
    rf"__(?P<prefix>[*$]?)(?P<body>{_NAME_RE}(?::{_NAME_RE})?)__"
)

# 가중치 문법: {weight}:line — weight는 양수 (정수/실수)
_WEIGHT_RE = re.compile(r"^\{(?P<w>[0-9]+(?:\.[0-9]+)?)\}:(?P<line>.*)$")


def parse_weighted_line(line: str) -> tuple[float, str]:
    """``{100}:tag`` 형태에서 ``(가중치, 텍스트)`` 추출.

    가중치 없으면 ``(1.0, line)`` 반환.
    """
    line = line.strip()
    m = _WEIGHT_RE.match(line)
    if not m:
        return 1.0, line
    try:
        w = float(m.group("w"))
        if w <= 0:
            return 1.0, m.group("line").strip()
        return w, m.group("line").strip()
    except ValueError:
        return 1.0, line


def load_lines(path: Path) -> list[str]:
    """와일드카드 파일에서 유효 라인 목록 반환 (주석/빈 줄 제거)."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out



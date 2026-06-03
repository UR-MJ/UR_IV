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


class WildcardResolver:
    """와일드카드 디렉토리를 관리하며 텍스트 내 패턴을 치환.

    상태가 있는 클래스 (순차 인덱스, 종속 매칭 기록).
    멀티스레드 환경에서 ``resolve()``는 thread-safe.
    """

    def __init__(self, wildcards_dir: Path,
                 rng: Optional[random.Random] = None):
        self.wildcards_dir = Path(wildcards_dir)
        self._rng = rng or random.Random()
        # name -> [lines]
        self._cache: dict[str, list[str]] = {}
        # name -> next index for sequential
        self._seq_state: dict[str, int] = {}
        # master_name -> last selected index for dependent
        self._dep_state: dict[str, int] = {}
        # overrides (특정 이름의 결과를 강제 지정 — NAIA의 wildcard_override 패턴)
        self._overrides: dict[str, str] = {}
        self._lock = threading.RLock()

    # ────────────────────────────────────────
    # 캐시 / 로드
    # ────────────────────────────────────────

    def _path(self, name: str) -> Path:
        return self.wildcards_dir / f"{name}.txt"

    def _get_lines(self, name: str) -> list[str]:
        with self._lock:
            if name not in self._cache:
                self._cache[name] = load_lines(self._path(name))
            return self._cache[name]

    def invalidate(self, name: Optional[str] = None) -> None:
        """캐시 무효화. ``name`` 지정 시 해당 와일드카드만, 아니면 전체."""
        with self._lock:
            if name is None:
                self._cache.clear()
            else:
                self._cache.pop(name, None)

    def reset_state(self) -> None:
        """순차/종속 상태 초기화 (캐시는 유지)."""
        with self._lock:
            self._seq_state.clear()
            self._dep_state.clear()

    # ────────────────────────────────────────
    # 오버라이드 (특정 이름의 결과를 강제 지정)
    # ────────────────────────────────────────

    def set_override(self, name: str, value: str) -> None:
        with self._lock:
            self._overrides[name] = value

    def clear_override(self, name: Optional[str] = None) -> None:
        with self._lock:
            if name is None:
                self._overrides.clear()
            else:
                self._overrides.pop(name, None)

    # ────────────────────────────────────────
    # 단일 선택
    # ────────────────────────────────────────

    def pick_random(self, name: str) -> str:
        """가중치 적용 랜덤 선택. 빈 와일드카드면 ``"__name__"`` 반환 (원본 유지)."""
        if name in self._overrides:
            return self._overrides[name]
        lines = self._get_lines(name)
        if not lines:
            _logger.debug(f"wildcard empty or missing: {name}")
            return f"__{name}__"
        weights: list[float] = []
        values: list[str] = []
        for ln in lines:
            w, v = parse_weighted_line(ln)
            weights.append(w)
            values.append(v)
        return self._rng.choices(values, weights=weights, k=1)[0]

    def pick_sequential(self, name: str) -> str:
        """순차 선택. 끝 도달 시 처음으로 순환."""
        if name in self._overrides:
            return self._overrides[name]
        lines = self._get_lines(name)
        if not lines:
            return f"__*{name}__"
        with self._lock:
            idx = self._seq_state.get(name, 0) % len(lines)
            self._seq_state[name] = (idx + 1) % len(lines)
        _, value = parse_weighted_line(lines[idx])
        return value

    def pick_dependent(self, master: str, slave: str) -> str:
        """master가 N번째 줄을 골랐으면 slave도 N번째 줄.

        master가 아직 안 뽑혔으면 master를 먼저 랜덤으로 뽑고 그 인덱스 사용.
        """
        slave_key = f"{master}:{slave}"
        if slave_key in self._overrides:
            return self._overrides[slave_key]

        slave_lines = self._get_lines(slave)
        if not slave_lines:
            return f"__${master}:{slave}__"

        with self._lock:
            if master in self._dep_state:
                idx = self._dep_state[master] % len(slave_lines)
            else:
                # master 결과가 없으면 무작위 인덱스 선택 + 기록
                master_lines = self._get_lines(master)
                if not master_lines:
                    idx = self._rng.randrange(len(slave_lines))
                else:
                    idx = self._rng.randrange(len(master_lines))
                self._dep_state[master] = idx
            idx = idx % len(slave_lines)

        _, value = parse_weighted_line(slave_lines[idx])
        return value

    def pick_dependent_master(self, master: str) -> str:
        """종속 관계의 master를 뽑되, 인덱스를 ``_dep_state``에 기록."""
        if master in self._overrides:
            return self._overrides[master]
        lines = self._get_lines(master)
        if not lines:
            return f"__{master}__"
        weights: list[float] = []
        values: list[str] = []
        for ln in lines:
            w, v = parse_weighted_line(ln)
            weights.append(w)
            values.append(v)
        idx = self._rng.choices(range(len(values)), weights=weights, k=1)[0]
        with self._lock:
            self._dep_state[master] = idx
        return values[idx]

    # ────────────────────────────────────────
    # 텍스트 전체 치환
    # ────────────────────────────────────────

    def resolve(self, text: str, max_depth: int = 8) -> str:
        """텍스트에서 모든 패턴을 치환. 중첩 와일드카드도 max_depth까지 재귀.

        :param text: 입력 텍스트
        :param max_depth: 재귀 깊이 한계 (무한 루프 방지)
        """
        if not text or max_depth <= 0:
            return text

        def _replace(m: re.Match) -> str:
            prefix = m.group("prefix")
            body = m.group("body")
            try:
                if prefix == "$":
                    if ":" not in body:
                        return m.group(0)  # 형식 오류 — 원본 유지
                    master, slave = body.split(":", 1)
                    return self.pick_dependent(master.strip(), slave.strip())
                if prefix == "*":
                    return self.pick_sequential(body)
                # 기본 랜덤
                return self.pick_random(body)
            except Exception:
                _logger.exception(f"wildcard expansion failed: {m.group(0)!r}")
                return m.group(0)

        result = _PATTERN_RE.sub(_replace, text)
        # 결과에 다시 패턴이 있으면 재귀 (중첩 와일드카드)
        if _PATTERN_RE.search(result) and result != text:
            return self.resolve(result, max_depth - 1)
        return result


# ─────────────────────────────────────────────
# 모듈 레벨 헬퍼
# ─────────────────────────────────────────────

_default_resolver: Optional[WildcardResolver] = None
_default_lock = threading.Lock()


def get_default_resolver() -> Optional[WildcardResolver]:
    """루트의 ``wildcards/`` 디렉토리를 사용하는 전역 resolver. 없으면 None."""
    global _default_resolver
    if _default_resolver is None:
        with _default_lock:
            if _default_resolver is None:
                root = Path(__file__).resolve().parent.parent
                wc_dir = root / "wildcards"
                if wc_dir.is_dir():
                    _default_resolver = WildcardResolver(wc_dir)
    return _default_resolver


def make_wildcard_hook(resolver: Optional[WildcardResolver] = None):
    """PromptPipeline 훅 — main_tags를 join → resolve → split.

    AFTER_WILDCARD가 아니라 그 전(POST_PROCESSING 마지막) 단계 등록 권장.
    그래야 ``ctx.main_tags`` 안의 ``__name__`` 패턴이 다음 단계까지 확장된 상태로 전달.
    """
    r = resolver or get_default_resolver()

    def hook(ctx) -> None:
        if r is None:
            return
        # 합쳐서 한 번에 resolve (와일드카드 인덱스 동기화 위해)
        combined = ", ".join(ctx.main_tags)
        resolved = r.resolve(combined)
        ctx.main_tags = [t.strip() for t in resolved.split(",") if t.strip()]

    return hook

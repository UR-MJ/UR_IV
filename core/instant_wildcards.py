"""
Instant Wildcards — 파일 기반 와일드카드의 보조 인라인 시스템.

NAIA 2.0 ``modules/instant_wildcard_module.py`` 패턴 참고.

목적
----
``wildcards/*.txt`` 파일 와일드카드(WildcardResolver)와 별도로,
**JSON 한 곳에 모아 관리**하는 가벼운 와일드카드.

용도:
- 자주 쓰는 짧은 후보군 (의상, 표정 등)을 매번 파일 만들지 않고 정의
- 와일드카드 이력 추적 (어떤 슬롯에서 어떤 값이 뽑혔는지)
- ImageWindow 우클릭 메뉴 "이 와일드카드 결과 복사/고정/제거" 등 고급 UX 기반

파일 형식 (``user_data/instant_wildcards.json``):
```json
{
  "version": 1,
  "wildcards": {
    "mood":      ["happy", "sad", "{2}:neutral"],
    "outfit":    ["dress", "swimsuit", "uniform"]
  }
}
```

가중치 문법은 wildcard_modes와 동일 (``{N}:tag``).
"""
from __future__ import annotations

import json
import random
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from utils.app_logger import get_logger
from core.wildcard_modes import parse_weighted_line  # 가중치 파서 재사용

_logger = get_logger("instant_wildcards")


# 패턴: $$NAME$$ (파일 와일드카드의 __NAME__와 충돌 안 함)
_PATTERN_RE = re.compile(r"\$\$(?P<name>[\w\-/.]+)\$\$")


@dataclass
class InstantWildcardSet:
    """저장 단위 — 이름 → 후보 라인 리스트."""
    version: int = 1
    wildcards: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"version": self.version, "wildcards": dict(self.wildcards)}

    @classmethod
    def from_dict(cls, d: dict) -> "InstantWildcardSet":
        wc = d.get("wildcards", {})
        return cls(
            version=int(d.get("version", 1)),
            wildcards={k: list(v) for k, v in wc.items() if isinstance(v, list)},
        )


@dataclass
class PickRecord:
    """확장 시 이력 기록."""
    name: str
    picked: str
    weight: float
    index: int  # 후보 리스트에서의 0-based index


class InstantWildcards:
    """JSON 와일드카드 매니저.

    스레드 안전. RNG는 인스턴스마다 별도 가능 (테스트 시 시드 고정).
    """

    def __init__(self,
                 store_path: Optional[Path] = None,
                 rng: Optional[random.Random] = None):
        self.store_path = Path(store_path) if store_path else None
        self._rng = rng or random.Random()
        self._set = InstantWildcardSet()
        # 이력 — 최근 확장에서 뽑힌 항목들 (UI 우클릭 메뉴 기반)
        self._history: list[PickRecord] = []
        # 오버라이드 — 강제 값 (디버깅/스코프 처리용)
        self._overrides: dict[str, str] = {}
        # 고정 — 다음 확장에서 동일 값 (사용자 "고정" 메뉴 후 재생성용)
        self._pinned: dict[str, str] = {}
        self._lock = threading.RLock()

        if self.store_path and self.store_path.is_file():
            self.load()

    # ────────────────────────────────────────
    # 영속화
    # ────────────────────────────────────────

    def load(self) -> bool:
        if not self.store_path or not self.store_path.is_file():
            return False
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            with self._lock:
                self._set = InstantWildcardSet.from_dict(data)
            return True
        except Exception:
            _logger.exception(f"instant wildcards load failed: {self.store_path}")
            return False

    def save(self) -> bool:
        if not self.store_path:
            return False
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = self._set.to_dict()
            from utils.atomic_json import atomic_write_json
            atomic_write_json(str(self.store_path), data, indent=2)
            return True
        except Exception:
            _logger.exception(f"instant wildcards save failed: {self.store_path}")
            return False

    # ────────────────────────────────────────
    # CRUD
    # ────────────────────────────────────────

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._set.wildcards.keys())

    def get(self, name: str) -> list[str]:
        with self._lock:
            return list(self._set.wildcards.get(name, []))

    def set(self, name: str, lines: list[str]) -> None:
        with self._lock:
            self._set.wildcards[name] = list(lines)

    def add_line(self, name: str, line: str) -> None:
        with self._lock:
            self._set.wildcards.setdefault(name, []).append(line)

    def remove_line(self, name: str, line: str) -> bool:
        with self._lock:
            lst = self._set.wildcards.get(name)
            if not lst or line not in lst:
                return False
            lst.remove(line)
            return True

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._set.wildcards.pop(name, None) is not None

    def rename(self, old: str, new: str) -> bool:
        with self._lock:
            if old not in self._set.wildcards or new in self._set.wildcards:
                return False
            self._set.wildcards[new] = self._set.wildcards.pop(old)
            return True

    # ────────────────────────────────────────
    # 선택 (스코프 처리: pinned > override > random)
    # ────────────────────────────────────────

    def pick(self, name: str) -> str:
        with self._lock:
            # 고정 우선
            if name in self._pinned:
                return self._pinned[name]
            # 오버라이드
            if name in self._overrides:
                return self._overrides[name]
            lines = self._set.wildcards.get(name, [])
            if not lines:
                return f"$${name}$$"
            weights: list[float] = []
            values: list[str] = []
            for ln in lines:
                w, v = parse_weighted_line(ln)
                weights.append(w)
                values.append(v)
            idx = self._rng.choices(range(len(values)), weights=weights, k=1)[0]
            picked = values[idx]
            self._history.append(PickRecord(name=name, picked=picked,
                                            weight=weights[idx], index=idx))
            return picked

    def resolve(self, text: str, max_depth: int = 8) -> str:
        """``$$name$$`` 패턴을 치환. 중첩도 처리."""
        if not text or max_depth <= 0:
            return text

        def _repl(m: re.Match) -> str:
            try:
                return self.pick(m.group("name"))
            except Exception:
                _logger.exception(f"instant resolve failed: {m.group(0)}")
                return m.group(0)

        result = _PATTERN_RE.sub(_repl, text)
        if _PATTERN_RE.search(result) and result != text:
            return self.resolve(result, max_depth - 1)
        return result

    # ────────────────────────────────────────
    # 이력 / 고정 / 오버라이드
    # ────────────────────────────────────────

    def history(self) -> list[PickRecord]:
        with self._lock:
            return list(self._history)

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    def pin(self, name: str, value: str) -> None:
        """다음 확장에서 동일 값 강제. ``unpin``으로 해제."""
        with self._lock:
            self._pinned[name] = value

    def unpin(self, name: Optional[str] = None) -> None:
        with self._lock:
            if name is None:
                self._pinned.clear()
            else:
                self._pinned.pop(name, None)

    def is_pinned(self, name: str) -> bool:
        with self._lock:
            return name in self._pinned

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
    # Pipeline 훅 팩토리
    # ────────────────────────────────────────

    def make_hook(self) -> Callable:
        """PromptPipeline 훅 — main_tags를 join → resolve → split.

        wildcard_modes의 ``make_wildcard_hook``과 같은 단계에 등록 가능
        (서로 다른 패턴이라 충돌 없음).
        """
        def hook(ctx) -> None:
            combined = ", ".join(ctx.main_tags)
            resolved = self.resolve(combined)
            ctx.main_tags = [t.strip() for t in resolved.split(",") if t.strip()]
            # 이력 메타에 보존
            hist = self.history()
            if hist:
                ctx.metadata.setdefault("instant_wildcard_picks", []).extend(
                    {"name": r.name, "picked": r.picked, "weight": r.weight, "index": r.index}
                    for r in hist
                )
        return hook

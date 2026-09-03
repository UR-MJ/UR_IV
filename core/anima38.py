"""Pure parsing for the Forge Anima 3.8B Semantic Connector script.

Forge exposes this feature as one always-on script with six positional
arguments.  Keeping coercion here lets both backend adapters share the exact
contract without importing Qt, ComfyUI, or the Forge extension.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence


SCRIPT_NAME = "Anima 3.8B (Qwen3.5 / v2)"
DEFAULT_ADAPTER = "Anima-3.8B-expanded_adapter.safetensors"
ARG_NAMES = (
    "enabled",
    "adapter",
    "strength",
    "negative",
    "negative_strength",
    "bypass",
)


@dataclass(frozen=True)
class Anima38Settings:
    enabled: bool = False
    adapter: str = DEFAULT_ADAPTER
    strength: float = 1.0
    negative: bool = False
    negative_strength: float = 1.0
    bypass: bool = False

    def as_args(self) -> list[Any]:
        """Return the Forge positional representation in its declared order."""

        return [getattr(self, name) for name in ARG_NAMES]


DEFAULT_SETTINGS = Anima38Settings()


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _strength(value: Any, default: float = 1.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(0.0, min(2.0, parsed))


def parse_args(raw: Any = None) -> Anima38Settings:
    """Parse Forge positional args or its supported one-dict API form.

    ``raw`` may be the args list itself, a mapping, or ``None``.  Unknown keys
    and trailing positional values are ignored; missing values use the Forge
    defaults.
    """

    if isinstance(raw, Mapping):
        values = dict(raw)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        items = list(raw)
        if len(items) == 1 and isinstance(items[0], Mapping):
            values = dict(items[0])
        else:
            values = dict(zip(ARG_NAMES, items))
    else:
        values = {}

    adapter = str(values.get("adapter") or DEFAULT_ADAPTER).strip()
    return Anima38Settings(
        enabled=_bool(values.get("enabled"), False),
        adapter=adapter or DEFAULT_ADAPTER,
        strength=_strength(values.get("strength"), 1.0),
        negative=_bool(values.get("negative"), False),
        negative_strength=_strength(values.get("negative_strength"), 1.0),
        bypass=_bool(values.get("bypass"), False),
    )


def parse_script_block(block: Any = None) -> Anima38Settings:
    """Parse an ``alwayson_scripts[SCRIPT_NAME]`` block."""

    if not isinstance(block, Mapping):
        return DEFAULT_SETTINGS
    return parse_args(block.get("args", ()))


__all__ = [
    "ARG_NAMES",
    "DEFAULT_ADAPTER",
    "DEFAULT_SETTINGS",
    "SCRIPT_NAME",
    "Anima38Settings",
    "parse_args",
    "parse_script_block",
]

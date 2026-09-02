"""체크포인트 이름 맞추기 — 백엔드마다 표기가 다르다.

Forge 는 `Anima-3.8B-v1.1.safetensors [4a458d26b2]` 처럼 해시를 붙이고, ComfyUI 는 붙이지 않는다.
설정에 저장된 이름이 그 표기 그대로가 아니면(백엔드를 오갔거나, 해시가 바뀌었거나) 예전엔
목록 첫 항목으로 떨어져 **엉뚱한 모델**(krea2)로 생성이 나갔다. 여기서 해시·대소문자·경로를
무시하고 같은 파일을 찾는다.
"""
from __future__ import annotations

import re
from typing import Sequence

_HASH_SUFFIX = re.compile(r"\s*\[[0-9a-fA-F]{6,}\]\s*$")


def checkpoint_key(title: str) -> str:
    """`dir/Name.safetensors [abcdef1234]` → `name.safetensors` (비교용)."""
    value = _HASH_SUFFIX.sub("", str(title or "")).strip()
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    return value.casefold()


def match_checkpoint(saved: str, items: Sequence[str]) -> int:
    """저장된 이름과 같은 체크포인트의 index. 정확히 같으면 그것, 아니면 해시·경로를 뺀 파일명으로. 없으면 -1."""
    if not saved:
        return -1
    for index, item in enumerate(items):
        if item == saved:
            return index
    key = checkpoint_key(saved)
    if not key:
        return -1
    for index, item in enumerate(items):
        if checkpoint_key(item) == key:
            return index
    return -1

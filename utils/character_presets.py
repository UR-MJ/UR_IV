# utils/character_presets.py
"""캐릭터별 커스텀 프리셋 저장/로드"""
import os
import json

_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "character_presets.json")


def _load() -> dict:
    if not os.path.exists(_FILE):
        return {}
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", " ")


def save_character_preset(name: str, extra_prompt: str):
    """캐릭터 프리셋 저장"""
    data = _load()
    data[_normalize(name)] = {"extra_prompt": extra_prompt, "display_name": name}
    _save(data)


def get_character_preset(name: str) -> str | None:
    """캐릭터 프리셋에서 extra_prompt 로드. 없으면 None."""
    data = _load()
    entry = data.get(_normalize(name))
    if entry:
        return entry.get("extra_prompt", "")
    return None


def delete_character_preset(name: str):
    """캐릭터 프리셋 삭제"""
    data = _load()
    key = _normalize(name)
    if key in data:
        del data[key]
        _save(data)


def list_character_presets() -> dict[str, str]:
    """전체 프리셋 목록. {정규화이름: extra_prompt}"""
    data = _load()
    return {k: v.get("extra_prompt", "") for k, v in data.items()}


def has_preset(name: str) -> bool:
    """프리셋 존재 여부"""
    data = _load()
    return _normalize(name) in data

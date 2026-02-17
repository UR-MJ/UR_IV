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


def save_character_preset(name: str, extra_prompt: str,
                          cond_rules: str = "", cond_neg_rules: str = ""):
    """캐릭터 프리셋 저장 (조건부 규칙 포함)"""
    data = _load()
    entry = {
        "extra_prompt": extra_prompt,
        "display_name": name,
    }
    if cond_rules:
        entry["cond_rules"] = cond_rules
    if cond_neg_rules:
        entry["cond_neg_rules"] = cond_neg_rules
    data[_normalize(name)] = entry
    _save(data)


def get_character_preset(name: str) -> str | None:
    """캐릭터 프리셋에서 extra_prompt 로드. 없으면 None."""
    data = _load()
    entry = data.get(_normalize(name))
    if entry:
        return entry.get("extra_prompt", "")
    return None


def get_character_preset_full(name: str) -> dict | None:
    """캐릭터 프리셋 전체 데이터 로드. 없으면 None.
    Returns: {extra_prompt, cond_rules, cond_neg_rules, display_name}
    """
    data = _load()
    return data.get(_normalize(name))


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

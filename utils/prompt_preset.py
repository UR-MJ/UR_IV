# utils/prompt_preset.py
"""프롬프트 프리셋 저장/불러오기"""
import os

from utils.atomic_json import atomic_write_json, load_json_safe

_PRESET_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'user_data', 'prompt_presets.json')


def _load_all() -> dict[str, dict]:
    return load_json_safe(_PRESET_FILE, {})


def _save_all(presets: dict[str, dict]):
    try:
        atomic_write_json(_PRESET_FILE, presets)
    except Exception as e:
        print(f"[Preset] 저장 실패: {e}")
        raise  # 호출자에게 전파하여 사용자에게 알림 가능


def save_preset(name: str, data: dict):
    """프리셋 저장 (name → {prompt, negative, character, copyright, artist, ...})"""
    presets = _load_all()
    presets[name] = data
    _save_all(presets)


def delete_preset(name: str):
    """프리셋 삭제"""
    presets = _load_all()
    presets.pop(name, None)
    _save_all(presets)


def get_preset(name: str) -> dict | None:
    """프리셋 불러오기"""
    return _load_all().get(name)


def list_presets() -> list[str]:
    """프리셋 이름 목록"""
    return list(_load_all().keys())


def get_all_presets() -> dict[str, dict]:
    """전체 프리셋 반환"""
    return _load_all()

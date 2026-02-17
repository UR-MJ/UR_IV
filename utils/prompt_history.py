# utils/prompt_history.py
"""최근 프롬프트 히스토리 관리"""
import os
import json

_HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompt_history.json')
_MAX_HISTORY = 50


def _load() -> list[dict]:
    """히스토리 파일 로드"""
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(history: list[dict]):
    """히스토리 파일 저장"""
    try:
        with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history[:_MAX_HISTORY], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_entry(prompt: str, negative: str):
    """새 프롬프트 기록 추가 (중복 시 맨 앞으로 이동)"""
    prompt = prompt.strip()
    if not prompt:
        return
    history = _load()
    entry = {"prompt": prompt, "negative": negative.strip()}
    # 동일 프롬프트 제거
    history = [h for h in history if h.get("prompt") != prompt]
    history.insert(0, entry)
    _save(history)


def get_history() -> list[dict]:
    """히스토리 목록 반환 (최신순)"""
    return _load()


def clear_history():
    """히스토리 전체 삭제"""
    _save([])

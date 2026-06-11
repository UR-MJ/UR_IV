"""
Workflow Profiles — 체크포인트/VAE/TE/샘플러/CFG/LoRA/Prefix/Suffix 묶음 저장.

ANIMA용, SDXL용, Flux용 등 자주 쓰는 생성 환경을 통째로 저장하고
드롭다운 한 번에 전환.

저장 위치: ``config/profiles/<name>.json``
JSON 스키마:
{
    "name": "ANIMA Pony",
    "created_at": <unix>,
    "version": 1,
    "fields": {
        "model_combo": "anima_v3.safetensors",
        "vae_main_combo": "qwen_image_vae.safetensors",
        "te_main_input": "anima_baseV10_txt.safetensors",
        "sampler_combo": "DPM++ 2M",
        "scheduler_combo": "Karras",
        "steps_input": "28",
        "cfg_input": "5",
        "shift_input": "0",
        "width_input": "1024",
        "height_input": "1024",
        "prefix_prompt_text": "score_9, score_8_up, ...",
        "suffix_prompt_text": "blurry, ...",
        "neg_prompt_text": "lowres, ...",
    },
    "lora_stack": [
        {"name": "...", "weight": 0.8, "enabled": true, "triggerWords": [...]},
    ]
}
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from utils.app_logger import get_logger

_logger = get_logger("workflow_profile")


# 프로파일에 포함될 위젯 ID 목록 (Vue widgets 키)
# 사용자가 자주 바꾸는 생성 세팅 위주
PROFILE_FIELDS: tuple[str, ...] = (
    "model_combo",
    "vae_main_combo",
    "te_main_input",
    "sampler_combo",
    "scheduler_combo",
    "steps_input",
    "cfg_input",
    "shift_input",
    "width_input",
    "height_input",
    "prefix_prompt_text",
    "suffix_prompt_text",
    "neg_prompt_text",
)


def _profiles_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    d = root / "config" / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_name(name: str) -> str:
    """파일명 안전 — core/file_naming.py 공용 유틸 위임 (기존 폴백 유지)."""
    from core.file_naming import sanitize_filename
    return sanitize_filename(name, fallback="프로파일")


def _path(name: str) -> Path:
    return _profiles_dir() / f"{_sanitize_name(name)}.json"


# ─────────────────────────────────────────
# 조회 / 삭제
# ─────────────────────────────────────────

def list_profiles() -> list[dict[str, Any]]:
    """모든 프로파일 메타데이터 — 이름순. (전체 fields 없이 가벼움)"""
    result: list[dict[str, Any]] = []
    for p in sorted(_profiles_dir().glob("*.json"), key=lambda x: x.name.lower()):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        result.append({
            "name": data.get("name", p.stem),
            "created_at": data.get("created_at", 0),
            "model": (data.get("fields") or {}).get("model_combo", ""),
            "vae": (data.get("fields") or {}).get("vae_main_combo", ""),
        })
    return result


def load_profile(name: str) -> dict[str, Any] | None:
    """전체 프로파일 데이터 로드."""
    path = _path(name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _logger.exception(f"프로파일 로드 실패: {name}")
        return None


def delete_profile(name: str) -> bool:
    path = _path(name)
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        _logger.exception(f"프로파일 삭제 실패: {name}")
        return False


def rename_profile(old: str, new: str) -> bool:
    """이름 변경. new가 이미 있으면 False."""
    old_path = _path(old)
    new_path = _path(new)
    if not old_path.is_file() or new_path.exists():
        return False
    try:
        data = json.loads(old_path.read_text(encoding="utf-8"))
        data["name"] = _sanitize_name(new)
        new_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        old_path.unlink()
        return True
    except Exception:
        _logger.exception(f"프로파일 이름 변경 실패: {old} → {new}")
        return False


# ─────────────────────────────────────────
# 저장 (현재 상태 → 프로파일)
# ─────────────────────────────────────────

def save_profile(name: str,
                 fields: dict[str, Any],
                 lora_stack: list[dict[str, Any]] | None = None,
                 overwrite: bool = True) -> bool:
    """``fields`` dict + ``lora_stack`` 리스트를 프로파일로 저장.

    :param fields: ``{widget_id: value}`` — PROFILE_FIELDS만 골라서 저장
    :param lora_stack: ``[{name, weight, enabled, triggerWords}, ...]``
    :param overwrite: False면 동명 프로파일 있을 때 False 반환
    """
    clean_name = _sanitize_name(name)
    if not clean_name:
        return False
    path = _path(clean_name)
    if path.exists() and not overwrite:
        return False

    # fields는 화이트리스트에 있는 키만
    filtered = {k: ("" if v is None else str(v)) for k, v in fields.items()
                if k in PROFILE_FIELDS}
    payload = {
        "name": clean_name,
        "created_at": int(time.time()),
        "version": 1,
        "fields": filtered,
        "lora_stack": [dict(e) for e in (lora_stack or [])],
    }
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        _logger.exception(f"프로파일 저장 실패: {clean_name}")
        return False


# ─────────────────────────────────────────
# 적용 (프로파일 → 호스트 widgets)
# ─────────────────────────────────────────

def apply_profile_to_host(profile_data: dict[str, Any], host: Any) -> dict[str, Any]:
    """프로파일을 호스트(GeneratorMainUI 등)에 적용.

    호스트가 가진 위젯 프록시를 통해 값 적용:
    - 'vae_main_combo' 같은 ComboBoxProxy는 setText (fallback 가능)
    - 'cfg_input', 'steps_input' 같은 SliderProxy/LineEditProxy는 setText
    - 'prefix_prompt_text' 같은 TextEditProxy는 setPlainText

    LoRA Stack은 호스트의 ``_vue_lora_text`` / ``_vue_lora_entries``를
    직접 갱신 + Vue로 push.

    :return: ``{applied: [...keys], skipped: [...]}``
    """
    applied: list[str] = []
    skipped: list[str] = []
    fields = (profile_data or {}).get("fields", {}) or {}

    for key, value in fields.items():
        proxy = getattr(host, key, None)
        if proxy is None:
            # ComboBox / SliderProxy의 일반적 widget_id 매핑
            skipped.append(key)
            continue
        try:
            # ComboBoxProxy / LineEditProxy / TextEditProxy / SliderProxy 모두 setText 지원
            if hasattr(proxy, "setPlainText"):
                proxy.setPlainText(str(value))
            elif hasattr(proxy, "setText"):
                proxy.setText(str(value))
            else:
                skipped.append(key)
                continue
            applied.append(key)
        except Exception:
            _logger.exception(f"프로파일 필드 적용 실패: {key}")
            skipped.append(key)

    # LoRA Stack 적용 — Vue 측의 lora_stack 액션 호출과 동일한 효과
    lora = (profile_data or {}).get("lora_stack", []) or []
    if isinstance(lora, list):
        try:
            host._vue_lora_entries = list(lora)
            # Vue로 푸시
            bridge = getattr(host, "vue_bridge", None)
            if bridge is not None and hasattr(bridge, "loraStackLoaded"):
                bridge.loraStackLoaded.emit(json.dumps(lora))
            applied.append("lora_stack")
        except Exception:
            _logger.exception("LoRA stack 적용 실패")
            skipped.append("lora_stack")

    return {"applied": applied, "skipped": skipped}


def collect_from_host(host: Any) -> dict[str, Any]:
    """호스트 현재 상태에서 프로파일 fields + lora_stack 추출.

    저장 시 호출 — Vue 위젯 값은 host.vue_bridge가 캐시함.
    """
    fields: dict[str, str] = {}
    for key in PROFILE_FIELDS:
        proxy = getattr(host, key, None)
        if proxy is None:
            continue
        try:
            if hasattr(proxy, "currentText"):
                fields[key] = proxy.currentText()
            elif hasattr(proxy, "toPlainText"):
                fields[key] = proxy.toPlainText()
            elif hasattr(proxy, "text"):
                fields[key] = proxy.text()
        except Exception:
            pass

    lora_stack = getattr(host, "_vue_lora_entries", None) or []
    if not isinstance(lora_stack, list):
        lora_stack = []
    return {"fields": fields, "lora_stack": list(lora_stack)}

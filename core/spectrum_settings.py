"""Opt-in Spectrum settings. No provider installation or global model eviction."""
from __future__ import annotations

import math
from collections.abc import Mapping


FIELDS = {
    "window_size": (2.0, 1.0, 4.0, False),
    "flex_window": (0.25, 0.0, 1.0, False),
    "warmup_steps": (6, 1, 150, True),
    "tail_actual_steps": (3, 1, 150, True),
    "blend_w": (0.3, 0.0, 1.0, False),
    "cheby_degree": (3, 1, 10, True),
    "ridge_lambda": (0.1, 0.001, 10.0, False),
    "history_size": (100, 5, 256, True),
}


def spectrum_payload_from_prefs(prefs: Mapping) -> dict:
    settings = prefs.get("comfySpectrum", {})
    if not isinstance(settings, Mapping) or settings.get("enabled") is not True:
        return {}
    payload = {"spectrum_enabled": True, "spectrum_one_sampler_only": True}
    for name, (default, low, high, integer) in FIELDS.items():
        value = settings.get(name, default)
        if isinstance(value, bool):
            raise ValueError(f"Spectrum {name}: 숫자를 입력하세요.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Spectrum {name}: 숫자를 입력하세요.") from exc
        if not math.isfinite(number) or not low <= number <= high or (integer and number != int(number)):
            raise ValueError(f"Spectrum {name}: {low}~{high} 범위를 확인하세요.")
        payload[f"spectrum_{name}"] = int(number) if integer else number
    return payload


def validate_spectrum_payload(payload: Mapping, object_info: Mapping) -> None:
    if payload.get("spectrum_enabled") not in (True, "true", 1):
        return
    settings = {name: payload.get(f"spectrum_{name}", spec[0]) for name, spec in FIELDS.items()}
    spectrum_payload_from_prefs({"comfySpectrum": {"enabled": True, **settings}})
    if "DiTSpectrumPatch" not in object_info:
        raise ValueError("Spectrum 실험 기능을 켰지만 ComfyUI에 DiTSpectrumPatch가 없습니다. 호환 조합 안내를 확인하거나 Spectrum을 끄세요.")
    steps = int(payload.get("steps", 20))
    if int(settings["warmup_steps"]) + int(settings["tail_actual_steps"]) >= steps:
        raise ValueError("Spectrum 준비 단계 + 마지막 실제 계산 단계는 전체 Steps보다 작아야 합니다.")
    if payload.get("speed_enabled") in (True, "true", 1):
        raise ValueError("Spectrum 실험 기능과 SPEED는 함께 켤 수 없습니다. 독립적으로 A/B 비교하세요.")

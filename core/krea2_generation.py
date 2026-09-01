"""Krea 2 execution seam shared by the regular T2I and I2I workers.

Krea 2 is a generation family hosted by ComfyUI, not a checkpoint that can be
inserted into the application's generic Comfy workflow.  This module owns the
entire translation from normal generation payloads to validated Krea workflow
graphs, including browser-image upload and Comfy resource choice resolution.
"""

from __future__ import annotations

import base64
import binascii
import inspect
import re
import secrets
import uuid
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from backends.base import GenerationResult
from core.creator_workflows import build


KREA2_FAMILY = "krea2"
KREA2_UI_LABEL = "KREA2"

_LORA_TAG = re.compile(r"<lora:[^>]+>", re.IGNORECASE)
_IMAGE_FORMATS = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
    "BMP": ("bmp", "image/bmp"),
    "TIFF": ("tiff", "image/tiff"),
}


def run_krea2_generation(
    backend: Any,
    operation: str,
    payload: Mapping[str, Any],
    progress_callback: Callable[[int, int, bytes | None], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> GenerationResult:
    """Run Krea 2 T2I or identity-edit I2I through a ComfyUI adapter.

    The adapter contract is intentionally structural: ``get_backend_type()``,
    ``get_object_info()``, ``upload_media()`` for I2I, and ``run_workflow()``.
    This keeps the orchestration independently testable with a small fake.
    """

    try:
        def ensure_not_cancelled() -> None:
            if cancel_check and cancel_check():
                raise RuntimeError("사용자가 작업을 취소했습니다")

        def call_cancellable(method: Callable[..., Any], *args: Any) -> Any:
            ensure_not_cancelled()
            try:
                parameters = inspect.signature(method).parameters.values()
                supports_cancel = any(
                    parameter.name == "cancel_check"
                    or parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in parameters
                )
            except (TypeError, ValueError):
                supports_cancel = False
            if supports_cancel:
                return method(*args, cancel_check=cancel_check)
            return method(*args)

        ensure_not_cancelled()
        _require_comfy_adapter(backend, operation)
        values = dict(payload or {})
        mode = str(operation or "").strip().lower()
        if mode not in {"t2i", "i2i"}:
            raise ValueError("operation은 't2i' 또는 'i2i'여야 합니다")

        prompt = _strip_standard_lora_tags(str(values.get("prompt", "") or ""))
        seed = _normalise_seed(values.get("seed", -1))
        width = _int_value(values.get("width", 1024), "width")
        height = _int_value(values.get("height", 1024), "height")

        if mode == "t2i":
            params = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "seed": seed,
                "steps": _int_value(values.get("steps", 8), "steps"),
                "cfg": _float_value(values.get("cfg_scale", values.get("cfg", 1)), "cfg"),
                "sampler": _normalise_sampler(values.get("sampler_name", values.get("sampler", "euler"))),
                "use_textfusion": False,
                "output_prefix": "Krea2/T2I",
            }
            built = build("krea2_t2i", params)
        else:
            source = _first_image(values.get("init_images"))
            source_data, source_ext, source_mime = _decode_image(source, "Krea2 I2I 원본")
            source_name = call_cancellable(
                backend.upload_media,
                source_data,
                f"krea2_source_{uuid.uuid4().hex}.{source_ext}",
                source_mime,
            )
            params = {
                "prompt": prompt,
                "input_image": source_name,
                "width": width,
                "height": height,
                "seed": seed,
                "steps": _int_value(values.get("steps", 15), "steps"),
                "cfg": _float_value(values.get("cfg_scale", values.get("cfg", 1)), "cfg"),
                "sampler": _normalise_sampler(values.get("sampler_name", values.get("sampler", "euler"))),
                "fidelity": _float_value(values.get("krea2_fidelity", values.get("fidelity", 4)), "fidelity"),
                "output_prefix": "Krea2/I2I",
            }
            reference = values.get("krea2_reference_image")
            if reference:
                ref_data, ref_ext, ref_mime = _decode_image(reference, "Krea2 identity reference")
                params["reference_image"] = call_cancellable(
                    backend.upload_media,
                    ref_data,
                    f"krea2_reference_{uuid.uuid4().hex}.{ref_ext}",
                    ref_mime,
                )
            built = build("krea2_edit", params)

        object_info = call_cancellable(backend.get_object_info)
        if not isinstance(object_info, dict):
            raise RuntimeError("ComfyUI /object_info 응답이 올바른 객체가 아닙니다")
        _check_required_nodes(built, set(object_info))
        _resolve_comfy_choices(built, object_info)

        result = call_cancellable(
            backend.run_workflow, built["workflow"], progress_callback
        )
        if not isinstance(result, GenerationResult):
            raise TypeError("ComfyUI adapter가 GenerationResult를 반환하지 않았습니다")
        if not result.success:
            return result

        info = dict(built.get("metadata", {}))
        info.update(result.info or {})
        if "cfg" in info:
            info.setdefault("cfg_scale", info["cfg"])
        if "sampler" in info:
            info.setdefault("sampler_name", info["sampler"])
        info.update({
            "generation_family": KREA2_FAMILY,
            "model": "Krea 2 Turbo",
            "prompt": prompt,
            "negative_prompt": str(values.get("negative_prompt", "") or ""),
            "negative_prompt_applied": False,
        })
        result.info = info
        return result
    except Exception as exc:
        return GenerationResult(
            success=False,
            error=f"Krea2 생성 준비/실행 실패: {exc}",
        )


def _require_comfy_adapter(backend: Any, operation: str) -> None:
    backend_type = ""
    try:
        backend_type = str(backend.get_backend_type()).strip().lower()
    except Exception:
        pass
    if backend_type != "comfyui":
        raise RuntimeError("Krea2 T2I/I2I는 ComfyUI 백엔드가 필요합니다")
    required = ["get_object_info", "run_workflow"]
    if str(operation).strip().lower() == "i2i":
        required.append("upload_media")
    missing = [name for name in required if not callable(getattr(backend, name, None))]
    if missing:
        raise RuntimeError("현재 ComfyUI adapter에 필요한 기능이 없습니다: " + ", ".join(missing))


def _normalise_seed(raw: Any) -> int:
    seed = _int_value(raw, "seed")
    if seed < 0:
        return secrets.randbits(32)
    if seed > 0xFFFFFFFF:
        raise ValueError("seed는 -1 또는 0~4294967295 범위여야 합니다")
    return seed


def _int_value(raw: Any, name: str) -> int:
    if isinstance(raw, bool):
        raise ValueError(f"{name}은 정수여야 합니다")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}은 정수여야 합니다") from exc
    return value


def _float_value(raw: Any, name: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"{name}은 숫자여야 합니다")
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}은 숫자여야 합니다") from exc


def _normalise_sampler(raw: Any) -> str:
    value = str(raw or "").strip().lower().replace("++", "pp")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    if "2m" in value and "sde" in value:
        return "dpmpp_2m_sde"
    if "dpm" in value and "sde" in value:
        return "dpmpp_sde"
    if "heun" in value:
        return "heun"
    return "euler"


def _strip_standard_lora_tags(prompt: str) -> str:
    cleaned = _LORA_TAG.sub("", prompt)
    cleaned = re.sub(r"\s*,\s*,+", ", ", cleaned)
    cleaned = re.sub(r",\s+", ", ", cleaned)
    return cleaned.strip(" ,\t\r\n")


def _first_image(raw: Any) -> Any:
    if isinstance(raw, (list, tuple)) and raw:
        return raw[0]
    raise ValueError("Krea2 I2I 원본 이미지가 없습니다")


def _decode_image(raw: Any, label: str) -> tuple[bytes, str, str]:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{label} 데이터가 없습니다")
    encoded = raw.strip()
    if encoded.startswith("data:"):
        if "," not in encoded:
            raise ValueError(f"{label} data URL이 올바르지 않습니다")
        encoded = encoded.split(",", 1)[1]
    try:
        data = base64.b64decode("".join(encoded.split()), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{label} base64가 올바르지 않습니다") from exc
    if not data:
        raise ValueError(f"{label}가 비어 있습니다")
    if len(data) > 100 * 1024 * 1024:
        raise ValueError(f"{label}는 100MB 이하여야 합니다")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            image_format = str(image.format or "").upper()
    except Exception as exc:
        raise ValueError(f"{label}가 지원되는 이미지가 아닙니다") from exc
    if image_format not in _IMAGE_FORMATS:
        raise ValueError(f"{label} 형식은 PNG/JPEG/WebP/BMP/TIFF 중 하나여야 합니다")
    extension, mime = _IMAGE_FORMATS[image_format]
    return data, extension, mime


def _check_required_nodes(built: Mapping[str, Any], available: set[str]) -> None:
    missing = sorted(set(built.get("required_node_types", ())) - available)
    if missing:
        raise RuntimeError("ComfyUI 필수 노드가 없습니다: " + ", ".join(missing))


def _resolve_comfy_choices(
    built: Mapping[str, Any],
    object_info: Mapping[str, Any],
) -> None:
    """Resolve portable model paths to exact server-native combo values."""

    for node in built.get("workflow", {}).values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        schema = object_info.get(class_type, {})
        input_schema = schema.get("input", {}) if isinstance(schema, dict) else {}
        definitions: dict[str, Any] = {}
        for section in ("required", "optional"):
            section_values = input_schema.get(section, {}) if isinstance(input_schema, dict) else {}
            if isinstance(section_values, dict):
                definitions.update(section_values)
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for name, value in list(inputs.items()):
            if class_type == "LoadImage" and name == "image":
                continue
            definition = definitions.get(name)
            if not isinstance(value, str) or not isinstance(definition, (list, tuple)) or not definition:
                continue
            choices = definition[0]
            if not isinstance(choices, (list, tuple)):
                continue
            normalized = value.replace("\\", "/").casefold()
            match = next(
                (
                    choice
                    for choice in choices
                    if isinstance(choice, str)
                    and choice.replace("\\", "/").casefold() == normalized
                ),
                None,
            )
            if match is None:
                requested_stem = Path(normalized).stem
                stem_matches = [
                    choice
                    for choice in choices
                    if isinstance(choice, str)
                    and Path(choice.replace("\\", "/").casefold()).stem == requested_stem
                ]
                if len(stem_matches) == 1:
                    match = stem_matches[0]
            if match is not None:
                inputs[name] = match
            elif choices:
                raise RuntimeError(
                    f"ComfyUI 리소스 선택지에 {class_type}.{name}={value!r} 항목이 없습니다"
                )

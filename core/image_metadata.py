"""
Image Metadata — PNG / JPEG / WebP 생성 메타데이터 추출 + 이식.

NAIA 2.0 ``tabs/png_info_tab.py`` 패턴 참고 (NAI Comment / Stealth PNG 제외).

지원 포맷:
- **PNG**: ``tEXt`` 청크의 ``parameters`` (WebUI) / ``workflow`` / ``prompt`` (ComfyUI)
- **JPEG**: EXIF ``UserComment`` (WebUI 호환), ``ImageDescription``
- **WebP**: EXIF/XMP (PIL이 PNG 텍스트 청크와 비슷하게 노출)

목적:
1. 추출 — 이미지에서 생성 파라미터를 dict로
2. 이식 — 한 이미지의 메타를 다른 이미지에 복사 (편집 후 원본 보존용)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Union

from utils.app_logger import get_logger

_logger = get_logger("image_metadata")


class MetadataSource:
    WEBUI = "webui"
    COMFYUI = "comfyui"
    UNKNOWN = "unknown"


@dataclass
class ImageMetadata:
    """추출된 생성 메타.

    포맷 간 차이를 흡수하는 정규화된 표현.
    원본 raw 텍스트도 ``raw_parameters`` / ``raw_workflow``에 보존.
    """
    source: str = MetadataSource.UNKNOWN

    # 정규화된 필드 — WebUI Parameters 파싱 결과
    prompt: str = ""
    negative_prompt: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)  # steps, cfg, sampler 등

    # ComfyUI 원본
    workflow: Optional[dict] = None  # ComfyUI workflow JSON (graph format)
    prompt_graph: Optional[dict] = None  # ComfyUI prompt JSON (API format)

    # 보존용 원본
    raw_parameters: str = ""  # WebUI Parameters 텍스트 그대로
    raw_workflow: str = ""    # ComfyUI workflow JSON 그대로
    raw_prompt: str = ""      # ComfyUI prompt JSON 그대로

    def has_any(self) -> bool:
        return bool(
            self.prompt or self.negative_prompt or self.parameters
            or self.workflow or self.prompt_graph
        )

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "parameters": dict(self.parameters),
            "has_workflow": self.workflow is not None,
            "has_prompt_graph": self.prompt_graph is not None,
            "raw_parameters": self.raw_parameters,
        }


# ─────────────────────────────────────────────
# 추출
# ─────────────────────────────────────────────

def extract_from_file(path: Union[str, Path]) -> ImageMetadata:
    """파일에서 메타데이터 추출. 실패해도 빈 ``ImageMetadata`` 반환."""
    p = Path(path)
    if not p.is_file():
        return ImageMetadata()
    try:
        from PIL import Image
        with Image.open(p) as img:
            return extract_from_pil(img)
    except Exception:
        _logger.exception(f"메타 추출 실패: {p}")
        return ImageMetadata()


def extract_from_bytes(data: bytes) -> ImageMetadata:
    """바이트에서 추출."""
    try:
        from PIL import Image
        with Image.open(BytesIO(data)) as img:
            return extract_from_pil(img)
    except Exception:
        _logger.exception("메타 추출 실패 (bytes)")
        return ImageMetadata()


def extract_from_pil(img) -> ImageMetadata:
    """PIL Image 객체에서 추출."""
    meta = ImageMetadata()

    # 1) PNG tEXt / iTXt
    if hasattr(img, "info") and img.info:
        raw_info = img.info

        # WebUI: "parameters" 키
        if "parameters" in raw_info:
            meta.raw_parameters = str(raw_info["parameters"])
            meta.source = MetadataSource.WEBUI
            _parse_webui_parameters(meta.raw_parameters, meta)

        # ComfyUI: "workflow" (graph) / "prompt" (API)
        if "workflow" in raw_info:
            meta.raw_workflow = str(raw_info["workflow"])
            try:
                meta.workflow = json.loads(meta.raw_workflow)
                if meta.source == MetadataSource.UNKNOWN:
                    meta.source = MetadataSource.COMFYUI
            except json.JSONDecodeError:
                pass

        if "prompt" in raw_info and meta.source != MetadataSource.WEBUI:
            # WebUI의 prompt 키와 충돌 — WebUI 우선
            meta.raw_prompt = str(raw_info["prompt"])
            try:
                meta.prompt_graph = json.loads(meta.raw_prompt)
                if meta.source == MetadataSource.UNKNOWN:
                    meta.source = MetadataSource.COMFYUI
            except json.JSONDecodeError:
                pass

    # 2) JPEG/WebP — EXIF UserComment
    if meta.source == MetadataSource.UNKNOWN:
        comment = _read_exif_user_comment(img)
        if comment:
            meta.raw_parameters = comment
            meta.source = MetadataSource.WEBUI
            _parse_webui_parameters(comment, meta)

    return meta


def _read_exif_user_comment(img) -> str:
    """EXIF UserComment(0x9286) 또는 ImageDescription(0x010E) 읽기."""
    try:
        exif = img.getexif() if hasattr(img, "getexif") else None
        if not exif:
            return ""
        # UserComment
        v = exif.get(0x9286)
        if isinstance(v, (bytes, bytearray)):
            # WebUI는 보통 UTF-16/UTF-8 prefix 후 텍스트
            try:
                if v[:8] == b"UNICODE\0":
                    return v[8:].decode("utf-16-be", errors="replace").rstrip("\x00")
                if v[:8] == b"ASCII\0\0\0":
                    return v[8:].decode("ascii", errors="replace").rstrip("\x00")
                return v.decode("utf-8", errors="replace").rstrip("\x00")
            except Exception:
                return ""
        if isinstance(v, str):
            return v
        # ImageDescription
        d = exif.get(0x010E)
        if isinstance(d, str):
            return d
    except Exception:
        pass
    return ""


# WebUI Parameters 형식:
# <positive prompt>
# Negative prompt: <negative>
# Steps: 20, Sampler: Euler, CFG scale: 7, Seed: 12345, Size: 512x768, ...
_NEG_RE = re.compile(r"\nNegative prompt:\s*", re.IGNORECASE)
_PARAM_TAIL_RE = re.compile(
    r"\n(?=(?:Steps|Sampler|CFG scale|Seed|Size|Model|Denoising strength|Schedule type|Version|Clip skip):)",
    re.IGNORECASE,
)


def _parse_webui_parameters(text: str, meta: ImageMetadata) -> None:
    """WebUI ``parameters`` 텍스트 파싱."""
    if not text:
        return
    body = text.replace("\r\n", "\n")

    # Negative prompt 분리
    neg_split = _NEG_RE.split(body, maxsplit=1)
    if len(neg_split) == 2:
        positive_text = neg_split[0].strip()
        rest = neg_split[1]
    else:
        positive_text = body
        rest = ""

    # 파라미터 라인 분리 (Steps: ... 가 처음 등장하는 위치)
    if rest:
        tail_split = _PARAM_TAIL_RE.split(rest, maxsplit=1)
        if len(tail_split) == 2:
            negative_text = tail_split[0].strip()
            param_text = tail_split[1].strip()
        else:
            negative_text = rest.strip()
            param_text = ""
    else:
        # rest 없을 때: positive 안에 Steps: 라인이 있을 수도
        tail_split = _PARAM_TAIL_RE.split(positive_text, maxsplit=1)
        if len(tail_split) == 2:
            positive_text = tail_split[0].strip()
            param_text = tail_split[1].strip()
        else:
            param_text = ""
        negative_text = ""

    meta.prompt = positive_text
    meta.negative_prompt = negative_text
    meta.parameters = _parse_param_line(param_text) if param_text else {}


def _parse_param_line(text: str) -> dict[str, Any]:
    """``Steps: 20, Sampler: Euler, ...`` 파싱.

    값 안에 쉼표가 있으면 따옴표로 감싸진 케이스 처리.
    """
    result: dict[str, Any] = {}
    # 단순 split — WebUI 포맷은 보통 안 따옴표 안 쓰지만 lora 해시 같은 경우 있음
    # 정규식: KEY: VALUE 패턴, VALUE는 다음 ", KEY:" 전까지
    tokens = re.findall(r'([A-Za-z][\w \-/]+):\s*("(?:[^"\\]|\\.)*"|[^,\n]+)', text)
    for k, v in tokens:
        key = k.strip()
        value = v.strip().strip('"')
        # 숫자 변환 시도
        if re.match(r"^-?\d+$", value):
            result[key] = int(value)
        elif re.match(r"^-?\d*\.\d+$", value):
            result[key] = float(value)
        else:
            result[key] = value
    return result


# ─────────────────────────────────────────────
# 이식
# ─────────────────────────────────────────────

def transplant(src: Union[str, Path],
               dst: Union[str, Path],
               out: Union[str, Path],
               include_workflow: bool = True) -> bool:
    """``src`` 이미지의 메타를 추출해서 ``dst`` 이미지에 이식 → ``out``에 저장.

    PNG로 저장 (원본 dst 포맷 무관 — 메타 손실 없도록).

    :param include_workflow: ComfyUI workflow/prompt 그래프까지 복사할지
    """
    meta = extract_from_file(src)
    if not meta.has_any():
        _logger.warning(f"이식 실패: src에 메타 없음: {src}")
        return False
    return embed_to_file(dst, meta, out, include_workflow=include_workflow)


def embed_to_file(src_image: Union[str, Path],
                  meta: ImageMetadata,
                  out: Union[str, Path],
                  include_workflow: bool = True) -> bool:
    """이미지에 메타를 박아 ``out``에 PNG로 저장."""
    try:
        from PIL import Image, PngImagePlugin
        with Image.open(src_image) as img:
            img_copy = img.convert("RGBA" if img.mode in ("RGBA", "LA") else "RGB")

        pnginfo = PngImagePlugin.PngInfo()

        # WebUI parameters
        params_text = meta.raw_parameters or _format_parameters(meta)
        if params_text:
            pnginfo.add_text("parameters", params_text)

        # ComfyUI workflow / prompt
        if include_workflow:
            if meta.raw_workflow:
                pnginfo.add_text("workflow", meta.raw_workflow)
            elif meta.workflow is not None:
                pnginfo.add_text("workflow", json.dumps(meta.workflow, ensure_ascii=False))
            if meta.raw_prompt:
                pnginfo.add_text("prompt", meta.raw_prompt)
            elif meta.prompt_graph is not None:
                pnginfo.add_text("prompt", json.dumps(meta.prompt_graph, ensure_ascii=False))

        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img_copy.save(out_path, format="PNG", pnginfo=pnginfo)
        return True
    except Exception:
        _logger.exception(f"메타 이식 실패: {out}")
        return False


def _format_parameters(meta: ImageMetadata) -> str:
    """raw_parameters가 없을 때 정규화 필드로 WebUI 형식 재구성."""
    if not (meta.prompt or meta.negative_prompt or meta.parameters):
        return ""
    parts: list[str] = []
    parts.append(meta.prompt)
    if meta.negative_prompt:
        parts.append(f"Negative prompt: {meta.negative_prompt}")
    if meta.parameters:
        kv = ", ".join(f"{k}: {v}" for k, v in meta.parameters.items())
        parts.append(kv)
    return "\n".join(parts)

"""Local-only, non-destructive adapter for the experimental relight node.

No input paths, URLs, models, GPU allocations or network access are accepted.
The one cached result may only be exported by its exact preview request ID.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import threading
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageOps, PngImagePlugin

from comfy_custom_nodes.ai_studio_forge_parity.relight import relight_image, settings_from

MAX_PIXELS = 16_777_216
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_REQUEST_CHARS = 128 * 1024 * 1024
_DATA_URL = re.compile(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def decode_relight_image(value, label, *, shape=None, normal=False):
    if not isinstance(value, str) or len(value) > (MAX_FILE_BYTES * 4 // 3 + 128):
        raise ValueError(f"{label}: 64 MB 이하의 PNG/JPEG/WebP data URL이 필요합니다.")
    match = _DATA_URL.fullmatch(value)
    if not match:
        raise ValueError(f"{label}: 로컬 파일을 업로드하세요. 경로나 외부 URL은 허용하지 않습니다.")
    try:
        data = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{label}: 올바르지 않은 base64 이미지입니다.") from exc
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"{label}: 이미지 파일이 64 MB를 넘습니다.")
    with Image.open(io.BytesIO(data)) as opened:
        if opened.format not in {"PNG", "JPEG", "WEBP"} or getattr(opened, "n_frames", 1) != 1:
            raise ValueError(f"{label}: 정지 PNG/JPEG/WebP만 사용할 수 있습니다.")
        width, height = opened.size
        if min(width, height) < 2 or width * height > MAX_PIXELS:
            raise ValueError(f"{label}: 최소 2×2, 최대 16 MP 이미지를 사용하세요.")
        if normal and opened.mode not in {"RGB", "RGBA"}:
            raise ValueError("노멀: RGB로 XYZ가 인코딩된 맵이 필요합니다.")
        metadata = {}
        size = 0
        for key, text in opened.info.items():
            if isinstance(key, str) and isinstance(text, str) and len(key) <= 100:
                size += len(text.encode("utf-8"))
                if size <= 1024 * 1024:
                    metadata[key] = text
        icc = opened.info.get("icc_profile")
        if not isinstance(icc, bytes) or len(icc) > 1024 * 1024 or opened.mode not in {"RGB", "RGBA", "P"}:
            icc = None
        image = ImageOps.exif_transpose(opened)
        if shape is not None and image.size != shape:
            raise ValueError(f"{label}: 원본과 같은 해상도 {shape[0]}×{shape[1]} 맵을 사용하세요. 자동 리사이즈하지 않습니다.")
        # Preserve source transparency, including indexed PNG transparency.
        mode = "RGBA" if "A" in image.getbands() or "transparency" in opened.info else "RGB"
        pixels = np.asarray(image.convert(mode), dtype=np.float32) / 255.
        exif = image.getexif().tobytes() if image.getexif() else None
    return pixels, {"text": metadata, "icc": icc, "exif": exif, "sha256": hashlib.sha256(data).hexdigest()}


def encode_relight_png(pixels, *, metadata=None, diagnostic=False):
    image = Image.fromarray(np.rint(np.clip(pixels, 0, 1) * 255).astype(np.uint8))
    if diagnostic:
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    options = {}
    if metadata:
        info = PngImagePlugin.PngInfo()
        for key, value in metadata.get("text", {}).items():
            info.add_text(key, value)
        options["pnginfo"] = info
        for key in ("icc", "exif"):
            if metadata.get(key):
                options["icc_profile" if key == "icc" else key] = metadata[key]
    out = io.BytesIO()
    image.save(out, format="PNG", **options)
    return out.getvalue()


def png_data_url(data):
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def render_relight_preview(request):
    values = [request.get(key, "") for key in ("image", "depth", "normals", "mask")]
    if any(not isinstance(value, str) for value in values) or sum(map(len, values)) > MAX_REQUEST_CHARS:
        raise ValueError("이미지·맵의 총 전송 크기는 128 MB 이하로 제한됩니다.")
    settings = settings_from(request.get("settings"))
    image, metadata = decode_relight_image(values[0], "원본")
    shape = (image.shape[1], image.shape[0])
    maps = {}
    for key, label, value in zip(("depth", "normals", "mask"), ("깊이", "노멀", "마스크"), values[1:]):
        if value:
            pixels, _ = decode_relight_image(value, label, shape=shape, normal=key == "normals")
            maps[key] = pixels if key == "normals" else pixels[..., 0]
    result = relight_image(image, settings=settings, **maps)
    provenance = {
        "tool": "AI Studio Pro experimental relight", "version": 1,
        "source_sha256": metadata["sha256"], "settings": settings,
        "geometry": result["geometry"],
        "cast_shadows": bool("depth" in maps and settings["shadow_strength"] > 0 and settings["shadow_length"] > 0),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    metadata["text"]["ai_studio_relight"] = json.dumps(provenance, ensure_ascii=False)
    png = encode_relight_png(result["image"], metadata=metadata)
    diagnostics = {key: png_data_url(encode_relight_png(result[key], diagnostic=True))
                   for key in ("light", "normals", "shadow")}
    return {"png": png, "width": shape[0], "height": shape[1], "geometry": result["geometry"],
            "diagnostics": diagnostics, "sourceSha256": metadata["sha256"]}


def export_relight_png(data, output_root):
    root = Path(output_root).resolve()
    destination = root / "relight"
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    if not destination.is_relative_to(root):
        raise ValueError("조명 결과 폴더가 앱 출력 폴더 밖을 가리킵니다.")
    # Explicit O_EXCL creation: no original or previous export can be replaced.
    for _ in range(5):
        path = destination / f"relight_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(6)}.png"
        try:
            with path.open("xb") as stream:
                try:
                    stream.write(data)
                except Exception:
                    stream.close()
                    path.unlink(missing_ok=True)  # Only this newly-created partial export.
                    raise
            return str(path)
        except FileExistsError:
            continue
    raise ValueError("새 결과 파일 이름을 만들지 못했습니다. 다시 저장하세요.")


class RelightActionsMixin:
    def _relight_emit(self, event):
        if getattr(self, "_relight_closed", False):
            return
        signal = getattr(getattr(self, "vue_bridge", None), "relightEvent", None)
        if signal is not None:
            try:
                signal.emit(json.dumps(event, ensure_ascii=False))
            except RuntimeError:
                pass  # The Qt bridge may have been destroyed while CPU work ended.

    def _relight_error(self, event, exc):
        from core.error_handler import handle_error, sanitize_for_ui
        handle_error("E040", "실험 조명 편집", exc, notify=False)
        self._relight_emit({**event, "ok": False, "error": sanitize_for_ui(str(exc), 600)})

    def _ensure_relight_runtime(self):
        if not hasattr(self, "_relight_lock"):
            self._relight_lock = threading.RLock()
            self._relight_job = None
            self._relight_preview = None

    def _handle_relight_action(self, action, payload):
        if action in ("relight_preview", "relight_export", "relight_cancel"):
            return self._run_relight_action(action, payload)
        return False

    def _shutdown_relight(self):
        self._ensure_relight_runtime()
        with self._relight_lock:
            self._relight_closed = True
            self._relight_preview = None
            if self._relight_job:
                self._relight_job["cancel"].set()

    def _run_relight_action(self, action, payload):
        if getattr(self, "_relight_closed", False):
            return True
        request = dict(payload) if isinstance(payload, dict) else {}
        request_id = request.get("requestId", "")
        event = {"requestId": request_id if isinstance(request_id, str) else "", "action": action, "ok": False}
        try:
            if getattr(self, "web_mode", False):
                raise ValueError("실험 조명 편집은 로컬 앱에서만 사용할 수 있습니다.")
            if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
                raise ValueError("작업 식별자가 올바르지 않습니다. 패널을 다시 열어 주세요.")
            self._ensure_relight_runtime()
            with self._relight_lock:
                if action == "relight_cancel":
                    if self._relight_job and self._relight_job["requestId"] == request_id:
                        self._relight_job["cancel"].set()
                    if self._relight_preview and self._relight_preview["requestId"] == request_id:
                        self._relight_preview = None
                    self._relight_emit({**event, "ok": True, "canceled": True})
                    return True
                if self._relight_job:
                    if self._relight_job["requestId"] == request_id:
                        return True  # Idempotent transport redelivery, not a second CPU job.
                    raise ValueError("조명 작업 하나가 실행 중입니다. 완료된 뒤 다시 시도하세요.")
                if action == "relight_export":
                    cached = self._relight_preview
                    if not cached or cached["requestId"] != request.get("previewRequestId"):
                        raise ValueError("이 미리보기는 더 이상 유효하지 않습니다. 다시 미리보기를 만드세요.")
                    cached_png = cached["png"]
                    from config import OUTPUT_DIR
                    output_root = OUTPUT_DIR
                else:
                    self._relight_preview = None
                    cached_png = output_root = None
                job = {"requestId": request_id, "cancel": threading.Event()}
                self._relight_job = job
        except Exception as exc:
            self._relight_error(event, exc)
            return True

        def work():
            try:
                if job["cancel"].is_set():
                    with self._relight_lock:
                        if self._relight_job is job:
                            self._relight_job = None
                    self._relight_emit({**event, "canceled": True, "error": "조명 작업을 취소했습니다."})
                    return
                if action == "relight_preview":
                    result = render_relight_preview(request)
                    output = {**event, "ok": True, "image": png_data_url(result["png"]),
                              **{key: value for key, value in result.items() if key != "png"}}
                    with self._relight_lock:
                        if job["cancel"].is_set() or getattr(self, "_relight_closed", False):
                            if self._relight_job is job:
                                self._relight_job = None
                            self._relight_emit({**event, "canceled": True, "error": "변경된 입력의 이전 미리보기를 폐기했습니다."})
                            return
                        self._relight_preview = {"requestId": request_id, "png": result["png"]}
                        self._relight_job = None
                        self._relight_emit(output)
                elif not job["cancel"].is_set():
                    path = export_relight_png(cached_png, output_root)
                    with self._relight_lock:
                        self._relight_job = None
                        self._relight_emit({**event, "ok": True, "path": path})
            except Exception as exc:
                with self._relight_lock:
                    if self._relight_job is job:
                        self._relight_job = None
                self._relight_error(event, exc)
            finally:
                with self._relight_lock:
                    if self._relight_job is job:
                        self._relight_job = None

        try:
            thread = threading.Thread(target=work, daemon=True, name="ai-studio-relight")
            thread.start()
        except Exception as exc:
            with self._relight_lock:
                self._relight_job = None
            self._relight_error(event, exc)
        return True

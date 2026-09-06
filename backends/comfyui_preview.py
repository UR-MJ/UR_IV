"""Bounded, prompt-scoped decoding of ComfyUI WebSocket preview frames.

The wire formats are documented by ComfyUI's ``server.py`` / ``protocol.py``:
event 1 has a uint32 image type; event 4 has uint32 JSON length + metadata.
This client implementation does not execute image metadata or fetch URLs.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import struct
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from PIL import Image


MAX_PREVIEW_BYTES = 16 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_PREVIEW_PIXELS = 4096 * 4096
_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


@dataclass(frozen=True)
class PreviewFrame:
    image: bytes
    mime: str
    prompt_id: str | None = None


def decode_preview(frame: bytes) -> PreviewFrame | None:
    """Reject unknown, oversized, malformed or mislabeled image frames."""
    if not isinstance(frame, bytes) or not 8 < len(frame) <= MAX_PREVIEW_BYTES + MAX_METADATA_BYTES + 8:
        return None
    event, discriminator = struct.unpack_from(">II", frame)
    prompt_id = None
    if event == 1:
        mime = {1: "image/jpeg", 2: "image/png"}.get(discriminator)
        image = frame[8:]
    elif event == 4:
        if not 0 < discriminator <= MAX_METADATA_BYTES or 8 + discriminator >= len(frame):
            return None
        try:
            metadata = json.loads(frame[8:8 + discriminator])
        except (ValueError, UnicodeDecodeError, RecursionError):
            return None
        if not isinstance(metadata, dict):
            return None
        mime = metadata.get("image_type")
        # A present-but-invalid identity must never become an anonymous frame.
        if "prompt_id" in metadata:
            prompt_id = metadata["prompt_id"]
            if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 256:
                return None
        image = frame[8 + discriminator:]
    else:
        return None
    if not isinstance(mime, str) or mime not in _FORMATS or not 0 < len(image) <= MAX_PREVIEW_BYTES:
        return None
    signature_ok = (
        mime == "image/png" and image.startswith(b"\x89PNG\r\n\x1a\n")
        or mime == "image/jpeg" and image.startswith(b"\xff\xd8\xff") and image.endswith(b"\xff\xd9")
        or mime == "image/webp" and image.startswith(b"RIFF") and image[8:12] == b"WEBP"
    )
    if not signature_ok:
        return None
    try:
        with Image.open(io.BytesIO(image)) as decoded:
            width, height = decoded.size
            if decoded.format != _FORMATS[mime] or width <= 0 or height <= 0 or width * height > MAX_PREVIEW_PIXELS:
                return None
            if getattr(decoded, "n_frames", 1) != 1:
                return None
            decoded.verify()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None
    return PreviewFrame(image, mime, prompt_id)


class PreviewStream:
    """Expose raw base64 strings at most four times a second for one job.

    Legacy event-1 frames carry no job identity. They are accepted only after
    this request's execution has been observed on its unique client socket.
    A foreign execution suspends anonymous frames until our job resumes. Event
    4 is additionally checked against its embedded prompt ID. Nonstandard
    nodes broadcasting anonymous images cannot provide absolute attribution;
    prefer the negotiated metadata protocol whenever the server supports it.
    """

    def __init__(self, prompt_id: str, *, interval: float = 0.25,
                 clock: Callable[[], float] = time.monotonic):
        self.prompt_id = prompt_id
        self._interval = max(0.0, interval)
        self._clock = clock
        self._active = False
        self._finished = False
        self._last_emit = float("-inf")
        self._last_digest = None

    def observe(self, message: Mapping) -> None:
        data = message.get("data")
        if not isinstance(data, Mapping):
            return
        event = message.get("type")
        identity = data.get("prompt_id")
        if identity and identity != self.prompt_id:
            if event in {"execution_start", "executing", "progress", "progress_state"}:
                self._active = False
            return
        if event in {"execution_error", "execution_interrupted", "execution_success"} or (
            event == "executing" and "node" in data and data["node"] is None
        ):
            if identity == self.prompt_id or self._active:
                self._active = False
                self._finished = True
        elif identity == self.prompt_id and event in {"execution_start", "executing", "progress", "progress_state"}:
            self._active = True

    def consume(self, frame: bytes) -> str | None:
        if self._finished:
            return None
        now = self._clock()
        if now - self._last_emit < self._interval:
            return None
        decoded = decode_preview(frame)
        if decoded is None:
            return None
        if decoded.prompt_id is not None:
            if decoded.prompt_id != self.prompt_id:
                return None
        elif not self._active:
            return None
        digest = hashlib.sha256(decoded.image).digest()
        if digest == self._last_digest:
            return None
        self._last_digest = digest
        self._last_emit = now
        # Keep the established Forge -> worker -> generationPreview contract.
        return base64.b64encode(decoded.image).decode("ascii")

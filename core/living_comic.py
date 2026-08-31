"""Render animated comic pages from one to six panel clips.

The public :func:`render_living_comic` function deliberately hides codec,
layout, looping, compositing, cancellation, and atomic-output details from the
Qt/Vue controller.  Pillow owns page composition while PyAV is loaded lazily
only when an export is actually requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
import math
import os
import re
import uuid


PAGE_SIZE = (1400, 2100)
MAX_PANELS = 6
MIN_FPS = 1
MAX_FPS = 24
MIN_SECONDS = 0.25
MAX_SECONDS = 15.0
MAX_OUTPUT_FRAMES = 240
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".gif"}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VALID_LAYOUTS = {"auto", "grid", "vertical", "horizontal", "hero", "strip", "focus"}


class LivingComicError(RuntimeError):
    """Base error shown to the Creator UI."""


class LivingComicDependencyError(LivingComicError):
    """Raised when an optional runtime dependency is unavailable."""


class LivingComicCancelled(LivingComicError):
    """Raised when the caller cancels an in-progress export."""


@dataclass(frozen=True)
class PanelBox:
    """One panel rectangle in page pixels."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class BubbleSpec:
    text: str
    kind: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class PanelSpec:
    source_path: Path
    is_video: bool
    bubbles: tuple[BubbleSpec, ...]


@dataclass(frozen=True)
class LivingDocument:
    title: str
    layout: str
    panels: tuple[PanelSpec, ...]
    width: int = PAGE_SIZE[0]
    height: int = PAGE_SIZE[1]


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise LivingComicError(f"{name} 값이 올바르지 않습니다") from exc
    if not minimum <= parsed <= maximum:
        raise LivingComicError(f"{name} 값은 {minimum}~{maximum} 범위여야 합니다")
    return parsed


def _bounded_float(value: Any, name: str, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise LivingComicError(f"{name} 값이 올바르지 않습니다") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise LivingComicError(f"{name} 값은 {minimum:g}~{maximum:g} 범위여야 합니다")
    return parsed


def _fraction(value: Any, default: float, minimum: float, maximum: float) -> float:
    """Accept both Vue's 0..1 coordinates and legacy 0..100 percentages."""

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if abs(parsed) > 1.0:
        parsed /= 100.0
    return min(maximum, max(minimum, parsed))


def _safe_title(value: Any) -> str:
    title = str(value or "Living Comic").strip()[:160] or "Living Comic"
    return re.sub(r"[\x00-\x1f]", "", title)


def _bubble_from_raw(raw: Mapping[str, Any]) -> BubbleSpec:
    kind = str(raw.get("kind", raw.get("style", "speech"))).strip().lower()
    if kind not in {"speech", "thought", "narration"}:
        kind = "speech"
    return BubbleSpec(
        text=str(raw.get("text", "")).strip()[:800],
        kind=kind,
        x=_fraction(raw.get("x"), 0.08, 0.0, 0.95),
        y=_fraction(raw.get("y"), 0.08, 0.0, 0.95),
        width=_fraction(raw.get("width"), 0.38, 0.08, 0.90),
        height=_fraction(raw.get("height"), 0.18, 0.05, 0.80),
    )


def normalize_living_document(document: Mapping[str, Any]) -> LivingDocument:
    """Validate and normalize a frontend/canonical Comic document.

    Every panel needs either ``videoPath``/``video_path`` or an image path.  An
    image becomes a still animated panel, making partial storyboards exportable
    while preserving strict file validation.
    """

    if not isinstance(document, Mapping):
        raise LivingComicError("Living Comic 문서는 객체여야 합니다")
    raw_panels = document.get("panels")
    if not isinstance(raw_panels, Sequence) or isinstance(raw_panels, (str, bytes)):
        raise LivingComicError("Living Comic 문서에 panels 배열이 필요합니다")
    if not 1 <= len(raw_panels) <= MAX_PANELS:
        raise LivingComicError("Living Comic은 1~6개의 컷을 지원합니다")

    flattened: dict[int, list[Mapping[str, Any]]] = {index: [] for index in range(len(raw_panels))}
    raw_flat_bubbles = document.get("bubbles", [])
    if isinstance(raw_flat_bubbles, Sequence) and not isinstance(raw_flat_bubbles, (str, bytes)):
        for raw in raw_flat_bubbles:
            if not isinstance(raw, Mapping):
                continue
            try:
                panel_index = int(raw.get("panelIndex", raw.get("panel_index", 0)))
            except (TypeError, ValueError):
                panel_index = 0
            if 0 <= panel_index < len(raw_panels):
                flattened[panel_index].append(raw)

    panels: list[PanelSpec] = []
    for index, raw_panel in enumerate(raw_panels):
        if not isinstance(raw_panel, Mapping):
            raise LivingComicError(f"컷 {index + 1} 데이터가 올바르지 않습니다")
        raw_path = (
            raw_panel.get("videoPath")
            or raw_panel.get("video_path")
            or raw_panel.get("imagePath")
            or raw_panel.get("image_path")
        )
        if not str(raw_path or "").strip():
            raise LivingComicError(f"컷 {index + 1}에 영상 또는 이미지가 없습니다")
        try:
            path = Path(str(raw_path)).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise LivingComicError(f"컷 {index + 1} 미디어를 찾을 수 없습니다: {raw_path}") from exc
        if not path.is_file():
            raise LivingComicError(f"컷 {index + 1} 미디어가 파일이 아닙니다: {path}")
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_VIDEO_SUFFIXES | SUPPORTED_IMAGE_SUFFIXES:
            raise LivingComicError(f"컷 {index + 1}에서 지원하지 않는 미디어 형식입니다: {suffix}")

        raw_nested = raw_panel.get("bubbles", [])
        candidates: list[Mapping[str, Any]] = []
        if isinstance(raw_nested, Sequence) and not isinstance(raw_nested, (str, bytes)):
            candidates.extend(item for item in raw_nested if isinstance(item, Mapping))
        # Canonical documents contain both nested and flattened representations.
        # Prefer nested bubbles and only fall back to flattened ones.
        if not candidates:
            candidates.extend(flattened[index])
        seen: set[str] = set()
        bubbles: list[BubbleSpec] = []
        for raw_bubble in candidates:
            bubble_id = str(raw_bubble.get("id", ""))
            if bubble_id and bubble_id in seen:
                continue
            if bubble_id:
                seen.add(bubble_id)
            bubble = _bubble_from_raw(raw_bubble)
            if bubble.text:
                bubbles.append(bubble)

        panels.append(
            PanelSpec(
                source_path=path,
                is_video=suffix in SUPPORTED_VIDEO_SUFFIXES,
                bubbles=tuple(bubbles),
            )
        )

    layout = str(document.get("layout", "auto") or "auto").strip().lower()
    if layout not in VALID_LAYOUTS:
        layout = "auto"
    if layout == "strip":
        layout = "vertical"
    elif layout == "focus":
        layout = "hero"

    # Export dimensions stay fixed so the viewer has one stable page contract.
    return LivingDocument(
        title=_safe_title(document.get("title")),
        layout=layout,
        panels=tuple(panels),
    )


def _grid_boxes(
    count: int,
    columns: int,
    page_size: tuple[int, int],
    margin: int,
    gap: int,
    *,
    top: int | None = None,
    available_height: int | None = None,
) -> list[PanelBox]:
    page_width, page_height = page_size
    columns = max(1, min(count, columns))
    rows = math.ceil(count / columns)
    origin_y = margin if top is None else top
    usable_height = page_height - (2 * margin) if available_height is None else available_height
    cell_width = (page_width - (2 * margin) - (columns - 1) * gap) // columns
    cell_height = (usable_height - (rows - 1) * gap) // rows
    boxes = []
    for index in range(count):
        row, column = divmod(index, columns)
        boxes.append(
            PanelBox(
                margin + column * (cell_width + gap),
                origin_y + row * (cell_height + gap),
                cell_width,
                cell_height,
            )
        )
    return boxes


def compute_panel_boxes(
    panel_count: int,
    layout: str = "auto",
    page_size: tuple[int, int] = PAGE_SIZE,
    *,
    margin: int = 32,
    gap: int = 24,
) -> list[PanelBox]:
    """Return non-overlapping page rectangles for all supported layouts."""

    panel_count = _bounded_int(panel_count, "컷 수", 1, MAX_PANELS)
    page_width = _bounded_int(page_size[0], "페이지 너비", 320, 8192)
    page_height = _bounded_int(page_size[1], "페이지 높이", 320, 8192)
    if margin < 0 or gap < 0 or page_width <= 2 * margin or page_height <= 2 * margin:
        raise LivingComicError("페이지 여백 설정이 올바르지 않습니다")
    page_size = (page_width, page_height)
    layout = str(layout or "auto").lower()
    if layout == "strip":
        layout = "vertical"
    elif layout == "focus":
        layout = "hero"
    if layout not in {"auto", "grid", "vertical", "horizontal", "hero"}:
        layout = "auto"

    if layout == "auto":
        if panel_count == 1:
            layout = "hero"
        elif panel_count == 2:
            layout = "vertical"
        elif panel_count in {3, 5}:
            layout = "hero"
        else:
            layout = "grid"

    if layout == "vertical":
        return _grid_boxes(panel_count, 1, page_size, margin, gap)
    if layout == "horizontal":
        return _grid_boxes(panel_count, panel_count, page_size, margin, gap)
    if layout == "grid":
        columns = 2 if panel_count <= 4 else 3
        return _grid_boxes(panel_count, columns, page_size, margin, gap)

    # Hero: one wide lead panel with the remaining panels in a compact grid.
    if panel_count == 1:
        return [PanelBox(margin, margin, page_width - 2 * margin, page_height - 2 * margin)]
    hero_height = int((page_height - 2 * margin - gap) * 0.55)
    boxes = [PanelBox(margin, margin, page_width - 2 * margin, hero_height)]
    remainder_height = page_height - margin - (margin + hero_height + gap)
    remainder_count = panel_count - 1
    columns = 2 if remainder_count <= 4 else 3
    boxes.extend(
        _grid_boxes(
            remainder_count,
            columns,
            page_size,
            margin,
            gap,
            top=margin + hero_height + gap,
            available_height=remainder_height,
        )
    )
    return boxes


def cycle_frame_index(output_index: int, source_frame_count: int) -> int:
    """Map any non-negative output frame to a safely looping source index."""

    output_index = _bounded_int(output_index, "출력 프레임", 0, 2**31 - 1)
    source_frame_count = _bounded_int(source_frame_count, "소스 프레임 수", 1, 2**31 - 1)
    return output_index % source_frame_count


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError as exc:  # pragma: no cover - Pillow is a base dependency
        raise LivingComicDependencyError(
            "Living Comic 내보내기에는 Pillow가 필요합니다: pip install Pillow"
        ) from exc
    return Image, ImageDraw, ImageFont, ImageOps


def _load_av():
    try:
        import av
    except ImportError as exc:
        raise LivingComicDependencyError(
            "Living Comic MP4 내보내기에는 PyAV가 필요합니다: pip install av"
        ) from exc
    return av


class _StillSource:
    def __init__(self, path: Path, image_module: Any) -> None:
        try:
            with image_module.open(path) as source:
                self._image = source.convert("RGB").copy()
        except Exception as exc:
            raise LivingComicError(f"이미지를 읽을 수 없습니다: {path}") from exc

    def next_image(self, _output_fps: int):
        return self._image.copy()

    def close(self) -> None:
        self._image.close()


class _LoopingVideoSource:
    """Constant-memory decoder that reopens a clip whenever it reaches EOF."""

    def __init__(self, path: Path, av_module: Any) -> None:
        self.path = path
        self.av = av_module
        self.container = None
        self.stream = None
        self.decoder: Optional[Iterable[Any]] = None
        self.current = None
        self.accumulator = 0.0
        self.source_fps = 0.0
        self._open()

    def _open(self) -> None:
        self.close()
        try:
            self.container = self.av.open(str(self.path), mode="r")
            if not self.container.streams.video:
                raise LivingComicError(f"영상 스트림이 없습니다: {self.path}")
            self.stream = self.container.streams.video[0]
            try:
                self.source_fps = float(self.stream.average_rate or self.stream.base_rate or 0)
            except (TypeError, ValueError, ZeroDivisionError):
                self.source_fps = 0.0
            self.decoder = iter(self.container.decode(self.stream))
        except LivingComicError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise LivingComicError(f"영상을 열 수 없습니다: {self.path}") from exc

    def _decode_one(self):
        assert self.decoder is not None
        try:
            return next(self.decoder)
        except StopIteration:
            self._open()
            assert self.decoder is not None
            try:
                return next(self.decoder)
            except StopIteration as exc:
                raise LivingComicError(f"영상에 디코딩 가능한 프레임이 없습니다: {self.path}") from exc
        except Exception as exc:
            raise LivingComicError(f"영상 프레임을 읽을 수 없습니다: {self.path}") from exc

    def next_image(self, output_fps: int):
        if self.current is None:
            self.current = self._decode_one()
        result = self.current.to_image().convert("RGB")

        ratio = self.source_fps / max(1, output_fps) if self.source_fps > 0 else 1.0
        self.accumulator += ratio
        advances = int(self.accumulator)
        self.accumulator -= advances
        # Low-frame-rate sources deliberately duplicate frames; high-frame-rate
        # sources skip enough decoded frames to preserve approximate playback speed.
        for _ in range(advances):
            self.current = self._decode_one()
        return result

    def close(self) -> None:
        decoder, container = self.decoder, self.container
        self.decoder = None
        self.stream = None
        self.container = None
        self.current = None
        if decoder is not None:
            close = getattr(decoder, "close", None)
            if callable(close):
                close()
        if container is not None:
            try:
                container.close()
            except Exception:
                pass


def _font(image_font: Any, size: int, bold: bool = False):
    candidates = (
        ("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
        ("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        "DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return image_font.truetype(candidate, size=size)
        except (OSError, ValueError):
            continue
    return image_font.load_default()


def _wrap_text(draw: Any, text: str, font: Any, max_width: int, max_lines: int) -> list[str]:
    words = list(text) if " " not in text else text.split()
    separator = "" if " " not in text else " "
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current}{separator if current else ''}{word}"
        box = draw.textbbox((0, 0), candidate, font=font)
        if current and box[2] - box[0] > max_width:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    if not lines:
        return [""]
    if len(lines) == max_lines and "".join(lines).replace(" ", "") != text.replace(" ", ""):
        last = lines[-1]
        lines[-1] = (last[:-1] + "…") if len(last) > 1 else "…"
    return lines


def _draw_bubble(draw: Any, bubble: BubbleSpec, box: PanelBox, image_font: Any) -> None:
    x = box.x + round(bubble.x * box.width)
    y = box.y + round(bubble.y * box.height)
    width = max(90, round(bubble.width * box.width))
    height = max(60, round(bubble.height * box.height))
    x = min(x, box.x + box.width - width - 8)
    y = min(y, box.y + box.height - height - 8)
    x = max(box.x + 8, x)
    y = max(box.y + 8, y)
    rect = (x, y, x + width, y + height)
    radius = min(34, max(8, min(width, height) // 5))
    fill = (255, 255, 255, 235) if bubble.kind != "narration" else (246, 239, 213, 238)
    outline_width = max(2, min(box.width, box.height) // 180)
    if bubble.kind == "narration":
        draw.rectangle(rect, fill=fill, outline=(20, 20, 20, 255), width=outline_width)
    else:
        draw.rounded_rectangle(
            rect,
            radius=radius,
            fill=fill,
            outline=(20, 20, 20, 255),
            width=outline_width,
        )
        if bubble.kind == "thought":
            dot = max(7, radius // 3)
            draw.ellipse(
                (x + width // 5, y + height + dot // 3, x + width // 5 + dot, y + height + dot + dot // 3),
                fill=fill,
                outline=(20, 20, 20, 255),
                width=max(1, outline_width - 1),
            )

    font_size = max(15, min(38, min(width, height) // 5))
    font = _font(image_font, font_size, bold=bubble.kind == "narration")
    padding = max(10, font_size // 2)
    line_height = max(font_size + 4, int(font_size * 1.25))
    lines = _wrap_text(draw, bubble.text, font, width - 2 * padding, max(1, (height - 2 * padding) // line_height))
    text_y = y + max(padding, (height - len(lines) * line_height) // 2)
    for line in lines:
        bounds = draw.textbbox((0, 0), line, font=font)
        text_width = bounds[2] - bounds[0]
        draw.text(
            (x + (width - text_width) // 2, text_y),
            line,
            font=font,
            fill=(18, 18, 18, 255),
        )
        text_y += line_height


def _compose_frame(
    sources: Sequence[Any],
    panels: Sequence[PanelSpec],
    boxes: Sequence[PanelBox],
    output_fps: int,
    pillow: tuple[Any, Any, Any, Any],
):
    Image, ImageDraw, ImageFont, ImageOps = pillow
    page = Image.new("RGB", PAGE_SIZE, (16, 16, 18))
    for source, panel, box in zip(sources, panels, boxes):
        frame = source.next_image(output_fps)
        rgb = None
        try:
            rgb = frame.convert("RGB")
            fitted = ImageOps.fit(
                rgb,
                (box.width, box.height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            page.paste(fitted, (box.x, box.y))
            fitted.close()
        finally:
            if rgb is not None:
                rgb.close()
            frame.close()
    draw = ImageDraw.Draw(page, "RGBA")
    for panel, box in zip(panels, boxes):
        draw.rectangle(
            (box.x, box.y, box.x + box.width - 1, box.y + box.height - 1),
            outline=(255, 255, 255, 255),
            width=5,
        )
        for bubble in panel.bubbles:
            _draw_bubble(draw, bubble, box, ImageFont)
    return page


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def render_living_comic(
    document_dict: Mapping[str, Any],
    out_dir: str | os.PathLike[str],
    fps: int = 8,
    seconds: float = 4,
    cancelled: Optional[Callable[[], bool]] = None,
) -> list[str]:
    """Compose panel clips and atomically export MP4 plus animated WebP.

    The callable returns absolute output paths in ``[mp4, webp]`` order.  No
    final file is exposed until both temporary encodes have completed.
    """

    document = normalize_living_document(document_dict)
    fps = _bounded_int(fps, "FPS", MIN_FPS, MAX_FPS)
    seconds = _bounded_float(seconds, "길이", MIN_SECONDS, MAX_SECONDS)
    total_frames = max(1, int(round(fps * seconds)))
    if total_frames > MAX_OUTPUT_FRAMES:
        raise LivingComicError(f"출력 프레임은 최대 {MAX_OUTPUT_FRAMES}개까지 지원합니다")
    if cancelled is not None and cancelled():
        raise LivingComicCancelled("Living Comic 내보내기가 취소되었습니다")

    pillow = _load_pillow()
    Image, _ImageDraw, _ImageFont, _ImageOps = pillow
    av = _load_av()
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not output_dir.is_dir():
        raise LivingComicError(f"출력 폴더를 만들 수 없습니다: {output_dir}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = f"living_comic_{stamp}_{uuid.uuid4().hex[:8]}"
    mp4_path = output_dir / f"{basename}.mp4"
    webp_path = output_dir / f"{basename}.webp"
    mp4_temp = output_dir / f".{basename}.mp4.writing"
    webp_temp = output_dir / f".{basename}.webp.writing"
    boxes = compute_panel_boxes(len(document.panels), document.layout)

    sources: list[Any] = []
    mp4_container = None
    webp_frames: list[Any] = []
    try:
        for panel in document.panels:
            source = (
                _LoopingVideoSource(panel.source_path, av)
                if panel.is_video
                else _StillSource(panel.source_path, Image)
            )
            sources.append(source)

        try:
            mp4_container = av.open(
                str(mp4_temp), mode="w", format="mp4", options={"movflags": "+faststart"}
            )
            stream = mp4_container.add_stream("libx264", rate=fps)
            stream.width, stream.height = PAGE_SIZE
            stream.pix_fmt = "yuv420p"
            stream.options = {"crf": "20", "preset": "medium"}
        except Exception as exc:
            raise LivingComicDependencyError(
                "PyAV의 H.264(libx264) 인코더를 사용할 수 없습니다. FFmpeg/PyAV 설치를 확인하세요"
            ) from exc

        duration_ms = max(1, round(1000 / fps))
        for frame_index in range(total_frames):
            if cancelled is not None and cancelled():
                raise LivingComicCancelled("Living Comic 내보내기가 취소되었습니다")
            page = _compose_frame(sources, document.panels, boxes, fps, pillow)
            try:
                video_frame = av.VideoFrame.from_image(page)
                video_frame.pts = frame_index
                for packet in stream.encode(video_frame):
                    mp4_container.mux(packet)
                # Palette frames substantially reduce retained memory while
                # Pillow still writes a full-size animated WebP at the end.
                webp_frames.append(page.quantize(colors=256, method=Image.Quantize.FASTOCTREE))
            finally:
                page.close()

        for packet in stream.encode():
            mp4_container.mux(packet)
        mp4_container.close()
        mp4_container = None

        if not webp_frames:
            raise LivingComicError("내보낼 프레임이 없습니다")
        webp_frames[0].save(
            webp_temp,
            format="WEBP",
            save_all=True,
            append_images=webp_frames[1:],
            duration=duration_ms,
            loop=0,
            quality=86,
            method=4,
        )
        _fsync_file(mp4_temp)
        _fsync_file(webp_temp)
        if cancelled is not None and cancelled():
            raise LivingComicCancelled("Living Comic 내보내기가 취소되었습니다")
        os.replace(mp4_temp, mp4_path)
        os.replace(webp_temp, webp_path)
        return [str(mp4_path.resolve()), str(webp_path.resolve())]
    except LivingComicError:
        raise
    except Exception as exc:
        raise LivingComicError(f"Living Comic 내보내기에 실패했습니다: {exc}") from exc
    finally:
        if mp4_container is not None:
            try:
                mp4_container.close()
            except Exception:
                pass
        for source in sources:
            source.close()
        for frame in webp_frames:
            try:
                frame.close()
            except Exception:
                pass
        for temporary in (mp4_temp, webp_temp):
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass

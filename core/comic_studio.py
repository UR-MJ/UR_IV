"""Comic Studio document model, persistence, and storyboard planning.

The module intentionally has a small interface: :class:`ComicStudio` owns
validation, atomic persistence, Ollama JSON parsing, and deterministic fallback
planning.  Vue only needs to understand the serialized document shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
import json
import os
import re
import time
import uuid


MAX_PANELS = 6
MAX_BUBBLES = 24
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
VALID_STYLES = {"manga", "anime", "webtoon", "cinematic", "painterly", "graphic novel"}
VALID_BUBBLE_STYLES = {"speech", "thought", "narration"}
VALID_LAYOUTS = {"auto", "grid", "vertical", "horizontal", "hero", "strip", "focus"}


class ComicDocumentError(ValueError):
    """Raised when a Comic document violates the public interface."""


@dataclass
class ComicPanel:
    id: str
    name: str
    text: str
    shot: str = "medium shot"
    characters: str = ""
    image_prompt: str = ""
    negative_prompt: str = ""
    motion_prompt: str = "subtle natural motion, preserve composition"
    image_path: str = ""
    video_path: str = ""
    seed: int = -1


@dataclass
class ComicBubble:
    id: str
    name: str
    text: str
    panel_index: int
    style: str = "speech"
    x: float = 0.1
    y: float = 0.08
    width: float = 0.34
    height: float = 0.16


@dataclass
class ComicDocument:
    version: int = 1
    id: str = field(default_factory=lambda: f"comic_{uuid.uuid4().hex[:12]}")
    title: str = "Untitled Comic"
    scene: str = ""
    art_style: str = "manga"
    layout: str = "auto"
    character_lock: str = ""
    panels: List[ComicPanel] = field(default_factory=list)
    bubbles: List[ComicBubble] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        bubbles_by_panel: Dict[int, List[Dict[str, Any]]] = {}
        serialized_bubbles = []
        for bubble in self.bubbles:
            item = {
                "id": bubble.id,
                "name": bubble.name,
                "text": bubble.text,
                "panelIndex": bubble.panel_index,
                "panel_index": bubble.panel_index,
                "kind": bubble.style,
                "style": bubble.style,
                "x": bubble.x,
                "y": bubble.y,
                "width": bubble.width,
                "height": bubble.height,
            }
            serialized_bubbles.append(item)
            bubbles_by_panel.setdefault(bubble.panel_index, []).append(item)
        panels = []
        for index, panel in enumerate(self.panels):
            panels.append(
                {
                    "id": panel.id,
                    "name": panel.name,
                    "text": panel.text,
                    "shot": panel.shot,
                    "characters": panel.characters,
                    "prompt": panel.image_prompt,
                    "imagePrompt": panel.image_prompt,
                    "image_prompt": panel.image_prompt,
                    "negative": panel.negative_prompt,
                    "negativePrompt": panel.negative_prompt,
                    "negative_prompt": panel.negative_prompt,
                    "motion": panel.motion_prompt,
                    "motionPrompt": panel.motion_prompt,
                    "motion_prompt": panel.motion_prompt,
                    "imagePath": panel.image_path,
                    "image_path": panel.image_path,
                    "videoPath": panel.video_path,
                    "video_path": panel.video_path,
                    "seed": panel.seed,
                    "bubbles": bubbles_by_panel.get(index, []),
                }
            )
        return {
            "version": self.version,
            "id": self.id,
            "title": self.title,
            "scene": self.scene,
            "style": self.art_style.title(),
            "artStyle": self.art_style,
            "art_style": self.art_style,
            "layout": self.layout,
            "characterLock": self.character_lock,
            "character_lock": self.character_lock,
            "width": 1400,
            "height": 2100,
            "panels": panels,
            "bubbles": serialized_bubbles,
            "updated_at": self.updated_at,
        }


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        return min(maximum, max(minimum, float(value)))
    except (TypeError, ValueError):
        return default


def _seed(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return -1
    return parsed if -1 <= parsed <= (2**63 - 1) else -1


def _id(value: Any, prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:80]
    return cleaned or f"{prefix}_{uuid.uuid4().hex[:12]}"


class ComicStudio:
    """Validate, plan, save, and load one editable Comic document.

    ``complete_json`` is an injected adapter for the external Ollama dependency.
    It receives ``(system_prompt, user_prompt)`` and returns response text.
    Omitting it gives a deterministic local fallback, which keeps the module and
    tests useful when Ollama is unavailable.
    """

    def __init__(
        self,
        state_path: Path | str,
        complete_json: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        self.state_path = Path(state_path)
        self._complete_json = complete_json

    def normalize(self, raw: Dict[str, Any]) -> ComicDocument:
        if not isinstance(raw, dict):
            raise ComicDocumentError("Comic 문서는 객체여야 합니다")

        raw_panels = raw.get("panels", [])
        raw_bubbles = list(raw.get("bubbles", []) or [])
        if not isinstance(raw_panels, list) or not (1 <= len(raw_panels) <= MAX_PANELS):
            raise ComicDocumentError("Comic 문서는 1~6개의 컷이 필요합니다")
        if not isinstance(raw_bubbles, list):
            raise ComicDocumentError("말풍선 데이터가 올바르지 않습니다")
        for panel_index, item in enumerate(raw_panels):
            if isinstance(item, dict) and isinstance(item.get("bubbles"), list):
                for nested in item["bubbles"]:
                    if isinstance(nested, dict):
                        bubble = dict(nested)
                        bubble.setdefault("panelIndex", panel_index)
                        raw_bubbles.append(bubble)
        # Canonical documents contain both the flattened and nested views.
        deduped_bubbles = []
        seen_bubbles = set()
        for item in raw_bubbles:
            key = str(item.get("id", "")) if isinstance(item, dict) else ""
            if key and key in seen_bubbles:
                continue
            if key:
                seen_bubbles.add(key)
            deduped_bubbles.append(item)
        raw_bubbles = deduped_bubbles
        if len(raw_bubbles) > MAX_BUBBLES:
            raise ComicDocumentError("말풍선은 최대 24개까지 사용할 수 있습니다")

        panels: List[ComicPanel] = []
        for index, item in enumerate(raw_panels):
            if not isinstance(item, dict):
                raise ComicDocumentError(f"컷 {index + 1} 데이터가 올바르지 않습니다")
            description = _text(item.get("text", item.get("description", item.get("prompt"))), 1600)
            image_prompt = _text(
                item.get("image_prompt", item.get("imagePrompt", item.get("prompt", description))), 4000
            )
            panels.append(
                ComicPanel(
                    id=_id(item.get("id"), "panel"),
                    name=_text(item.get("name"), 100) or f"컷 {index + 1}",
                    text=description,
                    shot=_text(item.get("shot"), 500),
                    characters=_text(item.get("characters"), 1800),
                    image_prompt=image_prompt,
                    negative_prompt=_text(
                        item.get("negative_prompt", item.get("negativePrompt", item.get("negative"))), 3000
                    ),
                    motion_prompt=_text(
                        item.get("motion_prompt", item.get("motionPrompt", item.get("motion"))), 1800
                    ),
                    image_path=_text(item.get("image_path", item.get("imagePath")), 2048),
                    video_path=_text(item.get("video_path", item.get("videoPath")), 2048),
                    seed=_seed(item.get("seed", -1)),
                )
            )

        bubbles: List[ComicBubble] = []
        for index, item in enumerate(raw_bubbles):
            if not isinstance(item, dict):
                continue
            panel_index = int(_number(item.get("panel_index", item.get("panelIndex", 0)), 0, 0, len(panels) - 1))
            style = str(item.get("style", item.get("kind", "speech")))
            if style not in VALID_BUBBLE_STYLES:
                style = "speech"
            bubbles.append(
                ComicBubble(
                    id=_id(item.get("id"), "bubble"),
                    name=_text(item.get("name"), 100) or f"대사 {index + 1}",
                    text=_text(item.get("text"), 800),
                    panel_index=panel_index,
                    style=style,
                    x=_number(item.get("x"), 8, 0.0, 95.0),
                    y=_number(item.get("y"), 8, 0.0, 95.0),
                    width=_number(item.get("width"), 38, 8.0, 90.0),
                    height=_number(item.get("height"), 18, 5.0, 80.0),
                )
            )

        art_style = str(raw.get("art_style", raw.get("artStyle", raw.get("style", "manga")))).strip().lower()
        layout = str(raw.get("layout", "auto"))
        document = ComicDocument(
            version=1,
            id=_id(raw.get("id"), "comic"),
            title=_text(raw.get("title"), 160) or "Untitled Comic",
            scene=_text(raw.get("scene"), 12000),
            art_style=art_style if art_style in VALID_STYLES else "manga",
            layout=layout if layout in VALID_LAYOUTS else "auto",
            character_lock=_text(raw.get("character_lock", raw.get("characterLock")), 3000),
            panels=panels,
            bubbles=bubbles,
            updated_at=time.time(),
        )
        self._check_size(document)
        return document

    def plan(
        self,
        scene: str,
        panel_count: int = 3,
        art_style: str = "manga",
        character_lock: str = "",
    ) -> ComicDocument:
        scene = _text(scene, 12000)
        if not scene:
            raise ComicDocumentError("장면 설명을 입력하세요")
        panel_count = max(1, min(MAX_PANELS, int(panel_count or 3)))
        art_style = str(art_style or "manga").strip().lower()
        if art_style not in VALID_STYLES:
            art_style = "manga"

        raw = None
        if self._complete_json is not None:
            system = self._director_system_prompt(panel_count, art_style, character_lock)
            response = self._complete_json(system, scene)
            raw = self._parse_json_response(response)
        if raw is None:
            raw = self._fallback_plan(scene, panel_count, character_lock)

        raw.update(
            {
                "scene": scene,
                "art_style": art_style,
                "character_lock": character_lock,
                "title": raw.get("title") or _text(scene.splitlines()[0], 80),
            }
        )
        if len(raw.get("panels", [])) != panel_count:
            raise ComicDocumentError(f"콘티 응답에는 정확히 {panel_count}개의 컷이 필요합니다")
        return self.normalize(raw)

    def save(self, raw: Dict[str, Any] | ComicDocument) -> ComicDocument:
        document = raw if isinstance(raw, ComicDocument) else self.normalize(raw)
        payload = document.to_dict()
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise ComicDocumentError("Comic 문서가 저장 한도를 초과했습니다")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".writing")
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)
        return document

    def load(self) -> Optional[ComicDocument]:
        if not self.state_path.is_file():
            return None
        if self.state_path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ComicDocumentError("저장된 Comic 문서가 크기 제한을 초과했습니다")
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ComicDocumentError(f"Comic 문서를 읽을 수 없습니다: {exc}") from exc
        return self.normalize(raw)

    @staticmethod
    def _parse_json_response(text: str) -> Dict[str, Any]:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ComicDocumentError("콘티 모델이 JSON 객체를 반환하지 않았습니다")
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ComicDocumentError(f"콘티 JSON을 해석할 수 없습니다: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ComicDocumentError("콘티 응답은 JSON 객체여야 합니다")
        return parsed

    @staticmethod
    def _director_system_prompt(panel_count: int, style: str, character_lock: str) -> str:
        lock = character_lock.strip() or "사용자가 지정한 외모와 복장을 컷마다 동일하게 반복"
        return (
            "당신은 한국어 만화 콘티 감독입니다. 설명 없이 JSON 객체만 반환하세요. "
            f"panels 배열은 정확히 {panel_count}개이며 스타일은 {style}입니다. "
            "각 panel은 name, text, shot, characters, imagePrompt, negativePrompt, "
            "motionPrompt 필드를 가집니다. bubbles는 name, text, panelIndex, "
            "style(speech|thought|narration)을 가집니다. "
            f"캐릭터 일관성 규칙: {lock}. 사건 순서와 사용자가 쓴 대사를 보존하세요."
        )

    @staticmethod
    def _fallback_plan(scene: str, panel_count: int, character_lock: str) -> Dict[str, Any]:
        beats = [part.strip() for part in re.split(r"(?:\n+|(?<=[.!?。！？])\s+)", scene) if part.strip()]
        if not beats:
            beats = [scene]
        panels = []
        for index in range(panel_count):
            beat = beats[min(index, len(beats) - 1)]
            panels.append(
                {
                    "name": f"컷 {index + 1}",
                    "text": beat,
                    "shot": "wide establishing shot" if index == 0 else "medium cinematic shot",
                    "characters": character_lock,
                    "imagePrompt": ", ".join(filter(None, (character_lock, beat, "coherent comic panel composition"))),
                    "negativePrompt": "inconsistent character, malformed hands, text, watermark",
                    "motionPrompt": "subtle natural motion, preserve identity and original composition",
                }
            )
        return {"title": _text(scene, 80), "panels": panels, "bubbles": []}

    @staticmethod
    def _check_size(document: ComicDocument) -> None:
        size = len(json.dumps(document.to_dict(), ensure_ascii=False).encode("utf-8"))
        if size > MAX_DOCUMENT_BYTES:
            raise ComicDocumentError("Comic 문서가 크기 제한을 초과했습니다")


def panel_generation_payloads(document: ComicDocument | Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Yield queue-ready payloads while enforcing one shared character lock."""

    if isinstance(document, dict):
        validator = ComicStudio(Path(os.devnull))
        document = validator.normalize(document)
    for index, panel in enumerate(document.panels):
        positive = ", ".join(
            part for part in (document.character_lock, panel.characters, panel.image_prompt) if part
        )
        yield {
            "panel_index": index,
            "panel_id": panel.id,
            "prompt": positive,
            "negative_prompt": panel.negative_prompt,
            "seed": panel.seed,
            "motion_prompt": panel.motion_prompt,
        }

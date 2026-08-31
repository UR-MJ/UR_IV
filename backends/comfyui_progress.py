"""ComfyUI workflow progress aggregation.

ComfyUI reports sampler-local progress, node transitions, and cached nodes as
separate websocket events.  ``ProgressTracker`` hides those details behind one
small, pure interface and produces a monotonic workflow-level percentage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ProgressUpdate:
    """One observable workflow-level progress update."""

    step: int
    total: int = 100
    stage: str = "running"
    node_id: Optional[str] = None
    node_class: Optional[str] = None


def _node_weight(class_type: str) -> float:
    """Return a coarse cost weight without depending on custom-node names.

    The rules intentionally use capabilities embedded in class names instead
    of a model-specific allowlist.  Unknown nodes remain part of the total with
    a small non-zero weight.
    """
    name = (class_type or "").lower()

    # Loaders can be expensive, but normally report no fractional progress.
    if "loader" in name or name.startswith("load"):
        return 2.0
    # Sampling dominates both image and video diffusion workflows.
    if "sampler" in name or "sampling" in name:
        return 12.0
    if "upscale" in name or "supir" in name or "esrgan" in name:
        return 6.0
    if "video" in name or "movie" in name:
        return 6.0
    if "vae" in name and ("encode" in name or "decode" in name):
        return 3.0
    if "encode" in name or "conditioning" in name:
        return 2.0
    if "save" in name or "preview" in name or "combine" in name:
        return 2.0
    if "audio" in name:
        return 2.0
    return 1.0


class ProgressTracker:
    """Aggregate ComfyUI websocket messages into monotonic 0..100 progress.

    Interface invariant: :meth:`consume` never returns a ``step`` lower than a
    previous update.  The workflow is treated as opaque API-format nodes; no
    execution-order knowledge or model-specific node registration is required.
    """

    def __init__(self, workflow: Mapping[str, Any]):
        self._classes: dict[str, str] = {}
        self._weights: dict[str, float] = {}
        for raw_node_id, raw_node in workflow.items():
            if not isinstance(raw_node, Mapping):
                continue
            node_id = str(raw_node_id)
            class_type = str(raw_node.get("class_type", "Unknown"))
            self._classes[node_id] = class_type
            self._weights[node_id] = _node_weight(class_type)

        # Even a malformed/empty workflow has a well-defined progress scale.
        self._total_weight = sum(self._weights.values()) or 1.0
        self._completed: set[str] = set()
        self._fractions: dict[str, float] = {}
        self._current_node: Optional[str] = None
        self._last_step = 0
        self._status_reported = False

    def consume(self, message: Mapping[str, Any]) -> Optional[ProgressUpdate]:
        """Consume one decoded websocket message.

        Unknown events return ``None``.  Recognised events may return an update
        whose numeric progress is unchanged when the human-readable stage or
        current node changed.
        """
        message_type = str(message.get("type", ""))
        raw_data = message.get("data", {})
        data = raw_data if isinstance(raw_data, Mapping) else {}

        if message_type == "status":
            if self._status_reported:
                return None
            self._status_reported = True
            return self._update(stage="queued")

        if message_type == "execution_cached":
            raw_nodes = data.get("nodes", [])
            if not isinstance(raw_nodes, (list, tuple, set)):
                raw_nodes = []
            for raw_node_id in raw_nodes:
                self._complete(str(raw_node_id))
            return self._update(stage="cached")

        if message_type == "executing":
            raw_node_id = data.get("node")
            if raw_node_id is None:
                for node_id in self._weights:
                    self._complete(node_id)
                self._current_node = None
                return self._update(stage="complete", force_complete=True)

            node_id = str(raw_node_id)
            if self._current_node and self._current_node != node_id:
                self._complete(self._current_node)
            self._current_node = node_id
            self._fractions.setdefault(node_id, 0.0)
            return self._update(stage="executing", node_id=node_id)

        if message_type == "progress":
            raw_node_id = data.get("node", self._current_node)
            node_id = str(raw_node_id) if raw_node_id is not None else None
            if node_id is not None:
                if self._current_node and self._current_node != node_id:
                    self._complete(self._current_node)
                self._current_node = node_id

            try:
                value = float(data.get("value", 0))
                maximum = float(data.get("max", 0))
            except (TypeError, ValueError):
                value, maximum = 0.0, 0.0

            if node_id is not None and maximum > 0:
                fraction = min(1.0, max(0.0, value / maximum))
                self._fractions[node_id] = max(
                    self._fractions.get(node_id, 0.0), fraction
                )
            return self._update(stage="progress", node_id=node_id)

        # ``executed`` is not guaranteed by every ComfyUI version, but using it
        # when present makes completion accounting more accurate.
        if message_type == "executed":
            raw_node_id = data.get("node")
            node_id = str(raw_node_id) if raw_node_id is not None else None
            if node_id is not None:
                self._complete(node_id)
            return self._update(stage="executed", node_id=node_id)

        if message_type == "execution_success":
            for node_id in self._weights:
                self._complete(node_id)
            self._current_node = None
            return self._update(stage="complete", force_complete=True)

        return None

    def _complete(self, node_id: str) -> None:
        if node_id not in self._weights:
            return
        self._completed.add(node_id)
        self._fractions[node_id] = 1.0

    def _update(self, *, stage: str, node_id: Optional[str] = None,
                force_complete: bool = False) -> ProgressUpdate:
        if force_complete:
            raw_step = 100
        else:
            completed_weight = 0.0
            for weighted_node_id, weight in self._weights.items():
                if weighted_node_id in self._completed:
                    completed_weight += weight
                else:
                    completed_weight += weight * self._fractions.get(
                        weighted_node_id, 0.0
                    )
            raw_step = int(round(completed_weight / self._total_weight * 100))

        self._last_step = max(self._last_step, min(100, raw_step))
        resolved_node_id = node_id or self._current_node
        return ProgressUpdate(
            step=self._last_step,
            stage=stage,
            node_id=resolved_node_id,
            node_class=self._classes.get(resolved_node_id) if resolved_node_id else None,
        )

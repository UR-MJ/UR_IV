"""Pure ANIMA 28/40/52-block LoRA compatibility for ComfyUI.

This module deliberately has no ComfyUI or torch import.  The Comfy node
adapter can inspect its MODEL through :func:`inspect_anima_model`, prepare a
fresh state dict with :func:`prepare_anima_lora_for_model`, and only then hand
that state dict to ComfyUI's LoRA parser.

Mappings are ``target block index -> source block index``.  Expansion copies
the preceding lineage block into each inserted position; contraction keeps
only the inherited lineage.  The adjacent-generation insertion positions are
functional model metadata: 28->40 comes from Anima-2.9B's published
``expand_manifest.json`` and 40->52 comes from the Anima 3.8B checkpoint's
``insertion_positions`` metadata.  This module derives every direction from
those positions locally.  The caller's raw mapping is never mutated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


ANIMA_BASE_BLOCKS = 28
ANIMA_29B_BLOCKS = 40
ANIMA_38B_BLOCKS = 52
SUPPORTED_BLOCK_COUNTS = (
    ANIMA_BASE_BLOCKS,
    ANIMA_29B_BLOCKS,
    ANIMA_38B_BLOCKS,
)

_NAMESPACE_PATTERNS = (
    (
        "kohya",
        re.compile(r"^(lora_unet_blocks_)(\d+)(.*)$"),
    ),
    (
        "native",
        re.compile(r"^(diffusion_model\.blocks\.)(\d+)(.*)$"),
    ),
)

# Semantic Connector v2 belongs only to the 52-block model.  Qwen3.5 is an
# independent text encoder and is intentionally not included here.
ANIMA_38B_CONNECTOR_PREFIXES = (
    "net.anima_v2_connector.",
    "diffusion_model.anima_v2_connector.",
    "lora_unet_anima_v2_connector_",
)


class AnimaLoraCompatibilityError(ValueError):
    """Raised when applying a LoRA would require guessing or lose keys silently."""


@dataclass(frozen=True)
class AnimaModelInfo:
    """Result of inspecting a possible ComfyUI MODEL/ModelPatcher."""

    is_anima: bool
    block_count: int | None
    evidence: tuple[str, ...] = ()
    has_38b_connector: bool = False


@dataclass(frozen=True)
class AnimaLoraRemapReport:
    """Observable outcome of preparing one LoRA state dict."""

    model_is_anima: bool
    source_blocks: int | None
    target_blocks: int | None
    namespaces: tuple[str, ...]
    action: str
    changed: bool
    remapped: bool
    passthrough: bool
    duplicated_blocks: int = 0
    dropped_blocks: int = 0
    duplicated_tensor_keys: int = 0
    dropped_block_keys: int = 0
    dropped_connector_keys: int = 0


@dataclass(frozen=True)
class PreparedAnimaLora:
    """A fresh state-dict mapping and the report describing how it was made."""

    state_dict: dict[Any, Any]
    report: AnimaLoraRemapReport


@dataclass(frozen=True)
class _BlockEntry:
    original_key: str
    prefix: str
    suffix: str
    value: Any


# Published by Gazingstars123/Anima-2.9B in ``expand_manifest.json`` at
# revision 9f9cb502dbae7a616c3cc5a530633427fe735665.  These are model-layout
# metadata, not a copied loader implementation.
_ANIMA_29B_INSERTION_POSITIONS = (
    2, 5, 8, 11, 14, 17, 21, 24, 27, 30, 33, 36,
)

# Published inside the Anima-3.8B-v1.1 checkpoint's ``insertion_positions``
# metadata.  Each LLaMA-Pro insertion inherits the immediately preceding
# 2.9B lineage block at initialisation.
_ANIMA_38B_INSERTION_POSITIONS = (
    3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47,
)


def _make_expansion_mapping(
    source_count: int,
    inserted_to_source: Mapping[int, int],
) -> tuple[int, ...]:
    target_count = source_count + len(inserted_to_source)
    mapping: list[int] = []
    next_source = 0
    for target_index in range(target_count):
        if target_index in inserted_to_source:
            source_index = int(inserted_to_source[target_index])
            if source_index != next_source - 1:
                raise ValueError(
                    "inserted ANIMA block must clone the immediately preceding "
                    f"lineage: target={target_index}, source={source_index}"
                )
            mapping.append(source_index)
            continue
        if next_source >= source_count:
            raise ValueError("ANIMA expansion consumed too many source blocks")
        mapping.append(next_source)
        next_source += 1
    if next_source != source_count:
        raise ValueError(
            f"ANIMA expansion consumed {next_source}/{source_count} source blocks"
        )
    return tuple(mapping)


def _make_contraction_mapping(
    target_count: int,
    source_count: int,
    inserted_positions: set[int],
) -> tuple[int, ...]:
    mapping = tuple(
        source_index
        for source_index in range(source_count)
        if source_index not in inserted_positions
    )
    if len(mapping) != target_count:
        raise ValueError(
            f"ANIMA contraction produced {len(mapping)} positions, expected "
            f"{target_count}"
        )
    return mapping


def _preceding_lineage_sources(
    insertion_positions: tuple[int, ...],
) -> dict[int, int]:
    """Derive inserted target -> preceding source from ordered positions."""

    return {
        target_index: target_index - inserted_before - 1
        for inserted_before, target_index in enumerate(insertion_positions)
    }


_ANIMA_29B_INSERTED_TO_BASE_SOURCE = _preceding_lineage_sources(
    _ANIMA_29B_INSERTION_POSITIONS,
)
_ANIMA_38B_INSERTED_TO_29B_SOURCE = _preceding_lineage_sources(
    _ANIMA_38B_INSERTION_POSITIONS,
)
_ANIMA_28_TO_40 = _make_expansion_mapping(
    ANIMA_BASE_BLOCKS,
    _ANIMA_29B_INSERTED_TO_BASE_SOURCE,
)
_ANIMA_40_TO_28 = _make_contraction_mapping(
    ANIMA_BASE_BLOCKS,
    ANIMA_29B_BLOCKS,
    set(_ANIMA_29B_INSERTION_POSITIONS),
)
_ANIMA_40_TO_52 = _make_expansion_mapping(
    ANIMA_29B_BLOCKS,
    _ANIMA_38B_INSERTED_TO_29B_SOURCE,
)
_ANIMA_52_TO_40 = _make_contraction_mapping(
    ANIMA_29B_BLOCKS,
    ANIMA_38B_BLOCKS,
    set(_ANIMA_38B_INSERTION_POSITIONS),
)
_ANIMA_28_TO_52 = tuple(
    _ANIMA_28_TO_40[source_40] for source_40 in _ANIMA_40_TO_52
)
_ANIMA_52_TO_28 = tuple(
    _ANIMA_52_TO_40[source_40] for source_40 in _ANIMA_40_TO_28
)

BLOCK_MAPPINGS: dict[tuple[int, int], tuple[int, ...]] = {
    (ANIMA_BASE_BLOCKS, ANIMA_29B_BLOCKS): _ANIMA_28_TO_40,
    (ANIMA_29B_BLOCKS, ANIMA_BASE_BLOCKS): _ANIMA_40_TO_28,
    (ANIMA_29B_BLOCKS, ANIMA_38B_BLOCKS): _ANIMA_40_TO_52,
    (ANIMA_38B_BLOCKS, ANIMA_29B_BLOCKS): _ANIMA_52_TO_40,
    (ANIMA_BASE_BLOCKS, ANIMA_38B_BLOCKS): _ANIMA_28_TO_52,
    (ANIMA_38B_BLOCKS, ANIMA_BASE_BLOCKS): _ANIMA_52_TO_28,
}


def _image_model_marker(value: Any) -> str:
    return str(value or "").strip().casefold()


def inspect_anima_model(model: Any) -> AnimaModelInfo:
    """Inspect a Comfy MODEL without importing ComfyUI.

    Merely having 28, 40, or 52 blocks is not enough: another architecture
    could have the same depth.  An exact Anima class name or an ``image_model``
    configuration marker is required before the block list is trusted.
    """

    if model is None:
        return AnimaModelInfo(False, None)

    base = getattr(model, "model", model)
    diffusion = getattr(base, "diffusion_model", None)
    has_38b_connector = (
        diffusion is not None
        and getattr(diffusion, "anima_v2_connector", None) is not None
    )
    evidence: list[str] = []

    for label, candidate in (("model", base), ("diffusion_model", diffusion)):
        if candidate is not None and type(candidate).__name__.casefold() == "anima":
            evidence.append(f"{label}.class")

    model_config = getattr(base, "model_config", None)
    unet_config = getattr(model_config, "unet_config", None)
    if isinstance(unet_config, Mapping):
        if _image_model_marker(unet_config.get("image_model")) == "anima":
            evidence.append("model_config.unet_config.image_model")
    for label, candidate in (("model", base), ("model_config", model_config)):
        if _image_model_marker(getattr(candidate, "image_model", None)) == "anima":
            evidence.append(f"{label}.image_model")

    if not evidence:
        return AnimaModelInfo(False, None)

    blocks = getattr(diffusion, "blocks", None)
    if blocks is None:
        return AnimaModelInfo(
            True,
            None,
            tuple(dict.fromkeys(evidence)),
            has_38b_connector,
        )
    try:
        block_count = len(blocks)
    except TypeError:
        block_count = None
    return AnimaModelInfo(
        True,
        block_count,
        tuple(dict.fromkeys(evidence)),
        has_38b_connector,
    )


def _collect_block_entries(
    state_dict: Mapping[Any, Any],
) -> dict[str, dict[int, list[_BlockEntry]]]:
    found: dict[str, dict[int, list[_BlockEntry]]] = {
        name: {} for name, _ in _NAMESPACE_PATTERNS
    }
    for key, value in state_dict.items():
        if not isinstance(key, str):
            continue
        for namespace, pattern in _NAMESPACE_PATTERNS:
            match = pattern.match(key)
            if match is None:
                continue
            index = int(match.group(2))
            found[namespace].setdefault(index, []).append(
                _BlockEntry(key, match.group(1), match.group(3), value)
            )
            break
    return found


def _layout_for_indices(namespace: str, indices: set[int]) -> int:
    for block_count in SUPPORTED_BLOCK_COUNTS:
        if indices == set(range(block_count)):
            return block_count
    # Some real ANIMA training runs intentionally omit frozen leading blocks
    # (for example 2..27 or 2..39).  The terminal block still identifies the
    # source architecture without guessing; missing entries simply remain
    # absent when the lineage is expanded or contracted.
    if indices:
        anchored_count = max(indices) + 1
        if (
            anchored_count in SUPPORTED_BLOCK_COUNTS
            and indices.issubset(set(range(anchored_count)))
        ):
            return anchored_count
    preview = ",".join(str(value) for value in sorted(indices)[:12])
    if len(indices) > 12:
        preview += ",..."
    raise AnimaLoraCompatibilityError(
        f"ANIMA LoRA namespace {namespace!r} is sparse or unsupported "
        f"(indices=[{preview}], count={len(indices)}); refusing to guess its layout"
    )


def _detect_source_layout(
    entries: Mapping[str, Mapping[int, list[_BlockEntry]]],
) -> tuple[int | None, tuple[str, ...]]:
    layouts: dict[str, int] = {}
    for namespace, indexed in entries.items():
        if indexed:
            layouts[namespace] = _layout_for_indices(namespace, set(indexed))
    if not layouts:
        return None, ()
    if len(layouts) > 1:
        detail = ", ".join(
            f"{namespace}={count}" for namespace, count in layouts.items()
        )
        if len(set(layouts.values())) != 1:
            raise AnimaLoraCompatibilityError(
                f"ANIMA LoRA namespaces describe different layouts ({detail})"
            )
        # Matching layouts can legitimately coexist when the namespaces carry
        # different modules (for example attention in Kohya form and MLP in
        # native form).  The Comfy boundary validates the converted aliases
        # against the live model key map and rejects only real collisions.
    return next(iter(layouts.values())), tuple(layouts)


def _is_38b_connector_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.casefold()
    return lowered.startswith(ANIMA_38B_CONNECTOR_PREFIXES)


def _clone_duplicate(value: Any) -> Any:
    clone = getattr(value, "clone", None)
    return clone() if callable(clone) else value


def remap_anima_lora_state_dict(
    raw_lora: Mapping[Any, Any],
    target_blocks: int,
    *,
    has_38b_connector: bool | None = None,
) -> PreparedAnimaLora:
    """Return a prepared copy for one known ANIMA target block count.

    Forge's ``llm_adapter`` namespace migration is intentionally absent:
    ComfyUI owns its own key conversion, and applying Forge's rewrite here can
    make otherwise valid Comfy keys unmatchable.
    """

    if target_blocks not in SUPPORTED_BLOCK_COUNTS:
        raise AnimaLoraCompatibilityError(
            f"unsupported ANIMA model depth {target_blocks}; expected one of "
            f"{SUPPORTED_BLOCK_COUNTS}"
        )

    entries = _collect_block_entries(raw_lora)
    source_blocks, namespaces = _detect_source_layout(entries)
    connector_keys = [key for key in raw_lora if _is_38b_connector_key(key)]
    if (
        target_blocks == ANIMA_38B_BLOCKS
        and connector_keys
        and has_38b_connector is False
    ):
        raise AnimaLoraCompatibilityError(
            "ANIMA LoRA contains Semantic Connector v2 keys, but the active "
            "52-block MODEL has no anima_v2_connector module"
        )
    dropped_connectors: set[Any] = set()
    if target_blocks < ANIMA_38B_BLOCKS and connector_keys:
        non_connector_keys = [
            key for key in raw_lora if not _is_38b_connector_key(key)
        ]
        if not non_connector_keys:
            raise AnimaLoraCompatibilityError(
                "ANIMA 3.8B connector-only LoRA cannot be projected to a "
                f"{target_blocks}-block model"
            )
        dropped_connectors.update(connector_keys)

    all_block_keys = {
        entry.original_key
        for indexed in entries.values()
        for block_entries in indexed.values()
        for entry in block_entries
    }
    prepared = {
        key: value
        for key, value in raw_lora.items()
        if key not in all_block_keys and key not in dropped_connectors
    }

    duplicated_tensor_keys = 0
    dropped_block_keys = 0
    if source_blocks is not None:
        mapping = (
            tuple(range(target_blocks))
            if source_blocks == target_blocks
            else BLOCK_MAPPINGS[(source_blocks, target_blocks)]
        )
        retained_sources = set(mapping)
        dropped_block_keys = sum(
            len(block_entries)
            for namespace in namespaces
            for source_index, block_entries in entries[namespace].items()
            if source_index not in retained_sources
        )
        emitted_sources: set[tuple[str, int]] = set()
        for target_index, source_index in enumerate(mapping):
            for namespace in namespaces:
                duplicate_source = (namespace, source_index) in emitted_sources
                for entry in entries[namespace].get(source_index, ()):
                    destination = f"{entry.prefix}{target_index}{entry.suffix}"
                    if destination in prepared:
                        raise AnimaLoraCompatibilityError(
                            "ANIMA LoRA remap destination collision: "
                            f"{entry.original_key!r} -> {destination!r}"
                        )
                    prepared[destination] = (
                        _clone_duplicate(entry.value)
                        if duplicate_source
                        else entry.value
                    )
                    if duplicate_source:
                        duplicated_tensor_keys += 1
                emitted_sources.add((namespace, source_index))

    remapped = source_blocks is not None and source_blocks != target_blocks
    key_names_changed = set(prepared) != set(raw_lora)
    changed = remapped or bool(dropped_connectors) or key_names_changed
    if source_blocks is None:
        action = "drop_38b_connector" if dropped_connectors else "passthrough_no_blocks"
    elif source_blocks < target_blocks:
        action = "expand"
    elif source_blocks > target_blocks:
        action = "contract"
    elif dropped_connectors:
        action = "native_drop_38b_connector"
    else:
        action = "native"

    report = AnimaLoraRemapReport(
        model_is_anima=True,
        source_blocks=source_blocks,
        target_blocks=target_blocks,
        namespaces=namespaces,
        action=action,
        changed=changed,
        remapped=remapped,
        passthrough=not changed,
        duplicated_blocks=(
            max(0, target_blocks - source_blocks)
            if source_blocks is not None and remapped
            else 0
        ),
        dropped_blocks=(
            max(0, source_blocks - target_blocks)
            if source_blocks is not None and remapped
            else 0
        ),
        duplicated_tensor_keys=duplicated_tensor_keys,
        dropped_block_keys=dropped_block_keys,
        dropped_connector_keys=len(dropped_connectors),
    )
    return PreparedAnimaLora(prepared, report)


def prepare_anima_lora_for_model(
    raw_lora: Mapping[Any, Any],
    model: Any,
) -> PreparedAnimaLora:
    """Prepare a LoRA for a Comfy MODEL, or return a non-Anima shallow copy."""

    model_info = inspect_anima_model(model)
    if not model_info.is_anima:
        copied = dict(raw_lora)
        return PreparedAnimaLora(
            copied,
            AnimaLoraRemapReport(
                model_is_anima=False,
                source_blocks=None,
                target_blocks=None,
                namespaces=(),
                action="passthrough_non_anima",
                changed=False,
                remapped=False,
                passthrough=True,
            ),
        )
    if model_info.block_count is None:
        raise AnimaLoraCompatibilityError(
            "ANIMA MODEL does not expose diffusion_model.blocks"
        )
    return remap_anima_lora_state_dict(
        raw_lora,
        model_info.block_count,
        has_38b_connector=model_info.has_38b_connector,
    )


__all__ = [
    "ANIMA_29B_BLOCKS",
    "ANIMA_38B_BLOCKS",
    "ANIMA_38B_CONNECTOR_PREFIXES",
    "ANIMA_BASE_BLOCKS",
    "BLOCK_MAPPINGS",
    "SUPPORTED_BLOCK_COUNTS",
    "AnimaLoraCompatibilityError",
    "AnimaLoraRemapReport",
    "AnimaModelInfo",
    "PreparedAnimaLora",
    "inspect_anima_model",
    "prepare_anima_lora_for_model",
    "remap_anima_lora_state_dict",
]

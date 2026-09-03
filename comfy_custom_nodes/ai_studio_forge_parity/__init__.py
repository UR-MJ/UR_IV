"""AI Studio Pro's bundled Forge Neo compatibility nodes for ComfyUI."""
from __future__ import annotations

from .anima38_nodes import (
    NODE_CLASS_MAPPINGS as _ANIMA38_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _ANIMA38_DISPLAY_NAMES,
)
from .anima_lora_nodes import NODE_CLASS_MAPPINGS as _ANIMA_LORA_NODES
from .generation import NODE_CLASS_MAPPINGS as _GENERATION_NODES
from .guidance import NODE_CLASS_MAPPINGS as _GUIDANCE_NODES
from .sam3_nodes import (
    NODE_CLASS_MAPPINGS as _SAM3_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _SAM3_DISPLAY_NAMES,
)


__version__ = "1.1.1"


def _merge_node_maps(*maps):
    merged = {}
    for mapping in maps:
        duplicates = set(merged).intersection(mapping)
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise RuntimeError(f"Duplicate AI Studio ComfyUI node IDs: {names}")
        merged.update(mapping)
    return merged


NODE_CLASS_MAPPINGS = _merge_node_maps(
    _ANIMA38_NODES,
    _ANIMA_LORA_NODES,
    _GUIDANCE_NODES,
    _GENERATION_NODES,
    _SAM3_NODES,
)

NODE_DISPLAY_NAME_MAPPINGS = {
    node_id: node_id.replace("ForgeNeo", "Forge Neo ")
    for node_id in NODE_CLASS_MAPPINGS
}
NODE_DISPLAY_NAME_MAPPINGS.update(_SAM3_DISPLAY_NAMES)
NODE_DISPLAY_NAME_MAPPINGS.update(_ANIMA38_DISPLAY_NAMES)


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

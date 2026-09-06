"""Transport-only H3 conditioning cache contract; no torch or Comfy imports."""
from __future__ import annotations

import copy
import json


CACHE_NODE_TYPES = frozenset({"ForgeNeoH3ConditioningCachePrepare", "ForgeNeoH3ConditioningCacheLoad"})
DEFAULT_MAX_BYTES = 8 * 1024 ** 3
DEFAULT_MAX_ENTRIES = 32
CACHE_SCHEMA = 1


def split_workflow(graph: dict, metadata: dict, *, max_bytes=DEFAULT_MAX_BYTES,
                   max_entries=DEFAULT_MAX_ENTRIES) -> list[dict]:
    """Separate heavy text/reference encoding from diffusion model loading.

    MiniMax's conditioning nodes return an empty joint AV latent. Creating that
    empty latent in stage two preserves keyframes/references (in CONDITIONING)
    without serializing Comfy's custom NestedTensor Python class.
    """
    max_bytes, max_entries = cache_limits(max_bytes, max_entries)
    ancestors = set()

    def visit(node_id):
        if node_id in ancestors:
            return
        ancestors.add(node_id)
        for value in graph[node_id].get("inputs", {}).values():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in graph:
                visit(str(value[0]))

    visit("6")
    encode = {key: copy.deepcopy(graph[key]) for key in sorted(ancestors)}
    model_identity = [copy.deepcopy(graph[key]) for key in ("1", "2", "3", "4") if key in graph]
    descriptor = json.dumps({"schema": CACHE_SCHEMA, "mode": metadata["mode"],
                             "conditioning": encode, "models": model_identity},
                            sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    common = {"descriptor": descriptor, "max_bytes": max_bytes, "max_entries": max_entries}
    encode["90"] = {"class_type": "ForgeNeoH3ConditioningCachePrepare",
                    "inputs": {**common, "conditioning": ["6", 0]}}
    sample = copy.deepcopy(graph)
    # Retain VAE loaders required by output decoders, not CLIP or input encoders.
    for node_id in ancestors - {"3", "4"}:
        sample.pop(node_id, None)
    sample["6"] = {"class_type": "ForgeNeoH3ConditioningCacheLoad", "inputs": common.copy()}
    sample["17"] = {"class_type": "EmptyMiniMaxH3LatentAV", "inputs": {
        "width": metadata["width"], "height": metadata["height"], "length": metadata["frames"],
    }}
    sample["11"]["inputs"]["latent_image"] = ["17", 0]
    return [{"name": "encode", "workflow": encode, "allow_empty_outputs": True},
            {"name": "sample", "workflow": sample, "allow_empty_outputs": False}]


def cache_limits(max_bytes=DEFAULT_MAX_BYTES, max_entries=DEFAULT_MAX_ENTRIES):
    if isinstance(max_bytes, bool) or isinstance(max_entries, bool):
        raise ValueError("H3 cache limits must be integers")
    max_bytes, max_entries = int(max_bytes), int(max_entries)
    if not 1024 ** 2 <= max_bytes <= 128 * 1024 ** 3 or not 1 <= max_entries <= 1024:
        raise ValueError("H3 cache limits require 1 MiB–128 GiB and 1–1024 entries")
    return max_bytes, max_entries


def prepare_receipt(result_info: dict) -> dict:
    """Require a positive cache receipt, never mistake empty history for success."""
    outputs = result_info.get("node_outputs", {}) if isinstance(result_info, dict) else {}
    for output in outputs.values() if isinstance(outputs, dict) else ():
        receipts = output.get("h3_conditioning_cache", []) if isinstance(output, dict) else []
        for receipt in receipts if isinstance(receipts, list) else ():
            if (isinstance(receipt, dict) and receipt.get("ready") is True
                    and receipt.get("models_unloaded") is True):
                key = receipt.get("key", "")
                if isinstance(key, str) and len(key) == 64 and all(char in "0123456789abcdef" for char in key):
                    return dict(receipt)
    raise RuntimeError("H3 인코딩 캐시 준비 완료를 확인하지 못했습니다")

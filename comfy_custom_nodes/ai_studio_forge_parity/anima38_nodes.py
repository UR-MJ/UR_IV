"""Lazy Forge Neo aliases for the pinned Anima 3.8B ComfyUI runtime.

The vendored runtime intentionally remains byte-for-byte identical to its
upstream release.  It imports ComfyUI, torch, transformers, and safetensors, so
this adapter keeps that import behind a runtime boundary.  AI Studio's regular
Python process can therefore inspect the node contracts without installing or
initialising ComfyUI.

When this module is imported by ComfyUI, the optional bootstrap below installs
only the lightweight 52-block model-detection patch.  The full upstream runtime
and its timestep-aware Semantic Connector v2 patch remain lazy until ComfyUI
asks for one of these nodes' input schema or executes it.  This prevents an
optional Anima dependency from disabling unrelated nodes in the same pack.
"""

from __future__ import annotations

import importlib
import logging
import threading
from types import ModuleType
from typing import Any


_VENDOR_MODULE = f"{__package__}.vendor.comfyui_anima_3_8b"
_RUNTIME: ModuleType | None = None
_RUNTIME_LOCK = threading.RLock()
logger = logging.getLogger(__name__)


class Anima38RuntimeUnavailable(RuntimeError):
    """Raised when a wrapper node is invoked outside a usable ComfyUI host."""


def _import_optional_host_module(module_name: str) -> ModuleType | None:
    """Import a Comfy host module without hiding its internal import failures."""

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        missing = str(getattr(error, "name", "") or "")
        if missing in {"comfy", "comfy.model_detection", "folder_paths"}:
            return None
        raise


def _comfy_host_available() -> bool:
    """Return whether the two host modules needed during runtime import exist."""

    for module_name in ("comfy.model_detection", "folder_paths"):
        if _import_optional_host_module(module_name) is None:
            return False
    return True


def _install_pro52_detection_if_available(*, required: bool) -> bool:
    """Install upstream's small 52-block detector without loading ML libraries."""

    model_detection = _import_optional_host_module("comfy.model_detection")
    if model_detection is None:
        if required:
            raise Anima38RuntimeUnavailable(
                "Forge Neo Anima 3.8B nodes require a current ComfyUI host "
                "with comfy.model_detection available."
            )
        return False

    current = getattr(model_detection, "detect_unet_config", None)
    if not callable(current):
        raise RuntimeError("ComfyUI detect_unet_config() is unavailable.")
    if getattr(current, "_anima_qwen35_pro52_patch", False):
        return True

    def detect_unet_config(state_dict, key_prefix, metadata=None):
        config = current(state_dict, key_prefix, metadata)
        if config is None or config.get("image_model") != "anima":
            return config

        block_prefix = f"{key_prefix}blocks."
        block_indices = []
        for key in state_dict:
            if not key.startswith(block_prefix):
                continue
            index = key[len(block_prefix):].split(".", 1)[0]
            if index.isdigit():
                block_indices.append(int(index))
        if block_indices:
            block_count = max(block_indices) + 1
            if config.get("num_blocks") != block_count:
                config["num_blocks"] = block_count
                logger.info("Detected %d Anima DiT blocks", block_count)
        return config

    detect_unet_config._anima_qwen35_pro52_patch = True
    model_detection.detect_unet_config = detect_unet_config
    return True


def _install_upstream_patches(runtime: ModuleType) -> None:
    """Install both upstream patches; their marker checks make this idempotent."""

    detection_installer = getattr(runtime, "install_pro52_model_detection", None)
    if not callable(detection_installer):
        raise RuntimeError(
            "Pinned Anima runtime does not expose install_pro52_model_detection()."
        )
    detection_installer()

    semantic_runtime = importlib.import_module(
        f"{_VENDOR_MODULE}.semantic_v2_runtime"
    )
    timestep_installer = getattr(semantic_runtime, "install_timestep_support", None)
    if not callable(timestep_installer):
        raise RuntimeError(
            "Pinned Anima runtime does not expose install_timestep_support()."
        )
    timestep_installer()


def ensure_anima38_runtime(*, required: bool = True) -> ModuleType | None:
    """Load the pinned runtime and ensure its idempotent ComfyUI patches.

    A missing ComfyUI host may be tolerated by explicit callers using
    ``required=False`` because this source tree is also imported by AI Studio's
    ordinary unit tests. Missing runtime dependencies inside a present ComfyUI
    installation are deliberately not hidden.
    """

    global _RUNTIME
    if _RUNTIME is not None:
        _install_upstream_patches(_RUNTIME)
        return _RUNTIME

    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            _install_upstream_patches(_RUNTIME)
            return _RUNTIME
        if not _comfy_host_available():
            if required:
                raise Anima38RuntimeUnavailable(
                    "Forge Neo Anima 3.8B nodes require a current ComfyUI host "
                    "with comfy.model_detection and folder_paths available."
                )
            return None

        _install_pro52_detection_if_available(required=True)
        runtime = importlib.import_module(_VENDOR_MODULE)
        _install_upstream_patches(runtime)
        _RUNTIME = runtime
        return runtime


def _provider_class(name: str) -> type:
    runtime = ensure_anima38_runtime(required=True)
    mapping = getattr(runtime, "NODE_CLASS_MAPPINGS", None)
    provider = mapping.get(name) if isinstance(mapping, dict) else None
    if not isinstance(provider, type):
        raise RuntimeError(
            f"Pinned Anima runtime does not register provider node {name!r}."
        )
    return provider


def _input_types(name: str) -> dict[str, Any]:
    input_types = getattr(_provider_class(name), "INPUT_TYPES", None)
    if not callable(input_types):
        raise RuntimeError(f"Pinned Anima provider {name!r} has no INPUT_TYPES().")
    return input_types()


def _provider(name: str) -> Any:
    return _provider_class(name)()


class ForgeNeoAnimaQwen35Loader:
    """Load the Qwen3.5 4B text encoder through the pinned upstream node."""

    @classmethod
    def INPUT_TYPES(cls):
        return _input_types("AnimaQwen35Loader")

    RETURN_TYPES = ("CLIP",)
    FUNCTION = "load_clip"
    CATEGORY = "AI Studio/Forge Neo/Anima"
    TITLE = "Forge Neo Load Qwen3.5 4B (Anima)"
    DESCRIPTION = "Loads the Qwen3.5 4B text encoder used by the Anima adapter."

    def load_clip(self, qwen35_model):
        return _provider("AnimaQwen35Loader").load_clip(qwen35_model)


class ForgeNeoAnimaQwen35Prompt:
    """Encode one prompt with native and Qwen3.5 Anima text encoders."""

    @classmethod
    def INPUT_TYPES(cls):
        return _input_types("AnimaQwen35UnifiedPrompt")

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("expanded", "native")
    FUNCTION = "encode"
    CATEGORY = "AI Studio/Forge Neo/Anima"
    TITLE = "Forge Neo Qwen3.5 Prompt (Anima)"
    DESCRIPTION = "Encodes one prompt with a selected progressive-cross adapter."

    def encode(
        self,
        model,
        native_clip,
        qwen35_clip,
        adapter_name,
        prompt,
        adapter_strength,
    ):
        return _provider("AnimaQwen35UnifiedPrompt").encode(
            model,
            native_clip,
            qwen35_clip,
            adapter_name,
            prompt,
            adapter_strength,
        )


class ForgeNeoAnima38V2Loader:
    """Load the bundled Anima 3.8B DiT and Semantic Connector v2."""

    @classmethod
    def INPUT_TYPES(cls):
        return _input_types("Anima38BV2Loader")

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load_model"
    CATEGORY = "AI Studio/Forge Neo/Anima"
    TITLE = "Forge Neo Anima 3.8B v2"
    DESCRIPTION = "Loads the bundled Anima 3.8B DiT and Semantic Connector v2."

    def load_model(self, model_name):
        return _provider("Anima38BV2Loader").load_model(model_name)


class ForgeNeoAnima38V2Prompt:
    """Create fixed-strength v2 conditioning and release both text encoders."""

    @classmethod
    def INPUT_TYPES(cls):
        return _input_types("Anima38BV2Prompt")

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("expanded", "native")
    FUNCTION = "encode"
    CATEGORY = "AI Studio/Forge Neo/Anima"
    TITLE = "Forge Neo Anima 3.8B v2 Prompt"
    DESCRIPTION = (
        "Creates fixed-strength Semantic Connector v2 conditioning and releases "
        "both text encoders."
    )

    def encode(self, model, native_clip, qwen35_clip, prompt):
        return _provider("Anima38BV2Prompt").encode(
            model,
            native_clip,
            qwen35_clip,
            prompt,
        )


NODE_CLASS_MAPPINGS = {
    "ForgeNeoAnimaQwen35Loader": ForgeNeoAnimaQwen35Loader,
    "ForgeNeoAnimaQwen35Prompt": ForgeNeoAnimaQwen35Prompt,
    "ForgeNeoAnima38V2Loader": ForgeNeoAnima38V2Loader,
    "ForgeNeoAnima38V2Prompt": ForgeNeoAnima38V2Prompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ForgeNeoAnimaQwen35Loader": "Forge Neo Load Qwen3.5 4B (Anima)",
    "ForgeNeoAnimaQwen35Prompt": "Forge Neo Qwen3.5 Prompt (Anima)",
    "ForgeNeoAnima38V2Loader": "Forge Neo Anima 3.8B v2",
    "ForgeNeoAnima38V2Prompt": "Forge Neo Anima 3.8B v2 Prompt",
}


# Install only the dependency-free detection hook during custom-node import.
# The full torch/transformers runtime stays lazy until INPUT_TYPES or execution.
# Outside ComfyUI this is an intentional no-op.
_install_pro52_detection_if_available(required=False)


__all__ = [
    "Anima38RuntimeUnavailable",
    "ForgeNeoAnimaQwen35Loader",
    "ForgeNeoAnimaQwen35Prompt",
    "ForgeNeoAnima38V2Loader",
    "ForgeNeoAnima38V2Prompt",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "ensure_anima38_runtime",
]

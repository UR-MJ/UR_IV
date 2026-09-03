from __future__ import annotations

import logging
import os

from safetensors import SafetensorError, safe_open

import comfy.model_management
import comfy.ops
import comfy.sd
import comfy.utils
import folder_paths

from .bundle_v2 import BUNDLE_ARCHITECTURE, BUNDLE_FORMAT, CONNECTOR_PREFIX
from .prompt import AnimaQwen35UnifiedPrompt, V2_ARCHITECTURE
from .semantic_connector_v2 import QualityAnchoredSemanticConnectorV2
from .semantic_v2_runtime import emit_conditioning


logger = logging.getLogger(__name__)
LAYER_INDICES = (7, 15, 23, 31)


def bundle_candidates() -> list[str]:
    candidates = []
    for name in folder_paths.get_filename_list("diffusion_models"):
        if not name.lower().endswith(".safetensors"):
            continue
        path = folder_paths.get_full_path("diffusion_models", name)
        if path is None or not os.path.isfile(path):
            continue
        try:
            with safe_open(path, framework="pt", device="cpu") as checkpoint:
                metadata = checkpoint.metadata() or {}
                if (
                    metadata.get("architecture") == BUNDLE_ARCHITECTURE
                    and metadata.get("anima_v2_bundle_format") == BUNDLE_FORMAT
                ):
                    candidates.append(name)
        except (OSError, ValueError, SafetensorError):
            continue
    return sorted(candidates) or ["Anima-3.8B-v2.safetensors"]


def _adapter_metadata(metadata: dict[str, str]) -> dict[str, str]:
    prefix = "anima_v2_adapter_"
    return {
        name[len(prefix):]: value
        for name, value in metadata.items()
        if name.startswith(prefix)
    }


def _connector_config(metadata: dict[str, str]) -> dict[str, object]:
    adapter = _adapter_metadata(metadata)
    if adapter.get("architecture") != V2_ARCHITECTURE:
        raise RuntimeError("The bundled connector is not Semantic Connector v2.")
    return {
        "num_queries": int(adapter.get("semantic_query_tokens", "64")),
        "resampler_blocks": int(adapter.get("semantic_resampler_blocks", "6")),
        "resampler_dim": int(adapter.get("semantic_resampler_dim", "2048")),
        "resampler_heads": int(adapter.get("semantic_resampler_heads", "16")),
        "mlp_hidden_dim": int(
            adapter.get("semantic_resampler_mlp_hidden_dim", "5632")
        ),
        "initialize_from_native": False,
        "register_native_adapter": False,
        "initialize_resampler": False,
    }


def load_bundled_v2_model(
    bundle_path: str,
    model_options: dict | None = None,
    disable_dynamic: bool = False,
):
    model_options = model_options or {}
    state, metadata = comfy.utils.load_torch_file(
        bundle_path, return_metadata=True
    )
    metadata = metadata or {}
    if (
        metadata.get("architecture") != BUNDLE_ARCHITECTURE
        or metadata.get("anima_v2_bundle_format") != BUNDLE_FORMAT
    ):
        raise RuntimeError(f"Not an {BUNDLE_ARCHITECTURE} checkpoint: {bundle_path}")

    connector_prefix = metadata.get("anima_v2_connector_prefix", CONNECTOR_PREFIX)
    connector_state = {
        name[len(connector_prefix):]: state.pop(name)
        for name in list(state)
        if name.startswith(connector_prefix)
    }
    if not connector_state:
        raise RuntimeError("The bundled checkpoint contains no connector tensors.")

    model = comfy.sd.load_diffusion_model_state_dict(
        state,
        model_options=model_options,
        metadata=metadata,
        disable_dynamic=disable_dynamic,
    )
    if model is None:
        raise RuntimeError(f"Could not load the bundled Anima model: {bundle_path}")

    base_model = model.model
    diffusion_model = getattr(base_model, "diffusion_model", None)
    native_adapter = getattr(diffusion_model, "llm_adapter", None)
    if native_adapter is None or len(native_adapter.blocks) != 6:
        raise RuntimeError("The bundled checkpoint is not a compatible Anima model.")

    operations = base_model.model_config.custom_operations
    if operations is None:
        operations = comfy.ops.pick_operations(
            base_model.get_dtype(),
            base_model.manual_cast_dtype,
            fp8_optimizations=base_model.model_config.optimizations.get(
                "fp8", False
            ),
            model_config=base_model.model_config,
        )
    connector = QualityAnchoredSemanticConnectorV2(
        native_adapter=native_adapter,
        semantic_source_dim=2560,
        layer_indices=LAYER_INDICES,
        operations=operations,
        **_connector_config(metadata),
    )
    connector.load_trainable_state_dict(
        connector_state,
        assign=model.is_dynamic(),
    )
    connector.eval().requires_grad_(False)
    connector._anima_v2_model_managed = True
    connector._anima_v2_bundle_path = bundle_path
    diffusion_model.add_module("anima_v2_connector", connector)
    comfy.model_management.archive_model_dtypes(connector)
    model.size = 0
    model.cached_patcher_init = (
        load_bundled_v2_model,
        (bundle_path, model_options),
    )
    logger.info(
        "Loaded bundled anima.3-8B-v2 model: %s",
        os.path.basename(bundle_path),
    )
    return model


class Anima38BV2Loader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model_name": (bundle_candidates(),)}}

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load_model"
    CATEGORY = "loaders/Anima"
    TITLE = "anima.3-8B-v2"
    DESCRIPTION = "Loads the bundled Anima 3.8B DiT and Semantic Connector v2."

    def load_model(self, model_name):
        bundle_path = folder_paths.get_full_path("diffusion_models", model_name)
        if bundle_path is None or not os.path.isfile(bundle_path):
            raise FileNotFoundError(f"Bundled anima.3-8B-v2 model not found: {model_name}")
        return (load_bundled_v2_model(bundle_path),)


class Anima38BV2Prompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "native_clip": ("CLIP",),
                "qwen35_clip": ("CLIP",),
                "prompt": ("STRING", {
                    "multiline": True,
                    "dynamicPrompts": True,
                    "tooltip": "One prompt shared by both Anima text encoders.",
                }),
            }
        }

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("expanded", "native")
    FUNCTION = "encode"
    CATEGORY = "conditioning/Anima"
    TITLE = "anima.3-8B-v2 Prompt"
    DESCRIPTION = "Creates fixed-strength v2 conditioning and releases both text encoders."

    @staticmethod
    def _unload_clip(clip) -> None:
        comfy.model_management.unload_model_and_clones(
            clip.patcher,
            unload_additional_models=False,
            all_devices=True,
        )

    def encode(self, model, native_clip, qwen35_clip, prompt):
        try:
            native = AnimaQwen35UnifiedPrompt._encode_native(native_clip, prompt)
        finally:
            self._unload_clip(native_clip)

        native_source, native_metadata = native[0]
        if native_source.ndim != 3 or native_source.shape[-1] != 1024:
            raise RuntimeError("native_clip must be Anima's native Qwen3 0.6B encoder.")
        if native_metadata.get("t5xxl_ids") is None:
            raise RuntimeError("Native Anima conditioning has no T5 token IDs.")

        try:
            semantic_states, semantic_mask = (
                AnimaQwen35UnifiedPrompt._encode_semantic_layers(
                    qwen35_clip, prompt
                )
            )
        finally:
            self._unload_clip(qwen35_clip)

        diffusion_model = getattr(model.model, "diffusion_model", None)
        native_adapter = getattr(diffusion_model, "llm_adapter", None)
        connector = getattr(diffusion_model, "anima_v2_connector", None)
        if native_adapter is None or connector is None:
            raise RuntimeError("model must come from the anima.3-8B-v2 loader.")

        bundle_path = getattr(connector, "_anima_v2_bundle_path", "anima.3-8B-v2")
        return emit_conditioning(
            expanded_adapter=connector,
            native_adapter=native_adapter,
            native=native,
            native_source=native_source,
            native_metadata=native_metadata,
            semantic_states=semantic_states,
            semantic_mask=semantic_mask,
            adapter_strength=1.0,
            architecture=V2_ARCHITECTURE,
            checkpoint_path=bundle_path,
        )

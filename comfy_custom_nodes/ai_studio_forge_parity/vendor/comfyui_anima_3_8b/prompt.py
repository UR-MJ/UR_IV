from __future__ import annotations

import logging
import os

import torch
import torch.nn.functional as F
import safetensors.torch
from safetensors import SafetensorError, safe_open

import comfy.model_management
import comfy.ops
import folder_paths

from .progressive_cross_adapter import ProgressiveQwen35CrossAdapter
from .semantic_v2_runtime import emit_conditioning, load_adapter

logger = logging.getLogger(__name__)
EXPECTED_ARCHITECTURE = "anima_progressive_qwen35_cross_adapter_v1"
V2_ARCHITECTURE = "anima_qwen35_quality_anchored_semantic_connector_v2"
SUPPORTED_ARCHITECTURES = {EXPECTED_ARCHITECTURE, V2_ARCHITECTURE}
LAYER_INDICES = (7, 15, 23, 31)


def adapter_candidates():
    candidates = []
    for name in folder_paths.get_filename_list("text_encoders"):
        if not name.lower().endswith(".safetensors"):
            continue
        path = folder_paths.get_full_path("text_encoders", name)
        if path is None or not os.path.isfile(path):
            continue
        try:
            with safe_open(path, framework="pt", device="cpu") as checkpoint:
                metadata = checkpoint.metadata() or {}
                keys = checkpoint.keys()
                if metadata.get("architecture") not in SUPPORTED_ARCHITECTURES:
                    continue
                is_v2 = metadata.get("architecture") == V2_ARCHITECTURE
                if not is_v2 and any(key.startswith("timestep_gates.") for key in keys):
                    continue
                if not is_v2 and any(key.startswith("anchor_deviation") for key in keys):
                    continue
                # Joint training checkpoints also contain absolute DiT block
                # weights. They must first be materialized into a MODEL + clean
                # adapter pair; offering them here leads to a misleading adapter
                # state-dict mismatch and, worse, would omit the trained DiT.
                if any(key.startswith("dit_blocks.") for key in keys):
                    continue
        except (OSError, ValueError, SafetensorError):
            continue
        candidates.append(name)
    return sorted(candidates) or ["qwen35_expanded_adapter.safetensors"]


def _pad_context(context, length=512):
    if context.shape[1] >= length:
        return context[:, :length]
    return F.pad(context, (0, 0, 0, length - context.shape[1]))


class AnimaQwen35UnifiedPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "native_clip": ("CLIP",),
                "qwen35_clip": ("CLIP",),
                "adapter_name": (adapter_candidates(),),
                "prompt": ("STRING", {
                    "multiline": True,
                    "dynamicPrompts": True,
                    "tooltip": "One prompt shared by both Anima text encoders.",
                }),
                "adapter_strength": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.05,
                    "tooltip": "1.0 is trained strength; 0.0 is native Anima.",
                }),
            }
        }

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("expanded", "native")
    FUNCTION = "encode"
    CATEGORY = "conditioning/Anima"
    TITLE = "Qwen3.5 Unified Prompt (Anima)"
    DESCRIPTION = (
        "Encodes one prompt with a selected progressive-cross adapter. "
    )

    @staticmethod
    def _encode_native(clip, text):
        conditioning = clip.encode_from_tokens_scheduled(clip.tokenize(text))
        if len(conditioning) != 1:
            raise RuntimeError("Unified Prompt expects one unscheduled native prompt.")
        return conditioning

    @staticmethod
    def _encode_semantic_layers(clip, text):
        tokens = clip.tokenize(text)
        token_pairs = tokens.get("qwen35_4b")
        if token_pairs is None:
            raise RuntimeError(
                "qwen35_clip must come from Load Qwen3.5 4B (Anima)."
            )

        clip.load_model(tokens)
        execution_device = clip.patcher.load_device
        try:
            inner = clip.cond_stage_model.qwen35_4b
        except AttributeError as error:
            raise RuntimeError(
                "qwen35_clip must come from Load Qwen3.5 4B (Anima)."
            ) from error

        inner.set_clip_options({"execution_device": execution_device})
        with comfy.model_management.cuda_device_context(execution_device):
            states, attention_mask = inner.raw_hidden_states(
                token_pairs,
                LAYER_INDICES,
                execution_device,
            )

        intermediate_device = comfy.model_management.intermediate_device()
        return (
            [
                state.to(device=intermediate_device, dtype=torch.bfloat16)
                for state in states
            ],
            attention_mask.to(intermediate_device),
        )

    @staticmethod
    def _native_adapter(model):
        base_model = getattr(model, "model", None)
        diffusion_model = getattr(base_model, "diffusion_model", None)
        adapter = getattr(diffusion_model, "llm_adapter", None)
        if adapter is None:
            raise RuntimeError("The MODEL input is not a compatible Anima model.")
        if len(adapter.blocks) != 6:
            raise RuntimeError(
                f"Expected Anima's 6-block LLM adapter, got {len(adapter.blocks)} blocks."
            )
        return adapter

    @staticmethod
    def _checkpoint(adapter_name):
        checkpoint_path = folder_paths.get_full_path("text_encoders", adapter_name)
        if checkpoint_path is None or not os.path.isfile(checkpoint_path):
            raise FileNotFoundError(f"Adapter not found: {adapter_name}")
        with safe_open(checkpoint_path, framework="pt", device="cpu") as checkpoint:
            metadata = checkpoint.metadata() or {}
            keys = set(checkpoint.keys())
        architecture = metadata.get("architecture", "")
        if architecture not in SUPPORTED_ARCHITECTURES:
            raise RuntimeError(
                f"{adapter_name} uses {architecture or 'no architecture metadata'}; "
                f"expected one of {sorted(SUPPORTED_ARCHITECTURES)}."
            )
        is_v2 = architecture == V2_ARCHITECTURE
        if not is_v2 and any(key.startswith("timestep_gates.") for key in keys):
            raise RuntimeError("Timestep-gated adapters are not supported by this node.")
        if not is_v2 and any(key.startswith("anchor_deviation") for key in keys):
            raise RuntimeError("De-anchored adapters are not supported by this node.")
        if any(key.startswith("dit_blocks.") for key in keys):
            raise RuntimeError(
                f"{adapter_name} is a joint adapter+DiT checkpoint, not a standalone "
                "text-encoder adapter. Materialize it into a diffusion-model checkpoint "
                "and an adapter-only checkpoint, then select that matched pair."
            )
        return checkpoint_path, metadata

    def encode(
        self,
        model,
        native_clip,
        qwen35_clip,
        adapter_name,
        prompt,
        adapter_strength,
    ):
        checkpoint_path, checkpoint_metadata = self._checkpoint(adapter_name)
        native = self._encode_native(native_clip, prompt)
        if adapter_strength == 0.0:
            return native, native

        native_source, native_metadata = native[0]
        if native_source.ndim != 3 or native_source.shape[-1] != 1024:
            raise RuntimeError(
                "native_clip must be Anima's native Qwen3 0.6B encoder."
            )
        target_ids = native_metadata.get("t5xxl_ids")
        if target_ids is None:
            raise RuntimeError("Native Anima conditioning has no T5 token IDs.")

        semantic_states, semantic_mask = self._encode_semantic_layers(
            qwen35_clip, prompt
        )
        comfy.model_management.load_models_gpu([model], force_full_load=True)
        native_adapter = self._native_adapter(model)
        device = native_adapter.embed.weight.device
        dtype = native_adapter.embed.weight.dtype
        source = native_source.to(device=device, dtype=dtype)
        semantic_states = [
            state.to(device=device, dtype=dtype) for state in semantic_states
        ]
        semantic_mask = semantic_mask.to(device=device, dtype=torch.bool)
        target_ids = torch.as_tensor(
            target_ids, device=device, dtype=torch.long
        ).reshape(1, -1)[:, :512]

        architecture = checkpoint_metadata.get("architecture", "")
        if architecture == V2_ARCHITECTURE:
            connector_config = {
                "num_queries": int(checkpoint_metadata.get(
                    "semantic_query_tokens", "64"
                )),
                "resampler_blocks": int(checkpoint_metadata.get(
                    "semantic_resampler_blocks", "6"
                )),
                "resampler_dim": int(checkpoint_metadata.get(
                    "semantic_resampler_dim", "2048"
                )),
                "resampler_heads": int(checkpoint_metadata.get(
                    "semantic_resampler_heads", "16"
                )),
                "mlp_hidden_dim": int(checkpoint_metadata.get(
                    "semantic_resampler_mlp_hidden_dim", "5632"
                )),
                "initialize_from_native": False,
                "initialize_resampler": False,
            }
            expanded_adapter = load_adapter(
                checkpoint_path=checkpoint_path,
                native_adapter=native_adapter,
                device=device,
                connector_config=connector_config,
            )
            return emit_conditioning(
                expanded_adapter=expanded_adapter,
                native_adapter=native_adapter,
                native=native,
                native_source=native_source,
                native_metadata=native_metadata,
                semantic_states=semantic_states,
                semantic_mask=semantic_mask,
                adapter_strength=adapter_strength,
                architecture=architecture,
                checkpoint_path=checkpoint_path,
            )

        expanded_adapter = ProgressiveQwen35CrossAdapter(
            native_adapter=native_adapter,
            semantic_source_dim=2560,
            layer_indices=LAYER_INDICES,
            operations=comfy.ops.disable_weight_init,
        )
        state_dict = safetensors.torch.load_file(
            checkpoint_path, device=str(device)
        )
        expanded_adapter.load_trainable_state_dict(state_dict)
        expanded_adapter.eval()

        expanded_context = expanded_adapter(
            source,
            target_ids,
            semantic_states,
            semantic_source_mask=semantic_mask,
            include_inserted_blocks=True,
        )
        native_context_scale = float(
            checkpoint_metadata.get("native_context_scale", "1.0")
        )
        native_context = None
        if native_context_scale != 1.0 or adapter_strength != 1.0:
            native_context = native_adapter(source, target_ids)
        if native_context_scale != 1.0:
            # Preserve the learned Qwen residual E-N while scaling only the
            # frozen native anchor: scale*N + (E-N) == E + (scale-1)*N.
            expanded_context = expanded_context + (
                native_context_scale - 1.0
            ) * native_context
        if adapter_strength != 1.0:
            expanded_context = native_context + float(adapter_strength) * (
                expanded_context - native_context
            )

        target_weights = native_metadata.get("t5xxl_weights")
        if target_weights is not None:
            weights = torch.as_tensor(
                target_weights, device=device, dtype=expanded_context.dtype
            ).reshape(1, -1, 1)[:, :expanded_context.shape[1]]
            expanded_context = expanded_context * weights
        expanded_context = _pad_context(expanded_context)
        expanded_context = expanded_context.to(
            comfy.model_management.intermediate_device()
        )

        output_metadata = {
            key: value for key, value in native_metadata.items()
            if key not in {"t5xxl_ids", "t5xxl_weights", "attention_mask"}
        }
        output_metadata.update({
            "qwen35_expanded_adapter": os.path.basename(checkpoint_path),
            "qwen35_expanded_strength": float(adapter_strength),
            "qwen35_expanded_architecture": EXPECTED_ARCHITECTURE,
            "qwen35_expanded_step": checkpoint_metadata.get("step", ""),
            "qwen35_native_context_scale": native_context_scale,
        })
        logger.info(
            "Encoded Anima prompt with %s at strength %.2f",
            adapter_name,
            adapter_strength,
        )
        return [[expanded_context, output_metadata]], native

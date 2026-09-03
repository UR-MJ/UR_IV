from __future__ import annotations

import logging
import os

import safetensors.torch

import comfy.sd
import comfy.utils
from comfy.supported_models_base import ClipTarget
import folder_paths

from .text_encoder import AnimaQwen35Tokenizer, text_encoder_factory

logger = logging.getLogger(__name__)


class AnimaQwen35Loader:
    @classmethod
    def INPUT_TYPES(cls):
        def is_qwen35_4b(name):
            filename = str(name).replace("\\", "/").rsplit("/", 1)[-1].lower()
            markers = ("qwen35_4b", "qwen3.5-4b", "qwen3_5_4b")
            return filename.endswith(".safetensors") and any(
                marker in filename for marker in markers
            )

        candidates = sorted({
            name for name in folder_paths.get_filename_list("text_encoders")
            if is_qwen35_4b(name)
        })
        preferred = "qwen35_4b.safetensors"
        if preferred in candidates:
            candidates.remove(preferred)
            candidates.insert(0, preferred)
        if not candidates:
            candidates = [preferred]
        return {"required": {"qwen35_model": (candidates,)}}

    RETURN_TYPES = ("CLIP",)
    FUNCTION = "load_clip"
    CATEGORY = "loaders/Anima"
    TITLE = "Load Qwen3.5 4B (Anima)"
    DESCRIPTION = "Loads the Qwen3.5 4B text encoder used by the Anima adapter."

    def load_clip(self, qwen35_model):
        clip_path = folder_paths.get_full_path("text_encoders", qwen35_model)
        if clip_path is None or not os.path.isfile(clip_path):
            raise FileNotFoundError(f"Qwen3.5 text encoder not found: {qwen35_model}")

        state_dict = safetensors.torch.load_file(clip_path)
        detection = {}
        for key in (
            "model.norm.weight",
            "model.layers.0.input_layernorm.weight",
            "norm.1.weight",
            "layers.0.input_layernorm.weight",
        ):
            if key in state_dict:
                detection["dtype_llama"] = state_dict[key].dtype
                break
        quantization = comfy.utils.detect_layer_quantization(state_dict, "")
        if quantization is not None:
            detection["llama_quantization_metadata"] = quantization

        target = ClipTarget(
            AnimaQwen35Tokenizer,
            text_encoder_factory(**detection),
        )
        parameter_count = sum(tensor.numel() for tensor in state_dict.values())
        clip = comfy.sd.CLIP(
            target=target,
            state_dict=[state_dict],
            parameters=parameter_count,
        )
        logger.info("Loaded Qwen3.5 text encoder: %s", qwen35_model)
        return (clip,)


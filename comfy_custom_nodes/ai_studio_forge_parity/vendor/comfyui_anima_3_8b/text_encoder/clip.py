from __future__ import annotations

import torch

import comfy.sd1_clip

from .model import Qwen35HybridModel


class Qwen35ClipModel(comfy.sd1_clip.SDClipModel):
    def __init__(
        self,
        device="cpu",
        layer="last",
        layer_idx=None,
        dtype=None,
        attention_mask=True,
        model_options=None,
    ):
        super().__init__(
            device=device,
            layer=layer,
            layer_idx=layer_idx,
            textmodel_json_config={},
            dtype=dtype,
            special_tokens={"pad": 151643},
            layer_norm_hidden_state=False,
            model_class=Qwen35HybridModel,
            enable_attention_masks=attention_mask,
            return_attention_masks=attention_mask,
            model_options=model_options or {},
        )

    def raw_hidden_states(self, tokens, layer_indices, execution_device):
        if len(tokens) != 1:
            raise RuntimeError(
                "Qwen3.5 Unified Prompt supports one prompt of at most 1024 tokens."
            )

        token_ids = []
        for item in tokens[0]:
            token = item[0] if isinstance(item, (tuple, list)) else item
            if not isinstance(token, int):
                raise RuntimeError(
                    "Textual-inversion embeddings are not supported by the Qwen3.5 input."
                )
            token_ids.append(token)

        embeds, attention_mask, num_tokens, embeds_info = self.process_tokens(
            [token_ids], execution_device
        )
        outputs = self.transformer(
            None,
            attention_mask,
            embeds=embeds,
            num_tokens=num_tokens,
            intermediate_output=list(layer_indices),
            final_layer_norm_intermediate=False,
            dtype=torch.float32,
            embeds_info=embeds_info,
        )
        intermediate = outputs[1]
        if not isinstance(intermediate, dict):
            raise RuntimeError("Qwen3.5 did not return the requested hidden layers.")
        return [intermediate[index].float() for index in layer_indices], attention_mask


class AnimaQwen35TextEncoder(comfy.sd1_clip.SD1ClipModel):
    def __init__(self, device="cpu", dtype=None, model_options=None):
        super().__init__(
            device=device,
            dtype=dtype,
            name="qwen35_4b",
            clip_model=Qwen35ClipModel,
            model_options=model_options or {},
        )

    def encode_token_weights(self, token_weight_pairs):
        output = super().encode_token_weights(token_weight_pairs)
        if "t5xxl" in token_weight_pairs:
            output[2]["t5xxl_ids"] = torch.tensor(
                [item[0] for item in token_weight_pairs["t5xxl"][0]],
                dtype=torch.int,
            )
            output[2]["t5xxl_weights"] = torch.tensor(
                [item[1] for item in token_weight_pairs["t5xxl"][0]]
            )
        return output


def text_encoder_factory(dtype_llama=None, llama_quantization_metadata=None):
    class ConfiguredAnimaQwen35TextEncoder(AnimaQwen35TextEncoder):
        def __init__(self, device="cpu", dtype=None, model_options=None):
            if dtype_llama is not None:
                dtype = dtype_llama
            options = dict(model_options or {})
            if llama_quantization_metadata is not None:
                options["quantization_metadata"] = llama_quantization_metadata
            super().__init__(device=device, dtype=dtype, model_options=options)

    return ConfiguredAnimaQwen35TextEncoder


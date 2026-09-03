from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn

from comfy.ldm.anima.model import Attention


class ProgressiveQwen35CrossAdapter(nn.Module):
    """Parameter-efficient LLaMA-Pro expansion of Anima's text connector.

    The inherited six connector blocks are frozen.  After each one, a new
    Qwen3.5 cross-attention residual is inserted.
    """

    architecture = "anima_progressive_qwen35_cross_adapter_v1"

    def __init__(
        self,
        native_adapter: nn.Module,
        semantic_source_dim: int,
        layer_indices: Sequence[int],
        operations,
        register_native_adapter: bool = True,
    ) -> None:
        super().__init__()
        if register_native_adapter:
            self.native_adapter = native_adapter
            object.__setattr__(self, "_unregistered_native_adapter", None)
        else:
            # Keep the shared module reachable without registering it as a child.
            # It remains owned, moved and serialized exactly once by the DiT.
            object.__setattr__(
                self,
                "_unregistered_native_adapter",
                native_adapter,
            )
        self.layer_indices = tuple(int(index) for index in layer_indices)
        model_dim = native_adapter.embed.weight.shape[1]
        num_heads = native_adapter.blocks[0].self_attn.n_heads
        head_dim = model_dim // num_heads
        device = native_adapter.embed.weight.device
        dtype = native_adapter.embed.weight.dtype

        self.query_norms = nn.ModuleList([
            operations.RMSNorm(model_dim, eps=1e-6, device=device, dtype=dtype)
            for _ in native_adapter.blocks
        ])
        self.source_norms = nn.ModuleList([
            operations.RMSNorm(
                semantic_source_dim, eps=1e-6, device=device, dtype=dtype
            )
            for _ in native_adapter.blocks
        ])
        self.semantic_attentions = nn.ModuleList([
            Attention(
                query_dim=model_dim,
                context_dim=semantic_source_dim,
                n_heads=num_heads,
                head_dim=head_dim,
                device=device,
                dtype=dtype,
                operations=operations,
            )
            for _ in native_adapter.blocks
        ])
        self.layer_mix_logits = nn.Parameter(torch.zeros(
            len(native_adapter.blocks),
            len(self.layer_indices),
            device=device,
            dtype=dtype,
        ))

        if not self._has_unmaterialized_parameters():
            self._initialize_from_native()
        self.set_trainability()

    def get_native_adapter(self) -> nn.Module:
        native_adapter = getattr(self, "native_adapter", None)
        if native_adapter is None:
            native_adapter = self._unregistered_native_adapter
        if native_adapter is None:
            raise RuntimeError("The embedded Anima native adapter is no longer available.")
        return native_adapter

    def _has_unmaterialized_parameters(self) -> bool:
        return any(
            hasattr(module, "weight") and module.weight is None
            for module in self.modules()
        )

    @torch.no_grad()
    def _initialize_from_native(self) -> None:
        native_adapter = self.get_native_adapter()
        for native, query_norm, source_norm, attention in zip(
            native_adapter.blocks,
            self.query_norms,
            self.source_norms,
            self.semantic_attentions,
        ):
            query_norm.weight.copy_(native.norm_cross_attn.weight)
            attention.q_proj.weight.copy_(native.cross_attn.q_proj.weight)
            attention.q_norm.weight.copy_(native.cross_attn.q_norm.weight)
            attention.k_norm.weight.copy_(native.cross_attn.k_norm.weight)
            nn.init.xavier_uniform_(attention.k_proj.weight)
            nn.init.xavier_uniform_(attention.v_proj.weight)
            attention.o_proj.weight.zero_()
            source_norm.weight.fill_(1.0)

        if self.layer_mix_logits.shape[1] > 1:
            self.layer_mix_logits.copy_(torch.linspace(
                -0.5,
                0.5,
                self.layer_mix_logits.shape[1],
                device=self.layer_mix_logits.device,
                dtype=self.layer_mix_logits.dtype,
            ).repeat(self.layer_mix_logits.shape[0], 1))

    def set_trainability(self, gates_only: bool = False) -> None:
        if gates_only:
            raise ValueError("ProgressiveQwen35CrossAdapter has no gates")
        self.get_native_adapter().requires_grad_(False)
        for name, parameter in self.named_parameters():
            parameter.requires_grad_(not name.startswith("native_adapter."))

    @staticmethod
    def _attention_mask(mask: torch.Tensor | None) -> torch.Tensor | None:
        if mask is None:
            return None
        mask = mask.to(torch.bool)
        return mask.unsqueeze(1).unsqueeze(1) if mask.ndim == 2 else mask

    @staticmethod
    def _mixed_source(
        hidden_states: Sequence[torch.Tensor],
        mix: torch.Tensor,
        block_index: int,
    ) -> torch.Tensor:
        return sum(
            hidden * mix[block_index, layer_index]
            for layer_index, hidden in enumerate(hidden_states)
        )

    def forward(
        self,
        native_source: torch.Tensor,
        target_input_ids: torch.Tensor,
        semantic_hidden_states: Sequence[torch.Tensor],
        target_attention_mask: torch.Tensor | None = None,
        native_source_mask: torch.Tensor | None = None,
        semantic_source_mask: torch.Tensor | None = None,
        include_inserted_blocks: bool = True,
        **_ignored,
    ) -> torch.Tensor:
        if len(semantic_hidden_states) != len(self.layer_indices):
            raise ValueError(
                f"Expected {len(self.layer_indices)} semantic layers, "
                f"got {len(semantic_hidden_states)}"
            )

        target_attention_mask = self._attention_mask(target_attention_mask)
        native_source_mask = self._attention_mask(native_source_mask)
        semantic_source_mask = self._attention_mask(semantic_source_mask)

        native_adapter = self.get_native_adapter()
        x = native_adapter.in_proj(
            native_adapter.embed(
                target_input_ids, out_dtype=native_source.dtype
            )
        )
        query_positions = torch.arange(x.shape[1], device=x.device).unsqueeze(0)
        native_positions = torch.arange(
            native_source.shape[1], device=x.device
        ).unsqueeze(0)
        semantic_positions = torch.arange(
            semantic_hidden_states[0].shape[1], device=x.device
        ).unsqueeze(0)
        query_rope = native_adapter.rotary_emb(x, query_positions)
        native_rope = native_adapter.rotary_emb(x, native_positions)
        semantic_rope = native_adapter.rotary_emb(x, semantic_positions)
        mix = self.layer_mix_logits.float().softmax(dim=-1).to(dtype=x.dtype)

        for index, native_block in enumerate(native_adapter.blocks):
            x = native_block(
                x,
                native_source,
                target_attention_mask=target_attention_mask,
                source_attention_mask=native_source_mask,
                position_embeddings=query_rope,
                position_embeddings_context=native_rope,
            )
            if include_inserted_blocks:
                semantic_source = self.source_norms[index](self._mixed_source(
                    semantic_hidden_states, mix, index
                ))
                x = x + self.semantic_attentions[index](
                    self.query_norms[index](x),
                    mask=semantic_source_mask,
                    context=semantic_source,
                    position_embeddings=query_rope,
                    position_embeddings_context=semantic_rope,
                )

        return native_adapter.norm(native_adapter.out_proj(x))

    def trainable_state_dict(self) -> dict[str, torch.Tensor]:
        return {
            name: value.detach().cpu()
            for name, value in self.state_dict().items()
            if not name.startswith("native_adapter.")
        }

    def load_trainable_state_dict(self, state: dict[str, torch.Tensor]) -> None:
        if self._has_unmaterialized_parameters():
            incompatible = self.load_state_dict(state, strict=False)
            missing = sorted(
                name for name in incompatible.missing_keys
                if not name.startswith("native_adapter.")
            )
            unexpected = sorted(incompatible.unexpected_keys)
        else:
            current = self.state_dict()
            expected = {
                name for name in current if not name.startswith("native_adapter.")
            }
            missing = sorted(expected - set(state))
            unexpected = sorted(set(state) - expected)
            if not missing and not unexpected:
                current.update(state)
                self.load_state_dict(current, strict=True)
        if missing or unexpected:
            raise RuntimeError(
                f"Cross-adapter checkpoint mismatch: missing={missing}, "
                f"unexpected={unexpected}"
            )
        self.set_trainability()

    def parameter_report(self) -> dict[str, int]:
        frozen = sum(
            parameter.numel()
            for parameter in self.get_native_adapter().parameters()
        )
        trainable = sum(
            parameter.numel() for parameter in self.parameters()
            if parameter.requires_grad
        )
        return {
            "frozen_native": frozen,
            "trainable_cross_attentions": sum(
                parameter.numel() for parameter in self.semantic_attentions.parameters()
            ),
            "trainable_norms": sum(
                parameter.numel() for parameter in self.query_norms.parameters()
            ) + sum(parameter.numel() for parameter in self.source_norms.parameters()),
            "trainable_routing": self.layer_mix_logits.numel(),
            "total_trainable": trainable,
            "total_parameters": sum(parameter.numel() for parameter in self.parameters()),
        }

    def anchor_profile(self) -> dict:
        return {}

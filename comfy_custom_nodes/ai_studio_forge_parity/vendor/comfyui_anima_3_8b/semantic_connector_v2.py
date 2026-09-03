from __future__ import annotations

import math
from collections.abc import Sequence

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.checkpoint import checkpoint

from comfy.ldm.anima.model import Attention
from .progressive_cross_adapter import ProgressiveQwen35CrossAdapter


def sinusoidal_timestep_embedding(
    timesteps: torch.Tensor,
    dim: int,
    max_period: int = 10_000,
) -> torch.Tensor:
    """Embed Anima's continuous [0, 1] flow timestep without changing dtype."""
    half = dim // 2
    frequencies = torch.exp(
        -math.log(max_period)
        * torch.arange(half, device=timesteps.device, dtype=torch.float32)
        / max(half, 1)
    )
    angles = timesteps.float().reshape(-1, 1) * 1_000.0 * frequencies.reshape(1, -1)
    embedding = torch.cat((angles.cos(), angles.sin()), dim=-1)
    if dim % 2:
        embedding = F.pad(embedding, (0, 1))
    return embedding


class MultiHeadAttention(nn.Module):
    """SDPA attention with independently sized query and context streams."""

    def __init__(
        self,
        query_dim: int,
        context_dim: int,
        num_heads: int,
        device: torch.device,
        dtype: torch.dtype,
        operations,
    ) -> None:
        super().__init__()
        if query_dim % num_heads:
            raise ValueError("query_dim must be divisible by num_heads")
        self.num_heads = num_heads
        self.head_dim = query_dim // num_heads
        self.query_dim = query_dim
        self.q_proj = operations.Linear(query_dim, query_dim, bias=False, device=device, dtype=dtype)
        self.k_proj = operations.Linear(context_dim, query_dim, bias=False, device=device, dtype=dtype)
        self.v_proj = operations.Linear(context_dim, query_dim, bias=False, device=device, dtype=dtype)
        self.o_proj = operations.Linear(query_dim, query_dim, bias=False, device=device, dtype=dtype)

    def forward(
        self,
        query: torch.Tensor,
        context: torch.Tensor,
        context_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        batch, query_tokens, _ = query.shape
        context_tokens = context.shape[1]

        def heads(value: torch.Tensor, tokens: int) -> torch.Tensor:
            return value.reshape(
                batch, tokens, self.num_heads, self.head_dim
            ).transpose(1, 2)

        q = heads(self.q_proj(query), query_tokens)
        k = heads(self.k_proj(context), context_tokens)
        v = heads(self.v_proj(context), context_tokens)
        mask = None
        if context_mask is not None:
            mask = context_mask.to(torch.bool).reshape(batch, 1, 1, context_tokens)
        attended = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        attended = attended.transpose(1, 2).reshape(batch, query_tokens, self.query_dim)
        return self.o_proj(attended)


class TimestepModulatedNorm(nn.Module):
    """Parameter-free LayerNorm whose scale and shift come from the timestep."""

    def __init__(
        self,
        dim: int,
        device: torch.device,
        dtype: torch.dtype,
        operations,
    ) -> None:
        super().__init__()
        self.norm = operations.LayerNorm(
            dim, elementwise_affine=False, device=device, dtype=dtype
        )

    def forward(
        self,
        value: torch.Tensor,
        scale: torch.Tensor,
        shift: torch.Tensor,
    ) -> torch.Tensor:
        return self.norm(value) * (1.0 + scale.unsqueeze(1)) + shift.unsqueeze(1)


class SemanticResamplerBlock(nn.Module):
    """One timestep-aware query-resampler block.

    Cross-attention changes which Qwen tokens are extracted at each diffusion
    timestep. Self-attention then lets the learned semantic queries negotiate a
    compact scene representation before a SwiGLU feed-forward update.
    """

    def __init__(
        self,
        dim: int,
        qwen_dim: int,
        num_heads: int,
        mlp_hidden_dim: int,
        device: torch.device,
        dtype: torch.dtype,
        operations,
    ) -> None:
        super().__init__()
        self.cross_norm = TimestepModulatedNorm(dim, device, dtype, operations)
        self.self_norm = TimestepModulatedNorm(dim, device, dtype, operations)
        self.mlp_norm = TimestepModulatedNorm(dim, device, dtype, operations)
        self.source_norm = operations.LayerNorm(qwen_dim, device=device, dtype=dtype)
        self.cross_attention = MultiHeadAttention(
            dim, qwen_dim, num_heads, device, dtype, operations
        )
        self.self_attention = MultiHeadAttention(
            dim, dim, num_heads, device, dtype, operations
        )
        self.mlp_in = operations.Linear(
            dim, 2 * mlp_hidden_dim, bias=False, device=device, dtype=dtype
        )
        self.mlp_out = operations.Linear(
            mlp_hidden_dim, dim, bias=False, device=device, dtype=dtype
        )
        # Six vectors: scale/shift for cross-attention, self-attention and MLP.
        # This makes extraction itself timestep-dependent rather than multiplying
        # a finished residual by a timestep gate.
        self.time_modulation = operations.Linear(
            dim, 6 * dim, bias=True, device=device, dtype=dtype
        )

    def forward(
        self,
        queries: torch.Tensor,
        qwen_features: torch.Tensor,
        timestep_embedding: torch.Tensor,
        qwen_mask: torch.Tensor | None,
    ) -> torch.Tensor:
        modulation = self.time_modulation(F.silu(timestep_embedding))
        cross_scale, cross_shift, self_scale, self_shift, mlp_scale, mlp_shift = (
            modulation.chunk(6, dim=-1)
        )
        queries = queries + self.cross_attention(
            self.cross_norm(queries, cross_scale, cross_shift),
            self.source_norm(qwen_features),
            qwen_mask,
        )
        normalized = self.self_norm(queries, self_scale, self_shift)
        queries = queries + self.self_attention(normalized, normalized)
        normalized = self.mlp_norm(queries, mlp_scale, mlp_shift)
        gate, value = self.mlp_in(normalized).chunk(2, dim=-1)
        return queries + self.mlp_out(F.silu(gate) * value)


class TimestepAwareSemanticResampler(nn.Module):
    """Preserve four Qwen layer streams and compress them into semantic queries."""

    def __init__(
        self,
        qwen_dim: int,
        output_dim: int,
        num_layers: int,
        num_queries: int,
        num_blocks: int,
        model_dim: int,
        num_heads: int,
        mlp_hidden_dim: int,
        device: torch.device,
        dtype: torch.dtype,
        operations,
        initialize_weights: bool = True,
    ) -> None:
        super().__init__()
        self.num_layers = num_layers
        self.model_dim = model_dim
        self.query_tokens = nn.Parameter(torch.empty(
            1, num_queries, model_dim, device=device, dtype=dtype
        ))
        self.layer_embeddings = nn.Parameter(torch.empty(
            num_layers, 1, qwen_dim, device=device, dtype=dtype
        ))
        self.time_mlp = nn.Sequential(
            operations.Linear(model_dim, model_dim, device=device, dtype=dtype),
            nn.SiLU(),
            operations.Linear(model_dim, model_dim, device=device, dtype=dtype),
        )
        self.blocks = nn.ModuleList([
            SemanticResamplerBlock(
                model_dim,
                qwen_dim,
                num_heads,
                mlp_hidden_dim,
                device,
                dtype,
                operations,
            )
            for _ in range(num_blocks)
        ])
        self.output_norm = operations.LayerNorm(model_dim, device=device, dtype=dtype)
        self.output_projection = operations.Linear(
            model_dim, output_dim, bias=False, device=device, dtype=dtype
        )
        self.gradient_checkpointing = False
        if initialize_weights:
            self.reset_parameters()

    @torch.no_grad()
    def reset_parameters(self) -> None:
        nn.init.normal_(self.query_tokens, std=0.02)
        nn.init.normal_(self.layer_embeddings, std=0.02)
        for module in self.modules():
            if isinstance(module, nn.Linear) and module.weight is not None:
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    module.bias.zero_()

    def forward(
        self,
        hidden_states: Sequence[torch.Tensor],
        timesteps: torch.Tensor,
        source_mask: torch.Tensor | None,
    ) -> torch.Tensor:
        if len(hidden_states) != self.num_layers:
            raise ValueError(
                f"Expected {self.num_layers} Qwen layers, got {len(hidden_states)}"
            )
        batch = hidden_states[0].shape[0]
        layer_streams = [
            hidden + self.layer_embeddings[index].unsqueeze(0)
            for index, hidden in enumerate(hidden_states)
        ]
        qwen_features = torch.cat(layer_streams, dim=1)
        qwen_mask = None
        if source_mask is not None:
            qwen_mask = torch.cat([source_mask] * self.num_layers, dim=1)

        time = sinusoidal_timestep_embedding(timesteps, self.model_dim).to(
            dtype=qwen_features.dtype
        )
        time = self.time_mlp(time)
        queries = self.query_tokens.expand(batch, -1, -1)
        for block in self.blocks:
            if self.gradient_checkpointing and self.training:
                queries = checkpoint(
                    block,
                    queries,
                    qwen_features,
                    time,
                    qwen_mask,
                    use_reentrant=False,
                )
            else:
                queries = block(queries, qwen_features, time, qwen_mask)
        return self.output_projection(self.output_norm(queries))


class QualityAnchoredSemanticConnectorV2(nn.Module):
    """Large semantic connector with an exact frozen quality anchor.

    The selected frozen v1 adapter is run exactly as it was at the anchor epoch. A 400--800M
    timestep-aware semantic resampler supplies a separate 64-token bank to six
    new decoupled cross-attention residuals. Their output projections start at
    zero, so before training this module is bit-identical to the anchored v1
    connector. The DiT and Qwen remain external and frozen.

    At model_dim=2048, mlp_hidden_dim=5632:
      4 resampler blocks: roughly 400M trainable parameters
      6 resampler blocks: roughly 600M trainable parameters (default)
      8 resampler blocks: roughly 800M trainable parameters
    """

    architecture = "anima_qwen35_quality_anchored_semantic_connector_v2"

    def __init__(
        self,
        native_adapter: nn.Module,
        semantic_source_dim: int,
        layer_indices: Sequence[int],
        operations,
        num_queries: int = 64,
        resampler_blocks: int = 6,
        resampler_dim: int = 2048,
        resampler_heads: int = 16,
        mlp_hidden_dim: int = 5632,
        initialize_from_native: bool = True,
        register_native_adapter: bool = True,
        initialize_resampler: bool = True,
    ) -> None:
        super().__init__()
        self.layer_indices = tuple(int(index) for index in layer_indices)
        self.quality_anchor = ProgressiveQwen35CrossAdapter(
            native_adapter,
            semantic_source_dim=semantic_source_dim,
            layer_indices=self.layer_indices,
            operations=operations,
            register_native_adapter=register_native_adapter,
        )
        model_dim = native_adapter.embed.weight.shape[1]
        num_heads = native_adapter.blocks[0].self_attn.n_heads
        head_dim = model_dim // num_heads
        device = native_adapter.embed.weight.device
        dtype = native_adapter.embed.weight.dtype

        self.semantic_resampler = TimestepAwareSemanticResampler(
            qwen_dim=semantic_source_dim,
            output_dim=model_dim,
            num_layers=len(self.layer_indices),
            num_queries=num_queries,
            num_blocks=resampler_blocks,
            model_dim=resampler_dim,
            num_heads=resampler_heads,
            mlp_hidden_dim=mlp_hidden_dim,
            device=device,
            dtype=dtype,
            operations=operations,
            initialize_weights=initialize_resampler,
        )
        self.v2_query_norms = nn.ModuleList([
            operations.RMSNorm(model_dim, eps=1e-6, device=device, dtype=dtype)
            for _ in native_adapter.blocks
        ])
        self.v2_semantic_norms = nn.ModuleList([
            operations.RMSNorm(model_dim, eps=1e-6, device=device, dtype=dtype)
            for _ in native_adapter.blocks
        ])
        self.v2_attentions = nn.ModuleList([
            Attention(
                query_dim=model_dim,
                context_dim=model_dim,
                n_heads=num_heads,
                head_dim=head_dim,
                device=device,
                dtype=dtype,
                operations=operations,
            )
            for _ in native_adapter.blocks
        ])
        if initialize_from_native and not self._has_unmaterialized_v2_parameters():
            self._initialize_v2_injections()
        self.set_trainability()

    @property
    def native_adapter(self) -> nn.Module:
        return self.quality_anchor.get_native_adapter()

    def _has_unmaterialized_v2_parameters(self) -> bool:
        """ComfyUI's lazy ops expose module weights as ``None`` until loading."""
        return any(
            hasattr(module, "weight") and module.weight is None
            for group in (
                self.v2_query_norms,
                self.v2_semantic_norms,
                self.v2_attentions,
            )
            for module in group.modules()
        )

    @torch.no_grad()
    def _initialize_v2_injections(self) -> None:
        for native, query_norm, semantic_norm, attention in zip(
            self.native_adapter.blocks,
            self.v2_query_norms,
            self.v2_semantic_norms,
            self.v2_attentions,
        ):
            query_norm.weight.copy_(native.norm_cross_attn.weight)
            semantic_norm.weight.fill_(1.0)
            attention.q_proj.weight.copy_(native.cross_attn.q_proj.weight)
            attention.q_norm.weight.copy_(native.cross_attn.q_norm.weight)
            attention.k_norm.weight.copy_(native.cross_attn.k_norm.weight)
            nn.init.xavier_uniform_(attention.k_proj.weight)
            nn.init.xavier_uniform_(attention.v_proj.weight)
            attention.o_proj.weight.zero_()

    def set_gradient_checkpointing(self, enabled: bool) -> None:
        self.semantic_resampler.gradient_checkpointing = bool(enabled)

    @torch.no_grad()
    def align_device(self, device: torch.device | str) -> None:
        """Move connector-owned tensors while leaving the live Anima adapter alone."""
        for name, parameter in self.named_parameters():
            if (
                not name.startswith("quality_anchor.native_adapter.")
                and parameter.device != torch.device(device)
            ):
                parameter.data = parameter.data.to(device)
        for name, buffer in self.named_buffers():
            if (
                not name.startswith("quality_anchor.native_adapter.")
                and buffer.device != torch.device(device)
            ):
                buffer.data = buffer.data.to(device)

    def set_trainability(self, gates_only: bool = False) -> None:
        if gates_only:
            raise ValueError("QualityAnchoredSemanticConnectorV2 has no gate-only mode")
        self.quality_anchor.requires_grad_(False)
        self.semantic_resampler.requires_grad_(True)
        self.v2_query_norms.requires_grad_(True)
        self.v2_semantic_norms.requires_grad_(True)
        self.v2_attentions.requires_grad_(True)

    @staticmethod
    def _attention_mask(mask: torch.Tensor | None) -> torch.Tensor | None:
        if mask is None:
            return None
        mask = mask.to(torch.bool)
        return mask.unsqueeze(1).unsqueeze(1) if mask.ndim == 2 else mask

    def load_quality_anchor_state_dict(self, state: dict[str, torch.Tensor]) -> None:
        self.quality_anchor.load_trainable_state_dict(state)
        self.quality_anchor.requires_grad_(False)

    def forward(
        self,
        native_source: torch.Tensor,
        target_input_ids: torch.Tensor,
        semantic_hidden_states: Sequence[torch.Tensor],
        target_attention_mask: torch.Tensor | None = None,
        native_source_mask: torch.Tensor | None = None,
        semantic_source_mask: torch.Tensor | None = None,
        timesteps: torch.Tensor | None = None,
        include_inserted_blocks: bool = True,
        include_v2: bool = True,
        **_ignored,
    ) -> torch.Tensor:
        if timesteps is None:
            raise ValueError("QualityAnchoredSemanticConnectorV2 requires diffusion timesteps")
        if len(semantic_hidden_states) != len(self.layer_indices):
            raise ValueError(
                f"Expected {len(self.layer_indices)} semantic layers, "
                f"got {len(semantic_hidden_states)}"
            )

        target_attention_mask = self._attention_mask(target_attention_mask)
        native_source_mask = self._attention_mask(native_source_mask)
        semantic_attention_mask = self._attention_mask(semantic_source_mask)
        semantic_bank = None
        if include_inserted_blocks and include_v2:
            semantic_bank = self.semantic_resampler(
                semantic_hidden_states,
                timesteps,
                semantic_source_mask,
            )

        x = self.native_adapter.in_proj(
            self.native_adapter.embed(
                target_input_ids, out_dtype=native_source.dtype
            )
        )
        query_positions = torch.arange(x.shape[1], device=x.device).unsqueeze(0)
        native_positions = torch.arange(native_source.shape[1], device=x.device).unsqueeze(0)
        anchor_positions = torch.arange(
            semantic_hidden_states[0].shape[1], device=x.device
        ).unsqueeze(0)
        bank_rope = None
        if semantic_bank is not None:
            bank_positions = torch.arange(
                semantic_bank.shape[1], device=x.device
            ).unsqueeze(0)
            bank_rope = self.native_adapter.rotary_emb(x, bank_positions)
        query_rope = self.native_adapter.rotary_emb(x, query_positions)
        native_rope = self.native_adapter.rotary_emb(x, native_positions)
        anchor_rope = self.native_adapter.rotary_emb(x, anchor_positions)
        anchor_mix = self.quality_anchor.layer_mix_logits.float().softmax(dim=-1).to(x.dtype)

        for index, native_block in enumerate(self.native_adapter.blocks):
            x = native_block(
                x,
                native_source,
                target_attention_mask=target_attention_mask,
                source_attention_mask=native_source_mask,
                position_embeddings=query_rope,
                position_embeddings_context=native_rope,
            )
            if not include_inserted_blocks:
                continue
            anchor_source = self.quality_anchor.source_norms[index](
                self.quality_anchor._mixed_source(
                    semantic_hidden_states, anchor_mix, index
                )
            )
            x = x + self.quality_anchor.semantic_attentions[index](
                self.quality_anchor.query_norms[index](x),
                mask=semantic_attention_mask,
                context=anchor_source,
                position_embeddings=query_rope,
                position_embeddings_context=anchor_rope,
            )
            if semantic_bank is not None:
                x = x + self.v2_attentions[index](
                    self.v2_query_norms[index](x),
                    context=self.v2_semantic_norms[index](semantic_bank),
                    position_embeddings=query_rope,
                    position_embeddings_context=bank_rope,
                )

        return self.native_adapter.norm(self.native_adapter.out_proj(x))

    def trainable_state_dict(self) -> dict[str, torch.Tensor]:
        # Include the frozen v1 anchor so the v2 checkpoint is self-contained.
        return {
            name: value.detach().cpu()
            for name, value in self.state_dict().items()
            if not name.startswith("quality_anchor.native_adapter.")
        }

    def load_trainable_state_dict(
        self,
        state: dict[str, torch.Tensor],
        *,
        assign: bool = False,
    ) -> None:
        # strict=False lets ComfyUI's lazy ops materialize placeholder weights.
        # The only intentionally absent tensors are the live native adapter,
        # which comes from the selected diffusion model rather than this file.
        incompatible = self.load_state_dict(state, strict=False, assign=assign)
        missing = sorted(
            name for name in incompatible.missing_keys
            if not name.startswith("quality_anchor.native_adapter.")
        )
        unexpected = sorted(incompatible.unexpected_keys)
        if missing or unexpected:
            raise RuntimeError(
                f"V2 checkpoint mismatch: missing={missing[:10]}, "
                f"unexpected={unexpected[:10]}"
            )
        self.set_trainability()

    def parameter_report(self) -> dict[str, int]:
        frozen_native = sum(p.numel() for p in self.native_adapter.parameters())
        frozen_anchor = sum(
            p.numel() for name, p in self.quality_anchor.named_parameters()
            if not name.startswith("native_adapter.")
        )
        resampler = sum(p.numel() for p in self.semantic_resampler.parameters())
        injection = sum(p.numel() for p in self.v2_query_norms.parameters())
        injection += sum(p.numel() for p in self.v2_semantic_norms.parameters())
        injection += sum(p.numel() for p in self.v2_attentions.parameters())
        return {
            "frozen_native": frozen_native,
            "frozen_v1_quality_anchor": frozen_anchor,
            "trainable_semantic_resampler": resampler,
            "trainable_decoupled_injections": injection,
            "total_trainable": sum(p.numel() for p in self.parameters() if p.requires_grad),
            "total_parameters": sum(p.numel() for p in self.parameters()),
        }

    def anchor_profile(self) -> dict:
        return {}

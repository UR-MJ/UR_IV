from __future__ import annotations

import logging
import os
import weakref

import safetensors.torch
import torch
import torch.nn.functional as F

import comfy.model_management
import comfy.ops

from .semantic_connector_v2 import QualityAnchoredSemanticConnectorV2

logger = logging.getLogger(__name__)

LAYER_INDICES = (7, 15, 23, 31)
RUN_WINDOW = 64

# The registry is mirrored onto ComfyUI's shared Anima class by
# install_timestep_support(). This matters because ComfyUI may import a custom
# node through more than one package name; module globals alone are not shared.
_GATED_RUNS: dict[int, _GatedAdapterRun] = {}
_GATED_RUN_COUNTER = [0]
_ADAPTER_CACHE = {"key": None, "adapter": None}
_BATCH_SPLIT_WARNED = [False]


def _pad_context(context: torch.Tensor, length: int = 512) -> torch.Tensor:
    if context.shape[1] >= length:
        return context[:, :length]
    return F.pad(context, (0, 0, 0, length - context.shape[1]))


def _blend_context(
    expanded_context,
    native_adapter,
    source,
    target_ids,
    *,
    adapter_strength,
    native_strength,
):
    if adapter_strength == 1.0 and native_strength == 1.0:
        return expanded_context
    native_context = native_adapter(source, target_ids)
    return (
        float(native_strength) * native_context
        + float(adapter_strength) * (expanded_context - native_context)
    )


class _GatedAdapterRun:
    """Lightweight settings for one cached conditioning result.

    Semantic tensors travel in ComfyUI conditioning metadata. Runs normally all
    reference the same adapter in _ADAPTER_CACHE. Bundled-model runs resolve the
    connector from the active DiT instead, so the registry cannot keep an old
    model alive or bypass a fresh multi-GPU clone.
    """

    def __init__(
        self,
        adapter,
        native_adapter,
        block_flags,
        adapter_strength,
        native_strength,
        name,
    ):
        self.model_managed = bool(
            getattr(adapter, "_anima_v2_model_managed", False)
        )
        self._adapter_ref = weakref.ref(adapter) if self.model_managed else None
        self._native_adapter_ref = (
            weakref.ref(native_adapter) if self.model_managed else None
        )
        self.adapter = None if self.model_managed else adapter
        self.native_adapter = None if self.model_managed else native_adapter
        self.block_flags = dict(block_flags)
        self.adapter_strength = float(adapter_strength)
        self.native_strength = float(native_strength)
        self.name = name

    def apply(
        self,
        context,
        target_ids,
        semantic_states,
        semantic_mask,
        target_weights,
        timesteps,
        model_adapter=None,
        model_native_adapter=None,
    ):
        if self.model_managed:
            adapter = model_adapter or self._adapter_ref()
            native_adapter = model_native_adapter or self._native_adapter_ref()
        else:
            adapter = self.adapter
            native_adapter = self.native_adapter
        if adapter is None or native_adapter is None:
            raise RuntimeError(
                "The active anima.3-8B-v2 model has no bundled connector."
            )
        device = context.device
        if not self.model_managed:
            adapter.align_device(device)
        dtype = native_adapter.embed.weight.dtype
        source = context.to(dtype=dtype)
        semantic_states = [
            state.to(device=device, dtype=dtype) for state in semantic_states
        ]
        if semantic_mask is not None:
            semantic_mask = semantic_mask.to(device=device, dtype=torch.bool)
        target_ids = target_ids.to(device=device, dtype=torch.long)
        expanded_context = adapter(
            source,
            target_ids,
            semantic_states,
            semantic_source_mask=semantic_mask,
            timesteps=timesteps,
            **self.block_flags,
        )
        expanded_context = _blend_context(
            expanded_context,
            native_adapter,
            source,
            target_ids,
            adapter_strength=self.adapter_strength,
            native_strength=self.native_strength,
        )
        if target_weights is not None:
            weights = target_weights.to(
                device=device, dtype=expanded_context.dtype
            ).reshape(expanded_context.shape[0], -1, 1)
            expanded_context = expanded_context * weights[:, :expanded_context.shape[1]]
        return _pad_context(expanded_context).to(context.dtype)


def _register_run(run: _GatedAdapterRun) -> int:
    import comfy.ldm.anima.model as anima_model

    runs = getattr(anima_model.Anima, "_qwen35_gated_runs", None)
    if runs is None:
        runs = _GATED_RUNS
        anima_model.Anima._qwen35_gated_runs = runs
    counter = getattr(anima_model.Anima, "_qwen35_gated_run_counter", None)
    if counter is None:
        counter = _GATED_RUN_COUNTER
        anima_model.Anima._qwen35_gated_run_counter = counter
    counter[0] += 1
    run_id = counter[0]
    runs[run_id] = run
    for stale in sorted(runs)[:-RUN_WINDOW]:
        runs.pop(stale, None)
    return run_id


def load_adapter(checkpoint_path, native_adapter, device, connector_config):
    """Load and cache one standalone semantic-connector-v2 checkpoint."""
    connector_config = dict(connector_config)
    connector_config.setdefault("initialize_resampler", False)
    key = (
        str(checkpoint_path),
        id(native_adapter),
        tuple(sorted(connector_config.items())),
    )
    if _ADAPTER_CACHE["key"] == key and _ADAPTER_CACHE["adapter"] is not None:
        return _ADAPTER_CACHE["adapter"]

    _ADAPTER_CACHE["key"] = None
    _ADAPTER_CACHE["adapter"] = None
    adapter = QualityAnchoredSemanticConnectorV2(
        native_adapter=native_adapter,
        semantic_source_dim=2560,
        layer_indices=LAYER_INDICES,
        operations=comfy.ops.disable_weight_init,
        **connector_config,
    )
    state = safetensors.torch.load_file(checkpoint_path, device=str(device))
    adapter.load_trainable_state_dict(state)
    adapter.eval().requires_grad_(False)
    _ADAPTER_CACHE["key"] = key
    _ADAPTER_CACHE["adapter"] = adapter
    return adapter


def emit_conditioning(
    *,
    expanded_adapter,
    native_adapter,
    native,
    native_source,
    native_metadata,
    semantic_states,
    semantic_mask,
    adapter_strength,
    checkpoint_path,
    architecture,
):
    """Emit pre-adapter data; the connector runs later with each timestep."""
    if not _BATCH_SPLIT_WARNED[0]:
        _BATCH_SPLIT_WARNED[0] = True
        logger.info(
            "[Anima 3-8B] Semantic Connector v2 runs once per denoising step; "
            "positive and ordinary negative conditioning use separate DiT passes."
        )

    intermediate = comfy.model_management.intermediate_device()
    target_ids = torch.as_tensor(
        native_metadata["t5xxl_ids"], dtype=torch.long
    ).reshape(1, -1)[:, :512]
    states = [state.to(intermediate) for state in semantic_states]
    metadata = {
        key: value
        for key, value in native_metadata.items()
        if key != "attention_mask"
    }
    metadata["t5xxl_ids"] = target_ids
    metadata["qwen35_semantic_states"] = states
    metadata["qwen35_semantic_mask"] = semantic_mask.to(
        device=intermediate, dtype=torch.long
    )
    run = _GatedAdapterRun(
        adapter=expanded_adapter,
        native_adapter=native_adapter,
        block_flags={"include_inserted_blocks": True},
        adapter_strength=adapter_strength,
        native_strength=1.0,
        name=os.path.basename(checkpoint_path),
    )
    metadata["qwen35_gated_run"] = _register_run(run)
    metadata.update({
        "qwen35_expanded_adapter": os.path.basename(checkpoint_path),
        "qwen35_expanded_strength": float(adapter_strength),
        "qwen35_expanded_native_strength": 1.0,
        "qwen35_expanded_architecture": architecture,
        "qwen35_expanded_timestep_gate": True,
    })
    logger.info(
        "[Anima 3-8B] %s (Semantic Connector v2): native=%d tokens, "
        "Qwen=%d tokens, run=%d, strength=%.2f",
        os.path.basename(checkpoint_path),
        native_source.shape[1],
        states[0].shape[1],
        metadata["qwen35_gated_run"],
        adapter_strength,
    )
    return [[native_source.to(intermediate), metadata]], native


def install_timestep_support() -> None:
    global _GATED_RUNS, _GATED_RUN_COUNTER
    try:
        import comfy.conds
        import comfy.model_base
        import comfy.ldm.anima.model as anima_model
    except Exception as error:
        logger.debug("[Anima 3-8B] v2 timestep patch unavailable: %s", error)
        return

    shared_runs = getattr(anima_model.Anima, "_qwen35_gated_runs", None)
    if shared_runs is None:
        anima_model.Anima._qwen35_gated_runs = _GATED_RUNS
    else:
        _GATED_RUNS = shared_runs
    shared_counter = getattr(anima_model.Anima, "_qwen35_gated_run_counter", None)
    if shared_counter is None:
        anima_model.Anima._qwen35_gated_run_counter = _GATED_RUN_COUNTER
    else:
        _GATED_RUN_COUNTER = shared_counter

    # Coexist with an already-installed compatible patch from an older pack.
    if getattr(anima_model.Anima, "_qwen35_timestep_gate_patch", False):
        logger.info("[Anima 3-8B] using existing compatible v2 timestep patch")
        return

    original_extra_conds = comfy.model_base.Anima.extra_conds

    def patched_extra_conds(self, **kwargs):
        run_id = kwargs.get("qwen35_gated_run")
        if run_id is None:
            return original_extra_conds(self, **kwargs)
        out = comfy.model_base.BaseModel.extra_conds(self, **kwargs)
        device = kwargs["device"]
        cross_attn = kwargs.get("cross_attn")
        if cross_attn is None:
            return out
        out["c_crossattn"] = comfy.conds.CONDRegular(cross_attn)
        out["qwen35_gated_run"] = comfy.conds.CONDRegular(
            torch.tensor([[int(run_id)]], dtype=torch.long)
        )
        target_ids = kwargs.get("t5xxl_ids")
        if target_ids is None:
            raise RuntimeError(
                "Semantic Connector v2 conditioning has no T5 token IDs. "
                "Re-run the Anima 3-8B prompt node."
            )
        out["t5xxl_ids"] = comfy.conds.CONDRegular(
            torch.as_tensor(target_ids, dtype=torch.long).reshape(1, -1).to(device)
        )
        target_weights = kwargs.get("t5xxl_weights")
        if target_weights is not None:
            out["t5xxl_weights"] = comfy.conds.CONDRegular(
                torch.as_tensor(target_weights).reshape(1, -1).to(device)
            )
        for index, state in enumerate(kwargs.get("qwen35_semantic_states") or ()):
            out[f"qwen35_semantic_{index}"] = comfy.conds.CONDRegular(state.to(device))
        semantic_mask = kwargs.get("qwen35_semantic_mask")
        if semantic_mask is not None:
            out["qwen35_semantic_mask"] = comfy.conds.CONDRegular(
                semantic_mask.reshape(1, -1).to(device=device, dtype=torch.long)
            )
        return out

    comfy.model_base.Anima.extra_conds = patched_extra_conds
    original_forward = anima_model.Anima.forward

    def patched_forward(self, x, timesteps, context, **kwargs):
        run_ref = kwargs.pop("qwen35_gated_run", None)
        semantic_states = []
        while f"qwen35_semantic_{len(semantic_states)}" in kwargs:
            semantic_states.append(
                kwargs.pop(f"qwen35_semantic_{len(semantic_states)}")
            )
        semantic_mask = kwargs.pop("qwen35_semantic_mask", None)
        if run_ref is None:
            return original_forward(self, x, timesteps, context, **kwargs)

        run_id = int(run_ref.reshape(-1)[0])
        runs = getattr(anima_model.Anima, "_qwen35_gated_runs", _GATED_RUNS)
        run = runs.get(run_id)
        if run is None:
            raise RuntimeError(
                f"Semantic Connector v2 run {run_id} is no longer registered "
                f"(live runs: {sorted(runs)}). More than {RUN_WINDOW} newer "
                "conditioning runs were created, or the node pack was reloaded. "
                "Re-run the prompt node."
            )
        target_ids = kwargs.pop("t5xxl_ids", None)
        target_weights = kwargs.pop("t5xxl_weights", None)
        context = run.apply(
            context,
            target_ids,
            semantic_states,
            semantic_mask,
            target_weights,
            timesteps,
            model_adapter=getattr(self, "anima_v2_connector", None),
            model_native_adapter=getattr(self, "llm_adapter", None),
        )
        return original_forward(self, x, timesteps, context, **kwargs)

    anima_model.Anima.forward = patched_forward
    anima_model.Anima._qwen35_timestep_gate_patch = True
    logger.info(
        "[Anima 3-8B] standalone Semantic Connector v2 support installed "
        "(run window: %d)",
        RUN_WINDOW,
    )


install_timestep_support()

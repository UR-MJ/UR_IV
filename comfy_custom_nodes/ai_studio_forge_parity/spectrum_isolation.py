"""Container-only copies for a per-sampler provider call (never clone tensors).

Independently implemented; this is not the LAKIS Spectrum source patch.
The installed provider remains responsible for its own diffusion-model hooks.
"""
from __future__ import annotations


def copy_option_containers(value, memo=None):
    memo = {} if memo is None else memo
    if id(value) in memo:
        return memo[id(value)]
    if isinstance(value, dict):
        result = {}
        memo[id(value)] = result
        result.update((key, copy_option_containers(item, memo)) for key, item in value.items())
        return result
    if isinstance(value, list):
        result = []
        memo[id(value)] = result
        result.extend(copy_option_containers(item, memo) for item in value)
        return result
    # Comfy's model_options contract isolates dict/list, retaining tensors,
    # callables and backend-owned handles exactly, including objects in tuples.
    return value


def isolated_sampler_model(model):
    clone = model.clone()
    clone.model_options = copy_option_containers(getattr(model, "model_options", {}))
    return clone

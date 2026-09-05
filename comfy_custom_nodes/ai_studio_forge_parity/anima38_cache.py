"""Conditioning-owned run lifetimes for the unmodified pinned Anima runtime.

Upstream keeps only 64 run IDs, independently of Comfy's output cache. A fixed
negative prompt can outlive that window while positives change. This shim
keeps each run until its conditioning metadata (including shallow/deep copies)
is released. It does not disable Comfy caching or retain discarded prompts.
"""

from __future__ import annotations

import contextvars
import functools
import importlib
import sys
import threading
import weakref
from types import ModuleType


_OWNER_KEY = "ai_studio_anima_run_owner"
_INSTALL_LOCK = threading.RLock()


class _RunOwner:
    def __init__(self, registry: _RunRegistry, run_id: int):
        self._release = weakref.finalize(self, registry.release, run_id)

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        # Comfy and conditioning nodes copy metadata. Every copy must retain
        # the same lease; releasing any one copy cannot invalidate the others.
        return self


class _RunRegistry(dict):
    _ai_studio_conditioning_lifetimes = True

    def __init__(self, existing, counter):
        super().__init__(existing)
        self.counter = counter
        self.counter[0] = max([self.counter[0], *existing])
        self.lock = threading.RLock()
        self.pending = contextvars.ContextVar("anima_conditioning_runs", default=None)
        self.managed: set[int] = set()
        # Preserve already-cached outputs from a previously imported runtime.
        # These pre-shim entries have no lifetime token and remain bounded by
        # upstream's original 64-entry compatibility window.
        self.legacy = set(existing)

    def __setitem__(self, key, value):
        with self.lock:
            super().__setitem__(key, value)
            pending = self.pending.get()
            if pending is not None:
                self.managed.add(key)
                pending.append(key)
            else:
                self.legacy.add(key)
                for stale in sorted(self.legacy)[:-64]:
                    self.release(stale)

    def pop(self, key, *default):
        with self.lock:
            if key in self.managed:
                # An old imported _register_run may still perform its FIFO
                # pruning. It must not delete conditioning owned by this shim.
                return self[key]
            self.legacy.discard(key)
            return super().pop(key, *default)

    def release(self, key):
        with self.lock:
            self.managed.discard(key)
            self.legacy.discard(key)
            super().pop(key, None)

    def register(self, run):
        with self.lock:
            self.counter[0] += 1
            run_id = self.counter[0]
            self[run_id] = run
            return run_id


def _own_conditioning(emitter, registry):
    @functools.wraps(emitter)
    def emit_conditioning(*args, **kwargs):
        pending: list[int] = []
        context = registry.pending.set(pending)
        attached: set[int] = set()
        try:
            result = emitter(*args, **kwargs)
            owners: dict[int, _RunOwner] = {}
            for conditioning in result:
                for _tensor, metadata in conditioning:
                    run_id = metadata.get("qwen35_gated_run")
                    if run_id not in pending:
                        continue
                    if run_id not in owners:
                        owners[run_id] = _RunOwner(registry, run_id)
                    metadata[_OWNER_KEY] = owners[run_id]
                    attached.add(run_id)
            return result
        finally:
            registry.pending.reset(context)
            for run_id in pending:
                if run_id not in attached:
                    # Exceptions after registration must not leak model runs.
                    registry.release(run_id)

    emit_conditioning._ai_studio_run_registry = registry
    return emit_conditioning


def install_conditioning_cache_support(semantic_runtime: ModuleType) -> None:
    """Patch loaded aliases, sharing lifetime state across imports and reloads."""

    if not callable(getattr(semantic_runtime, "emit_conditioning", None)):
        raise RuntimeError("The Anima runtime has no conditioning emitter.")
    anima_model = importlib.import_module("comfy.ldm.anima.model")
    with _INSTALL_LOCK:
        anima = anima_model.Anima
        registry = getattr(anima, "_qwen35_gated_runs", {})
        counter = getattr(anima, "_qwen35_gated_run_counter", [0])
        if not getattr(registry, "_ai_studio_conditioning_lifetimes", False):
            registry = _RunRegistry(registry, counter)
            anima._qwen35_gated_runs = registry
        anima._qwen35_gated_run_counter = registry.counter

        # prompt.py and v2.py import emit_conditioning by value. Existing
        # standalone copies of the same provider can hold those aliases too.
        modules = [module for module in tuple(sys.modules.values()) if isinstance(module, ModuleType)]
        candidates = [semantic_runtime]
        for module in modules:
            if (
                module is not semantic_runtime
                and module.__name__.endswith(".semantic_v2_runtime")
                and callable(vars(module).get("emit_conditioning"))
                and callable(vars(module).get("_register_run"))
            ):
                candidates.append(module)
        for module in candidates:
            emitter = module.emit_conditioning
            module._register_run = registry.register
            module._GATED_RUNS = registry
            module._GATED_RUN_COUNTER = registry.counter
            if getattr(emitter, "_ai_studio_run_registry", None) is registry:
                continue
            wrapped = _own_conditioning(emitter, registry)
            module.emit_conditioning = wrapped
            for consumer in modules:
                if vars(consumer).get("emit_conditioning") is emitter:
                    consumer.emit_conditioning = wrapped


__all__ = ["install_conditioning_cache_support"]

"""Small lazy compatibility layer for the AI Studio ComfyUI node pack.

This module intentionally imports neither ComfyUI nor torch at module import
time.  The app owns this node pack and also imports parts of it in its normal
Python test process, where the large ComfyUI runtime is not installed.
"""

from __future__ import annotations

import importlib
from typing import Any, Iterable


class MissingComfyProvider(RuntimeError):
    """Raised when an explicitly enabled feature has no runtime provider."""


def require_torch():
    try:
        return importlib.import_module("torch")
    except Exception as exc:  # pragma: no cover - depends on the host runtime
        raise RuntimeError(
            "This Forge-parity node needs torch and must run inside ComfyUI."
        ) from exc


def comfy_nodes():
    try:
        return importlib.import_module("nodes")
    except Exception as exc:  # pragma: no cover - depends on the host runtime
        raise RuntimeError(
            "ComfyUI's nodes module is unavailable. Install this pack under "
            "ComfyUI/custom_nodes and restart ComfyUI."
        ) from exc


def folder_paths_module():
    try:
        return importlib.import_module("folder_paths")
    except Exception as exc:  # pragma: no cover - depends on the host runtime
        raise RuntimeError("ComfyUI folder_paths is unavailable.") from exc


def node_mapping() -> dict[str, type]:
    mapping = getattr(comfy_nodes(), "NODE_CLASS_MAPPINGS", None)
    if not isinstance(mapping, dict):
        raise RuntimeError("ComfyUI NODE_CLASS_MAPPINGS is unavailable.")
    return mapping


def provider_class(name: str, *, feature: str | None = None) -> type:
    cls = node_mapping().get(name)
    if cls is None:
        label = feature or name
        raise MissingComfyProvider(
            f"{label} is enabled, but required ComfyUI provider node "
            f"{name!r} is not installed. Install/update the provider and "
            "restart ComfyUI."
        )
    return cls


def provider(name: str, *, feature: str | None = None) -> Any:
    return provider_class(name, feature=feature)()


def node_result(value: Any) -> tuple[Any, ...]:
    """Normalize legacy tuples, output dictionaries, and io.NodeOutput."""

    if isinstance(value, dict) and "result" in value:
        value = value["result"]
    elif hasattr(value, "result"):
        result = getattr(value, "result")
        if result is not None:
            value = result
        elif hasattr(value, "args"):
            value = getattr(value, "args")
    elif hasattr(value, "args") and not isinstance(value, (tuple, list)):
        value = getattr(value, "args")

    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def invoke_provider(
    name: str,
    *,
    method: str | None = None,
    feature: str | None = None,
    args: Iterable[Any] = (),
    kwargs: dict[str, Any] | None = None,
) -> tuple[Any, ...]:
    instance = provider(name, feature=feature)
    function_name = method or getattr(instance, "FUNCTION", None)
    function = getattr(instance, function_name, None) if function_name else None
    if not callable(function):
        raise RuntimeError(
            f"Provider {name!r} does not expose the expected "
            f"{function_name or 'node execution'} method."
        )
    return node_result(function(*tuple(args), **(kwargs or {})))


def filename_choices(kind: str, *, fallback: str = "None") -> list[str]:
    """Return a non-empty Comfy combo list, including tests outside ComfyUI."""

    try:
        values = list(folder_paths_module().get_filename_list(kind))
    except Exception:
        values = []
    return values or [fallback]


def sampler_names() -> list[str]:
    try:
        comfy_samplers = importlib.import_module("comfy.samplers")
        return list(comfy_samplers.KSampler.SAMPLERS)
    except Exception:
        return ["euler"]


def scheduler_names() -> list[str]:
    try:
        comfy_samplers = importlib.import_module("comfy.samplers")
        return list(comfy_samplers.KSampler.SCHEDULERS)
    except Exception:
        return ["simple"]


def clone_model(model: Any, feature: str) -> Any:
    clone = getattr(model, "clone", None)
    if not callable(clone):
        raise RuntimeError(f"{feature} requires a ComfyUI MODEL input.")
    return clone()


def model_options(model: Any) -> dict[str, Any]:
    options = getattr(model, "model_options", None)
    if not isinstance(options, dict):
        raise RuntimeError("The MODEL has no ComfyUI model_options dictionary.")
    return options


def is_disabled_choice(value: Any) -> bool:
    return str(value or "").strip().casefold() in {
        "",
        "none",
        "off",
        "use current",
        "use same checkpoint",
        "use same choices",
        "(none)",
    }

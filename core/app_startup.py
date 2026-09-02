"""Shared dependency and data preparation for every application entrypoint."""

from __future__ import annotations


def prepare_application() -> int:
    """Prepare the environment after the process has registered its app lease."""

    from core.check_requirements import main as check_requirements

    result = int(check_requirements())
    if result:
        return result

    from core.fetch_data import ensure_data

    return int(ensure_data())


__all__ = ["prepare_application"]

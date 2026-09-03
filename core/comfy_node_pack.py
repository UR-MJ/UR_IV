"""Installation and capability checks for AI Studio's bundled ComfyUI nodes.

The node sources live with the application so Forge/Comfy feature parity is
versioned together with the workflow compiler.  A linked ComfyUI installation
is never overwritten blindly: only a directory carrying our ownership marker
may be refreshed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


PACK_ID = "ai_studio_forge_parity"
PACK_VERSION = "1.0.0"
OWNER_ID = "ai-studio-pro.bundled-comfy-nodes"
OWNER_MARKER = ".aistudio-owned.json"

REQUIRED_NODE_TYPES = frozenset(
    {
        "ForgeNeoNegPip",
        "ForgeNeoAnimaDAVE",
        "ForgeNeoAnimaModGuidance",
        "ForgeNeoSkimmedCFG",
        "ForgeNeoAnimaSafePAG",
        "ForgeNeoDCWCWMSMC",
        "ForgeNeoAnimaGuidanceSuite",
        "ForgeNeoAnimaDetailDaemon",
        "ForgeNeoKSamplerCNS",
        "ForgeNeoLatentInput",
        "ForgeNeoHiresFix",
        "ForgeNeoMaskSelector",
        "ForgeNeoLoraBlockWeight",
        "ForgeNeoCharacterReference",
        "ForgeNeoReferencePrompt",
        "ForgeNeoReferenceOutput",
        "ForgeNeoAnimaPiD",
        "ForgeNeoAnimaVAE2x",
        "ForgeNeoSAM3Mask",
        "ForgeNeoSAM3Detailer",
        "ForgeNeoSAM3Refine",
        "ForgeNeoSAM3TileRepair",
        "ForgeNeoADetailer",
        "ForgeNeoSaveImage",
    }
)


class ComfyNodePackError(RuntimeError):
    """Raised when the bundled node pack cannot be installed safely."""


@dataclass(frozen=True)
class NodePackInstallResult:
    target: Path
    fingerprint: str
    changed: bool


def bundled_node_pack_path(project_root: Path | str | None = None) -> Path:
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else Path(__file__).resolve().parent.parent
    )
    return root / "comfy_custom_nodes" / PACK_ID


def _pack_files(source: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in source.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.name != OWNER_MARKER
            and path.suffix.casefold() in {".py", ".json", ".md", ".txt"}
        ),
        key=lambda path: path.relative_to(source).as_posix(),
    )


def node_pack_fingerprint(source: Path | str) -> str:
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ComfyNodePackError(f"번들 ComfyUI 노드 폴더가 없습니다: {source_path}")
    digest = hashlib.sha256()
    files = _pack_files(source_path)
    if not files:
        raise ComfyNodePackError(f"번들 ComfyUI 노드가 비어 있습니다: {source_path}")
    for path in files:
        relative = path.relative_to(source_path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _read_marker(target: Path) -> dict[str, Any] | None:
    marker = target / OWNER_MARKER
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("owner") != OWNER_ID:
        return None
    return data


def install_bundled_node_pack(
    custom_nodes_root: Path | str,
    *,
    source: Path | str | None = None,
) -> NodePackInstallResult:
    """Atomically copy the bundled pack into one explicit ``custom_nodes`` root.

    The root itself must already exist.  Existing third-party content at the
    reserved pack name is treated as a conflict.  A previous app-owned copy is
    refreshed only when its content fingerprint changes.
    """

    root = Path(custom_nodes_root).expanduser().resolve()
    if not root.is_dir():
        raise ComfyNodePackError(f"ComfyUI custom_nodes 폴더가 없습니다: {root}")
    source_path = Path(source).resolve() if source is not None else bundled_node_pack_path()
    if not (source_path / "__init__.py").is_file():
        raise ComfyNodePackError(
            f"번들 ComfyUI 노드 진입점을 찾을 수 없습니다: {source_path / '__init__.py'}"
        )
    fingerprint = node_pack_fingerprint(source_path)
    target = root / PACK_ID
    existing = _read_marker(target) if target.exists() else None
    if target.exists() and existing is None:
        raise ComfyNodePackError(
            f"앱 소유가 아닌 같은 이름의 ComfyUI 확장이 있어 덮어쓰지 않았습니다: {target}"
        )
    if existing and existing.get("fingerprint") == fingerprint:
        try:
            installed_fingerprint = node_pack_fingerprint(target)
        except ComfyNodePackError:
            installed_fingerprint = ""
        if installed_fingerprint == fingerprint:
            return NodePackInstallResult(target=target, fingerprint=fingerprint, changed=False)

    suffix = uuid.uuid4().hex[:10]
    staging = root / f".{PACK_ID}.staging-{suffix}"
    backup = root / f".{PACK_ID}.backup-{suffix}"
    try:
        shutil.copytree(
            source_path,
            staging,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", OWNER_MARKER),
        )
        marker = {
            "owner": OWNER_ID,
            "packId": PACK_ID,
            "version": PACK_VERSION,
            "fingerprint": fingerprint,
        }
        (staging / OWNER_MARKER).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(staging, target)
        except Exception:
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return NodePackInstallResult(target=target, fingerprint=fingerprint, changed=True)


def missing_required_nodes(object_info: Mapping[str, Any]) -> list[str]:
    """Return stable, sorted node IDs absent from a Comfy ``/object_info`` map."""

    available = {str(key) for key in object_info}
    return sorted(REQUIRED_NODE_TYPES - available)


def capability_manifest() -> dict[str, Any]:
    return {
        "id": PACK_ID,
        "version": PACK_VERSION,
        "owner": OWNER_ID,
        "nodes": sorted(REQUIRED_NODE_TYPES),
        "forgeSam3Source": "forge_sam3_extension@0.21.2",
    }

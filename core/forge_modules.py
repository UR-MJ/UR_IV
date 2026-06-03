"""
Forge Neo의 ``models/`` 디렉토리를 스캔해 VAE / Text Encoder 파일명 목록 반환.

- VAE: ``models/VAE/``
- Text Encoder: ``models/text_encoder/``

ANIMA 등 외부 VAE/TE를 요구하는 모델 사용 시 dropdown에 자동으로 노출.

기본 경로는 ``C:\\sd-webui-forge-neo\\models``이며
``FORGE_MODELS_ROOT`` 환경변수 또는 ``config/forge_models_root.txt``로 오버라이드 가능.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_FORGE_MODELS_ROOT = r"C:\sd-webui-forge-neo\models"

# Forge Neo 표준 하위 디렉토리명
VAE_SUBDIR = "VAE"
TE_SUBDIR = "text_encoder"
SAM3_SUBDIR = "sam3"

# 모듈 파일로 인식할 확장자
_EXTS = {".safetensors", ".pt", ".bin", ".ckpt", ".pth"}
# SAM3 체크포인트는 .pt 또는 .safetensors만 허용 (Forge sam3ext와 동일)
_SAM3_EXTS = {".pt", ".safetensors"}


def get_forge_root() -> Path:
    """Forge models 루트 경로 반환. 환경변수 → config 파일 → 기본값 순서."""
    # 1) 환경변수
    env = os.environ.get("FORGE_MODELS_ROOT", "").strip()
    if env:
        return Path(env)

    # 2) config/forge_models_root.txt
    try:
        project_root = Path(__file__).resolve().parent.parent
        cfg = project_root / "config" / "forge_models_root.txt"
        if cfg.is_file():
            content = cfg.read_text(encoding="utf-8").strip()
            if content:
                return Path(content)
    except Exception:
        pass

    # 3) 기본값
    return Path(DEFAULT_FORGE_MODELS_ROOT)


def _list_files(subdir: str) -> list[str]:
    """주어진 하위 디렉토리에서 모듈 파일명 목록을 정렬해 반환."""
    root = get_forge_root() / subdir
    if not root.is_dir():
        return []
    out: list[str] = []
    try:
        for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file() and p.suffix.lower() in _EXTS:
                out.append(p.name)
    except OSError:
        return []
    return out


def list_vae_files() -> list[str]:
    return _list_files(VAE_SUBDIR)


def list_te_files() -> list[str]:
    return _list_files(TE_SUBDIR)


def list_sam3_checkpoints() -> list[str]:
    """SAM3 detection 체크포인트 파일명 반환.

    Forge ``forge_sam3_extension/sam3ext/core.py::find_checkpoint_options()``과
    동일한 규칙:
    - 위치: ``models/sam3/`` 와 ``models/``(루트)
    - 확장자: ``.pt`` / ``.safetensors``
    - 파일명이 ``sam3``로 시작하는 것만 (대소문자 무관) — anima-lllite 등
      ControlNet 가중치가 같은 폴더에 있어도 노이즈 제거.

    매칭 결과가 없으면 ``["sam3.pt"]``를 fallback으로 반환.
    """
    root = get_forge_root()
    seen: set[str] = set()
    result: list[str] = []

    def _consider(p: Path) -> None:
        name = p.name
        if name.lower().startswith("sam3") and p.suffix.lower() in _SAM3_EXTS:
            if name not in seen:
                seen.add(name)
                result.append(name)

    # models/sam3/sam3*.{pt,safetensors}
    sam3_dir = root / SAM3_SUBDIR
    if sam3_dir.is_dir():
        try:
            for p in sorted(sam3_dir.iterdir(), key=lambda x: x.name.lower()):
                if p.is_file():
                    _consider(p)
        except OSError:
            pass

    # models/sam3*.{pt,safetensors} (루트)
    if root.is_dir():
        try:
            for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
                if p.is_file():
                    _consider(p)
        except OSError:
            pass

    if not result:
        result.append("sam3.pt")
    return result

# core/path_safety.py
"""경로 검증 유틸리티 — path traversal / 시스템 디렉터리 쓰기 방어.

입력(읽기) / 출력(쓰기) 양쪽에서 재사용할 수 있는 얇은 래퍼.
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import unquote

logger = logging.getLogger(__name__)

# Windows/Unix 주요 시스템 루트 — 쓰기 금지, 읽기도 명시 허용 외엔 금지
_FORBIDDEN_ROOTS: tuple[str, ...] = (
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\programdata",
    "/etc",
    "/var",
    "/usr",
    "/proc",
    "/sys",
    "/boot",
)

_DEFAULT_IMAGE_EXTS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif",
})


def _strip_file_scheme(path: str) -> str:
    """file:// 스킴과 URL 인코딩을 해제."""
    path = unquote(str(path))
    for prefix in ("file:///", "file://"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def _is_forbidden(resolved: Path) -> bool:
    lowered = str(resolved).lower()
    return any(lowered.startswith(root) for root in _FORBIDDEN_ROOTS)


class UnsafePathError(ValueError):
    """검증에 실패한 경로가 사용되었음을 나타낸다."""


def safe_input_path(
    raw: str,
    *,
    allowed_exts: frozenset[str] | None = _DEFAULT_IMAGE_EXTS,
) -> str | None:
    """외부(Vue/설정/EXIF)에서 온 읽기용 경로를 검증한다.

    - 존재 + 일반 파일
    - 시스템 디렉터리 차단
    - 확장자 화이트리스트 (None이면 생략)
    성공 시 정규화된 절대 경로, 실패 시 None.
    """
    if not raw:
        return None
    try:
        resolved = Path(_strip_file_scheme(raw)).resolve(strict=False)
    except (OSError, ValueError) as e:
        logger.warning("input path resolve failed: %r (%s)", raw, e)
        return None
    if _is_forbidden(resolved):
        logger.warning("input path forbidden root: %s", resolved)
        return None
    if allowed_exts is not None and resolved.suffix.lower() not in allowed_exts:
        logger.warning("input path blocked ext: %s", resolved)
        return None
    if not resolved.is_file():
        return None
    return str(resolved)


def safe_output_dir(raw: str, *, create: bool = True) -> str:
    """설정에서 받은 출력 폴더 경로를 검증.

    - 시스템 디렉터리로 쓰기 금지
    - 드라이브/루트 자체(C:\\, /)로의 직접 쓰기 금지
    - 필요 시 mkdir(parents=True)
    실패 시 UnsafePathError.
    """
    if not raw:
        raise UnsafePathError("output folder is empty")
    try:
        resolved = Path(_strip_file_scheme(raw)).resolve(strict=False)
    except (OSError, ValueError) as e:
        raise UnsafePathError(f"resolve failed: {e}") from e
    if _is_forbidden(resolved):
        raise UnsafePathError(f"forbidden system dir: {resolved}")
    if resolved.parent == resolved:
        raise UnsafePathError(f"refuse to write to filesystem root: {resolved}")
    if create:
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise UnsafePathError(f"mkdir failed: {e}") from e
    if not resolved.is_dir():
        raise UnsafePathError(f"not a directory: {resolved}")
    return str(resolved)


def safe_output_file(raw: str, output_root: str) -> str:
    """output_root 아래로만 쓸 수 있도록 제약된 파일 경로를 만든다.

    - raw가 절대 경로이면 output_root 하위인지 검증
    - raw가 상대 경로이면 output_root와 join 후 하위 검증
    실패 시 UnsafePathError.
    """
    root = Path(safe_output_dir(output_root, create=True))
    cand = Path(_strip_file_scheme(raw))
    if not cand.is_absolute():
        cand = root / cand
    try:
        resolved = cand.resolve(strict=False)
    except (OSError, ValueError) as e:
        raise UnsafePathError(f"resolve failed: {e}") from e
    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise UnsafePathError(f"path escapes output root: {resolved}") from e
    return str(resolved)


def safe_config_file(raw: str, *, must_exist: bool = True) -> str:
    """설정 파일 경로(워크플로우 JSON 등) 검증.

    - 시스템 디렉터리 차단
    - 필요 시 존재 강제
    실패 시 UnsafePathError.
    """
    if not raw:
        raise UnsafePathError("path is empty")
    try:
        resolved = Path(_strip_file_scheme(raw)).resolve(strict=False)
    except (OSError, ValueError) as e:
        raise UnsafePathError(f"resolve failed: {e}") from e
    if _is_forbidden(resolved):
        raise UnsafePathError(f"forbidden system dir: {resolved}")
    if must_exist and not resolved.is_file():
        raise UnsafePathError(f"file not found: {resolved}")
    return str(resolved)

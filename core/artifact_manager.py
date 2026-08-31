"""Verified, resumable installation of optional Creator artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional
import hashlib
import os
import shutil


class ArtifactError(RuntimeError):
    pass


class ArtifactCancelled(ArtifactError):
    pass


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    url: str
    relative_path: str
    size: int
    sha256: str
    feature: str = "creator"
    license_id: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping) -> "ArtifactSpec":
        return cls(
            artifact_id=str(raw.get("id", "")).strip(),
            url=str(raw.get("url", "")).strip(),
            relative_path=str(raw.get("path", "")).strip(),
            size=int(raw.get("size", 0) or 0),
            sha256=str(raw.get("sha256", "")).lower().strip(),
            feature=str(raw.get("feature", "creator")).strip() or "creator",
            license_id=str(raw.get("license", "")).strip(),
        )


@dataclass(frozen=True)
class ArtifactStatus:
    artifact_id: str
    path: str
    state: str
    downloaded: int
    total: int
    verified: bool = False


class RequestsArtifactTransport:
    """Production HTTP adapter. Tests provide an in-memory adapter."""

    def open(self, url: str, offset: int):
        import requests

        headers = {"Range": f"bytes={offset}-"} if offset else {}
        response = requests.get(url, headers=headers, stream=True, timeout=(15, 120))
        response.raise_for_status()
        if offset and response.status_code != 206:
            # Server ignored Range. Caller will restart from zero.
            response.close()
            fresh_response, _ = self.open(url, 0)
            return fresh_response, False
        return response, True


class ArtifactManager:
    """Install one verified artifact through ``status`` and ``ensure``."""

    def __init__(self, root: Path | str, transport=None) -> None:
        self.root = Path(root).resolve()
        self.transport = transport or RequestsArtifactTransport()

    def status(self, spec: ArtifactSpec) -> ArtifactStatus:
        target = self._target(spec)
        if not target.is_file():
            part = target.with_suffix(target.suffix + ".part")
            downloaded = part.stat().st_size if part.is_file() else 0
            return ArtifactStatus(spec.artifact_id, str(target), "missing", downloaded, spec.size)
        size = target.stat().st_size
        if spec.size and size != spec.size:
            return ArtifactStatus(spec.artifact_id, str(target), "corrupt", size, spec.size)
        verified = self._sha256(target) == spec.sha256
        return ArtifactStatus(
            spec.artifact_id,
            str(target),
            "ready" if verified else "corrupt",
            size,
            spec.size,
            verified,
        )

    def ensure(
        self,
        spec: ArtifactSpec,
        *,
        progress: Optional[Callable[[ArtifactStatus], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> ArtifactStatus:
        self._validate(spec)
        current = self.status(spec)
        if current.verified:
            if progress:
                progress(current)
            return current

        target = self._target(spec)
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(target.suffix + ".part")
        offset = part.stat().st_size if part.is_file() else 0
        if spec.size and offset > spec.size:
            part.unlink()
            offset = 0

        remaining = max(0, spec.size - offset)
        free = shutil.disk_usage(target.parent).free
        # Keep a small safety margin for filesystem metadata and the final rename.
        required = remaining + max(64 * 1024 * 1024, int(spec.size * 0.01))
        if spec.size and free < required:
            raise ArtifactError(
                f"디스크 여유 공간이 부족합니다: 필요 {required} bytes, 사용 가능 {free} bytes"
            )

        response_info = self.transport.open(spec.url, offset)
        if isinstance(response_info, tuple) and len(response_info) == 2:
            response, resumed = response_info
        else:
            response, resumed = response_info, True
        if offset and not resumed:
            offset = 0
            if part.exists():
                part.unlink()

        mode = "ab" if offset else "wb"
        downloaded = offset
        try:
            with part.open(mode) as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if cancelled and cancelled():
                        raise ArtifactCancelled("다운로드가 취소되었습니다")
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if spec.size and downloaded > spec.size:
                        raise ArtifactError("다운로드 크기가 manifest를 초과했습니다")
                    if progress:
                        progress(
                            ArtifactStatus(
                                spec.artifact_id,
                                str(target),
                                "downloading",
                                downloaded,
                                spec.size,
                            )
                        )
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            close = getattr(response, "close", None)
            if close:
                close()

        if spec.size and downloaded != spec.size:
            raise ArtifactError(f"다운로드 크기 불일치: {downloaded} != {spec.size}")
        digest = self._sha256(part)
        if digest != spec.sha256:
            raise ArtifactError(f"SHA-256 불일치: {spec.artifact_id}")
        os.replace(part, target)
        ready = ArtifactStatus(
            spec.artifact_id, str(target), "ready", downloaded, spec.size, True
        )
        if progress:
            progress(ready)
        return ready

    def _target(self, spec: ArtifactSpec) -> Path:
        candidate = (self.root / spec.relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactError("아티팩트 경로가 설치 루트를 벗어납니다") from exc
        return candidate

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate(spec: ArtifactSpec) -> None:
        if not spec.artifact_id or not spec.url or not spec.relative_path:
            raise ArtifactError("manifest의 id, url, path는 필수입니다")
        if spec.size <= 0:
            raise ArtifactError("manifest의 size는 양수여야 합니다")
        if len(spec.sha256) != 64 or any(ch not in "0123456789abcdef" for ch in spec.sha256):
            raise ArtifactError("manifest의 sha256이 올바르지 않습니다")


def feature_specs(manifest: Iterable[Mapping], feature: str) -> list[ArtifactSpec]:
    return [
        spec
        for spec in (ArtifactSpec.from_mapping(item) for item in manifest)
        if spec.feature == feature
    ]

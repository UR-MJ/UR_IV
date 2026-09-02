"""Central, traversal-safe paths for application-owned persistent storage.

The module owns *where* application files live, not how domain data is
serialised.  Callers may inject a temporary project root through
``StoragePaths`` in tests; normal runtime code uses the module-level helpers.

Legacy migration is deliberately conservative.  A legacy file is copied to a
temporary sibling, flushed, atomically published, and only then removed.  A
pre-existing destination always wins and a failed migration leaves the source
untouched.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypeAlias


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PathInput: TypeAlias = str | os.PathLike[str]
LegacyPaths: TypeAlias = PathInput | Iterable[PathInput] | None


class StoragePathError(ValueError):
    """Raised when a storage name or migration source escapes the project."""


class StorageMigrationError(OSError):
    """Raised when a legacy file could not be safely migrated."""


class StoragePaths:
    """Resolve application storage beneath one explicitly supplied root.

    Four boundaries are intentionally exposed:

    - ``config``: durable application preferences and path configuration
    - ``user_data``: user-authored presets and documents
    - ``cache``: disposable, reproducible runtime data
    - ``logs``: diagnostics and crash reports

    File methods accept nested relative names, create their parent directory,
    and reject absolute paths, drive-relative paths, ``..`` traversal, and
    symlink-based escapes.
    """

    def __init__(self, project_root: PathInput = PROJECT_ROOT) -> None:
        root = Path(project_root).expanduser().resolve(strict=False)
        self.project_root = root
        self.config_dir = root / "config"
        self.user_data_dir = root / "user_data"
        self.cache_dir = root / "cache"
        self.log_dir = root / "logs"

    def config_file(
        self,
        name: PathInput,
        *,
        legacy_paths: LegacyPaths = None,
    ) -> Path:
        return self._file(self.config_dir, name, legacy_paths=legacy_paths)

    def user_data_file(
        self,
        name: PathInput,
        *,
        legacy_paths: LegacyPaths = None,
    ) -> Path:
        return self._file(self.user_data_dir, name, legacy_paths=legacy_paths)

    def cache_file(
        self,
        name: PathInput,
        *,
        legacy_paths: LegacyPaths = None,
    ) -> Path:
        return self._file(self.cache_dir, name, legacy_paths=legacy_paths)

    def log_file(
        self,
        name: PathInput,
        *,
        legacy_paths: LegacyPaths = None,
    ) -> Path:
        return self._file(self.log_dir, name, legacy_paths=legacy_paths)

    def _file(self, base: Path, name: PathInput, *, legacy_paths: LegacyPaths) -> Path:
        relative = self._safe_relative_name(name)
        resolved_base = base.resolve(strict=False)
        self._require_within(resolved_base, self.project_root, label="storage boundary")
        resolved_base.mkdir(parents=True, exist_ok=True)
        destination = (resolved_base / relative).resolve(strict=False)
        self._require_within(destination, resolved_base, label="storage destination")
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Resolve again after mkdir so an existing symlink in a newly reached
        # parent cannot redirect the destination outside its storage boundary.
        destination = destination.resolve(strict=False)
        self._require_within(destination, resolved_base, label="storage destination")

        if destination.exists():
            if not destination.is_file():
                raise StoragePathError(f"storage destination is not a file: {destination}")
            return destination

        for legacy in self._iter_legacy_paths(legacy_paths):
            source = self._safe_legacy_path(legacy)
            if source == destination or not source.exists():
                continue
            if source.is_symlink() or not source.is_file():
                raise StoragePathError(f"legacy path is not a regular file: {source}")
            self._migrate_file(source, destination)
            break
        return destination

    @staticmethod
    def _safe_relative_name(name: PathInput) -> Path:
        raw_value = os.fspath(name)
        if not isinstance(raw_value, str):
            raise TypeError("storage name must be a string or text path")
        if not raw_value or not raw_value.strip() or "\x00" in raw_value:
            raise StoragePathError("storage name must be a non-empty relative file name")

        # Treat both slash styles as separators even when tests run on a host
        # whose native separator differs from the stored Windows paths.
        portable = raw_value.replace("\\", "/")
        windows = PureWindowsPath(raw_value)
        if windows.drive or windows.is_absolute() or PurePosixPath(portable).is_absolute():
            raise StoragePathError(f"absolute storage path is not allowed: {raw_value!r}")

        parts = portable.split("/")
        if any(part == ".." for part in parts):
            raise StoragePathError(f"storage path traversal is not allowed: {raw_value!r}")
        clean_parts = [part for part in parts if part not in ("", ".")]
        if not clean_parts:
            raise StoragePathError("storage name must identify a file")
        return Path(*clean_parts)

    def _safe_legacy_path(self, legacy: PathInput) -> Path:
        raw_value = os.fspath(legacy)
        if not isinstance(raw_value, str):
            raise TypeError("legacy path must be a string or text path")
        candidate = Path(raw_value).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        resolved = candidate.resolve(strict=False)
        self._require_within(resolved, self.project_root, label="legacy path")
        return resolved

    @staticmethod
    def _iter_legacy_paths(legacy_paths: LegacyPaths) -> tuple[PathInput, ...]:
        if legacy_paths is None:
            return ()
        if isinstance(legacy_paths, (str, os.PathLike)):
            return (legacy_paths,)
        return tuple(legacy_paths)

    @staticmethod
    def _require_within(candidate: Path, root: Path, *, label: str) -> None:
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise StoragePathError(f"{label} escapes project storage: {candidate}") from exc

    @staticmethod
    def _migrate_file(source: Path, destination: Path) -> None:
        """Publish a copy atomically, then remove the legacy source.

        Copying first is intentional: unlike a direct rename, every failure up
        to and including publication leaves the original file in place.  A
        source unlink failure after publication is non-fatal and merely leaves
        a harmless legacy duplicate; the destination wins on later calls.
        """

        temporary: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.migrating-",
                dir=destination.parent,
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            shutil.copy2(source, temporary)
            # Windows' ``fsync``/``_commit`` requires a writable descriptor.
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())

            # A destination created while the copy was in progress takes
            # precedence.  In that case the source remains untouched.
            if destination.exists():
                return
            os.replace(temporary, destination)
            temporary = None
            try:
                source.unlink()
            except OSError:
                # The durable destination is already available.  Keeping the
                # source is safer than treating cleanup as migration failure.
                pass
        except Exception as exc:
            raise StorageMigrationError(
                f"failed to migrate legacy file {source} -> {destination}: {exc}"
            ) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


storage_paths = StoragePaths(PROJECT_ROOT)


def config_file(name: PathInput, *, legacy_paths: LegacyPaths = None) -> Path:
    return storage_paths.config_file(name, legacy_paths=legacy_paths)


def user_data_file(name: PathInput, *, legacy_paths: LegacyPaths = None) -> Path:
    return storage_paths.user_data_file(name, legacy_paths=legacy_paths)


def cache_file(name: PathInput, *, legacy_paths: LegacyPaths = None) -> Path:
    return storage_paths.cache_file(name, legacy_paths=legacy_paths)


def log_file(name: PathInput, *, legacy_paths: LegacyPaths = None) -> Path:
    return storage_paths.log_file(name, legacy_paths=legacy_paths)


__all__ = [
    "PROJECT_ROOT",
    "StorageMigrationError",
    "StoragePathError",
    "StoragePaths",
    "cache_file",
    "config_file",
    "log_file",
    "storage_paths",
    "user_data_file",
]

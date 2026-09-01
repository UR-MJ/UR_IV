"""Manifest-backed access to the application's bundled tag data.

``TagDatabase`` is the single seam between tag-data consumers and the on-disk
layout.  Callers select a stable :class:`TagAsset` identifier instead of
depending on filenames, formats, or directory structure.  The manifest and
individual assets are loaded only when a method needs them.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TAG_DATABASE_ROOT = PROJECT_ROOT / "tags_db"
MANIFEST_VERSION = 1


class TagAsset(str, Enum):
    """Stable identifiers published by ``tags_db/manifest.json``."""

    AUTOCOMPLETE_CATALOG = "autocomplete_catalog"
    KOREAN_TAG_CATALOG = "korean_tag_catalog"
    RATING_COUNTS = "rating_counts"
    CHARACTER_PROFILES = "character_profiles"
    CHARACTER_FEATURES = "character_features"
    CHARACTER_PROMPT_TAGS = "character_prompt_tags"
    CURATED_CHARACTER_SERIES = "curated_character_series"
    EXTENDED_CHARACTER_SERIES = "extended_character_series"
    TAG_GROUPS = "tag_groups"
    TAG_IMPLICATIONS = "tag_implications"
    CLOTHING_REGIONS = "clothing_regions"
    EXPRESSION_TAGS = "expression_tags"
    LOCATION_TAGS = "location_tags"
    META_TAGS = "meta_tags"
    OBJECT_TAGS = "object_tags"
    POSE_ACTION_TAGS = "pose_action_tags"
    APPEARANCE_TAGS_CURATED = "appearance_tags_curated"
    APPEARANCE_TAGS_EXTENDED = "appearance_tags_extended"
    CLOTHING_TAGS_CURATED = "clothing_tags_curated"
    CLOTHING_TAGS_EXTENDED = "clothing_tags_extended"
    COLOR_TERMS_CURATED = "color_terms_curated"
    COLOR_TERMS_EXTENDED = "color_terms_extended"


class TagDatabase:
    """Resolve and read tag assets through a versioned manifest.

    ``root`` is the directory containing ``manifest.json``.  Construction does
    no filesystem I/O.  Asset paths must be relative descendants of ``root``;
    absolute paths, parent traversal, drive-qualified paths, and symlink escapes
    are rejected before a path is returned or opened.
    """

    _JSON_FORMATS = frozenset({"json"})
    _LINE_FORMATS = frozenset({"text", "txt", "lines"})
    _PARQUET_FORMATS = frozenset({"parquet"})

    def __init__(self, root: str | Path | None = None) -> None:
        selected_root = DEFAULT_TAG_DATABASE_ROOT if root is None else Path(root)
        self._root = selected_root.expanduser().resolve(strict=False)
        self._manifest_cache: dict[str, Any] | None = None

    @property
    def root(self) -> Path:
        """Absolute directory containing the manifest and its assets."""

        return self._root

    def path(self, asset: TagAsset | str) -> Path:
        """Return the traversal-safe path registered for ``asset``.

        The returned path is not required to exist.  Readers naturally raise
        ``FileNotFoundError`` when a registered file is absent, while
        :meth:`validate_assets` reports all missing files in one pass.
        """

        asset_id = self._asset_id(asset)
        descriptor = self._descriptor(asset_id)
        return self._safe_asset_path(descriptor.get("path"), asset_id)

    def read_json(self, asset: TagAsset | str) -> Any:
        """Read a manifest asset declared as JSON."""

        asset_id = self._asset_id(asset)
        self._require_format(asset_id, self._JSON_FORMATS)
        with self.path(asset_id).open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)

    def read_lines(self, asset: TagAsset | str) -> list[str]:
        """Read non-empty, whitespace-trimmed lines from a text asset."""

        asset_id = self._asset_id(asset)
        self._require_format(asset_id, self._LINE_FORMATS)
        with self.path(asset_id).open("r", encoding="utf-8-sig") as handle:
            return [line for raw_line in handle if (line := raw_line.strip())]

    def read_parquet(
        self,
        asset: TagAsset | str,
        columns: Sequence[str] | None = None,
    ):
        """Read a Parquet asset, optionally projecting specific columns.

        Pandas is imported lazily so lightweight consumers can resolve JSON and
        text assets without paying its import cost.
        """

        asset_id = self._asset_id(asset)
        self._require_format(asset_id, self._PARQUET_FORMATS)
        import pandas as pd

        requested_columns = None if columns is None else list(columns)
        return pd.read_parquet(self.path(asset_id), columns=requested_columns)

    def load_tag_groups(self) -> dict[str, set[str]]:
        """Return ``group -> tags`` from the canonical group table."""

        frame = self.read_parquet(TagAsset.TAG_GROUPS, columns=["group", "tag"])
        return self._collect_pairs(frame, "group", "tag", TagAsset.TAG_GROUPS)

    def load_active_implications(self) -> dict[str, set[str]]:
        """Return ``antecedent -> consequents`` from active implications."""

        frame = self.read_parquet(
            TagAsset.TAG_IMPLICATIONS,
            columns=["antecedent", "consequent"],
        )
        return self._collect_pairs(
            frame,
            "antecedent",
            "consequent",
            TagAsset.TAG_IMPLICATIONS,
        )

    def all_group_tags(self) -> set[str]:
        """Return the union of every tag in the canonical group table."""

        groups = self.load_tag_groups()
        return set().union(*groups.values()) if groups else set()

    def validate_assets(self) -> list[str]:
        """Return all manifest, path, file, and canonical-schema problems.

        Validation is intentionally non-throwing so startup diagnostics can
        show every actionable problem at once.  It checks every published
        :class:`TagAsset`, rejects unrecognised manifest entries, verifies basic
        descriptor metadata and file presence, then checks the two canonical
        relational schemas used by the convenience loaders.
        """

        errors: list[str] = []
        try:
            manifest = self._manifest()
        except Exception as exc:
            return [f"manifest: {exc}"]

        assets = manifest["assets"]
        known_ids = {asset.value for asset in TagAsset}
        actual_ids = set(assets)

        for asset_id in sorted(known_ids - actual_ids):
            errors.append(f"{asset_id}: manifest entry is missing")
        for asset_id in sorted(actual_ids - known_ids):
            errors.append(f"{asset_id}: unknown asset identifier")

        for asset_id in sorted(actual_ids & known_ids):
            descriptor = assets[asset_id]
            if not isinstance(descriptor, Mapping):
                errors.append(f"{asset_id}: descriptor must be an object")
                continue

            asset_format = descriptor.get("format")
            if not isinstance(asset_format, str) or not asset_format.strip():
                errors.append(f"{asset_id}: format must be a non-empty string")

            description = descriptor.get("description")
            if not isinstance(description, str) or not description.strip():
                errors.append(f"{asset_id}: description must be a non-empty string")

            columns = descriptor.get("columns")
            if columns is not None and (
                not isinstance(columns, list)
                or not all(isinstance(column, str) and column for column in columns)
            ):
                errors.append(f"{asset_id}: columns must be a list of non-empty strings")

            try:
                asset_path = self._safe_asset_path(descriptor.get("path"), asset_id)
            except Exception as exc:
                errors.append(f"{asset_id}: {exc}")
                continue
            if not asset_path.exists():
                errors.append(f"{asset_id}: file does not exist: {asset_path}")
            elif not asset_path.is_file():
                errors.append(f"{asset_id}: asset path is not a file: {asset_path}")
            elif (
                isinstance(asset_format, str)
                and asset_format.strip().casefold() in self._PARQUET_FORMATS
                and isinstance(columns, list)
            ):
                try:
                    import pyarrow.parquet as pq

                    actual_columns = set(pq.read_schema(asset_path).names)
                    missing = set(columns) - actual_columns
                    if missing:
                        joined = ", ".join(sorted(missing))
                        errors.append(f"{asset_id}: missing columns: {joined}")
                except Exception as exc:
                    errors.append(f"{asset_id}: cannot read parquet schema: {exc}")

        return errors

    def _manifest(self) -> dict[str, Any]:
        if self._manifest_cache is not None:
            return self._manifest_cache

        manifest_path = self._root / "manifest.json"
        with manifest_path.open("r", encoding="utf-8-sig") as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be a JSON object")
        if manifest.get("version") != MANIFEST_VERSION:
            raise ValueError(
                f"unsupported manifest version: {manifest.get('version')!r} "
                f"(expected {MANIFEST_VERSION})"
            )
        assets = manifest.get("assets")
        if not isinstance(assets, dict):
            raise ValueError("manifest assets must be an object")
        if not all(isinstance(asset_id, str) for asset_id in assets):
            raise ValueError("manifest asset identifiers must be strings")

        self._manifest_cache = manifest
        return manifest

    def _descriptor(self, asset_id: str) -> Mapping[str, Any]:
        descriptor = self._manifest()["assets"].get(asset_id)
        if descriptor is None:
            raise KeyError(f"asset is not registered in manifest: {asset_id}")
        if not isinstance(descriptor, Mapping):
            raise ValueError(f"{asset_id}: descriptor must be an object")
        return descriptor

    @staticmethod
    def _asset_id(asset: TagAsset | str) -> str:
        try:
            return TagAsset(asset).value
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown tag asset: {asset!r}") from exc

    def _safe_asset_path(self, value: Any, asset_id: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("path must be a non-empty relative string")

        raw_path = value.strip()
        windows_path = PureWindowsPath(raw_path)
        portable_path = PurePosixPath(raw_path.replace("\\", "/"))
        if (
            windows_path.is_absolute()
            or bool(windows_path.drive)
            or portable_path.is_absolute()
            or ".." in portable_path.parts
        ):
            raise ValueError(f"unsafe asset path: {raw_path!r}")

        relative_path = Path(*portable_path.parts)
        candidate = (self._root / relative_path).resolve(strict=False)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise ValueError(f"unsafe asset path: {raw_path!r}") from exc
        return candidate

    def _require_format(self, asset_id: str, accepted: Iterable[str]) -> None:
        descriptor = self._descriptor(asset_id)
        declared = descriptor.get("format")
        normalised = declared.strip().casefold() if isinstance(declared, str) else ""
        accepted_formats = set(accepted)
        if normalised not in accepted_formats:
            expected = ", ".join(sorted(accepted_formats))
            raise ValueError(
                f"{asset_id}: expected format {expected}, found {declared!r}"
            )

    @staticmethod
    def _collect_pairs(frame, key_column: str, value_column: str, asset: TagAsset):
        import pandas as pd

        missing = {key_column, value_column} - set(frame.columns)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"{asset.value}: missing columns: {joined}")

        result: dict[str, set[str]] = {}
        for key_value, item_value in frame[[key_column, value_column]].itertuples(
            index=False,
            name=None,
        ):
            if pd.isna(key_value) or pd.isna(item_value):
                continue
            key = str(key_value).strip()
            item = str(item_value).strip()
            if key and item:
                result.setdefault(key, set()).add(item)
        return result


DEFAULT_TAG_DATABASE = TagDatabase()


def get_tag_database(root: str | Path | None = None) -> TagDatabase:
    """Return the default database or an isolated database rooted elsewhere."""

    if root is None:
        return DEFAULT_TAG_DATABASE
    return TagDatabase(root)


__all__ = [
    "DEFAULT_TAG_DATABASE",
    "TagAsset",
    "TagDatabase",
    "get_tag_database",
]

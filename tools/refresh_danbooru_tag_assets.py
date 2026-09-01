#!/usr/bin/env python3
"""Refresh the runtime Danbooru tag assets from reproducible sources.

Inputs may be local paths or HTTP(S) URLs.  The source CSV format is the
headerless tagcomplete layout ``tag,category,count,aliases``.  PYU supplies the
catalog and aliases; the daily file overlays its newer category/count values;
Danbooru's active aliases and implications are fetched with stable ID-cursor
pagination.

All four outputs are built under a same-volume staging directory, validated,
and individually replaced with ``os.replace``.  The source metadata file is
committed last and therefore acts as the transaction marker.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


TOOL_VERSION = "1.0.0"
DEFAULT_API_BASE = "https://shima.donmai.us"
CSV_RELATIVE = Path("autocomplete/danbooru_autocomplete_catalog.csv")
ALIASES_RELATIVE = Path("taxonomy/danbooru_active_tag_aliases.parquet")
IMPLICATIONS_RELATIVE = Path("taxonomy/danbooru_active_tag_implications.parquet")
METADATA_RELATIVE = Path("catalogs/danbooru_source_metadata.json")
OUTPUT_RELATIVES = (
    CSV_RELATIVE,
    ALIASES_RELATIVE,
    IMPLICATIONS_RELATIVE,
    METADATA_RELATIVE,
)


class RefreshError(RuntimeError):
    """Expected input, network, validation, or publication failure."""


@dataclass
class TagRecord:
    category: int
    count: int
    aliases: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Relationship:
    id: int
    antecedent: str
    consequent: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _log(message: str) -> None:
    print(message, flush=True)


def _sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_tag(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", "_", text)


def _normalise_aliases(value: Any) -> set[str]:
    aliases: set[str] = set()
    for raw in str(value or "").split(","):
        alias = _normalise_tag(raw)
        if alias:
            aliases.add(alias)
    return aliases


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _new_session():
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RefreshError("requests is required: pip install requests") from exc
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": (
                f"AI-Studio-Pro-Danbooru-Refresh/{TOOL_VERSION} "
                "(read-only public data refresh)"
            ),
        }
    )
    return session


def _request(session: Any, url: str, *, params: dict[str, Any] | None, args: argparse.Namespace):
    last_error: Exception | None = None
    for attempt in range(args.retries + 1):
        try:
            response = session.get(
                url,
                params=params,
                timeout=(args.connect_timeout, args.read_timeout),
                stream=False,
            )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= args.retries:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = max(float(retry_after), args.retry_backoff * (2**attempt))
                except ValueError:
                    delay = args.retry_backoff * (2**attempt)
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt >= args.retries:
                break
            time.sleep(args.retry_backoff * (2**attempt))
    raise RefreshError(f"request failed after retries: {url}: {last_error}") from last_error


def _is_http(value: str) -> bool:
    return urlparse(value).scheme.lower() in {"http", "https"}


def _local_path(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme.lower() == "file":
        raw = unquote(parsed.path)
        if parsed.netloc:
            raw = f"//{parsed.netloc}{raw}"
        if re.match(r"^/[A-Za-z]:/", raw):
            raw = raw[1:]
        return Path(raw).expanduser().resolve(strict=True)
    return Path(value).expanduser().resolve(strict=True)


def _materialise_source(
    specification: str,
    destination: Path,
    *,
    session: Any,
    args: argparse.Namespace,
) -> tuple[Path, dict[str, Any]]:
    """Return a readable local file and provenance metadata."""

    if _is_http(specification):
        response = _request(session, specification, params=None, args=args)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            handle.write(response.content)
            handle.flush()
            os.fsync(handle.fileno())
        record = {
            "kind": "url",
            "requested": specification,
            "resolved": response.url,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "size_bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
        }
        return destination, record
    source = _local_path(specification)
    if not source.is_file():
        raise RefreshError(f"source is not a file: {source}")
    return source, {
        "kind": "path",
        "requested": specification,
        "resolved": str(source),
        "size_bytes": source.stat().st_size,
        "sha256": _sha256(source),
        "last_modified": datetime.fromtimestamp(
            source.stat().st_mtime, timezone.utc
        ).isoformat(),
    }


def _read_tag_csv(path: Path, *, source_label: str) -> tuple[dict[str, TagRecord], int]:
    records: dict[str, TagRecord] = {}
    raw_rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row_number, row in enumerate(reader, 1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != 4:
                raise RefreshError(
                    f"{source_label} row {row_number}: expected 4 columns, got {len(row)}"
                )
            if row_number == 1 and row[0].strip().casefold() in {"tag", "name"}:
                continue
            tag = _normalise_tag(row[0])
            if not tag:
                raise RefreshError(f"{source_label} row {row_number}: empty tag")
            try:
                category = int(row[1].strip())
                count = int(row[2].strip())
            except ValueError as exc:
                raise RefreshError(
                    f"{source_label} row {row_number}: invalid category/count"
                ) from exc
            if category not in {0, 1, 3, 4, 5}:
                raise RefreshError(
                    f"{source_label} row {row_number}: unsupported category {category}"
                )
            if count < 0:
                raise RefreshError(f"{source_label} row {row_number}: negative count")
            aliases = _normalise_aliases(row[3])
            aliases.discard(tag)
            previous = records.get(tag)
            if previous is None:
                records[tag] = TagRecord(category, count, aliases)
            else:
                if (previous.category, previous.count) != (category, count):
                    raise RefreshError(
                        f"{source_label}: duplicate tag with conflicting data: {tag}"
                    )
                previous.aliases.update(aliases)
            raw_rows += 1
    if not records:
        raise RefreshError(f"{source_label} contained no tag rows")
    return records, raw_rows


def _fetch_relationships(
    kind: str,
    *,
    session: Any,
    args: argparse.Namespace,
) -> tuple[list[Relationship], dict[str, Any]]:
    if kind not in {"tag_aliases", "tag_implications"}:
        raise ValueError(kind)
    endpoint = f"{args.api_base.rstrip('/')}/{kind}.json"
    cursor: int | None = None
    seen_ids: set[int] = set()
    relationships: list[Relationship] = []
    pages = 0
    latest_updated_at = ""
    previous_page_min: int | None = None
    while True:
        params: dict[str, Any] = {
            "limit": args.page_limit,
            "search[status]": "active",
            "only": "id,antecedent_name,consequent_name,status,updated_at",
        }
        if cursor is not None:
            params["page"] = f"b{cursor}"
        response = _request(session, endpoint, params=params, args=args)
        try:
            payload = response.json()
        except ValueError as exc:
            raise RefreshError(f"{kind}: API returned non-JSON data") from exc
        if not isinstance(payload, list):
            raise RefreshError(f"{kind}: API response must be a JSON list")
        pages += 1
        if not payload:
            break
        page_ids: list[int] = []
        for item in payload:
            if not isinstance(item, dict):
                raise RefreshError(f"{kind}: relationship must be an object")
            try:
                relation_id = int(item["id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RefreshError(f"{kind}: relationship has invalid id") from exc
            if relation_id <= 0 or relation_id in seen_ids:
                raise RefreshError(f"{kind}: duplicate/non-positive id {relation_id}")
            if str(item.get("status", "")).casefold() != "active":
                raise RefreshError(f"{kind}: non-active record {relation_id}")
            antecedent = _normalise_tag(item.get("antecedent_name"))
            consequent = _normalise_tag(item.get("consequent_name"))
            if not antecedent or not consequent:
                raise RefreshError(f"{kind}: empty relationship name at id {relation_id}")
            if antecedent == consequent:
                raise RefreshError(f"{kind}: self relationship at id {relation_id}")
            updated_at = str(item.get("updated_at") or "")
            latest_updated_at = max(latest_updated_at, updated_at)
            seen_ids.add(relation_id)
            page_ids.append(relation_id)
            relationships.append(
                Relationship(relation_id, antecedent, consequent, updated_at)
            )
        # A b<ID> cursor forces ID-desc order. Verify it instead of trusting the API.
        if any(left <= right for left, right in zip(page_ids, page_ids[1:])):
            raise RefreshError(f"{kind}: page is not strictly ID-descending")
        page_min = min(page_ids)
        if previous_page_min is not None and max(page_ids) >= previous_page_min:
            raise RefreshError(f"{kind}: ID cursor pages overlap or move backwards")
        previous_page_min = page_min
        if cursor is not None and page_min >= cursor:
            raise RefreshError(f"{kind}: pagination cursor did not advance")
        cursor = page_min
        if pages % 10 == 0:
            _log(f"  {kind}: {len(relationships):,} active rows / {pages} pages")
        if args.api_delay:
            time.sleep(args.api_delay)

    pairs = {(item.antecedent, item.consequent) for item in relationships}
    if len(pairs) != len(relationships):
        raise RefreshError(f"{kind}: duplicate antecedent/consequent pairs")
    if kind == "tag_aliases":
        aliases: dict[str, str] = {}
        for item in relationships:
            previous = aliases.setdefault(item.antecedent, item.consequent)
            if previous != item.consequent:
                raise RefreshError(
                    f"tag_aliases: {item.antecedent} maps to both {previous} "
                    f"and {item.consequent}"
                )
    canonical_payload = [
        {
            "id": item.id,
            "antecedent": item.antecedent,
            "consequent": item.consequent,
            "updated_at": item.updated_at,
        }
        for item in sorted(relationships, key=lambda value: value.id)
    ]
    canonical_sha = hashlib.sha256(
        json.dumps(canonical_payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return relationships, {
        "url": endpoint,
        "filter": "status=active",
        "pagination": "id_desc page=b<minimum_id>",
        "requested_page_limit": args.page_limit,
        "pages": pages,
        "rows": len(relationships),
        "latest_updated_at": latest_updated_at or None,
        "canonical_sha256": canonical_sha,
    }


def _resolved_alias_map(relationships: Iterable[Relationship]) -> dict[str, str]:
    direct = {item.antecedent: item.consequent for item in relationships}
    resolved: dict[str, str] = {}

    def resolve(alias: str) -> str:
        if alias in resolved:
            return resolved[alias]
        trail: list[str] = []
        current = alias
        while current in direct:
            if current in trail:
                cycle = " -> ".join([*trail, current])
                raise RefreshError(f"active alias cycle: {cycle}")
            trail.append(current)
            current = direct[current]
        for value in trail:
            resolved[value] = current
        return current

    for antecedent in sorted(direct):
        resolve(antecedent)
    if any(alias == canonical for alias, canonical in resolved.items()):
        raise RefreshError("resolved alias map contains a self relationship")
    return resolved


def _merge_tags(
    pyu: dict[str, TagRecord],
    daily: dict[str, TagRecord],
    official_aliases: dict[str, str],
) -> tuple[dict[str, TagRecord], dict[str, int]]:
    merged = {
        tag: TagRecord(row.category, row.count, set(row.aliases))
        for tag, row in pyu.items()
    }
    daily_added = 0
    for tag, row in daily.items():
        target = merged.get(tag)
        if target is None:
            merged[tag] = TagRecord(row.category, row.count, set(row.aliases))
            daily_added += 1
        else:
            # The dated daily snapshot is authoritative for category and count.
            target.category = row.category
            target.count = row.count
            target.aliases.update(row.aliases)

    synthesised = 0
    removed_alias_rows = 0
    # First ensure every final canonical exists, using an aliased row as fallback.
    for alias, canonical in official_aliases.items():
        if canonical not in merged:
            source = merged.get(alias)
            if source is None:
                merged[canonical] = TagRecord(0, 0, set())
                synthesised += 1
            else:
                merged[canonical] = TagRecord(
                    source.category, source.count, set(source.aliases)
                )
        merged[canonical].aliases.add(alias)

    # Active alias antecedents must not remain as competing canonical rows.
    for alias, canonical in official_aliases.items():
        if alias in merged and alias != canonical:
            source = merged.pop(alias)
            merged[canonical].aliases.update(source.aliases)
            removed_alias_rows += 1

    # Resolve source-provided aliases through the official map, then make their
    # ownership deterministic. Official aliases always win; ambiguous informal
    # aliases go to the highest-count canonical and are counted in metadata.
    official_owner = dict(official_aliases)
    source_candidates: dict[str, list[str]] = {}
    for canonical, row in merged.items():
        normalised: set[str] = set()
        for alias in row.aliases:
            final = official_aliases.get(alias)
            if final is not None and final != canonical:
                merged.setdefault(final, TagRecord(0, 0, set())).aliases.add(alias)
                continue
            if alias and alias != canonical:
                normalised.add(alias)
                source_candidates.setdefault(alias, []).append(canonical)
        row.aliases = normalised
    ambiguous = 0
    for alias, owners in source_candidates.items():
        if alias in official_owner:
            winner = official_owner[alias]
        else:
            unique_owners = set(owners)
            if len(unique_owners) > 1:
                ambiguous += 1
            winner = min(unique_owners, key=lambda tag: (-merged[tag].count, tag))
        for owner in set(owners):
            if owner != winner:
                merged[owner].aliases.discard(alias)
        if winner in merged and winner != alias:
            merged[winner].aliases.add(alias)
    for canonical, row in merged.items():
        row.aliases.discard(canonical)
    return merged, {
        "pyu_tags": len(pyu),
        "daily_tags": len(daily),
        "daily_only_tags_added": daily_added,
        "official_aliases": len(official_aliases),
        "synthesised_canonicals": synthesised,
        "active_alias_rows_removed": removed_alias_rows,
        "ambiguous_source_aliases_resolved": ambiguous,
        "output_tags": len(merged),
    }


def _write_catalog_csv(path: Path, records: dict[str, TagRecord]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records.items(), key=lambda item: (-item[1].count, item[0]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        for tag, record in ordered:
            writer.writerow(
                [tag, record.category, record.count, ",".join(sorted(record.aliases))]
            )
        handle.flush()
        os.fsync(handle.fileno())
    return len(ordered)


def _write_relationship_parquet(
    path: Path,
    rows: Iterable[tuple[str, str]],
    *,
    columns: tuple[str, str],
    metadata: dict[str, str],
) -> int:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RefreshError("pyarrow is required: pip install pyarrow") from exc
    ordered = sorted(set(rows))
    schema = pa.schema(
        [pa.field(columns[0], pa.string()), pa.field(columns[1], pa.string())],
        metadata={key.encode("utf-8"): value.encode("utf-8") for key, value in metadata.items()},
    )
    table = pa.Table.from_arrays(
        [
            pa.array([row[0] for row in ordered], type=pa.string()),
            pa.array([row[1] for row in ordered], type=pa.string()),
        ],
        schema=schema,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=9,
        use_dictionary=True,
        write_statistics=True,
    )
    return len(ordered)


def _artifact(path: Path, relative: Path, *, rows: int, schema: list[str]) -> dict[str, Any]:
    return {
        "path": relative.as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "rows": rows,
        "schema": schema,
    }


def _validate_outputs(stage: Path, metadata: dict[str, Any]) -> None:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RefreshError("pyarrow is required: pip install pyarrow") from exc
    artifacts = metadata.get("artifacts", {})
    expected_names = {relative.as_posix() for relative in OUTPUT_RELATIVES[:-1]}
    if set(artifacts) != expected_names:
        raise RefreshError("metadata artifact set is incomplete")
    for relative_text, artifact in artifacts.items():
        relative = Path(*relative_text.split("/"))
        path = stage / relative
        if not path.is_file() or path.stat().st_size != artifact["size_bytes"]:
            raise RefreshError(f"missing/size-mismatched staged artifact: {relative_text}")
        if _sha256(path) != artifact["sha256"]:
            raise RefreshError(f"SHA mismatch for staged artifact: {relative_text}")
        if path.suffix == ".parquet":
            parquet = pq.ParquetFile(path)
            if parquet.metadata.num_rows != artifact["rows"]:
                raise RefreshError(f"row mismatch: {relative_text}")
            if parquet.schema_arrow.names != artifact["schema"]:
                raise RefreshError(f"schema mismatch: {relative_text}")
        else:
            seen_tags: set[str] = set()
            alias_owners: dict[str, str] = {}
            rows = 0
            with path.open("r", encoding="utf-8", newline="") as handle:
                for row_number, row in enumerate(csv.reader(handle), 1):
                    if len(row) != 4:
                        raise RefreshError(f"output CSV row {row_number} is malformed")
                    tag = row[0]
                    if tag in seen_tags:
                        raise RefreshError(f"duplicate output tag: {tag}")
                    seen_tags.add(tag)
                    for alias in _normalise_aliases(row[3]):
                        previous = alias_owners.setdefault(alias, tag)
                        if previous != tag:
                            raise RefreshError(
                                f"output alias {alias!r} belongs to multiple tags"
                            )
                    int(row[1])
                    int(row[2])
                    rows += 1
            if rows != artifact["rows"]:
                raise RefreshError("output CSV row mismatch")


def _atomic_publish(stage: Path, tags_db: Path) -> None:
    """Replace all data files with rollback copies; commit metadata last."""
    ordered = [*OUTPUT_RELATIVES[:-1], METADATA_RELATIVE]
    rollback = stage / ".rollback"
    backups: dict[Path, Path | None] = {}
    for relative in ordered:
        target = tags_db / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            backups[relative] = None
            continue
        backup = rollback / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(target, backup)
        except OSError:
            shutil.copy2(target, backup)
        backups[relative] = backup
    replaced: list[Path] = []
    try:
        for relative in ordered:
            staged = stage / relative
            if not staged.is_file():
                raise RefreshError(f"staged output missing: {staged}")
            os.replace(staged, tags_db / relative)
            replaced.append(relative)
    except Exception as exc:
        rollback_errors: list[str] = []
        for relative in reversed(replaced):
            target = tags_db / relative
            backup = backups[relative]
            try:
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    os.replace(backup, target)
            except OSError as rollback_exc:  # pragma: no cover - exceptional I/O
                rollback_errors.append(f"{relative}: {rollback_exc}")
        detail = f"; rollback errors={rollback_errors}" if rollback_errors else ""
        raise RefreshError(f"atomic publish failed: {exc}{detail}") from exc


def refresh(args: argparse.Namespace) -> dict[str, Any]:
    tags_db = Path(args.tags_db).expanduser().resolve(strict=False)
    tags_db.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=".danbooru-tags-stage-", dir=tags_db.parent)
    )
    session = _new_session()
    fetched_at = _utc_now()
    try:
        _log("Loading PYU and daily tag sources...")
        pyu_path, pyu_source = _materialise_source(
            args.pyu_csv, stage / ".sources/pyu.csv", session=session, args=args
        )
        daily_path, daily_source = _materialise_source(
            args.daily_counts,
            stage / ".sources/daily.csv",
            session=session,
            args=args,
        )
        meta_path, pyu_meta_source = _materialise_source(
            args.pyu_meta, stage / ".sources/pyu-meta.json", session=session, args=args
        )
        try:
            pyu_meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RefreshError(f"invalid PYU metadata JSON: {exc}") from exc
        pyu, pyu_raw_rows = _read_tag_csv(pyu_path, source_label="PYU CSV")
        daily, daily_raw_rows = _read_tag_csv(
            daily_path, source_label="daily count CSV"
        )
        pyu_source.update({"rows": pyu_raw_rows, "unique_tags": len(pyu)})
        daily_source.update({"rows": daily_raw_rows, "unique_tags": len(daily)})
        pyu_meta_source["document"] = pyu_meta

        _log("Fetching official active aliases...")
        aliases, aliases_source = _fetch_relationships(
            "tag_aliases", session=session, args=args
        )
        _log("Fetching official active implications...")
        implications, implications_source = _fetch_relationships(
            "tag_implications", session=session, args=args
        )
        alias_map = _resolved_alias_map(aliases)
        merged, merge_stats = _merge_tags(pyu, daily, alias_map)

        csv_rows = _write_catalog_csv(stage / CSV_RELATIVE, merged)
        common_parquet_meta = {
            "refresh_tool": f"refresh_danbooru_tag_assets.py/{TOOL_VERSION}",
            "api_base": args.api_base,
            "fetched_at": fetched_at,
        }
        alias_rows = _write_relationship_parquet(
            stage / ALIASES_RELATIVE,
            alias_map.items(),
            columns=("alias", "canonical"),
            metadata={**common_parquet_meta, "relationship_status": "active"},
        )
        implication_rows = _write_relationship_parquet(
            stage / IMPLICATIONS_RELATIVE,
            ((item.antecedent, item.consequent) for item in implications),
            columns=("antecedent", "consequent"),
            metadata={**common_parquet_meta, "relationship_status": "active"},
        )
        if alias_rows != len(alias_map):
            raise RefreshError("alias parquet lost rows during deduplication")
        if implication_rows != len(implications):
            raise RefreshError("implication parquet lost rows during deduplication")

        artifacts = {
            CSV_RELATIVE.as_posix(): _artifact(
                stage / CSV_RELATIVE,
                CSV_RELATIVE,
                rows=csv_rows,
                schema=["tag", "category", "count", "aliases"],
            ),
            ALIASES_RELATIVE.as_posix(): _artifact(
                stage / ALIASES_RELATIVE,
                ALIASES_RELATIVE,
                rows=alias_rows,
                schema=["alias", "canonical"],
            ),
            IMPLICATIONS_RELATIVE.as_posix(): _artifact(
                stage / IMPLICATIONS_RELATIVE,
                IMPLICATIONS_RELATIVE,
                rows=implication_rows,
                schema=["antecedent", "consequent"],
            ),
        }
        metadata = {
            "format_version": 1,
            "generated_by": f"tools/refresh_danbooru_tag_assets.py {TOOL_VERSION}",
            "fetched_at": fetched_at,
            "sources": {
                "pyu_csv": pyu_source,
                "pyu_meta": pyu_meta_source,
                "daily_counts": daily_source,
                "official_active_aliases": aliases_source,
                "official_active_implications": implications_source,
            },
            "merge": merge_stats,
            "artifacts": artifacts,
        }
        _write_bytes(stage / METADATA_RELATIVE, _json_bytes(metadata))
        _validate_outputs(stage, metadata)
        # The metadata file is also parsed before it becomes the commit marker.
        json.loads((stage / METADATA_RELATIVE).read_text(encoding="utf-8"))
        _log("Publishing validated tag assets atomically...")
        _atomic_publish(stage, tags_db)
        _log(f"Updated {csv_rows:,} tags, {alias_rows:,} aliases, "
             f"{implication_rows:,} implications")
        _log(f"Metadata: {tags_db / METADATA_RELATIVE}")
        return metadata
    finally:
        session.close()
        shutil.rmtree(stage, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Refresh PYU/HDiffusion/Danbooru tag assets with validation."
    )
    parser.add_argument("--pyu-csv", required=True, help="PYU 4-column CSV path or URL")
    parser.add_argument("--pyu-meta", required=True, help="PYU meta.json path or URL")
    parser.add_argument(
        "--daily-counts", required=True, help="HDiffusion daily 4-column CSV path or URL"
    )
    parser.add_argument(
        "--tags-db",
        default=str(project_root / "tags_db"),
        help="destination tags_db directory (default: project tags_db)",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--api-delay", type=float, default=0.2)
    parser.add_argument("--page-limit", type=int, default=1000)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--read-timeout", type=float, default=90.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--retry-backoff", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.page_limit <= 0 or args.page_limit > 1000:
        parser.error("--page-limit must be between 1 and 1000")
    if args.api_delay < 0:
        parser.error("--api-delay must be non-negative")
    if args.retries < 0:
        parser.error("--retries must be non-negative")
    try:
        refresh(args)
    except RefreshError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

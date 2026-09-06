"""Verified, single-owner model downloads shared by Settings and Creator.

Only packaged artifact IDs cross the UI interface. URLs and relative filenames
are trusted catalog data, never supplied by a browser. A job owns its cancel
event until its worker settles; an old callback cannot mutate a newer job.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence
from urllib.parse import urljoin, urlsplit

from core.storage_paths import StoragePaths, storage_paths
from utils.atomic_json import atomic_write_json, load_json_safe


@dataclass(frozen=True)
class ModelArtifact:
    id: str
    label: str
    category: str
    filename: str
    size: int
    sha256: str
    url: str
    source_url: str = ""

    def __post_init__(self):
        relative = PurePosixPath(self.filename.replace("\\", "/"))
        if (not self.id or not self.filename or relative.is_absolute()
                or ".." in relative.parts or ":" in self.filename
                or "\x00" in self.filename):
            raise ValueError("안전하지 않은 모델 파일 이름입니다")
        if self.size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("모델의 크기와 SHA-256이 필요합니다")
        if self.category not in {
            "checkpoints", "diffusion_models", "loras", "vae", "text_encoders",
            "upscale_models", "auxiliary",
        }:
            raise ValueError("지원하지 않는 모델 분류입니다")
        _checked_download_url(self.url)


@dataclass(frozen=True)
class ModelPack:
    id: str
    label: str
    description: str
    artifact_ids: tuple[str, ...]
    requirements: str = ""


class ModelDownloadError(RuntimeError):
    pass


class _Canceled(ModelDownloadError):
    pass


class _IntegrityError(ModelDownloadError):
    pass


def _checked_download_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    allowed = host in {
        "huggingface.co", "github.com", "raw.githubusercontent.com",
        "objects.githubusercontent.com", "release-assets.githubusercontent.com",
    } or host.endswith((".huggingface.co", ".hf.co"))
    if (parsed.scheme != "https" or not allowed or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise ValueError("검증된 HTTPS 모델 저장소 주소만 사용할 수 있습니다")
    return url


def _default_snapshot() -> dict:
    from core.backend_runtime import get_backend_runtime_manager
    return get_backend_runtime_manager().snapshot()


def _catalog() -> tuple[list[ModelArtifact], list[ModelPack]]:
    data = json.loads(Path(__file__).with_name("model_download_catalog.json").read_text(encoding="utf-8"))
    return (
        [ModelArtifact(**item) for item in data["artifacts"]],
        [ModelPack(**{**item, "artifact_ids": tuple(item["artifact_ids"])}) for item in data["packs"]],
    )


class ModelDownloadManager:
    """Nonblocking status/start/cancel/verify interface; one worker per manager.

    ``http`` accepts a requests.Session-compatible adapter for offline tests.
    ``wait``/``shutdown`` are lifecycle helpers, not UI-thread operations.
    Existing files are never overwritten, including during atomic publication.
    """

    def __init__(self, *, artifacts: Sequence[ModelArtifact] | None = None,
                 packs: Sequence[ModelPack] | None = None,
                 storage: StoragePaths = storage_paths, model_root: Path | None = None,
                 snapshot_provider: Callable[[], Mapping] = _default_snapshot,
                 http=None, on_event: Callable[[dict], None] | None = None,
                 disk_usage: Callable = shutil.disk_usage):
        if artifacts is None or packs is None:
            default_artifacts, default_packs = _catalog()
            artifacts = default_artifacts if artifacts is None else artifacts
            packs = default_packs if packs is None else packs
        self.artifacts = {item.id: item for item in artifacts}
        self.packs = {pack.id: pack for pack in packs}
        if len(self.artifacts) != len(artifacts) or len(self.packs) != len(packs):
            raise ValueError("중복된 다운로드 목록 ID입니다")
        for pack in self.packs.values():
            if not pack.artifact_ids or any(key not in self.artifacts for key in pack.artifact_ids):
                raise ValueError(f"잘못된 모델 묶음: {pack.id}")
        self.storage = storage
        self.model_root = Path(model_root or storage.project_root / "user_data" / "models").resolve()
        self.snapshot_provider = snapshot_provider
        self.http = http
        self.on_event = on_event
        self.disk_usage = disk_usage
        self._manifest_path = storage.config_file("model_downloads/manifest.json")
        self._prefs_path = storage.config_file("model_downloads/preferences.json")
        self._manifest = load_json_safe(str(self._manifest_path), {})
        self._prefs = load_json_safe(str(self._prefs_path), {})
        if not isinstance(self._manifest, dict):
            self._manifest = {}
        if not isinstance(self._prefs, dict):
            self._prefs = {}
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._closed = False
        self._files: list[dict] = []
        self._state = {"state": "idle", "busy": False, "jobId": "", "message": "확인할 모델 기능을 선택하세요", "error": "", "downloadedBytes": 0, "totalBytes": 0, "percent": 0, "fileId": "", "revision": 0}

    def _roots(self) -> dict[str, list[Path]]:
        from core.forge_modules import get_app_model_paths
        from core.model_inventory import ModelInventory
        fallback = get_app_model_paths(self.model_root)
        fallback.update({key: self.model_root / key for key in ("upscale_models", "auxiliary")})
        snapshot = self.snapshot_provider()
        inventory = ModelInventory(snapshot)
        order = list(inventory.engines)
        if inventory.primary_engine in order:
            order.remove(inventory.primary_engine)
            order.insert(0, inventory.primary_engine)
        roots = {key: [] for key in fallback}
        for engine in order:
            data = inventory.engines[engine]
            configured = data.get("modelPaths", {})
            if not isinstance(configured, Mapping):
                continue
            for category in roots:
                values = configured.get(category, [])
                if isinstance(values, (str, os.PathLike)):
                    values = [values]
                if not isinstance(values, (list, tuple)):
                    continue
                for value in values:
                    if str(value or "").strip():
                        roots[category].append(Path(value).expanduser().resolve())
            # Forge's Settings checkpoint folder also contains UNET-only files.
            if engine == "forge":
                roots["diffusion_models"].extend(roots["checkpoints"])
        for category, root in fallback.items():
            roots[category].append(root.resolve())
            roots[category] = list(dict.fromkeys(roots[category]))
        # Turbo reads this DATA file beside its node source, not from models/.
        # Never install a node or claim readiness using an unrelated aux folder.
        comfy = inventory.engines.get("comfyui", {})
        node_name = "ComfyUI-MiniMax-H3-Turbo"
        candidates = []
        for value in (comfy.get("extensionDir"), str(Path(comfy["sourceRoot"]) / "custom_nodes") if comfy.get("sourceRoot") else ""):
            if not value:
                continue
            base = Path(value).expanduser().resolve()
            candidate = base if base.name.casefold() == node_name.casefold() else base / node_name
            resolved = candidate.resolve()
            if resolved.is_relative_to(base) and resolved.is_dir():
                candidates.append(resolved)
        roots["_h3_grid"] = list(dict.fromkeys(candidates))
        roots["_index"] = {}
        return roots

    def _existing(self, item: ModelArtifact, roots: Mapping) -> Path | None:
        matches = []
        basename = PurePosixPath(item.filename.replace("\\", "/")).name.casefold()
        search_roots = roots.get("_h3_grid", []) if item.id == "h3-temb-grid" else roots[item.category]
        for root in search_roots:
            root = Path(root).resolve()
            direct = (root / item.filename.replace("\\", "/")).resolve()
            if direct.is_relative_to(root) and direct.is_file():
                matches.append(direct)
            if not root.is_dir():
                continue
            cache = roots["_index"]
            if root not in cache:
                wanted = {PurePosixPath(artifact.filename.replace("\\", "/")).name.casefold() for artifact in self.artifacts.values()}
                index = {}
                for directory, subdirs, filenames in os.walk(root, followlinks=False):
                    subdirs[:] = [name for name in subdirs if not (Path(directory) / name).is_symlink()]
                    for filename in filenames:
                        key = filename.casefold()
                        if key in wanted:
                            index.setdefault(key, []).append(Path(directory) / filename)
                cache[root] = index
            for path in cache[root].get(basename, []):
                candidate = path.resolve()
                if candidate.is_relative_to(root) and candidate.is_file() and candidate not in matches:
                    matches.append(candidate)
        return next((path for path in matches if path.stat().st_size == item.size), matches[0] if matches else None)

    def _destination(self, item: ModelArtifact, roots: Mapping) -> Path:
        existing = self._existing(item, roots)
        if existing is not None:
            return existing
        target_roots = roots.get("_h3_grid", []) if item.id == "h3-temb-grid" else roots[item.category]
        if not target_roots:
            raise ModelDownloadError("ComfyUI-MiniMax-H3-Turbo 노드를 먼저 설치하세요. 그리드는 설치된 노드 폴더에만 저장합니다")
        root = Path(target_roots[0]).resolve()
        target = (root / item.filename.replace("\\", "/")).resolve()
        if not target.is_relative_to(root):
            raise ModelDownloadError("모델 경로가 지정된 폴더 밖을 가리킵니다")
        return target

    @staticmethod
    def _signature(path: Path) -> dict:
        stat = path.stat()
        return {"size": stat.st_size, "mtimeNs": stat.st_mtime_ns, "ctimeNs": stat.st_ctime_ns}

    def _file_status(self, item: ModelArtifact, roots: Mapping) -> dict:
        target = self._destination(item, roots)
        state = "missing"
        if target.is_file():
            signature = self._signature(target)
            state = "present" if signature["size"] == item.size else "mismatch"
            receipt = self._manifest.get(item.id, {})
            if not isinstance(receipt, dict):
                receipt = {}
            if (state == "present" and receipt.get("path") == str(target)
                    and receipt.get("sha256") == item.sha256 and receipt.get("signature") == signature):
                state = "verified"
        return {"id": item.id, "label": item.label, "filename": item.filename,
                "category": item.category, "size": item.size, "path": str(target),
                "status": state, "sourceUrl": item.source_url or item.url}

    def _safe_file_status(self, item: ModelArtifact, roots: Mapping) -> dict:
        try:
            return self._file_status(item, roots)
        except (OSError, ValueError, ModelDownloadError) as exc:
            return {"id": item.id, "label": item.label, "filename": item.filename,
                    "category": item.category, "size": item.size, "path": "",
                    "status": "blocked" if item.id == "h3-temb-grid" else "inaccessible",
                    "blockedReason": str(exc), "sourceUrl": item.source_url or item.url}

    def status(self, *, refresh: bool = True) -> dict:
        with self._lock:
            if refresh and not self._state["busy"]:
                roots = self._roots()
                self._files = [self._safe_file_status(item, roots) for item in self.artifacts.values()]
            files = [dict(item) for item in self._files]
            by_id = {item["id"]: item for item in files}
            packs = []
            for pack in self.packs.values():
                required = [by_id[key] for key in pack.artifact_ids if key in by_id]
                present = [item for item in required if item["status"] in ("present", "verified")]
                blocked = [item for item in required if item["status"] in ("blocked", "inaccessible", "mismatch")]
                packs.append({"id": pack.id, "label": pack.label, "description": pack.description,
                              "requirements": pack.requirements, "fileIds": list(pack.artifact_ids),
                              "downloadable": not blocked,
                              "blockedReason": blocked[0].get("blockedReason", "크기가 다른 기존 파일을 확인하세요. 기존 파일은 자동으로 덮어쓰지 않습니다") if blocked else "",
                              "ready": len(required) == len(pack.artifact_ids) and len(present) == len(required),
                              "verified": bool(required) and all(item["status"] == "verified" for item in required),
                              "installedCount": len(present), "missingCount": len(pack.artifact_ids) - len(present),
                              "totalBytes": sum(self.artifacts[key].size for key in pack.artifact_ids),
                              "requiredBytes": sum(item["size"] for item in required if item not in present)})
            return {"available": True, **self._state, "files": files, "packs": packs,
                    "selectedPackIds": [key for key in self._prefs.get("selectedPackIds", []) if isinstance(key, str) and key in self.packs] if isinstance(self._prefs.get("selectedPackIds", []), list) else []}

    def _emit(self, **patch) -> None:
        with self._lock:
            if self._cancel.is_set() and self._state["busy"] and patch.get("busy") is not False:
                patch.update(state="canceling", message="취소 중 · 파일 작업이 끝날 때까지 기다려 주세요")
            self._state.update(patch)
            self._state["revision"] += 1
            event = self.status(refresh=False)
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass  # A disconnected renderer cannot fail an otherwise safe download.

    def start(self, pack_ids: Sequence[str]) -> dict:
        return self._start_job(pack_ids, verify_only=False)

    def verify(self, pack_ids: Sequence[str]) -> dict:
        """Hash selected existing files; never repairs or downloads implicitly."""
        return self._start_job(pack_ids, verify_only=True)

    def _start_job(self, pack_ids: Sequence[str], *, verify_only: bool) -> dict:
        with self._lock:
            if self._closed:
                raise ModelDownloadError("다운로드 관리자가 종료되었습니다")
            if self._thread and self._thread.is_alive():
                raise ModelDownloadError("이전 다운로드/취소 작업이 끝날 때까지 기다려 주세요")
            if not isinstance(pack_ids, (list, tuple)) or not pack_ids or any(not isinstance(key, str) or key not in self.packs for key in pack_ids):
                raise ModelDownloadError("다운로드 목록에서 유효한 기능을 선택하세요")
            selected = list(dict.fromkeys(pack_ids))
            keys = list(dict.fromkeys(key for pack_id in selected for key in self.packs[pack_id].artifact_ids))
            self.status()
            roots = self._roots()
            for key in keys:
                self._destination(self.artifacts[key], roots)  # All prerequisites before any download.
            self._prefs = {"selectedPackIds": selected}
            atomic_write_json(str(self._prefs_path), self._prefs)
            self._cancel = threading.Event()
            self._state.update(state="preparing", busy=True, jobId=uuid.uuid4().hex,
                               error="", message="모델 파일을 확인하는 중", downloadedBytes=0,
                               totalBytes=sum(self.artifacts[key].size for key in keys), percent=0,
                               revision=self._state["revision"] + 1)
            self._thread = threading.Thread(target=self._run, args=(keys, roots, verify_only), daemon=True, name="model-download")
            self._thread.start()
            return self.status(refresh=False)

    def _check_cancel(self):
        if self._cancel.is_set():
            raise _Canceled("취소되었습니다. 이어받기 파일은 보존했습니다")

    def _hash(self, path: Path, item: ModelArtifact) -> None:
        self._emit(state="verifying", fileId=item.id, message=f"{item.label} SHA-256 검증 중")
        before = self._signature(path)
        digest = hashlib.sha256()
        hashed, last_progress = 0, 0.0
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self._check_cancel()
                digest.update(chunk)
                hashed += len(chunk)
                if time.monotonic() - last_progress >= 0.25:
                    last_progress = time.monotonic()
                    self._emit(filePercent=min(100, hashed / item.size * 100))
        if before != self._signature(path) or before["size"] != item.size or digest.hexdigest() != item.sha256:
            raise _IntegrityError(f"{item.label}: 크기 또는 SHA-256이 일치하지 않습니다. 기존 파일은 보존했습니다")

    def _remember(self, item: ModelArtifact, target: Path):
        with self._lock:
            self._manifest[item.id] = {"path": str(target), "sha256": item.sha256, "signature": self._signature(target)}
            atomic_write_json(str(self._manifest_path), self._manifest)

    @staticmethod
    def _check_write_path(target: Path):
        if target.resolve() != target or target.is_symlink():
            raise ModelDownloadError("다운로드 도중 저장 경로가 다른 위치를 가리키게 되었습니다")

    def _verify_partial(self, partial: Path, item: ModelArtifact):
        try:
            self._hash(partial, item)
        except _IntegrityError:
            if partial.stat().st_size >= item.size:
                self._check_write_path(partial)
                os.rename(partial, partial.with_name(partial.name + ".invalid-" + uuid.uuid4().hex))
            raise

    def _download(self, item: ModelArtifact, target: Path, completed: int):
        self._check_write_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        if partial.is_symlink():
            raise ModelDownloadError("이어받기 파일이 심볼릭 링크입니다")
        received = partial.stat().st_size if partial.exists() else 0
        if received > item.size:
            os.rename(partial, partial.with_name(partial.name + ".invalid-" + uuid.uuid4().hex))
            raise ModelDownloadError(f"이어받기 파일이 예상 크기보다 큽니다: {partial}")
        if received == item.size:
            self._verify_partial(partial, item)
            self._publish(item, partial, target)
            return
        if self.http is None:
            import requests
            self.http = requests.Session()
        headers = {"Accept-Encoding": "identity"}
        if received:
            headers["Range"] = f"bytes={received}-"
        response = self._request(item.url, headers)
        try:
            response_headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            if response_headers.get("content-encoding", "identity").lower() not in ("", "identity"):
                raise ModelDownloadError("압축된 모델 응답은 안전하게 이어받을 수 없습니다")
            if response.status_code == 206:
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response_headers.get("content-range", ""))
                if not match or tuple(map(int, match.groups())) != (received, item.size - 1, item.size):
                    raise ModelDownloadError("서버의 Content-Range가 요청한 이어받기 범위와 다릅니다")
            elif response.status_code == 200:
                # Server ignored Range: discard only this app's temporary data,
                # and accept a complete, separately verified response instead.
                received = 0
            else:
                raise ModelDownloadError(f"모델 서버 오류: HTTP {response.status_code}")
            declared = response_headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) != item.size - received):
                raise ModelDownloadError("서버의 Content-Length가 예상 모델 크기와 다릅니다")
            self._emit(state="downloading", fileId=item.id, message=f"{item.label} 다운로드 중")
            last_progress = 0.0
            self._check_write_path(partial)
            with partial.open("ab" if received else "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    self._check_cancel()
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > item.size:
                        raise ModelDownloadError("서버가 예상 크기보다 큰 모델을 반환했습니다")
                    handle.write(chunk)
                    if time.monotonic() - last_progress >= 0.25:
                        last_progress = time.monotonic()
                        self._emit(downloadedBytes=completed + received,
                                   percent=min(100, (completed + received) / self._state["totalBytes"] * 100),
                                   filePercent=received / item.size * 100)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            response.close()
        self._verify_partial(partial, item)
        self._publish(item, partial, target)

    def _request(self, url: str, headers: dict):
        for _ in range(6):
            self._check_cancel()
            response = self.http.get(_checked_download_url(url), stream=True, timeout=(10, 10),
                                     allow_redirects=False, headers=headers)
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = next((value for key, value in response.headers.items() if key.lower() == "location"), "")
            response.close()
            if not location:
                raise ModelDownloadError("모델 리디렉션 주소가 없습니다")
            url = _checked_download_url(urljoin(url, location))
        raise ModelDownloadError("모델 리디렉션 횟수를 초과했습니다")

    def _publish(self, item: ModelArtifact, partial: Path, target: Path):
        self._check_cancel()
        self._check_write_path(target)
        self._check_write_path(partial)
        # Windows rename and POSIX link publish atomically without replacing a
        # file another program created while this download was in flight.
        if os.name == "nt":
            os.rename(partial, target)
        else:
            os.link(partial, target)
            partial.unlink()
        self._remember(item, target)

    def _run(self, keys: list[str], roots: dict, verify_only: bool):
        state, message, error = "complete", "선택한 모델 준비가 완료되었습니다", ""
        completed = 0
        try:
            destinations = {key: self._destination(self.artifacts[key], roots) for key in keys}
            if not verify_only:
                self._check_disk_space(keys, destinations)
            for key in keys:
                self._check_cancel()
                item = self.artifacts[key]
                target = destinations[key]
                if target.is_file():
                    self._hash(target, item)
                    self._remember(item, target)
                else:
                    if verify_only:
                        raise ModelDownloadError(f"{item.label}: 검증할 파일이 없습니다")
                    self._download(item, target, completed)
                completed += item.size
                self._emit(downloadedBytes=completed, percent=completed / self._state["totalBytes"] * 100)
        except _Canceled as exc:
            state, message = "canceled", str(exc)
        except Exception as exc:
            if self._cancel.is_set():
                state, message = "canceled", "취소되었습니다. 이어받기 파일은 보존했습니다"
            else:
                state, message, error = "error", str(exc), str(exc)
        finally:
            with self._lock:
                roots["_index"] = {}
                self._files = [self._safe_file_status(item, roots) for item in self.artifacts.values()]
            self._emit(state=state, busy=False, message=message, error=error, fileId="")

    def _check_disk_space(self, keys: list[str], destinations: Mapping):
        required = {}
        for key in keys:
            target = destinations[key]
            if target.is_file():
                continue
            ancestor = target.parent
            while not ancestor.exists():
                ancestor = ancestor.parent
            partial = target.with_name(target.name + ".part")
            partial_size = partial.stat().st_size if partial.is_file() and not partial.is_symlink() else 0
            remaining = max(0, self.artifacts[key].size - partial_size)
            device = ancestor.stat().st_dev
            record = required.setdefault(device, {"path": ancestor, "bytes": 0})
            record["bytes"] += remaining
        for record in required.values():
            reserve = 64 * 1024 * 1024
            if self.disk_usage(record["path"]).free < record["bytes"] + reserve:
                raise ModelDownloadError(f"저장 공간이 부족합니다: {record['path']} · 필요한 여유 공간 {record['bytes'] + reserve:,}바이트")

    def cancel(self, job_id: str = "") -> dict:
        with self._lock:
            if job_id and job_id != self._state["jobId"]:
                raise ModelDownloadError("이미 지난 다운로드 요청입니다")
            if self._state["busy"]:
                self._cancel.set()
                self._emit(state="canceling", message="취소 중 · 파일 작업이 끝날 때까지 기다려 주세요")
            return self.status(refresh=False)

    def wait(self, timeout: float | None = None) -> dict:
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
        # Shutdown can be called on the Qt thread. Never rescan a large local
        # or network model library after the manager has been closed.
        return self.status(refresh=not self._closed)

    def shutdown(self, timeout: float = 12) -> dict:
        with self._lock:
            self._closed = True
        self.cancel()
        return self.wait(timeout)

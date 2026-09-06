"""Owned, bounded H3 conditioning cache. Torch/Comfy are imported only at use.

This is an independent implementation, not a copy of GemmaStudio's nodes.
Only CPU tensors and plain containers are serialized; neither model objects nor
Comfy's NestedTensor instances are accepted by the weights-only cache format.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
from pathlib import Path
import re
import threading
import sys
import uuid


CACHE_SCHEMA = 1
_KEY = re.compile(r"[0-9a-f]{64}")
_LOCK = threading.RLock()
_FINGERPRINTS = {}
_MODEL_IDENTITIES = {}


class ConditioningCacheCancelled(RuntimeError):
    pass


def _digest_file(path, cancelled=lambda: False):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            if cancelled():
                raise ConditioningCacheCancelled("H3 캐시 작업이 취소되었습니다")
            digest.update(chunk)
    return digest.hexdigest()


def _cpu_value(value):
    import torch
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().contiguous()
    if isinstance(value, dict) and all(isinstance(k, (str, int)) for k in value):
        return {key: _cpu_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_cpu_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ValueError(f"H3 cache does not support {type(value).__name__}")


def _conditioning(value):
    import torch
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("H3 cache must contain non-empty CONDITIONING")
    for pair in value:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not isinstance(pair[0], torch.Tensor) or not isinstance(pair[1], dict)):
            raise ValueError("H3 cache CONDITIONING schema is invalid")
    return _cpu_value(value)


class ConditioningCache:
    """CPU disk store with SHA integrity, count/byte limits and exact-scope clear."""

    def __init__(self, root, *, max_bytes=8 * 1024 ** 3, max_entries=32):
        self.root = Path(root).resolve()
        self.max_bytes, self.max_entries = int(max_bytes), int(max_entries)
        if not 1024 ** 2 <= self.max_bytes <= 128 * 1024 ** 3 or not 1 <= self.max_entries <= 1024:
            raise ValueError("Invalid H3 conditioning cache limits")
        if self.root == Path(self.root.anchor):
            raise ValueError("A filesystem root cannot be a conditioning cache")

    def _path(self, key, suffix=".pt"):
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ValueError("Invalid H3 cache key")
        path = self.root / (key + suffix)
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError("H3 cache path is outside its owned directory")
        return path

    def _files(self):
        if not self.root.is_dir():
            return []
        return [p for p in self.root.iterdir() if p.is_file() and not p.is_symlink()
                and p.suffix == ".pt" and _KEY.fullmatch(p.stem)]

    def _remove(self, key):
        for suffix in (".pt", ".json"):
            self._path(key, suffix).unlink(missing_ok=True)

    def _prune(self, keep):
        files = self._files()
        total, count = sum(p.stat().st_size for p in files), len(files)
        for stale in sorted((p for p in files if p.stem != keep), key=lambda p: p.stat().st_mtime_ns):
            if total <= self.max_bytes and count <= self.max_entries:
                break
            total -= stale.stat().st_size
            count -= 1
            self._remove(stale.stem)

    def stats(self):
        with _LOCK:
            files = self._files()
            return {"entries": len(files), "bytes": sum(p.stat().st_size for p in files),
                    "maxBytes": self.max_bytes, "maxEntries": self.max_entries,
                    "scope": "comfy_server"}

    def clear(self):
        with _LOCK:
            before = self.stats()
            for path in self._files():
                self._remove(path.stem)
            return {**self.stats(), "removedEntries": before["entries"], "removedBytes": before["bytes"]}

    def get(self, key, *, cancelled=lambda: False):
        import torch
        with _LOCK:
            path, manifest = self._path(key), self._path(key, ".json")
            if not path.is_file() or not manifest.is_file():
                return None
            try:
                info = json.loads(manifest.read_text(encoding="utf-8"))
                if (info.get("schema") != CACHE_SCHEMA or info.get("key") != key
                        or info.get("bytes") != path.stat().st_size
                        or path.stat().st_size > self.max_bytes
                        or info.get("sha256") != _digest_file(path, cancelled)):
                    raise ValueError("H3 cache integrity mismatch")
                envelope = torch.load(path, map_location="cpu", weights_only=True)
                if envelope.get("schema") != CACHE_SCHEMA or envelope.get("key") != key:
                    raise ValueError("H3 cache identity mismatch")
                value = _conditioning(envelope["conditioning"])
                if cancelled():
                    raise ConditioningCacheCancelled("H3 캐시 작업이 취소되었습니다")
                os.utime(path, None)
                self._prune(key)
                return value
            except ConditioningCacheCancelled:
                raise
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, EOFError,
                    AttributeError, pickle.UnpicklingError):
                self._remove(key)
                return None

    def put(self, key, conditioning, *, cancelled=lambda: False):
        import torch
        with _LOCK:
            destination = self._path(key)
            value = _conditioning(conditioning)
            if cancelled():
                raise ConditioningCacheCancelled("H3 캐시 작업이 취소되었습니다")
            self.root.mkdir(parents=True, exist_ok=True)
            nonce = uuid.uuid4().hex
            temporary = self.root / f"{key}.{nonce}.tmp"
            temporary_manifest = self.root / f"{key}.{nonce}.json.tmp"
            try:
                torch.save({"schema": CACHE_SCHEMA, "key": key, "conditioning": value}, temporary)
                size = temporary.stat().st_size
                if size > self.max_bytes:
                    raise ValueError("H3 conditioning이 캐시 용량 한도를 초과했습니다. 한도를 늘리거나 캐시를 끄세요")
                digest = _digest_file(temporary, cancelled)
                temporary_manifest.write_text(json.dumps({"schema": CACHE_SCHEMA, "key": key,
                    "sha256": digest, "bytes": size}), encoding="utf-8")
                if cancelled():
                    raise ConditioningCacheCancelled("H3 캐시 작업이 취소되었습니다")
                others = sorted((p for p in self._files() if p.stem != key), key=lambda p: p.stat().st_mtime_ns)
                total = sum(p.stat().st_size for p in others) + size
                while others and (len(others) + 1 > self.max_entries or total > self.max_bytes):
                    stale = others.pop(0)
                    total -= stale.stat().st_size
                    self._remove(stale.stem)
                os.replace(temporary, destination)
                os.replace(temporary_manifest, self._path(key, ".json"))
                return {"key": key, "bytes": size, "ready": True, "hit": False}
            finally:
                temporary.unlink(missing_ok=True)
                temporary_manifest.unlink(missing_ok=True)


def content_identity(path, *, memoize=False, cancelled=lambda: False):
    """Hash actual server-side bytes, rejecting files modified during hashing.

    Large model digests are reused only while path/size/mtime/ctime/inode match.
    Media are always hashed; upload filenames are not their content identity.
    """
    path = Path(path).resolve()
    stat = path.stat()
    stamp = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    memo_key = (str(path), stamp)
    if cancelled():
        raise ConditioningCacheCancelled("H3 캐시 작업이 취소되었습니다")
    if memoize and memo_key in _FINGERPRINTS:
        digest = _FINGERPRINTS[memo_key]
    else:
        digest = _digest_file(path, cancelled)
        after = path.stat()
        if stamp != (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino):
            raise RuntimeError("H3 입력/모델 파일이 변경되었습니다. 변경이 끝난 뒤 다시 생성하세요")
        if memoize:
            if len(_FINGERPRINTS) >= 256:
                _FINGERPRINTS.clear()
            _FINGERPRINTS[memo_key] = digest
    return {"sha256": digest, "bytes": stat.st_size}


def conditioning_identity(descriptor, resolve_model, resolve_input, *, engine_files=(),
                          cancelled=lambda: False):
    """Resolve graph filenames at the Comfy host, including remote installations."""
    if not isinstance(descriptor, str) or len(descriptor) > 1024 * 1024:
        raise ValueError("Invalid H3 cache descriptor")
    value = json.loads(descriptor)
    if value.get("schema") != CACHE_SCHEMA or not isinstance(value.get("conditioning"), dict):
        raise ValueError("Unsupported H3 cache descriptor schema")
    models = {"UNETLoader": ("diffusion_models", "unet_name"),
              "CLIPLoader": ("text_encoders", "clip_name"), "VAELoader": ("vae", "vae_name")}
    for node in [*value["conditioning"].values(), *value.get("models", [])]:
        kind, inputs = node["class_type"], node["inputs"]
        if kind in models:
            category, field = models[kind]
            inputs[field] = content_identity(resolve_model(category, inputs[field]),
                                              memoize=True, cancelled=cancelled)
        elif kind in {"LoadImage", "GemmaVideoReferencePreprocessor"}:
            field = "image" if kind == "LoadImage" else "file"
            inputs[field] = content_identity(resolve_input(inputs[field]), cancelled=cancelled)
    value["implementation"] = [content_identity(path, memoize=True, cancelled=cancelled)
                                for path in engine_files]
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _cancelled():
    manager = sys.modules.get("comfy.model_management")
    return bool(manager and manager.processing_interrupted())


def _unload_encoder_models():
    """Synchronous execution-worker barrier, not the asynchronous /free flag."""
    manager = sys.modules.get("comfy.model_management")
    if manager is None:
        raise RuntimeError("ComfyUI model management is unavailable for H3 cache unloading")
    if _cancelled():
        raise ConditioningCacheCancelled("H3 캐시 작업이 취소되었습니다")
    manager.unload_all_models()
    manager.soft_empty_cache()
    if _cancelled():
        raise ConditioningCacheCancelled("H3 캐시 작업이 취소되었습니다")


def _runtime(descriptor, max_bytes, max_entries):
    import folder_paths

    def relative(name):
        name = str(name).replace("\\", "/")
        if not name or name.startswith("/") or ":" in name or ".." in name.split("/"):
            raise ValueError("H3 cache dependency must be a safe relative filename")
        return name

    def model(category, name):
        path = folder_paths.get_full_path(category, relative(name))
        if not path:
            raise FileNotFoundError(f"H3 cache model identity is unavailable: {category}/{name}")
        # Native Comfy loaders cache model objects by filename, independently
        # of this disk cache. Never pair a new on-disk identity with an already
        # loaded, old model after an in-place replacement in this process.
        identity = content_identity(path, memoize=True, cancelled=_cancelled)
        resolved = str(Path(path).resolve())
        with _LOCK:
            previous = _MODEL_IDENTITIES.get(resolved)
            if previous is not None and previous != identity:
                raise RuntimeError("H3 모델 파일이 실행 중 변경되었습니다. ComfyUI 서버를 재시작한 뒤 다시 생성하세요")
            if previous is None and len(_MODEL_IDENTITIES) >= 256:
                raise RuntimeError("H3 모델 확인 기록 한도에 도달했습니다. ComfyUI 서버를 재시작하세요")
            _MODEL_IDENTITIES[resolved] = identity
        return path

    def media(name):
        root = Path(folder_paths.get_input_directory()).resolve()
        path = (root / relative(name)).resolve()
        if not path.is_relative_to(root):
            raise ValueError("H3 cache input is outside the Comfy input directory")
        return path

    root = Path(folder_paths.get_output_directory()) / "aistudio_cache" / "h3_conditioning"
    base = Path(getattr(folder_paths, "base_path", ""))
    engine_files = [Path(__file__)]
    for name in ("comfyui_version.py", "comfy_extras/nodes_minimax_h3.py",
                 "comfy/text_encoders/minimax.py", "comfy/ldm/minimax/model.py"):
        candidate = base / name
        if candidate.is_file():
            engine_files.append(candidate)
    nodes = sys.modules.get("nodes")
    for node_type in sorted({node["class_type"] for node in json.loads(descriptor)["conditioning"].values()}):
        cls = getattr(nodes, "NODE_CLASS_MAPPINGS", {}).get(node_type)
        module = sys.modules.get(getattr(cls, "__module__", ""))
        source = getattr(module, "__file__", "")
        if source and Path(source).is_file() and Path(source) not in engine_files:
            engine_files.append(Path(source))
    key = conditioning_identity(descriptor, model, media, engine_files=engine_files, cancelled=_cancelled)
    return ConditioningCache(root, max_bytes=max_bytes, max_entries=max_entries), key


class ForgeNeoH3ConditioningCachePrepare:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"descriptor": ("STRING", {"default": ""}),
            "max_bytes": ("INT", {"default": 8 * 1024 ** 3, "min": 1024 ** 2, "max": 128 * 1024 ** 3}),
            "max_entries": ("INT", {"default": 32, "min": 1, "max": 1024}),
            "conditioning": ("CONDITIONING", {"lazy": True})}}

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "prepare"
    CATEGORY = "AI Studio/Creator"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")  # Validate disk integrity/model identity on every request.

    def check_lazy_status(self, descriptor, max_bytes=8 * 1024 ** 3, max_entries=32, conditioning=None):
        store, key = _runtime(descriptor, max_bytes, max_entries)
        pending = getattr(self, "_pending_identity", None)
        if pending is not None and pending != key:
            self._pending_identity = None
            self._cached = None
            raise RuntimeError("H3 모델/입력이 인코딩 중 변경되었습니다. 다시 생성하세요")
        self._identity = key
        self._cached = store.get(key, cancelled=_cancelled)
        if self._cached is None and conditioning is None:
            self._pending_identity = key
            return ["conditioning"]
        return []

    def prepare(self, descriptor, max_bytes=8 * 1024 ** 3, max_entries=32, conditioning=None):
        store, key = _runtime(descriptor, max_bytes, max_entries)
        expected = getattr(self, "_identity", None) or key
        self._pending_identity = None
        self._identity = None
        if expected != key:
            self._cached = None
            raise RuntimeError("H3 모델/입력이 인코딩 중 변경되었습니다. 다시 생성하세요")
        cached = getattr(self, "_cached", None)
        self._cached = None
        if cached is None:
            cached = store.get(key, cancelled=_cancelled)
        if cached is not None:
            receipt = {"ready": True, "hit": True, "key": key}
        elif conditioning is not None:
            receipt = store.put(key, conditioning, cancelled=_cancelled)
        else:
            raise RuntimeError("H3 conditioning cache miss: encoder input is required")
        _unload_encoder_models()
        receipt["models_unloaded"] = True
        return {"ui": {"h3_conditioning_cache": [{**receipt, **store.stats()}]}, "result": ()}


class ForgeNeoH3ConditioningCacheLoad:
    @classmethod
    def INPUT_TYPES(cls):
        inputs = dict(ForgeNeoH3ConditioningCachePrepare.INPUT_TYPES()["required"])
        inputs.pop("conditioning")
        return {"required": inputs, "optional": {"expected_key": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "load"
    CATEGORY = "AI Studio/Creator"
    IS_CHANGED = ForgeNeoH3ConditioningCachePrepare.IS_CHANGED

    def load(self, descriptor, max_bytes=8 * 1024 ** 3, max_entries=32, expected_key=""):
        store, key = _runtime(descriptor, max_bytes, max_entries)
        if expected_key and key != expected_key:
            raise RuntimeError("H3 모델/입력이 캐시 준비 이후 변경되었습니다. 다시 생성하세요")
        value = store.get(key, cancelled=_cancelled)
        if value is None:
            raise RuntimeError("H3 conditioning cache is missing or corrupt. Run the encoding stage again.")
        return (value,)


NODE_CLASS_MAPPINGS = {cls.__name__: cls for cls in (
    ForgeNeoH3ConditioningCachePrepare, ForgeNeoH3ConditioningCacheLoad)}


def _register_routes():
    # Importing this file in the desktop app must not import a Comfy host.
    server = sys.modules.get("server")
    instance = getattr(getattr(server, "PromptServer", None), "instance", None)
    if instance is None or getattr(instance, "_aistudio_h3_cache_routes", False):
        return
    from aiohttp import web
    import folder_paths

    def store():
        return ConditioningCache(Path(folder_paths.get_output_directory()) / "aistudio_cache" / "h3_conditioning")

    @instance.routes.get("/aistudio/h3-cache/status")
    async def status(_request):
        return web.json_response(store().stats())

    @instance.routes.post("/aistudio/h3-cache/clear")
    async def clear(_request):
        # Queue can change after this check; the disk lock still prevents a
        # partial write/delete overlap, and sample loads fail closed if evicted.
        with _LOCK:
            current, pending = instance.prompt_queue.get_current_queue()
            if current or pending:
                return web.json_response({"error": "ComfyUI is busy"}, status=409)
            return web.json_response(store().clear())

    instance._aistudio_h3_cache_routes = True


_register_routes()

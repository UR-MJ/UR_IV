"""Creator Studio action module.

This mixin is the single seam between Vue actions and the Creator domain
modules.  Heavy work runs off the Qt thread; Vue receives transport-neutral
JSON events through :class:`ui.vue_bridge.VueBridge`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import base64
import copy
import json
import mimetypes
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager


_CREATOR_ACTIONS = {
    "creator_get_state",
    "creator_select_media",
    "creator_generate",
    "creator_cancel",
    "creator_h3_cache_status",
    "creator_h3_cache_clear",
    "comic_plan",
    "comic_save",
    "comic_generate_all",
    "comic_animate_all",
    "comic_export_page",
    "comic_export_living",
}


class CreatorActionsMixin:
    """Handle all Creator actions behind one small action-dispatch interface."""

    def _handle_creator_action(self, action: str, payload: dict) -> bool:
        # Literal tuple is intentional: tests/test_bridge_contract.py extracts
        # action names statically from ``action in (...)`` expressions.
        if action in (
            "creator_get_state", "creator_select_media", "creator_generate",
            "creator_cancel", "comic_plan", "comic_save",
            "comic_generate_all", "comic_animate_all", "comic_export_page",
            "comic_export_living",
            "creator_h3_cache_status", "creator_h3_cache_clear",
        ):
            pass
        else:
            return False
        self._ensure_creator_runtime()
        handlers = {
            "creator_get_state": self._creator_request_state,
            "creator_select_media": self._creator_select_media,
            "creator_generate": self._creator_start_generation,
            "creator_cancel": self._creator_cancel,
            "creator_h3_cache_status": lambda data: self._creator_cache_request("status", data),
            "creator_h3_cache_clear": lambda data: self._creator_cache_request("clear", data),
            "comic_plan": self._comic_start_plan,
            "comic_save": self._comic_save,
            "comic_generate_all": self._comic_start_generate_all,
            "comic_animate_all": self._comic_start_animate_all,
            "comic_export_page": self._comic_export_page,
            "comic_export_living": self._comic_start_export_living,
        }
        handlers[action](payload or {})
        return True

    def _ensure_creator_runtime(self) -> None:
        if hasattr(self, "_creator_coordinator"):
            return
        from core.resource_coordinator import get_generation_coordinator

        self._creator_cancel_event = threading.Event()
        self._creator_state_lock = threading.RLock()
        self._creator_running = False
        self._creator_mode = ""
        self._creator_active_job = None
        self._creator_job_local = threading.local()
        self._creator_coordinator = get_generation_coordinator(
            unload_llm=self._creator_unload_ollama,
            on_state=lambda state: self._creator_emit(
                "creatorStateChanged",
                {
                    "resourcePhase": state.phase,
                    "resourceOwner": state.owner,
                    "llmUnloaded": state.llm_unloaded,
                    "running": self._creator_running,
                    "busy": state.phase != "idle" or self._creator_running,
                    "ready": state.phase == "idle" and not self._creator_running,
                    "status": "running" if state.phase != "idle" or self._creator_running else "ready",
                    "mode": self._creator_mode,
                },
            ),
        )

    def _creator_emit(self, signal_name: str, payload: Dict[str, Any]) -> None:
        payload = dict(payload)
        if signal_name in {"creatorProgress", "creatorResult"}:
            local = getattr(self, "_creator_job_local", None)
            job = getattr(local, "job", None) or getattr(self, "_creator_active_job", None)
            payload.setdefault("requestId", job["requestId"] if job else "")
            if (job and payload["requestId"] == job["requestId"]
                    and job["cancel"].is_set() and signal_name == "creatorResult"
                    and payload.get("ok")):
                payload = {"ok": False, "canceled": True, "mode": payload.get("mode", ""),
                           "requestId": job["requestId"], "error": "생성이 취소되었습니다"}
        bridge = getattr(self, "vue_bridge", None)
        signal = getattr(bridge, signal_name, None)
        if signal is not None:
            signal.emit(json.dumps(payload, ensure_ascii=False))

    def _creator_set_running(self, running: bool, mode: str = "") -> None:
        with self._creator_state_lock:
            self._creator_running = bool(running)
            self._creator_mode = str(mode if running else "")
        self._creator_emit(
            "creatorStateChanged",
            {
                "running": self._creator_running,
                "busy": self._creator_running,
                "status": "running" if self._creator_running else "ready",
                "mode": self._creator_mode,
            },
        )

    def _creator_run_thread(self, mode: str, target, payload: dict) -> None:
        payload = dict(payload)
        request_id = str(payload.get("requestId") or secrets.token_hex(16))[:100]
        payload["requestId"] = request_id
        with self._creator_state_lock:
            if self._creator_running:
                if self._creator_active_job and self._creator_active_job["requestId"] == request_id:
                    # Retried transport delivery is not a terminal failure of
                    # the already accepted job with this identity.
                    return
                self._creator_emit(
                    "creatorResult",
                    {"ok": False, "mode": mode, "requestId": request_id,
                     "error": "다른 Creator 작업이 실행 중입니다"},
                )
                return
            job = {"requestId": request_id, "cancel": threading.Event(), "backend": None,
                   "backend_lock": threading.RLock()}
            self._creator_active_job = job
            self._creator_cancel_event = job["cancel"]
            self._creator_set_running(True, mode)

        def _work():
            self._creator_job_local.job = job
            try:
                target(payload)
            except Exception as exc:
                self._creator_emit(
                    "creatorResult",
                    {"ok": False, "mode": mode, "requestId": request_id,
                     "canceled": job["cancel"].is_set(), "error": str(exc)[:2000]},
                )
            finally:
                with self._creator_state_lock:
                    if self._creator_active_job is job:
                        self._creator_active_job = None
                        self._creator_set_running(False)
                self._creator_job_local.job = None

        threading.Thread(
            target=_work,
            daemon=True,
            name=f"creator-{re.sub(r'[^a-z0-9_-]', '-', mode.lower())}",
        ).start()

    # ── Creator state and generic generation ──────────────────────────────

    def _creator_request_state(self, payload: dict) -> None:
        def _work():
            state = {
                "running": self._creator_running,
                "busy": self._creator_running,
                "mode": self._creator_mode,
                "backend": "",
                "connected": False,
                "ready": False,
                "status": "checking",
                "nodeTypes": [],
            }
            try:
                from backends import get_backend, get_backend_type

                backend = get_backend()
                state["backend"] = get_backend_type().value
                state["connected"] = bool(backend.test_connection())
                state["ready"] = state["connected"]
                state["status"] = "ready" if state["connected"] else "offline"
                if state["backend"] == "comfyui" and state["connected"]:
                    state["nodeTypes"] = sorted(self._creator_object_info(backend).keys())
            except Exception as exc:
                state["error"] = str(exc)
                state["status"] = "error"
            self._creator_emit("creatorStateChanged", state)

            comic = self._comic_studio()
            try:
                reconciled = comic.reconcile(payload.get("comicRecovery"))
                persistence = {"status": reconciled.status, "source": "backend"}
                if reconciled.conflict_path:
                    persistence["conflictPath"] = reconciled.conflict_path
                self._comic_emit_document(reconciled.document, **persistence)
            except Exception as exc:
                self._comic_emit_document(None, status="error", error=str(exc))

        threading.Thread(target=_work, daemon=True, name="creator-state").start()

    def _creator_select_media(self, payload: dict) -> None:
        from PyQt6.QtWidgets import QFileDialog

        slot = str(payload.get("slot", "source"))[:50]
        file_filter = (
            "Creator Media (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff "
            "*.mp4 *.webm *.mov *.mkv *.avi *.m4v);;All Files (*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Creator 입력 파일 선택", "", file_filter)
        if path:
            self._creator_emit(
                "creatorMediaSelected",
                {"slot": slot, "path": path.replace("\\", "/")},
            )

    def _creator_start_generation(self, payload: dict) -> None:
        mode = str(payload.get("mode", "")).strip()
        target = self._comic_generate_panel if mode == "comic_panel" else self._creator_generate
        self._creator_run_thread(mode or "creator", target, payload)

    def _creator_generate(self, payload: dict) -> None:
        from backends import BackendType, get_backend, get_backend_type
        from core.creator_workflows import build

        if get_backend_type() is not BackendType.COMFYUI:
            raise RuntimeError("Creator 영상/Krea2 생성은 ComfyUI 백엔드가 필요합니다")
        backend = get_backend()
        if not hasattr(backend, "run_workflow"):
            raise RuntimeError("현재 ComfyUI adapter가 Creator 워크플로 실행을 지원하지 않습니다")

        requested_mode = str(payload.get("mode", ""))
        params = self._creator_prepare_params(backend, dict(payload))
        canonical_mode = "krea2_edit" if requested_mode in {"krea2", "krea_edit"} else requested_mode
        object_info = self._creator_object_info(backend)
        available = set(object_info.keys())
        self._creator_configure_h3_cache(canonical_mode, params, available)
        if (
            canonical_mode in {"h3_t2v", "h3_i2v"}
            and str(params.get("quality", "turbo")).strip().lower() == "turbo"
            and "block_cache" not in params
            and "blockCache" not in params
        ):
            params["block_cache"] = "MiniMaxH3BlockCacheT8" in available
        built = build(canonical_mode, params)
        self._creator_check_nodes(built, available)
        self._creator_resolve_comfy_choices(built, object_info)

        unload = self._creator_should_unload_ollama()
        all_artifacts = []
        info: Dict[str, Any] = {"passes": []}
        with self._creator_reserve(backend, requested_mode or "creator", unload):
            result = self._creator_run_workflow(backend, built, self._creator_progress_callback)
            if not result.success:
                raise RuntimeError(result.error or "Creator 생성에 실패했습니다")
            all_artifacts.extend(result.artifacts)
            info["passes"].append({"mode": canonical_mode, **(result.info or {})})

            if canonical_mode == "krea2_edit" and bool(params.get("hires")):
                primary = next(
                    (artifact for artifact in result.artifacts if artifact.kind in {"image", "animated"} and artifact.data),
                    None,
                )
                if primary is None:
                    raise RuntimeError("Krea2 hires 입력으로 사용할 이미지 결과가 없습니다")
                hires_name = backend.upload_media(
                    primary.data,
                    primary.filename or "krea2_edit.png",
                    primary.mime or "image/png",
                )
                hires_params = {
                    "input_image": hires_name,
                    "source_size": self._creator_image_size(primary.data),
                    "prompt": params.get("prompt", ""),
                    "seed": params["seed"],
                    "scale": params.get("hiresScale", params.get("hires_scale", 2)),
                    "denoise": params.get("hiresDenoise", params.get("hires_denoise", 0.45)),
                }
                hires_built = build("krea2_hires", hires_params)
                self._creator_check_nodes(hires_built, available)
                self._creator_resolve_comfy_choices(hires_built, object_info)
                self._creator_check_cancelled()
                result = self._creator_run_workflow(backend, hires_built, self._creator_progress_callback)
                if not result.success:
                    raise RuntimeError(result.error or "Krea2 hires 생성에 실패했습니다")
                all_artifacts.extend(result.artifacts)
                info["passes"].append({"mode": "krea2_hires", **(result.info or {})})
        if self._creator_cancel_event.is_set():
            raise RuntimeError("생성이 취소되었습니다")
        artifacts = self._creator_save_artifacts(all_artifacts, requested_mode or "creator")
        primary = artifacts[-1] if artifacts else {}
        self._creator_emit(
            "creatorResult",
            {
                "ok": True,
                "mode": requested_mode,
                "path": primary.get("path", ""),
                "mediaType": primary.get("kind", ""),
                "artifacts": artifacts,
                "info": info,
            },
        )

    @contextmanager
    def _creator_reserve(self, backend, owner, unload):
        with self._creator_coordinator.reserve(owner, unload_llm=unload, timeout=0):
            self._creator_claim_backend(backend)
            try:
                self._creator_check_cancelled()
                yield
            finally:
                job = getattr(self._creator_job_local, "job", None)
                if job is not None:
                    with job["backend_lock"], self._creator_state_lock:
                        if self._creator_active_job is job:
                            job["backend"] = None

    def _creator_claim_backend(self, backend) -> None:
        """Called only while this job owns the shared generation lease."""
        job = getattr(self._creator_job_local, "job", None)
        if job is not None:
            with job["backend_lock"], self._creator_state_lock:
                if self._creator_active_job is job:
                    job["backend"] = backend

    def _creator_check_cancelled(self) -> None:
        local = getattr(self, "_creator_job_local", None)
        job = getattr(local, "job", None)
        if job is not None and job["cancel"].is_set():
            raise RuntimeError("생성이 취소되었습니다")

    def _creator_cache_preferences(self):
        prefs = self._creator_prefs()
        enabled = prefs.get("h3ConditioningCacheEnabled", True) is True
        try:
            gb = max(1, min(64, int(prefs.get("h3ConditioningCacheMaxGB", 8))))
            entries = max(1, min(256, int(prefs.get("h3ConditioningCacheMaxEntries", 32))))
        except (ValueError, TypeError, OverflowError):
            gb, entries = 8, 32
        return enabled, gb * 1024 ** 3, entries

    def _creator_configure_h3_cache(self, mode, params, available):
        if not mode.startswith("h3_"):
            return
        from core.h3_conditioning_cache import CACHE_NODE_TYPES
        enabled, max_bytes, max_entries = self._creator_cache_preferences()
        enabled = params.get("conditioning_cache", params.get("h3ConditioningCacheEnabled", enabled)) is True
        supported = (CACHE_NODE_TYPES | {"EmptyMiniMaxH3LatentAV"}).issubset(available)
        params["conditioning_cache"] = enabled and supported
        params["conditioning_cache_max_bytes"] = max_bytes
        params["conditioning_cache_max_entries"] = max_entries
        if enabled and not supported:
            self._creator_emit("creatorProgress", {"stage": "cache_unavailable", "percent": 0,
                "cache": "unavailable", "message": "H3 캐시 노드가 없어 이번 작업은 캐시 없이 생성합니다. ComfyUI 노드 업데이트/재시작이 필요합니다."})

    def _creator_run_workflow(self, backend, built, progress):
        from core.h3_conditioning_cache import prepare_receipt

        stages = built.get("stages") or [{"name": "sample", "workflow": built["workflow"]}]
        receipt = None
        result = None
        for stage in stages:
            self._creator_check_cancelled()
            encode = stage["name"] == "encode"
            graph = copy.deepcopy(stage["workflow"])
            if receipt and not encode:
                graph["6"]["inputs"]["expected_key"] = receipt["key"]
            if encode:
                self._creator_emit("creatorProgress", {"stage": "cache_check", "percent": 0,
                    "message": "H3 인코딩 캐시와 서버의 모델·입력 파일을 확인하는 중"})

            def stage_progress(value, maximum, preview=None):
                if len(stages) == 1:
                    progress(value, maximum, preview)
                    return
                ratio = max(0.0, min(1.0, value / maximum if maximum else 0))
                progress(round((ratio * 25) if encode else (25 + ratio * 75)), 100, preview)

            kwargs = {"cancel_check": self._creator_cancel_event.is_set}
            if encode:
                kwargs["allow_empty_outputs"] = True
            result = backend.run_workflow(graph, stage_progress, **kwargs)
            self._creator_check_cancelled()
            if not result.success:
                raise RuntimeError(result.error or "Creator 워크플로 실행에 실패했습니다")
            if encode:
                receipt = prepare_receipt(result.info or {})
                self._creator_emit("creatorProgress", {"stage": "cache_hit" if receipt.get("hit") else "cache_saved",
                    "percent": 25, "cache": "hit" if receipt.get("hit") else "miss",
                    "message": "저장된 H3 인코딩을 재사용합니다 · 인코더 해제 완료" if receipt.get("hit") else "H3 인코딩 저장 · 인코더 해제 완료"})
                self._creator_check_cancelled()
        if receipt is not None:
            result.info = {**(result.info or {}), "conditioning_cache": receipt}
        return result

    def _creator_cache_request(self, operation, payload):
        def work():
            import requests
            event = {"operation": operation, "requestId": str(payload.get("requestId", ""))[:100],
                     "ok": False, "available": False, "scope": "comfy_server"}
            enabled, max_bytes, max_entries = self._creator_cache_preferences()
            event.update(enabled=enabled, maxBytes=max_bytes, maxEntries=max_entries)
            try:
                from backends import BackendType, get_backend, get_backend_type
                if get_backend_type() is not BackendType.COMFYUI:
                    raise RuntimeError("H3 캐시는 선택된 ComfyUI 서버에서 관리합니다")
                with self._creator_state_lock:
                    if operation == "clear" and self._creator_running:
                        raise RuntimeError("Creator 작업이 끝난 뒤 캐시를 비워 주세요")
                backend = get_backend()
                url = f"{backend.api_url.rstrip('/')}/aistudio/h3-cache/{operation}"
                response = (requests.post(url, json={}, timeout=15) if operation == "clear"
                            else requests.get(url, timeout=15))
                if response.status_code == 404:
                    raise RuntimeError("ComfyUI에 H3 캐시 노드가 없습니다. 노드 업데이트 후 서버를 재시작하세요")
                event["available"] = True
                if response.status_code == 409:
                    raise RuntimeError("ComfyUI 서버에서 다른 작업이 실행 중입니다. 완료 후 캐시를 비워 주세요")
                response.raise_for_status()
                data = response.json()
                # Never forward arbitrary server paths or other clients' metadata.
                for key in ("entries", "bytes", "removedEntries", "removedBytes"):
                    if key in data:
                        event[key] = max(0, int(data[key]))
                event["ok"] = True
            except Exception as exc:
                # Network errors may contain a URL; do not expose backend addresses.
                event["error"] = str(exc)[:300] if isinstance(exc, RuntimeError) else "H3 캐시 서버 요청에 실패했습니다"
            self._creator_emit("creatorCacheEvent", event)
        threading.Thread(target=work, daemon=True, name=f"creator-cache-{operation}").start()

    def _creator_cancel(self, payload: dict) -> None:
        requested = str(payload.get("requestId") or "")[:100]
        with self._creator_state_lock:
            job = self._creator_active_job
            if job is None or (requested and requested != job["requestId"]):
                self._creator_emit("creatorProgress", {
                    "stage": "cancel_ignored", "requestId": requested,
                    "message": "해당 Creator 작업은 실행 중이 아닙니다",
                })
                return
            if job["cancel"].is_set():
                return
            job["cancel"].set()

        def interrupt_owned():
            # Network latency must not hold the short UI state lock. Only the
            # worker's lease release waits on this separate ownership lock.
            with job["backend_lock"]:
                with self._creator_state_lock:
                    backend = job["backend"] if self._creator_active_job is job else None
                if backend is None:
                    return
                try:
                    backend.interrupt()
                except Exception:
                    pass
        threading.Thread(target=interrupt_owned, daemon=True, name="creator-cancel").start()
        self._creator_emit("creatorProgress", {"stage": "cancel", "requestId": job["requestId"],
                                               "message": "취소 요청 전송"})

    def _creator_progress_callback(self, value: int, maximum: int, _preview=None) -> None:
        percent = int(value if maximum == 100 else (value * 100 / maximum if maximum else 0))
        self._creator_emit(
            "creatorProgress",
            {
                "stage": "generate",
                "value": int(value),
                "maximum": int(maximum),
                "percent": max(0, min(100, percent)),
            },
        )

    @staticmethod
    def _creator_object_info(backend) -> dict:
        import requests

        response = requests.get(f"{backend.api_url.rstrip('/')}/object_info", timeout=15)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _creator_prepare_params(self, backend, params: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the Vue payload and upload only media used by the graph."""

        mode = str(params.get("mode", "")).strip().lower()
        source_key = "input_video" if mode == "h3_v2v" else "input_image"
        uploads = (
            (("sourcePath", "source_path"), source_key),
            (("identityPath", "identity_path"), "input_image"),
            (("referencePath", "reference_path"), "reference_image"),
            (("imagePath", "image_path"), "input_image"),
            (("videoPath", "video_path"), "input_video"),
        )
        for incoming_names, normalized in uploads:
            path_text = ""
            for incoming in incoming_names:
                value = params.pop(incoming, "")
                if value:
                    path_text = value
                    break
            if not path_text:
                continue
            path = Path(str(path_text)).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {path}")
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            params[normalized] = backend.upload_media(path.read_bytes(), path.name, mime)

        seed = params.get("seed", -1)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed는 정수여야 합니다")
        params["seed"] = secrets.randbits(63) if seed < 0 else seed
        params["generate_audio"] = bool(params.get("includeAudio", params.get("generate_audio", False)))
        if mode == "h3_v2v":
            params["include_reference_audio"] = bool(params["generate_audio"])

        audio_prompt = str(params.pop("audioPrompt", params.pop("audio_prompt", "")) or "").strip()
        dialogue = str(params.pop("dialogue", "") or "").strip()
        prompt_parts = [str(params.get("prompt", "")).strip()]
        if audio_prompt:
            prompt_parts.append(f"Overall soundscape: {audio_prompt}")
        if dialogue:
            prompt_parts.append(f"Dialogue: {dialogue}")
        negative = str(params.pop("negative", "") or "").strip()
        if negative:
            prompt_parts.append(f"Avoid: {negative}")
        if mode == "h3_v2v":
            reference_instructions = []
            if params.get("input_image"):
                reference_instructions.append("Use <Picture 1> for subject identity and appearance.")
            reference_instructions.append("Use <Video 1> for motion, staging, and camera movement.")
            if params.get("include_reference_audio"):
                reference_instructions.append("Use <Audio 1> as the synchronized sound reference.")
            prompt_parts.insert(0, " ".join(reference_instructions))
        params["prompt"] = "\n".join(part for part in prompt_parts if part)
        return params

    @staticmethod
    def _creator_check_nodes(built: Dict[str, Any], available: set[str]) -> None:
        missing = sorted(set(built.get("required_node_types", ())) - available)
        if missing:
            raise RuntimeError("ComfyUI 필수 노드가 없습니다: " + ", ".join(missing))

    @staticmethod
    def _creator_resolve_comfy_choices(
        built: Dict[str, Any], object_info: Dict[str, Any]
    ) -> None:
        """Replace portable model paths with the server's exact combo values.

        ComfyUI returns subfolder choices with OS-native separators.  Matching
        them slash-insensitively keeps one workflow portable across Windows and
        Linux while still satisfying Comfy's exact ``value_not_in_list`` check.
        """

        graphs = [built.get("workflow", {})] + [stage["workflow"] for stage in built.get("stages", [])]
        descriptors = []
        for graph in list(graphs):
            for node in graph.values():
                if node.get("class_type") not in {"ForgeNeoH3ConditioningCachePrepare", "ForgeNeoH3ConditioningCacheLoad"}:
                    continue
                inputs = node["inputs"]
                descriptor = json.loads(inputs["descriptor"])
                descriptors.append((inputs, descriptor))
                graphs.extend([descriptor["conditioning"], dict(enumerate(descriptor["models"]))])
        for node in (node for graph in graphs for node in graph.values()):
            if not isinstance(node, dict):
                continue
            schema = object_info.get(str(node.get("class_type", "")), {})
            input_schema = schema.get("input", {}) if isinstance(schema, dict) else {}
            definitions: Dict[str, Any] = {}
            for section in ("required", "optional"):
                values = input_schema.get(section, {}) if isinstance(input_schema, dict) else {}
                if isinstance(values, dict):
                    definitions.update(values)
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            for name, value in list(inputs.items()):
                if node.get("class_type") == "LoadImage" and name == "image":
                    # Uploaded files may be newer than this /object_info snapshot.
                    continue
                definition = definitions.get(name)
                if not isinstance(value, str) or not isinstance(definition, (list, tuple)) or not definition:
                    continue
                choices = definition[0]
                if not isinstance(choices, (list, tuple)):
                    continue
                normalized = value.replace("\\", "/").casefold()
                match = next(
                    (
                        choice for choice in choices
                        if isinstance(choice, str)
                        and choice.replace("\\", "/").casefold() == normalized
                    ),
                    None,
                )
                if match is None:
                    requested_stem = Path(normalized).stem
                    stem_matches = [
                        choice for choice in choices
                        if isinstance(choice, str)
                        and Path(choice.replace("\\", "/").casefold()).stem == requested_stem
                    ]
                    if len(stem_matches) == 1:
                        match = stem_matches[0]
                if match is not None:
                    inputs[name] = match
                elif choices:
                    raise RuntimeError(
                        f"ComfyUI 리소스 선택지에 {node.get('class_type')}.{name}="
                        f"{value!r} 항목이 없습니다"
                    )
        for inputs, descriptor in descriptors:
            inputs["descriptor"] = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _creator_image_size(data: bytes) -> tuple[int, int]:
        from io import BytesIO
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            return image.size

    # ── Comic planning, generation, and export ───────────────────────────

    def _comic_studio(self):
        from core.comic_studio import ComicStudio
        from core.storage_paths import user_data_file

        return ComicStudio(
            user_data_file(
                "creator/comic_studio.json",
                legacy_paths="config/comic_studio.json",
            ),
            complete_json=self._comic_ollama_complete if self._creator_ollama_config()[1] else None,
        )

    def _comic_start_plan(self, payload: dict) -> None:
        self._creator_run_thread("comic_plan", self._comic_plan, payload)

    def _comic_plan(self, payload: dict) -> None:
        studio = self._comic_studio()
        document = studio.plan(
            str(payload.get("scene", "")),
            int(payload.get("panelCount", payload.get("panel_count", 3)) or 3),
            str(payload.get("style", payload.get("artStyle", "manga"))),
            str(payload.get("characterLock", payload.get("character_lock", ""))),
        )
        expected = payload.get("expectedRevision")
        document = studio.save(
            document,
            expected_revision=int(expected) if expected is not None else None,
        )
        self._creator_emit("comicStoryboardReady", document.to_dict())
        self._comic_emit_document(document, status="saved", source="plan")
        self._creator_emit("creatorResult", {"ok": True, "mode": "comic_plan"})

    def _comic_save(self, payload: dict) -> None:
        from core.comic_studio import ComicRevisionConflict

        request_id = str(payload.get("requestId", ""))[:100]
        try:
            expected = payload.get("expectedRevision")
            document = self._comic_studio().save(
                payload.get("document", payload),
                expected_revision=int(expected) if expected is not None else None,
            )
            self._comic_emit_document(
                document,
                status="saved",
                source="backend",
                requestId=request_id,
            )
        except ComicRevisionConflict as exc:
            self._comic_emit_document(
                exc.current_document,
                status="conflict",
                source="backend",
                requestId=request_id,
                expectedRevision=exc.expected_revision,
                actualRevision=exc.actual_revision,
                conflictPath=exc.conflict_path,
                error=str(exc),
            )
        except Exception as exc:
            self._comic_emit_document(
                None,
                status="error",
                source="backend",
                requestId=request_id,
                error=str(exc),
            )

    def _comic_emit_document(self, document, *, status: str, **persistence) -> None:
        payload = {
            "document": document.to_dict() if document is not None else None,
            "persistence": {"status": status, **persistence},
        }
        self._creator_emit("comicDocumentChanged", payload)

    def _comic_start_generate_all(self, payload: dict) -> None:
        self._creator_run_thread("comic_generate", self._comic_generate_all, payload)

    def _comic_generate_all(self, payload: dict) -> None:
        from backends import get_backend
        from core.comic_studio import panel_generation_payloads

        studio = self._comic_studio()
        document = studio.normalize(payload.get("document", payload))
        backend = get_backend()
        model = str(payload.get("model", "") or self._creator_current_model())
        width = int(payload.get("width", 1024) or 1024)
        height = int(payload.get("height", 1024) or 1024)
        panel_payloads = list(panel_generation_payloads(document))
        unload = self._creator_should_unload_ollama()
        with self._creator_reserve(backend, "comic_generate", unload):
            for index, panel_payload in enumerate(panel_payloads):
                if self._creator_cancel_event.is_set():
                    raise RuntimeError("Comic 컷 생성이 취소되었습니다")
                generation_payload = {
                    "prompt": panel_payload["prompt"],
                    "negative_prompt": panel_payload["negative_prompt"],
                    "seed": panel_payload["seed"],
                    "width": width,
                    "height": height,
                }

                def _progress(value, maximum, preview=None, panel_index=index):
                    local = value / maximum if maximum else 0
                    overall = int(((panel_index + local) / len(panel_payloads)) * 100)
                    self._creator_emit(
                        "creatorProgress",
                        {
                            "stage": "comic_image",
                            "panelIndex": panel_index,
                            "panelCount": len(panel_payloads),
                            "percent": overall,
                        },
                    )

                result = backend.txt2img(model, generation_payload, _progress)
                if not result.success or not result.image_data:
                    raise RuntimeError(result.error or f"컷 {index + 1} 생성 결과가 없습니다")
                path = self._creator_write_bytes(
                    result.image_data, f"comic_panel_{index + 1}.png", "comic"
                )
                document.panels[index].image_path = path
                document = studio.save(document)
                self._comic_emit_document(document, status="saved", source="generation")

        last_path = document.panels[-1].image_path if document.panels else ""
        self._creator_emit(
            "creatorResult",
            {
                "ok": True,
                "mode": "comic_generate",
                "path": last_path,
                "mediaType": "image",
                "document": document.to_dict(),
            },
        )

    def _comic_generate_panel(self, payload: dict) -> None:
        from backends import get_backend
        from core.comic_studio import panel_generation_payloads

        studio = self._comic_studio()
        document = studio.normalize(payload.get("document", payload))
        panel_id = str((payload.get("panel") or {}).get("id", payload.get("panelId", "")))
        try:
            panel_index = next(index for index, panel in enumerate(document.panels) if panel.id == panel_id)
        except StopIteration as exc:
            raise ValueError("생성할 Comic 컷을 찾을 수 없습니다") from exc
        panel_payload = list(panel_generation_payloads(document))[panel_index]
        backend = get_backend()
        generation_payload = {
            "prompt": panel_payload["prompt"],
            "negative_prompt": panel_payload["negative_prompt"],
            "seed": panel_payload["seed"],
            "width": int(payload.get("width", 1024) or 1024),
            "height": int(payload.get("height", 1024) or 1024),
        }
        with self._creator_reserve(backend, "comic_panel", self._creator_should_unload_ollama()):
            result = backend.txt2img(
                str(payload.get("model", "") or self._creator_current_model()),
                generation_payload,
                self._creator_progress_callback,
            )
        if self._creator_cancel_event.is_set():
            raise RuntimeError("Comic 컷 생성이 취소되었습니다")
        if not result.success or not result.image_data:
            raise RuntimeError(result.error or "Comic 컷 이미지 결과가 없습니다")
        path = self._creator_write_bytes(
            result.image_data, f"comic_panel_{panel_index + 1}.png", "comic"
        )
        document.panels[panel_index].image_path = path
        document = studio.save(document)
        self._comic_emit_document(document, status="saved", source="generation")
        self._creator_emit(
            "creatorResult",
            {
                "ok": True,
                "mode": "comic_panel",
                "panelId": panel_id,
                "path": path,
                "mediaType": "image",
                "document": document.to_dict(),
            },
        )

    def _comic_start_animate_all(self, payload: dict) -> None:
        self._creator_run_thread("comic_animate", self._comic_animate_all, payload)

    def _comic_animate_all(self, payload: dict) -> None:
        from backends import BackendType, get_backend, get_backend_type
        from core.creator_workflows import build

        if get_backend_type() is not BackendType.COMFYUI:
            raise RuntimeError("Living Comic은 ComfyUI 백엔드가 필요합니다")
        studio = self._comic_studio()
        document = studio.normalize(payload.get("document", payload))
        backend = get_backend()
        object_info = self._creator_object_info(backend)
        available = set(object_info.keys())
        unload = self._creator_should_unload_ollama()
        with self._creator_reserve(backend, "comic_animate", unload):
            for index, panel in enumerate(document.panels):
                if self._creator_cancel_event.is_set():
                    raise RuntimeError("Comic 애니메이션이 취소되었습니다")
                if not panel.image_path:
                    raise RuntimeError(f"컷 {index + 1} 이미지가 없습니다")
                uploaded = backend.upload_media(
                    Path(panel.image_path).read_bytes(),
                    Path(panel.image_path).name,
                    mimetypes.guess_type(panel.image_path)[0] or "image/png",
                )
                params = dict(payload.get("videoSettings", {}))
                params.update(
                    {
                        "input_image": uploaded,
                        "prompt": panel.motion_prompt or panel.text,
                        "seed": secrets.randbits(63) if panel.seed < 0 else panel.seed,
                    }
                )
                self._creator_configure_h3_cache("h3_i2v", params, available)
                built = build("h3_i2v", params)
                self._creator_check_nodes(built, available)
                self._creator_resolve_comfy_choices(built, object_info)

                def _progress(value, maximum, preview=None, panel_index=index):
                    local = value / maximum if maximum else 0
                    self._creator_emit(
                        "creatorProgress",
                        {
                            "stage": "comic_video",
                            "panelIndex": panel_index,
                            "panelCount": len(document.panels),
                            "percent": int(((panel_index + local) / len(document.panels)) * 100),
                        },
                    )

                result = self._creator_run_workflow(backend, built, _progress)
                if not result.success:
                    raise RuntimeError(result.error or f"컷 {index + 1} 영상 생성 실패")
                saved = self._creator_save_artifacts(result.artifacts, "comic_video")
                video = next((item for item in saved if item["kind"] in {"video", "animated"}), None)
                if not video:
                    raise RuntimeError(f"컷 {index + 1} 영상 결과가 없습니다")
                panel.video_path = video["path"]
                document = studio.save(document)
                self._comic_emit_document(document, status="saved", source="generation")
        last_path = document.panels[-1].video_path if document.panels else ""
        self._creator_emit(
            "creatorResult",
            {
                "ok": True,
                "mode": "comic_animate",
                "path": last_path,
                "mediaType": "video",
                "document": document.to_dict(),
            },
        )

    def _comic_export_page(self, payload: dict) -> None:
        try:
            data_url = str(payload.get("dataUrl", ""))
            fmt = "webp" if str(payload.get("format", "png")).lower() == "webp" else "png"
            match = re.fullmatch(
                rf"data:image/{fmt};base64,([A-Za-z0-9+/=]+)", data_url
            )
            if not match:
                raise ValueError("내보낼 Comic 이미지 데이터가 올바르지 않습니다")
            data = base64.b64decode(match.group(1), validate=True)
            if not data or len(data) > 50 * 1024 * 1024:
                raise ValueError("Comic 이미지가 비어 있거나 50MB 제한을 초과했습니다")
            path = self._creator_write_bytes(data, f"comic_page.{fmt}", "comic")
            if payload.get("document"):
                document = self._comic_studio().save(payload["document"])
                self._comic_emit_document(document, status="saved", source="export")
            self._creator_emit(
                "creatorResult",
                {
                    "ok": True,
                    "mode": "comic_export",
                    "path": path,
                    "mediaType": "image",
                    "artifacts": [{"kind": "image", "path": path}],
                },
            )
        except Exception as exc:
            self._creator_emit(
                "creatorResult", {"ok": False, "mode": "comic_export", "error": str(exc)}
            )

    def _comic_start_export_living(self, payload: dict) -> None:
        self._creator_run_thread("comic_living_export", self._comic_export_living, payload)

    def _comic_export_living(self, payload: dict) -> None:
        from core.living_comic import render_living_comic

        document = self._comic_studio().normalize(payload.get("document", payload))
        out_dir = self._creator_output_dir("comic")
        result = render_living_comic(
            document.to_dict(),
            out_dir,
            fps=int(payload.get("fps", 8) or 8),
            seconds=float(payload.get("seconds", 4) or 4),
            cancelled=self._creator_cancel_event.is_set,
        )
        artifacts = [
            {"kind": "video" if path.lower().endswith(".mp4") else "animated", "path": path}
            for path in result
        ]
        self._creator_emit(
            "creatorResult",
            {
                "ok": True,
                "mode": "comic_living_export",
                "path": artifacts[0]["path"] if artifacts else "",
                "mediaType": artifacts[0]["kind"] if artifacts else "",
                "artifacts": artifacts,
            },
        )

    # ── Shared helpers ───────────────────────────────────────────────────

    def _creator_save_artifacts(self, artifacts: Iterable, feature: str) -> list:
        saved = []
        for index, artifact in enumerate(artifacts or []):
            self._creator_check_cancelled()
            kind = str(getattr(artifact, "kind", "binary"))
            data = getattr(artifact, "data", None)
            filename = str(getattr(artifact, "filename", "") or f"{feature}_{index + 1}.bin")
            mime = str(getattr(artifact, "mime", "") or mimetypes.guess_type(filename)[0] or "")
            path = str(getattr(artifact, "path", "") or "")
            if data:
                path = self._creator_write_bytes(data, filename, feature)
            self._creator_check_cancelled()
            saved.append(
                {
                    "kind": kind,
                    "path": path.replace("\\", "/"),
                    "filename": Path(path or filename).name,
                    "mime": mime,
                    "metadata": getattr(artifact, "metadata", {}) or {},
                }
            )
        return saved

    def _creator_write_bytes(self, data: bytes, filename: str, feature: str) -> str:
        from core.file_naming import sanitize_filename

        safe_name = sanitize_filename(Path(filename).stem, fallback=feature)
        suffix = Path(filename).suffix.lower() or ".bin"
        directory = self._creator_output_dir(feature)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        candidate = directory / f"{safe_name}_{stamp}{suffix}"
        serial = 2
        while candidate.exists():
            candidate = directory / f"{safe_name}_{stamp}_{serial}{suffix}"
            serial += 1
        temporary = candidate.with_suffix(candidate.suffix + ".writing")
        self._creator_check_cancelled()
        try:
            temporary.write_bytes(data)
            with self._creator_state_lock:
                self._creator_check_cancelled()
                os.replace(temporary, candidate)
        finally:
            temporary.unlink(missing_ok=True)
        return str(candidate).replace("\\", "/")

    @staticmethod
    def _creator_output_dir(feature: str) -> Path:
        from config import OUTPUT_DIR

        safe_feature = re.sub(r"[^a-z0-9_-]", "_", feature.lower())[:60] or "creator"
        directory = Path(OUTPUT_DIR) / "creator" / safe_feature
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _creator_current_model(self) -> str:
        widget = getattr(self, "model_combo", None)
        if widget and hasattr(widget, "currentText"):
            return str(widget.currentText() or "")
        return ""

    @staticmethod
    def _creator_prefs() -> dict:
        path = Path(__file__).resolve().parent.parent / "config" / "ui_prefs.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _creator_ollama_config(self) -> tuple[str, str]:
        prefs = self._creator_prefs()
        return (
            str(prefs.get("ollamaUrl", "http://localhost:11434") or "http://localhost:11434").rstrip("/"),
            str(prefs.get("ollamaModel", "") or ""),
        )

    def _creator_should_unload_ollama(self) -> bool:
        prefs = self._creator_prefs()
        return bool(prefs.get("ollamaUnloadOnGen", False) and prefs.get("ollamaModel"))

    def _creator_unload_ollama(self) -> bool:
        from core.ollama_client import OllamaClient

        url, model = self._creator_ollama_config()
        if not model:
            return True
        client = OllamaClient(url, model)
        if not client.test_connection():
            # Ollama 가 떠 있지 않으면 점유한 VRAM 도 없다 → 언로드 성공으로 본다.
            # ui/generator_generation.py 의 _maybe_unload_ollama 와 같은 의미론
            # ("Ollama 미실행/미설정이면 조용히 무시").
            return True
        return client.unload()

    def _comic_ollama_complete(self, system: str, user: str) -> str:
        import requests

        url, model = self._creator_ollama_config()
        if not model:
            raise RuntimeError("Settings에서 Comic Director용 Ollama 모델을 선택하세요")
        response = requests.post(
            f"{url}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.35, "num_predict": 3600},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return str((data.get("message") or {}).get("content") or data.get("response") or "")

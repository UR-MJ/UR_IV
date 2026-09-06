"""Native-only Settings actions for the verified model download manager."""
from __future__ import annotations

import json
import queue
import threading

from core.model_downloads import ModelDownloadManager


_INIT_LOCK = threading.RLock()


class ModelDownloadActionsMixin:
    def _model_download_emit(self, state: dict) -> None:
        if getattr(self, "web_mode", False) or getattr(self, "_model_download_closed", False):
            return
        signal = getattr(getattr(self, "vue_bridge", None), "modelDownloadEvent", None)
        if signal is not None:
            signal.emit(json.dumps(state, ensure_ascii=False))

    def _handle_model_download_action(self, action: str, payload: dict) -> bool:
        if action in (
            "model_download_status", "model_download_start",
            "model_download_cancel", "model_download_verify",
        ):
            pass
        else:
            return False
        # A web client must never discover local paths or initiate installation.
        if getattr(self, "web_mode", False):
            return True
        with _INIT_LOCK:
            if getattr(self, "_model_download_closed", False):
                return True
            if not hasattr(self, "_model_download_requests"):
                self._model_download_requests = queue.Queue(maxsize=8)
                self._model_download_dispatcher = threading.Thread(
                    target=self._model_download_dispatch, daemon=True, name="model-download-actions")
                self._model_download_dispatcher.start()
            try:
                # Only IDs cross the boundary; arbitrary URLs and paths are ignored.
                self._model_download_requests.put_nowait((action, dict(payload or {})))
            except queue.Full:
                self._model_download_emit({"available": True, "actionError": "요청 처리 중입니다. 잠시 기다려 주세요"})
        return True

    def _model_download_dispatch(self) -> None:
        manager = None
        while True:
            task = self._model_download_requests.get()
            try:
                if task is None or getattr(self, "_model_download_closed", False):
                    return
                action, payload = task
                if manager is None:
                    with _INIT_LOCK:
                        if getattr(self, "_model_download_closed", False):
                            return
                        factory = getattr(self, "_model_download_manager_factory", ModelDownloadManager)
                        manager = factory(on_event=self._model_download_emit)
                        self._model_download_manager = manager
                if action == "model_download_status":
                    state = manager.status()
                elif action == "model_download_cancel":
                    state = manager.cancel(str(payload.get("jobId", "")))
                else:
                    selected = payload.get("packIds", [])
                    if not isinstance(selected, list) or not all(isinstance(item, str) for item in selected):
                        raise ValueError("다운로드 목록에서 기능을 선택하세요")
                    method = manager.start if action == "model_download_start" else manager.verify
                    state = method(selected)
                self._model_download_emit({**state, "actionError": ""})
            except Exception as exc:
                state = manager.status(refresh=False) if manager else {"available": False, "busy": False}
                self._model_download_emit({**state, "actionError": str(exc)})
            finally:
                self._model_download_requests.task_done()

    def _shutdown_model_downloads(self) -> None:
        with _INIT_LOCK:
            self._model_download_closed = True
            manager = getattr(self, "_model_download_manager", None)
            requests = getattr(self, "_model_download_requests", None)
            if manager is not None:
                # The daemon worker preserves its partial file, checks cancellation
                # per chunk and has a bounded HTTP read timeout. Do not freeze Qt.
                manager.shutdown(timeout=0)
            if requests is not None:
                try:
                    requests.put_nowait(None)
                except queue.Full:
                    pass  # The dispatcher sees the closed flag at the next item.

"""Bounded native-only compatibility inspection; never installs extensions."""
from __future__ import annotations

import json
import threading

from core.comfy_compatibility import inspect_compatibility, save_baseline


_INIT_LOCK = threading.Lock()


class ComfyCompatibilityActionsMixin:
    def _compatibility_emit(self, report):
        if getattr(self, "web_mode", False) or getattr(self, "_compatibility_closed", False):
            return
        signal = getattr(getattr(self, "vue_bridge", None), "comfyCompatibilityResult", None)
        if signal is not None:
            try:
                signal.emit(json.dumps(report, ensure_ascii=False))
            except RuntimeError:
                pass  # QObject already disposed during app shutdown.

    def _compatibility_url(self):
        import config
        return str(config.COMFYUI_API_URL).strip().rstrip("/")

    def _handle_comfy_compatibility_action(self, action, payload):
        if action in ("comfy_compatibility_refresh", "comfy_compatibility_save_baseline"):
            pass
        else:
            return False
        if getattr(self, "web_mode", False) or getattr(self, "_compatibility_closed", False):
            return True
        payload = payload if isinstance(payload, dict) else {}
        request_id = str(payload.get("requestId", ""))[:100]
        with _INIT_LOCK:
            if not hasattr(self, "_compatibility_lock"):
                self._compatibility_lock = threading.Lock()
                self._compatibility_busy = False
            if self._compatibility_busy:
                self._compatibility_emit({"ok": False, "requestId": request_id, "error": "호환 조합 확인 중입니다. 잠시 후 다시 시도하세요."})
                return True
            self._compatibility_busy = True
        endpoint = self._compatibility_url()

        def work():
            try:
                inspect = getattr(self, "_compatibility_inspector", inspect_compatibility)
                report = inspect(endpoint)
                with self._compatibility_lock:
                    if getattr(self, "_compatibility_closed", False):
                        return
                    if endpoint != self._compatibility_url():
                        self._compatibility_emit({"ok": False, "requestId": request_id, "error": "ComfyUI 주소가 변경되었습니다. 다시 확인하세요."})
                        return
                    if action == "comfy_compatibility_save_baseline":
                        save = getattr(self, "_compatibility_baseline_saver", save_baseline)
                        report["baseline"] = save(report)
                        report["message"] = "현재 감지 조합을 기준으로 저장했습니다. 실제 생성 성공을 보증하는 인증은 아닙니다."
                    self._compatibility_emit({**report, "requestId": request_id})
            except Exception as exc:
                # Do not forward requests exception text containing credentials/paths.
                from core.error_handler import sanitize_for_ui
                error = sanitize_for_ui(str(exc)) if isinstance(exc, ValueError) else "호환 조합을 확인하지 못했습니다. 서버 연결과 설정 저장 권한을 확인하세요."
                self._compatibility_emit({"ok": False, "requestId": request_id, "error": error})
            finally:
                with _INIT_LOCK:
                    self._compatibility_busy = False

        worker = threading.Thread(target=work, daemon=True, name="comfy-compatibility")
        self._compatibility_worker = worker
        worker.start()
        return True

    def _shutdown_comfy_compatibility(self):
        with _INIT_LOCK:
            self._compatibility_closed = True

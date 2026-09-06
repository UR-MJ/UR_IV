"""Native Comfy workflow inspection, validated controls, and quality presets."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import threading
import uuid

from core.comfy_workflow_controls import (
    WorkflowControlError, clear_workflow_controls, describe_controls,
    feature_preflight, load_workflow_controls, save_workflow_controls,
    validate_controls, controls_for_wire,
)
from utils.atomic_json import atomic_write_json

_PRESET_PATH = Path(__file__).resolve().parent.parent / "config" / "comfy_quality_preset.json"
PRESET_FIELDS = (
    "hires_options_group", "hires_scale_input", "hires_denoising_input",
    "adetailer_group", "sam3_group", "_sam3_detect_prompt", "_sam3_mode",
    "_sam3_mask_mode", "_sam3_denoise", "_sam3_inpaint_only_masked",
)


def preset_values(name: str, targets: str = "face") -> dict:
    if name == "fast":
        return {"hires_options_group": False, "adetailer_group": False, "sam3_group": False}
    if name != "detail" or targets not in ("none", "face", "eyes", "face_then_eyes"):
        raise WorkflowControlError("빠름/정밀 프리셋과 보정 대상을 확인하세요")
    values = {"hires_options_group": True, "hires_scale_input": "1.5",
              "hires_denoising_input": "0.35", "adetailer_group": False,
              "sam3_group": targets != "none"}
    if targets != "none":
        values.update({"_sam3_detect_prompt": "face" if targets == "face_then_eyes" else targets, "_sam3_mode": "Inpaint",
                       "_sam3_mask_mode": "Individual", "_sam3_denoise": "0.3",
                       "_sam3_inpaint_only_masked": True})
    return values


def _proxy_read(proxy):
    for name in ("isChecked", "toPlainText", "currentText", "text"):
        fn = getattr(proxy, name, None)
        if fn is not None:
            return fn()
    raise WorkflowControlError("지원하지 않는 생성 설정 프록시입니다")


def _proxy_write(proxy, value):
    if isinstance(value, bool) and hasattr(proxy, "setChecked"):
        proxy.setChecked(value)
        return
    for name in ("setPlainText", "setText", "setCurrentText"):
        fn = getattr(proxy, name, None)
        if fn is not None:
            fn(str(value))
            return
    raise WorkflowControlError("지원하지 않는 생성 설정 프록시입니다")


def _endpoint_id(endpoint):
    return hashlib.sha256(str(endpoint or '').rstrip('/').encode('utf-8')).hexdigest()


def apply_quality_preset(host, name: str, targets: str = "face", *, endpoint=None, state_path=None) -> dict:
    """Apply through registered WidgetProxies; preserve first custom snapshot."""
    proxies = getattr(getattr(host, "vue_bridge", None), "_proxies", {})
    missing = [key for key in PRESET_FIELDS if key not in proxies]
    if missing:
        raise WorkflowControlError("생성 설정이 아직 준비되지 않았습니다: " + ", ".join(missing))
    path = Path(state_path or _PRESET_PATH)
    state = {"version": 1, "active": "custom", "backup": None}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkflowControlError("기존 프리셋 복원 파일을 읽지 못했습니다. 파일을 보존하고 확인하세요") from exc
        if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("backup"), (dict, type(None))):
            raise WorkflowControlError("프리셋 복원 파일 형식이 올바르지 않습니다")
    before = {key: _proxy_read(proxies[key]) for key in PRESET_FIELDS}
    if name == "restore":
        if not state.get("backup"):
            raise WorkflowControlError("복원할 사용자 설정이 없습니다")
        changes = state["backup"]
        if set(changes) != set(PRESET_FIELDS):
            raise WorkflowControlError("복원할 설정 목록이 변경되었습니다. 원본 복원 파일을 확인하세요")
        after_state = {"version": 1, "active": "custom", "backup": None}
    else:
        changes = preset_values(name, targets)
        after_state = {"version": 1, "active": name, "targets": targets, "backup": state.get("backup") or before}
        session_id = getattr(host, '_comfy_quality_session_id', None) or uuid.uuid4().hex
        host._comfy_quality_session_id = session_id
        after_state.update(sessionId=session_id, endpointId=_endpoint_id(endpoint),
                           armed=bool(endpoint and name == 'detail' and targets == 'face_then_eyes'))
    # Persist the recovery snapshot before any UI mutations.
    atomic_write_json(str(path), {**state, "backup": state.get("backup") or before})
    try:
        for key, value in changes.items():
            _proxy_write(proxies[key], value)
        atomic_write_json(str(path), after_state)
    except Exception:
        for key, value in before.items():
            _proxy_write(proxies[key], value)
        raise
    host._comfy_quality_disarmed = not after_state.get('armed', False)
    return {"name": after_state["active"], "canRestore": bool(after_state["backup"]),
            "changed": list(changes), "note": "해상도·기본 스텝·모델·업스케일러 선택은 유지했습니다."}


def _disarm_quality_preset(host, *, state_path=None, state=None):
    """Disarm this host immediately, preserving the recovery snapshot on disk."""
    session_id = getattr(host, '_comfy_quality_session_id', None)
    if not session_id or getattr(host, '_comfy_quality_disarmed', False):
        return
    host._comfy_quality_disarmed = True  # A failed disk write must still fail closed.
    path = Path(state_path or _PRESET_PATH)
    if state is None:
        if not path.exists():
            return
        state = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(state, dict) and state.get('sessionId') == session_id and state.get('armed'):
        atomic_write_json(str(path), {**state, 'armed': False})


def quality_preset_payload(payload, *, host=None, endpoint=None, state_path=None):
    """Only the explicitly armed window/server may snapshot the extra pass."""
    session_id = getattr(host, '_comfy_quality_session_id', None)
    if not session_id or not endpoint or getattr(host, '_comfy_quality_disarmed', False):
        return {}
    path = Path(state_path or _PRESET_PATH)
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowControlError("정밀 프리셋 정보를 읽지 못했습니다. 복원 파일을 확인하세요") from exc
    if not isinstance(state, dict) or state.get("version") != 1:
        raise WorkflowControlError("정밀 프리셋 정보 형식이 올바르지 않습니다")
    if state.get("active") != "detail" or state.get("targets") != "face_then_eyes":
        return {}
    if (not state.get('armed') or state.get('sessionId') != session_id
            or state.get('endpointId') != _endpoint_id(endpoint)):
        return {}
    from core.comfy_workflow_compiler import ComfyWorkflowCompiler
    sam = ComfyWorkflowCompiler()._sam3_state(payload)
    if sam is None or sam.get("sam3_prompt") != "face" or sam.get("sam3_mode", "Inpaint") != "Inpaint":
        _disarm_quality_preset(host, state_path=path, state=state)
        return {}  # Manual SAM3 changes take precedence over the preset.
    return {"_comfy_detail_passes": ["eyes"]}


class ComfyWorkflowActionsMixin:
    def _comfy_quality_user_change(self, widget_id, previous, value):
        # Programmatic proxy writes (preset apply/restore) never enter this hook.
        if widget_id not in ('sam3_group', '_sam3_detect_prompt', '_sam3_mode') or previous == value:
            return
        try:
            _disarm_quality_preset(self)
        except (OSError, ValueError) as exc:
            from core.error_handler import handle_error
            try:
                handle_error('E030', '정밀 프리셋 해제 저장', exc, notify=False)
            except (UnicodeError, OSError):
                pass
            self.vue_bridge.showNotification.emit('warning', '추가 눈 보정은 해제했지만 상태 저장에 실패했습니다. 설정 파일을 확인하세요.')

    def _comfy_controls_emit(self, event):
        if getattr(self, "_comfy_controls_closed", False):
            return
        signal = getattr(getattr(self, "vue_bridge", None), "comfyWorkflowEvent", None)
        if not event.get("busy") and event.get("requestId") == getattr(self, "_comfy_controls_request_id", None):
            self._comfy_controls_busy = False
        if signal is not None:
            try:
                signal.emit(json.dumps(event, ensure_ascii=False))
            except RuntimeError:
                pass  # Qt object can be disposed while bounded HTTP finishes.

    def _shutdown_comfy_workflow_controls(self):
        self._comfy_controls_closed = True
        self._comfy_controls_serial = getattr(self, "_comfy_controls_serial", 0) + 1

    def _handle_comfy_workflow_action(self, action, payload):
        if action in ("comfy_controls_inspect", "comfy_controls_save", "comfy_controls_clear",
                      "comfy_feature_preflight", "comfy_quality_preset"):
            pass
        else:
            return False
        request = dict(payload or {})
        request_id = str(request.get("requestId", ""))[:120]
        event = {"requestId": request_id, "action": action, "ok": False}
        if getattr(self, "_comfy_controls_closed", False):
            return True
        if getattr(self, "_comfy_controls_busy", False):
            self._comfy_controls_emit({**event, "busy": True, "error": "이전 워크플로 요청을 처리 중입니다. 잠시 기다려 주세요"})
            return True
        if getattr(self, "web_mode", False):
            self._comfy_controls_emit({**event, "error": "워크플로 파일·프리셋 관리는 로컬 앱에서 사용하세요"})
            return True
        from backends import get_backend, get_backend_type
        try:
            backend = get_backend()
            if get_backend_type().value != "comfyui":
                raise WorkflowControlError("ComfyUI 백엔드를 먼저 선택하세요")
            mode = str(request.get("mode") or "txt2img")
            if mode not in ("txt2img", "img2img"):
                raise WorkflowControlError("T2I 또는 I2I 워크플로를 선택하세요")
            path = backend._configured_workflow_path(mode)
            api_url = backend.api_url
            if action == "comfy_quality_preset":
                if getattr(getattr(self, "queue_manager", None), "is_running", False):
                    raise WorkflowControlError("대기열 실행 중에는 프리셋을 변경할 수 없습니다")
                worker = getattr(self, "gen_worker", None)
                if worker is not None and worker.isRunning():
                    raise WorkflowControlError("현재 생성이 끝난 뒤 프리셋을 변경하세요")
                result = apply_quality_preset(self, str(request.get("preset", "")), str(request.get("targets", "face")), endpoint=api_url)
                self._comfy_controls_emit({**event, "ok": True, "preset": result})
                return True
            # Snapshot proxy values only on the UI thread, never in the worker.
            generation_payload = model = None
            if action == "comfy_feature_preflight":
                generation_payload, error = self._build_generation_payload(snapshot=True)
                if error or generation_payload is None:
                    raise WorkflowControlError(error or "생성 설정을 확인하세요")
                model = self.model_combo.currentText()
            serial = getattr(self, "_comfy_controls_serial", 0) + 1
            self._comfy_controls_serial = serial
            self._comfy_controls_busy = True
            self._comfy_controls_request_id = request_id
        except Exception as exc:
            self._comfy_controls_error(event, exc)
            return True

        def work():
            try:
                def current():
                    return (get_backend() is backend and backend.api_url == api_url
                            and backend._configured_workflow_path(mode) == path
                            and not getattr(self, "_comfy_controls_closed", False)
                            and getattr(self, "_comfy_controls_serial", None) == serial)

                if action == "comfy_controls_clear":
                    if not current():
                        raise WorkflowControlError("백엔드가 바뀌었습니다. 다시 확인하세요")
                    clear_workflow_controls(api_url, path)
                    self._comfy_controls_emit({**event, "ok": True, "cleared": True})
                    return
                graph = backend._load_configured_workflow(mode)
                # Read capabilities only: do not call _workflow_compiler(), which
                # can install node packs or restart an app-owned backend.
                info = backend.get_object_info()
                if not current():
                    raise WorkflowControlError("백엔드 또는 워크플로가 바뀌었습니다. 다시 확인하세요")
                if action == "comfy_feature_preflight":
                    if mode != "txt2img":
                        raise WorkflowControlError("빠름/정밀 프리셋 사전 검증은 현재 T2I 생성 설정을 대상으로 합니다")
                    from core.comfy_workflow_compiler import ComfyWorkflowCompiler
                    binding = load_workflow_controls(api_url, path, graph)
                    result = feature_preflight(ComfyWorkflowCompiler(info), model, generation_payload,
                                               workflow=graph, workflow_controls=binding)
                    self._comfy_controls_emit({**event, "ok": True, "preflight": result})
                    return
                if graph is None:
                    raise WorkflowControlError("현재 앱 기본 워크플로입니다. API 설정에서 사용자 워크플로 파일을 선택하면 노드별 입력이 표시됩니다")
                schema = describe_controls(graph, info)
                if action == "comfy_controls_save":
                    binding = save_workflow_controls(api_url, path, graph, info, request.get("binding"))
                    self._comfy_controls_emit({**event, "ok": True, "schema": schema, "binding": controls_for_wire(binding, schema), "saved": True})
                else:
                    warning = ""
                    try:
                        binding = load_workflow_controls(api_url, path, graph)
                        if binding is not None:
                            binding = validate_controls(graph, info, binding)
                    except WorkflowControlError as exc:
                        binding, warning = None, str(exc)
                    self._comfy_controls_emit({**event, "ok": True, "schema": schema, "binding": controls_for_wire(binding, schema),
                                               "warning": warning, "mode": mode})
            except Exception as exc:
                self._comfy_controls_error(event, exc)
            finally:
                if getattr(self, "_comfy_controls_serial", None) == serial:
                    self._comfy_controls_busy = False

        threading.Thread(target=work, daemon=True, name="comfy-workflow-controls").start()
        return True

    def _comfy_controls_error(self, event, exc):
        if getattr(self, "_comfy_controls_closed", False):
            return
        from core.error_handler import handle_error, sanitize_for_ui
        try:
            handle_error("E030", "Comfy 워크플로 설정", exc, notify=False)
        except (UnicodeError, OSError):
            pass  # A legacy Windows console must not swallow the UI error.
        finally:
            self._comfy_controls_emit({**event, "error": sanitize_for_ui(str(exc), 700)})

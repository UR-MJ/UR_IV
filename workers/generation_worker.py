# workers/generation_worker.py
import base64
import copy
import json
import logging
import threading
import time
from contextlib import contextmanager

from PyQt6.QtCore import QThread, pyqtSignal

from backends import get_backend
from core.error_handler import sanitize_for_ui
from core.resource_coordinator import ResourceBusyError, get_generation_coordinator

logger = logging.getLogger(__name__)


class WebUIInfoWorker(QThread):
    """서버 정보 로드 워커"""
    info_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def run(self):
        """백엔드 API에서 모델, 샘플러 등 정보 가져오기"""
        try:
            backend = get_backend()
            info = backend.get_info()
            self.info_ready.emit({
                'models': info.models,
                'samplers': info.samplers,
                'schedulers': info.schedulers,
                'upscalers': info.upscalers,
                'options': info.options,
                'vae': info.vae,
                'checkpoints': info.checkpoints,
            })
        except Exception as e:
            logger.exception("WebUIInfoWorker failed")
            self.error_occurred.emit(sanitize_for_ui(e))


class _CancellableMixin:
    """QThread 생성 워커에 공통으로 쓰는 취소 플래그."""

    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        # 플래그만으론 이미 보낸 HTTP 요청이 끝까지 돈다 — 백엔드에 실제 중단 요청.
        # fire-and-forget: 메인 스레드를 막지 않고, 실패해도 무시.
        import threading

        def _do_interrupt():
            try:
                owned_interrupt = getattr(self, '_interrupt_owned_backend', None)
                if owned_interrupt:
                    owned_interrupt()
                else:
                    get_backend().interrupt()
            except Exception:
                logger.debug("backend interrupt 실패(무시)", exc_info=True)
        threading.Thread(target=_do_interrupt, daemon=True).start()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


def _run_postprocess_chain(backend, image_data: bytes, chain: list[dict],
                           *, cancelled_cb=None) -> tuple[bytes, list[str]]:
    """후처리 체인을 실행하되 한 단계 실패해도 이전 결과를 보존.

    Returns:
        (final_bytes, errors) — errors는 사람이 읽을 수 있는 실패 메시지 리스트.
    """
    if not chain:
        return image_data, []

    errors: list[str] = []
    last_good_b64 = base64.b64encode(image_data).decode("utf-8")
    current_b64 = last_good_b64

    for step in chain:
        if cancelled_cb and cancelled_cb():
            errors.append("후처리 취소됨")
            break
        step_type = step.get("type")
        settings = dict(step.get("settings", {}))
        try:
            if step_type == "adetailer":
                current_b64 = backend.adetailer(current_b64, settings)
            elif step_type == "sam3":
                current_b64 = backend.sam3(current_b64, settings)
            else:
                errors.append(f"알 수 없는 후처리 타입: {step_type}")
                continue
            last_good_b64 = current_b64  # 이 단계 성공 확정
        except Exception as e:
            logger.exception("postprocess step '%s' failed", step_type)
            errors.append(f"{step_type}: {sanitize_for_ui(e)}")
            # 실패 시 이전 성공 결과로 롤백하여 다음 단계는 그것을 기반으로 시도
            current_b64 = last_good_b64

    return base64.b64decode(last_good_b64), errors


class _GenerationDeferred(RuntimeError):
    """A queued snapshot could not be submitted; keep it for explicit resume."""


class GenerationFlowWorker(QThread, _CancellableMixin):
    """이미지 생성 워커"""
    finished = pyqtSignal(object, dict)
    progress = pyqtSignal(int, int, object)  # step, total_steps, preview_bytes|None

    def __init__(self, model_name: str, payload: dict, *, backend=None):
        QThread.__init__(self)
        _CancellableMixin.__init__(self)
        self.model_name = model_name
        self.payload = copy.deepcopy(payload)
        self._backend_snapshot = backend
        self._backend_lock = threading.RLock()
        self._owned_backend = None
        self._start_time: float | None = None
        self._result_emitted = False

    def _emit_result(self, result, info):
        info = dict(info or {})
        xyz_info = self.payload.get("_xyz_info")
        if isinstance(xyz_info, dict):
            info["_xyz_info"] = copy.deepcopy(xyz_info)
        self._result_emitted = True
        self.finished.emit(result, info)

    # 기존 호출부 호환용 static wrapper
    @staticmethod
    def _run_postprocess_chain(backend, image_data: bytes, chain: list[dict]) -> bytes:
        final, _errors = _run_postprocess_chain(backend, image_data, chain)
        return final

    def _interrupt_owned_backend(self):
        # Hold only this worker's lease lock, never a GUI lock, during HTTP.
        with self._backend_lock:
            if self._owned_backend is not None:
                self._owned_backend.interrupt()

    @contextmanager
    def _backend_lease(self, backend):
        with get_generation_coordinator().reserve("txt2img", unload_llm=False, timeout=0):
            with self._backend_lock:
                if self._backend_snapshot is not None and get_backend() is not self._backend_snapshot:
                    raise _GenerationDeferred("XYZ 작업의 백엔드가 변경되었습니다. 원래 백엔드를 선택하고 대기열을 재개하세요.")
                self._owned_backend = backend
            try:
                yield
            finally:
                with self._backend_lock:
                    self._owned_backend = None

    def run(self):
        self._start_time = time.monotonic()
        dispatched = False
        try:
            backend = self._backend_snapshot if self._backend_snapshot is not None else get_backend()
            payload = dict(self.payload)
            if "_chat_deferred_prompt" in payload:
                from core.chat_generation import prepare_prompt_payload
                payload = prepare_prompt_payload(payload)
            xyz_info = payload.pop("_xyz_info", None)
            postprocess_chain = list(payload.pop("_postprocess_chain", []) or [])
            generation_family = str(payload.pop("_generation_family", "standard") or "standard").lower()

            def on_progress(step: int, total: int, preview):
                if self.is_cancelled:
                    return
                self.progress.emit(step, total, preview)

            if self.is_cancelled:
                self._emit_result("생성 취소됨", {'cancelled': True})
                return

            with self._backend_lease(backend):
                if self.is_cancelled:
                    self._emit_result("생성 취소됨", {'cancelled': True})
                    return
                dispatched = True
                if generation_family == "krea2":
                    from core.krea2_generation import run_krea2_generation

                    # Forge-specific post-process steps are not part of the Krea
                    # Comfy graph contract and must not leak into this branch.
                    postprocess_chain = []
                    result = run_krea2_generation(
                        backend, "t2i", payload, progress_callback=on_progress,
                    )
                else:
                    result = backend.txt2img(
                        self.model_name, payload, progress_callback=on_progress,
                    )

                # 취소 후 도착한 결과(interrupt의 부분 이미지 포함)는 성공으로 emit하지 않음
                # — 디스크 저장/히스토리/성공 통계/자동화 계속으로 이어지던 버그 방지
                if self.is_cancelled:
                    self._emit_result("생성 취소됨", {'cancelled': True})
                    return

                if not result.success:
                    self._emit_result(result.error, {})
                    return

                final_image, pp_errors = _run_postprocess_chain(
                    backend, result.image_data, postprocess_chain,
                    cancelled_cb=lambda: self.is_cancelled,
                )
            if self.is_cancelled:
                self._emit_result("생성 취소됨", {'cancelled': True})
                return
            info = dict(result.info or {})
            if xyz_info:
                info['_xyz_info'] = xyz_info
            if pp_errors:
                info['postprocess_errors'] = pp_errors
            self._emit_result(final_image, info)

        except Exception as e:
            if self.is_cancelled:
                # interrupt로 인한 요청 중단 예외는 '취소'로 보고
                self._emit_result("생성 취소됨", {'cancelled': True})
                return
            if (self._backend_snapshot is not None and not dispatched
                    and isinstance(e, (_GenerationDeferred, ResourceBusyError))):
                self._emit_result(sanitize_for_ui(e), {'_queue_deferred': True})
                return
            logger.exception("GenerationFlowWorker failed")
            self._emit_result(f"이미지 생성 중 오류: {sanitize_for_ui(e)}", {})


class Img2ImgFlowWorker(QThread, _CancellableMixin):
    """img2img / inpaint 생성 워커"""
    finished = pyqtSignal(object, dict)
    progress = pyqtSignal(int, int, object)

    def __init__(self, model_name: str, payload: dict):
        QThread.__init__(self)
        _CancellableMixin.__init__(self)
        self.model_name = model_name
        self.payload = payload

    def run(self):
        try:
            backend = get_backend()
            payload = dict(self.payload)
            postprocess_chain = list(payload.pop("_postprocess_chain", []) or [])
            generation_family = str(payload.pop("_generation_family", "standard") or "standard").lower()

            def on_progress(step: int, total: int, preview):
                if self.is_cancelled:
                    return
                self.progress.emit(step, total, preview)

            if self.is_cancelled:
                self.finished.emit("생성 취소됨", {'cancelled': True})
                return

            with get_generation_coordinator().reserve(
                "img2img", unload_llm=False, timeout=0
            ):
                if generation_family == "krea2":
                    from core.krea2_generation import run_krea2_generation

                    postprocess_chain = []
                    result = run_krea2_generation(
                        backend, "i2i", payload, progress_callback=on_progress,
                    )
                else:
                    result = backend.img2img(
                        self.model_name, payload, progress_callback=on_progress,
                    )

                if self.is_cancelled:
                    self.finished.emit("생성 취소됨", {'cancelled': True})
                    return

                if not result.success:
                    self.finished.emit(result.error, {})
                    return

                final_image, pp_errors = _run_postprocess_chain(
                    backend, result.image_data, postprocess_chain,
                    cancelled_cb=lambda: self.is_cancelled,
                )
            if self.is_cancelled:
                self.finished.emit("생성 취소됨", {'cancelled': True})
                return
            info = dict(result.info or {})
            if pp_errors:
                info['postprocess_errors'] = pp_errors
            self.finished.emit(final_image, info)

        except Exception as e:
            if self.is_cancelled:
                self.finished.emit("생성 취소됨", {'cancelled': True})
                return
            logger.exception("Img2ImgFlowWorker failed")
            self.finished.emit(f"img2img 생성 중 오류: {sanitize_for_ui(e)}", {})

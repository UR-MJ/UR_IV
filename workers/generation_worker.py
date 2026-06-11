# workers/generation_worker.py
import base64
import json
import logging
import time

from PyQt6.QtCore import QThread, pyqtSignal

from backends import get_backend
from core.error_handler import sanitize_for_ui

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


class GenerationFlowWorker(QThread, _CancellableMixin):
    """이미지 생성 워커"""
    finished = pyqtSignal(object, dict)
    progress = pyqtSignal(int, int, object)  # step, total_steps, preview_bytes|None

    def __init__(self, model_name: str, payload: dict):
        QThread.__init__(self)
        _CancellableMixin.__init__(self)
        self.model_name = model_name
        self.payload = payload
        self._start_time: float | None = None

    # 기존 호출부 호환용 static wrapper
    @staticmethod
    def _run_postprocess_chain(backend, image_data: bytes, chain: list[dict]) -> bytes:
        final, _errors = _run_postprocess_chain(backend, image_data, chain)
        return final

    def run(self):
        self._start_time = time.monotonic()
        try:
            backend = get_backend()
            payload = dict(self.payload)
            postprocess_chain = list(payload.pop("_postprocess_chain", []) or [])

            def on_progress(step: int, total: int, preview):
                if self.is_cancelled:
                    return
                self.progress.emit(step, total, preview)

            if self.is_cancelled:
                self.finished.emit("생성 취소됨", {'cancelled': True})
                return

            result = backend.txt2img(self.model_name, payload, progress_callback=on_progress)

            # 취소 후 도착한 결과(interrupt의 부분 이미지 포함)는 성공으로 emit하지 않음
            # — 디스크 저장/히스토리/성공 통계/자동화 계속으로 이어지던 버그 방지
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
                # interrupt로 인한 요청 중단 예외는 '취소'로 보고
                self.finished.emit("생성 취소됨", {'cancelled': True})
                return
            logger.exception("GenerationFlowWorker failed")
            self.finished.emit(f"이미지 생성 중 오류: {sanitize_for_ui(e)}", {})


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

            def on_progress(step: int, total: int, preview):
                if self.is_cancelled:
                    return
                self.progress.emit(step, total, preview)

            if self.is_cancelled:
                self.finished.emit("생성 취소됨", {'cancelled': True})
                return

            result = backend.img2img(self.model_name, payload, progress_callback=on_progress)

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

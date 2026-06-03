"""
AutomationController — 자동 생성 루프 제어.

NAIA 2.0의 ``modules/automation_module.py`` 패턴 참고.

기능
----
- 4가지 모드:
  + ``COUNT``      : N번 실행 후 종료
  + ``TIMER``      : X분 동안 실행 후 종료
  + ``UNLIMITED``  : 사용자가 중단할 때까지 무한
  + ``CONDITIONAL``: 사용자 콜백이 False 반환할 때까지
- 반복 간격 (delay) — 카운트다운 이벤트 발행으로 UI 표시 가능
- 재시도 (실패 시 최대 N회)
- 일시정지 / 재개 / 중단
- AppContext 이벤트 발행 (외부에서 Vue로 전달 등)

설계
----
- ``threading.Thread`` 기반 (Qt 비의존 → 테스트 용이).
- UR_IV의 QWebChannel 시그널과는 AppContext 이벤트로 간접 연결.
- 한 인스턴스 = 한 자동화 세션. 동시 여러 개 가능.

사용 예
-------
>>> def my_generate():
...     # 실제 생성 함수
...     return True  # or raise
>>>
>>> ctrl = AutomationController(generate_fn=my_generate)
>>> ctrl.configure(mode=AutomationMode.COUNT, limit=10, delay=2.0, max_retries=3)
>>> ctrl.start()
>>> # ... 다른 곳에서
>>> ctrl.pause()
>>> ctrl.resume()
>>> ctrl.stop()
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from utils.app_logger import get_logger

_logger = get_logger("automation")


class AutomationMode(Enum):
    COUNT = "count"
    TIMER = "timer"
    UNLIMITED = "unlimited"
    CONDITIONAL = "conditional"


class AutomationState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    FINISHED = "finished"
    FAILED = "failed"


class AutomationEvents:
    """AppContext에 발행되는 이벤트 이름."""
    STARTED = "automation_started"          # data: {mode, limit, delay}
    ITERATION_BEGIN = "automation_iter_begin"  # data: {iter, total_or_none}
    ITERATION_END = "automation_iter_end"      # data: {iter, success, retries}
    COUNTDOWN_TICK = "automation_countdown"    # data: {remaining_seconds, iter}
    PAUSED = "automation_paused"
    RESUMED = "automation_resumed"
    STOPPED = "automation_stopped"             # data: {reason, completed}
    FAILED = "automation_failed"               # data: {error, iter}


@dataclass
class AutomationConfig:
    mode: AutomationMode = AutomationMode.COUNT
    limit: int = 10                 # COUNT일 때 반복 횟수
    timer_seconds: float = 600.0    # TIMER일 때 총 실행 시간 (초)
    delay: float = 1.0              # 반복 간 대기 (초)
    max_retries: int = 3            # 실패 시 재시도 횟수
    stop_on_failure: bool = False   # True면 max_retries 초과 시 전체 중단
    # 0이면 비활성. N이면 매 N회 generation 후 backend cleanup_models 호출
    # (Forge API의 LoRA patches 누적 문제 회피용)
    cleanup_every_n: int = 0
    # CONDITIONAL일 때: 매 반복 전 호출, False 반환 시 종료
    continue_predicate: Optional[Callable[[], bool]] = None


@dataclass
class AutomationStats:
    completed: int = 0
    failed: int = 0
    total_retries: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    def elapsed(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time if self.start_time else 0.0


class AutomationController:
    """자동 생성 루프 컨트롤러.

    스레드 안전. ``start()`` → 백그라운드 스레드에서 루프 실행.
    """

    def __init__(self,
                 generate_fn: Callable[[], Any],
                 config: Optional[AutomationConfig] = None,
                 publish_events: bool = True):
        """
        :param generate_fn: 실제 생성을 수행하는 함수. 성공 시 임의 값 반환,
                            실패 시 예외 발생. 예외는 재시도 트리거.
        :param config: 설정. None이면 기본값 사용.
        :param publish_events: True면 AppContext에 자동화 이벤트 발행.
        """
        self.generate_fn = generate_fn
        self.config = config or AutomationConfig()
        self.publish_events = publish_events
        self.stats = AutomationStats()

        self._state = AutomationState.IDLE
        self._thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # 시작 시 unpaused
        self._stop_event = threading.Event()
        self._state_lock = threading.RLock()

    # ────────────────────────────────────────
    # 설정 / 상태
    # ────────────────────────────────────────

    def configure(self, **kwargs: Any) -> None:
        """설정 변경 — 실행 중에는 다음 반복부터 적용."""
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
            else:
                # Mode value로도 받기
                if k == "mode" and isinstance(v, str):
                    self.config.mode = AutomationMode(v)

    @property
    def state(self) -> AutomationState:
        with self._state_lock:
            return self._state

    def is_running(self) -> bool:
        return self.state in (AutomationState.RUNNING, AutomationState.PAUSED)

    # ────────────────────────────────────────
    # 제어
    # ────────────────────────────────────────

    def start(self) -> bool:
        """루프 시작. 이미 실행 중이면 False."""
        with self._state_lock:
            if self.is_running():
                return False
            self._state = AutomationState.RUNNING
            self.stats = AutomationStats(start_time=time.time())
            self._pause_event.set()
            self._stop_event.clear()

        self._thread = threading.Thread(target=self._loop, daemon=True, name="AutomationLoop")
        self._thread.start()
        self._publish(AutomationEvents.STARTED, {
            "mode": self.config.mode.value,
            "limit": self.config.limit,
            "delay": self.config.delay,
        })
        return True

    def pause(self) -> bool:
        with self._state_lock:
            if self._state != AutomationState.RUNNING:
                return False
            self._state = AutomationState.PAUSED
            self._pause_event.clear()
        self._publish(AutomationEvents.PAUSED, None)
        return True

    def resume(self) -> bool:
        with self._state_lock:
            if self._state != AutomationState.PAUSED:
                return False
            self._state = AutomationState.RUNNING
            self._pause_event.set()
        self._publish(AutomationEvents.RESUMED, None)
        return True

    def stop(self, wait: bool = False, timeout: float = 5.0) -> bool:
        """루프 중단 요청. ``wait=True``면 스레드 종료까지 대기."""
        with self._state_lock:
            if self._state in (AutomationState.IDLE, AutomationState.FINISHED, AutomationState.FAILED):
                return False
            self._state = AutomationState.STOPPING
            self._pause_event.set()  # paused면 깨우기
            self._stop_event.set()
        if wait and self._thread is not None:
            self._thread.join(timeout=timeout)
        return True

    def wait(self, timeout: Optional[float] = None) -> bool:
        """루프 종료까지 대기. timeout 초과 시 False."""
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    # ────────────────────────────────────────
    # 루프 본체
    # ────────────────────────────────────────

    def _loop(self) -> None:
        cfg = self.config
        iteration = 0

        try:
            while True:
                # 종료 조건
                if self._stop_event.is_set():
                    self._finish(reason="stopped")
                    return

                # CONDITIONAL: predicate False면 종료
                if cfg.mode == AutomationMode.CONDITIONAL:
                    pred = cfg.continue_predicate
                    if pred is not None and not pred():
                        self._finish(reason="predicate_false")
                        return

                # COUNT: limit 도달
                if cfg.mode == AutomationMode.COUNT and self.stats.completed >= cfg.limit:
                    self._finish(reason="count_reached")
                    return

                # TIMER: 시간 초과
                if cfg.mode == AutomationMode.TIMER and self.stats.elapsed() >= cfg.timer_seconds:
                    self._finish(reason="timer_expired")
                    return

                iteration += 1
                self._publish(AutomationEvents.ITERATION_BEGIN, {
                    "iter": iteration,
                    "total": cfg.limit if cfg.mode == AutomationMode.COUNT else None,
                })

                # 일시정지 대기 (stop 신호 오면 빠져나옴)
                while not self._pause_event.wait(timeout=0.2):
                    if self._stop_event.is_set():
                        self._finish(reason="stopped")
                        return

                # 생성 + 재시도
                success = self._run_one_with_retry(iteration)
                if success:
                    self.stats.completed += 1
                else:
                    self.stats.failed += 1
                    if cfg.stop_on_failure:
                        self._finish(reason="failure")
                        return

                self._publish(AutomationEvents.ITERATION_END, {
                    "iter": iteration,
                    "success": success,
                })

                # 정기 cleanup — N회마다 backend LoRA patches 정리
                # OOM 발생 전에 예방 (Forge API 호출 누적 회피)
                if cfg.cleanup_every_n > 0 and iteration % cfg.cleanup_every_n == 0:
                    try:
                        from core.app_context import get_context
                        backend = get_context().get_service('backend')
                        if backend and hasattr(backend, 'cleanup_models'):
                            _logger.info(f"iter {iteration}: 정기 cleanup (매 {cfg.cleanup_every_n}회)")
                            backend.cleanup_models(full_reload=False)  # 빠른 cleanup
                    except Exception as ce:
                        _logger.debug(f"periodic cleanup failed: {ce}")

                # 카운트다운 (delay)
                if cfg.delay > 0:
                    if not self._countdown(cfg.delay, iteration):
                        self._finish(reason="stopped")
                        return

        except Exception as e:
            _logger.exception("automation loop crashed")
            with self._state_lock:
                self._state = AutomationState.FAILED
            self.stats.end_time = time.time()
            self._publish(AutomationEvents.FAILED, {"error": str(e), "iter": iteration})

    def _run_one_with_retry(self, iteration: int) -> bool:
        cfg = self.config
        attempts = 0
        last_err: Optional[Exception] = None
        while attempts <= cfg.max_retries:
            if self._stop_event.is_set():
                return False
            try:
                self.generate_fn()
                return True
            except Exception as e:
                last_err = e
                attempts += 1
                self.stats.total_retries += 1
                _logger.warning(f"iter {iteration} attempt {attempts} failed: {e}")
                # OOM 회복 시도 — 재시도 전에 CUDA 캐시 + Python GC + backend LoRA cleanup
                # 같은 메모리 상태로 재시도하면 또 OOM이라 무의미
                err_str = str(e).lower()
                is_oom = ('out of memory' in err_str or 'cuda' in err_str
                          or 'allocation' in err_str)
                if is_oom:
                    _logger.warning(f"iter {iteration}: OOM 감지 → CUDA 캐시 + GC + backend cleanup")
                    try:
                        import gc
                        gc.collect()
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                            torch.cuda.synchronize()
                    except Exception:
                        pass
                    # backend에 LoRA patches 정리 요청 — Forge API 호출 누적 문제 회피
                    try:
                        from core.app_context import get_context
                        backend = get_context().get_service('backend')
                        if backend and hasattr(backend, 'cleanup_models'):
                            _logger.warning(f"iter {iteration}: backend cleanup (full reload)")
                            backend.cleanup_models(full_reload=True)
                    except Exception as ce:
                        _logger.warning(f"backend cleanup failed: {ce}")
                if attempts <= cfg.max_retries:
                    # OOM은 더 오래 쉬고 (메모리 회복 시간), 일반 에러는 짧게
                    wait = min(2.0 ** attempts, 30.0)
                    if is_oom:
                        wait = max(wait, 5.0)  # OOM은 최소 5초
                    time.sleep(wait)
        if last_err is not None:
            _logger.error(f"iter {iteration} failed after {cfg.max_retries} retries")
        return False

    def _countdown(self, total_seconds: float, iteration: int) -> bool:
        """0.5초 단위로 카운트다운 이벤트 발행. 중단/일시정지 응답.

        :return: 정상 완료 True, 중단됨 False
        """
        end_at = time.time() + total_seconds
        last_tick = -1
        while True:
            if self._stop_event.is_set():
                return False
            # 일시정지면 카운트다운 멈춤 (end_at도 연장)
            if not self._pause_event.is_set():
                # paused — 풀릴 때까지 대기
                pause_started = time.time()
                self._pause_event.wait(timeout=0.5)
                end_at += time.time() - pause_started
                continue

            remaining = end_at - time.time()
            if remaining <= 0:
                return True
            tick = int(remaining)
            if tick != last_tick:
                self._publish(AutomationEvents.COUNTDOWN_TICK, {
                    "remaining_seconds": tick,
                    "iter": iteration,
                })
                last_tick = tick
            # 0.2초 단위로 깨어남
            time.sleep(0.2)

    def _finish(self, reason: str) -> None:
        with self._state_lock:
            self._state = AutomationState.FINISHED
        self.stats.end_time = time.time()
        self._publish(AutomationEvents.STOPPED, {
            "reason": reason,
            "completed": self.stats.completed,
            "failed": self.stats.failed,
            "elapsed": self.stats.elapsed(),
        })

    # ────────────────────────────────────────
    # 이벤트
    # ────────────────────────────────────────

    def _publish(self, event: str, data: Any) -> None:
        if not self.publish_events:
            return
        try:
            from core.app_context import get_context
            get_context().publish(event, data)
        except Exception:
            pass

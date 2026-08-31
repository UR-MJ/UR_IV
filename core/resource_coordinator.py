"""Serialize heavyweight generation and coordinate owned GPU resources."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock, RLock
from typing import Callable, Iterator, Optional
import time


class ResourceBusyError(RuntimeError):
    """Another Creator job currently owns the GPU generation lease."""


class ResourceTransitionError(RuntimeError):
    """An owned resource could not be moved to the required state."""


@dataclass(frozen=True)
class ResourceState:
    phase: str
    owner: str = ""
    llm_unloaded: bool = False
    since: float = 0.0


class GenerationResourceCoordinator:
    """Own a single generation lease and optional LLM lifecycle hooks.

    External Forge/Comfy processes are intentionally outside this interface.
    Only hooks explicitly supplied by the application are invoked, preventing
    the coordinator from killing a process it does not own.
    """

    def __init__(
        self,
        unload_llm: Optional[Callable[[], bool]] = None,
        restore_llm: Optional[Callable[[], bool]] = None,
        on_state: Optional[Callable[[ResourceState], None]] = None,
    ) -> None:
        self._lease = Lock()
        self._state_lock = RLock()
        self._unload_llm = unload_llm
        self._restore_llm = restore_llm
        self._on_state = on_state
        self._state = ResourceState("idle", since=time.time())

    def configure(
        self,
        *,
        unload_llm: Optional[Callable[[], bool]] = None,
        restore_llm: Optional[Callable[[], bool]] = None,
        on_state: Optional[Callable[[ResourceState], None]] = None,
    ) -> None:
        """Attach application hooks without replacing the shared lease.

        The first ordinary generation may happen before Creator Studio opens.
        Late configuration therefore updates lifecycle callbacks while keeping
        the exact same lock and state object used by every generation path.
        """

        with self._state_lock:
            if unload_llm is not None:
                self._unload_llm = unload_llm
            if restore_llm is not None:
                self._restore_llm = restore_llm
            if on_state is not None:
                self._on_state = on_state

    @property
    def state(self) -> ResourceState:
        with self._state_lock:
            return self._state

    @contextmanager
    def reserve(
        self,
        owner: str,
        *,
        unload_llm: bool = True,
        restore_llm: bool = False,
        timeout: float = 0.0,
    ) -> Iterator[ResourceState]:
        owner = str(owner or "creator")[:120]
        acquired = self._lease.acquire(timeout=max(0.0, float(timeout)))
        if not acquired:
            raise ResourceBusyError("다른 생성 작업이 GPU 리소스를 사용 중입니다")

        did_unload = False
        try:
            self._set_state("preparing", owner, False)
            if unload_llm and self._unload_llm is not None:
                did_unload = bool(self._unload_llm())
                if not did_unload:
                    raise ResourceTransitionError("Ollama 모델 언로드를 확인하지 못했습니다")
            running = self._set_state("running", owner, did_unload)
            yield running
        finally:
            self._set_state("releasing", owner, did_unload)
            if did_unload and restore_llm and self._restore_llm is not None:
                try:
                    self._restore_llm()
                except Exception:
                    # A failed warm-up must never strand the generation lease.
                    pass
            self._set_state("idle", "", False)
            self._lease.release()

    def _set_state(self, phase: str, owner: str, llm_unloaded: bool) -> ResourceState:
        state = ResourceState(phase, owner, llm_unloaded, time.time())
        with self._state_lock:
            self._state = state
        if self._on_state is not None:
            try:
                self._on_state(state)
            except Exception:
                pass
        return state


_SHARED_GENERATION_COORDINATOR = GenerationResourceCoordinator()


def get_generation_coordinator(
    *,
    unload_llm: Optional[Callable[[], bool]] = None,
    restore_llm: Optional[Callable[[], bool]] = None,
    on_state: Optional[Callable[[ResourceState], None]] = None,
) -> GenerationResourceCoordinator:
    """Return the process-wide GPU generation lease and optionally configure it."""

    _SHARED_GENERATION_COORDINATOR.configure(
        unload_llm=unload_llm,
        restore_llm=restore_llm,
        on_state=on_state,
    )
    return _SHARED_GENERATION_COORDINATOR

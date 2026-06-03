"""
AppContext — 전역 이벤트 버스 + 서비스 로케이터.

목적
----
UR_IV의 Python 측 모듈들이 직접 서로를 호출하는 결합을 끊기 위한 중앙 허브.
Vue↔Python QWebChannel 시그널과 별개로, **Python 내부** 모듈 간 통신 표준.

설계 원칙
---------
- 싱글톤 (프로세스당 1개). ``get_context()`` 또는 ``AppContext.get()``로 접근.
- 스레드 안전 (``threading.RLock``).
- 구독자 예외는 격리되며 다른 구독자 호출을 막지 않음.
- 콜백이 ``publish()``를 호출해도 데드락 없음 (lock 밖에서 디스패치).
- 구독은 정수 handle 반환 → ``unsubscribe(event, handle)``로 해제.

사용 예
-------
>>> from core.app_context import get_context, Events
>>> ctx = get_context()
>>> h = ctx.subscribe(Events.BACKEND_CHANGED, lambda m: print(m))
>>> ctx.publish(Events.BACKEND_CHANGED, "comfyui")
>>> ctx.unsubscribe(Events.BACKEND_CHANGED, h)

서비스 로케이터 사용 예
-----------------------
>>> ctx.register_service("generator", my_generator)
>>> gen = ctx.get_service("generator")
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from utils.app_logger import get_logger

_logger = get_logger("app_context")


class Events:
    """표준 이벤트 이름 상수. 새 이벤트 추가 시 여기에 등록 권장."""

    # 백엔드 / 모드
    BACKEND_CHANGED = "backend_changed"          # data: BackendType
    BACKEND_URL_CHANGED = "backend_url_changed"  # data: str (url)

    # 생성 흐름
    GENERATION_STARTED = "generation_started"    # data: payload dict
    GENERATION_PROGRESS = "generation_progress"  # data: {step, total}
    GENERATION_FINISHED = "generation_finished"  # data: {image_data, info}
    GENERATION_FAILED = "generation_failed"      # data: error str

    # 프롬프트 파이프라인
    PROMPT_GENERATED = "prompt_generated"        # data: final prompt str
    PROMPT_CONTEXT_READY = "prompt_context_ready"  # data: PromptContext

    # 큐
    QUEUE_UPDATED = "queue_updated"              # data: queue list
    QUEUE_ITEM_ADDED = "queue_item_added"        # data: item dict
    QUEUE_ITEM_COMPLETED = "queue_item_completed"  # data: item dict

    # 시스템
    SAVE_DIRECTORY_CHANGED = "save_directory_changed"  # data: new dir str
    VRAM_UPDATED = "vram_updated"                # data: {used, total, free}
    SETTINGS_LOADED = "settings_loaded"          # data: dict
    SETTINGS_SAVED = "settings_saved"            # data: dict


class _Subscription:
    """내부 구독 레코드."""
    __slots__ = ("handle", "callback", "event")

    def __init__(self, handle: int, callback: Callable[[Any], None], event: str):
        self.handle = handle
        self.callback = callback
        self.event = event


class AppContext:
    """프로세스 전역 컨텍스트.

    스레드 안전. 콜백 예외는 로그만 남기고 흘려보낸다.
    """

    _instance: Optional["AppContext"] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get(cls) -> "AppContext":
        """싱글톤 인스턴스 반환."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        # event_name -> list[_Subscription]
        self._subs: dict[str, list[_Subscription]] = {}
        # 서비스 이름 -> 인스턴스
        self._services: dict[str, Any] = {}
        # 핸들 카운터 (단조 증가)
        self._next_handle = 1
        # 모든 mutating 연산 보호
        self._lock = threading.RLock()

    # ────────────────────────────────────────────────────────
    # 이벤트 버스
    # ────────────────────────────────────────────────────────

    def subscribe(self, event: str, callback: Callable[[Any], None]) -> int:
        """이벤트 구독. 정수 handle 반환 → unsubscribe에 사용."""
        if not callable(callback):
            raise TypeError(f"callback must be callable, got {type(callback).__name__}")
        with self._lock:
            handle = self._next_handle
            self._next_handle += 1
            self._subs.setdefault(event, []).append(
                _Subscription(handle, callback, event)
            )
            return handle

    def unsubscribe(self, event: str, handle: int) -> bool:
        """handle로 구독 해제. 성공 시 True."""
        with self._lock:
            subs = self._subs.get(event)
            if not subs:
                return False
            new_subs = [s for s in subs if s.handle != handle]
            if len(new_subs) == len(subs):
                return False
            if new_subs:
                self._subs[event] = new_subs
            else:
                # 빈 리스트 정리
                self._subs.pop(event, None)
            return True

    def unsubscribe_all(self, event: str) -> int:
        """이벤트의 모든 구독 해제. 해제된 개수 반환."""
        with self._lock:
            subs = self._subs.pop(event, [])
            return len(subs)

    def publish(self, event: str, data: Any = None) -> int:
        """이벤트 발행 — 모든 구독자 동기 호출. 성공 호출 개수 반환.

        주의:
        - lock 밖에서 콜백 디스패치 → 콜백 내부에서 publish/subscribe 안전.
        - 각 콜백 예외는 격리 (다른 콜백 호출 안 막음).
        - 호출 순서는 구독 등록 순서.
        """
        with self._lock:
            subs_snapshot = list(self._subs.get(event, []))

        delivered = 0
        for sub in subs_snapshot:
            try:
                sub.callback(data)
                delivered += 1
            except Exception:
                _logger.exception(
                    f"subscriber #{sub.handle} for '{event}' raised — continuing"
                )
        return delivered

    def subscriber_count(self, event: str) -> int:
        with self._lock:
            return len(self._subs.get(event, []))

    # ────────────────────────────────────────────────────────
    # 서비스 로케이터
    # ────────────────────────────────────────────────────────

    def register_service(self, name: str, instance: Any) -> None:
        """이름으로 서비스 등록. 동일 이름 재등록 시 덮어씀."""
        with self._lock:
            self._services[name] = instance

    def get_service(self, name: str, default: Any = None) -> Any:
        """이름으로 서비스 조회. 없으면 default."""
        with self._lock:
            return self._services.get(name, default)

    def has_service(self, name: str) -> bool:
        with self._lock:
            return name in self._services

    def remove_service(self, name: str) -> bool:
        with self._lock:
            return self._services.pop(name, None) is not None

    # ────────────────────────────────────────────────────────
    # 유틸
    # ────────────────────────────────────────────────────────

    def clear(self) -> None:
        """모든 구독자/서비스 제거 — 테스트용."""
        with self._lock:
            self._subs.clear()
            self._services.clear()
            self._next_handle = 1


def get_context() -> AppContext:
    """편의 함수 — AppContext 싱글톤 반환."""
    return AppContext.get()

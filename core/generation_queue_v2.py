"""
GenerationQueue v2 — 우선순위 기반 생성 작업 큐.

NAIA 2.0의 ``core/generation_queue_manager.py`` 패턴 참고.
UR_IV의 기존 Queue 패널(widgets/queue_panel.py)을 대체/강화하려는 목적.

기능
----
- 우선순위 (낮을수록 먼저 — heapq 기반)
- 작업 상태: ``PENDING / RUNNING / DONE / FAILED / CANCELLED``
- pause / resume (큐 전체)
- cancel (개별 작업 — RUNNING이면 마크만, PENDING이면 즉시 제거)
- snapshot / restore (JSON 직렬화)
- AppContext 이벤트 발행

설계
----
- 단일 워커 스레드가 큐를 비움 (생성 자체는 순차 — Forge 모델 reload 충돌 회피).
- 동시 실행이 필요하면 여러 QueueWorker 인스턴스 사용.
- 작업 페이로드는 임의 dict — 호출자가 정의.
"""
from __future__ import annotations

import heapq
import itertools
import json
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from utils.app_logger import get_logger

_logger = get_logger("queue_v2")


class QueueItemStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueEvents:
    ITEM_ADDED = "queue_item_added"
    ITEM_STARTED = "queue_item_started"
    ITEM_FINISHED = "queue_item_finished"     # data: item (success)
    ITEM_FAILED = "queue_item_failed"          # data: item + error
    ITEM_CANCELLED = "queue_item_cancelled"
    QUEUE_PAUSED = "queue_paused"
    QUEUE_RESUMED = "queue_resumed"
    QUEUE_EMPTY = "queue_empty"
    QUEUE_UPDATED = "queue_updated"            # data: snapshot list


@dataclass
class QueueItem:
    """큐 작업 단위. ``payload``는 호출자 정의 임의 데이터."""
    id: int = 0
    priority: int = 100       # 낮을수록 먼저
    label: str = ""           # UI 표시용
    payload: dict = field(default_factory=dict)
    status: QueueItemStatus = QueueItemStatus.PENDING
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str = ""
    retries: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "QueueItem":
        d = dict(d)
        if isinstance(d.get("status"), str):
            d["status"] = QueueItemStatus(d["status"])
        return cls(**d)


class GenerationQueueV2:
    """우선순위 큐 + 단일 워커 스레드.

    사용:
    >>> def my_processor(payload: dict) -> None:
    ...     # 실제 생성 호출
    ...     ...
    >>> q = GenerationQueueV2(processor=my_processor)
    >>> q.start()
    >>> q.enqueue(payload={"prompt": "1girl"}, priority=10, label="job 1")
    >>> q.pause(); q.resume(); q.stop()
    """

    def __init__(self,
                 processor: Callable[[dict], Any],
                 publish_events: bool = True):
        self.processor = processor
        self.publish_events = publish_events

        # heap: list of (priority, seq, item) — seq로 안정 정렬
        self._heap: list[tuple[int, int, QueueItem]] = []
        # 빠른 검색을 위한 id→item 매핑 (히스토리 포함)
        self._index: dict[int, QueueItem] = {}
        self._seq_counter = itertools.count()
        self._id_counter = itertools.count(1)

        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # unpaused

        self._worker: Optional[threading.Thread] = None
        self._current_item: Optional[QueueItem] = None

    # ────────────────────────────────────────
    # 조회
    # ────────────────────────────────────────

    def pending_items(self) -> list[QueueItem]:
        """대기 중인 작업 — 우선순위 순. (참조 복사)"""
        with self._lock:
            sorted_heap = sorted(self._heap, key=lambda t: (t[0], t[1]))
            return [t[2] for t in sorted_heap]

    def all_items(self) -> list[QueueItem]:
        """완료/실패 포함 모든 작업 — 생성 순."""
        with self._lock:
            return sorted(self._index.values(), key=lambda i: i.id)

    def current(self) -> Optional[QueueItem]:
        with self._lock:
            return self._current_item

    def size(self) -> int:
        with self._lock:
            return len(self._heap)

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    # ────────────────────────────────────────
    # 작업 추가/제거
    # ────────────────────────────────────────

    def enqueue(self,
                payload: dict,
                priority: int = 100,
                label: str = "") -> QueueItem:
        item = QueueItem(
            id=next(self._id_counter),
            priority=priority,
            label=label or f"item-{priority}",
            payload=dict(payload),
            created_at=time.time(),
        )
        with self._lock:
            heapq.heappush(self._heap, (priority, next(self._seq_counter), item))
            self._index[item.id] = item
        self._wake.set()
        self._publish(QueueEvents.ITEM_ADDED, item.to_dict())
        self._publish_snapshot()
        return item

    def cancel(self, item_id: int) -> bool:
        """작업 취소. RUNNING이면 status만 마크 (워커가 끝낸 후 정리)."""
        with self._lock:
            item = self._index.get(item_id)
            if item is None:
                return False
            if item.status == QueueItemStatus.PENDING:
                # heap에서 제거 (lazy delete — heappush 비용 피함)
                self._heap = [t for t in self._heap if t[2].id != item_id]
                heapq.heapify(self._heap)
                item.status = QueueItemStatus.CANCELLED
                item.finished_at = time.time()
                self._publish(QueueEvents.ITEM_CANCELLED, item.to_dict())
                self._publish_snapshot()
                return True
            if item.status == QueueItemStatus.RUNNING:
                # 워커는 우리가 못 끊음 — 플래그만 세움 (processor가 자율 확인)
                item.status = QueueItemStatus.CANCELLED
                self._publish(QueueEvents.ITEM_CANCELLED, item.to_dict())
                return True
            return False

    def clear_pending(self) -> int:
        """대기 중 작업 모두 취소. 취소된 개수 반환."""
        with self._lock:
            count = 0
            for _, _, item in self._heap:
                item.status = QueueItemStatus.CANCELLED
                item.finished_at = time.time()
                count += 1
            self._heap.clear()
        self._publish_snapshot()
        return count

    # ────────────────────────────────────────
    # 실행 제어
    # ────────────────────────────────────────

    def start(self) -> bool:
        """워커 시작. pause()를 start() 전에 호출한 경우 일시정지 상태로 시작."""
        with self._lock:
            if self.is_running():
                return False
            self._stop_event.clear()
            # _pause_event는 의도적으로 건드리지 않음:
            # - 새 인스턴스는 __init__에서 set() 상태 (정상 시작)
            # - 사용자가 start() 전에 pause() 호출한 경우 clear 상태 유지 (paused로 시작)
        self._worker = threading.Thread(target=self._loop, daemon=True, name="QueueWorker")
        self._worker.start()
        return True

    def pause(self) -> None:
        self._pause_event.clear()
        self._publish(QueueEvents.QUEUE_PAUSED, None)

    def resume(self) -> None:
        self._pause_event.set()
        self._wake.set()
        self._publish(QueueEvents.QUEUE_RESUMED, None)

    def stop(self, wait: bool = True, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self._wake.set()
        self._pause_event.set()
        if wait and self._worker is not None:
            self._worker.join(timeout=timeout)

    # ────────────────────────────────────────
    # 영속화
    # ────────────────────────────────────────

    def snapshot(self) -> dict:
        """전체 상태 dict로 직렬화. JSON 호환."""
        with self._lock:
            return {
                "version": 1,
                "items": [item.to_dict() for item in self.all_items()],
                "current_id": self._current_item.id if self._current_item else None,
            }

    def save_snapshot(self, path: Path) -> bool:
        try:
            path.write_text(
                json.dumps(self.snapshot(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except Exception:
            _logger.exception(f"queue snapshot save failed: {path}")
            return False

    def restore(self, snapshot: dict) -> int:
        """snapshot에서 PENDING 작업만 큐에 복원. RUNNING/DONE은 인덱스에만.

        :return: 큐에 다시 들어간 개수
        """
        items = snapshot.get("items", [])
        restored = 0
        with self._lock:
            for d in items:
                try:
                    item = QueueItem.from_dict(d)
                except Exception:
                    continue
                # id가 카운터보다 크면 카운터 업데이트
                self._id_counter = itertools.count(max(item.id + 1,
                                                       next(itertools.count(item.id))))
                self._index[item.id] = item
                if item.status in (QueueItemStatus.PENDING, QueueItemStatus.RUNNING):
                    # RUNNING도 복원 시점에 다시 PENDING으로 강등 (워커 끊어졌으므로)
                    item.status = QueueItemStatus.PENDING
                    heapq.heappush(self._heap, (item.priority, next(self._seq_counter), item))
                    restored += 1
        self._wake.set()
        self._publish_snapshot()
        return restored

    def load_snapshot(self, path: Path) -> int:
        if not path.is_file():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return self.restore(data)
        except Exception:
            _logger.exception(f"queue snapshot load failed: {path}")
            return 0

    # ────────────────────────────────────────
    # 워커 루프
    # ────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # 일시정지 대기
            if not self._pause_event.is_set():
                # paused — 풀릴 때까지 또는 stop까지
                while not self._pause_event.wait(timeout=0.2):
                    if self._stop_event.is_set():
                        return

            # 다음 작업 가져오기
            with self._lock:
                if not self._heap:
                    item = None
                else:
                    _, _, item = heapq.heappop(self._heap)
                self._current_item = item

            if item is None:
                self._publish(QueueEvents.QUEUE_EMPTY, None)
                # 새 작업 대기
                self._wake.wait(timeout=1.0)
                self._wake.clear()
                continue

            # 처리
            if item.status == QueueItemStatus.CANCELLED:
                # 취소 마크된 것 스킵
                continue

            item.status = QueueItemStatus.RUNNING
            item.started_at = time.time()
            self._publish(QueueEvents.ITEM_STARTED, item.to_dict())
            self._publish_snapshot()

            try:
                self.processor(item.payload)
                if item.status != QueueItemStatus.CANCELLED:
                    item.status = QueueItemStatus.DONE
                item.finished_at = time.time()
                self._publish(QueueEvents.ITEM_FINISHED, item.to_dict())
            except Exception as e:
                item.status = QueueItemStatus.FAILED
                item.error = str(e)
                item.finished_at = time.time()
                _logger.exception(f"queue item {item.id} failed")
                self._publish(QueueEvents.ITEM_FAILED, item.to_dict())

            with self._lock:
                self._current_item = None
            self._publish_snapshot()

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

    def _publish_snapshot(self) -> None:
        if not self.publish_events:
            return
        try:
            from core.app_context import get_context
            snap = [item.to_dict() for item in self.all_items()]
            get_context().publish(QueueEvents.QUEUE_UPDATED, snap)
        except Exception:
            pass

# core/model_cache.py
"""무거운 모델(YOLO / SAM3)의 유휴 기반 캐시. 순수 로직이라 테스트 가능.

왜 필요한가
- YOLO: `ui/vue_bridge.py`가 auto_censor/auto_detect 때마다 루프 안에서 `YOLO(path)`를
  새로 만들었다. 등록 모델이 3개면 클릭 한 번에 3회 로딩.
- SAM3: `core/sam_refiner.py`가 `_SAM3_BUNDLE_CACHE`를 두고도 `finally`에서 매번
  `clear()` 해버려 캐시가 무력화됐다. 체크포인트가 3.45GB라 클릭마다 수십 초.

즉시 언로드는 VRAM을 아끼려던 의도였지만, 연속 작업에서는 매번 재로딩 비용을 물었다.
그래서 '쓰고 나서 N초 동안 아무도 안 쓰면 내린다'로 바꾼다. 연속 클릭은 캐시 히트,
자리를 비우면 알아서 반납.

이 모듈은 torch/ultralytics를 import하지 않는다 — 로더는 호출자가 콜백으로 준다.
"""
import threading
import time

# 기본 유휴 시간. SAM3는 로딩이 비싸고(수십 초) 덩치도 커서(3.5GB) 짧게,
# YOLO는 가벼워서(수십 MB) 길게 잡는다.
DEFAULT_IDLE_SECONDS = 90.0


class IdleModelCache:
    """key → 모델. `idle_seconds` 동안 접근이 없으면 해제한다.

    스레드 안전. `get()`은 캐시에 없으면 loader(key)로 만들고 저장한다.
    해제 시 `on_evict(model)`이 있으면 호출한다(VRAM 반납 등).
    """

    def __init__(self, name: str, idle_seconds: float = DEFAULT_IDLE_SECONDS,
                 max_items: int = 4, on_evict=None, time_fn=time.monotonic):
        self.name = name
        self.idle_seconds = float(idle_seconds)
        self.max_items = max(1, int(max_items))
        self._on_evict = on_evict
        self._now = time_fn
        self._lock = threading.RLock()
        self._items = {}        # key → (model, last_used)

    # ── 조회 ────────────────────────────────────────────────────────────────
    def get(self, key, loader):
        """캐시에서 꺼내거나 loader(key)로 만든다.

        loader는 락 **밖에서** 호출한다 — 모델 로딩이 수십 초라 락을 잡고 있으면
        다른 스레드(썸네일 생성 등)가 통째로 멈춘다.
        """
        self.sweep()
        with self._lock:
            entry = self._items.get(key)
            if entry is not None:
                self._items[key] = (entry[0], self._now())
                return entry[0]

        model = loader(key)

        with self._lock:
            # 그 사이 다른 스레드가 먼저 넣었으면 그걸 쓴다 (중복 로딩 1회는 감수)
            existing = self._items.get(key)
            if existing is not None:
                return existing[0]
            self._items[key] = (model, self._now())
            self._enforce_capacity_locked()
        return model

    def peek(self, key):
        with self._lock:
            entry = self._items.get(key)
            return entry[0] if entry else None

    def touch(self, key):
        with self._lock:
            entry = self._items.get(key)
            if entry:
                self._items[key] = (entry[0], self._now())

    # ── 해제 ────────────────────────────────────────────────────────────────
    def sweep(self) -> int:
        """유휴 시간이 지난 항목 해제. 반환: 해제한 개수."""
        cutoff = self._now() - self.idle_seconds
        with self._lock:
            stale = [k for k, (_m, used) in self._items.items() if used <= cutoff]
            evicted = [self._items.pop(k)[0] for k in stale]
        for model in evicted:
            self._evict(model)
        return len(evicted)

    def clear(self) -> int:
        with self._lock:
            evicted = [m for m, _u in self._items.values()]
            self._items.clear()
        for model in evicted:
            self._evict(model)
        return len(evicted)

    def _enforce_capacity_locked(self):
        while len(self._items) > self.max_items:
            oldest = min(self._items.items(), key=lambda kv: kv[1][1])[0]
            model = self._items.pop(oldest)[0]
            # 락 안이지만 _evict는 GC/empty_cache 정도라 짧다
            self._evict(model)

    def _evict(self, model):
        if self._on_evict is None:
            return
        try:
            self._on_evict(model)
        except Exception:
            pass

    # ── 상태 ────────────────────────────────────────────────────────────────
    def __len__(self):
        with self._lock:
            return len(self._items)

    def keys(self):
        with self._lock:
            return tuple(self._items)

    def stats(self) -> dict:
        with self._lock:
            now = self._now()
            return {
                'name': self.name,
                'count': len(self._items),
                'idle_seconds': self.idle_seconds,
                'keys': [
                    {'key': str(k), 'idle': round(now - used, 1)}
                    for k, (_m, used) in self._items.items()
                ],
            }


def release_torch_memory():
    """CUDA 캐시 반납. torch가 없으면 조용히 무시."""
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
    except Exception:
        pass


# ── 전역 캐시 인스턴스 ──────────────────────────────────────────────────────
# YOLO: 가볍고(수십 MB) 자주 쓰임 → 길게 잡는다
YOLO_CACHE = IdleModelCache('yolo', idle_seconds=300.0, max_items=8,
                            on_evict=lambda _m: release_torch_memory())

# SAM3: 3.45GB. 연속 작업(클릭 여러 번)은 캐시 히트로 받고,
# 손을 떼면 90초 뒤 VRAM을 돌려준다. 예전처럼 매번 clear() 하지 않는다.
SAM3_CACHE = IdleModelCache('sam3', idle_seconds=90.0, max_items=1,
                            on_evict=lambda _m: release_torch_memory())


def sweep_all() -> int:
    return YOLO_CACHE.sweep() + SAM3_CACHE.sweep()


def clear_all() -> int:
    return YOLO_CACHE.clear() + SAM3_CACHE.clear()

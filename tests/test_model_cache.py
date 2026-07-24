"""모델 캐시 테스트 — 유휴 해제 + 로딩 1회 보장.

회귀 방지 대상:
  · YOLO가 클릭마다 재로딩되던 문제 (vue_bridge 루프 안에서 YOLO(path) 생성)
  · SAM3가 `finally: cache.clear()` 때문에 캐시가 무력화돼 3.45GB를 매번 다시 읽던 문제
"""
import threading
import unittest

from core.model_cache import IdleModelCache


class _Clock:
    """테스트용 가짜 시계 — 실제로 기다리지 않는다."""
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class TestIdleModelCache(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.loads = []
        self.evicted = []
        self.cache = IdleModelCache('test', idle_seconds=60.0, max_items=3,
                                    on_evict=self.evicted.append,
                                    time_fn=self.clock)

    def _loader(self, key):
        self.loads.append(key)
        return f"model:{key}"

    def test_loads_once_then_hits_cache(self):
        for _ in range(5):
            self.assertEqual(self.cache.get('a', self._loader), 'model:a')
        self.assertEqual(self.loads, ['a'], "캐시 히트여야 하는데 재로딩됨")

    def test_distinct_keys_load_separately(self):
        self.cache.get('a', self._loader)
        self.cache.get('b', self._loader)
        self.assertEqual(self.loads, ['a', 'b'])
        self.assertEqual(len(self.cache), 2)

    def test_idle_eviction(self):
        self.cache.get('a', self._loader)
        self.clock.advance(61)
        self.assertEqual(self.cache.sweep(), 1)
        self.assertEqual(len(self.cache), 0)
        self.assertEqual(self.evicted, ['model:a'])

    def test_not_evicted_before_idle(self):
        self.cache.get('a', self._loader)
        self.clock.advance(30)
        self.assertEqual(self.cache.sweep(), 0)
        self.assertEqual(len(self.cache), 1)

    def test_access_refreshes_idle_timer(self):
        self.cache.get('a', self._loader)
        self.clock.advance(50)
        self.cache.get('a', self._loader)      # 갱신
        self.clock.advance(50)                 # 최초 접근 기준 100초지만 갱신 후 50초
        self.assertEqual(self.cache.sweep(), 0)
        self.assertEqual(self.loads, ['a'])

    def test_get_sweeps_stale_entries(self):
        self.cache.get('a', self._loader)
        self.clock.advance(61)
        self.cache.get('b', self._loader)      # get 내부에서 sweep
        self.assertEqual(self.evicted, ['model:a'])

    def test_reload_after_eviction(self):
        self.cache.get('a', self._loader)
        self.clock.advance(61)
        self.cache.sweep()
        self.cache.get('a', self._loader)
        self.assertEqual(self.loads, ['a', 'a'])

    def test_capacity_evicts_oldest(self):
        for key in ('a', 'b', 'c'):
            self.cache.get(key, self._loader)
            self.clock.advance(1)
        self.cache.get('d', self._loader)
        self.assertEqual(len(self.cache), 3)
        self.assertNotIn('a', self.cache.keys())
        self.assertEqual(self.evicted, ['model:a'])

    def test_clear_evicts_everything(self):
        self.cache.get('a', self._loader)
        self.cache.get('b', self._loader)
        self.assertEqual(self.cache.clear(), 2)
        self.assertEqual(len(self.cache), 0)
        self.assertEqual(sorted(self.evicted), ['model:a', 'model:b'])

    def test_peek_does_not_load(self):
        self.assertIsNone(self.cache.peek('a'))
        self.assertEqual(self.loads, [])

    def test_evict_callback_error_is_swallowed(self):
        cache = IdleModelCache('boom', idle_seconds=1,
                               on_evict=lambda _m: (_ for _ in ()).throw(RuntimeError('x')),
                               time_fn=self.clock)
        cache.get('a', self._loader)
        self.clock.advance(2)
        self.assertEqual(cache.sweep(), 1)   # 예외가 새어나오면 안 됨

    def test_stats_shape(self):
        self.cache.get('a', self._loader)
        stats = self.cache.stats()
        self.assertEqual(stats['name'], 'test')
        self.assertEqual(stats['count'], 1)
        self.assertEqual(stats['keys'][0]['key'], 'a')

    def test_concurrent_get_returns_same_instance(self):
        """여러 스레드가 동시에 요청해도 결국 같은 객체를 쓴다 (락 밖 로딩이라
        중복 로딩 자체는 발생할 수 있지만, 저장되는 인스턴스는 하나여야 한다)."""
        results = []
        barrier = threading.Barrier(4)

        def worker():
            barrier.wait()
            results.append(self.cache.get('shared', lambda k: object()))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(set(id(r) for r in results)), 1)


if __name__ == '__main__':
    unittest.main()

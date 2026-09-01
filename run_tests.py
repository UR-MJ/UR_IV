#!/usr/bin/env python
"""테스트 실행기 — 추가 설치 없이 표준 라이브러리(unittest)로 tests/ 전체 실행.

사용법:
    python run_tests.py            # 전체 (481개, 약 13초) — /verify · /ship 이 쓰는 경로
    python run_tests.py --quick    # 느린 통합 테스트 3종 제외 (약 1초) — PostToolUse 훅용

성공하면 종료코드 0, 하나라도 실패하면 1.
(pytest 불필요 — 비개발자도 한 줄로 검증 가능)

⚠ venv 의존성(pandas/PIL/PyQt6/requests)이 필요하다. 시스템 python 으로 돌리면
   ModuleNotFoundError 가 대량 발생한다 — `venv/Scripts/python.exe` 를 쓸 것.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))

# 실제 소켓 서버 · subprocess 스폰 · 스레드 대기를 쓰는 통합 테스트.
# 전체 11.7초 중 10.6초(91%)를 이 3개가 차지한다 → --quick 에서 제외.
SLOW_MODULES = frozenset({
    "tests.test_generation_api",
    "tests.test_generation_api_remote_e2e",
    "tests.test_backend_runtime",
})

# 위 느린 모듈이 커버하는 소스. 이 파일들을 고쳤다면 --quick 이어도 전체를 돌려야 한다.
# (hook_run_tests.py 가 이 집합을 import 해서 quick/full 을 결정 — 단일 진실 원천)
SLOW_MODULE_SOURCES = frozenset({
    "core/generation_api.py",
    "core/resource_coordinator.py",
    "core/backend_runtime.py",
    "backends/base.py",
})


def _iter_tests(suite):
    """중첩된 TestSuite 를 평탄화해 개별 TestCase 를 내놓는다."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_tests(item)
        else:
            yield item


def _without_slow(suite):
    """SLOW_MODULES 소속 테스트만 걷어낸다.

    import 실패로 생긴 _FailedTest 는 모듈이 unittest.loader 라 그대로 남는다 —
    느린 모듈이 깨져도 quick 모드에서 조용히 묻히지 않는다.
    """
    kept = unittest.TestSuite()
    for test in _iter_tests(suite):
        if type(test).__module__ not in SLOW_MODULES:
            kept.addTest(test)
    return kept


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    quick = "--quick" in argv

    sys.path.insert(0, ROOT)
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(ROOT, "tests"),
                            pattern="test_*.py", top_level_dir=ROOT)
    if quick:
        suite = _without_slow(suite)

    # quick 은 훅이 호출 → 실패 시 stderr 꼬리가 잘리지 않게 출력을 짧게(dots).
    result = unittest.TextTestRunner(verbosity=1 if quick else 2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

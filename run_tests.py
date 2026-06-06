#!/usr/bin/env python
"""테스트 실행기 — 추가 설치 없이 표준 라이브러리(unittest)로 tests/ 전체 실행.

사용법:
    python run_tests.py

성공하면 종료코드 0, 하나라도 실패하면 1.
(pytest 불필요 — 비개발자도 한 줄로 검증 가능)
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    sys.path.insert(0, ROOT)
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(ROOT, "tests"),
                            pattern="test_*.py", top_level_dir=ROOT)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

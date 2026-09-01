#!/usr/bin/env python
"""Claude Code PostToolUse 훅 — Python 파일을 Edit/Write 했을 때만 회귀 테스트 실행.

Claude Code 가 stdin 으로 tool 정보(JSON)를 준다. .py 수정일 때만 테스트를 돌리고,
실패하면 stderr + exit 2 로 Claude 에게 피드백한다(편집 자체를 되돌리진 않음).
.claude/settings.json 의 PostToolUse 훅에서 호출된다.

두 가지를 지킨다:
  1) **venv 인터프리터로 실행.** sys.executable(시스템 python)로 돌리면 pandas/PIL/
     PyQt6/requests 가 없어 ModuleNotFoundError 32개가 터지고, 그 가짜 실패가 매 편집마다
     Claude 에게 피드백돼 턴을 낭비한다.
  2) **기본은 --quick(약 1초).** 느린 통합 테스트 3종은 전체 시간의 91%를 먹으므로
     그것들이 커버하는 소스(run_tests.SLOW_MODULE_SOURCES)를 건드렸을 때만 전체를 돌린다.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tools/ -> repo root

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Windows 기본 stderr 는 cp949(+backslashreplace) — 한글·기호가 깨져 Claude 가
# 피드백을 못 읽는다. 훅의 존재 이유가 사라지므로 UTF-8 로 고정한다.
try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # 파이프가 아닌 드문 경우
    pass


def _interpreter() -> str:
    """저장소 venv 를 우선 사용한다. 없으면 현재 인터프리터로 폴백."""
    candidates = (
        os.path.join(ROOT, "venv", "Scripts", "python.exe"),  # Windows
        os.path.join(ROOT, "venv", "bin", "python"),          # POSIX
    )
    for path in candidates:
        if os.path.exists(path):
            return path
    return sys.executable


def _repo_relpath(file_path: str):
    """편집된 파일을 저장소 기준 상대경로(슬래시)로. 저장소 밖이면 None."""
    try:
        rel = os.path.relpath(os.path.abspath(file_path), ROOT)
    except ValueError:  # 다른 드라이브
        return None
    if rel.startswith(".."):
        return None
    return rel.replace(os.sep, "/")


def _needs_full_suite(rel: str) -> bool:
    """느린 통합 테스트가 커버하는 소스(또는 그 테스트 자체)를 고쳤나?"""
    try:
        from run_tests import SLOW_MODULES, SLOW_MODULE_SOURCES
    except Exception:
        return True  # 판단 불가면 안전하게 전체
    if rel in SLOW_MODULE_SOURCES:
        return True
    module = rel[:-3].replace("/", ".")  # tests/test_x.py -> tests.test_x
    return module in SLOW_MODULES


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    fp = ((data.get("tool_input") or {}).get("file_path") or "")
    if not str(fp).endswith(".py"):
        return 0  # 파이썬 파일이 아니면 스킵 (Vue/MD/JSON 등)

    rel = _repo_relpath(str(fp))
    if rel is None or rel.startswith(("venv/", ".claude/")):
        return 0  # 저장소 밖이거나 가상환경/설정 파일이면 스킵

    runner = os.path.join(ROOT, "run_tests.py")
    if not os.path.exists(runner):
        return 0

    full = _needs_full_suite(rel)
    argv = [_interpreter(), runner] + ([] if full else ["--quick"])
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # 자식도 UTF-8 로 출력
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           cwd=ROOT, env=env, timeout=180)
    except subprocess.TimeoutExpired:
        sys.stderr.write("⚠ run_tests.py 180초 초과 — 테스트가 멈춤(행) 상태일 수 있음.\n")
        return 2
    except Exception as exc:
        sys.stderr.write(f"⚠ run_tests.py 실행 실패: {exc}\n")
        return 2

    if r.returncode == 0:
        return 0

    scope = "전체" if full else "quick"
    sys.stderr.write(
        f"⚠ run_tests.py({scope}) 실패 — 방금 수정한 {rel} 이 회귀를 일으켰을 수 있음. 확인 필요:\n")
    # unittest 는 stderr 로 쓴다 — 실패 트레이스백이 있는 쪽에 예산을 더 준다.
    sys.stderr.write((r.stderr or "")[-3000:])
    tail = (r.stdout or "").strip()
    if tail:
        sys.stderr.write("\n[stdout]\n" + tail[-800:])
    return 2  # PostToolUse: exit 2 = stderr 를 Claude 에게 피드백


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Claude Code PostToolUse 훅 — Python 파일을 Edit/Write 했을 때만 run_tests.py 실행.

Claude Code가 stdin으로 tool 정보(JSON)를 준다. .py 수정일 때만 테스트를 돌리고,
실패하면 stderr + exit 2 로 Claude에게 피드백한다(편집 자체를 되돌리진 않음).
.claude/settings.json 의 PostToolUse 훅에서 호출된다.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tools/ -> repo root


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    fp = ((data.get("tool_input") or {}).get("file_path") or "")
    if not str(fp).endswith(".py"):
        return 0  # 파이썬 파일이 아니면 스킵 (Vue/MD/JSON 등)
    runner = os.path.join(ROOT, "run_tests.py")
    if not os.path.exists(runner):
        return 0
    try:
        r = subprocess.run([sys.executable, runner],
                           capture_output=True, text=True, cwd=ROOT, timeout=120)
    except Exception:
        return 0
    if r.returncode != 0:
        sys.stderr.write(
            "⚠ run_tests.py 실패 — 방금 수정한 Python 변경이 회귀를 일으켰을 수 있음. 확인 필요:\n")
        sys.stderr.write((r.stdout or "")[-2500:])
        sys.stderr.write((r.stderr or "")[-800:])
        return 2  # PostToolUse: exit 2 = stderr를 Claude에게 피드백
    return 0


if __name__ == "__main__":
    sys.exit(main())

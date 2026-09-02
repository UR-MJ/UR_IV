"""앱이 띄운 자식 프로세스(Forge/ComfyUI)가 앱보다 오래 살지 않게 하는 두 겹의 안전장치.

1. **Job Object (Windows)** — 자식을 `KILL_ON_JOB_CLOSE` 잡에 넣는다. 앱이 어떻게 죽든
   (X 버튼, 크래시, 작업 관리자 강제 종료) 잡 핸들이 닫히는 순간 OS 가 자식과 손자
   (launch.py → webui 서버)를 함께 끝낸다. 예전엔 closeEvent 의 taskkill 만 있어서
   강제 종료하면 Forge 가 고아로 남아 다음 실행이 17863 같은 포트로 밀렸다.
2. **PID 파일 + 시작 시 청소** — 1 이 못 미친 경우(잡 생성 실패 등)를 위해, 띄운 PID 와
   식별 표식(data-dir 경로)을 파일에 적어 두고 다음 시작 때 그 PID 가 살아 있고 명령줄에
   표식이 있으면 트리째 끝낸다. 표식이 없으면 남의 프로세스이므로 절대 건드리지 않는다.

Qt 에 의존하지 않는다. tests/test_process_guard.py 가 가짜 함수로 청소 규칙을, 실제
자식 프로세스로 잡 오브젝트를 검증한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

_IS_WINDOWS = os.name == "nt"


# ── 1. Job Object ──────────────────────────────────────────────────────────────

class KillOnCloseJob:
    """앱 프로세스가 사라지면 안의 프로세스를 전부 끝내는 잡. Windows 가 아니면 조용히 no-op."""

    def __init__(self) -> None:
        self._handle: Any = None
        self.error: str = ""
        if not _IS_WINDOWS:
            return
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                raise OSError(ctypes.get_last_error(), "CreateJobObjectW")

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint64) for name in (
                    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
            JobObjectExtendedLimitInformation = 9
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = kernel32.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
            )
            if not ok:
                raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
            self._kernel32 = kernel32
            self._handle = job
        except Exception as exc:  # noqa: BLE001 — 안전장치 실패는 기록만, 앱은 계속
            self.error = f"{type(exc).__name__}: {exc}"
            self._handle = None

    @property
    def active(self) -> bool:
        return self._handle is not None

    def assign(self, process: subprocess.Popen) -> bool:
        """Popen 자식을 잡에 넣는다. 성공하면 True — 실패해도 예외는 내지 않는다."""
        if not self.active:
            return False
        try:
            handle = getattr(process, "_handle", None)   # Popen 이 여는 프로세스 핸들 (Windows)
            if handle is None:
                return False
            if not self._kernel32.AssignProcessToJobObject(self._handle, int(handle)):
                import ctypes
                self.error = f"AssignProcessToJobObject failed: {ctypes.get_last_error()}"
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            return False

    def close(self) -> None:
        """잡 핸들을 닫는다 = 안의 프로세스 전부 종료 (앱 종료 시 자동으로도 일어난다)."""
        if self._handle is not None:
            try:
                self._kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None


_job: KillOnCloseJob | None = None


def app_job() -> KillOnCloseJob:
    """프로세스 전체가 공유하는 잡 하나."""
    global _job
    if _job is None:
        _job = KillOnCloseJob()
    return _job


# ── 2. PID 파일 + 고아 청소 ──────────────────────────────────────────────────────

def write_pid_file(path: Path, pid: int, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": int(pid), "marker": marker}), encoding="utf-8")


def read_pid_file(path: Path) -> tuple[int, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data["pid"]), str(data.get("marker") or "")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_pid_file(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if _IS_WINDOWS:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _command_line(pid: int) -> str:
    """프로세스의 명령줄 — 표식 확인용. 못 읽으면 빈 문자열(= 건드리지 않는다)."""
    if not _IS_WINDOWS:
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return ""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}').CommandLine"],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _kill_tree(pid: int) -> None:
    if _IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def sweep_orphan(
    path: Path,
    marker: str,
    *,
    is_alive: Callable[[int], bool] = _pid_alive,
    command_line: Callable[[int], str] = _command_line,
    kill_tree: Callable[[int], None] = _kill_tree,
) -> str:
    """지난 실행이 남긴 프로세스를 정리한다. 무엇을 했는지 한 줄로 돌려준다.

    규칙: PID 파일이 있고 → 그 PID 가 살아 있고 → 그 프로세스의 명령줄에 *우리 표식*
    (data-dir 경로) 이 있을 때만 끝낸다. 하나라도 어긋나면 손대지 않는다 — PID 는
    재사용되므로 표식 없이 죽이면 남의 프로그램을 죽일 수 있다.
    """
    entry = read_pid_file(path)
    if entry is None:
        return "no-pid-file"
    pid, saved_marker = entry
    clear_pid_file(path)
    if not marker or saved_marker != marker:
        return "marker-mismatch"
    if not is_alive(pid):
        return "already-gone"
    cmdline = command_line(pid)
    if marker.replace("\\", "/").lower() not in cmdline.replace("\\", "/").lower():
        return "pid-reused"
    kill_tree(pid)
    return f"killed-orphan:{pid}"


def marker_for(data_root: os.PathLike | str) -> str:
    """명령줄에서 우리 것임을 알아보는 표식 — --data-dir 로 넘기는 경로 그대로."""
    return str(data_root)


if sys.platform == "win32":  # pragma: no cover — 문서용
    __doc__ += "\n(Windows: Job Object + taskkill /T)"

"""GPU VRAM 사용량 — **장치 전체(모든 프로세스)** 기준.

왜 따로 있나: 하단 VRAM 바가 Forge 의 `/sdapi/v1/memory` 를 30초마다 읽었는데, 그 값은 Forge
자신이 잡은 메모리(체크포인트 ≈12GB)라 Ollama 가 27GB 를 올려도 12.1 에서 꿈쩍하지 않았다.
사용자가 기대하는 건 작업 관리자의 숫자 — 카드 전체가 얼마나 찼는가 — 이므로 NVML 로 직접 잰다.

우선순위: pynvml(NVML, 마이크로초) → `nvidia-smi` 프로세스 → None(호출자가 백엔드 값으로 대체).
Qt 에 의존하지 않는다 — tests/test_gpu_stats.py 가 가짜 NVML·가짜 nvidia-smi 로 검증한다.
"""
from __future__ import annotations

import subprocess
from typing import Any, Callable

_nvml_handle: Any = None
_nvml_broken = False


def _read_nvml(nvml: Any) -> dict | None:
    """pynvml 로 0번 장치의 used/total(bytes). 초기화는 한 번만, 실패하면 이후 시도 안 함."""
    global _nvml_handle, _nvml_broken
    if nvml is None or _nvml_broken:
        return None
    try:
        if _nvml_handle is None:
            nvml.nvmlInit()
            _nvml_handle = nvml.nvmlDeviceGetHandleByIndex(0)
        info = nvml.nvmlDeviceGetMemoryInfo(_nvml_handle)
        used, total = int(info.used), int(info.total)
        if total <= 0:
            return None
        return {"vram_used": used, "vram_total": total, "vram_free": max(0, total - used), "source": "nvml"}
    except Exception:
        _nvml_handle = None
        _nvml_broken = True
        return None


def _read_nvidia_smi(run: Callable[..., Any]) -> dict | None:
    """`nvidia-smi --query-gpu=memory.used,memory.total` (MiB) — NVML 이 없을 때."""
    try:
        proc = run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        line = (proc.stdout or "").strip().splitlines()
        if proc.returncode != 0 or not line:
            return None
        used_mib, total_mib = (float(x.strip()) for x in line[0].split(",")[:2])
        if total_mib <= 0:
            return None
        used, total = int(used_mib * 1024 * 1024), int(total_mib * 1024 * 1024)
        return {"vram_used": used, "vram_total": total, "vram_free": max(0, total - used), "source": "nvidia-smi"}
    except Exception:
        return None


def _import_nvml() -> Any:
    try:
        import pynvml  # noqa: WPS433 — 선택 의존성
        return pynvml
    except Exception:
        return None


def read_vram(*, nvml: Any = "auto", run: Callable[..., Any] = subprocess.run) -> dict | None:
    """장치 전체 VRAM {vram_used, vram_total, vram_free, source} 또는 None."""
    module = _import_nvml() if nvml == "auto" else nvml
    return _read_nvml(module) or _read_nvidia_smi(run)


def reset_cache() -> None:
    """테스트용 — NVML 핸들·고장 플래그 초기화."""
    global _nvml_handle, _nvml_broken
    _nvml_handle = None
    _nvml_broken = False

"""하단 VRAM 바의 데이터 — 장치 전체 사용량을 NVML → nvidia-smi 순으로 읽는다."""
from __future__ import annotations

import types
import unittest

from core import gpu_stats


class _MemInfo:
    def __init__(self, used, total):
        self.used, self.total = used, total


def _fake_nvml(used, total, *, calls):
    mod = types.SimpleNamespace()
    mod.nvmlInit = lambda: calls.append("init")
    mod.nvmlDeviceGetHandleByIndex = lambda i: f"h{i}"
    mod.nvmlDeviceGetMemoryInfo = lambda h: (calls.append("mem"), _MemInfo(used, total))[1]
    return mod


def _fake_run(stdout, returncode=0):
    def run(cmd, **kw):
        assert cmd[0] == "nvidia-smi" and "--query-gpu=memory.used,memory.total" in cmd
        return types.SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


class GpuStatsTests(unittest.TestCase):
    def setUp(self):
        gpu_stats.reset_cache()

    def test_nvml_is_device_wide_and_initialised_once(self):
        calls = []
        nvml = _fake_nvml(31_177 * 2**20, 32_607 * 2**20, calls=calls)
        first = gpu_stats.read_vram(nvml=nvml, run=_fake_run(""))
        second = gpu_stats.read_vram(nvml=nvml, run=_fake_run(""))
        self.assertEqual(first["source"], "nvml")
        self.assertEqual(first["vram_total"], 32_607 * 2**20)
        self.assertEqual(first["vram_used"], 31_177 * 2**20)
        self.assertEqual(first["vram_free"], (32_607 - 31_177) * 2**20)
        self.assertEqual(second["vram_used"], first["vram_used"])
        self.assertEqual(calls.count("init"), 1, "핸들은 한 번만 만든다 — 5초마다 nvmlInit 하지 않는다")
        self.assertEqual(calls.count("mem"), 2)

    def test_nvidia_smi_fallback_parses_mib(self):
        out = gpu_stats.read_vram(nvml=None, run=_fake_run("12345, 32607\n"))
        self.assertEqual(out["source"], "nvidia-smi")
        self.assertEqual(out["vram_used"], 12345 * 2**20)
        self.assertEqual(out["vram_total"], 32607 * 2**20)

    def test_broken_nvml_falls_back_and_is_not_retried(self):
        calls = []
        nvml = types.SimpleNamespace(
            nvmlInit=lambda: calls.append("init") or (_ for _ in ()).throw(RuntimeError("no driver")),
            nvmlDeviceGetHandleByIndex=lambda i: "h", nvmlDeviceGetMemoryInfo=lambda h: _MemInfo(1, 2),
        )
        out = gpu_stats.read_vram(nvml=nvml, run=_fake_run("100, 200"))
        self.assertEqual(out["source"], "nvidia-smi")
        gpu_stats.read_vram(nvml=nvml, run=_fake_run("100, 200"))
        self.assertEqual(calls.count("init"), 1, "고장난 NVML 은 다시 두드리지 않는다")

    def test_nothing_available_returns_none(self):
        self.assertIsNone(gpu_stats.read_vram(nvml=None, run=_fake_run("", returncode=1)))
        self.assertIsNone(gpu_stats.read_vram(nvml=None, run=_fake_run("garbage")))

    def test_real_nvml_if_present_reports_sane_numbers(self):
        """실제 GPU 가 있으면 총량이 양수이고 사용량이 총량을 넘지 않는다 — 없으면 None 이어도 통과."""
        out = gpu_stats.read_vram()
        if out is None:
            self.skipTest("GPU/NVML 없음")
        self.assertGreater(out["vram_total"], 0)
        self.assertLessEqual(out["vram_used"], out["vram_total"])


if __name__ == "__main__":
    unittest.main()

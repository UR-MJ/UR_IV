"""연결된 설치의 실행 배치 파일 → 앱 실행 인자. 실제 배치 파일 본문으로 검증한다."""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from core import launch_args as la

FORGE_BAT = """@echo off
git pull
:: set PYTHON=
:: set GIT=
:: set VENV_DIR=
set COMMANDLINE_ARGS= --sage --uv --pin-shared-memory --cuda-malloc --cuda-stream --theme dark --api --flash --onnxruntime-gpu --enable-triton-backend
:: --xformers --sage --uv
:: --pin-shared-memory --cuda-malloc --cuda-stream
call webui.bat
"""
COMFY_BAT = """.\\python_embeded\\python.exe -s ComfyUI\\main.py --windows-standalone-build
echo If you see this and ComfyUI did not start try updating your Nvidia Drivers to the latest.
pause
"""
COMFY_FAST_BAT = """.\\python_embeded\\python.exe -s ComfyUI\\main.py --windows-standalone-build --fast fp16_accumulation --use-sage-attention
echo If you see this and ComfyUI did not start try updating your Nvidia Drivers to the latest.
pause
"""


class ForgeBatTests(unittest.TestCase):
    def test_reads_commandline_args_and_skips_commented_lines(self):
        args = la.parse_forge_user_bat(FORGE_BAT)
        self.assertEqual(args[:2], ["--sage", "--uv"])
        self.assertNotIn("--xformers", args, ":: 주석의 옛 플래그를 살리면 안 된다")

    def test_managed_flags_are_dropped_with_their_values(self):
        kept, dropped = la.strip_managed_flags(la.parse_forge_user_bat(FORGE_BAT), la.FORGE_MANAGED_FLAGS)
        self.assertEqual(kept, ["--sage", "--pin-shared-memory", "--cuda-malloc", "--cuda-stream",
                                "--flash", "--onnxruntime-gpu", "--enable-triton-backend"])
        self.assertEqual(dropped, ["--uv", "--theme", "--api"])
        self.assertNotIn("dark", kept, "--theme 의 값도 같이 빠져야 한다")

    def test_accumulating_syntax_and_quotes(self):
        text = 'set COMMANDLINE_ARGS=--xformers\nset COMMANDLINE_ARGS=%COMMANDLINE_ARGS% --ckpt-dir "C:\\my models" --medvram\n'
        args = la.parse_forge_user_bat(text)
        self.assertEqual(args, ["--xformers", "--ckpt-dir", '"C:\\my models"', "--medvram"])
        kept, dropped = la.strip_managed_flags(args, la.FORGE_MANAGED_FLAGS)
        self.assertEqual(kept, ["--xformers", "--medvram"])

    def test_flag_with_inline_value_is_dropped_as_one_token(self):
        kept, dropped = la.strip_managed_flags(["--port=7860", "--sage"], la.FORGE_MANAGED_FLAGS)
        self.assertEqual((kept, dropped), (["--sage"], ["--port=7860"]))


class ComfyBatTests(unittest.TestCase):
    def test_reads_args_after_main_py_and_drops_standalone_flag(self):
        args = la.parse_comfy_run_bat(COMFY_FAST_BAT)
        self.assertEqual(args, ["--windows-standalone-build", "--fast", "fp16_accumulation", "--use-sage-attention"])
        kept, dropped = la.strip_managed_flags(args, la.COMFY_MANAGED_FLAGS)
        self.assertEqual(kept, ["--fast", "fp16_accumulation", "--use-sage-attention"])
        self.assertEqual(dropped, ["--windows-standalone-build"])

    def test_optional_listen_value_is_dropped_only_when_it_is_a_value(self):
        kept, _ = la.strip_managed_flags(["--listen", "0.0.0.0", "--fast"], la.COMFY_MANAGED_FLAGS)
        self.assertEqual(kept, ["--fast"])
        kept, _ = la.strip_managed_flags(["--listen", "--fast"], la.COMFY_MANAGED_FLAGS)
        self.assertEqual(kept, ["--fast"])


class MergeTests(unittest.TestCase):
    def test_user_args_override_imported_flags(self):
        merged = la.merge_args(["--sage", "--fast", "fp16_accumulation", "--cuda-malloc"], ["--fast", "cublas_ops", "--medvram"])
        self.assertEqual(merged, ["--sage", "--cuda-malloc", "--fast", "cublas_ops", "--medvram"])

    def test_empty_sides(self):
        self.assertEqual(la.merge_args([], ["--a"]), ["--a"])
        self.assertEqual(la.merge_args(["--a", "1"], []), ["--a", "1"])


class DiscoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_forge_uses_webui_user_bat(self):
        (self.root / "webui-user.bat").write_text(FORGE_BAT, encoding="utf-8")
        found = la.discover_launch_args("forge", [self.root])
        self.assertTrue(found.source.endswith("webui-user.bat"))
        self.assertEqual(found.args[:2], ["--sage", "--pin-shared-memory"])
        self.assertEqual(found.dropped, ["--uv", "--theme", "--api"])

    def test_forge_without_bat_imports_nothing(self):
        found = la.discover_launch_args("forge", [self.root])
        self.assertEqual((found.source, found.args), ("", []))

    def test_comfy_prefers_fast_bat_when_fp16_is_on(self):
        (self.root / la.COMFY_RUN_BAT).write_text(COMFY_BAT, encoding="utf-8")
        (self.root / la.COMFY_FAST_FP16_BAT).write_text(COMFY_FAST_BAT, encoding="utf-8")
        plain = la.discover_launch_args("comfyui", [self.root / "ComfyUI", self.root])
        self.assertTrue(plain.source.endswith(la.COMFY_RUN_BAT))
        self.assertEqual(plain.args, [])
        fast = la.discover_launch_args("comfyui", [self.root / "ComfyUI", self.root], fast_fp16=True)
        self.assertTrue(fast.source.endswith(la.COMFY_FAST_FP16_BAT))
        self.assertEqual(fast.args, ["--fast", "fp16_accumulation", "--use-sage-attention"])

    def test_comfy_fp16_without_fast_bat_appends_the_flag(self):
        (self.root / la.COMFY_RUN_BAT).write_text(COMFY_BAT, encoding="utf-8")
        found = la.discover_launch_args("comfyui", [self.root], fast_fp16=True)
        self.assertEqual(found.args, ["--fast", "fp16_accumulation"])
        nothing = la.discover_launch_args("comfyui", [], fast_fp16=True)
        self.assertEqual((nothing.source, nothing.args), ("", ["--fast", "fp16_accumulation"]))


if __name__ == "__main__":
    unittest.main()

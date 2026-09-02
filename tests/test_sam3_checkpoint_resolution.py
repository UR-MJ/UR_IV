"""SAM3 체크포인트는 앱이 스캔한 폴더의 **절대 경로**로 보낸다.

관리형 Forge 는 `--data-dir` 아래 models 를 보므로, 이름만 보내면 확장이
`<data>/models/sam3/<name>` 을 찾다 'SAM3 checkpoint not found' 로 죽는다.
확장(sam3ext/core.py::resolve_checkpoint_path)은 절대 경로면 그대로 쓴다.
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest.mock import patch

from core import forge_modules, sam3_args


class ResolveSam3CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "sam3").mkdir()
        (self.root / "sam3" / "sam3.1_multiplex_fp16.safetensors").write_bytes(b"x")
        (self.root / "sam3.pt").write_bytes(b"x")
        self.patch = patch("core.forge_modules.get_forge_root", return_value=self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_name_in_sam3_folder_becomes_absolute(self):
        resolved = forge_modules.resolve_sam3_checkpoint("sam3.1_multiplex_fp16.safetensors")
        self.assertEqual(pathlib.Path(resolved), (self.root / "sam3" / "sam3.1_multiplex_fp16.safetensors").resolve())
        self.assertTrue(pathlib.Path(resolved).is_absolute())

    def test_name_in_models_root_and_default(self):
        self.assertEqual(pathlib.Path(forge_modules.resolve_sam3_checkpoint("sam3.pt")), (self.root / "sam3.pt").resolve())
        self.assertEqual(pathlib.Path(forge_modules.resolve_sam3_checkpoint("")), (self.root / "sam3.pt").resolve(), "빈 값은 기본 sam3.pt")

    def test_unknown_name_and_absolute_path_pass_through(self):
        self.assertEqual(forge_modules.resolve_sam3_checkpoint("nope.pt"), "nope.pt")
        absolute = str((self.root / "sam3" / "sam3.1_multiplex_fp16.safetensors").resolve())
        self.assertEqual(forge_modules.resolve_sam3_checkpoint(absolute), absolute)
        self.assertEqual(forge_modules.resolve_sam3_checkpoint("auto"), "auto", "확장의 HF 자동 다운로드 키워드는 건드리지 않는다")

    def test_build_state_sends_the_absolute_path(self):
        state = sam3_args.build_state({"sam3_checkpoint": "sam3.1_multiplex_fp16.safetensors"})
        self.assertTrue(pathlib.Path(state["sam3_checkpoint"]).is_absolute())
        self.assertTrue(state["sam3_checkpoint"].endswith("sam3.1_multiplex_fp16.safetensors"))
        self.assertTrue(state["sam3_enable"])


if __name__ == "__main__":
    unittest.main()

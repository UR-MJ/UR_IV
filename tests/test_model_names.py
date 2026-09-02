"""저장된 체크포인트 이름이 백엔드 표기(해시 유무)와 달라도 같은 파일을 고른다."""
from __future__ import annotations

import unittest

from core.model_names import checkpoint_key, match_checkpoint

FORGE_TITLES = [
    "krea2_raw_bf16.safetensors",
    "anima_baseV10.safetensors [bd43b7cffe]",
    "Anima-3.8B-v1.1.safetensors [4a458d26b2]",
    "Anima-2.9B-preview-v1.safetensors [0b3020d1b9]",
]


class CheckpointMatchTests(unittest.TestCase):
    def test_exact_title_wins(self):
        self.assertEqual(match_checkpoint("Anima-3.8B-v1.1.safetensors [4a458d26b2]", FORGE_TITLES), 2)

    def test_saved_without_hash_matches_forge_title_with_hash(self):
        """ComfyUI 에서 저장된 이름(해시 없음)으로 Forge 목록을 다시 볼 때 — 예전엔 index 0(krea2) 로 떨어졌다."""
        self.assertEqual(match_checkpoint("Anima-3.8B-v1.1.safetensors", FORGE_TITLES), 2)

    def test_saved_with_stale_hash_still_matches_by_filename(self):
        self.assertEqual(match_checkpoint("Anima-3.8B-v1.1.safetensors [deadbeef00]", FORGE_TITLES), 2)

    def test_case_and_subfolder_are_ignored(self):
        self.assertEqual(match_checkpoint("models\\ANIMA-3.8B-V1.1.SAFETENSORS", FORGE_TITLES), 2)

    def test_unknown_and_empty(self):
        self.assertEqual(match_checkpoint("nope.safetensors", FORGE_TITLES), -1)
        self.assertEqual(match_checkpoint("", FORGE_TITLES), -1)

    def test_key(self):
        self.assertEqual(checkpoint_key("C:/x/Anima-3.8B-v1.1.safetensors [4a458d26b2]"), "anima-3.8b-v1.1.safetensors")
        self.assertEqual(checkpoint_key("krea2_raw_bf16.safetensors"), "krea2_raw_bf16.safetensors")


if __name__ == "__main__":
    unittest.main()

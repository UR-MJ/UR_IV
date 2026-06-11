"""utils/atomic_json.py — 원자적 쓰기 + 손상 백업 로드 테스트."""
import json
import os
import tempfile
import unittest

from utils.atomic_json import atomic_write_json, load_json_safe


class TestAtomicWriteJson(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'sub', 'data.json')

    def tearDown(self):
        self.dir.cleanup()

    def test_write_and_read_roundtrip(self):
        atomic_write_json(self.path, {'a': 1, '한글': [1, 2]})
        with open(self.path, encoding='utf-8') as f:
            self.assertEqual(json.load(f), {'a': 1, '한글': [1, 2]})

    def test_no_tmp_leftover(self):
        atomic_write_json(self.path, [1, 2, 3])
        self.assertFalse(os.path.exists(self.path + '.tmp'))

    def test_overwrite_existing(self):
        atomic_write_json(self.path, {'v': 1})
        atomic_write_json(self.path, {'v': 2})
        self.assertEqual(load_json_safe(self.path, {}), {'v': 2})

    def test_indent_none_compact(self):
        atomic_write_json(self.path, {'a': 1}, indent=None)
        with open(self.path, encoding='utf-8') as f:
            self.assertNotIn('\n', f.read())


class TestLoadJsonSafe(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'data.json')

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_returns_default(self):
        self.assertEqual(load_json_safe(self.path, []), [])
        self.assertEqual(load_json_safe(self.path, {'x': 1}), {'x': 1})

    def test_corrupt_backed_up_not_silently_lost(self):
        # 손상 파일 → default 반환 + .corrupt 백업 (다음 저장이 덮어써도 원본 보존)
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('{"truncated": ')
        self.assertEqual(load_json_safe(self.path, {}), {})
        self.assertFalse(os.path.exists(self.path))
        self.assertTrue(os.path.exists(self.path + '.corrupt'))
        with open(self.path + '.corrupt', encoding='utf-8') as f:
            self.assertEqual(f.read(), '{"truncated": ')

    def test_corrupt_backup_disabled(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('not json')
        self.assertEqual(load_json_safe(self.path, [], backup_corrupt=False), [])
        self.assertTrue(os.path.exists(self.path))  # 원본 유지

    def test_wrong_root_type_returns_default(self):
        atomic_write_json(self.path, {'a': 1})
        self.assertEqual(load_json_safe(self.path, []), [])  # dict인데 list 기대 → default

    def test_valid_load(self):
        atomic_write_json(self.path, [{'p': 'x'}])
        self.assertEqual(load_json_safe(self.path, []), [{'p': 'x'}])


if __name__ == "__main__":
    unittest.main()

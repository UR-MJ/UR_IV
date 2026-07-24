"""이미지 캐시 정리 테스트.

실측(2026-07) image_cache 812MB / thumbs 96,641개 — 정리 루틴이 아예 없었다.
여기서 검증하는 핵심 안전장치: **undo 히스토리가 참조하는 최근 파일은 지우지 않는다.**
"""
import os
import shutil
import tempfile
import time
import unittest

from core.cache_cleanup import (
    SHARD_PREFIX_LEN,
    migrate_flat_to_sharded,
    prune_by_total_size,
    prune_editor_temp,
    shard_path,
)


class _TmpDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='cachetest_')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _touch(self, name, size=16, age_hours=0.0):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(b'x' * size)
        if age_hours:
            when = time.time() - age_hours * 3600
            os.utime(path, (when, when))
        return path


class TestShardPath(_TmpDir):
    def test_prefix_split(self):
        p = shard_path('/base', 'abcdef123', '.jpg')
        self.assertEqual(os.path.basename(p), 'abcdef123.jpg')
        self.assertEqual(os.path.basename(os.path.dirname(p)),
                         'abcdef123'[:SHARD_PREFIX_LEN])

    def test_short_digest_does_not_crash(self):
        self.assertTrue(shard_path('/base', '', '.jpg').endswith('.jpg'))


class TestPruneEditorTemp(_TmpDir):
    def test_keeps_recent_even_when_old(self):
        # undo 스택이 참조하는 최근 파일은 나이와 무관하게 보존돼야 한다
        for i in range(5):
            self._touch(f'edited_{i}.png', age_hours=100)
        removed = prune_editor_temp(self.dir, keep=5, max_age_hours=1)
        self.assertEqual(removed, 0)
        self.assertEqual(len(os.listdir(self.dir)), 5)

    def test_removes_old_beyond_keep(self):
        for i in range(10):
            self._touch(f'edited_{i:02d}.png', age_hours=100 - i)
        removed = prune_editor_temp(self.dir, keep=3, max_age_hours=1)
        self.assertEqual(removed, 7)
        self.assertEqual(len(os.listdir(self.dir)), 3)

    def test_recent_files_survive_age_filter(self):
        for i in range(10):
            self._touch(f'edited_{i:02d}.png', age_hours=0)
        # 전부 방금 만든 파일 → keep 초과분이어도 max_age 미달이라 안 지움
        self.assertEqual(prune_editor_temp(self.dir, keep=3, max_age_hours=24), 0)

    def test_under_keep_is_noop(self):
        self._touch('edited_a.png')
        self.assertEqual(prune_editor_temp(self.dir, keep=10), 0)

    def test_missing_dir_is_safe(self):
        self.assertEqual(prune_editor_temp(os.path.join(self.dir, 'nope'), keep=1), 0)

    def test_ignores_non_images(self):
        self._touch('notes.txt', age_hours=100)
        for i in range(5):
            self._touch(f'edited_{i}.png', age_hours=100)
        prune_editor_temp(self.dir, keep=0, max_age_hours=1)
        self.assertIn('notes.txt', os.listdir(self.dir))

    def test_keep_zero_removes_all_old(self):
        for i in range(4):
            self._touch(f'edited_{i}.png', age_hours=100)
        self.assertEqual(prune_editor_temp(self.dir, keep=0, max_age_hours=1), 4)


class TestPruneBySize(_TmpDir):
    def test_removes_oldest_until_under_limit(self):
        for i in range(10):
            self._touch(f'f{i:02d}.jpg', size=100, age_hours=100 - i)
        removed = prune_by_total_size(self.dir, max_bytes=500)
        self.assertGreaterEqual(removed, 5)
        total = sum(os.path.getsize(os.path.join(self.dir, f))
                    for f in os.listdir(self.dir))
        self.assertLessEqual(total, 500)

    def test_newest_survive(self):
        for i in range(5):
            self._touch(f'f{i}.jpg', size=100, age_hours=100 - i)
        prune_by_total_size(self.dir, max_bytes=200)
        remaining = sorted(os.listdir(self.dir))
        self.assertIn('f4.jpg', remaining)

    def test_under_limit_is_noop(self):
        self._touch('a.jpg', size=10)
        self.assertEqual(prune_by_total_size(self.dir, max_bytes=10_000), 0)

    def test_recursive_walks_shards(self):
        for i in range(6):
            self._touch(os.path.join(f'{i:02d}', f'{i:02d}abc.jpg'),
                        size=100, age_hours=100 - i)
        removed = prune_by_total_size(self.dir, max_bytes=250, recursive=True)
        self.assertGreaterEqual(removed, 3)


class TestMigrate(_TmpDir):
    def test_moves_flat_files_into_shards(self):
        names = ['aabbcc.jpg', 'aaddee.jpg', 'ffgghh.jpg']
        for n in names:
            self._touch(n)
        moved = migrate_flat_to_sharded(self.dir)
        self.assertEqual(moved, 3)
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'aa', 'aabbcc.jpg')))
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'aa', 'aaddee.jpg')))
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'ff', 'ffgghh.jpg')))
        # 평면 위치에는 더 이상 없어야 한다
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'aabbcc.jpg')))

    def test_already_sharded_is_noop(self):
        self._touch(os.path.join('aa', 'aabbcc.jpg'))
        self.assertEqual(migrate_flat_to_sharded(self.dir), 0)

    def test_respects_limit(self):
        for i in range(10):
            self._touch(f'{i:02d}aaaa.jpg')
        self.assertEqual(migrate_flat_to_sharded(self.dir, limit=4), 4)

    def test_missing_dir_is_safe(self):
        self.assertEqual(migrate_flat_to_sharded(os.path.join(self.dir, 'nope')), 0)


if __name__ == '__main__':
    unittest.main()

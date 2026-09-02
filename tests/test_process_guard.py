"""앱이 띄운 백엔드가 앱보다 오래 살지 않게 — 잡 오브젝트와 PID 파일 청소 규칙."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

from core import process_guard as pg


class SweepRulesTests(unittest.TestCase):
    """청소는 '우리가 띄운 것' 이 확실할 때만 — PID 는 재사용되므로 표식이 핵심이다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "forge.pid"
        self.marker = r"C:\Users\URL\Desktop\Image viewer\user_data\managed_backends\forge\data"
        self.killed = []

    def tearDown(self):
        self.tmp.cleanup()

    def _sweep(self, *, alive=True, cmdline=None):
        cmd = cmdline if cmdline is not None else f'python launch.py --api --data-dir "{self.marker}" --port 17860'
        return pg.sweep_orphan(
            self.path, self.marker,
            is_alive=lambda pid: alive,
            command_line=lambda pid: cmd,
            kill_tree=self.killed.append,
        )

    def test_orphan_with_our_marker_is_killed_and_pid_file_removed(self):
        pg.write_pid_file(self.path, 4242, self.marker)
        self.assertEqual(self._sweep(), "killed-orphan:4242")
        self.assertEqual(self.killed, [4242])
        self.assertFalse(self.path.exists())

    def test_marker_compares_case_and_slash_insensitively(self):
        pg.write_pid_file(self.path, 7, self.marker)
        result = self._sweep(cmdline=f"python launch.py --data-dir '{self.marker.replace(chr(92), '/').upper()}'")
        self.assertEqual(result, "killed-orphan:7")

    def test_reused_pid_without_marker_is_left_alone(self):
        """사용자가 7860 으로 직접 띄운 Forge — 같은 launch.py 라도 data-dir 이 다르면 남의 것."""
        pg.write_pid_file(self.path, 99, self.marker)
        result = self._sweep(cmdline=r"python C:\sd-webui-forge-classic\launch.py --api --port 7860")
        self.assertEqual(result, "pid-reused")
        self.assertEqual(self.killed, [])

    def test_dead_pid_and_missing_file_do_nothing(self):
        self.assertEqual(self._sweep(), "no-pid-file")
        pg.write_pid_file(self.path, 5, self.marker)
        self.assertEqual(self._sweep(alive=False), "already-gone")
        self.assertEqual(self.killed, [])

    def test_marker_mismatch_is_not_ours(self):
        pg.write_pid_file(self.path, 5, r"D:\other\data")
        self.assertEqual(self._sweep(), "marker-mismatch")
        self.assertEqual(self.killed, [])

    def test_corrupt_pid_file_is_ignored(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self._sweep(), "no-pid-file")


@unittest.skipUnless(os.name == "nt", "Windows Job Object")
class JobObjectTests(unittest.TestCase):
    def test_child_dies_when_job_closes(self):
        """앱이 강제 종료되면 잡 핸들이 닫힌다 — 그때 자식이 따라 죽어야 고아가 안 남는다."""
        job = pg.KillOnCloseJob()
        self.assertTrue(job.active, job.error)
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        )
        try:
            self.assertTrue(job.assign(child), job.error)
            self.assertIsNone(child.poll(), "잡에 넣는 것만으로 죽으면 안 된다")
            job.close()
            deadline = time.time() + 5
            while child.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            self.assertIsNotNone(child.poll(), "잡을 닫았는데 자식이 살아 있다")
        finally:
            if child.poll() is None:
                child.kill()

    def test_app_job_is_shared(self):
        self.assertIs(pg.app_job(), pg.app_job())


if __name__ == "__main__":
    unittest.main()

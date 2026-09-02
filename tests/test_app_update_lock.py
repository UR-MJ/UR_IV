from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from core.app_update_lock import acquire_update_lock, is_update_in_progress


@unittest.skipUnless(os.name == "nt", "Windows named mutex contract")
class AppUpdateLockTests(unittest.TestCase):
    def test_mutex_is_busy_while_helper_lives_and_recovers_after_forced_exit(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        code = (
            "from core.app_update_lock import acquire_update_lock; "
            "import os,time; "
            "lock=acquire_update_lock(timeout=0); "
            "print('ready', flush=True); "
            "time.sleep(30)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual("ready", process.stdout.readline().strip())
            self.assertTrue(is_update_in_progress(project_root))
        finally:
            process.kill()
            process.communicate(timeout=5)

        # Kernel ownership disappears with the killed helper; no stale file or
        # timestamp recovery is needed before the next application start.
        lock = acquire_update_lock(project_root, timeout=1.0)
        lock.release()
        self.assertFalse(is_update_in_progress(project_root))


if __name__ == "__main__":
    unittest.main()

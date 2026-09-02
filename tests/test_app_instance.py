from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from core.app_instance import (
    live_app_instance_pids,
    register_app_instance,
    unregister_app_instance,
    wait_for_update_lock,
)


class AppInstanceRegistryTests(unittest.TestCase):
    def test_register_list_and_unregister_are_project_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = register_app_instance(temp, pid=43210)
            self.assertTrue(marker.is_file())
            with patch("core.app_instance.process_exists", return_value=True):
                self.assertEqual(live_app_instance_pids(temp), [43210])
                self.assertEqual(live_app_instance_pids(temp, exclude_pid=43210), [])
            unregister_app_instance(temp, pid=43210)
            self.assertFalse(marker.exists())

    def test_dead_instance_marker_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = register_app_instance(temp, pid=43211)
            with patch("core.app_instance.process_exists", return_value=False):
                self.assertEqual(live_app_instance_pids(temp), [])
            self.assertFalse(marker.exists())

    def test_reused_pid_does_not_keep_a_stale_instance_marker_live(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("core.app_instance.process_start_identity", return_value="old"):
                marker = register_app_instance(temp, pid=43212)
            with (
                patch("core.app_instance.process_exists", return_value=True),
                patch("core.app_instance.process_start_identity", return_value="new"),
            ):
                self.assertEqual(live_app_instance_pids(temp), [])
            self.assertFalse(marker.exists())

    def test_live_update_lock_prevents_a_new_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "core.app_update_lock.wait_until_update_complete",
                    side_effect=RuntimeError("busy"),
                ) as wait,
                self.assertRaises(RuntimeError),
            ):
                wait_for_update_lock(temp, timeout=0)
            wait.assert_called_once_with(temp, timeout=0)


if __name__ == "__main__":
    unittest.main()

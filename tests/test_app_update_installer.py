from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

from core.app_update_installer import (
    InstallerError,
    apply_plan,
    load_plan,
    run_installer,
)


EXPECTED_HEAD = "a" * 40
TARGET_COMMIT = "b" * 40
TRUSTED_REMOTE = "https://github.com/UR-al/UR_IV.git"


class RecordingGit:
    """Small in-memory Git state machine used by apply_plan tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.head = EXPECTED_HEAD
        self.remote_url = TRUSTED_REMOTE
        self.branch = "main"
        self.tag_target = TARGET_COMMIT
        self.target_version = "2.7.0"
        self.ancestor = True
        self.changed = "src/updated.py\0"
        self.unstaged = "config/local.json\0"
        self.staged = ""
        self.untracked = "notes/private.txt\0"
        self.ignored = ""
        self.merged = False
        self.fail_merge = False
        self.verified_head: str | None = None

    def __call__(self, root: Path, *args: str) -> str:
        checkout_root = root.resolve()
        self.calls.append(tuple(args))
        command = tuple(args)
        if command == ("rev-parse", "--show-toplevel"):
            return str(checkout_root)
        if command == ("rev-parse", "HEAD"):
            if self.merged:
                return self.verified_head or TARGET_COMMIT
            return self.head
        if command == ("remote", "get-url", "origin"):
            return self.remote_url
        if command == ("branch", "--show-current"):
            return self.branch
        if command == ("rev-parse", "v2.7.0^{commit}"):
            return self.tag_target
        if command[0:2] == ("cat-file", "-e"):
            return ""
        if command == ("show", f"{TARGET_COMMIT}:VERSION"):
            return f"{self.target_version}\n"
        if command == (
            "merge-base",
            "--is-ancestor",
            EXPECTED_HEAD,
            TARGET_COMMIT,
        ):
            if not self.ancestor:
                raise InstallerError("not an ancestor")
            return ""
        if command == ("diff", "--name-only", "--no-renames", "-z", EXPECTED_HEAD, TARGET_COMMIT):
            return self.changed
        if command == ("diff", "--name-only", "-z"):
            return self.unstaged
        if command == ("diff", "--cached", "--name-only", "-z"):
            return self.staged
        if command == ("ls-files", "-z", "--others", "--exclude-standard"):
            return self.untracked
        if command[:6] == (
            "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--",
        ):
            return self.ignored
        if command == ("-c", "core.hooksPath=NUL", "merge", "--ff-only", TARGET_COMMIT):
            if self.fail_merge:
                raise InstallerError("fast-forward failed")
            self.merged = True
            return ""
        raise AssertionError(f"unexpected Git command: {command!r}")


class AppUpdateInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "project"
        (self.root / ".git").mkdir(parents=True)
        self.updates_dir = self.root / "cache" / "updates"
        self.updates_dir.mkdir(parents=True)
        self.logs_dir = self.root / "logs"
        self.logs_dir.mkdir()
        self.launcher_path = self.root / "new_run_main_ui.bat"
        self.launcher_path.write_text("@echo off\n", encoding="utf-8")
        self.plan_path = self.updates_dir / "pending-test.json"
        self.ready_path = self.updates_dir / "pending-test.ready.json"
        self.result_path = self.logs_dir / "update-result.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def valid_plan(self, **overrides: Any) -> dict[str, Any]:
        plan: dict[str, Any] = {
            "schema": 1,
            "projectRoot": str(self.root),
            "expectedHead": EXPECTED_HEAD,
            "targetCommit": TARGET_COMMIT,
            "tagName": "v2.7.0",
            "remoteName": "origin",
            "branch": "main",
            "launcher": str(self.launcher_path),
            "parentPid": 12345,
            "resultPath": str(self.result_path),
            "readyPath": str(self.ready_path),
        }
        plan.update(overrides)
        return plan

    @staticmethod
    def write_plan(path: Path, plan: Mapping[str, Any]) -> None:
        path.write_text(json.dumps(dict(plan)), encoding="utf-8")

    def test_load_plan_accepts_and_normalises_a_valid_helper_plan(self) -> None:
        self.write_plan(
            self.plan_path,
            self.valid_plan(
                expectedHead=EXPECTED_HEAD.upper(),
                targetCommit=TARGET_COMMIT.upper(),
            ),
        )

        loaded = load_plan(self.plan_path)

        self.assertEqual(loaded["projectRoot"], str(self.root.resolve()))
        self.assertEqual(loaded["launcher"], str(self.launcher_path.resolve()))
        self.assertEqual(loaded["resultPath"], str(self.result_path.resolve()))
        self.assertEqual(loaded["readyPath"], str(self.ready_path.resolve()))
        self.assertEqual(loaded["expectedHead"], EXPECTED_HEAD)
        self.assertEqual(loaded["targetCommit"], TARGET_COMMIT)
        self.assertEqual(loaded["parentPid"], 12345)

    def test_load_plan_rejects_paths_outside_their_allowed_directories(self) -> None:
        outside_plan = self.root / "pending-outside.json"
        cases = {
            "plan": (outside_plan, self.valid_plan()),
            "result": (
                self.plan_path,
                self.valid_plan(resultPath=str(self.root / "result.json")),
            ),
            "ready": (
                self.plan_path,
                self.valid_plan(readyPath=str(self.logs_dir / "ready.json")),
            ),
        }

        for label, (path, plan) in cases.items():
            with self.subTest(label=label):
                self.write_plan(path, plan)
                with self.assertRaisesRegex(InstallerError, f"{label} is outside"):
                    load_plan(path)

    def test_load_plan_rejects_invalid_update_identity(self) -> None:
        cases = {
            "commit": (
                {"expectedHead": "a" * 39},
                "invalid update commit",
            ),
            "tag": (
                {"tagName": "v2.7.0-rc1"},
                "invalid Git update identity",
            ),
            "empty branch": (
                {"branch": ""},
                "invalid Git update identity",
            ),
            "remote control character": (
                {"remoteName": "origin\nmalicious"},
                "invalid Git name",
            ),
            "parent process": (
                {"parentPid": 0},
                "invalid parent process",
            ),
        }

        for label, (overrides, message) in cases.items():
            with self.subTest(label=label):
                self.write_plan(self.plan_path, self.valid_plan(**overrides))
                with self.assertRaisesRegex(InstallerError, message):
                    load_plan(self.plan_path)

    def test_load_plan_requires_the_exact_project_launcher(self) -> None:
        other_launcher = self.root / "other.bat"
        other_launcher.write_text("@echo off\n", encoding="utf-8")
        self.write_plan(
            self.plan_path,
            self.valid_plan(launcher=str(other_launcher)),
        )

        with self.assertRaisesRegex(InstallerError, "invalid launcher"):
            load_plan(self.plan_path)

    def test_apply_plan_uses_only_fast_forward_then_verifies_head(self) -> None:
        fake_git = RecordingGit()
        fake_git.root = self.root.resolve()

        result = apply_plan(self.valid_plan(), run_git=fake_git)

        self.assertEqual(
            result,
            {"ok": True, "tagName": "v2.7.0", "commit": TARGET_COMMIT},
        )
        self.assertEqual(
            fake_git.calls,
            [
                ("rev-parse", "--show-toplevel"),
                ("rev-parse", "HEAD"),
                ("branch", "--show-current"),
                ("remote", "get-url", "origin"),
                ("rev-parse", "v2.7.0^{commit}"),
                ("cat-file", "-e", f"{TARGET_COMMIT}:VERSION"),
                ("cat-file", "-e", f"{TARGET_COMMIT}:new_main_ui.py"),
                ("cat-file", "-e", f"{TARGET_COMMIT}:new_run_main_ui.bat"),
                ("cat-file", "-e", f"{TARGET_COMMIT}:frontend_dist/index.html"),
                ("show", f"{TARGET_COMMIT}:VERSION"),
                (
                    "merge-base",
                    "--is-ancestor",
                    EXPECTED_HEAD,
                    TARGET_COMMIT,
                ),
                ("diff", "--name-only", "--no-renames", "-z", EXPECTED_HEAD, TARGET_COMMIT),
                ("diff", "--name-only", "-z"),
                ("diff", "--cached", "--name-only", "-z"),
                ("ls-files", "-z", "--others", "--exclude-standard"),
                ("ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", ":(literal)src/updated.py"),
                ("-c", "core.hooksPath=NUL", "merge", "--ff-only", TARGET_COMMIT),
                ("rev-parse", "HEAD"),
            ],
        )

    def test_apply_plan_rejects_changed_checkout_and_release_identity(self) -> None:
        cases = {
            "checkout": ("head", "c" * 40, "checkout changed"),
            "branch": ("branch", "other", "branch changed"),
            "remote": ("remote_url", "https://example.com/evil/repo.git", "untrusted"),
            "tag": ("tag_target", "c" * 40, "release tag changed"),
        }

        for label, (attribute, value, message) in cases.items():
            with self.subTest(label=label):
                fake_git = RecordingGit()
                fake_git.root = self.root.resolve()
                setattr(fake_git, attribute, value)
                with self.assertRaisesRegex(InstallerError, message):
                    apply_plan(self.valid_plan(), run_git=fake_git)
                self.assertNotIn(
                    ("-c", "core.hooksPath=NUL", "merge", "--ff-only", TARGET_COMMIT),
                    fake_git.calls,
                )

    def test_apply_plan_rejects_divergence_and_overlapping_dirty_files(self) -> None:
        divergent = RecordingGit()
        divergent.root = self.root.resolve()
        divergent.ancestor = False
        with self.assertRaisesRegex(InstallerError, "not an ancestor"):
            apply_plan(self.valid_plan(), run_git=divergent)
        self.assertNotIn(("-c", "core.hooksPath=NUL", "merge", "--ff-only", TARGET_COMMIT), divergent.calls)

        conflicting = RecordingGit()
        conflicting.root = self.root.resolve()
        conflicting.changed = "src/updated.py\0"
        conflicting.unstaged = ""
        conflicting.staged = "src\\updated.py\0"
        with self.assertRaisesRegex(InstallerError, "local files changed"):
            apply_plan(self.valid_plan(), run_git=conflicting)
        self.assertNotIn(("-c", "core.hooksPath=NUL", "merge", "--ff-only", TARGET_COMMIT), conflicting.calls)

        ignored = RecordingGit()
        ignored.root = self.root.resolve()
        ignored.changed = "config/설정.json\0"
        ignored.unstaged = ""
        ignored.untracked = ""
        ignored.ignored = "CONFIG/설정.json\0"
        with self.assertRaisesRegex(InstallerError, "local files changed"):
            apply_plan(self.valid_plan(), run_git=ignored)
        self.assertNotIn(("-c", "core.hooksPath=NUL", "merge", "--ff-only", TARGET_COMMIT), ignored.calls)

    def test_apply_plan_rejects_failed_or_unverifiable_fast_forward(self) -> None:
        failed_merge = RecordingGit()
        failed_merge.root = self.root.resolve()
        failed_merge.fail_merge = True
        with self.assertRaisesRegex(InstallerError, "fast-forward failed"):
            apply_plan(self.valid_plan(), run_git=failed_merge)

        wrong_head = RecordingGit()
        wrong_head.root = self.root.resolve()
        wrong_head.verified_head = "c" * 40
        with self.assertRaisesRegex(InstallerError, "could not be verified"):
            apply_plan(self.valid_plan(), run_git=wrong_head)

    def test_apply_plan_rejects_release_with_mismatched_version_contract(self) -> None:
        fake_git = RecordingGit()
        fake_git.target_version = "2.7.1"

        with self.assertRaisesRegex(InstallerError, "VERSION does not match"):
            apply_plan(self.valid_plan(), run_git=fake_git)
        self.assertNotIn(
            ("-c", "core.hooksPath=NUL", "merge", "--ff-only", TARGET_COMMIT),
            fake_git.calls,
        )

    def test_apply_plan_rejects_another_live_app_instance(self) -> None:
        fake_git = RecordingGit()
        fake_git.root = self.root.resolve()
        with (
            patch("core.app_instance.live_app_instance_pids", return_value=[777]),
            self.assertRaisesRegex(InstallerError, "another AI Studio Pro instance"),
        ):
            apply_plan(self.valid_plan(), run_git=fake_git)
        self.assertEqual([], fake_git.calls)

    def test_run_installer_success_writes_receipt_launches_and_cleans_up(self) -> None:
        self.write_plan(self.plan_path, self.valid_plan())
        waited: list[int] = []
        applied: list[Mapping[str, Any]] = []
        launched: list[Path] = []

        def fake_waiter(pid: int) -> bool:
            waited.append(pid)
            self.assertTrue(self.ready_path.is_file())
            return True

        def fake_applier(plan: Mapping[str, Any]) -> Mapping[str, Any]:
            applied.append(plan)
            return {"ok": True, "commit": TARGET_COMMIT, "ignored": "value"}

        exit_code = run_installer(
            self.plan_path,
            waiter=fake_waiter,
            applier=fake_applier,
            launcher=launched.append,
            lock_factory=lambda _root: nullcontext(),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(waited, [12345])
        self.assertEqual(len(applied), 1)
        self.assertEqual(launched, [self.launcher_path.resolve()])
        receipt = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["tagName"], "v2.7.0")
        self.assertEqual(receipt["commit"], TARGET_COMMIT)
        self.assertNotIn("ignored", receipt)
        self.assertRegex(receipt["finishedAt"], r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertFalse(self.plan_path.exists())
        self.assertFalse(self.ready_path.exists())

    def test_run_installer_failure_relaunches_previous_app_and_cleans_up(self) -> None:
        self.write_plan(self.plan_path, self.valid_plan())
        launched: list[Path] = []

        def failing_applier(plan: Mapping[str, Any]) -> Mapping[str, Any]:
            del plan
            raise InstallerError("simulated fast-forward failure")

        exit_code = run_installer(
            self.plan_path,
            waiter=lambda pid: pid == 12345,
            applier=failing_applier,
            launcher=launched.append,
            lock_factory=lambda _root: nullcontext(),
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(launched, [self.launcher_path.resolve()])
        receipt = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["tagName"], "v2.7.0")
        self.assertIn("simulated fast-forward failure", receipt["message"])
        self.assertFalse(self.plan_path.exists())
        self.assertFalse(self.ready_path.exists())

    def test_run_installer_timeout_does_not_apply_or_duplicate_the_live_app(self) -> None:
        self.write_plan(self.plan_path, self.valid_plan())
        applied = False
        launched: list[Path] = []

        def unexpected_applier(plan: Mapping[str, Any]) -> Mapping[str, Any]:
            nonlocal applied
            applied = True
            return plan

        exit_code = run_installer(
            self.plan_path,
            waiter=lambda pid: False,
            applier=unexpected_applier,
            launcher=launched.append,
            lock_factory=lambda _root: nullcontext(),
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(applied)
        self.assertEqual(launched, [])
        receipt = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertFalse(receipt["ok"])
        self.assertIn("did not exit", receipt["message"])
        self.assertFalse(self.plan_path.exists())
        self.assertFalse(self.ready_path.exists())


if __name__ == "__main__":
    unittest.main()

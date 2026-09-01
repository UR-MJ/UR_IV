from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.backend_runtime import (
    COMFYUI_REPOSITORY,
    FORGE_REPOSITORY,
    PROJECT_ROOT,
    BackendRuntimeError,
    BackendRuntimeManager,
    CommandResult,
    LocalRuntimeAdapter,
)


COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def write_local_git_repository(
    source: Path,
    *,
    repository: str,
    branch: str,
    commit: str = COMMIT_A,
) -> None:
    git_dir = source / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="ascii")
    (git_dir / "refs" / "heads" / branch).write_text(
        commit + "\n", encoding="ascii"
    )
    (git_dir / "config").write_text(
        f'[remote "origin"]\n\turl = {repository}\n', encoding="utf-8"
    )


def write_windows_venv_python(source: Path, folder: str = ".venv") -> Path:
    python = source / folder / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b"linked python")
    return python


class LocalRuntimeAdapterTests(unittest.TestCase):
    def test_shutdown_cancels_an_owned_command_process(self):
        adapter = LocalRuntimeAdapter()
        ready = threading.Event()
        errors: list[Exception] = []

        def run_command() -> None:
            try:
                adapter.run(
                    [
                        sys.executable,
                        "-u",
                        "-c",
                        "import time; print('ready', flush=True); time.sleep(30)",
                    ],
                    timeout=60,
                    on_line=lambda line: ready.set() if line == "ready" else None,
                )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        worker = threading.Thread(target=run_command, daemon=True)
        worker.start()
        self.assertTrue(ready.wait(timeout=3))
        adapter.shutdown()
        worker.join(timeout=6)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], BackendRuntimeError)
        self.assertEqual(errors[0].code, "COMMAND_CANCELLED")


class FakeProcess:
    def __init__(self, pid: int, *, early_exit: bool = False):
        self.pid = pid
        self.running = not early_exit
        self.returncode = 1 if early_exit else None
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return None if self.running else self.returncode

    def terminate(self):
        self.terminate_calls += 1
        self.running = False
        self.returncode = 0

    def wait(self, timeout=None):
        if self.running:
            raise TimeoutError(f"process {self.pid} is still running")
        return int(self.returncode or 0)

    def kill(self):
        self.kill_calls += 1
        self.running = False
        self.returncode = -9


class FakeRuntimeAdapter:
    """Filesystem-backed fake; no command ever reaches GitHub, PyPI or HTTP."""

    def __init__(self):
        self.calls: list[dict] = []
        self.start_calls: list[dict] = []
        self.probe_calls: list[tuple[str, str, float]] = []
        self.probe_entered = threading.Event()
        self.processes: list[FakeProcess] = []
        self.start_behaviours: list[str] = []
        self.unavailable_ports: set[int] = set()
        self.remote_heads = {
            FORGE_REPOSITORY: COMMIT_A,
            COMFYUI_REPOSITORY: COMMIT_A,
        }
        self.extension_requirements = False
        self.uv_path: str | None = None
        self._next_pid = 4100
        self.probe_overrides: dict[str, bool] = {}

    def which(self, executable: str):
        if executable == "git":
            return "C:\\fake\\git.exe"
        if executable == "uv":
            return self.uv_path
        if executable == "powershell.exe":
            return "C:\\fake\\powershell.exe"
        # Force the module to use this test interpreter for venv creation.
        return None

    def run(self, argv, *, cwd=None, env=None, timeout=None, on_line=None):
        args = [str(item) for item in argv]
        workdir = Path(cwd).resolve() if cwd is not None else None
        self.calls.append({
            "argv": args,
            "cwd": workdir,
            "env": dict(env or {}),
            "timeout": timeout,
        })
        if on_line:
            on_line("fake adapter operation")

        if len(args) >= 2 and args[:2] == ["git", "ls-remote"]:
            repository = args[2]
            commit = self.remote_heads.get(repository, COMMIT_A)
            ref = args[3] if len(args) > 3 else "HEAD"
            return CommandResult(0, f"{commit}\t{ref}\n")

        if len(args) >= 2 and args[:2] == ["git", "clone"]:
            repository = args[-2]
            destination = Path(args[-1])
            branch = "main"
            if "--branch" in args:
                branch = args[args.index("--branch") + 1]
            destination.mkdir(parents=True, exist_ok=False)
            git_dir = destination / ".git"
            (git_dir / "refs" / "heads").mkdir(parents=True)
            (git_dir / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="ascii")
            (git_dir / "refs" / "heads" / branch).write_text(
                self.remote_heads.get(repository, COMMIT_A) + "\n", encoding="ascii"
            )
            (git_dir / "config").write_text(
                f'[remote "origin"]\n\turl = {repository}\n', encoding="utf-8"
            )
            (destination / ".fake-repository").write_text(repository, encoding="utf-8")
            (destination / ".fake-branch").write_text(branch, encoding="utf-8")
            (destination / ".fake-commit").write_text(
                self.remote_heads.get(repository, COMMIT_A), encoding="utf-8"
            )
            if repository == FORGE_REPOSITORY:
                (destination / "launch.py").write_text("# forge", encoding="utf-8")
            elif repository == COMFYUI_REPOSITORY:
                (destination / "main.py").write_text("# comfy", encoding="utf-8")
                (destination / "requirements.txt").write_text("torch\n", encoding="utf-8")
                (destination / "manager_requirements.txt").write_text(
                    "comfyui_manager\n", encoding="utf-8"
                )
            else:
                (destination / "extension.py").write_text("# extension", encoding="utf-8")
                if self.extension_requirements:
                    (destination / "requirements.txt").write_text(
                        "extension-dependency\n", encoding="utf-8"
                    )
            return CommandResult(0, "cloned")

        if len(args) >= 3 and args[:3] == ["git", "rev-parse", "HEAD"]:
            return CommandResult(0, self._read(workdir, ".fake-commit"))

        if len(args) >= 3 and args[:3] == ["git", "describe", "--tags"]:
            commit = self._read(workdir, ".fake-commit")
            return CommandResult(0, f"test-{commit[:12]}")

        if len(args) >= 3 and args[:3] == ["git", "branch", "--show-current"]:
            return CommandResult(0, self._read(workdir, ".fake-branch") or "main")

        if len(args) >= 4 and args[:4] == ["git", "config", "--get", "remote.origin.url"]:
            return CommandResult(0, self._read(workdir, ".fake-repository"))

        if len(args) >= 3 and args[:3] == ["git", "status", "--porcelain"]:
            return CommandResult(0, self._read(workdir, ".fake-dirty"))

        if len(args) >= 3 and args[:3] == ["git", "pull", "--ff-only"]:
            repository = self._read(workdir, ".fake-repository")
            commit = self.remote_heads.get(repository, COMMIT_A)
            (workdir / ".fake-commit").write_text(commit, encoding="utf-8")
            branch = self._read(workdir, ".fake-branch") or "main"
            (workdir / ".git" / "refs" / "heads" / branch).write_text(
                commit + "\n", encoding="ascii"
            )
            return CommandResult(0, "fast-forward")

        if len(args) >= 4 and args[1:3] == ["-m", "venv"]:
            self._make_venv(Path(args[3]))
            return CommandResult(0, "venv created")

        if self.uv_path and args[:2] == [self.uv_path, "venv"]:
            self._make_venv(Path(args[2]))
            return CommandResult(0, "uv venv created")

        if args and args[0].casefold().endswith("powershell.exe") and "New-Item" in args[-1]:
            # A real junction is not needed for lifecycle tests.  The module only
            # requires the mount to exist after the injected command succeeds.
            Path(env["AISTUDIO_JUNCTION_PATH"]).mkdir(parents=True, exist_ok=True)
            return CommandResult(0, "junction created")

        # pip, Forge bootstrap and Comfy import verification are all local fake
        # successes. Their argv is asserted by individual tests below.
        return CommandResult(0, "ok")

    def start(self, argv, *, cwd, env, log_path):
        behaviour = self.start_behaviours.pop(0) if self.start_behaviours else "healthy"
        process = FakeProcess(self._next_pid, early_exit=behaviour == "early_exit")
        self._next_pid += 1
        self.processes.append(process)
        call = {
            "argv": [str(item) for item in argv],
            "cwd": Path(cwd).resolve(),
            "env": dict(env),
            "log_path": Path(log_path),
            "process": process,
        }
        self.start_calls.append(call)
        return process

    def probe(self, url: str, path: str, timeout: float = 2.0):
        self.probe_calls.append((url, path, timeout))
        self.probe_entered.set()
        override_key = f"{url}{path}"
        if override_key in self.probe_overrides:
            return self.probe_overrides[override_key]
        if not self.start_calls:
            return False
        latest = self.start_calls[-1]["process"]
        return bool(latest.poll() is None)

    def port_available(self, host: str, port: int):
        return int(port) not in self.unavailable_ports

    @staticmethod
    def _read(folder: Path | None, filename: str):
        if folder is None:
            return ""
        path = folder / filename
        return path.read_text(encoding="utf-8").strip() if path.is_file() else ""

    @staticmethod
    def _make_venv(root: Path):
        python = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_bytes(b"fake python")


class BlockingRuntimeAdapter(FakeRuntimeAdapter):
    """Blocks the first remote check so concurrency is tested via the Interface."""

    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self._blocked_once = False

    def run(self, argv, *, cwd=None, env=None, timeout=None, on_line=None):
        args = [str(item) for item in argv]
        if args[:2] == ["git", "ls-remote"] and not self._blocked_once:
            self._blocked_once = True
            self.entered.set()
            if not self.release.wait(timeout=2):
                raise AssertionError("test did not release the fake remote check")
        return super().run(
            argv, cwd=cwd, env=env, timeout=timeout, on_line=on_line
        )


class BackendRuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_dir.name)
        self.runtime_root = self.temp / "managed_backends"
        self.config_path = self.temp / "backend_runtime.json"
        self.adapter = FakeRuntimeAdapter()

        model_root = self.temp / "models"
        self.model_paths = {
            "checkpoint_dir": model_root / "checkpoints",
            "lora_dir": model_root / "loras",
            "vae_dir": model_root / "vae",
            "text_encoder_dir": model_root / "text_encoders",
        }
        for folder in self.model_paths.values():
            folder.mkdir(parents=True)
        self.model_patch = patch(
            "core.forge_modules.get_forge_paths", return_value=self.model_paths
        )
        self.model_patch.start()
        self.manager = self.make_manager()

    def tearDown(self):
        self.manager.stop_all_owned()
        self.model_patch.stop()
        self.temp_dir.cleanup()

    def make_manager(self, *, adapter=None):
        return BackendRuntimeManager(
            config_path=self.config_path,
            runtime_root=self.runtime_root,
            adapter=adapter or self.adapter,
            health_timeout=0.05,
        )

    def install(self, engine="forge"):
        return self.manager.execute(engine, "install")


class BackendRuntimeConfigurationTests(BackendRuntimeTestCase):
    def test_default_root_is_project_user_data_unless_explicitly_overridden(self):
        fake_project = self.temp / "project"
        with patch.dict(
            os.environ,
            {"LOCALAPPDATA": str(self.temp / "local_app_data")},
            clear=False,
        ), patch("core.backend_runtime.PROJECT_ROOT", fake_project):
            os.environ.pop("AISTUDIO_MANAGED_BACKENDS_DIR", None)
            manager = BackendRuntimeManager(
                config_path=self.temp / "default-root-config.json",
                adapter=self.adapter,
            )
            self.assertEqual(
                Path(manager.snapshot()["runtimeRoot"]),
                (fake_project / "user_data" / "managed_backends").resolve(),
            )

        override = self.temp / "explicit-runtime-root"
        with patch.dict(
            os.environ,
            {"AISTUDIO_MANAGED_BACKENDS_DIR": str(override)},
            clear=False,
        ):
            manager = BackendRuntimeManager(
                config_path=self.temp / "override-root-config.json",
                adapter=self.adapter,
            )
            self.assertEqual(
                Path(manager.snapshot()["runtimeRoot"]), override.resolve()
            )

    def test_configure_persists_atomically_and_aliases_forge_neo(self):
        external_extensions = self.temp / "external-forge" / "extensions"
        external_extensions.mkdir(parents=True)

        state = self.manager.configure(
            "forge_neo",
            {"active": True, "autoStart": True, "extensionDir": str(external_extensions)},
        )

        self.assertEqual(state["activeEngine"], "forge")
        self.assertTrue(state["engines"]["forge"]["autoStart"])
        self.assertEqual(
            Path(state["engines"]["forge"]["extensionDir"]),
            external_extensions.resolve(),
        )
        self.assertTrue(self.config_path.is_file())
        self.assertFalse(self.config_path.with_suffix(self.config_path.suffix + ".tmp").exists())
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["activeEngine"], "forge")

        restored = self.make_manager().snapshot()
        self.assertEqual(restored["activeEngine"], "forge")
        self.assertTrue(restored["engines"]["forge"]["autoStart"])
        self.assertEqual(
            Path(restored["engines"]["forge"]["extensionDir"]),
            external_extensions.resolve(),
        )

    def test_auto_start_is_unique_and_use_does_not_silently_change_it(self):
        self.manager.configure("forge", {"autoStart": True})
        selected = self.manager.configure("comfyui", {"autoStart": True})
        self.assertFalse(selected["engines"]["forge"]["autoStart"])
        self.assertTrue(selected["engines"]["comfyui"]["autoStart"])

        self.manager.execute("forge", "install")
        used = self.manager.execute("forge", "use")
        self.assertEqual(used["snapshot"]["activeEngine"], "forge")
        self.assertFalse(used["snapshot"]["engines"]["forge"]["autoStart"])
        self.assertTrue(used["snapshot"]["engines"]["comfyui"]["autoStart"])

    def test_structural_and_project_paths_are_rejected_as_extension_roots(self):
        unsafe_paths = [
            PROJECT_ROOT / "core",
            self.runtime_root,
            self.runtime_root / "forge",
            self.runtime_root / "forge" / "releases",
        ]
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        (self.runtime_root / "forge" / "releases").mkdir(parents=True, exist_ok=True)

        for unsafe in unsafe_paths:
            with self.subTest(path=str(unsafe)):
                with self.assertRaises(BackendRuntimeError) as caught:
                    self.manager.configure("forge", {"extensionDir": str(unsafe)})
                self.assertEqual(caught.exception.code, "EXTENSION_PATH_UNSAFE")

    def test_external_engine_extension_roots_cannot_overlap(self):
        forge_root = self.temp / "external-engines"
        comfy_nested = forge_root / "custom_nodes"
        comfy_nested.mkdir(parents=True)
        self.manager.configure("forge", {"extensionDir": str(forge_root)})

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.configure("comfyui", {"extensionDir": str(comfy_nested)})

        self.assertEqual(caught.exception.code, "EXTENSION_PATH_CONFLICT")

    @unittest.skipUnless(os.name == "nt", "junction command contract is Windows-only")
    def test_junction_path_is_passed_out_of_band_not_interpolated_into_shell(self):
        external = self.temp / "external&literal" / "extensions"
        external.mkdir(parents=True)

        self.manager.execute(
            "forge", "save_extension_dir", {"extensionDir": str(external)}
        )

        junction_calls = [
            call for call in self.adapter.calls
            if call["argv"] and call["argv"][0].casefold().endswith("powershell.exe")
        ]
        self.assertEqual(len(junction_calls), 1)
        call = junction_calls[0]
        self.assertEqual(call["env"]["AISTUDIO_JUNCTION_TARGET"], str(external.resolve()))
        self.assertNotIn(str(external.resolve()), " ".join(call["argv"]))

    def test_forge_rejects_comfy_managed_shared_extension_folder(self):
        comfy_extensions = (
            self.runtime_root / "comfyui" / "shared" / "custom_nodes"
        )
        comfy_extensions.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.configure(
                "forge", {"extensionDir": str(comfy_extensions)}
            )

        self.assertEqual(caught.exception.code, "EXTENSION_PATH_UNSAFE")


class BackendRuntimeSnapshotTests(BackendRuntimeTestCase):
    def test_snapshot_never_runs_remote_git_or_http(self):
        extension_root = self.runtime_root / "forge" / "shared" / "extensions"
        extension = extension_root / "test-extension"
        git_dir = extension / ".git"
        (git_dir / "refs" / "heads").mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
        (git_dir / "refs" / "heads" / "main").write_text(
            COMMIT_A + "\n", encoding="ascii"
        )
        (git_dir / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/example/test-extension.git\n',
            encoding="utf-8",
        )
        (extension / ".fake-repository").write_text(
            "https://github.com/example/test-extension.git", encoding="utf-8"
        )
        (extension / ".fake-branch").write_text("main", encoding="utf-8")
        (extension / ".fake-commit").write_text(COMMIT_A, encoding="utf-8")
        self.adapter.calls.clear()

        snapshot = self.manager.snapshot()

        self.assertEqual(snapshot["engines"]["forge"]["extensions"][0]["id"], "test-extension")
        self.assertEqual(self.adapter.calls, [], "snapshot() must not spawn commands")
        self.assertEqual(self.adapter.probe_calls, [], "snapshot() must not probe HTTP")

    def test_forge_and_comfy_installations_are_isolated(self):
        forge_result = self.manager.execute("forge", "install")
        comfy_result = self.manager.execute("comfyui", "install")
        snapshot = self.manager.snapshot()

        self.assertTrue(forge_result["ok"])
        self.assertTrue(comfy_result["ok"])
        forge = snapshot["engines"]["forge"]
        comfy = snapshot["engines"]["comfyui"]
        self.assertTrue(forge["installed"])
        self.assertTrue(comfy["installed"])
        self.assertNotEqual(Path(forge["sourceRoot"]), Path(comfy["sourceRoot"]))
        self.assertNotEqual(Path(forge["dataRoot"]), Path(comfy["dataRoot"]))
        self.assertNotEqual(Path(forge["extensionDir"]), Path(comfy["extensionDir"]))

        clone_calls = [call["argv"] for call in self.adapter.calls if call["argv"][:2] == ["git", "clone"]]
        self.assertTrue(any("--branch" in call and "neo" in call and FORGE_REPOSITORY in call for call in clone_calls))
        self.assertTrue(any("--branch" in call and "master" in call and COMFYUI_REPOSITORY in call for call in clone_calls))


class BackendRuntimeLinkedInstallTests(BackendRuntimeTestCase):
    def make_linked_forge(self) -> Path:
        root = self.temp / "existing-forge"
        root.mkdir()
        (root / "launch.py").write_text("# linked forge", encoding="utf-8")
        write_windows_venv_python(root, "venv")
        write_local_git_repository(
            root, repository=FORGE_REPOSITORY, branch="neo"
        )
        for relative in (
            "extensions",
            "models/Stable-diffusion",
            "models/diffusion_models",
            "models/Lora",
            "models/VAE",
            "models/text_encoder",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        return root

    def make_linked_comfy(self) -> Path:
        root = self.temp / "existing-comfy"
        root.mkdir()
        (root / "main.py").write_text("# linked comfy", encoding="utf-8")
        write_windows_venv_python(root)
        write_local_git_repository(
            root, repository=COMFYUI_REPOSITORY, branch="master"
        )
        for relative in (
            "custom_nodes",
            "models/checkpoints",
            "models/diffusion_models",
            "models/unet",
            "models/loras",
            "models/vae",
            "models/text_encoders",
            "models/clip",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def source_manifest(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_broad_existing_install_boundaries_are_rejected(self):
        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute(
                "forge",
                "set_install_root",
                {"existingRoot": str(self.runtime_root)},
            )
        self.assertEqual(caught.exception.code, "LINKED_INSTALL_PATH_UNSAFE")

    def test_direct_configure_cannot_bypass_running_model_topology_transaction(self):
        forge_root = self.make_linked_forge()
        comfy_root = self.make_linked_comfy()
        self.manager.execute(
            "forge", "set_install_root", {"existingRoot": str(forge_root)}
        )
        self.manager.execute("forge", "start")

        for patch_payload in (
            {"sourceMode": "existing", "existingRoot": str(comfy_root)},
            {"existingRoot": str(comfy_root)},
        ):
            with self.subTest(patch=patch_payload):
                with self.assertRaises(BackendRuntimeError) as caught:
                    self.manager.configure("comfyui", patch_payload)
                self.assertEqual(
                    caught.exception.code, "MODEL_TOPOLOGY_TRANSACTION_REQUIRED"
                )
                self.assertEqual(caught.exception.stage, "configure")
                self.assertEqual(
                    caught.exception.details.get("runningEngine"), "forge"
                )

        snapshot = self.manager.snapshot()
        self.assertTrue(snapshot["engines"]["forge"]["running"])
        self.assertEqual(snapshot["engines"]["comfyui"]["sourceMode"], "managed")
        self.assertEqual(snapshot["engines"]["comfyui"]["existingRoot"], "")

    def test_linked_forge_persists_exact_layout_and_starts_without_installing(self):
        root = self.make_linked_forge()
        before = self.source_manifest(root)

        linked = self.manager.execute(
            "forge", "set_install_root", {"existingRoot": str(root)}
        )
        forge = linked["snapshot"]["engines"]["forge"]

        self.assertEqual(forge["sourceMode"], "existing")
        self.assertEqual(Path(forge["existingRoot"]), root.resolve())
        self.assertEqual(Path(forge["installRoot"]), root.resolve())
        self.assertEqual(Path(forge["sourceRoot"]), root.resolve())
        self.assertEqual(
            Path(forge["pythonPath"]),
            (root / "venv" / "Scripts" / "python.exe").resolve(),
        )
        self.assertFalse(forge["portable"])
        self.assertFalse(forge["extensionDirApproved"])
        self.assertFalse(forge["extensionWritable"])
        self.assertEqual(Path(forge["extensionDir"]), (root / "extensions").resolve())
        self.assertEqual(
            forge["modelPaths"]["checkpoints"][0],
            str(self.model_paths["checkpoint_dir"].resolve()),
            "the existing Forge Settings override must keep first priority",
        )
        self.assertIn(
            str((root / "models" / "Stable-diffusion").resolve()),
            forge["modelPaths"]["checkpoints"],
        )

        self.adapter.calls.clear()
        started = self.manager.execute("forge", "start")
        start_call = self.adapter.start_calls[-1]
        self.assertEqual(started["apiUrl"], "http://127.0.0.1:17860")
        self.assertEqual(start_call["cwd"], root.resolve())
        self.assertEqual(
            Path(start_call["argv"][0]),
            (root / "venv" / "Scripts" / "python.exe").resolve(),
        )
        self.assertEqual(
            Path(start_call["argv"][start_call["argv"].index("--data-dir") + 1]),
            self.runtime_root / "forge" / "data",
        )
        self.assertIn("--skip-prepare-environment", start_call["argv"])
        forbidden_calls = [
            call["argv"]
            for call in self.adapter.calls
            if call["argv"][:2] == ["git", "clone"]
            or "pip" in call["argv"]
            or call["argv"][1:3] == ["-m", "venv"]
            or any(Path(part).name.casefold() == "webui-user.bat" for part in call["argv"])
        ]
        self.assertEqual(
            forbidden_calls, [],
            "linked start must not clone, create a venv, install packages or run user.bat",
        )
        self.manager.execute("forge", "stop")
        self.assertEqual(self.source_manifest(root), before)

        restored = self.make_manager().snapshot()["engines"]["forge"]
        self.assertEqual(restored["sourceMode"], "existing")
        self.assertEqual(Path(restored["sourceRoot"]), root.resolve())

    def test_linked_comfy_detects_git_venv_and_both_portable_selection_levels(self):
        direct = self.make_linked_comfy()
        direct_before = self.source_manifest(direct)
        linked = self.manager.execute(
            "comfyui", "set_install_root", {"installRoot": str(direct)}
        )
        comfy = linked["snapshot"]["engines"]["comfyui"]

        self.assertTrue(comfy["installed"])
        self.assertFalse(comfy["portable"])
        self.assertEqual(linked["snapshot"]["primaryModelEngine"], "comfyui")
        self.assertEqual(linked["snapshot"]["activeEngine"], "")
        direct_start = self.manager.execute("comfyui", "start")
        direct_argv = self.adapter.start_calls[-1]["argv"]
        self.assertNotIn("-s", direct_argv)
        self.assertNotIn("--windows-standalone-build", direct_argv)
        self.assertNotIn(
            "--enable-manager", direct_argv,
            "linked Comfy must not expose manager writes to the external Python/custom_nodes",
        )
        self.assertTrue(direct_start["ok"])
        self.manager.execute("comfyui", "stop")
        self.assertEqual(self.source_manifest(direct), direct_before)

        outer = self.temp / "ComfyUI_windows_portable"
        inner = outer / "ComfyUI"
        inner.mkdir(parents=True)
        (inner / "main.py").write_text("# portable comfy", encoding="utf-8")
        (inner / "comfyui_version.py").write_text(
            '__version__ = "0.31.0"\n', encoding="utf-8"
        )
        embedded = outer / "python_embeded" / "python.exe"
        embedded.parent.mkdir()
        embedded.write_bytes(b"portable python")
        (inner / "custom_nodes").mkdir()
        (inner / "models" / "loras").mkdir(parents=True)

        self.manager.execute(
            "comfyui", "set_install_root", {"path": str(outer)}
        )
        portable = self.manager.snapshot()["engines"]["comfyui"]
        self.assertTrue(portable["portable"])
        self.assertEqual(Path(portable["installRoot"]), outer.resolve())
        self.assertEqual(Path(portable["sourceRoot"]), inner.resolve())
        self.assertEqual(Path(portable["pythonPath"]), embedded.resolve())
        self.assertEqual(portable["version"], "0.31.0")

        self.manager.execute("comfyui", "start")
        portable_argv = self.adapter.start_calls[-1]["argv"]
        self.assertEqual(portable_argv[:3], [str(embedded.resolve()), "-s", str(inner.resolve() / "main.py")])
        self.assertEqual(portable_argv[3], "--windows-standalone-build")
        self.assertNotIn("--enable-manager", portable_argv)
        self.manager.execute("comfyui", "stop")

        self.manager.execute(
            "comfyui", "set_install_root", {"existingRoot": str(inner)}
        )
        inner_selected = self.manager.snapshot()["engines"]["comfyui"]
        self.assertEqual(Path(inner_selected["existingRoot"]), inner.resolve())
        self.assertEqual(Path(inner_selected["installRoot"]), outer.resolve())
        self.assertTrue(inner_selected["portable"])

    def test_linking_inactive_source_restarts_active_backend_with_new_shared_paths(self):
        comfy_root = self.make_linked_comfy()
        self.manager.execute(
            "comfyui", "set_install_root", {"existingRoot": str(comfy_root)}
        )
        self.manager.execute("comfyui", "start")
        original_comfy = self.adapter.start_calls[-1]["process"]
        forge_root = self.make_linked_forge()
        forge_before = self.source_manifest(forge_root)
        comfy_before = self.source_manifest(comfy_root)

        self.manager.execute(
            "forge", "set_install_root", {"existingRoot": str(forge_root)}
        )

        restarted = self.adapter.start_calls[-1]
        self.assertEqual(original_comfy.terminate_calls, 1)
        self.assertEqual(restarted["env"]["AISTUDIO_MANAGED_ENGINE"], "comfyui")
        self.assertTrue(self.manager.snapshot()["engines"]["comfyui"]["running"])
        config_path = Path(
            restarted["argv"][restarted["argv"].index("--extra-model-paths-config") + 1]
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIn(
            str((forge_root / "models" / "Stable-diffusion").resolve()),
            config["aistudio_shared"]["checkpoints"].splitlines(),
        )
        self.assertEqual(self.source_manifest(forge_root), forge_before)
        self.assertEqual(self.source_manifest(comfy_root), comfy_before)

    def test_linked_source_restart_failure_restores_state_and_previous_backend(self):
        comfy_root = self.make_linked_comfy()
        self.manager.execute(
            "comfyui", "set_install_root", {"existingRoot": str(comfy_root)}
        )
        self.manager.execute("comfyui", "start")
        original_comfy = self.adapter.start_calls[-1]["process"]
        forge_root = self.make_linked_forge()
        forge_before = self.source_manifest(forge_root)
        self.adapter.start_behaviours.extend(["early_exit", "healthy"])

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute(
                "forge", "set_install_root", {"existingRoot": str(forge_root)}
            )

        self.assertEqual(caught.exception.code, "PROCESS_EXITED_EARLY")
        snapshot = self.manager.snapshot()
        self.assertEqual(snapshot["primaryModelEngine"], "comfyui")
        self.assertEqual(snapshot["engines"]["forge"]["sourceMode"], "managed")
        self.assertFalse(snapshot["engines"]["forge"]["installed"])
        self.assertTrue(snapshot["engines"]["comfyui"]["running"])
        self.assertTrue(snapshot["engines"]["comfyui"]["healthy"])
        self.assertEqual(original_comfy.terminate_calls, 1)
        self.assertEqual(len(self.adapter.start_calls), 3)
        self.assertEqual(self.source_manifest(forge_root), forge_before)

    def test_linked_check_is_read_only_and_update_is_explicitly_rejected(self):
        root = self.make_linked_forge()
        self.manager.execute(
            "forge", "set_install_root", {"existingRoot": str(root)}
        )
        self.adapter.remote_heads[FORGE_REPOSITORY] = COMMIT_B
        before = self.source_manifest(root)

        checked = self.manager.execute("forge", "check_update")

        self.assertEqual(checked["localCommit"], COMMIT_A)
        self.assertEqual(checked["remoteCommit"], COMMIT_B)
        self.assertTrue(checked["updateAvailable"])
        self.assertEqual(self.source_manifest(root), before)
        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute("forge", "update")
        self.assertEqual(caught.exception.code, "LINKED_UPDATE_UNSUPPORTED")
        self.assertFalse(any(call["argv"][:2] == ["git", "clone"] for call in self.adapter.calls))
        self.assertFalse(any("pip" in call["argv"] for call in self.adapter.calls))

    def test_linked_comfy_reads_declared_version_without_executing_or_requiring_git(self):
        outer = self.temp / "portable-version-only"
        source = outer / "ComfyUI"
        source.mkdir(parents=True)
        (source / "main.py").write_text("# portable comfy", encoding="utf-8")
        (source / "pyproject.toml").write_text(
            '[project]\nname = "comfyui"\nversion = "0.30.0"\n',
            encoding="utf-8",
        )
        embedded = outer / "python_embedded" / "python.exe"
        embedded.parent.mkdir()
        embedded.write_bytes(b"portable python")
        (source / "custom_nodes").mkdir()
        before = self.source_manifest(outer)

        linked = self.manager.execute(
            "comfyui", "set_install_root", {"existingRoot": str(outer)}
        )

        self.assertEqual(linked["snapshot"]["engines"]["comfyui"]["version"], "0.30.0")
        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute("comfyui", "check_update")
        self.assertEqual(caught.exception.code, "LINKED_VERSION_UNAVAILABLE")
        self.assertEqual(self.source_manifest(outer), before)

    def test_primary_model_source_is_independent_validated_and_orders_shared_paths(self):
        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute("forge", "set_primary_model_engine")
        self.assertEqual(caught.exception.code, "PRIMARY_MODEL_SOURCE_UNAVAILABLE")

        forge_root = self.make_linked_forge()
        comfy_root = self.make_linked_comfy()
        self.manager.execute(
            "forge", "set_install_root", {"existingRoot": str(forge_root)}
        )
        self.manager.execute(
            "comfyui", "set_install_root", {"existingRoot": str(comfy_root)}
        )
        selected = self.manager.execute(
            "comfyui", "set_primary_model_engine"
        )
        snapshot = selected["snapshot"]
        self.assertEqual(snapshot["primaryModelEngine"], "comfyui")
        self.assertEqual(snapshot["activeEngine"], "")
        self.assertEqual(
            set(snapshot["engines"]["comfyui"]["modelPaths"]),
            {"checkpoints", "diffusion_models", "loras", "vae", "text_encoders"},
        )

        self.manager.execute("forge", "start")
        forge_argv = self.adapter.start_calls[-1]["argv"]
        checkpoint_values = [
            forge_argv[index + 1]
            for index, value in enumerate(forge_argv[:-1])
            if value == "--ckpt-dirs"
        ]
        self.assertEqual(
            checkpoint_values[0], str((comfy_root / "models" / "checkpoints").resolve())
        )

        self.manager.execute("comfyui", "start")
        comfy_argv = self.adapter.start_calls[-1]["argv"]
        config_path = Path(
            comfy_argv[comfy_argv.index("--extra-model-paths-config") + 1]
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        shared_checkpoints = config["aistudio_shared"]["checkpoints"].splitlines()
        self.assertEqual(
            shared_checkpoints[0],
            str((comfy_root / "models" / "checkpoints").resolve()),
        )
        self.assertIn(str(self.model_paths["checkpoint_dir"].resolve()), shared_checkpoints)

    def test_auto_detected_extension_folder_is_read_only_until_explicitly_saved(self):
        root = self.make_linked_forge()
        self.manager.execute(
            "forge", "set_install_root", {"existingRoot": str(root)}
        )

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute(
                "forge",
                "install_extension",
                {"repoUrl": "https://github.com/example/plugin.git"},
            )
        self.assertEqual(caught.exception.code, "EXTENSION_WRITE_NOT_APPROVED")
        self.assertFalse((root / "extensions" / "plugin").exists())

        approved = self.manager.execute(
            "forge",
            "save_extension_dir",
            {"extensionDir": str(root / "extensions")},
        )
        forge = approved["snapshot"]["engines"]["forge"]
        self.assertTrue(forge["extensionDirApproved"])
        self.assertTrue(forge["extensionWritable"])

    def test_use_managed_install_clears_link_without_deleting_external_files(self):
        root = self.make_linked_forge()
        before = self.source_manifest(root)
        self.manager.execute(
            "forge", "set_install_root", {"existingRoot": str(root)}
        )

        switched = self.manager.execute("forge", "use_managed_install")
        forge = switched["snapshot"]["engines"]["forge"]

        self.assertEqual(forge["sourceMode"], "managed")
        self.assertEqual(forge["existingRoot"], "")
        self.assertFalse(forge["installed"])
        self.assertEqual(self.source_manifest(root), before)


class BackendRuntimeLaunchTests(BackendRuntimeTestCase):
    def test_forge_never_passes_bare_uv_hook_into_the_managed_venv(self):
        self.adapter.uv_path = "C:\\fake\\uv.exe"

        self.manager.execute("forge", "install")
        self.manager.execute("forge", "start")

        forge_commands = [
            call["argv"] for call in self.adapter.calls
            if any(Path(part).name.casefold() == "launch.py" for part in call["argv"])
        ]
        self.assertTrue(forge_commands)
        self.assertTrue(all("--uv" not in command for command in forge_commands))
        self.assertNotIn("--uv", self.adapter.start_calls[-1]["argv"])
        self.assertTrue(any(call["argv"][:2] == [self.adapter.uv_path, "venv"] for call in self.adapter.calls))

    def test_near_simultaneous_engine_start_is_rejected_then_retry_switches(self):
        self.manager.execute("forge", "install")
        self.manager.execute("comfyui", "install")
        manager = BackendRuntimeManager(
            config_path=self.config_path,
            runtime_root=self.runtime_root,
            adapter=self.adapter,
            health_timeout=1.0,
        )
        forge_health = "http://127.0.0.1:17860/sdapi/v1/samplers"
        self.adapter.probe_overrides[forge_health] = False
        errors: list[Exception] = []

        def start(engine: str) -> None:
            try:
                manager.execute(engine, "start")
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        forge_worker = threading.Thread(target=start, args=("forge",), daemon=True)
        forge_worker.start()
        deadline = time.monotonic() + 0.5
        while not self.adapter.start_calls and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(self.adapter.start_calls), 1)

        comfy_worker = threading.Thread(target=start, args=("comfyui",), daemon=True)
        comfy_worker.start()
        time.sleep(0.05)
        self.assertEqual(
            len(self.adapter.start_calls), 1,
            "the second engine must not enter while the first transaction is active",
        )
        comfy_worker.join(timeout=1)
        self.assertFalse(comfy_worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], BackendRuntimeError)
        self.assertEqual(errors[0].code, "OPERATION_BUSY")

        self.adapter.probe_overrides[forge_health] = True
        forge_worker.join(timeout=2)
        self.assertFalse(forge_worker.is_alive())
        self.assertEqual(len(self.adapter.start_calls), 1)
        self.assertTrue(manager.snapshot()["engines"]["forge"]["running"])
        self.assertFalse(manager.snapshot()["engines"]["comfyui"]["running"])

        retried = manager.execute("comfyui", "start")

        self.assertTrue(retried["activate"])
        self.assertEqual(len(self.adapter.start_calls), 2)
        self.assertFalse(manager.snapshot()["engines"]["forge"]["running"])
        self.assertTrue(manager.snapshot()["engines"]["comfyui"]["running"])
        manager.stop_all_owned()

    def test_launch_argv_uses_private_ports_data_and_forge_model_paths(self):
        self.manager.execute("forge", "install")
        forge_start = self.manager.execute("forge", "start")
        forge_call = self.adapter.start_calls[-1]
        forge_argv = forge_call["argv"]

        self.assertEqual(forge_start["apiUrl"], "http://127.0.0.1:17860")
        self.assertIn("--api", forge_argv)
        self.assertIn("--api-server-stop", forge_argv)
        self.assertEqual(forge_argv[forge_argv.index("--port") + 1], "17860")
        self.assertEqual(
            Path(forge_argv[forge_argv.index("--data-dir") + 1]),
            self.runtime_root / "forge" / "data",
        )
        expected_flags = {
            "--ckpt-dirs": self.model_paths["checkpoint_dir"],
            "--lora-dirs": self.model_paths["lora_dir"],
            "--vae-dirs": self.model_paths["vae_dir"],
            "--text-encoder-dirs": self.model_paths["text_encoder_dir"],
        }
        for flag, expected_path in expected_flags.items():
            self.assertEqual(Path(forge_argv[forge_argv.index(flag) + 1]), expected_path)
        self.assertEqual(forge_call["env"]["AISTUDIO_MANAGED_ENGINE"], "forge")
        self.assertTrue(forge_call["env"]["AISTUDIO_LAUNCH_NONCE"])

        self.manager.execute("comfyui", "install")
        comfy_start = self.manager.execute("comfyui", "start")
        comfy_argv = self.adapter.start_calls[-1]["argv"]
        self.assertEqual(comfy_start["apiUrl"], "http://127.0.0.1:18188")
        self.assertEqual(comfy_argv[comfy_argv.index("--listen") + 1], "127.0.0.1")
        self.assertEqual(comfy_argv[comfy_argv.index("--port") + 1], "18188")
        self.assertEqual(
            Path(comfy_argv[comfy_argv.index("--base-directory") + 1]),
            self.runtime_root / "comfyui" / "data",
        )
        extra_paths = Path(comfy_argv[comfy_argv.index("--extra-model-paths-config") + 1])
        self.assertTrue(extra_paths.is_file())
        comfy_model_config = json.loads(extra_paths.read_text(encoding="utf-8"))
        self.assertEqual(
            comfy_model_config["aistudio_shared"]["checkpoints"],
            str(self.model_paths["checkpoint_dir"]),
        )
        self.assertIn("--enable-manager", comfy_argv)
        # Starting Comfy stops only the Forge child owned by this manager.
        self.assertEqual(forge_call["process"].terminate_calls, 1)

    def test_explicit_install_restarts_opposite_backend_for_model_topology(self):
        self.manager.execute("comfyui", "install")
        self.manager.execute("comfyui", "start")
        original_comfy = self.adapter.start_calls[-1]["process"]

        self.manager.execute("forge", "install")

        self.assertEqual(original_comfy.terminate_calls, 1)
        self.assertEqual(len(self.adapter.start_calls), 2)
        restarted = self.adapter.start_calls[-1]
        self.assertEqual(restarted["env"]["AISTUDIO_MANAGED_ENGINE"], "comfyui")
        self.assertIn("--enable-manager", restarted["argv"])
        self.assertTrue(self.manager.snapshot()["engines"]["comfyui"]["running"])

    def test_start_auto_install_does_not_bounce_previous_backend_mid_switch(self):
        self.manager.execute("forge", "install")
        self.manager.execute("forge", "start")
        original_forge = self.adapter.start_calls[-1]["process"]

        switched = self.manager.execute("comfyui", "start")

        self.assertTrue(switched["activate"])
        self.assertEqual(original_forge.terminate_calls, 1)
        self.assertEqual(
            [call["env"]["AISTUDIO_MANAGED_ENGINE"] for call in self.adapter.start_calls],
            ["forge", "comfyui"],
            "auto-install must not restart Forge only to stop it again for the switch",
        )
        self.assertTrue(self.manager.snapshot()["engines"]["comfyui"]["running"])

    def test_failed_engine_switch_restores_the_previous_managed_backend(self):
        self.manager.execute("forge", "install")
        self.manager.execute("comfyui", "install")
        self.manager.execute("forge", "start")
        original_forge = self.adapter.start_calls[-1]["process"]
        self.adapter.start_behaviours.extend(["early_exit", "healthy"])

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute("comfyui", "start")

        self.assertEqual(caught.exception.code, "PROCESS_EXITED_EARLY")
        snapshot = self.manager.snapshot()["engines"]
        self.assertTrue(snapshot["forge"]["running"])
        self.assertTrue(snapshot["forge"]["healthy"])
        self.assertFalse(snapshot["comfyui"]["running"])
        self.assertEqual(original_forge.terminate_calls, 1)
        self.assertEqual(len(self.adapter.start_calls), 3)

    def test_plain_start_activates_when_it_replaces_a_running_managed_engine(self):
        self.manager.execute("forge", "install")
        self.manager.execute("comfyui", "install")
        self.manager.execute("forge", "use")

        switched = self.manager.execute("comfyui", "start")
        snapshot = self.manager.snapshot()

        self.assertTrue(switched["activate"])
        self.assertEqual(switched["replacedEngine"], "forge")
        self.assertEqual(snapshot["activeEngine"], "comfyui")
        self.assertFalse(snapshot["engines"]["forge"]["running"])
        self.assertTrue(snapshot["engines"]["comfyui"]["running"])
        self.assertTrue(snapshot["engines"]["comfyui"]["active"])

    def test_stop_never_touches_a_process_owned_by_another_manager(self):
        self.manager.execute("forge", "install")
        self.manager.execute("forge", "start")
        owned_process = self.adapter.start_calls[-1]["process"]

        fresh_manager = self.make_manager()
        stopped = fresh_manager.execute("forge", "stop")

        self.assertTrue(stopped["ok"])
        self.assertFalse(stopped["stopped"])
        self.assertFalse(stopped["owned"])
        self.assertEqual(owned_process.terminate_calls, 0)
        self.assertIsNone(owned_process.poll())

        owned_stop = self.manager.execute("forge", "stop")
        self.assertTrue(owned_stop["stopped"])
        self.assertTrue(owned_stop["owned"])
        self.assertEqual(owned_process.terminate_calls, 1)

    def test_stop_reports_an_already_exited_owned_process_as_owned(self):
        self.manager.execute("forge", "install")
        self.manager.execute("forge", "start")
        owned_process = self.adapter.start_calls[-1]["process"]
        owned_process.running = False
        owned_process.returncode = 1

        stopped = self.manager.execute("forge", "stop")

        self.assertTrue(stopped["stopped"])
        self.assertTrue(stopped["owned"])
        self.assertEqual(owned_process.terminate_calls, 0)

    def test_port_collision_uses_and_persists_next_private_port(self):
        self.manager.execute("forge", "install")
        self.adapter.unavailable_ports.add(17860)

        started = self.manager.execute("forge", "start")

        self.assertEqual(started["apiUrl"], "http://127.0.0.1:17861")
        self.assertEqual(
            self.adapter.start_calls[-1]["argv"][
                self.adapter.start_calls[-1]["argv"].index("--port") + 1
            ],
            "17861",
        )
        self.assertEqual(self.manager.snapshot()["engines"]["forge"]["port"], 17861)

    def test_busy_operation_reports_structured_error_without_blocking(self):
        adapter = BlockingRuntimeAdapter()
        manager = self.make_manager(adapter=adapter)
        worker_errors = []

        def run_check():
            try:
                manager.execute("forge", "check_update")
            except Exception as exc:  # pragma: no cover - assertion below reports it
                worker_errors.append(exc)

        worker = threading.Thread(target=run_check, daemon=True)
        worker.start()
        self.assertTrue(adapter.entered.wait(timeout=1))
        try:
            with self.assertRaises(BackendRuntimeError) as caught:
                manager.execute("forge", "check_update")
        finally:
            adapter.release.set()
            worker.join(timeout=2)
        self.assertEqual(caught.exception.code, "OPERATION_BUSY")
        self.assertTrue(caught.exception.retryable)
        self.assertFalse(worker.is_alive())
        self.assertEqual(worker_errors, [])

    def test_cross_engine_start_cannot_interleave_with_an_inflight_operation(self):
        # Seed an installed Comfy runtime with the ordinary fake, then use a new
        # adapter that holds Forge's remote check open.  START must fail fast at
        # the global operation gate and must not launch or stop any process.
        self.manager.execute("comfyui", "install")
        adapter = BlockingRuntimeAdapter()
        manager = self.make_manager(adapter=adapter)
        worker_errors = []

        def run_check():
            try:
                manager.execute("forge", "check_update")
            except Exception as exc:  # pragma: no cover - asserted below
                worker_errors.append(exc)

        worker = threading.Thread(target=run_check, daemon=True)
        worker.start()
        self.assertTrue(adapter.entered.wait(timeout=1))
        try:
            started_at = time.monotonic()
            with self.assertRaises(BackendRuntimeError) as caught:
                manager.execute("comfyui", "start")
            elapsed = time.monotonic() - started_at
        finally:
            adapter.release.set()
            worker.join(timeout=2)

        self.assertEqual(caught.exception.code, "OPERATION_BUSY")
        self.assertTrue(caught.exception.retryable)
        self.assertLess(elapsed, 0.25)
        self.assertEqual(adapter.start_calls, [])
        self.assertFalse(worker.is_alive())
        self.assertEqual(worker_errors, [])

    def test_progress_callback_is_json_safe_and_completes(self):
        events = []
        result = self.manager.execute("forge", "install", on_progress=events.append)

        self.assertTrue(result["ok"])
        self.assertEqual(events[0]["phase"], "start")
        self.assertEqual(events[-1]["phase"], "complete")
        self.assertEqual(events[-1]["progress"], 100)
        json.dumps(events, ensure_ascii=False)

    def test_stop_all_owned_cancels_health_wait_without_waiting_for_timeout(self):
        manager = BackendRuntimeManager(
            config_path=self.config_path,
            runtime_root=self.runtime_root,
            adapter=self.adapter,
            health_timeout=1.0,
        )
        manager.execute("forge", "install")
        health_url = "http://127.0.0.1:17860/sdapi/v1/samplers"
        self.adapter.probe_overrides[health_url] = False
        start_errors = []

        def start_runtime():
            try:
                manager.execute("forge", "start")
            except Exception as exc:  # asserted after the worker finishes
                start_errors.append(exc)

        worker = threading.Thread(target=start_runtime, daemon=True)
        worker.start()
        self.assertTrue(self.adapter.probe_entered.wait(timeout=1))

        import time

        started = time.monotonic()
        manager.stop_all_owned()
        elapsed = time.monotonic() - started
        worker.join(timeout=1)

        self.assertLess(elapsed, 0.4, "shutdown must wake the health wait immediately")
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(start_errors), 1)
        self.assertIsInstance(start_errors[0], BackendRuntimeError)
        self.assertEqual(start_errors[0].code, "START_CANCELLED")
        self.assertFalse(manager.snapshot()["engines"]["forge"]["running"])
        self.assertEqual(self.adapter.start_calls[-1]["process"].terminate_calls, 1)


class BackendRuntimeUpdateTests(BackendRuntimeTestCase):
    def test_inactive_engine_update_restarts_active_backend_without_stale_model_paths(self):
        self.manager.execute("forge", "install")
        old_forge_source = Path(
            self.manager.snapshot()["engines"]["forge"]["sourceRoot"]
        )
        old_models = old_forge_source / "models" / "Stable-diffusion"
        old_models.mkdir(parents=True)
        self.manager.execute("comfyui", "install")
        self.manager.execute("comfyui", "start")
        original_comfy = self.adapter.start_calls[-1]["process"]
        old_config_path = Path(
            self.adapter.start_calls[-1]["argv"][
                self.adapter.start_calls[-1]["argv"].index("--extra-model-paths-config") + 1
            ]
        )
        old_config = json.loads(old_config_path.read_text(encoding="utf-8"))
        self.assertIn(
            str(old_models.resolve()),
            old_config["aistudio_shared"]["checkpoints"].splitlines(),
        )
        self.adapter.remote_heads[FORGE_REPOSITORY] = COMMIT_B

        self.manager.execute("forge", "update")

        snapshot = self.manager.snapshot()
        self.assertEqual(snapshot["engines"]["forge"]["commit"], COMMIT_B)
        self.assertTrue(snapshot["engines"]["comfyui"]["running"])
        self.assertEqual(original_comfy.terminate_calls, 1)
        self.assertEqual(len(self.adapter.start_calls), 2)
        restarted = self.adapter.start_calls[-1]
        new_config_path = Path(
            restarted["argv"][restarted["argv"].index("--extra-model-paths-config") + 1]
        )
        new_config = json.loads(new_config_path.read_text(encoding="utf-8"))
        self.assertNotIn(
            str(old_models.resolve()),
            new_config["aistudio_shared"]["checkpoints"].splitlines(),
        )

    def test_failed_updated_runtime_start_rolls_back_and_restarts_previous_release(self):
        self.manager.execute("forge", "install")
        self.manager.execute("forge", "start")
        before = self.manager.snapshot()["engines"]["forge"]
        old_source = Path(before["sourceRoot"])
        old_process = self.adapter.start_calls[-1]["process"]
        self.adapter.remote_heads[FORGE_REPOSITORY] = COMMIT_B
        self.adapter.start_behaviours.extend(["early_exit", "healthy"])

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute("forge", "update")

        self.assertEqual(caught.exception.code, "UPDATE_VERIFY_FAILED")
        after = self.manager.snapshot()["engines"]["forge"]
        self.assertEqual(Path(after["sourceRoot"]), old_source)
        self.assertEqual(after["commit"], COMMIT_A)
        self.assertTrue(after["running"])
        self.assertEqual(old_process.terminate_calls, 1)
        self.assertEqual(len(self.adapter.start_calls), 3)
        self.assertIsNone(self.adapter.start_calls[-1]["process"].poll())


class BackendRuntimeExtensionTests(BackendRuntimeTestCase):
    def test_existing_extension_credentials_are_redacted_from_snapshot_and_marker(self):
        external = self.temp / "external-secure-extensions"
        extension = external / "private-node"
        git_dir = extension / ".git"
        (git_dir / "refs" / "heads").mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
        (git_dir / "refs" / "heads" / "main").write_text(
            COMMIT_A + "\n", encoding="ascii"
        )
        credential_url = "https://secret-token@github.com/example/private-node.git"
        public_url = "https://github.com/example/private-node.git"
        (git_dir / "config").write_text(
            f'[remote "origin"]\n\turl = {credential_url}\n', encoding="utf-8"
        )
        (extension / ".fake-repository").write_text(credential_url, encoding="utf-8")
        (extension / ".fake-commit").write_text(COMMIT_A, encoding="utf-8")
        self.manager.configure("forge", {"extensionDir": str(external)})

        snapshot = self.manager.snapshot()
        self.assertEqual(
            snapshot["engines"]["forge"]["extensions"][0]["repoUrl"], public_url
        )
        self.assertNotIn("secret-token", json.dumps(snapshot))

        self.manager.execute("forge", "check_extension", {"id": "private-node"})
        marker = self.runtime_root / "forge" / "extension_state" / "private-node.json"
        marker_text = marker.read_text(encoding="utf-8")
        self.assertIn(public_url, marker_text)
        self.assertNotIn("secret-token", marker_text)

    def test_external_extension_clone_without_managed_runtime_defers_dependencies(self):
        external_extensions = self.temp / "existing-forge" / "extensions"
        external_extensions.mkdir(parents=True)
        self.manager.configure(
            "forge", {"extensionDir": str(external_extensions)}
        )
        self.adapter.extension_requirements = True
        repository = "https://github.com/example/external-plugin.git"

        installed = self.manager.execute(
            "forge", "install_extension", {"repoUrl": repository}
        )

        target = external_extensions / "external-plugin"
        self.assertTrue(installed["ok"])
        self.assertTrue(target.is_dir())
        self.assertTrue(installed["dependenciesPending"])
        self.assertEqual(
            Path(installed["requirementsPath"]), target / "requirements.txt"
        )
        pip_calls = [
            call for call in self.adapter.calls if "pip" in call["argv"]
        ]
        self.assertEqual(
            pip_calls, [], "an external extension must never mutate a managed venv"
        )

    def test_extension_url_and_destination_validation_prevent_unsafe_writes(self):
        self.manager.execute("forge", "install")
        invalid_urls = [
            "http://github.com/example/plugin.git",
            "https://user:secret@github.com/example/plugin.git",
            "https://github.com/example/plugin.git?token=secret",
            "file:///C:/temp/plugin",
            "https://github.com/example/%2e%2e.git",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(BackendRuntimeError) as caught:
                    self.manager.execute("forge", "install_extension", {"repoUrl": url})
                self.assertEqual(caught.exception.code, "INVALID_EXTENSION_SOURCE")

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute("forge", "update_extension", {"id": "../escape"})
        self.assertEqual(caught.exception.code, "INVALID_EXTENSION_TARGET")

    def test_extension_install_check_and_update_use_only_forge_runtime(self):
        self.adapter.extension_requirements = True
        self.manager.execute("forge", "install")
        repository = "https://github.com/example/forge-plugin.git"
        self.adapter.remote_heads[repository] = COMMIT_A

        installed = self.manager.execute(
            "forge", "install_extension", {"repoUrl": repository}
        )

        self.assertTrue(installed["ok"])
        extension_root = Path(installed["snapshot"]["engines"]["forge"]["extensionDir"])
        extension = extension_root / "forge-plugin"
        self.assertTrue(extension.is_dir())
        self.assertFalse(
            (Path(installed["snapshot"]["engines"]["comfyui"]["extensionDir"]) / "forge-plugin").exists()
        )
        pip_calls = [call["argv"] for call in self.adapter.calls if "pip" in call["argv"]]
        self.assertTrue(pip_calls)
        forge_python = Path(installed["snapshot"]["engines"]["forge"]["sourceRoot"]).parent / "venv"
        forge_python = forge_python / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.assertTrue(any(str(forge_python) in call for call in pip_calls))

        self.adapter.remote_heads[repository] = COMMIT_B
        checked = self.manager.execute(
            "forge", "check_extension", {"id": "forge-plugin"}
        )
        self.assertTrue(checked["updateAvailable"])
        self.assertEqual(checked["remoteCommit"], COMMIT_B)

        updated = self.manager.execute(
            "forge", "update_extension", {"id": "forge-plugin"}
        )
        self.assertTrue(updated["ok"])
        self.assertEqual(
            (extension / ".fake-commit").read_text(encoding="utf-8"), COMMIT_B
        )
        self.assertFalse(updated["restartRequired"])

    def test_extension_update_refuses_dirty_repository(self):
        self.manager.execute("forge", "install")
        repository = "https://github.com/example/dirty-plugin.git"
        self.manager.execute("forge", "install_extension", {"repoUrl": repository})
        extension = self.runtime_root / "forge" / "shared" / "extensions" / "dirty-plugin"
        (extension / ".fake-dirty").write_text(" M local.py", encoding="utf-8")

        with self.assertRaises(BackendRuntimeError) as caught:
            self.manager.execute("forge", "update_extension", {"id": "dirty-plugin"})

        self.assertEqual(caught.exception.code, "EXTENSION_DIRTY")


if __name__ == "__main__":
    unittest.main()

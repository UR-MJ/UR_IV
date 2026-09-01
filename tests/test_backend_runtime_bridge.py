import json
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QObject

from ui.vue_bridge import VueBridge
from ui.generator_webui import WebUIMixin


class _Parent(QObject):
    def __init__(self, *, web_mode=False):
        super().__init__()
        self.web_mode = web_mode


class _Manager:
    def __init__(self):
        self.execute_calls = []

    def snapshot(self):
        return {
            "ok": True,
            "activeEngine": "forge",
            "primaryModelEngine": "comfyui",
            "runtimeRoot": "C:/managed",
            "engines": {
                "forge": {
                    "engine": "forge",
                    "name": "Forge Neo",
                    "installed": True,
                    "running": True,
                    "healthy": True,
                    "owned": True,
                    "active": True,
                    "autoStart": True,
                    "sourceMode": "existing",
                    "existingRoot": "C:/existing/forge",
                    "root": "C:/managed/forge",
                    "installRoot": "C:/existing/forge",
                    "sourceRoot": "C:/existing/forge",
                    "pythonPath": "C:/existing/forge/venv/Scripts/python.exe",
                    "dataRoot": "C:/managed/forge/data",
                    "modelPaths": {"loras": ["C:/existing/forge/models/Lora"]},
                    "apiUrl": "http://127.0.0.1:7860",
                    "extensionDir": "C:/existing/forge/extensions",
                    "defaultExtensionDir": "C:/managed/forge/extensions",
                    "version": "abc123",
                    "commit": "abc123-full",
                    "remoteCommit": "def456",
                    "updateAvailable": True,
                    "updateStatus": "Update available",
                },
                "comfyui": {
                    "engine": "comfyui",
                    "installed": False,
                    "running": False,
                    "owned": False,
                    "autoStart": False,
                    "apiUrl": "http://127.0.0.1:8188",
                },
            },
        }

    def configure(self, _engine, _patch):
        return self.snapshot()

    def execute(self, engine, action, payload=None, on_progress=None):
        self.execute_calls.append((engine, action, dict(payload or {})))
        if on_progress:
            on_progress({"phase": "health", "message": "ready"})
        return {
            "ok": True,
            "engine": engine,
            "action": action,
            "message": "ready",
            "apiUrl": "http://127.0.0.1:7860",
            "owned": True,
            "activate": action == "use" or bool((payload or {}).get("startup", False)),
            "snapshot": self.snapshot(),
        }


def _runtime_module(manager):
    module = types.ModuleType("core.backend_runtime")
    module.get_backend_runtime_manager = lambda: manager
    return module


class BackendRuntimeBridgeTests(unittest.TestCase):
    def test_autostart_uses_the_unique_toggle_even_when_another_engine_was_active(self):
        class AutoManager(_Manager):
            def snapshot(self):
                state = super().snapshot()
                state["activeEngine"] = "forge"
                state["engines"]["forge"]["autoStart"] = False
                state["engines"]["comfyui"].update({
                    "installed": True,
                    "autoStart": True,
                })
                return state

        class Bridge:
            def __init__(self):
                self.calls = []

            def runBackendRuntimeOperation(self, engine, action, payload):
                self.calls.append((engine, action, json.loads(payload)))
                return json.dumps({"ok": True, "accepted": True})

        class Host(WebUIMixin):
            web_mode = False

            def __init__(self):
                self.vue_bridge = Bridge()

        host = Host()
        manager = AutoManager()
        with patch.dict(sys.modules, {"core.backend_runtime": _runtime_module(manager)}):
            accepted = host._try_managed_backend_autostart()

        self.assertTrue(accepted)
        self.assertEqual(host.vue_bridge.calls[0][0], "comfyui")
        self.assertEqual(host.vue_bridge.calls[0][1], "start")
        self.assertTrue(host.vue_bridge.calls[0][2]["startup"])

    def test_snapshot_normalizes_core_engine_ids_for_settings(self):
        manager = _Manager()
        parent = _Parent()
        bridge = VueBridge(parent)
        with patch.dict(sys.modules, {"core.backend_runtime": _runtime_module(manager)}):
            state = json.loads(bridge.getBackendRuntimeState())

        self.assertTrue(state["ok"])
        self.assertTrue(state["nativeOperations"])
        self.assertEqual(state["active"]["engine"], "forge")
        self.assertEqual(state["primaryModelEngine"], "comfyui")
        forge = state["engines"]["forge"]
        self.assertTrue(forge["installed"])
        self.assertTrue(forge["running"])
        self.assertTrue(forge["autoStart"])
        self.assertEqual(forge["extensionDir"], "C:/existing/forge/extensions")
        self.assertEqual(forge["version"], "abc123")
        self.assertEqual(forge["sourceMode"], "existing")
        self.assertEqual(forge["sourceRoot"], "C:/existing/forge")
        self.assertTrue(forge["pythonPath"].endswith("python.exe"))
        self.assertEqual(forge["modelPaths"]["loras"], ["C:/existing/forge/models/Lora"])

    def test_web_mode_allows_snapshot_but_rejects_native_mutators(self):
        manager = _Manager()
        parent = _Parent(web_mode=True)
        bridge = VueBridge(parent)
        with patch.dict(sys.modules, {"core.backend_runtime": _runtime_module(manager)}):
            state = json.loads(bridge.getBackendRuntimeState())
            operation = json.loads(
                bridge.runBackendRuntimeOperation("forge", "start", "{}")
            )
            selection = json.loads(bridge.selectBackendExtensionDirectory("forge"))
            install_selection = json.loads(bridge.selectBackendInstallDirectory("forge"))

        self.assertTrue(state["ok"])
        self.assertFalse(state["nativeOperations"])
        self.assertFalse(operation["accepted"])
        self.assertFalse(selection["ok"])
        self.assertFalse(install_selection["ok"])
        self.assertEqual(manager.execute_calls, [])

    def test_start_is_nonblocking_and_emits_one_generic_terminal_event(self):
        manager = _Manager()
        parent = _Parent()
        bridge = VueBridge(parent)
        terminal = threading.Event()
        events = []

        def collect(raw):
            event = json.loads(raw)
            events.append(event)
            if event.get("type") in {"completed", "error"}:
                terminal.set()

        bridge.backendRuntimeEvent.connect(collect)
        with patch.dict(sys.modules, {"core.backend_runtime": _runtime_module(manager)}):
            accepted = json.loads(
                bridge.runBackendRuntimeOperation("forge", "start", "{}")
            )
            self.assertTrue(accepted["accepted"])
            app = QCoreApplication.instance() or QCoreApplication([])
            deadline = time.monotonic() + 2.0
            while not terminal.is_set() and time.monotonic() < deadline:
                app.processEvents()
                terminal.wait(0.01)
            self.assertTrue(terminal.is_set())

        completed = [event for event in events if event.get("type") == "completed"]
        self.assertEqual(len(completed), 1)
        self.assertFalse(completed[0]["activate"])
        self.assertEqual(completed[0]["engine"], "forge")
        self.assertEqual(manager.execute_calls[0][0], "forge")
        self.assertEqual(manager.execute_calls[0][1], "start")

    def test_use_and_startup_autostart_activate_but_plain_start_does_not(self):
        manager = _Manager()
        parent = _Parent()
        bridge = VueBridge(parent)
        terminal = threading.Event()
        events = []

        def collect(raw):
            event = json.loads(raw)
            if event.get("type") in {"completed", "error"}:
                events.append(event)
                terminal.set()

        bridge.backendRuntimeEvent.connect(collect)
        app = QCoreApplication.instance() or QCoreApplication([])
        with patch.dict(sys.modules, {"core.backend_runtime": _runtime_module(manager)}):
            for action, payload, expected in (
                ("use", "{}", True),
                ("start", '{"startup": true}', True),
            ):
                terminal.clear()
                bridge.runBackendRuntimeOperation("forge", action, payload)
                deadline = time.monotonic() + 2.0
                while not terminal.is_set() and time.monotonic() < deadline:
                    app.processEvents()
                    terminal.wait(0.01)
                self.assertTrue(terminal.is_set())
                self.assertEqual(events[-1]["activate"], expected)

    def test_plain_start_forwards_core_replacement_activation(self):
        class SwitchingManager(_Manager):
            def execute(self, engine, action, payload=None, on_progress=None):
                result = super().execute(engine, action, payload, on_progress)
                result["activate"] = True
                result["replacedEngine"] = "forge"
                result["apiUrl"] = "http://127.0.0.1:18188"
                return result

        manager = SwitchingManager()
        parent = _Parent()
        bridge = VueBridge(parent)
        terminal = threading.Event()
        events = []

        def collect(raw):
            event = json.loads(raw)
            if event.get("type") in {"completed", "error"}:
                events.append(event)
                terminal.set()

        bridge.backendRuntimeEvent.connect(collect)
        app = QCoreApplication.instance() or QCoreApplication([])
        with patch.dict(sys.modules, {"core.backend_runtime": _runtime_module(manager)}):
            bridge.runBackendRuntimeOperation("comfyui", "start", "{}")
            deadline = time.monotonic() + 2.0
            while not terminal.is_set() and time.monotonic() < deadline:
                app.processEvents()
                terminal.wait(0.01)

        self.assertTrue(terminal.is_set())
        self.assertTrue(events[-1]["activate"])
        self.assertEqual(events[-1]["result"]["replacedEngine"], "forge")

    def test_actual_core_configure_operation_matches_bridge_contract(self):
        from core import backend_runtime

        with tempfile.TemporaryDirectory() as temp:
            manager = backend_runtime.BackendRuntimeManager(
                config_path=f"{temp}/runtime.json",
                runtime_root=f"{temp}/managed",
            )
            parent = _Parent()
            bridge = VueBridge(parent)
            terminal = threading.Event()
            events = []

            def collect(raw):
                event = json.loads(raw)
                events.append(event)
                if event.get("type") in {"completed", "error"}:
                    terminal.set()

            bridge.backendRuntimeEvent.connect(collect)
            with patch.object(backend_runtime, "_MANAGER", manager):
                accepted = json.loads(bridge.runBackendRuntimeOperation(
                    "forge", "set_auto_start", '{"autoStart": true}'
                ))
                self.assertTrue(accepted["accepted"])
                app = QCoreApplication.instance() or QCoreApplication([])
                deadline = time.monotonic() + 2.0
                while not terminal.is_set() and time.monotonic() < deadline:
                    app.processEvents()
                    terminal.wait(0.01)
                self.assertTrue(terminal.is_set())
                state = json.loads(bridge.getBackendRuntimeState())

            self.assertTrue(events[-1]["ok"])
            self.assertTrue(state["engines"]["forge"]["autoStart"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backends.base import GenerationResult, MediaArtifact
from backends.comfyui_backend import ComfyUIBackend
from core.comfy_node_pack import (
    ComfyNodePackError,
    NodePackInstallResult,
    OWNER_ID,
    OWNER_MARKER,
    REQUIRED_NODE_TYPES,
    install_bundled_node_pack,
    missing_required_nodes,
    node_pack_fingerprint,
)
from comfy_custom_nodes.ai_studio_forge_parity import NODE_CLASS_MAPPINGS


def _source(root: Path, body: str = "VALUE = 1\n") -> Path:
    source = root / "source"
    source.mkdir()
    (source / "__init__.py").write_text(body, encoding="utf-8")
    return source


class TestBundledComfyNodePack(unittest.TestCase):
    def test_install_is_owned_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            custom_nodes = tmp_path / "custom_nodes"
            custom_nodes.mkdir()
            source = _source(tmp_path)

            first = install_bundled_node_pack(custom_nodes, source=source)
            second = install_bundled_node_pack(custom_nodes, source=source)

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            marker = json.loads((first.target / OWNER_MARKER).read_text(encoding="utf-8"))
            self.assertEqual(marker["owner"], OWNER_ID)
            self.assertEqual(marker["fingerprint"], node_pack_fingerprint(source))

    def test_install_refreshes_only_an_app_owned_target(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            custom_nodes = tmp_path / "custom_nodes"
            custom_nodes.mkdir()
            source = _source(tmp_path)
            installed = install_bundled_node_pack(custom_nodes, source=source)
            (source / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")

            refreshed = install_bundled_node_pack(custom_nodes, source=source)

            self.assertTrue(refreshed.changed)
            self.assertEqual(
                (installed.target / "__init__.py").read_text(encoding="utf-8"),
                "VALUE = 2\n",
            )

    def test_install_repairs_tampered_owned_target_even_when_marker_is_current(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            custom_nodes = tmp_path / "custom_nodes"
            custom_nodes.mkdir()
            source = _source(tmp_path)
            installed = install_bundled_node_pack(custom_nodes, source=source)
            (installed.target / "__init__.py").write_text("VALUE = 99\n", encoding="utf-8")

            repaired = install_bundled_node_pack(custom_nodes, source=source)

            self.assertTrue(repaired.changed)
            self.assertEqual(
                (installed.target / "__init__.py").read_text(encoding="utf-8"),
                "VALUE = 1\n",
            )

    def test_install_refuses_unowned_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            custom_nodes = tmp_path / "custom_nodes"
            target = custom_nodes / "ai_studio_forge_parity"
            target.mkdir(parents=True)
            (target / "user.py").write_text("# mine\n", encoding="utf-8")
            source = _source(tmp_path)

            with self.assertRaisesRegex(ComfyNodePackError, "덮어쓰지"):
                install_bundled_node_pack(custom_nodes, source=source)

            self.assertTrue((target / "user.py").is_file())

    def test_missing_required_nodes_is_complete_and_stable(self):
        present = {name: {} for name in REQUIRED_NODE_TYPES if name != "ForgeNeoSAM3Mask"}
        self.assertEqual(missing_required_nodes(present), ["ForgeNeoSAM3Mask"])

    def test_required_manifest_matches_every_exported_bundled_node(self):
        self.assertEqual(REQUIRED_NODE_TYPES, frozenset(NODE_CLASS_MAPPINGS))


class _FakeRuntimeManager:
    def __init__(self, engine):
        self.engine = dict(engine)
        self.operations = []

    def snapshot(self):
        return {"engines": {"comfyui": dict(self.engine)}}

    def execute(self, engine, action, payload=None):
        self.operations.append((engine, action, payload))
        if action == "start":
            return {"apiUrl": "http://127.0.0.1:18189"}
        return {"ok": True}


class TestComfyBackendNodePackPreflight(unittest.TestCase):
    def _engine(self, **overrides):
        engine = {
            "apiUrl": "http://127.0.0.1:8188",
            "extensionDir": r"C:\ComfyUI\custom_nodes",
            "extensionWritable": True,
            "owned": False,
            "running": True,
        }
        engine.update(overrides)
        return engine

    def test_unapproved_external_extension_directory_is_never_written(self):
        manager = _FakeRuntimeManager(self._engine(extensionWritable=False))
        backend = ComfyUIBackend("http://localhost:8188")
        with mock.patch(
            "core.backend_runtime.get_backend_runtime_manager", return_value=manager,
        ), mock.patch("core.comfy_node_pack.install_bundled_node_pack") as install:
            backend._preflight_bundled_node_pack()

        install.assert_not_called()
        self.assertTrue(backend._node_pack_preflight_done)
        self.assertEqual(manager.operations, [])

    def test_changed_pack_restarts_only_manager_owned_comfy(self):
        manager = _FakeRuntimeManager(self._engine(owned=True))
        backend = ComfyUIBackend("http://127.0.0.1:8188")
        installed = NodePackInstallResult(
            target=Path(r"C:\ComfyUI\custom_nodes\ai_studio_forge_parity"),
            fingerprint="abc",
            changed=True,
        )
        with mock.patch(
            "core.backend_runtime.get_backend_runtime_manager", return_value=manager,
        ), mock.patch(
            "core.comfy_node_pack.install_bundled_node_pack", return_value=installed,
        ):
            backend._preflight_bundled_node_pack()

        self.assertEqual(
            manager.operations,
            [
                ("comfyui", "stop", None),
                ("comfyui", "start", {"installIfMissing": False}),
            ],
        )
        self.assertEqual(backend.api_url, "http://127.0.0.1:18189")
        self.assertTrue(backend._node_pack_preflight_done)

    def test_changed_pack_requires_manual_restart_for_external_comfy(self):
        manager = _FakeRuntimeManager(self._engine(owned=False))
        backend = ComfyUIBackend("http://127.0.0.1:8188")
        installed = NodePackInstallResult(
            target=Path(r"C:\ComfyUI\custom_nodes\ai_studio_forge_parity"),
            fingerprint="abc",
            changed=True,
        )
        with mock.patch(
            "core.backend_runtime.get_backend_runtime_manager", return_value=manager,
        ), mock.patch(
            "core.comfy_node_pack.install_bundled_node_pack", return_value=installed,
        ):
            with self.assertRaisesRegex(RuntimeError, "외부 ComfyUI를 한 번 재시작"):
                backend._preflight_bundled_node_pack()

        self.assertEqual(manager.operations, [])
        self.assertFalse(backend._node_pack_preflight_done)

    def test_refine_can_return_the_last_independent_image_like_forge(self):
        result = GenerationResult(
            success=True,
            image_data=b"first",
            artifacts=[
                MediaArtifact(kind="image", data=b"first", filename="first.png"),
                MediaArtifact(kind="image", data=b"last", filename="last.png"),
            ],
        )

        encoded = ComfyUIBackend._result_as_base64(
            result, "refine", prefer_last=True,
        )

        import base64
        self.assertEqual(base64.b64decode(encoded), b"last")

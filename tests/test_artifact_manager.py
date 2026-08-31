import hashlib
import tempfile
import unittest
from pathlib import Path

from core.artifact_manager import (
    ArtifactCancelled,
    ArtifactError,
    ArtifactManager,
    ArtifactSpec,
)


class _Response:
    def __init__(self, data):
        self.data = data
        self.closed = False

    def iter_content(self, chunk_size):
        for pos in range(0, len(self.data), 3):
            yield self.data[pos : pos + 3]

    def close(self):
        self.closed = True


class _Transport:
    def __init__(self, data):
        self.data = data
        self.offsets = []

    def open(self, _url, offset):
        self.offsets.append(offset)
        return _Response(self.data[offset:]), True


def _spec(data, path="models/test.bin"):
    return ArtifactSpec(
        artifact_id="test",
        url="https://example.invalid/test.bin",
        relative_path=path,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


class ArtifactManagerTests(unittest.TestCase):
    def test_installs_and_verifies_sha(self):
        data = b"verified creator artifact"
        with tempfile.TemporaryDirectory() as tmp:
            manager = ArtifactManager(tmp, _Transport(data))
            status = manager.ensure(_spec(data))
            self.assertTrue(status.verified)
            self.assertEqual(Path(status.path).read_bytes(), data)

    def test_resumes_part_file(self):
        data = b"0123456789abcdef"
        transport = _Transport(data)
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "models" / "test.bin.part"
            part.parent.mkdir(parents=True)
            part.write_bytes(data[:5])
            manager = ArtifactManager(tmp, transport)
            manager.ensure(_spec(data))
            self.assertEqual(transport.offsets, [5])

    def test_existing_same_size_but_bad_hash_is_replaced(self):
        data = b"correct"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "models" / "test.bin"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"xxxxxxx")
            manager = ArtifactManager(tmp, _Transport(data))
            manager.ensure(_spec(data))
            self.assertEqual(target.read_bytes(), data)

    def test_keeps_part_file_on_cancel(self):
        data = b"download data"
        with tempfile.TemporaryDirectory() as tmp:
            manager = ArtifactManager(tmp, _Transport(data))
            with self.assertRaises(ArtifactCancelled):
                manager.ensure(_spec(data), cancelled=lambda: True)
            self.assertTrue((Path(tmp) / "models" / "test.bin.part").exists())

    def test_rejects_path_escape(self):
        data = b"x"
        with tempfile.TemporaryDirectory() as tmp:
            manager = ArtifactManager(tmp, _Transport(data))
            with self.assertRaises(ArtifactError):
                manager.ensure(_spec(data, "../escape.bin"))


if __name__ == "__main__":
    unittest.main()

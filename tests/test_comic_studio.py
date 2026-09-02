import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from core.comic_studio import (
    ComicDocumentError,
    ComicRevisionConflict,
    ComicStudio,
    panel_generation_payloads,
)


class ComicStudioTests(unittest.TestCase):
    def test_plans_exact_panel_count_from_ollama_json(self):
        response = {
            "title": "비 오는 재회",
            "panels": [
                {
                    "name": f"컷 {i + 1}",
                    "text": f"장면 {i + 1}",
                    "imagePrompt": f"rainy alley panel {i + 1}",
                    "motionPrompt": "rain falling",
                }
                for i in range(3)
            ],
            "bubbles": [{"name": "유나", "text": "오랜만이야", "panelIndex": 1}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            studio = ComicStudio(
                Path(tmp) / "comic.json",
                complete_json=lambda _system, _user: f"```json\n{json.dumps(response)}\n```",
            )
            document = studio.plan("비 오는 밤에 다시 만난다.", 3, "webtoon", "red coat")
        self.assertEqual(len(document.panels), 3)
        self.assertEqual(document.bubbles[0].panel_index, 1)
        self.assertEqual(document.character_lock, "red coat")

    def test_atomic_save_and_load_normalizes_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "comic.json"
            studio = ComicStudio(path)
            document = studio.plan("첫 장면. 두 번째 장면.", 2)
            studio.save(document)
            loaded = studio.load()
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded.panels), 2)
            self.assertFalse(path.with_suffix(".json.writing").exists())

    def test_rejects_more_than_six_panels(self):
        studio = ComicStudio("unused.json")
        with self.assertRaises(ComicDocumentError):
            studio.normalize({"panels": [{} for _ in range(7)]})

    def test_generation_payload_repeats_character_lock(self):
        studio = ComicStudio("unused.json")
        document = studio.plan("장면 하나", 1, character_lock="same blue coat")
        payload = list(panel_generation_payloads(document))[0]
        self.assertIn("same blue coat", payload["prompt"])
        self.assertEqual(payload["panel_index"], 0)

    def test_invalid_model_json_is_reported_not_silently_replaced(self):
        studio = ComicStudio("unused.json", complete_json=lambda *_: "not json")
        with self.assertRaises(ComicDocumentError):
            studio.plan("장면", 2)

    def test_frontend_document_shape_round_trips_panel_media_and_bubbles(self):
        studio = ComicStudio("unused.json")
        raw = {
            "id": "comic-ui",
            "title": "UI 문서",
            "scene": "장면",
            "style": "Anime",
            "layout": "hero",
            "panels": [
                {
                    "id": "panel-ui",
                    "prompt": "red coat",
                    "negative": "watermark",
                    "motion": "slow push in",
                    "imagePath": "C:/output/panel.png",
                    "videoPath": "C:/output/panel.mp4",
                    "bubbles": [
                        {
                            "id": "bubble-ui",
                            "text": "안녕",
                            "kind": "speech",
                            "x": 12,
                            "y": 8,
                            "width": 36,
                            "height": 18,
                        }
                    ],
                }
            ],
        }
        serialized = studio.normalize(raw).to_dict()
        self.assertEqual(serialized["id"], "comic-ui")
        self.assertEqual(serialized["panels"][0]["prompt"], "red coat")
        self.assertEqual(serialized["panels"][0]["videoPath"], "C:/output/panel.mp4")
        self.assertEqual(serialized["panels"][0]["bubbles"][0]["text"], "안녕")

    def test_save_rejects_a_stale_revision_without_overwriting_newer_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "comic.json"
            studio = ComicStudio(path)
            second_writer = ComicStudio(path)
            first = studio.save(
                {"title": "초안", "panels": [{"id": "panel-1", "prompt": "first"}]},
                expected_revision=0,
            )
            newer = second_writer.save(
                {**first.to_dict(), "title": "새 버전"},
                expected_revision=first.revision,
            )

            with self.assertRaises(ComicRevisionConflict) as raised:
                studio.save(
                    {**first.to_dict(), "title": "뒤늦은 저장"},
                    expected_revision=first.revision,
                )

            self.assertEqual(raised.exception.actual_revision, newer.revision)
            self.assertEqual(studio.load().title, "새 버전")
            conflict_path = Path(raised.exception.conflict_path)
            self.assertTrue(conflict_path.is_file())
            self.assertEqual(
                json.loads(conflict_path.read_text(encoding="utf-8"))["document"]["title"],
                "뒤늦은 저장",
            )

    def test_identical_retry_is_idempotent_even_after_ack_was_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = ComicStudio(Path(tmp) / "comic.json")
            saved = studio.save(
                {"title": "동일 문서", "panels": [{"id": "panel-1", "prompt": "same"}]},
                expected_revision=0,
            )

            retried = studio.save(saved.to_dict(), expected_revision=0)

            self.assertEqual(retried.revision, saved.revision)
            self.assertEqual(retried.content_hash, saved.content_hash)

    def test_reconcile_migrates_a_legacy_local_only_document_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = ComicStudio(Path(tmp) / "comic.json")
            legacy = {
                "id": "local-only",
                "title": "브라우저에만 있던 문서",
                "panels": [{"id": "panel-1", "prompt": "keep me"}],
            }

            migrated = studio.reconcile(legacy)
            reopened = studio.reconcile(legacy)

            self.assertEqual(migrated.status, "recovered")
            self.assertEqual(migrated.document.title, "브라우저에만 있던 문서")
            self.assertEqual(reopened.status, "current")
            self.assertEqual(reopened.document.revision, migrated.document.revision)

    def test_reconcile_applies_a_dirty_mirror_only_to_its_matching_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = ComicStudio(Path(tmp) / "comic.json")
            base = studio.save(
                {"title": "기준", "panels": [{"id": "panel-1", "prompt": "base"}]},
                expected_revision=0,
            )
            recovered_raw = {**base.to_dict(), "title": "복구된 편집"}
            document_json = json.dumps(recovered_raw, ensure_ascii=False, separators=(",", ":"))
            mirror = {
                "schema": 2,
                "documentJson": document_json,
                "recoveryHash": hashlib.sha256(document_json.encode("utf-8")).hexdigest(),
                "baseRevision": base.revision,
                "baseContentHash": base.content_hash,
                "updatedAt": base.updated_at + 10,
                "dirty": True,
            }

            recovered = studio.reconcile(mirror)

            self.assertEqual(recovered.status, "recovered")
            self.assertEqual(recovered.document.title, "복구된 편집")
            self.assertEqual(recovered.document.revision, base.revision + 1)

    def test_reconcile_preserves_a_stale_dirty_mirror_as_conflict_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "comic.json"
            studio = ComicStudio(state_path)
            base = studio.save(
                {"title": "기준", "panels": [{"id": "panel-1", "prompt": "base"}]},
                expected_revision=0,
            )
            stale_raw = {**base.to_dict(), "title": "로컬 미저장 편집"}
            document_json = json.dumps(stale_raw, ensure_ascii=False, separators=(",", ":"))
            mirror = {
                "schema": 2,
                "documentJson": document_json,
                "recoveryHash": hashlib.sha256(document_json.encode("utf-8")).hexdigest(),
                "baseRevision": base.revision,
                "baseContentHash": base.content_hash,
                "updatedAt": base.updated_at + 10,
                "dirty": True,
            }
            studio.save(
                {**base.to_dict(), "title": "백엔드 최신 편집"},
                expected_revision=base.revision,
            )

            reconciled = studio.reconcile(mirror)

            self.assertEqual(reconciled.status, "conflict")
            self.assertEqual(reconciled.document.title, "백엔드 최신 편집")
            conflict_path = Path(reconciled.conflict_path)
            self.assertTrue(conflict_path.is_file())
            self.assertEqual(
                json.loads(conflict_path.read_text(encoding="utf-8"))["document"]["title"],
                "로컬 미저장 편집",
            )

    def test_invalid_recovery_hash_restores_the_authoritative_backend_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = ComicStudio(Path(tmp) / "comic.json")
            current = studio.save(
                {"title": "정상 백엔드", "panels": [{"id": "panel-1", "prompt": "safe"}]},
                expected_revision=0,
            )
            document_json = json.dumps(
                {**current.to_dict(), "title": "손상된 복구본"},
                ensure_ascii=False,
                separators=(",", ":"),
            )

            reconciled = studio.reconcile(
                {
                    "schema": 2,
                    "documentJson": document_json,
                    "recoveryHash": "0" * 64,
                    "baseRevision": current.revision,
                    "baseContentHash": current.content_hash,
                    "dirty": True,
                }
            )

            self.assertEqual(reconciled.status, "invalid-recovery")
            self.assertEqual(reconciled.document.title, "정상 백엔드")
            self.assertTrue(Path(reconciled.conflict_path).is_file())


if __name__ == "__main__":
    unittest.main()

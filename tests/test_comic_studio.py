import json
import tempfile
import unittest
from pathlib import Path

from core.comic_studio import (
    ComicDocumentError,
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


if __name__ == "__main__":
    unittest.main()

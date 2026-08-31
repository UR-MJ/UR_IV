from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from core.living_comic import (
    LivingComicDependencyError,
    LivingComicError,
    PAGE_SIZE,
    compute_panel_boxes,
    cycle_frame_index,
    normalize_living_document,
    render_living_comic,
)


class LivingComicLayoutTests(unittest.TestCase):
    def assert_valid_boxes(self, boxes):
        page_width, page_height = PAGE_SIZE
        for box in boxes:
            self.assertGreater(box.width, 0)
            self.assertGreater(box.height, 0)
            self.assertGreaterEqual(box.x, 0)
            self.assertGreaterEqual(box.y, 0)
            self.assertLessEqual(box.x + box.width, page_width)
            self.assertLessEqual(box.y + box.height, page_height)
        for index, first in enumerate(boxes):
            for second in boxes[index + 1 :]:
                overlap_width = min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
                overlap_height = min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
                self.assertTrue(overlap_width <= 0 or overlap_height <= 0)

    def test_layouts_cover_one_to_six_panels_without_overlap(self):
        for layout in ("auto", "grid", "vertical", "horizontal", "hero"):
            for count in range(1, 7):
                with self.subTest(layout=layout, count=count):
                    boxes = compute_panel_boxes(count, layout)
                    self.assertEqual(len(boxes), count)
                    self.assert_valid_boxes(boxes)

    def test_auto_layout_uses_lead_panel_for_three_panels(self):
        boxes = compute_panel_boxes(3, "auto")

        self.assertGreater(boxes[0].width, boxes[1].width)
        self.assertGreater(boxes[0].height, boxes[1].height)
        self.assertGreater(boxes[1].y, boxes[0].y)

    def test_cycle_frame_index_wraps_short_clips(self):
        cases = ((0, 3, 0), (2, 3, 2), (3, 3, 0), (10, 3, 1))
        for output_index, source_count, expected in cases:
            with self.subTest(output_index=output_index):
                self.assertEqual(cycle_frame_index(output_index, source_count), expected)


class LivingComicNormalizationTests(unittest.TestCase):
    def test_nested_bubbles_accept_percentage_or_ratio_coordinates(self):
        with TemporaryDirectory() as temp:
            image_path = Path(temp) / "panel.png"
            image_path.write_bytes(b"not decoded during normalization")
            document = normalize_living_document(
                {
                    "title": "Demo",
                    "layout": "focus",
                    "panels": [
                        {
                            "imagePath": str(image_path),
                            "bubbles": [
                                {"id": "ratio", "text": "hello", "x": 0.25, "y": 0.1, "width": 0.4},
                                {"id": "percent", "text": "world", "x": 25, "y": 10, "width": 40},
                            ],
                        }
                    ],
                }
            )

            self.assertEqual(document.layout, "hero")
            self.assertFalse(document.panels[0].is_video)
            first, second = document.panels[0].bubbles
            self.assertAlmostEqual(first.x, 0.25)
            self.assertAlmostEqual(second.x, 0.25)
            self.assertAlmostEqual(first.width, second.width)

    def test_flattened_bubbles_are_used_as_fallback(self):
        with TemporaryDirectory() as temp:
            video_path = Path(temp) / "panel.mp4"
            video_path.write_bytes(b"placeholder")
            document = normalize_living_document(
                {
                    "panels": [{"video_path": str(video_path)}],
                    "bubbles": [
                        {"id": "b1", "panel_index": 0, "text": "대사", "style": "narration"},
                        {"id": "ignored", "panel_index": 9, "text": "wrong panel"},
                    ],
                }
            )

            self.assertTrue(document.panels[0].is_video)
            self.assertEqual([bubble.text for bubble in document.panels[0].bubbles], ["대사"])
            self.assertEqual(document.panels[0].bubbles[0].kind, "narration")

    def test_missing_media_is_rejected(self):
        with TemporaryDirectory() as temp:
            missing = Path(temp) / "missing.mp4"
            with self.assertRaisesRegex(LivingComicError, "찾을 수 없습니다"):
                normalize_living_document({"panels": [{"videoPath": str(missing)}]})

    def test_unsupported_media_is_rejected(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "panel.txt"
            source.write_text("no", encoding="utf-8")
            with self.assertRaisesRegex(LivingComicError, "지원하지 않는"):
                normalize_living_document({"panels": [{"videoPath": str(source)}]})

    def test_missing_pyav_error_is_clear_and_leaves_no_output(self):
        try:
            import av  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("This assertion covers the no-PyAV installation path")

        with TemporaryDirectory() as temp:
            root = Path(temp)
            image_path = root / "panel.png"
            Image.new("RGB", (8, 8), "red").save(image_path)
            output_dir = root / "output"
            with self.assertRaisesRegex(LivingComicDependencyError, "pip install av"):
                render_living_comic({"panels": [{"imagePath": str(image_path)}]}, output_dir)
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path

from ui.vue_bridge import _scan_gallery_media


class TestGalleryMediaScan(unittest.TestCase):
    def test_includes_creator_media_and_ignores_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            names = [
                'still.PNG', 'animated.webp', 'clip.mp4', 'preview.WEBM',
                'sound.wav', 'music.FLAC',
            ]
            for index, name in enumerate(names, start=1):
                path = root / name
                path.write_bytes(b'x')
                os.utime(path, (index, index))
            (root / 'notes.txt').write_text('ignore', encoding='utf-8')
            (root / 'fake.mp4').mkdir()

            result = _scan_gallery_media(temp_dir)

            self.assertEqual([Path(path).name for path in result], list(reversed(names)))

    def test_supports_animated_and_audio_formats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            names = ['page.apng', 'animation.gif', 'voice.ogg', 'score.m4a', 'speech.opus']
            for name in names:
                (root / name).write_bytes(b'x')

            result_names = {Path(path).name for path in _scan_gallery_media(temp_dir)}

            self.assertEqual(result_names, set(names))

    def test_optional_creator_root_is_scanned_recursively(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            creator = root / 'creator'
            nested = creator / 'h3_v2v'
            nested.mkdir(parents=True)
            (nested / 'result.mp4').write_bytes(b'video')
            (root / 'regular.png').write_bytes(b'image')

            result_names = {
                Path(path).name
                for path in _scan_gallery_media(str(root), (str(creator),))
            }

            self.assertEqual(result_names, {'regular.png', 'result.mp4'})


if __name__ == '__main__':
    unittest.main()

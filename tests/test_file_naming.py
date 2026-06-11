"""core/file_naming.py — 사용자 입력 파일명 정규화 (경로 탈출 차단) 테스트."""
import unittest
from core.file_naming import sanitize_filename


class TestSanitizeFilename(unittest.TestCase):
    def test_normal_names_unchanged(self):
        self.assertEqual(sanitize_filename("my preset"), "my preset")
        self.assertEqual(sanitize_filename("ANIMA_v2-final"), "ANIMA_v2-final")
        self.assertEqual(sanitize_filename("한글 프리셋"), "한글 프리셋")

    def test_traversal_removed(self):
        # 구분자 제거 → '..'만 남아도 디렉토리 탈출 불가
        self.assertEqual(sanitize_filename("../config/ui_prefs"), "..configui_prefs")
        self.assertNotIn('/', sanitize_filename("../../etc/passwd"))
        self.assertNotIn('\\', sanitize_filename("..\\config\\cond_rules"))

    def test_absolute_path_neutralized(self):
        s = sanitize_filename(r"C:\config\ui_prefs")
        self.assertNotIn(':', s)
        self.assertNotIn('\\', s)

    def test_reserved_windows_names(self):
        self.assertEqual(sanitize_filename("con"), "_con")
        self.assertEqual(sanitize_filename("NUL"), "_NUL")
        self.assertEqual(sanitize_filename("com1"), "_com1")
        # 예약어 + 확장자 형태도 예약됨
        self.assertEqual(sanitize_filename("con.backup"), "_con.backup")

    def test_trailing_dots_spaces_stripped(self):
        # Windows는 끝의 점/공백을 무시 → 미리 잘라 불일치 방지
        self.assertEqual(sanitize_filename("name. . "), "name")

    def test_empty_falls_back(self):
        self.assertEqual(sanitize_filename(""), "untitled")
        self.assertEqual(sanitize_filename("///"), "untitled")
        self.assertEqual(sanitize_filename(None), "untitled")
        self.assertEqual(sanitize_filename("..\\", fallback=""), "")

    def test_max_len(self):
        self.assertEqual(len(sanitize_filename("a" * 200)), 64)
        self.assertEqual(len(sanitize_filename("a" * 200, max_len=128)), 128)

    def test_control_chars_removed(self):
        self.assertEqual(sanitize_filename("na\x00me\x1f"), "name")


if __name__ == "__main__":
    unittest.main()

# utils/shortcut_manager.py
"""
키보드 단축키 중앙 관리
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence


# 키 문자열 → Qt.Key 매핑
_KEY_MAP = {
    'up': Qt.Key.Key_Up,
    'down': Qt.Key.Key_Down,
    'left': Qt.Key.Key_Left,
    'right': Qt.Key.Key_Right,
    'delete': Qt.Key.Key_Delete,
    'backspace': Qt.Key.Key_Backspace,
    'return': Qt.Key.Key_Return,
    'enter': Qt.Key.Key_Return,
    'escape': Qt.Key.Key_Escape,
    'esc': Qt.Key.Key_Escape,
    'tab': Qt.Key.Key_Tab,
    'space': Qt.Key.Key_Space,
    'home': Qt.Key.Key_Home,
    'end': Qt.Key.Key_End,
    'pageup': Qt.Key.Key_PageUp,
    'pagedown': Qt.Key.Key_PageDown,
    'insert': Qt.Key.Key_Insert,
    'alt': Qt.Key.Key_Alt,
    'f1': Qt.Key.Key_F1, 'f2': Qt.Key.Key_F2, 'f3': Qt.Key.Key_F3,
    'f4': Qt.Key.Key_F4, 'f5': Qt.Key.Key_F5, 'f6': Qt.Key.Key_F6,
    'f7': Qt.Key.Key_F7, 'f8': Qt.Key.Key_F8, 'f9': Qt.Key.Key_F9,
    'f10': Qt.Key.Key_F10, 'f11': Qt.Key.Key_F11, 'f12': Qt.Key.Key_F12,
}

# Qt.Key → 표시 문자열
_KEY_DISPLAY = {v: k.capitalize() for k, v in _KEY_MAP.items()}
_KEY_DISPLAY[Qt.Key.Key_Return] = 'Return'
_KEY_DISPLAY[Qt.Key.Key_Escape] = 'Escape'

# 단축키 ID → 한글 라벨
SHORTCUT_LABELS = {
    'prev_image': '이전 이미지',
    'next_image': '다음 이미지',
    'delete_image': '이미지 삭제',
    'copy_image': '클립보드 복사',
    'pan_mode': '팬 모드 (이동)',
    'apply_effect': '효과 적용',
    'cancel_selection': '선택 취소',
    'undo': '실행 취소',
    'redo': '다시 실행',
    'tool_box': '사각형 도구',
    'tool_lasso': '올가미 도구',
    'tool_brush': '브러쉬 도구',
    'tool_eraser': '지우개 도구',
}


def _parse_key_string(key_str: str):
    """키 문자열을 (modifiers, key) 튜플로 파싱
    예: 'Ctrl+Z' → (ControlModifier, Key_Z)
         'Alt'   → (NoModifier, Key_Alt)
         'Up'    → (NoModifier, Key_Up)
    """
    parts = [p.strip() for p in key_str.split('+')]
    modifiers = Qt.KeyboardModifier.NoModifier
    key = None

    for part in parts:
        low = part.lower()
        if low == 'ctrl':
            modifiers |= Qt.KeyboardModifier.ControlModifier
        elif low == 'shift':
            modifiers |= Qt.KeyboardModifier.ShiftModifier
        elif low == 'alt' and len(parts) > 1:
            # Alt+X 조합에서 Alt은 수정자
            modifiers |= Qt.KeyboardModifier.AltModifier
        elif low in _KEY_MAP:
            key = _KEY_MAP[low]
        elif len(low) == 1 and low.isalnum():
            key = QKeySequence(part.upper())[0].key()
        else:
            # 알 수 없는 키 → 무시
            pass

    return modifiers, key


def key_event_to_string(event) -> str:
    """QKeyEvent를 사람이 읽을 수 있는 문자열로 변환"""
    parts = []
    mods = event.modifiers()

    if mods & Qt.KeyboardModifier.ControlModifier:
        parts.append('Ctrl')
    if mods & Qt.KeyboardModifier.ShiftModifier:
        parts.append('Shift')
    if mods & Qt.KeyboardModifier.AltModifier:
        parts.append('Alt')

    key = event.key()

    # 수정자 키 자체만 눌린 경우
    if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
        return ''  # 수정자만으로는 단축키 불완전
    if key == Qt.Key.Key_Alt:
        if not parts:
            return 'Alt'  # Alt 단독 (팬 모드 등)
        return ''  # Alt+다른수정자만은 불완전

    # 특수 키
    if key in _KEY_DISPLAY:
        parts.append(_KEY_DISPLAY[key])
    elif 0x20 <= key <= 0x7e:
        parts.append(chr(key).upper())
    else:
        return ''

    return '+'.join(parts)


class ShortcutManager:
    """키보드 단축키 중앙 관리 (싱글톤)"""

    DEFAULTS = {
        'prev_image': 'Up',
        'next_image': 'Down',
        'delete_image': 'Delete',
        'copy_image': 'Ctrl+C',
        'pan_mode': 'Alt',
        'apply_effect': 'Return',
        'cancel_selection': 'Escape',
        'undo': 'Ctrl+Z',
        'redo': 'Ctrl+Y',
        'tool_box': '1',
        'tool_lasso': '2',
        'tool_brush': '3',
        'tool_eraser': '4',
    }

    def __init__(self):
        self._shortcuts = dict(self.DEFAULTS)

    def get(self, name: str) -> str:
        return self._shortcuts.get(name, self.DEFAULTS.get(name, ''))

    def set(self, name: str, key_str: str):
        if name in self.DEFAULTS:
            self._shortcuts[name] = key_str

    def match(self, event, name: str) -> bool:
        """QKeyEvent가 등록된 단축키와 일치하는지 검사"""
        key_str = self.get(name)
        if not key_str:
            return False

        target_mods, target_key = _parse_key_string(key_str)

        if target_key is None:
            return False

        # 수정자 키 자체가 단축키인 경우 (예: Alt → 팬 모드)
        if target_key == Qt.Key.Key_Alt and target_mods == Qt.KeyboardModifier.NoModifier:
            return event.key() == Qt.Key.Key_Alt

        # 일반 단축키
        event_mods = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier |
            Qt.KeyboardModifier.ShiftModifier |
            Qt.KeyboardModifier.AltModifier
        )
        return event.key() == target_key and event_mods == target_mods

    def reset_to_defaults(self):
        self._shortcuts = dict(self.DEFAULTS)

    def to_dict(self) -> dict:
        return dict(self._shortcuts)

    def from_dict(self, d: dict):
        for k, v in d.items():
            if k in self.DEFAULTS:
                self._shortcuts[k] = v


# 싱글톤
_instance = None


def get_shortcut_manager() -> ShortcutManager:
    global _instance
    if _instance is None:
        _instance = ShortcutManager()
    return _instance

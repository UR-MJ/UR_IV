# utils/theme_manager.py
"""
다크/라이트 테마 관리
"""

DEFAULT_FONT_FAMILY = "'Pretendard', 'Malgun Gothic', sans-serif"
DEFAULT_FONT_SIZE = "10.5pt"

DARK_THEME = {
    'bg_primary': '#121212',
    'bg_secondary': '#1E1E1E',
    'bg_tertiary': '#252525',
    'bg_input': '#252525',
    'bg_button': '#2C2C2C',
    'bg_button_hover': '#3A3A3A',
    'bg_button_pressed': '#252525',
    'bg_tab': '#1E1E1E',
    'bg_tab_selected': '#2A2A2A',
    'bg_splitter': '#2C2C2C',
    'text_primary': '#E0E0E0',
    'text_secondary': '#B0B0B0',
    'text_muted': '#888888',
    'text_tab': '#888888',
    'text_tab_selected': '#E0E0E0',
    'border': '#2C2C2C',
    'border_input_focus': '#5865F2',
    'accent': '#5865F2',
    'scrollbar_bg': '#1E1E1E',
    'scrollbar_handle': '#3E3E3E',
    'disabled_bg': '#1E1E1E',
    'disabled_text': '#666666',
}

LIGHT_THEME = {
    'bg_primary': '#F5F5F5',
    'bg_secondary': '#FFFFFF',
    'bg_tertiary': '#E8E8E8',
    'bg_input': '#FFFFFF',
    'bg_button': '#E0E0E0',
    'bg_button_hover': '#D0D0D0',
    'bg_button_pressed': '#C0C0C0',
    'bg_tab': '#E8E8E8',
    'bg_tab_selected': '#FFFFFF',
    'bg_splitter': '#D0D0D0',
    'text_primary': '#1A1A1A',
    'text_secondary': '#555555',
    'text_muted': '#888888',
    'text_tab': '#777777',
    'text_tab_selected': '#1A1A1A',
    'border': '#D0D0D0',
    'border_input_focus': '#5865F2',
    'accent': '#5865F2',
    'scrollbar_bg': '#E8E8E8',
    'scrollbar_handle': '#BBBBBB',
    'disabled_bg': '#E0E0E0',
    'disabled_text': '#AAAAAA',
}

THEMES = {
    '다크': DARK_THEME,
    '라이트': LIGHT_THEME,
}

_QSS_TEMPLATE = """
    QWidget {{
        background-color: {bg_primary};
        color: {text_primary};
        font-family: {font_family};
        font-size: {font_size};
    }}

    QMainWindow {{
        background-color: {bg_primary};
    }}

    QSplitter::handle {{
        background-color: {bg_splitter};
        width: 2px;
    }}

    QGroupBox {{
        background-color: {bg_secondary};
        border: 1px solid {border};
        border-radius: 12px;
        margin-top: 25px;
        padding: 20px 15px 15px 15px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 15px;
        top: 5px;
        color: {text_primary};
        font-weight: bold;
        font-size: 11.5pt;
        background-color: transparent;
    }}

    QLineEdit, QTextEdit, QComboBox {{
        background-color: {bg_input};
        border: none;
        border-radius: 8px;
        padding: 8px 10px;
        color: {text_primary};
        selection-background-color: {accent};
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
        background-color: {bg_tertiary};
        border: 1px solid {border_input_focus};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 25px;
    }}

    QPushButton {{
        background-color: {bg_button};
        border: none;
        border-radius: 8px;
        color: {text_primary};
        padding: 10px 16px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {bg_button_hover};
    }}
    QPushButton:pressed {{
        background-color: {bg_button_pressed};
    }}
    QPushButton:checked {{
        background-color: {bg_button_hover};
        border: 1px solid {accent};
    }}
    QPushButton:disabled {{
        background-color: {disabled_bg};
        color: {disabled_text};
    }}

    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{
        background: {scrollbar_bg};
        width: 10px;
        margin: 0;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background: {scrollbar_handle};
        min-height: 30px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {accent};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        height: 0px; background: none;
    }}

    QTabWidget::pane {{ border: none; background-color: {bg_primary}; }}
    QTabBar::tab {{
        background: {bg_tab}; color: {text_tab}; padding: 10px 20px;
        border-top-left-radius: 8px; border-top-right-radius: 8px;
        margin-right: 2px; font-weight: bold;
    }}
    QTabBar::tab:selected {{
        background: {bg_tab_selected}; color: {text_tab_selected};
        border-bottom: 2px solid {accent};
    }}
    QTabBar::tab:hover {{ background: {bg_tertiary}; color: {text_primary}; }}

    QLabel {{
        color: {text_secondary};
        background: transparent;
    }}
"""


class ThemeManager:
    """테마 관리 클래스"""

    def __init__(self):
        self._current = '다크'
        self._font_family = DEFAULT_FONT_FAMILY
        self._font_size = DEFAULT_FONT_SIZE

    @property
    def current_theme_name(self) -> str:
        return self._current

    @property
    def current_font_family(self) -> str:
        """저장용 원본 글꼴 이름"""
        return self._font_family

    @property
    def current_font_size(self) -> str:
        return self._font_size

    def set_font(self, family: str, size_pt: float):
        """글꼴 설정 변경"""
        if family:
            self._font_family = f"'{family}', 'Malgun Gothic', sans-serif"
        self._font_size = f"{size_pt}pt"

    def get_font_family_name(self) -> str:
        """콤보박스 복원용: 첫 번째 폰트 이름만 추출"""
        raw = self._font_family
        if raw.startswith("'"):
            return raw.split("'")[1]
        return raw.split(",")[0].strip()

    def get_font_size_value(self) -> float:
        """스핀박스 복원용: pt 값만 추출"""
        return float(self._font_size.replace('pt', ''))

    def get_stylesheet(self, theme_name: str | None = None) -> str:
        """테마 이름에 대응하는 QSS 문자열 반환"""
        name = theme_name or self._current
        colors = THEMES.get(name, DARK_THEME)
        self._current = name
        fmt_vars = {
            **colors,
            'font_family': self._font_family,
            'font_size': self._font_size,
        }
        return _QSS_TEMPLATE.format(**fmt_vars)

    @staticmethod
    def available_themes() -> list[str]:
        return list(THEMES.keys())


# 싱글톤
_instance: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    global _instance
    if _instance is None:
        _instance = ThemeManager()
    return _instance

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
    'bg_status_bar': '#1A1A1A',
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
    'bg_status_bar': '#E0E0E0',
}

GEMINI_THEME = {
    'bg_primary': '#0A0A0A',
    'bg_secondary': '#141414',
    'bg_tertiary': '#1F1F1F',
    'bg_input': '#141414',
    'bg_button': '#1F1F1F',
    'bg_button_hover': '#2A2A2A',
    'bg_button_pressed': '#0A0A0A',
    'bg_tab': '#0A0A0A',
    'bg_tab_selected': '#0A0A0A',
    'bg_splitter': '#1F1F1F',
    'text_primary': '#FFFFFF',
    'text_secondary': '#A0A0A0',
    'text_muted': '#606060',
    'text_tab': '#606060',
    'text_tab_selected': '#FFFFFF',
    'border': '#1F1F1F',
    'border_input_focus': '#FACC15',
    'accent': '#FACC15',
    'scrollbar_bg': '#0A0A0A',
    'scrollbar_handle': '#2A2A2A',
    'disabled_bg': '#0F0F0F',
    'disabled_text': '#404040',
    'bg_status_bar': '#050505',
}

CLAUDE_THEME = {
    'bg_primary': '#0D0D0D',
    'bg_secondary': '#161616',
    'bg_tertiary': '#1C1C1C',
    'bg_input': '#111111',
    'bg_button': '#1A1A1A',
    'bg_button_hover': '#252525',
    'bg_button_pressed': '#0D0D0D',
    'bg_tab': '#0D0D0D',
    'bg_tab_selected': '#0D0D0D',
    'bg_splitter': '#1C1C1C',
    'text_primary': '#F0F0F0',
    'text_secondary': '#909090',
    'text_muted': '#555555',
    'text_tab': '#555555',
    'text_tab_selected': '#F0F0F0',
    'border': '#1E1E1E',
    'border_input_focus': '#E2B340',
    'accent': '#E2B340',
    'scrollbar_bg': '#0D0D0D',
    'scrollbar_handle': '#2A2A2A',
    'disabled_bg': '#111111',
    'disabled_text': '#3A3A3A',
    'bg_status_bar': '#080808',
}

THEMES = {
    'Claude': CLAUDE_THEME,
    'Gemini': GEMINI_THEME,
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
        width: 1px;
    }}

    QGroupBox {{
        background-color: {bg_secondary};
        border: 1px solid {border};
        border-radius: 6px;
        margin-top: 12px;
        padding: 24px 16px 16px 16px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 16px;
        top: 6px;
        color: {text_primary};
        font-weight: bold;
        font-size: 10pt;
    }}

    QLineEdit, QTextEdit, QComboBox {{
        background-color: {bg_input};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 8px 12px;
        color: {text_primary};
        selection-background-color: {accent};
        selection-color: black;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
        border: 1px solid {accent};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 28px;
    }}

    QPushButton {{
        background-color: {bg_button};
        border: 1px solid {border};
        border-radius: 6px;
        color: {text_primary};
        padding: 8px 16px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {bg_button_hover};
        border: 1px solid {accent};
    }}
    QPushButton:pressed {{
        background-color: {bg_button_pressed};
    }}
    QPushButton:checked {{
        background-color: {accent};
        color: black;
        border: 1px solid {accent};
    }}
    QPushButton:disabled {{
        background-color: {disabled_bg};
        color: {disabled_text};
        border: 1px solid {disabled_bg};
    }}

    QPushButton#primaryButton {{
        background-color: {accent};
        color: black;
        border: none;
        font-weight: 800;
    }}
    QPushButton#primaryButton:hover {{
        background-color: white;
    }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: transparent;
        width: 4px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {scrollbar_handle};
        min-height: 40px;
        border-radius: 2px;
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
        background: transparent;
        color: {text_muted};
        padding: 12px 20px;
        margin-right: 8px;
        font-weight: 600;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {text_primary};
        border-bottom: 2px solid {accent};
    }}
    QTabBar::tab:hover {{
        color: {text_primary};
    }}

    QLabel {{
        color: {text_secondary};
        background: transparent;
    }}

    QProgressBar {{
        background-color: {bg_input};
        border: none;
        border-radius: 2px;
        text-align: center;
        color: {text_primary};
        height: 4px;
    }}
    QProgressBar::chunk {{
        background-color: {accent};
    }}

    QListWidget {{
        background-color: {bg_secondary};
        border: 1px solid {border};
        border-radius: 4px;
        color: {text_primary};
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 6px 10px;
        border-radius: 3px;
    }}
    QListWidget::item:selected {{
        background-color: {accent};
        color: black;
    }}
    QListWidget::item:hover {{
        background-color: {bg_tertiary};
    }}

    QSpinBox, QDoubleSpinBox {{
        background-color: {bg_input};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 6px 10px;
        color: {text_primary};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {accent};
    }}

    QSlider::groove:horizontal {{
        height: 3px;
        background: {bg_tertiary};
        border-radius: 1px;
    }}
    QSlider::handle:horizontal {{
        width: 14px; height: 14px;
        margin: -6px 0;
        background: {accent};
        border-radius: 7px;
    }}
    QSlider::sub-page:horizontal {{
        background: {accent};
        border-radius: 1px;
    }}

    QMenu {{
        background-color: {bg_secondary};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 4px;
        color: {text_primary};
    }}
    QMenu::item {{
        padding: 7px 20px;
        border-radius: 3px;
    }}
    QMenu::item:selected {{
        background-color: {accent};
        color: black;
    }}
    QMenu::separator {{
        height: 1px;
        background: {border};
        margin: 4px 8px;
    }}

    QToolTip {{
        background-color: {bg_secondary};
        color: {text_primary};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 5px 8px;
    }}

    QDialog {{
        background-color: {bg_primary};
        color: {text_primary};
    }}

    QFrame {{
        color: {text_primary};
    }}

    QStatusBar {{
        background-color: {bg_status_bar};
        color: {text_muted};
        border-top: 1px solid {border};
    }}

    QCheckBox {{
        color: {text_primary};
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {border};
        border-radius: 3px;
        background: {bg_input};
    }}
    QCheckBox::indicator:checked {{
        background: {accent};
        border: 1px solid {accent};
    }}

    QRadioButton {{
        color: {text_primary};
        spacing: 6px;
    }}
    QRadioButton::indicator {{
        width: 14px; height: 14px;
        border: 1px solid {border};
        border-radius: 7px;
        background: {bg_input};
    }}
    QRadioButton::indicator:checked {{
        background: {accent};
        border: 2px solid {accent};
    }}
"""


class ThemeManager:
    """테마 관리 클래스"""

    def __init__(self):
        self._current = 'Claude'
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

    def get_colors(self) -> dict:
        """현재 테마 색상 딕셔너리 반환"""
        return THEMES.get(self._current, DARK_THEME)

    def get_stylesheet(self, theme_name: str | None = None) -> str:
        """테마 이름에 대응하는 QSS 문자열 반환"""
        import config
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


def get_color(key: str) -> str:
    """테마 색상 단축 접근 헬퍼"""
    return get_theme_manager().get_colors().get(key, '#888888')

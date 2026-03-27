# utils/theme_manager.py
"""
다크/라이트 테마 관리
"""
DEFAULT_FONT_FAMILY = "'Pretendard', 'Malgun Gothic', sans-serif"
DEFAULT_FONT_SIZE = "10.5pt"

MODERN_THEME = {
    'bg_primary': '#0A0A0A',
    'bg_secondary': '#131313',
    'bg_tertiary': '#1A1A1A',
    'bg_input': '#131313',
    'bg_button': '#181818',
    'bg_button_hover': '#222222',
    'bg_button_pressed': '#0E0E0E',
    'bg_tab': 'transparent',
    'bg_tab_selected': '#1A1A1A',
    'bg_splitter': '#151515',
    'text_primary': '#E8E8E8',
    'text_secondary': '#787878',
    'text_muted': '#484848',
    'text_tab': '#585858',
    'text_tab_selected': '#E8E8E8',
    'border': '#1A1A1A',
    'border_input_focus': '#E2B340',
    'accent': '#E2B340',
    'accent_hover': '#F0C850',
    'accent_dim': '#3A3020',
    'accent_gradient': 'qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E2B340, stop:1 #D4882A)',
    'success': '#4CAF50',
    'error': '#E05252',
    'warning': '#E2B340',
    'info': '#E2B340',
    'scrollbar_bg': '#0A0A0A',
    'scrollbar_handle': '#222222',
    'disabled_bg': '#0E0E0E',
    'disabled_text': '#333333',
    'bg_status_bar': '#070707',
    # Layout Variables
    'radius_base': '6px',
    'radius_card': '8px',
    'radius_button': '8px',
    'radius_primary_btn': '10px',
    'tab_padding': '10px 18px',
    'tab_margin': '0px 4px 0px 0px',
    'primary_btn_bg_hover': '#F0C850',
    'primary_btn_bg_disabled': '#3A3020',
    'primary_btn_text_disabled': '#666050',
}

THEMES = {
    '모던': MODERN_THEME,
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
        background-color: transparent;
        width: 1px;
    }}

    /* ── GroupBox: 카드 기반 레이아웃 ── */
    QGroupBox {{
        background-color: {bg_secondary};
        border: 1px solid {border};
        border-radius: {radius_card};
        margin-top: 18px;
        padding: 35px 12px 12px 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 18px;
        top: 12px;
        color: {text_secondary};
        font-weight: 700;
        font-size: 8.5pt;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    /* ── 입력 필드 ── */
    QLineEdit, QTextEdit, QComboBox {{
        background-color: {bg_input};
        border: 1px solid {border};
        border-radius: {radius_base};
        padding: 6px 10px;
        color: {text_primary};
        selection-background-color: {accent};
        selection-color: black;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
        border: 1px solid {accent};
        background-color: {bg_secondary};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}

    /* ── 버튼 ── */
    QPushButton {{
        background-color: {bg_button};
        border: 1px solid {border};
        border-radius: {radius_button};
        color: {text_primary};
        padding: 6px 12px;
        font-weight: 600;
        min-height: 24px;
    }}
    QPushButton:hover {{
        background-color: {bg_button_hover};
        border: 1px solid {text_secondary};
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
        border: 1px solid {border};
    }}

    /* ── 생성 버튼 ── */
    QPushButton#primaryButton {{
        background: {accent_gradient};
        color: black;
        border: none;
        border-radius: {radius_primary_btn};
        font-weight: 800;
        font-size: 11pt;
        padding: 10px;
        min-height: 36px;
    }}
    QPushButton#primaryButton:hover {{
        background: {primary_btn_bg_hover};
    }}
    QPushButton#primaryButton:disabled {{
        background: {primary_btn_bg_disabled};
        color: {primary_btn_text_disabled};
    }}

    /* ── 스크롤바 ── */
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

    /* ── 탭 ── */
    QTabWidget::pane {{ border: none; background-color: {bg_primary}; }}
    QTabBar {{
        alignment: center;
    }}
    QTabBar::tab {{
        background: {bg_button};
        color: {text_tab};
        padding: {tab_padding};
        margin: {tab_margin};
        font-weight: 700;
        border-radius: {radius_button};
        border: 1px solid {border};
        font-size: 9pt;
        min-width: 50px;
    }}
    QTabBar::tab:selected {{
        background: {bg_tertiary};
        color: {text_tab_selected};
        border: 1px solid {accent};
    }}
    QTabBar::tab:hover {{
        background: {bg_button_hover};
        color: {text_primary};
    }}

    QLabel {{
        color: {text_secondary};
        background: transparent;
    }}

    /* ── 체크박스: 기본 윈도우 스타일 유지 ── */
    QCheckBox {{
        color: {text_primary};
        spacing: 8px;
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

    QSlider::groove:horizontal {{
        height: 4px;
        background: {bg_input};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 16px; height: 16px;
        margin: -6px 0;
        background: {accent};
        border-radius: 8px;
    }}

    QListWidget {{
        background-color: {bg_secondary};
        border: 1px solid {border};
        border-radius: {radius_card};
        color: {text_primary};
        padding: 10px;
    }}
    QListWidget::item {{
        padding: 12px;
        border-radius: {radius_base};
        margin-bottom: 4px;
    }}
    QListWidget::item:selected {{
        background-color: {accent};
        color: black;
    }}
    QListWidget::item:hover {{
        background-color: {bg_tertiary};
    }}
"""


class ThemeManager:
    """테마 관리 클래스"""

    def __init__(self):
        self._current = '모던'
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
        return THEMES.get(self._current, MODERN_THEME)

    def get_stylesheet(self, theme_name: str | None = None) -> str:
        """테마 이름에 대응하는 QSS 문자열 반환"""
        import config
        name = theme_name or self._current
        colors = THEMES.get(name, MODERN_THEME)
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

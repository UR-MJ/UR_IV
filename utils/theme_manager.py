# utils/theme_manager.py
"""
테마 관리
"""
DEFAULT_FONT_FAMILY = "'Pretendard', 'Malgun Gothic', sans-serif"
DEFAULT_FONT_SIZE = "10.5pt"

# 모던 다크 (NAIS2 스타일 — 골드 강조색 + 알약형 레이아웃)
MODERN_THEME = {
    'bg_primary': '#0A0A0A',
    'bg_secondary': '#131313',
    'bg_tertiary': '#1A1A1A',
    'bg_input': '#141414',
    'bg_button': '#1C1C1C',
    'bg_button_hover': '#262626',
    'bg_button_pressed': '#0E0E0E',
    'bg_tab': 'transparent',
    'bg_tab_selected': '#1A1A1A',
    'bg_splitter': '#151515',
    'text_primary': '#F0F0F0',
    'text_secondary': '#888888',
    'text_muted': '#505050',
    'text_tab': '#606060',
    'text_tab_selected': '#F0F0F0',
    'border': '#1C1C1C',
    'border_input_focus': '#E2B340',
    'accent': '#E2B340',
    'accent_hover': '#F0C850',
    'accent_gradient': 'qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E2B340, stop:1 #D4882A)',
    'success': '#4CAF50',
    'error': '#E05252',
    'warning': '#E2B340',
    'info': '#E2B340',
    'scrollbar_bg': '#0A0A0A',
    'scrollbar_handle': '#232323',
    'disabled_bg': '#0F0F0F',
    'disabled_text': '#353535',
    'bg_status_bar': '#070707',
    # Layout Variables (Pill - NAIS2)
    'radius_base': '10px',
    'radius_card': '12px',
    'radius_button': '18px',
    'radius_primary_btn': '22px',
    'tab_padding': '8px 20px',
    'tab_margin': '4px 4px',
    'primary_btn_bg_hover': 'qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #F0C850, stop:1 #E09030)',
    'primary_btn_bg_disabled': '#1A1810',
    'primary_btn_text_disabled': '#504830',
}

# 클래식 다크 (기존 Discord 블루 스타일)
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
    'accent_hover': '#6B76FF',
    'accent_gradient': '#5865F2',
    'success': '#4CAF50',
    'error': '#F44336',
    'warning': '#FFC107',
    'info': '#5865F2',
    'scrollbar_bg': '#1E1E1E',
    'scrollbar_handle': '#3E3E3E',
    'disabled_bg': '#1E1E1E',
    'disabled_text': '#666666',
    'bg_status_bar': '#1A1A1A',
    # Layout Variables (Sharp)
    'radius_base': '4px',
    'radius_card': '6px',
    'radius_button': '4px',
    'radius_primary_btn': '6px',
    'tab_padding': '10px 16px',
    'tab_margin': '2px',
    'primary_btn_bg_hover': '#6B76FF',
    'primary_btn_bg_disabled': '#1E1E1E',
    'primary_btn_text_disabled': '#666666',
}

THEMES = {
    '모던': MODERN_THEME,
    '다크': DARK_THEME,
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
        padding: 35px 16px 16px 16px;
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
        padding: 10px 15px;
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
        width: 30px;
    }}

    /* ── 버튼 ── */
    QPushButton {{
        background-color: {bg_button};
        border: 1px solid {border};
        border-radius: {radius_button};
        color: {text_primary};
        padding: 8px 20px;
        font-weight: 600;
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
        padding: 12px;
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
    QTabBar::tab {{
        background: {bg_button};
        color: {text_tab};
        padding: {tab_padding};
        margin: {tab_margin};
        font-weight: 700;
        border-radius: {radius_button};
        border: 1px solid {border};
        font-size: 9pt;
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

    /* ── 체크박스 / 라디오 ── */
    QCheckBox {{
        color: {text_primary};
        spacing: 10px;
    }}
    QCheckBox::indicator {{
        width: 18px; height: 18px;
        border: 2px solid {border};
        border-radius: 5px;
        background: {bg_input};
    }}
    QCheckBox::indicator:checked {{
        background: {accent};
        border: 2px solid {accent};
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

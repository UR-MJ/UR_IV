# tabs/editor/draw_panel.py
"""그리기 도구 패널"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QButtonGroup, QFrame, QGridLayout, QColorDialog, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from widgets.sliders import NumericSlider


_PALETTE_COLORS = [
    "#000000", "#FFFFFF", "#FF0000", "#00FF00",
    "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF",
    "#FF8800", "#8800FF", "#888888", "#FF4488",
]

_TOOL_BTN_STYLE = """
    QPushButton {
        background-color: #2C2C2C; border: 1px solid #444;
        border-radius: 6px; color: #CCC;
        font-size: 13px; font-weight: bold;
        text-align: left; padding-left: 12px;
    }
    QPushButton:checked {
        background-color: #5865F2; color: white;
        border: 1px solid #5865F2;
    }
    QPushButton:hover { border: 1px solid #666; background-color: #333; }
    QPushButton:checked:hover { background-color: #6975F3; }
"""


class DrawPanel(QWidget):
    """그리기 도구 패널"""

    # 스포이트로 색상 추출 시 외부에서 연결
    color_changed = pyqtSignal()

    def __init__(self, parent_editor=None):
        super().__init__()
        self.parent_editor = parent_editor
        self._current_color = QColor("#000000")
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # ── 도구 선택 ──
        tool_header = QLabel("그리기 도구")
        tool_header.setStyleSheet(
            "color: #999; font-size: 18px; font-weight: bold; padding: 2px 2px;"
        )
        main_layout.addWidget(tool_header)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        tools = [
            (0, "🖊️  펜 (자유 그리기)"),
            (1, "📏  직선"),
            (2, "⬜  사각형"),
            (3, "⭕  원/타원"),
            (4, "🎨  채우기"),
            (5, "💉  스포이트"),
        ]

        for id_val, text in tools:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(_TOOL_BTN_STYLE)
            self.tool_group.addButton(btn, id_val)
            main_layout.addWidget(btn)

        self.tool_group.button(0).setChecked(True)

        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet("color: #333;")
        main_layout.addWidget(line1)

        # ── 팔레트 ──
        palette_header = QLabel("색상")
        palette_header.setStyleSheet(
            "color: #999; font-size: 14px; font-weight: bold; padding: 2px 2px;"
        )
        main_layout.addWidget(palette_header)

        palette_grid = QGridLayout()
        palette_grid.setSpacing(4)

        self._color_buttons = []
        for i, hex_color in enumerate(_PALETTE_COLORS):
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(
                f"background-color: {hex_color}; border: 2px solid #444; border-radius: 4px;"
            )
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked, c=hex_color: self._on_palette_click(c))
            palette_grid.addWidget(btn, i // 6, i % 6)
            self._color_buttons.append(btn)

        main_layout.addLayout(palette_grid)

        # 현재 색상 표시 + 커스텀 색상 버튼
        color_row = QHBoxLayout()
        color_row.setSpacing(6)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(36, 36)
        self._update_color_preview()
        color_row.addWidget(self.color_preview)

        btn_custom = QPushButton("+ 색상 선택")
        btn_custom.setFixedHeight(36)
        btn_custom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_custom.setStyleSheet(
            "background-color: #2C2C2C; color: #DDD; border: 1px solid #555; "
            "border-radius: 4px; font-size: 12px; font-weight: bold;"
        )
        btn_custom.clicked.connect(self._on_custom_color)
        color_row.addWidget(btn_custom)

        main_layout.addLayout(color_row)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet("color: #333;")
        main_layout.addWidget(line2)

        # ── 설정 슬라이더 ──
        self.slider_size = NumericSlider("크기", 1, 100, 3)
        main_layout.addWidget(self.slider_size)

        self.slider_opacity = NumericSlider("투명도", 1, 100, 100)
        main_layout.addWidget(self.slider_opacity)

        # ── 채우기/외곽선 토글 ──
        self.btn_filled = QPushButton("■ 채우기")
        self.btn_filled.setCheckable(True)
        self.btn_filled.setChecked(False)
        self.btn_filled.setFixedHeight(34)
        self.btn_filled.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_filled.setStyleSheet("""
            QPushButton {
                background-color: #2C2C2C; color: #CCC; border: 1px solid #444;
                border-radius: 6px; font-size: 13px; font-weight: bold;
            }
            QPushButton:checked {
                background-color: #4A90E2; color: white; border: 1px solid #4A90E2;
            }
            QPushButton:hover { border: 1px solid #666; }
        """)
        main_layout.addWidget(self.btn_filled)

        main_layout.addStretch(1)

        # 시그널 연결
        self.tool_group.buttonClicked.connect(self._on_tool_changed)
        self.slider_size.valueChanged.connect(self._on_param_changed)
        self.slider_opacity.valueChanged.connect(self._on_param_changed)
        self.btn_filled.toggled.connect(self._on_param_changed)

    # ── 속성 ──

    def current_draw_tool(self) -> str:
        """현재 그리기 도구 이름"""
        _map = {0: 'pen', 1: 'line', 2: 'rect', 3: 'ellipse', 4: 'fill', 5: 'eyedropper'}
        return _map.get(self.tool_group.checkedId(), 'pen')

    def current_color_bgr(self) -> tuple:
        """현재 선택 색상 (BGR)"""
        return (self._current_color.blue(), self._current_color.green(), self._current_color.red())

    def current_size(self) -> int:
        return self.slider_size.value()

    def current_opacity(self) -> float:
        return self.slider_opacity.value() / 100.0

    def is_filled(self) -> bool:
        return self.btn_filled.isChecked()

    def set_color_from_bgr(self, bgr: tuple):
        """스포이트 결과 반영 (BGR)"""
        self._current_color = QColor(bgr[2], bgr[1], bgr[0])
        self._update_color_preview()
        self._sync_to_label()

    # ── 내부 ──

    def _update_color_preview(self):
        hex_c = self._current_color.name()
        self.color_preview.setStyleSheet(
            f"background-color: {hex_c}; border: 2px solid #666; border-radius: 4px;"
        )

    def _on_palette_click(self, hex_color: str):
        self._current_color = QColor(hex_color)
        self._update_color_preview()
        self._sync_to_label()

    def _on_custom_color(self):
        color = QColorDialog.getColor(self._current_color, self, "색상 선택")
        if color.isValid():
            self._current_color = color
            self._update_color_preview()
            self._sync_to_label()

    def _on_tool_changed(self, btn):
        self._sync_to_label()
        if self.parent_editor and hasattr(self.parent_editor, 'image_label'):
            self.parent_editor.image_label.setFocus()

    def _on_param_changed(self, *args):
        self._sync_to_label()

    def _sync_to_label(self):
        """현재 설정을 InteractiveLabel에 동기화"""
        if not self.parent_editor:
            return
        label = getattr(self.parent_editor, 'image_label', None)
        if label and hasattr(label, 'set_draw_params'):
            label.set_draw_params(
                tool=self.current_draw_tool(),
                color=self.current_color_bgr(),
                size=self.current_size(),
                opacity=self.current_opacity(),
                filled=self.is_filled(),
            )

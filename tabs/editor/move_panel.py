# tabs/editor/move_panel.py
"""영역 이동 도구 패널"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QComboBox
)
from PyQt6.QtCore import Qt
from widgets.sliders import NumericSlider


_BTN_STYLE = """
    QPushButton {
        background-color: #2C2C2C; border: 1px solid #444;
        border-radius: 6px; color: #CCC;
        font-size: 13px; font-weight: bold;
        padding: 8px 12px;
    }
    QPushButton:hover { border: 1px solid #666; background-color: #333; }
    QPushButton:disabled { color: #555; background-color: #222; }
"""

_ACCENT_BTN = """
    QPushButton {
        background-color: #5865F2; border: 1px solid #5865F2;
        border-radius: 6px; color: white;
        font-size: 13px; font-weight: bold;
        padding: 8px 12px;
    }
    QPushButton:hover { background-color: #6975F3; }
    QPushButton:disabled { background-color: #3A3A5C; color: #777; }
"""

_INPAINT_BTN = """
    QPushButton {
        background-color: #e67e22; border: 1px solid #e67e22;
        border-radius: 6px; color: white;
        font-size: 13px; font-weight: bold;
        padding: 8px 12px;
    }
    QPushButton:hover { background-color: #f39c12; }
    QPushButton:disabled { background-color: #5C4A2C; color: #777; }
"""


class MovePanel(QWidget):
    """영역 이동 도구 패널"""

    def __init__(self, parent_editor=None):
        super().__init__()
        self.parent_editor = parent_editor
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 헤더
        header = QLabel("영역 이동")
        header.setStyleSheet(
            "color: #999; font-size: 18px; font-weight: bold; padding: 2px 2px;"
        )
        layout.addWidget(header)

        # 상태 라벨
        self.status_label = QLabel("마스킹을 먼저 해주세요")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "color: #AAA; font-size: 12px; padding: 6px; "
            "background-color: #1E1E1E; border-radius: 4px;"
        )
        layout.addWidget(self.status_label)

        # 구분선
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet("color: #333;")
        layout.addWidget(line1)

        # 채우기 색상
        fill_label = QLabel("구멍 채우기 색")
        fill_label.setStyleSheet("color: #999; font-size: 12px; font-weight: bold;")
        layout.addWidget(fill_label)

        self.fill_combo = QComboBox()
        self.fill_combo.addItem("검은색", (0, 0, 0))
        self.fill_combo.addItem("흰색", (255, 255, 255))
        self.fill_combo.setStyleSheet(
            "background-color: #2C2C2C; color: #CCC; border: 1px solid #444; "
            "border-radius: 4px; padding: 4px;"
        )
        self.fill_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.fill_combo)

        # 회전 / 크기 슬라이더
        self.slider_rotation = NumericSlider("회전 (°)", -180, 180, 0)
        layout.addWidget(self.slider_rotation)

        self.slider_scale = NumericSlider("크기 (%)", 10, 500, 100)
        layout.addWidget(self.slider_scale)

        # 이동 시작 버튼
        self.btn_start_move = QPushButton("✂️  이동 시작")
        self.btn_start_move.setFixedHeight(40)
        self.btn_start_move.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_start_move.setStyleSheet(_ACCENT_BTN)
        layout.addWidget(self.btn_start_move)

        # 확정 / 취소
        row = QHBoxLayout()
        row.setSpacing(6)

        self.btn_confirm = QPushButton("✅ 확정")
        self.btn_confirm.setFixedHeight(36)
        self.btn_confirm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_confirm.setStyleSheet(_BTN_STYLE)
        self.btn_confirm.setEnabled(False)
        row.addWidget(self.btn_confirm)

        self.btn_cancel = QPushButton("❌ 취소")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_cancel.setStyleSheet(_BTN_STYLE)
        self.btn_cancel.setEnabled(False)
        row.addWidget(self.btn_cancel)

        layout.addLayout(row)

        # 구분선
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet("color: #333;")
        layout.addWidget(line2)

        # Inpaint 전송
        self.btn_send_inpaint = QPushButton("🎨  Inpaint 전송")
        self.btn_send_inpaint.setFixedHeight(40)
        self.btn_send_inpaint.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_send_inpaint.setStyleSheet(_INPAINT_BTN)
        self.btn_send_inpaint.setEnabled(False)
        layout.addWidget(self.btn_send_inpaint)

        layout.addStretch(1)

    def update_status(self, text: str):
        """상태 라벨 업데이트"""
        self.status_label.setText(text)

    def set_moving_state(self, moving: bool):
        """이동 중 상태에 따라 버튼 활성화"""
        self.btn_start_move.setEnabled(not moving)
        self.btn_confirm.setEnabled(moving)
        self.btn_cancel.setEnabled(moving)
        self.btn_send_inpaint.setEnabled(False)

    def set_confirmed_state(self):
        """이동 확정 후 상태"""
        self.btn_start_move.setEnabled(True)
        self.btn_confirm.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_send_inpaint.setEnabled(True)

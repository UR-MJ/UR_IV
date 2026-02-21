# widgets/toggle_switch.py
"""
iOS 스타일 애니메이션 토글 스위치 위젯
QCheckBox 호환 인터페이스 제공
"""
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRectF,
    pyqtSignal, pyqtProperty, QSize
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

from utils.theme_manager import get_color


class ToggleSwitch(QWidget):
    """iOS 스타일 토글 스위치"""

    toggled = pyqtSignal(bool)
    stateChanged = pyqtSignal(int)   # QCheckBox 호환 (0=unchecked, 2=checked)

    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self._checked = checked
        self._handle_pos = 1.0 if checked else 0.0
        self._track_w = 44
        self._track_h = 24
        self._handle_size = 20
        self._handle_margin = 2
        self._animation = QPropertyAnimation(self, b"handlePos", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.setFixedSize(self._track_w, self._track_h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(self._track_w, self._track_h)

    @pyqtProperty(float)
    def handlePos(self) -> float:
        return self._handle_pos

    @handlePos.setter
    def handlePos(self, value: float):
        self._handle_pos = value
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked == checked:
            return
        self._checked = checked
        self._animate(checked)
        self.toggled.emit(checked)
        self.stateChanged.emit(2 if checked else 0)

    def checkState(self):
        """QCheckBox 호환"""
        return Qt.CheckState.Checked if self._checked else Qt.CheckState.Unchecked

    def setCheckState(self, state):
        """QCheckBox 호환"""
        self.setChecked(state == Qt.CheckState.Checked or state == 2)

    def toggle(self):
        self.setChecked(not self._checked)

    def _animate(self, checked: bool):
        self._animation.stop()
        self._animation.setStartValue(self._handle_pos)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 색상 계산
        accent = QColor(get_color('accent'))
        off_color = QColor(get_color('scrollbar_handle'))

        # 트랙 색상 (OFF→ON 보간)
        t = self._handle_pos
        track_r = int(off_color.red() + (accent.red() - off_color.red()) * t)
        track_g = int(off_color.green() + (accent.green() - off_color.green()) * t)
        track_b = int(off_color.blue() + (accent.blue() - off_color.blue()) * t)
        track_color = QColor(track_r, track_g, track_b)

        # 트랙 그리기
        track_rect = QRectF(0, 0, self._track_w, self._track_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(track_rect, self._track_h / 2, self._track_h / 2)

        # 핸들 위치 계산
        margin = self._handle_margin
        max_x = self._track_w - self._handle_size - margin
        handle_x = margin + (max_x - margin) * self._handle_pos
        handle_y = (self._track_h - self._handle_size) / 2

        # 핸들 그리기
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(QRectF(handle_x, handle_y, self._handle_size, self._handle_size))

        p.end()

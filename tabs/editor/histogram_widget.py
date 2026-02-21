# tabs/editor/histogram_widget.py
"""실시간 히스토그램 표시 위젯"""
import cv2
import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPen


class HistogramWidget(QWidget):
    """R/G/B 채널별 히스토그램 표시 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setMinimumWidth(200)
        self._hist_b = None
        self._hist_g = None
        self._hist_r = None

    def update_histogram(self, cv_img: np.ndarray):
        """이미지 히스토그램 계산 및 갱신"""
        if cv_img is None:
            self._hist_b = self._hist_g = self._hist_r = None
            self.update()
            return

        self._hist_b = cv2.calcHist([cv_img], [0], None, [256], [0, 256]).flatten()
        self._hist_g = cv2.calcHist([cv_img], [1], None, [256], [0, 256]).flatten()
        self._hist_r = cv2.calcHist([cv_img], [2], None, [256], [0, 256]).flatten()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 배경
        painter.fillRect(self.rect(), QColor("#1A1A1A"))

        if self._hist_b is None:
            painter.setPen(QColor("#555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "히스토그램 없음")
            painter.end()
            return

        w = self.width() - 4
        h = self.height() - 4
        ox, oy = 2, 2

        # 최대값으로 정규화
        max_val = max(
            self._hist_r.max(), self._hist_g.max(), self._hist_b.max(), 1
        )

        # 각 채널 그리기 (반투명)
        channels = [
            (self._hist_r, QColor(220, 50, 50, 100)),
            (self._hist_g, QColor(50, 200, 50, 100)),
            (self._hist_b, QColor(50, 80, 220, 100)),
        ]

        for hist, color in channels:
            painter.setPen(QPen(color, 1))
            normalized = hist / max_val
            step = w / 256.0
            for i in range(256):
                bar_h = int(normalized[i] * h)
                x = int(ox + i * step)
                painter.drawLine(x, oy + h, x, oy + h - bar_h)

        # 테두리
        painter.setPen(QPen(QColor("#444"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(ox, oy, w, h)

        painter.end()

# tabs/editor/perspective_dialog.py
"""원근 보정 다이얼로그 — 4점 드래그로 투시 변환"""
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QImage, QPen, QColor, QBrush, QPixmap
from utils.theme_manager import get_color


class PerspectiveCanvas(QWidget):
    """이미지 위에 4개 꼭짓점을 드래그할 수 있는 캔버스"""

    _HANDLE_RADIUS = 8

    def __init__(self, cv_img: np.ndarray, parent=None):
        super().__init__(parent)
        self._cv_img = cv_img
        self._img_h, self._img_w = cv_img.shape[:2]

        # QImage 변환
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        self._qimage = QImage(
            rgb.data.tobytes(), self._img_w, self._img_h,
            self._img_w * 3, QImage.Format.Format_RGB888
        )

        # 4개 꼭짓점 (이미지 좌표계, 초기값: 이미지 모서리에서 약간 안쪽)
        margin = 0.05
        self._points = [
            QPointF(self._img_w * margin, self._img_h * margin),          # 좌상
            QPointF(self._img_w * (1 - margin), self._img_h * margin),    # 우상
            QPointF(self._img_w * (1 - margin), self._img_h * (1 - margin)),  # 우하
            QPointF(self._img_w * margin, self._img_h * (1 - margin)),    # 좌하
        ]
        self._dragging_idx = -1

        self.setMinimumSize(400, 300)

    def _display_rect(self) -> QRectF:
        """위젯 내 이미지가 그려지는 영역 (비율 유지)"""
        w_ratio = self.width() / self._img_w
        h_ratio = self.height() / self._img_h
        scale = min(w_ratio, h_ratio)
        dw = self._img_w * scale
        dh = self._img_h * scale
        dx = (self.width() - dw) / 2
        dy = (self.height() - dh) / 2
        return QRectF(dx, dy, dw, dh)

    def _img_to_widget(self, pt: QPointF) -> QPointF:
        """이미지 좌표 → 위젯 좌표"""
        r = self._display_rect()
        x = r.x() + pt.x() / self._img_w * r.width()
        y = r.y() + pt.y() / self._img_h * r.height()
        return QPointF(x, y)

    def _widget_to_img(self, pt: QPointF) -> QPointF:
        """위젯 좌표 → 이미지 좌표"""
        r = self._display_rect()
        x = (pt.x() - r.x()) / r.width() * self._img_w
        y = (pt.y() - r.y()) / r.height() * self._img_h
        x = max(0, min(self._img_w, x))
        y = max(0, min(self._img_h, y))
        return QPointF(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 배경
        painter.fillRect(self.rect(), QColor(get_color('bg_secondary')))

        # 이미지
        r = self._display_rect()
        painter.drawImage(r, self._qimage)

        # 반투명 오버레이
        painter.setBrush(QBrush(QColor(88, 101, 242, 40)))
        pen = QPen(QColor("#5865F2"), 2)
        painter.setPen(pen)

        widget_pts = [self._img_to_widget(p) for p in self._points]
        from PyQt6.QtGui import QPolygonF
        painter.drawPolygon(QPolygonF(widget_pts))

        # 연결선
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        for i in range(4):
            painter.drawLine(widget_pts[i], widget_pts[(i + 1) % 4])

        # 핸들
        labels = ["TL", "TR", "BR", "BL"]
        for i, wpt in enumerate(widget_pts):
            # 원
            painter.setPen(QPen(QColor("#5865F2"), 2))
            painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
            painter.drawEllipse(wpt, self._HANDLE_RADIUS, self._HANDLE_RADIUS)
            # 라벨
            painter.setPen(QColor("#333"))
            painter.drawText(
                QRectF(wpt.x() - 10, wpt.y() - 6, 20, 12),
                Qt.AlignmentFlag.AlignCenter, labels[i]
            )

        painter.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = QPointF(event.position())
        for i, pt in enumerate(self._points):
            wpt = self._img_to_widget(pt)
            if (pos - wpt).manhattanLength() < self._HANDLE_RADIUS * 2:
                self._dragging_idx = i
                return

    def mouseMoveEvent(self, event):
        if self._dragging_idx < 0:
            return
        img_pt = self._widget_to_img(QPointF(event.position()))
        self._points[self._dragging_idx] = img_pt
        self.update()

    def mouseReleaseEvent(self, event):
        self._dragging_idx = -1

    def get_src_points(self) -> np.ndarray:
        """현재 4개 꼭짓점 (이미지 좌표)"""
        return np.array(
            [[p.x(), p.y()] for p in self._points], dtype=np.float32
        )


class PerspectiveDialog(QDialog):
    """원근 보정 다이얼로그"""

    def __init__(self, cv_img: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("원근 보정")
        self.setMinimumSize(600, 500)
        self._cv_img = cv_img
        self._result = None

        layout = QVBoxLayout(self)

        info = QLabel("4개 꼭짓점을 드래그하여 보정할 영역을 지정하세요")
        info.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        self._canvas = PerspectiveCanvas(cv_img, self)
        layout.addWidget(self._canvas, 1)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("적용")
        btn_ok.setFixedHeight(36)
        btn_ok.setStyleSheet(
            f"background-color: {get_color('accent')}; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        btn_ok.clicked.connect(self._on_accept)

        btn_cancel = QPushButton("취소")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            f"background-color: {get_color('bg_button_hover')}; color: {get_color('text_secondary')}; border-radius: 4px; font-size: 13px;"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_ok, 2)
        btn_row.addWidget(btn_cancel, 1)
        layout.addLayout(btn_row)

    def _on_accept(self):
        """원근 변환 적용"""
        src_pts = self._canvas.get_src_points()
        h, w = self._cv_img.shape[:2]

        # 목적지: 사각형 (src의 바운딩 박스 기준)
        x_min, y_min = src_pts.min(axis=0)
        x_max, y_max = src_pts.max(axis=0)
        out_w = int(x_max - x_min)
        out_h = int(y_max - y_min)
        if out_w < 10 or out_h < 10:
            return

        dst_pts = np.array([
            [0, 0],
            [out_w - 1, 0],
            [out_w - 1, out_h - 1],
            [0, out_h - 1]
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        self._result = cv2.warpPerspective(self._cv_img, M, (out_w, out_h))
        self.accept()

    def get_result(self) -> np.ndarray:
        """변환된 이미지 반환"""
        return self._result

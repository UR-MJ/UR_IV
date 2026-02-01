# tabs/editor/crop_dialog.py
"""크롭 대화상자 - 리사이즈 핸들이 있는 선택 영역"""
import numpy as np
import cv2
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget
)
from PyQt6.QtCore import Qt, QRect, QPoint, QRectF
from PyQt6.QtGui import QPainter, QImage, QPen, QColor, QBrush, QPixmap, QCursor


class CropWidget(QWidget):
    """이미지 위에 리사이즈 가능한 선택 사각형을 표시하는 위젯"""

    HANDLE_SIZE = 8

    def __init__(self, cv_image: np.ndarray, parent=None):
        super().__init__(parent)
        self._cv_image = cv_image
        self._qimage = self._cv_to_qimage(cv_image)
        self.setMinimumSize(400, 300)

        # 이미지 표시 영역 (paintEvent에서 계산)
        self._display_rect = QRect()
        self._scale = 1.0

        # 선택 영역 (이미지 좌표)
        img_h, img_w = cv_image.shape[:2]
        margin_x = img_w // 4
        margin_y = img_h // 4
        self._sel = QRect(margin_x, margin_y, img_w - 2 * margin_x, img_h - 2 * margin_y)

        # 드래그 상태
        self._drag_type: str | None = None  # None, 'move', 'handle-N'
        self._drag_start = QPoint()
        self._sel_start = QRect()

        self.setMouseTracking(True)

    @staticmethod
    def _cv_to_qimage(cv_img: np.ndarray) -> QImage:
        """OpenCV BGR → QImage"""
        if cv_img.ndim == 2:
            h, w = cv_img.shape
            return QImage(cv_img.data, w, h, w, QImage.Format.Format_Grayscale8)
        h, w, ch = cv_img.shape
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        return QImage(rgb.data.tobytes(), w, h, w * ch, QImage.Format.Format_RGB888)

    def get_crop_rect(self) -> tuple[int, int, int, int]:
        """이미지 좌표 기준 (x, y, w, h)"""
        r = self._sel.normalized()
        img_h, img_w = self._cv_image.shape[:2]
        x = max(0, min(r.x(), img_w - 1))
        y = max(0, min(r.y(), img_h - 1))
        w = min(r.width(), img_w - x)
        h = min(r.height(), img_h - y)
        return x, y, max(1, w), max(1, h)

    # ── 좌표 변환 ──

    def _calc_display(self):
        """위젯 크기에 맞게 이미지 표시 영역 계산"""
        iw, ih = self._qimage.width(), self._qimage.height()
        ww, wh = self.width(), self.height()
        if iw == 0 or ih == 0:
            return
        scale_w = ww / iw
        scale_h = wh / ih
        self._scale = min(scale_w, scale_h)
        dw = int(iw * self._scale)
        dh = int(ih * self._scale)
        dx = (ww - dw) // 2
        dy = (wh - dh) // 2
        self._display_rect = QRect(dx, dy, dw, dh)

    def _img_to_screen(self, pt: QPoint) -> QPoint:
        """이미지 좌표 → 스크린 좌표"""
        return QPoint(
            int(pt.x() * self._scale + self._display_rect.x()),
            int(pt.y() * self._scale + self._display_rect.y()),
        )

    def _screen_to_img(self, pt: QPoint) -> QPoint:
        """스크린 좌표 → 이미지 좌표"""
        if self._scale == 0:
            return QPoint(0, 0)
        return QPoint(
            int((pt.x() - self._display_rect.x()) / self._scale),
            int((pt.y() - self._display_rect.y()) / self._scale),
        )

    def _sel_screen_rect(self) -> QRect:
        """선택 영역의 스크린 좌표 QRect"""
        tl = self._img_to_screen(self._sel.topLeft())
        br = self._img_to_screen(self._sel.bottomRight())
        return QRect(tl, br)

    # ── 핸들 ──

    def _handle_rects(self) -> list[QRect]:
        """8개 핸들의 스크린 좌표 QRect 목록"""
        r = self._sel_screen_rect()
        hs = self.HANDLE_SIZE
        cx, cy = r.center().x(), r.center().y()
        points = [
            r.topLeft(), QPoint(cx, r.top()), r.topRight(),
            QPoint(r.left(), cy), QPoint(r.right(), cy),
            r.bottomLeft(), QPoint(cx, r.bottom()), r.bottomRight(),
        ]
        return [QRect(p.x() - hs, p.y() - hs, hs * 2, hs * 2) for p in points]

    _HANDLE_CURSORS = [
        Qt.CursorShape.SizeFDiagCursor,   # TL
        Qt.CursorShape.SizeVerCursor,      # TC
        Qt.CursorShape.SizeBDiagCursor,    # TR
        Qt.CursorShape.SizeHorCursor,      # ML
        Qt.CursorShape.SizeHorCursor,      # MR
        Qt.CursorShape.SizeBDiagCursor,    # BL
        Qt.CursorShape.SizeVerCursor,      # BC
        Qt.CursorShape.SizeFDiagCursor,    # BR
    ]

    # ── 페인트 ──

    def paintEvent(self, event):
        self._calc_display()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 배경
        painter.fillRect(self.rect(), QBrush(QColor("#1A1A1A")))

        # 이미지
        dr = self._display_rect
        painter.drawImage(dr, self._qimage)

        # 선택 밖 어둡게
        sr = self._sel_screen_rect()
        overlay = QColor(0, 0, 0, 150)
        # 위
        painter.fillRect(QRect(dr.left(), dr.top(), dr.width(), sr.top() - dr.top()), overlay)
        # 아래
        painter.fillRect(QRect(dr.left(), sr.bottom(), dr.width(), dr.bottom() - sr.bottom()), overlay)
        # 좌
        painter.fillRect(QRect(dr.left(), sr.top(), sr.left() - dr.left(), sr.height()), overlay)
        # 우
        painter.fillRect(QRect(sr.right(), sr.top(), dr.right() - sr.right(), sr.height()), overlay)

        # 선택 테두리
        pen = QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(sr)

        # 핸들
        painter.setPen(QPen(QColor("#5865F2"), 1))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for hr in self._handle_rects():
            painter.drawRect(hr)

        # 크기 정보
        x, y, w, h = self.get_crop_rect()
        info = f"{w} × {h}"
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(sr.center().x() - 30, sr.top() - 8, info)

        painter.end()

    # ── 마우스 이벤트 ──

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.pos()

        # 핸들 히트 테스트
        for i, hr in enumerate(self._handle_rects()):
            if hr.contains(pos):
                self._drag_type = f'handle-{i}'
                self._drag_start = pos
                self._sel_start = QRect(self._sel)
                return

        # 선택 영역 내부 → 이동
        if self._sel_screen_rect().contains(pos):
            self._drag_type = 'move'
            self._drag_start = pos
            self._sel_start = QRect(self._sel)
            return

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if self._drag_type is None:
            # 커서 변경
            for i, hr in enumerate(self._handle_rects()):
                if hr.contains(pos):
                    self.setCursor(QCursor(self._HANDLE_CURSORS[i]))
                    return
            if self._sel_screen_rect().contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            return

        delta_screen = pos - self._drag_start
        dx_img = int(delta_screen.x() / self._scale) if self._scale else 0
        dy_img = int(delta_screen.y() / self._scale) if self._scale else 0
        img_h, img_w = self._cv_image.shape[:2]

        if self._drag_type == 'move':
            new_x = self._sel_start.x() + dx_img
            new_y = self._sel_start.y() + dy_img
            new_x = max(0, min(new_x, img_w - self._sel_start.width()))
            new_y = max(0, min(new_y, img_h - self._sel_start.height()))
            self._sel = QRect(new_x, new_y, self._sel_start.width(), self._sel_start.height())

        elif self._drag_type.startswith('handle-'):
            idx = int(self._drag_type.split('-')[1])
            s = self._sel_start
            l, t, r, b = s.left(), s.top(), s.right(), s.bottom()

            # 핸들별 처리: TL=0, TC=1, TR=2, ML=3, MR=4, BL=5, BC=6, BR=7
            if idx in (0, 3, 5):  # left edge
                l = max(0, s.left() + dx_img)
            if idx in (2, 4, 7):  # right edge
                r = min(img_w - 1, s.right() + dx_img)
            if idx in (0, 1, 2):  # top edge
                t = max(0, s.top() + dy_img)
            if idx in (5, 6, 7):  # bottom edge
                b = min(img_h - 1, s.bottom() + dy_img)

            # 최소 크기 보장
            if r - l < 10:
                if idx in (0, 3, 5):
                    l = r - 10
                else:
                    r = l + 10
            if b - t < 10:
                if idx in (0, 1, 2):
                    t = b - 10
                else:
                    b = t + 10

            self._sel = QRect(QPoint(l, t), QPoint(r, b))

        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_type = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()


class CropDialog(QDialog):
    """크롭 대화상자"""

    def __init__(self, cv_image: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("이미지 크롭")
        self.setMinimumSize(600, 500)
        self.resize(900, 700)
        self.setStyleSheet("background-color: #1E1E1E; color: #EEE;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        info = QLabel("모서리와 변의 핸들을 드래그하여 크롭 영역을 조절하세요")
        info.setStyleSheet("color: #AAA; font-size: 12px;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        self.crop_widget = CropWidget(cv_image)
        layout.addWidget(self.crop_widget, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_confirm = QPushButton("✅ 크롭 적용")
        btn_confirm.setFixedHeight(38)
        btn_confirm.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 6px; "
            "font-size: 14px; font-weight: bold; padding: 0 20px;"
        )
        btn_confirm.clicked.connect(self.accept)
        btn_layout.addWidget(btn_confirm)

        btn_cancel = QPushButton("❌ 취소")
        btn_cancel.setFixedHeight(38)
        btn_cancel.setStyleSheet(
            "background-color: #333; color: #AAA; border-radius: 6px; "
            "font-size: 14px; padding: 0 20px;"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def get_crop_rect(self) -> tuple[int, int, int, int]:
        return self.crop_widget.get_crop_rect()

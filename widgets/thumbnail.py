# widgets/thumbnail.py
import os
from PyQt6.QtWidgets import QWidget, QMenu, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRectF
from PyQt6.QtGui import (
    QPixmap, QAction, QPainter, QPainterPath, QBrush, QColor, QPen, QFont
)
from core.image_utils import get_thumb_path


class ThumbnailItem(QWidget):
    clicked = pyqtSignal(str)  # filepath 전달
    action_triggered = pyqtSignal(str, str)  # action, filepath 전달

    def __init__(self, filepath, size=150, hover_enabled=True, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.thumb_size = size
        self.is_selected = False
        self._is_hovered = False
        self._hover_enabled = hover_enabled
        self.pixmap = None
        self._scaled_cache = None  # 스케일링된 이미지 캐시
        self._cache_size = None    # 캐시된 크기

        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if hover_enabled:
            self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # 썸네일 로드
        thumb_path = get_thumb_path(filepath)

        if os.path.exists(thumb_path):
            self.pixmap = QPixmap(thumb_path)
        elif os.path.exists(filepath):
            self.pixmap = QPixmap(filepath)

        # 크게 보기 버튼 (hover 활성화된 경우만)
        self._view_btn = None
        if hover_enabled:
            self._view_btn = QPushButton("크게 보기", self)
            btn_w, btn_h = 80, 28
            self._view_btn.setFixedSize(btn_w, btn_h)
            self._view_btn.move((size - btn_w) // 2, (size - btn_h) // 2)
            self._view_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(88, 101, 242, 200);
                    color: white; border: none; border-radius: 6px;
                    font-size: 12px; font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(88, 101, 242, 240);
                }
            """)
            self._view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._view_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._view_btn.clicked.connect(
                lambda: self.action_triggered.emit("view", self.filepath)
            )
            self._view_btn.hide()

        self.set_selected(False)

    def paintEvent(self, event):
        """커스텀 페인트 - 둥근 모서리 + 꽉 채우기 + 호버 오버레이"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 둥근 사각형 경로
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.setClipPath(path)

        # 배경
        if self.is_selected:
            painter.fillRect(self.rect(), QBrush(QColor("#3a3a3a")))
        else:
            painter.fillRect(self.rect(), QBrush(QColor("#232323")))

        # 이미지 그리기 (꽉 채우기 - 캐싱된 스케일 결과 사용)
        if self.pixmap and not self.pixmap.isNull():
            cur_size = (self.width(), self.height())
            if self._scaled_cache is None or self._cache_size != cur_size:
                scaled = self.pixmap.scaled(
                    self.width(), self.height(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                x = (scaled.width() - self.width()) // 2
                y = (scaled.height() - self.height()) // 2
                self._scaled_cache = scaled.copy(x, y, self.width(), self.height())
                self._cache_size = cur_size

            painter.drawPixmap(0, 0, self._scaled_cache)
        else:
            painter.setPen(QColor("#888888"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Image")

        # 호버 오버레이
        if self._is_hovered:
            overlay = QColor(0, 0, 0, 120)
            painter.fillRect(self.rect(), QBrush(overlay))

        # 테두리
        painter.setClipping(False)
        if self.is_selected:
            pen = QPen(QColor("#5865F2"), 3)
            painter.setPen(pen)
            painter.drawRoundedRect(2, 2, self.width()-4, self.height()-4, 10, 10)
        elif self._is_hovered:
            pen = QPen(QColor("#5865F2"), 2)
            painter.setPen(pen)
            painter.drawRoundedRect(1, 1, self.width()-2, self.height()-2, 11, 11)
        else:
            pen = QPen(QColor("#444444"), 1)
            painter.setPen(pen)
            painter.drawRoundedRect(0, 0, self.width()-1, self.height()-1, 12, 12)

    def sizeHint(self):
        return QSize(self.thumb_size, self.thumb_size)

    def set_selected(self, selected):
        self.is_selected = selected
        self.update()

    def enterEvent(self, event):
        if not self._hover_enabled:
            super().enterEvent(event)
            return
        self._is_hovered = True
        if self._view_btn:
            self._view_btn.show()
            self._view_btn.raise_()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._hover_enabled:
            super().leaveEvent(event)
            return
        self._is_hovered = False
        if self._view_btn:
            self._view_btn.hide()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.filepath)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2C2C2C; border: 1px solid #555; color: white;
            }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #5865F2; }
        """)

        action_load = QAction("📝 설정 불러오기", self)
        action_view = QAction("🖼️ 뷰어에서 보기", self)
        action_delete = QAction("🗑️ 이미지 삭제", self)

        action_load.triggered.connect(
            lambda: self.action_triggered.emit("load", self.filepath)
        )
        action_view.triggered.connect(
            lambda: self.action_triggered.emit("view", self.filepath)
        )
        action_delete.triggered.connect(
            lambda: self.action_triggered.emit("delete", self.filepath)
        )

        menu.addAction(action_load)
        menu.addAction(action_view)
        menu.addSeparator()
        menu.addAction(action_delete)

        menu.exec(event.globalPos())

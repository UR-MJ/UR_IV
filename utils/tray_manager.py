# utils/tray_manager.py
"""시스템 트레이 아이콘 및 알림 관리"""
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QObject, pyqtSignal
from utils.theme_manager import get_color


def _create_default_icon() -> QIcon:
    """기본 앱 아이콘 생성 (간단한 'A' 아이콘)"""
    pix = QPixmap(64, 64)
    pix.fill(QColor(88, 101, 242))  # Discord-like blue
    painter = QPainter(pix)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Arial", 36, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), 0x0084, "A")  # AlignCenter
    painter.end()
    return QIcon(pix)


class TrayManager(QObject):
    """시스템 트레이 아이콘 관리자"""
    show_window_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._icon = _create_default_icon()
        self._tray = QSystemTrayIcon(self._icon, self)
        self._tray.setToolTip("AI Studio Pro")

        # 컨텍스트 메뉴
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; }}"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background-color: #5865F2; }"
        )
        act_open = menu.addAction("열기")
        act_open.triggered.connect(self.show_window_requested.emit)
        menu.addSeparator()
        act_quit = menu.addAction("종료")
        act_quit.triggered.connect(self.quit_requested.emit)
        self._tray.setContextMenu(menu)

        # 더블클릭 → 창 표시
        self._tray.activated.connect(self._on_activated)

    def show(self):
        """트레이 아이콘 표시"""
        self._tray.show()

    def hide(self):
        """트레이 아이콘 숨기기"""
        self._tray.hide()

    def notify(self, title: str, message: str, duration_ms: int = 3000):
        """트레이 알림 표시"""
        if self._tray.isVisible():
            self._tray.showMessage(
                title, message,
                QSystemTrayIcon.MessageIcon.Information,
                duration_ms
            )

    def _on_activated(self, reason):
        """트레이 아이콘 활성화 (더블클릭)"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()

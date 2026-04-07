# utils/tray_manager.py
"""시스템 트레이 아이콘 및 알림 관리"""
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QObject, pyqtSignal
from utils.theme_manager import get_color


def _get_app_icon() -> QIcon:
    """앱 전용 아이콘 로드 (없으면 기본 생성)"""
    import os
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icons', 'app_icon.svg')
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    
    # 폴백: 아이콘 파일이 없을 경우 기존처럼 'A' 아이콘 생성
    pix = QPixmap(64, 64)
    pix.fill(QColor(250, 204, 21))  # Gemini Yellow
    painter = QPainter(pix)
    painter.setPen(QColor(0, 0, 0))
    font = QFont("Arial", 36, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), 0x0084, "A")
    painter.end()
    return QIcon(pix)


class TrayManager(QObject):
    """시스템 트레이 아이콘 관리자"""
    show_window_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._icon = _get_app_icon()
        self._tray = QSystemTrayIcon(self._icon, self)
        self._tray.setToolTip("AI Studio Pro")

        # 컨텍스트 메뉴
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; }}"
            "QMenu::item { padding: 6px 20px; }"
            f"QMenu::item:selected {{ background-color: {get_color('accent')}; }}"
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

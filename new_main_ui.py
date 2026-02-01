# main.py
"""
AI Studio - Pro
메인 실행 파일
"""
import sys
import os
from config import *
from ui.generator_main import GeneratorMainUI
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import Qt, QEvent, QObject
from PyQt6.QtGui import QPalette, QColor, QCursor


class ButtonCursorFilter(QObject):
    """QPushButton에 마우스 올리면 포인터 커서로 변경"""
    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and obj.isEnabled():
            if event.type() == QEvent.Type.Enter:
                obj.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            elif event.type() == QEvent.Type.Leave:
                obj.unsetCursor()
        return False


def main():
    """메인 실행 함수"""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("AI Studio Pro")
    app.setOrganizationName("AI Studio")
    
    # 다크 모드 팔레트
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Base, QColor(37, 37, 37))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(44, 44, 44))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Text, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Button, QColor(44, 44, 44))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, QColor(88, 101, 242))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(88, 101, 242))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    # 버튼 호버 시 포인터 커서 표시
    cursor_filter = ButtonCursorFilter(app)
    app.installEventFilter(cursor_filter)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    window = GeneratorMainUI()
    window.showMaximized()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
# widgets/font_combo.py
"""시스템 폰트 선택 콤보박스 (QFontComboBox 기반)"""
from PyQt6.QtWidgets import QFontComboBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class FontPreviewComboBox(QFontComboBox):
    """시스템 글꼴을 미리보기와 함께 표시하는 콤보박스"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(20)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setEditable(True)
        self.setInsertPolicy(QFontComboBox.InsertPolicy.NoInsert)
        self.setMinimumWidth(200)

        # 다크 테마 스타일 — 드롭다운 화살표 표시
        self.setStyleSheet("""
            QFontComboBox {
                background-color: #2A2A2A;
                color: #DDD;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 28px 4px 8px;
                min-height: 24px;
            }
            QFontComboBox:hover {
                border-color: #5865F2;
            }
            QFontComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #444;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                background-color: #333;
            }
            QFontComboBox::drop-down:hover {
                background-color: #444;
            }
            QFontComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #AAA;
                width: 0;
                height: 0;
            }
            QFontComboBox QAbstractItemView {
                background-color: #2A2A2A;
                color: #DDD;
                border: 1px solid #5865F2;
                selection-background-color: #5865F2;
                outline: none;
            }
            QFontComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 4px;
            }
            QFontComboBox QAbstractItemView::item:hover {
                background-color: #373737;
            }
        """)

    def set_current_font(self, family: str):
        """현재 폰트를 설정"""
        font = QFont(family)
        self.setCurrentFont(font)

    def wheelEvent(self, event):
        event.ignore()

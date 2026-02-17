# widgets/font_combo.py
"""시스템 폰트 선택 콤보박스 (QFontComboBox 기반)"""
from PyQt6.QtWidgets import QFontComboBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class FontPreviewComboBox(QFontComboBox):
    """시스템 글꼴을 미리보기와 함께 표시하는 콤보박스"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(15)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setEditable(True)
        self.setInsertPolicy(QFontComboBox.InsertPolicy.NoInsert)

        # 다크 테마 스타일
        self.setStyleSheet("""
            QFontComboBox {
                background-color: #2A2A2A;
                color: #DDD;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QFontComboBox:hover {
                border-color: #5865F2;
            }
            QFontComboBox::drop-down {
                border: none;
                width: 24px;
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

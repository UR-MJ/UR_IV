# widgets/font_combo.py
"""시스템 폰트 선택 콤보박스 (QComboBox + QFontDatabase 기반)"""
from PyQt6.QtWidgets import QComboBox, QCompleter
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase


class FontPreviewComboBox(QComboBox):
    """시스템 글꼴 이름만 깔끔하게 표시하는 콤보박스"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 시스템 글꼴 목록 로드
        families = sorted(QFontDatabase.families())
        self.addItems(families)

        self.setMaxVisibleItems(20)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumWidth(200)

        # 자동완성 (대소문자 무시, 부분 일치)
        completer = QCompleter(families, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(15)
        self.setCompleter(completer)

        # 다크 테마 스타일
        self.setStyleSheet("""
            QComboBox {
                background-color: #2A2A2A;
                color: #DDD;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 28px 4px 8px;
                min-height: 24px;
            }
            QComboBox:hover {
                border-color: #5865F2;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #444;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                background-color: #333;
            }
            QComboBox::drop-down:hover {
                background-color: #444;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #AAA;
                width: 0;
                height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: #2A2A2A;
                color: #DDD;
                border: 1px solid #5865F2;
                selection-background-color: #5865F2;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                min-height: 24px;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #373737;
            }
        """)

    def set_current_font(self, family: str):
        """현재 폰트를 설정"""
        idx = self.findText(family, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentText(family)

    def mousePressEvent(self, event):
        """클릭 시 바로 드롭다운 표시"""
        self.showPopup()
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        event.ignore()

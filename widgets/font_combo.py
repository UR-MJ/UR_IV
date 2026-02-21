# widgets/font_combo.py
"""시스템 폰트 선택 콤보박스 (QComboBox + QFontDatabase 기반)"""
from PyQt6.QtWidgets import QComboBox, QCompleter, QStyledItemDelegate, QStyle
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QFontDatabase, QColor
from utils.theme_manager import get_color


class FontItemDelegate(QStyledItemDelegate):
    """각 글꼴 항목을 해당 글꼴로 렌더링하는 델리게이트"""

    def paint(self, painter, option, index):
        font_family = index.data(Qt.ItemDataRole.DisplayRole)
        if not font_family:
            super().paint(painter, option, index)
            return

        painter.save()
        # 선택/호버 배경
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#5865F2"))
            painter.setPen(QColor(get_color('text_primary')))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(get_color('bg_button_hover')))
            painter.setPen(QColor(get_color('text_primary')))
        else:
            painter.setPen(QColor(get_color('text_primary')))

        painter.setFont(QFont(font_family, 11))
        painter.drawText(
            option.rect.adjusted(8, 0, -4, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            font_family,
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 28)


class FontPreviewComboBox(QComboBox):
    """시스템 글꼴 이름을 해당 글꼴로 미리보기하는 콤보박스"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 시스템 글꼴 목록 로드
        families = sorted(QFontDatabase.families())
        self.addItems(families)

        self.setMaxVisibleItems(20)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumWidth(200)

        # 드롭다운 항목을 해당 글꼴로 표시
        self.setItemDelegate(FontItemDelegate(self))

        # 자동완성 (대소문자 무시, 부분 일치)
        completer = QCompleter(families, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(15)
        self.setCompleter(completer)

        # 다크 테마 스타일
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {get_color('bg_tertiary')};
                color: {get_color('text_primary')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                padding: 4px 28px 4px 8px;
                min-height: 24px;
            }}
            QComboBox:hover {{
                border-color: #5865F2;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {get_color('border')};
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                background-color: {get_color('bg_button_hover')};
            }}
            QComboBox::drop-down:hover {{
                background-color: {get_color('border')};
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {get_color('text_secondary')};
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background-color: {get_color('bg_tertiary')};
                color: {get_color('text_primary')};
                border: 1px solid #5865F2;
                selection-background-color: #5865F2;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 24px;
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {get_color('bg_button_hover')};
            }}
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

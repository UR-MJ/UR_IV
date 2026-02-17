# widgets/font_combo.py
"""시스템 폰트 미리보기가 포함된 콤보박스"""
from PyQt6.QtWidgets import QComboBox, QStyledItemDelegate, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QModelIndex, QSize
from PyQt6.QtGui import QFont, QFontDatabase


class _FontPreviewDelegate(QStyledItemDelegate):
    """각 항목을 해당 폰트로 렌더링하는 델리게이트"""

    _PREVIEW_TEXT = " - 가나다 ABC 123"

    def paint(self, painter, option, index):
        family = index.data(Qt.ItemDataRole.DisplayRole)
        if not family:
            super().paint(painter, option, index)
            return

        painter.save()

        # 배경 (선택/호버)
        style = option.widget.style() if option.widget else None
        if style:
            style.drawPrimitive(
                style.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget
            )

        # 폰트 이름 (기본 폰트)
        name_font = QFont(painter.font())
        name_font.setPointSize(10)
        painter.setFont(name_font)
        painter.setPen(option.palette.text().color())

        text_rect = option.rect.adjusted(6, 0, 0, 0)
        top_rect = text_rect.adjusted(0, 2, 0, -text_rect.height() // 2)
        painter.drawText(top_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, family)

        # 미리보기 (해당 폰트로)
        preview_font = QFont(family)
        preview_font.setPointSize(10)
        painter.setFont(preview_font)
        painter.setPen(option.palette.text().color())

        bot_rect = text_rect.adjusted(0, text_rect.height() // 2, 0, -2)
        painter.drawText(
            bot_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._PREVIEW_TEXT
        )

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(0, 42)


class FontPreviewComboBox(QComboBox):
    """시스템 폰트를 미리보기와 함께 표시하는 콤보박스 (검색 지원)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMaxVisibleItems(12)

        self._delegate = _FontPreviewDelegate(self)
        self.setItemDelegate(self._delegate)

        # 시스템 폰트 로드
        self._all_families = sorted(QFontDatabase.families())
        self.addItems(self._all_families)

        # 검색 필터링
        self.lineEdit().textEdited.connect(self._filter_fonts)

    def _filter_fonts(self, text: str):
        """입력 텍스트로 폰트 목록 필터링"""
        text_lower = text.lower()
        self.blockSignals(True)
        self.clear()
        if not text_lower:
            self.addItems(self._all_families)
        else:
            filtered = [f for f in self._all_families if text_lower in f.lower()]
            self.addItems(filtered)
        self.blockSignals(False)
        self.showPopup()

    def set_current_font(self, family: str):
        """현재 폰트를 설정"""
        idx = self.findText(family)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentText(family)

    def wheelEvent(self, event):
        event.ignore()

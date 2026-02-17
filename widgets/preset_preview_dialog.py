# widgets/preset_preview_dialog.py
"""프리셋 미리보기 및 편집 다이얼로그"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QTextEdit,
    QCheckBox, QScrollArea, QWidget, QMessageBox, QSplitter,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont


_DARK_STYLE = """
QDialog {
    background-color: #1E1E1E;
    color: #DDD;
}
QLabel {
    color: #CCC;
}
QListWidget {
    background-color: #252525;
    color: #DDD;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 4px;
    font-size: 13px;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #5865F2;
    color: white;
}
QListWidget::item:hover {
    background-color: #333;
}
QLineEdit {
    background-color: #2A2A2A;
    color: #DDD;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 13px;
}
QLineEdit:focus {
    border: 1px solid #5865F2;
}
QTextEdit {
    background-color: #2A2A2A;
    color: #DDD;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px;
    font-size: 12px;
}
QTextEdit:focus {
    border: 1px solid #5865F2;
}
QCheckBox {
    color: #BBB;
    spacing: 6px;
    font-size: 12px;
    font-weight: bold;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #555;
    background-color: #2A2A2A;
}
QCheckBox::indicator:checked {
    background-color: #5865F2;
    border: 1px solid #5865F2;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
"""

_FIELD_DEFS = [
    ("character",    "Character",     "line"),
    ("copyright",    "Copyright",     "line"),
    ("artist",       "Artist",        "line"),
    ("main_prompt",  "Main Prompt",   "text"),
    ("prefix",       "Prefix",        "text"),
    ("suffix",       "Suffix",        "text"),
    ("negative",     "Negative",      "text"),
]


class PresetPreviewDialog(QDialog):
    """프리셋 미리보기 + 편집 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("프리셋 불러오기")
        self.setMinimumSize(900, 620)
        self.resize(960, 680)
        self.setStyleSheet(_DARK_STYLE)

        self._selected_name: str | None = None
        self._result_data: dict | None = None
        self._fields: dict[str, tuple[QCheckBox, QLineEdit | QTextEdit]] = {}

        self._init_ui()
        self._load_list()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 상단 제목
        title = QLabel("프리셋 불러오기")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #EEE; padding: 2px 0;")
        root.addWidget(title)

        # ── 본체: 좌측 목록 | 우측 편집 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet("QSplitter::handle { background-color: #333; }")

        # 좌측 — 프리셋 목록
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        list_label = QLabel("프리셋 목록")
        list_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #999;")
        left_layout.addWidget(list_label)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_preset_selected)
        left_layout.addWidget(self._list)

        splitter.addWidget(left)

        # 우측 — 필드 편집
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        detail_label = QLabel("프리셋 내용")
        detail_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #999; padding-bottom: 4px;")
        right_layout.addWidget(detail_label)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self._form = QVBoxLayout(scroll_widget)
        self._form.setContentsMargins(4, 4, 4, 4)
        self._form.setSpacing(6)

        for key, label, ftype in _FIELD_DEFS:
            row = QVBoxLayout()
            row.setSpacing(2)

            cb = QCheckBox(label)
            cb.setChecked(True)
            row.addWidget(cb)

            if ftype == "line":
                widget = QLineEdit()
                widget.setPlaceholderText(f"{label} 값 입력...")
                widget.setFixedHeight(32)
            else:
                widget = QTextEdit()
                widget.setPlaceholderText(f"{label} 값 입력...")
                widget.setMinimumHeight(60)
                widget.setMaximumHeight(120)

            row.addWidget(widget)
            self._form.addLayout(row)
            self._fields[key] = (cb, widget)

        self._form.addStretch(1)
        scroll.setWidget(scroll_widget)
        right_layout.addWidget(scroll)

        splitter.addWidget(right)
        splitter.setSizes([220, 700])

        root.addWidget(splitter, 1)

        # ── 구분선 ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #333;")
        root.addWidget(line)

        # ── 하단 버튼 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_delete = QPushButton("삭제")
        self._btn_delete.setFixedSize(100, 38)
        self._btn_delete.setStyleSheet(
            "QPushButton { background-color: #E74C3C; color: white; border-radius: 6px; "
            "font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #C0392B; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_delete.setEnabled(False)

        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch(1)

        self._btn_apply = QPushButton("적용")
        self._btn_apply.setFixedSize(120, 38)
        self._btn_apply.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; border-radius: 6px; "
            "font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background-color: #6975F3; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self._btn_apply.clicked.connect(self._on_apply)
        self._btn_apply.setEnabled(False)

        btn_close = QPushButton("닫기")
        btn_close.setFixedSize(100, 38)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #444; color: #DDD; border-radius: 6px; "
            "font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #555; }"
        )
        btn_close.clicked.connect(self.reject)

        btn_row.addWidget(self._btn_apply)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    # ── 데이터 ──

    def _load_list(self):
        """프리셋 목록 로드"""
        from utils.prompt_preset import list_presets
        self._list.clear()
        names = list_presets()
        for name in names:
            item = QListWidgetItem(name)
            self._list.addItem(item)

        if not names:
            self._clear_fields()

    def _on_preset_selected(self, current: QListWidgetItem, _prev):
        """프리셋 선택 시 내용 로드"""
        if not current:
            self._selected_name = None
            self._clear_fields()
            self._btn_apply.setEnabled(False)
            self._btn_delete.setEnabled(False)
            return

        from utils.prompt_preset import get_preset
        name = current.text()
        self._selected_name = name
        data = get_preset(name)
        if not data:
            self._clear_fields()
            return

        for key, (cb, widget) in self._fields.items():
            val = data.get(key, "")
            cb.setChecked(bool(val))
            if isinstance(widget, QLineEdit):
                widget.setText(val)
            else:
                widget.setPlainText(val)

        self._btn_apply.setEnabled(True)
        self._btn_delete.setEnabled(True)

    def _clear_fields(self):
        """모든 필드 초기화"""
        for _key, (cb, widget) in self._fields.items():
            cb.setChecked(True)
            if isinstance(widget, QLineEdit):
                widget.clear()
            else:
                widget.clear()

    # ── 버튼 핸들러 ──

    def _on_apply(self):
        """체크된 필드만 결과로 반환"""
        result = {}
        for key, (cb, widget) in self._fields.items():
            if cb.isChecked():
                if isinstance(widget, QLineEdit):
                    result[key] = widget.text()
                else:
                    result[key] = widget.toPlainText()
        self._result_data = result
        self.accept()

    def _on_delete(self):
        """선택된 프리셋 삭제"""
        if not self._selected_name:
            return

        reply = QMessageBox.question(
            self, "프리셋 삭제",
            f"'{self._selected_name}' 프리셋을 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from utils.prompt_preset import delete_preset
        delete_preset(self._selected_name)
        self._selected_name = None
        self._load_list()

    def get_result(self) -> dict | None:
        """적용된 데이터 반환 (체크된 필드만 포함)"""
        return self._result_data

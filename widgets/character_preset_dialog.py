# widgets/character_preset_dialog.py
"""캐릭터 특징 프리셋 다이얼로그 — 검색 & 선택 & 삽입"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QWidget,
    QTextEdit, QSplitter, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer
from widgets.common_widgets import FlowLayout


_STYLE = """
QDialog { background-color: #1E1E1E; color: #DDD; }
QLabel { color: #CCC; }
QLineEdit {
    background-color: #2A2A2A; color: #DDD;
    border: 1px solid #444; border-radius: 6px;
    padding: 8px 12px; font-size: 13px;
}
QLineEdit:focus { border: 1px solid #5865F2; }
QTextEdit {
    background-color: #2A2A2A; color: #DDD;
    border: 1px solid #444; border-radius: 6px;
    padding: 6px 10px; font-size: 12px;
}
QTextEdit:focus { border: 1px solid #5865F2; }
QListWidget {
    background-color: #252525; color: #DDD;
    border: 1px solid #333; border-radius: 6px;
    font-size: 12px; padding: 4px;
    outline: 0;
}
QListWidget::item {
    padding: 6px 8px; border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #5865F2; color: white;
}
QListWidget::item:hover {
    background-color: #333;
}
QScrollArea { border: none; }
"""

_TAG_CHECKED = (
    "QPushButton { background-color: #5865F2; color: white; "
    "border: none; border-radius: 11px; padding: 4px 12px; "
    "font-size: 11px; font-weight: bold; }"
    "QPushButton:hover { background-color: #6975F3; }"
)
_TAG_UNCHECKED = (
    "QPushButton { background-color: #333; color: #777; "
    "border: none; border-radius: 11px; padding: 4px 12px; "
    "font-size: 11px; text-decoration: line-through; }"
    "QPushButton:hover { background-color: #444; }"
)
_TAG_EXISTS = (
    "QPushButton { background-color: #2C2C2C; color: #555; "
    "border: 1px solid #3A3A3A; border-radius: 11px; padding: 4px 12px; "
    "font-size: 11px; }"
)


def _unescape(text: str) -> str:
    """이스케이프 문자 제거: \\( → (, \\) → )"""
    return text.replace(r"\(", "(").replace(r"\)", ")")


class CharacterPresetDialog(QDialog):
    """캐릭터 검색 + 특징 프리셋 삽입 다이얼로그"""

    def __init__(self, existing_tags: set[str] | None = None,
                 current_character: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("캐릭터 특징 프리셋")
        self.setMinimumSize(850, 600)
        self.resize(950, 650)
        self.setStyleSheet(_STYLE)

        self._existing_tags = existing_tags or set()
        self._lookup = None
        self._tag_buttons: list[tuple[QPushButton, str, bool]] = []
        self._current_char_key: str = ""
        self._result: dict | None = None
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._do_search)

        self._init_ui()

        # 현재 캐릭터가 있으면 이스케이프 제거 후 검색
        if current_character.strip():
            first_char = _unescape(current_character.split(",")[0].strip())
            self._search_input.setText(first_char)

    def _get_lookup(self):
        if self._lookup is None:
            from utils.character_features import get_character_features
            self._lookup = get_character_features()
        return self._lookup

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 타이틀
        title = QLabel("캐릭터 특징 프리셋")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #EEE;")
        root.addWidget(title)

        desc = QLabel(
            "캐릭터를 검색하고 특징 태그를 선택하여 프롬프트에 삽입합니다. "
            "추가 프롬프트도 함께 입력할 수 있습니다."
        )
        desc.setStyleSheet("color: #888; font-size: 12px;")
        root.addWidget(desc)

        # 검색 입력
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "캐릭터 이름 검색 (예: hatsune miku, remilia scarlet)"
        )
        self._search_input.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search_input)

        # 메인 영역: 왼쪽 목록 + 오른쪽 특징
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 왼쪽: 검색 결과 목록
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._result_label = QLabel("검색 결과")
        self._result_label.setStyleSheet(
            "color: #AAA; font-weight: bold; font-size: 12px;"
        )
        left_layout.addWidget(self._result_label)

        self._result_list = QListWidget()
        self._result_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._result_list.currentItemChanged.connect(self._on_item_selected)
        left_layout.addWidget(self._result_list)

        splitter.addWidget(left)

        # 오른쪽: 선택된 캐릭터 특징
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self._char_name_label = QLabel("캐릭터를 선택하세요")
        self._char_name_label.setStyleSheet(
            "color: #5865F2; font-weight: bold; font-size: 14px;"
        )
        right_layout.addWidget(self._char_name_label)

        self._char_count_label = QLabel("")
        self._char_count_label.setStyleSheet("color: #888; font-size: 11px;")
        right_layout.addWidget(self._char_count_label)

        # 전체 선택 / 해제 버튼
        sel_row = QHBoxLayout()
        btn_select_all = QPushButton("전체 선택")
        btn_select_all.setFixedHeight(26)
        btn_select_all.setStyleSheet(
            "QPushButton { background-color: #3A3A3A; color: #CCC; "
            "border-radius: 4px; font-size: 11px; padding: 0 10px; }"
            "QPushButton:hover { background-color: #444; }"
        )
        btn_select_all.clicked.connect(self._select_all_tags)
        sel_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("전체 해제")
        btn_deselect_all.setFixedHeight(26)
        btn_deselect_all.setStyleSheet(
            "QPushButton { background-color: #3A3A3A; color: #CCC; "
            "border-radius: 4px; font-size: 11px; padding: 0 10px; }"
            "QPushButton:hover { background-color: #444; }"
        )
        btn_deselect_all.clicked.connect(self._deselect_all_tags)
        sel_row.addWidget(btn_deselect_all)
        sel_row.addStretch()
        right_layout.addLayout(sel_row)

        # 태그 영역
        self._tag_scroll = QScrollArea()
        self._tag_scroll.setWidgetResizable(True)
        self._tag_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self._tag_container = QWidget()
        self._tag_container.setStyleSheet("background: transparent;")
        self._tag_flow = FlowLayout(self._tag_container)
        self._tag_flow.setSpacing(5)
        self._tag_scroll.setWidget(self._tag_container)
        right_layout.addWidget(self._tag_scroll, 1)

        # 추가 프롬프트 입력
        right_layout.addWidget(QLabel("추가 프롬프트 (함께 삽입)"))
        self._extra_prompt = QTextEdit()
        self._extra_prompt.setPlaceholderText(
            "추가로 삽입할 프롬프트를 입력하세요 (쉼표 구분)"
        )
        self._extra_prompt.setMaximumHeight(60)
        right_layout.addWidget(self._extra_prompt)

        splitter.addWidget(right)
        splitter.setSizes([280, 550])
        root.addWidget(splitter, 1)

        # 하단 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_apply_both = QPushButton("캐릭터 + 특징 적용")
        btn_apply_both.setFixedSize(160, 38)
        btn_apply_both.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; "
            "border-radius: 6px; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        btn_apply_both.clicked.connect(lambda: self._on_apply(include_name=True))
        btn_row.addWidget(btn_apply_both)

        btn_apply_features = QPushButton("특징만 적용")
        btn_apply_features.setFixedSize(120, 38)
        btn_apply_features.setStyleSheet(
            "QPushButton { background-color: #3A7D44; color: white; "
            "border-radius: 6px; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #4A9D54; }"
        )
        btn_apply_features.clicked.connect(lambda: self._on_apply(include_name=False))
        btn_row.addWidget(btn_apply_features)

        btn_close = QPushButton("닫기")
        btn_close.setFixedSize(80, 38)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #444; color: #DDD; "
            "border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #555; }"
        )
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        root.addLayout(btn_row)

    # ── 검색 ──

    def _on_search_changed(self, text: str):
        self._search_timer.start()

    def _do_search(self):
        query = self._search_input.text().strip()
        # 이스케이프 제거하여 검색
        query = _unescape(query)
        if not query:
            self._result_list.clear()
            self._result_label.setText("검색 결과")
            return

        lookup = self._get_lookup()
        results = lookup.search(query, limit=100)

        self._result_list.clear()
        for orig_key, features, count in results:
            item = QListWidgetItem(f"{orig_key}  ({count:,})")
            item.setData(Qt.ItemDataRole.UserRole, {
                "key": orig_key, "features": features, "count": count
            })
            self._result_list.addItem(item)

        self._result_label.setText(f"검색 결과 ({len(results)})")

    # ── 선택 ──

    def _on_item_selected(self, current: QListWidgetItem, previous):
        if current is None:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        name = data["key"]
        features = data["features"]
        count = data["count"]

        self._current_char_key = name
        self._char_name_label.setText(name)
        self._char_count_label.setText(f"Danbooru 게시물: {count:,}개")

        self._populate_tags(name, features)

    def _populate_tags(self, char_name: str, features_str: str):
        """태그 버튼 생성 (캐릭터 이름과 동일한 태그는 제외)"""
        self._tag_buttons.clear()
        while self._tag_flow.count():
            item = self._tag_flow.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # 캐릭터 이름 정규화 (중복 제외용)
        char_norm = char_name.strip().lower().replace("_", " ")

        tags = [t.strip() for t in features_str.split(",") if t.strip()]
        for tag in tags:
            norm = tag.strip().lower().replace("_", " ")

            # 캐릭터 이름 자체와 동일한 태그 건너뛰기
            if norm == char_norm:
                continue

            is_existing = norm in self._existing_tags
            # 이스케이프 버전도 체크
            escaped = norm.replace("(", r"\(").replace(")", r"\)")
            if escaped in self._existing_tags:
                is_existing = True

            btn = QPushButton(tag if not is_existing else f"{tag} (존재)")
            btn.setCheckable(True)
            btn.setChecked(not is_existing)
            btn.setEnabled(not is_existing)

            if is_existing:
                btn.setStyleSheet(_TAG_EXISTS)
            else:
                btn.setStyleSheet(_TAG_CHECKED)
                btn.toggled.connect(
                    lambda checked, b=btn: b.setStyleSheet(
                        _TAG_CHECKED if checked else _TAG_UNCHECKED
                    )
                )

            self._tag_flow.addWidget(btn)
            self._tag_buttons.append((btn, tag, is_existing))

    # ── 전체 선택/해제 ──

    def _select_all_tags(self):
        for btn, tag, is_existing in self._tag_buttons:
            if not is_existing:
                btn.setChecked(True)

    def _deselect_all_tags(self):
        for btn, tag, is_existing in self._tag_buttons:
            if not is_existing:
                btn.setChecked(False)

    # ── 적용 ──

    def _on_apply(self, include_name: bool):
        """결과 생성 후 accept"""
        selected_tags = []
        for btn, tag, is_existing in self._tag_buttons:
            if not is_existing and btn.isChecked():
                selected_tags.append(tag)

        # 추가 프롬프트
        extra = self._extra_prompt.toPlainText().strip()
        if extra:
            for t in extra.split(","):
                t = t.strip()
                if t:
                    selected_tags.append(t)

        char_name = self._current_char_key
        if not char_name or char_name == "캐릭터를 선택하세요":
            char_name = ""

        self._result = {
            "character_name": char_name if include_name else "",
            "tags": selected_tags,
        }
        self.accept()

    def get_result(self) -> dict | None:
        """다이얼로그 결과. {'character_name': str, 'tags': [str, ...]}"""
        return self._result

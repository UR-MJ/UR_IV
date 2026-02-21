# widgets/character_preset_dialog.py
"""캐릭터 특징 프리셋 다이얼로그 — 검색 & 선택 & 삽입"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QWidget,
    QSplitter, QAbstractItemView, QTextEdit, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer
from widgets.common_widgets import FlowLayout
from utils.theme_manager import get_color


def _get_style():
    return f"""
QDialog {{ background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')}; }}
QLabel {{ color: {get_color('text_primary')}; }}
QLineEdit {{
    background-color: {get_color('bg_input')}; color: {get_color('text_primary')};
    border: 1px solid {get_color('border')}; border-radius: 6px;
    padding: 8px 12px; font-size: 13px;
}}
QLineEdit:focus {{ border: 1px solid {get_color('accent')}; }}
QTextEdit {{
    background-color: {get_color('bg_input')}; color: {get_color('text_primary')};
    border: 1px solid {get_color('border')}; border-radius: 6px;
    padding: 6px 10px; font-size: 12px;
}}
QTextEdit:focus {{ border: 1px solid {get_color('accent')}; }}
QGroupBox {{
    color: {get_color('text_primary')}; font-weight: bold; font-size: 12px;
    border: 1px solid {get_color('border')}; border-radius: 6px;
    margin-top: 8px; padding-top: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    padding: 0 6px;
}}
QListWidget {{
    background-color: {get_color('bg_tertiary')}; color: {get_color('text_primary')};
    border: 1px solid {get_color('border')}; border-radius: 6px;
    font-size: 12px; padding: 4px;
    outline: 0;
}}
QListWidget::item {{
    padding: 6px 8px; border-radius: 4px;
}}
QListWidget::item:selected {{
    background-color: {get_color('accent')}; color: white;
}}
QListWidget::item:hover {{
    background-color: {get_color('bg_button')};
}}
QScrollArea {{ border: none; }}
"""

_TAG_CHECKED = (
    "QPushButton { background-color: #5865F2; color: white; "
    "border: none; border-radius: 11px; padding: 4px 12px; "
    "font-size: 11px; font-weight: bold; }"
    "QPushButton:hover { background-color: #6975F3; }"
)
def _tag_unchecked():
    return (
        f"QPushButton {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; "
        f"border: none; border-radius: 11px; padding: 4px 12px; "
        f"font-size: 11px; text-decoration: line-through; }}"
        f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
    )
def _tag_exists():
    return (
        f"QPushButton {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; "
        f"border: 1px solid {get_color('border')}; border-radius: 11px; padding: 4px 12px; "
        f"font-size: 11px; }}"
    )
_TAG_CUSTOM = (
    "QPushButton { background-color: #D35400; color: white; "
    "border: none; border-radius: 11px; padding: 4px 12px; "
    "font-size: 11px; font-weight: bold; }"
    "QPushButton:hover { background-color: #E67E22; }"
)
def _tag_custom_unchecked():
    return (
        f"QPushButton {{ background-color: #4A3000; color: {get_color('text_muted')}; "
        f"border: none; border-radius: 11px; padding: 4px 12px; "
        f"font-size: 11px; text-decoration: line-through; }}"
        f"QPushButton:hover {{ background-color: #5A3A00; }}"
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
        self.setMinimumSize(1100, 800)
        self.resize(1250, 900)
        self.setStyleSheet(_get_style())

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
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {get_color('text_primary')};")
        root.addWidget(title)

        desc = QLabel(
            "캐릭터를 검색하고 특징 태그를 선택하여 프롬프트에 삽입합니다. "
            "커스텀 프롬프트도 태그로 추가하여 on/off 할 수 있습니다."
        )
        desc.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 12px;")
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
            f"color: {get_color('text_secondary')}; font-weight: bold; font-size: 12px;"
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
        self._char_count_label.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 11px;")
        right_layout.addWidget(self._char_count_label)

        # 전체 선택 / 해제 버튼
        sel_row = QHBoxLayout()
        btn_select_all = QPushButton("전체 선택")
        btn_select_all.setFixedHeight(30)
        btn_select_all.setStyleSheet(
            f"QPushButton {{ background-color: {get_color('bg_button_hover')}; color: {get_color('text_secondary')}; "
            f"border-radius: 4px; font-size: 11px; padding: 0 10px; }}"
            f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
        )
        btn_select_all.clicked.connect(self._select_all_tags)
        sel_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("전체 해제")
        btn_deselect_all.setFixedHeight(30)
        btn_deselect_all.setStyleSheet(
            f"QPushButton {{ background-color: {get_color('bg_button_hover')}; color: {get_color('text_secondary')}; "
            f"border-radius: 4px; font-size: 11px; padding: 0 10px; }}"
            f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
        )
        btn_deselect_all.clicked.connect(self._deselect_all_tags)
        sel_row.addWidget(btn_deselect_all)
        sel_row.addStretch()
        right_layout.addLayout(sel_row)

        # 태그 영역 (핵심/의상 2섹션)
        self._tag_scroll = QScrollArea()
        self._tag_scroll.setWidgetResizable(True)
        self._tag_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self._tag_container = QWidget()
        self._tag_container.setStyleSheet("background: transparent;")
        self._tag_main_layout = QVBoxLayout(self._tag_container)
        self._tag_main_layout.setContentsMargins(0, 0, 0, 0)
        self._tag_main_layout.setSpacing(8)

        # 핵심 특징 섹션
        self._core_label = QLabel("핵심 특징")
        self._core_label.setStyleSheet(
            "color: #5865F2; font-weight: bold; font-size: 12px; padding: 2px 0;"
        )
        self._tag_main_layout.addWidget(self._core_label)
        self._core_flow_container = QWidget()
        self._core_flow_container.setStyleSheet("background: transparent;")
        self._core_flow = FlowLayout(self._core_flow_container)
        self._core_flow.setSpacing(5)
        self._tag_main_layout.addWidget(self._core_flow_container)

        # 의상 · 추가 특징 섹션
        self._costume_label = QLabel("의상 · 추가 특징")
        self._costume_label.setStyleSheet(
            "color: #D35400; font-weight: bold; font-size: 12px; padding: 2px 0;"
        )
        self._tag_main_layout.addWidget(self._costume_label)
        self._costume_flow_container = QWidget()
        self._costume_flow_container.setStyleSheet("background: transparent;")
        self._costume_flow = FlowLayout(self._costume_flow_container)
        self._costume_flow.setSpacing(5)
        self._tag_main_layout.addWidget(self._costume_flow_container)

        self._tag_main_layout.addStretch()
        self._tag_scroll.setWidget(self._tag_container)
        right_layout.addWidget(self._tag_scroll, 1)

        # 프롬프트 추가 입력 행
        add_row = QHBoxLayout()
        add_row.setSpacing(4)
        self._add_prompt_input = QLineEdit()
        self._add_prompt_input.setPlaceholderText(
            "프롬프트 추가 (쉼표로 여러 개 가능)"
        )
        self._add_prompt_input.setFixedHeight(30)
        self._add_prompt_input.returnPressed.connect(self._add_custom_prompts)
        add_row.addWidget(self._add_prompt_input, 1)

        btn_add = QPushButton("+ 추가")
        btn_add.setFixedSize(70, 30)
        btn_add.setStyleSheet(
            "QPushButton { background-color: #D35400; color: white; "
            "border-radius: 4px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background-color: #E67E22; }"
        )
        btn_add.clicked.connect(self._add_custom_prompts)
        add_row.addWidget(btn_add)
        right_layout.addLayout(add_row)

        # 프리셋 저장/삭제 + 상태
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)

        btn_save_preset = QPushButton("프리셋 저장")
        btn_save_preset.setFixedHeight(30)
        btn_save_preset.setStyleSheet(
            "QPushButton { background-color: #D35400; color: white; "
            "border-radius: 4px; font-weight: bold; font-size: 11px; "
            "padding: 0 10px; }"
            "QPushButton:hover { background-color: #E67E22; }"
        )
        btn_save_preset.clicked.connect(self._save_preset)
        preset_row.addWidget(btn_save_preset)

        btn_del_preset = QPushButton("프리셋 삭제")
        btn_del_preset.setFixedHeight(30)
        btn_del_preset.setStyleSheet(
            "QPushButton { background-color: #C0392B; color: white; "
            "border-radius: 4px; font-weight: bold; font-size: 11px; "
            "padding: 0 10px; }"
            "QPushButton:hover { background-color: #E74C3C; }"
        )
        btn_del_preset.clicked.connect(self._delete_preset)
        preset_row.addWidget(btn_del_preset)

        self._preset_status = QLabel("")
        self._preset_status.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 11px;")
        preset_row.addWidget(self._preset_status)
        preset_row.addStretch()
        right_layout.addLayout(preset_row)

        splitter.addWidget(right)
        splitter.setSizes([350, 850])
        root.addWidget(splitter, 1)

        # 캐릭터 조건부 프롬프트
        self._cond_toggle = QPushButton("▶ 캐릭터 조건부 프롬프트")
        self._cond_toggle.setCheckable(True)
        self._cond_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_input')}; color: #FFA726;
                border: 1px solid {get_color('border')}; border-radius: 6px;
                font-weight: bold; font-size: 12px;
                padding: 6px 12px; text-align: left;
            }}
            QPushButton:checked {{ background-color: #3A3000; border-color: #D35400; }}
            QPushButton:hover {{ background-color: {get_color('bg_button')}; }}
        """)
        self._cond_toggle.toggled.connect(self._on_cond_toggle)
        root.addWidget(self._cond_toggle)

        self._cond_container = QWidget()
        cond_layout = QVBoxLayout(self._cond_container)
        cond_layout.setContentsMargins(0, 0, 0, 0)
        cond_layout.setSpacing(4)

        from widgets.condition_block_editor import ConditionBlockEditor
        self._cond_block_editor = ConditionBlockEditor()
        self._cond_block_editor.setMinimumHeight(150)
        cond_layout.addWidget(self._cond_block_editor)

        self._cond_container.hide()
        root.addWidget(self._cond_container)

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
            f"QPushButton {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; "
            f"border-radius: 6px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
        )
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        root.addLayout(btn_row)

    def _on_cond_toggle(self, checked: bool):
        """조건부 프롬프트 섹션 토글"""
        self._cond_container.setVisible(checked)
        self._cond_toggle.setText(
            "▼ 캐릭터 조건부 프롬프트" if checked
            else "▶ 캐릭터 조건부 프롬프트"
        )

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

        # 최소 2글자 이상 (1글자 검색 시 수천 개 매칭 → 프리징 방지)
        if len(query) < 2:
            self._result_list.clear()
            self._result_label.setText("2글자 이상 입력하세요")
            return

        lookup = self._get_lookup()
        results = lookup.search(query, limit=100)

        # 저장된 프리셋 목록 (★ 표시용)
        from utils.character_presets import list_character_presets
        saved_presets = list_character_presets()

        self._result_list.clear()
        for orig_key, features, count in results:
            norm = orig_key.strip().lower().replace("_", " ")
            mark = "★ " if norm in saved_presets else ""
            item = QListWidgetItem(f"{mark}{orig_key}  ({count:,})")
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

        # 저장된 프리셋 자동 로드 → 커스텀 태그 + 조건부 규칙 복원
        from utils.character_presets import get_character_preset_full
        preset = get_character_preset_full(name)
        if preset:
            saved = preset.get("extra_prompt", "")
            if saved:
                # 저장된 태그 중 danbooru 특징에 없는 것만 커스텀 태그로 추가
                feature_norms = set()
                for t in features.split(","):
                    n = t.strip().lower().replace("_", " ")
                    if n:
                        feature_norms.add(n)

                for t in saved.split(","):
                    tag = t.strip()
                    norm = tag.lower().replace("_", " ")
                    if norm and norm not in feature_norms:
                        self._add_single_custom_tag(tag)

            # 조건부 규칙 복원 (새 JSON 포맷 우선, 기존 텍스트 포맷 마이그레이션)
            cond_json = preset.get("cond_rules_json", "")
            if cond_json:
                self._cond_block_editor.set_rules_json(cond_json)
            else:
                from utils.condition_block import migrate_old_rules
                rules = []
                old_pos = preset.get("cond_rules", "")
                old_neg = preset.get("cond_neg_rules", "")
                if old_pos:
                    rules.extend(migrate_old_rules(old_pos))
                if old_neg:
                    neg_rules = migrate_old_rules(old_neg)
                    for r in neg_rules:
                        r.location = "neg"
                    rules.extend(neg_rules)
                self._cond_block_editor.set_rules(rules)

            self._preset_status.setText("★ 저장된 프리셋 로드됨")
            self._preset_status.setStyleSheet("color: #D35400; font-size: 11px;")
        else:
            self._cond_block_editor.clear()
            self._preset_status.setText("")

    def _populate_tags(self, char_name: str, features_str: str):
        """태그 버튼 생성 — 핵심/의상 2섹션 분리"""
        self._tag_buttons.clear()
        for flow in [self._core_flow, self._costume_flow]:
            while flow.count():
                item = flow.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

        char_norm = char_name.strip().lower().replace("_", " ")

        # 핵심/의상 분리 조회
        lookup = self._get_lookup()
        core_result = lookup.lookup_core(char_name)
        costume_result = lookup.lookup_costume(char_name)

        core_tags = []
        if core_result:
            core_tags = [t.strip() for t in core_result[0].split(",") if t.strip()]
        costume_tags = []
        if costume_result:
            costume_tags = [t.strip() for t in costume_result[0].split(",") if t.strip()]

        # core/costume 모두 없으면 features_str을 전부 핵심으로 표시
        if not core_tags and not costume_tags:
            core_tags = [t.strip() for t in features_str.split(",") if t.strip()]

        self._core_label.setText(f"핵심 특징 ({len(core_tags)})")
        self._costume_label.setText(f"의상 · 추가 특징 ({len(costume_tags)})")
        self._costume_label.setVisible(bool(costume_tags))
        self._costume_flow_container.setVisible(bool(costume_tags))

        for tag_list, flow in [(core_tags, self._core_flow),
                                (costume_tags, self._costume_flow)]:
            for tag in tag_list:
                norm = tag.strip().lower().replace("_", " ")
                if norm == char_norm:
                    continue

                is_existing = norm in self._existing_tags
                escaped = norm.replace("(", r"\(").replace(")", r"\)")
                if escaped in self._existing_tags:
                    is_existing = True

                btn = QPushButton(tag if not is_existing else f"{tag} (존재)")
                btn.setCheckable(True)
                btn.setChecked(not is_existing)
                btn.setEnabled(not is_existing)

                if is_existing:
                    btn.setStyleSheet(_tag_exists())
                else:
                    btn.setStyleSheet(_TAG_CHECKED)
                    btn.toggled.connect(
                        lambda checked, b=btn: b.setStyleSheet(
                            _TAG_CHECKED if checked else _tag_unchecked()
                        )
                    )

                flow.addWidget(btn)
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

    # ── 커스텀 프롬프트 추가 ──

    def _add_custom_prompts(self):
        """입력창에서 프롬프트를 읽어 커스텀 태그 버튼으로 추가"""
        text = self._add_prompt_input.text().strip()
        if not text:
            return

        for t in text.split(","):
            tag = t.strip()
            if tag:
                self._add_single_custom_tag(tag)

        self._add_prompt_input.clear()

    def _add_single_custom_tag(self, tag: str):
        """커스텀 프롬프트를 태그 버튼으로 추가 (중복 무시)"""
        norm = tag.strip().lower().replace("_", " ")

        # 이미 존재하는 태그인지 확인
        for btn, existing_tag, is_existing in self._tag_buttons:
            if existing_tag.strip().lower().replace("_", " ") == norm:
                # 이미 있으면 체크만 켬
                if not is_existing:
                    btn.setChecked(True)
                return

        btn = QPushButton(tag)
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.setStyleSheet(_TAG_CUSTOM)
        btn.toggled.connect(
            lambda checked, b=btn: b.setStyleSheet(
                _TAG_CUSTOM if checked else _tag_custom_unchecked()
            )
        )
        self._core_flow.addWidget(btn)
        self._tag_buttons.append((btn, tag, False))

    # ── 프리셋 저장/삭제 ──

    def _save_preset(self):
        """현재 캐릭터의 체크된 태그 + 조건부 규칙을 프리셋으로 저장"""
        if not self._current_char_key:
            return

        checked_tags = []
        for btn, tag, is_existing in self._tag_buttons:
            if not is_existing and btn.isChecked():
                checked_tags.append(tag)

        combined = ", ".join(checked_tags)
        cond_rules_json = self._cond_block_editor.get_rules_json()

        from utils.character_presets import save_character_preset
        save_character_preset(
            self._current_char_key, combined, cond_rules_json
        )
        self._preset_status.setText(f"★ 저장 완료")
        self._preset_status.setStyleSheet("color: #27AE60; font-size: 11px;")

    def _delete_preset(self):
        """현재 캐릭터의 프리셋 삭제"""
        if not self._current_char_key:
            return
        from utils.character_presets import delete_character_preset, has_preset
        if not has_preset(self._current_char_key):
            self._preset_status.setText("프리셋 없음")
            self._preset_status.setStyleSheet("color: #E74C3C; font-size: 11px;")
            return
        delete_character_preset(self._current_char_key)
        self._preset_status.setText("프리셋 삭제됨")
        self._preset_status.setStyleSheet("color: #E74C3C; font-size: 11px;")

    # ── 적용 ──

    def _on_apply(self, include_name: bool):
        """결과 생성 후 accept"""
        selected_tags = []
        for btn, tag, is_existing in self._tag_buttons:
            if not is_existing and btn.isChecked():
                selected_tags.append(tag)

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

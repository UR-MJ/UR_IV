# tabs/settings_tab.py
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget,
    QLabel, QLineEdit, QGroupBox, QCheckBox, QPushButton, QTextEdit,
    QFileDialog, QMessageBox, QSpinBox, QDoubleSpinBox, QGridLayout,
    QScrollArea, QListWidgetItem, QInputDialog, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from widgets.common_widgets import NoScrollComboBox, NoScrollSpinBox, NoScrollDoubleSpinBox
from utils.shortcut_manager import (
    get_shortcut_manager, SHORTCUT_LABELS, key_event_to_string
)
from utils.file_wildcard import get_file_wildcard_manager
from utils.theme_manager import get_color
import config


class KeyCaptureButton(QPushButton):
    """클릭 후 다음 키 입력을 캡처하는 버튼"""

    def __init__(self, shortcut_id: str, parent=None):
        super().__init__(parent)
        self.shortcut_id = shortcut_id
        self._capturing = False
        sm = get_shortcut_manager()
        self.setText(sm.get(shortcut_id))
        self.setFixedHeight(30)
        self.setMinimumWidth(120)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_input')}; border: 1px solid {get_color('border')};
                border-radius: 4px; color: {get_color('text_primary')}; font-size: 12px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{ border: 1px solid {get_color('text_muted')}; }}
        """)
        self.clicked.connect(self._start_capture)

    def _start_capture(self):
        self._capturing = True
        self.setText("키를 눌러주세요...")
        self.setStyleSheet("""
            QPushButton {
                background-color: #3A3A00; border: 1px solid #FFD700;
                border-radius: 4px; color: #FFD700; font-size: 12px;
                padding: 2px 10px;
            }
        """)
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key_str = key_event_to_string(event)
        if not key_str:
            return  # 수정자만 눌린 경우 무시

        sm = get_shortcut_manager()
        sm.set(self.shortcut_id, key_str)
        self.setText(key_str)
        self._capturing = False
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_input')}; border: 1px solid {get_color('border')};
                border-radius: 4px; color: {get_color('text_primary')}; font-size: 12px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{ border: 1px solid {get_color('text_muted')}; }}
        """)

    def focusOutEvent(self, event):
        if self._capturing:
            self._capturing = False
            sm = get_shortcut_manager()
            self.setText(sm.get(self.shortcut_id))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color('bg_input')}; border: 1px solid {get_color('border')};
                    border-radius: 4px; color: {get_color('text_primary')}; font-size: 12px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{ border: 1px solid {get_color('text_muted')}; }}
            """)
        super().focusOutEvent(event)

    def refresh(self):
        """ShortcutManager의 현재 값으로 표시 갱신"""
        sm = get_shortcut_manager()
        self.setText(sm.get(self.shortcut_id))


class SettingsTab(QWidget):
    """설정 탭"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_ui = parent
        self._is_modern = getattr(config, 'UI_STYLE', 'classic') == 'modern'

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 사이드바
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180 if not self._is_modern else 200)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        if self._is_modern:
            self.sidebar.setStyleSheet(f"""
                QListWidget {{
                    background-color: {get_color('bg_primary')};
                    border: none;
                    border-right: 1px solid {get_color('border')};
                    outline: none;
                    padding: 8px 6px;
                }}
                QListWidget::item {{
                    color: {get_color('text_secondary')};
                    padding: 12px 16px;
                    font-weight: 600;
                    border-radius: 10px;
                    margin: 2px 0;
                }}
                QListWidget::item:selected {{
                    background-color: {get_color('bg_tertiary')};
                    color: {get_color('text_primary')};
                }}
                QListWidget::item:hover {{
                    background-color: {get_color('bg_secondary')};
                }}
            """)
        else:
            self.sidebar.setStyleSheet(f"""
                QListWidget {{
                    background-color: {get_color('bg_primary')};
                    border: none;
                    border-right: 1px solid {get_color('bg_input')};
                    outline: none;
                }}
                QListWidget::item {{
                    color: {get_color('text_secondary')};
                    padding: 15px 20px;
                    font-weight: bold;
                    border-bottom: 1px solid {get_color('bg_secondary')};
                }}
                QListWidget::item:selected {{
                    background-color: {get_color('bg_tertiary')};
                    color: {get_color('text_primary')};
                    border-left: 3px solid #5865F2;
                }}
                QListWidget::item:hover {{
                    background-color: {get_color('bg_secondary')};
                }}
            """)
        
        items = [
            "📝 프롬프트 로직",
            "✨ 자동완성",
            "🧹 프롬프트 정리",
            "🎴 와일드카드",
            "🎮 조작 및 단축키",
            "🖌️ 에디터 설정",
            "🔌 API 연결",
            "💾 저장 경로",
            "🌐 웹 브라우저",
            "🎨 테마",
            "📦 백업/복원"
        ]
        for item_text in items:
            self.sidebar.addItem(item_text)
            
        layout.addWidget(self.sidebar)
        
        # 페이지 스택
        self.pages = QStackedWidget()
        self.pages.setStyleSheet(f"background-color: {get_color('bg_primary')};")
        layout.addWidget(self.pages)
        
        # 각 페이지 생성
        self.page_logic = self._create_logic_page()
        self.page_autocomplete = self._create_autocomplete_page()
        self.page_cleaning = self._create_cleaning_page()
        self.page_wildcard = self._create_wildcard_page()
        self.page_controls = self._create_controls_page()
        self.page_editor = self._create_editor_page()
        self.page_api = self._create_api_page()
        self.page_storage = self._create_storage_page()
        self.page_web = self._create_web_page()
        self.page_theme = self._create_theme_page()
        self.page_backup = self._create_backup_page()

        self.pages.addWidget(self.page_logic)
        self.pages.addWidget(self.page_autocomplete)
        self.pages.addWidget(self.page_cleaning)
        self.pages.addWidget(self.page_wildcard)
        self.pages.addWidget(self.page_controls)
        self.pages.addWidget(self.page_editor)
        self.pages.addWidget(self.page_api)
        self.pages.addWidget(self.page_storage)
        self.pages.addWidget(self.page_web)
        self.pages.addWidget(self.page_theme)
        self.pages.addWidget(self.page_backup)

        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

    def _create_header(self, text):
        """헤더 라벨 생성"""
        if self._is_modern:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {get_color('text_primary')}; font-size: 20px; "
                f"font-weight: bold; margin-bottom: 12px; background: transparent;"
            )
        else:
            lbl = QLabel(f"<h2>{text}</h2>")
            lbl.setStyleSheet("color: white; margin-bottom: 10px;")
        return lbl

    def _create_container(self):
        """컨테이너 위젯 생성"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        w = QWidget()
        l = QVBoxLayout(w)
        if self._is_modern:
            l.setContentsMargins(36, 30, 36, 30)
            l.setSpacing(16)
        else:
            l.setContentsMargins(30, 30, 30, 30)
            l.setSpacing(20)
        l.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(w)
        return scroll, l

    def _create_logic_page(self):
        """프롬프트 로직 페이지"""
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(30, 30, 30, 30)
        l.setSpacing(20)

        l.addWidget(self._create_header("프롬프트 로직 설정"))

        # 조건부 프롬프트 (통합 블록 에디터)
        group = QGroupBox("조건부 프롬프트")
        gl = QVBoxLayout(group)

        self.cond_prompt_check = QCheckBox("조건부 프롬프트 활성화")
        self.cond_prevent_dupe_check = QCheckBox(
            "중복 태그 방지 (이미 있으면 추가 안 함)"
        )
        self.cond_prevent_dupe_check.setChecked(True)
        self.cond_prevent_dupe_check.setStyleSheet("color: #FFD700;")

        from widgets.condition_block_editor import ConditionBlockEditor

        gl.addWidget(self.cond_prompt_check)
        gl.addWidget(self.cond_prevent_dupe_check)

        # 2단 레이아웃: 왼쪽 Positive / 오른쪽 Negative
        editors_container = QWidget()
        editors_hl = QHBoxLayout(editors_container)
        editors_hl.setContentsMargins(0, 0, 0, 0)
        editors_hl.setSpacing(6)

        # Positive 에디터
        pos_w = QWidget()
        pos_vl = QVBoxLayout(pos_w)
        pos_vl.setContentsMargins(0, 0, 0, 0)
        pos_vl.setSpacing(4)
        pos_lbl = QLabel("Positive")
        pos_lbl.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 12px;")
        pos_vl.addWidget(pos_lbl)
        self.cond_block_editor_pos = ConditionBlockEditor(fixed_target="pos")
        pos_vl.addWidget(self.cond_block_editor_pos, 1)
        editors_hl.addWidget(pos_w)

        # Negative 에디터
        neg_w = QWidget()
        neg_vl = QVBoxLayout(neg_w)
        neg_vl.setContentsMargins(0, 0, 0, 0)
        neg_vl.setSpacing(4)
        neg_lbl = QLabel("Negative")
        neg_lbl.setStyleSheet("color: #F44336; font-weight: bold; font-size: 12px;")
        neg_vl.addWidget(neg_lbl)
        self.cond_block_editor_neg = ConditionBlockEditor(fixed_target="neg")
        neg_vl.addWidget(self.cond_block_editor_neg, 1)
        editors_hl.addWidget(neg_w)

        gl.addWidget(editors_container, 1)
        l.addWidget(group, 1)

        # 저장 버튼
        self.btn_save_logic = QPushButton("💾 설정 저장")
        self.btn_save_logic.clicked.connect(self.save_all_settings)
        l.addWidget(self.btn_save_logic)

        return w

    def _create_autocomplete_page(self):
        """자동완성 설정 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("✨ 자동완성 설정"))
        
        # 자동완성 활성화
        group = QGroupBox("자동완성 기능")
        gl = QVBoxLayout(group)
        
        self.chk_autocomplete_enabled = QCheckBox("자동완성 활성화")
        self.chk_autocomplete_enabled.setChecked(True)
        self.chk_autocomplete_enabled.setStyleSheet("font-weight: bold;")
        gl.addWidget(self.chk_autocomplete_enabled)
        
        # 최소 입력 글자
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("최소 입력 글자 수:"))
        self.spin_min_chars = NoScrollSpinBox()
        self.spin_min_chars.setRange(1, 5)
        self.spin_min_chars.setValue(2)
        h1.addWidget(self.spin_min_chars)
        h1.addStretch()
        gl.addLayout(h1)
        
        # 최대 제안 개수
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("최대 제안 개수:"))
        self.spin_max_suggestions = NoScrollSpinBox()
        self.spin_max_suggestions.setRange(5, 50)
        self.spin_max_suggestions.setValue(15)
        h2.addWidget(self.spin_max_suggestions)
        h2.addStretch()
        gl.addLayout(h2)
        
        l.addWidget(group)
        
        # 자동완성 대상
        group2 = QGroupBox("자동완성 대상")
        gl2 = QVBoxLayout(group2)
        
        self.chk_ac_character = QCheckBox("캐릭터 (Character)")
        self.chk_ac_character.setChecked(True)
        gl2.addWidget(self.chk_ac_character)
        
        self.chk_ac_copyright = QCheckBox("작품 (Copyright)")
        self.chk_ac_copyright.setChecked(True)
        gl2.addWidget(self.chk_ac_copyright)
        
        self.chk_ac_artist = QCheckBox("작가 (Artist)")
        self.chk_ac_artist.setChecked(True)
        gl2.addWidget(self.chk_ac_artist)
        
        self.chk_ac_general = QCheckBox("일반 태그 (General)")
        self.chk_ac_general.setChecked(True)
        gl2.addWidget(self.chk_ac_general)
        
        l.addWidget(group2)
        
        # 저장 버튼
        btn_save = QPushButton("💾 설정 저장")
        btn_save.clicked.connect(self.save_all_settings)
        l.addWidget(btn_save)
        
        return w

    def _create_cleaning_page(self):
        """프롬프트 정리 설정 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("🧹 프롬프트 자동 정리"))
        
        group = QGroupBox("자동 정리 옵션")
        gl = QVBoxLayout(group)
        
        self.chk_auto_comma = QCheckBox("쉼표 자동 정리 (tag1,tag2 → tag1, tag2)")
        self.chk_auto_comma.setChecked(True)
        gl.addWidget(self.chk_auto_comma)
        
        self.chk_auto_space = QCheckBox("공백 자동 정리 (여러 공백 → 단일 공백)")
        self.chk_auto_space.setChecked(True)
        gl.addWidget(self.chk_auto_space)
        
        self.chk_auto_escape = QCheckBox("괄호 자동 이스케이프 (() → \\(\\))")
        self.chk_auto_escape.setChecked(False)
        gl.addWidget(self.chk_auto_escape)
        
        self.chk_remove_duplicates = QCheckBox("중복 태그 자동 제거")
        self.chk_remove_duplicates.setChecked(False)
        gl.addWidget(self.chk_remove_duplicates)
        
        self.chk_underscore_to_space = QCheckBox("밑줄 → 공백 변환 (blue_hair → blue hair)")
        self.chk_underscore_to_space.setChecked(True)
        gl.addWidget(self.chk_underscore_to_space)

        # Connect signals
        self.chk_auto_comma.stateChanged.connect(self._on_cleaning_option_changed)
        self.chk_auto_space.stateChanged.connect(self._on_cleaning_option_changed)
        self.chk_auto_escape.stateChanged.connect(self._on_cleaning_option_changed)
        self.chk_remove_duplicates.stateChanged.connect(self._on_cleaning_option_changed)
        self.chk_underscore_to_space.stateChanged.connect(self._on_cleaning_option_changed)
        
        l.addWidget(group)
        
        # 저장 버튼
        btn_save = QPushButton("💾 설정 저장")
        btn_save.clicked.connect(self.save_all_settings)
        l.addWidget(btn_save)
        
        return w

    def _on_cleaning_option_changed(self):
        if self.parent_ui and hasattr(self.parent_ui, 'update_cleaner_options'):
            self.parent_ui.update_cleaner_options()

    # ── 와일드카드 페이지 ──

    def _create_wildcard_page(self):
        """와일드카드 관리 페이지"""
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        main_layout.addWidget(self._create_header("🎴 와일드카드 관리"))

        # 활성화 체크박스
        self.chk_wildcard_enabled = QCheckBox("와일드카드 시스템 활성화")
        self.chk_wildcard_enabled.setChecked(True)
        self.chk_wildcard_enabled.setStyleSheet("font-weight: bold; color: #FFD700;")
        main_layout.addWidget(self.chk_wildcard_enabled)

        # 상단: 파일 목록 + 편집기
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 왼쪽: 파일 목록
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        left_layout.addWidget(QLabel("와일드카드 목록"))
        self.wildcard_list = QListWidget()
        self.wildcard_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')};
                border-radius: 4px; color: {get_color('text_primary')};
            }}
            QListWidget::item {{ padding: 6px; }}
            QListWidget::item:selected {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; }}
        """)
        self.wildcard_list.currentRowChanged.connect(self._on_wildcard_selected)
        left_layout.addWidget(self.wildcard_list)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_new = QPushButton("+ 새로 만들기")
        btn_new.clicked.connect(self._new_wildcard)
        btn_del = QPushButton("- 삭제")
        btn_del.clicked.connect(self._delete_wildcard)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_del)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_panel)

        # 오른쪽: 편집기
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        # 파일명 표시
        self._wc_name_label = QLabel("파일을 선택하세요")
        self._wc_name_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 13px;")
        right_layout.addWidget(self._wc_name_label)

        self.wildcard_editor = QTextEdit()
        self.wildcard_editor.setPlaceholderText(
            "한 줄에 하나의 그룹\n"
            "쉼표로 옵션 구분\n\n"
            "예시:\n"
            "red hair, blue hair, green hair\n"
            "ponytail, twintails, braid\n"
            "[short|long] sleeves, bare arms"
        )
        self.wildcard_editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')};
                border-radius: 4px; color: {get_color('text_primary')}; font-family: Consolas;
                font-size: 12px;
            }}
        """)
        right_layout.addWidget(self.wildcard_editor)

        # 저장 + 미리보기 버튼
        edit_btn_row = QHBoxLayout()
        btn_save_wc = QPushButton("💾 저장")
        btn_save_wc.clicked.connect(self._save_current_wildcard)
        btn_preview = QPushButton("🎲 미리보기")
        btn_preview.clicked.connect(self._preview_wildcard)
        edit_btn_row.addWidget(btn_save_wc)
        edit_btn_row.addWidget(btn_preview)
        right_layout.addLayout(edit_btn_row)

        # 미리보기 결과
        self._wc_preview_label = QLabel("")
        self._wc_preview_label.setWordWrap(True)
        self._wc_preview_label.setStyleSheet(
            f"color: #8BC34A; background-color: {get_color('bg_primary')}; "
            f"border: 1px solid {get_color('border')}; border-radius: 4px; padding: 8px;"
        )
        self._wc_preview_label.setMinimumHeight(40)
        right_layout.addWidget(self._wc_preview_label)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter, 1)

        # 도움말
        help_group = QGroupBox("문법 도움말")
        help_layout = QVBoxLayout(help_group)
        help_text = QLabel(
            "<b>프롬프트에서 사용:</b> <code>~/이름/~</code><br>"
            "<b>n개 그룹만 선택:</b> <code>~/이름:2/~</code> (2개 그룹에서 각 1개)<br><br>"
            "<b>파일 형식 (한 줄 = 한 그룹):</b><br>"
            "<code>red hair, blue hair, green hair</code> ← 이 중 하나 선택<br>"
            "<code>ponytail, twintails, braid</code> ← 이 중 하나 선택<br><br>"
            "<b>특수 문법:</b><br>"
            "<code>[A|B]</code> → A 또는 B 중 랜덤 선택<br>"
            "<code>~/다른이름/~</code> → 중첩 와일드카드 (다른 파일 참조)<br>"
            "<code>#</code>으로 시작하는 줄은 주석 (무시됨)"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 11px;")
        help_text.setTextFormat(Qt.TextFormat.RichText)
        help_layout.addWidget(help_text)
        main_layout.addWidget(help_group)

        # 초기 목록 로드
        self._refresh_wildcard_list()

        return w

    def _refresh_wildcard_list(self):
        """와일드카드 목록 갱신"""
        mgr = get_file_wildcard_manager()
        self.wildcard_list.clear()
        for name in mgr.get_wildcard_names():
            info = mgr.get_info(name)
            item = QListWidgetItem(f"{name}  ({info['groups']}그룹, {info['total_options']}옵션)")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.wildcard_list.addItem(item)

    def _on_wildcard_selected(self, row):
        """와일드카드 파일 선택 시"""
        item = self.wildcard_list.item(row)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        mgr = get_file_wildcard_manager()
        content = mgr.get_wildcard_content(name)
        self.wildcard_editor.setPlainText(content)
        self._wc_name_label.setText(f"편집 중: {name}.txt  |  사용: ~/{ name }/~")
        self._wc_preview_label.setText("")

    def _new_wildcard(self):
        """새 와일드카드 생성"""
        name, ok = QInputDialog.getText(
            self, "새 와일드카드", "와일드카드 이름 (영문/한글, 확장자 제외):"
        )
        if not ok or not name.strip():
            return
        name = name.strip().replace(' ', '_')
        mgr = get_file_wildcard_manager()
        if name in mgr.get_wildcard_names():
            QMessageBox.warning(self, "중복", f"'{name}' 와일드카드가 이미 존재합니다.")
            return
        mgr.save_wildcard(name, "# 여기에 옵션을 작성하세요\n# 한 줄 = 한 그룹, 쉼표로 옵션 구분\n")
        self._refresh_wildcard_list()
        # 새로 만든 항목 선택
        for i in range(self.wildcard_list.count()):
            item = self.wildcard_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self.wildcard_list.setCurrentRow(i)
                break

    def _delete_wildcard(self):
        """선택된 와일드카드 삭제"""
        item = self.wildcard_list.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"'{name}' 와일드카드를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            mgr = get_file_wildcard_manager()
            mgr.delete_wildcard(name)
            self._refresh_wildcard_list()
            self.wildcard_editor.clear()
            self._wc_name_label.setText("파일을 선택하세요")
            self._wc_preview_label.setText("")

    def _save_current_wildcard(self):
        """현재 편집 중인 와일드카드 저장"""
        item = self.wildcard_list.currentItem()
        if not item:
            QMessageBox.warning(self, "알림", "저장할 와일드카드를 선택하세요.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        content = self.wildcard_editor.toPlainText()
        mgr = get_file_wildcard_manager()
        mgr.save_wildcard(name, content)
        self._refresh_wildcard_list()
        # 선택 유지
        for i in range(self.wildcard_list.count()):
            it = self.wildcard_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == name:
                self.wildcard_list.setCurrentRow(i)
                break
        QMessageBox.information(self, "저장 완료", f"'{name}' 와일드카드가 저장되었습니다.")

    def _preview_wildcard(self):
        """와일드카드 미리보기"""
        item = self.wildcard_list.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        # 먼저 현재 편집 내용 임시 저장 (미리보기용)
        mgr = get_file_wildcard_manager()
        content = self.wildcard_editor.toPlainText()
        mgr.save_wildcard(name, content)
        result = mgr.preview(name)
        self._wc_preview_label.setText(result)

    def _create_controls_page(self):
        """조작 및 단축키 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("조작 및 단축키 설정"))
        
        group = QGroupBox("마우스 휠 동작 설정")
        gl = QVBoxLayout(group)
        gl.setSpacing(15)
        
        # 줌 키
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("🔍 줌 (확대/축소) 키:"))
        self.combo_zoom_key = NoScrollComboBox() 
        self.combo_zoom_key.addItems(["Ctrl", "Shift", "Alt", "None"])
        self.combo_zoom_key.setCurrentText("Ctrl") 
        h1.addWidget(self.combo_zoom_key)
        gl.addLayout(h1)
        
        # 회전 키
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("🔄 이미지 회전 키:"))
        self.combo_rotate_key = NoScrollComboBox()
        self.combo_rotate_key.addItems(["Ctrl", "Shift", "Alt", "None"])
        self.combo_rotate_key.setCurrentText("Shift") 
        h2.addWidget(self.combo_rotate_key)
        gl.addLayout(h2)
        
        gl.addWidget(QLabel("※ 변경 후 '설정 저장'을 눌러야 적용됩니다."))
        l.addWidget(group)

        # ── 키보드 단축키 ──
        shortcut_group = QGroupBox("키보드 단축키")
        sg_layout = QVBoxLayout(shortcut_group)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnMinimumWidth(0, 140)

        self._key_capture_buttons = {}
        row = 0
        for sc_id, label_text in SHORTCUT_LABELS.items():
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {get_color('text_secondary')};")
            btn = KeyCaptureButton(sc_id)
            self._key_capture_buttons[sc_id] = btn
            grid.addWidget(lbl, row, 0)
            grid.addWidget(btn, row, 1)
            row += 1

        sg_layout.addLayout(grid)

        btn_reset = QPushButton("🔄 기본값 복원")
        btn_reset.setFixedHeight(30)
        btn_reset.setStyleSheet(f"""
            QPushButton {{ background-color: {get_color('bg_button')}; border: 1px solid {get_color('text_muted')};
                          border-radius: 4px; color: {get_color('text_primary')}; }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
        """)
        btn_reset.clicked.connect(self._reset_shortcuts)
        sg_layout.addWidget(btn_reset)

        l.addWidget(shortcut_group)

        self.btn_save_controls = QPushButton("💾 설정 저장")
        self.btn_save_controls.clicked.connect(self.save_all_settings)
        l.addWidget(self.btn_save_controls)

        return w

    def _reset_shortcuts(self):
        """단축키를 기본값으로 복원"""
        sm = get_shortcut_manager()
        sm.reset_to_defaults()
        for btn in self._key_capture_buttons.values():
            btn.refresh()
        QMessageBox.information(self, "복원 완료", "단축키가 기본값으로 복원되었습니다.")

    def _create_editor_page(self):
        """에디터 설정 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("🖌️ 에디터 기본값 설정"))

        # ── 도구 기본값 ──
        group_tool = QGroupBox("도구 기본값")
        gl_tool = QVBoxLayout(group_tool)
        gl_tool.setSpacing(10)

        # 도구 크기 (브러시/지우개)
        h_ts = QHBoxLayout()
        h_ts.addWidget(QLabel("도구 크기 (브러시/지우개):"))
        self.spin_def_tool_size = NoScrollSpinBox()
        self.spin_def_tool_size.setRange(1, 300)
        self.spin_def_tool_size.setValue(20)
        h_ts.addWidget(self.spin_def_tool_size)
        h_ts.addStretch()
        gl_tool.addLayout(h_ts)

        # 효과 강도
        h_es = QHBoxLayout()
        h_es.addWidget(QLabel("효과 강도:"))
        self.spin_def_effect_strength = NoScrollSpinBox()
        self.spin_def_effect_strength.setRange(1, 100)
        self.spin_def_effect_strength.setValue(15)
        h_es.addWidget(self.spin_def_effect_strength)
        h_es.addStretch()
        gl_tool.addLayout(h_es)

        # 검은띠 너비
        h_bw = QHBoxLayout()
        h_bw.addWidget(QLabel("검은띠 너비 (W):"))
        self.spin_def_bar_w = NoScrollSpinBox()
        self.spin_def_bar_w.setRange(1, 500)
        self.spin_def_bar_w.setValue(50)
        h_bw.addWidget(self.spin_def_bar_w)
        h_bw.addStretch()
        gl_tool.addLayout(h_bw)

        # 검은띠 높이
        h_bh = QHBoxLayout()
        h_bh.addWidget(QLabel("검은띠 높이 (H):"))
        self.spin_def_bar_h = NoScrollSpinBox()
        self.spin_def_bar_h.setRange(1, 500)
        self.spin_def_bar_h.setValue(20)
        h_bh.addWidget(self.spin_def_bar_h)
        h_bh.addStretch()
        gl_tool.addLayout(h_bh)

        # YOLO 신뢰도
        h_conf = QHBoxLayout()
        h_conf.addWidget(QLabel("YOLO 감지 신뢰도 (%):"))
        self.spin_def_detect_conf = NoScrollSpinBox()
        self.spin_def_detect_conf.setRange(1, 100)
        self.spin_def_detect_conf.setValue(25)
        h_conf.addWidget(self.spin_def_detect_conf)
        h_conf.addStretch()
        gl_tool.addLayout(h_conf)

        l.addWidget(group_tool)

        # ── 자석 올가미 / 떨림 보정 ──
        group_lasso = QGroupBox("올가미 & 경로 설정")
        gl_lasso = QVBoxLayout(group_lasso)
        gl_lasso.setSpacing(10)

        self.chk_def_magnetic_lasso = QCheckBox("기본적으로 자석 올가미 활성화")
        self.chk_def_magnetic_lasso.setChecked(False)
        gl_lasso.addWidget(self.chk_def_magnetic_lasso)

        # 에지 스냅 반경
        h_snap = QHBoxLayout()
        h_snap.addWidget(QLabel("자석 스냅 반경 (px):"))
        self.spin_def_snap_radius = NoScrollSpinBox()
        self.spin_def_snap_radius.setRange(1, 50)
        self.spin_def_snap_radius.setValue(12)
        h_snap.addWidget(self.spin_def_snap_radius)
        h_snap.addStretch()
        gl_lasso.addLayout(h_snap)

        # Canny 임계값
        h_canny_lo = QHBoxLayout()
        h_canny_lo.addWidget(QLabel("Canny 하한 임계값:"))
        self.spin_def_canny_low = NoScrollSpinBox()
        self.spin_def_canny_low.setRange(1, 300)
        self.spin_def_canny_low.setValue(50)
        h_canny_lo.addWidget(self.spin_def_canny_low)
        h_canny_lo.addStretch()
        gl_lasso.addLayout(h_canny_lo)

        h_canny_hi = QHBoxLayout()
        h_canny_hi.addWidget(QLabel("Canny 상한 임계값:"))
        self.spin_def_canny_high = NoScrollSpinBox()
        self.spin_def_canny_high.setRange(1, 500)
        self.spin_def_canny_high.setValue(150)
        h_canny_hi.addWidget(self.spin_def_canny_high)
        h_canny_hi.addStretch()
        gl_lasso.addLayout(h_canny_hi)

        # 떨림 보정 계수
        h_smooth = QHBoxLayout()
        h_smooth.addWidget(QLabel("떨림 보정 계수:"))
        self.spin_def_smooth_factor = NoScrollDoubleSpinBox()
        self.spin_def_smooth_factor.setRange(0.001, 0.1)
        self.spin_def_smooth_factor.setDecimals(3)
        self.spin_def_smooth_factor.setSingleStep(0.001)
        self.spin_def_smooth_factor.setValue(0.008)
        h_smooth.addWidget(self.spin_def_smooth_factor)
        h_smooth.addStretch()
        gl_lasso.addLayout(h_smooth)

        l.addWidget(group_lasso)

        # ── 줌 / 회전 ──
        group_view = QGroupBox("뷰 설정")
        gl_view = QVBoxLayout(group_view)
        gl_view.setSpacing(10)

        h_rot = QHBoxLayout()
        h_rot.addWidget(QLabel("회전 단위 (도):"))
        self.spin_def_rotation_step = NoScrollSpinBox()
        self.spin_def_rotation_step.setRange(1, 90)
        self.spin_def_rotation_step.setValue(5)
        h_rot.addWidget(self.spin_def_rotation_step)
        h_rot.addStretch()
        gl_view.addLayout(h_rot)

        h_undo = QHBoxLayout()
        h_undo.addWidget(QLabel("Undo 스택 한도:"))
        self.spin_def_undo_limit = NoScrollSpinBox()
        self.spin_def_undo_limit.setRange(5, 100)
        self.spin_def_undo_limit.setValue(20)
        h_undo.addWidget(self.spin_def_undo_limit)
        h_undo.addStretch()
        gl_view.addLayout(h_undo)

        l.addWidget(group_view)

        # 저장 버튼
        btn_save = QPushButton("💾 설정 저장")
        btn_save.clicked.connect(self.save_all_settings)
        l.addWidget(btn_save)

        return w

    def get_editor_defaults(self) -> dict:
        """에디터 기본값 반환"""
        return {
            'tool_size': self.spin_def_tool_size.value(),
            'effect_strength': self.spin_def_effect_strength.value(),
            'bar_w': self.spin_def_bar_w.value(),
            'bar_h': self.spin_def_bar_h.value(),
            'detect_conf': self.spin_def_detect_conf.value(),
            'magnetic_lasso': self.chk_def_magnetic_lasso.isChecked(),
            'snap_radius': self.spin_def_snap_radius.value(),
            'canny_low': self.spin_def_canny_low.value(),
            'canny_high': self.spin_def_canny_high.value(),
            'smooth_factor': self.spin_def_smooth_factor.value(),
            'rotation_step': self.spin_def_rotation_step.value(),
            'undo_limit': self.spin_def_undo_limit.value(),
        }

    def _create_api_page(self):
        """API 연결 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("API 연결 설정"))

        import config
        from backends import get_backend_type, BackendType

        # 백엔드 선택
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        select_group = QGroupBox("백엔드 선택")
        sg_layout = QVBoxLayout(select_group)
        self._api_btn_group = QButtonGroup(w)
        self.radio_webui = QRadioButton("WebUI (A1111 / Forge)")
        self.radio_comfyui = QRadioButton("ComfyUI")
        self._api_btn_group.addButton(self.radio_webui)
        self._api_btn_group.addButton(self.radio_comfyui)

        current_type = get_backend_type()
        self.radio_webui.setChecked(current_type == BackendType.WEBUI)
        self.radio_comfyui.setChecked(current_type == BackendType.COMFYUI)

        sg_layout.addWidget(self.radio_webui)
        sg_layout.addWidget(self.radio_comfyui)
        l.addWidget(select_group)

        # WebUI URL
        webui_group = QGroupBox("WebUI API")
        wg_layout = QVBoxLayout(webui_group)
        h = QHBoxLayout()
        self.api_input = QLineEdit(config.WEBUI_API_URL)
        self.api_input.setPlaceholderText("http://127.0.0.1:7860")
        h.addWidget(self.api_input)
        wg_layout.addLayout(h)
        l.addWidget(webui_group)

        # ComfyUI URL + 워크플로우
        comfyui_group = QGroupBox("ComfyUI API")
        cg_layout = QVBoxLayout(comfyui_group)

        h2 = QHBoxLayout()
        self.comfyui_api_input = QLineEdit(getattr(config, 'COMFYUI_API_URL', 'http://127.0.0.1:8188'))
        self.comfyui_api_input.setPlaceholderText("http://127.0.0.1:8188")
        h2.addWidget(QLabel("URL:"))
        h2.addWidget(self.comfyui_api_input)
        cg_layout.addLayout(h2)

        h3 = QHBoxLayout()
        self.comfyui_workflow_input = QLineEdit(getattr(config, 'COMFYUI_WORKFLOW_PATH', ''))
        self.comfyui_workflow_input.setPlaceholderText("워크플로우 JSON 경로")
        btn_browse_wf = QPushButton("찾아보기")
        btn_browse_wf.clicked.connect(self._browse_comfyui_workflow)
        h3.addWidget(QLabel("워크플로우:"))
        h3.addWidget(self.comfyui_workflow_input)
        h3.addWidget(btn_browse_wf)
        cg_layout.addLayout(h3)
        cg_layout.addWidget(QLabel("※ ComfyUI 'Save (API Format)' JSON 파일"))
        l.addWidget(comfyui_group)

        # 라디오에 따라 그룹 활성화
        def on_radio_changed():
            is_comfy = self.radio_comfyui.isChecked()
            webui_group.setEnabled(not is_comfy)
            comfyui_group.setEnabled(is_comfy)

        self.radio_webui.toggled.connect(on_radio_changed)
        on_radio_changed()

        # 연결 확인 + 저장
        btn_row = QHBoxLayout()
        self.btn_connect = QPushButton("🔄 연결 확인")
        self.btn_connect.clicked.connect(self.apply_api_url)
        self.btn_save_api = QPushButton("💾 설정 저장")
        self.btn_save_api.clicked.connect(self.save_all_settings)
        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_save_api)
        l.addLayout(btn_row)

        return w

    def _browse_comfyui_workflow(self):
        """ComfyUI 워크플로우 JSON 파일 선택"""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "워크플로우 JSON 선택", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self.comfyui_workflow_input.setText(path)

    def _create_storage_page(self):
        """저장 경로 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("저장 경로 설정"))

        from config import OUTPUT_DIR, PARQUET_DIR, EVENT_PARQUET_DIR

        # 이미지 저장 경로
        group = QGroupBox("이미지 저장 경로")
        gl = QHBoxLayout(group)

        self.path_input = QLineEdit(OUTPUT_DIR)
        self.btn_browse = QPushButton("📂 폴더 변경")
        self.btn_browse.clicked.connect(self.browse_folder)

        gl.addWidget(self.path_input)
        gl.addWidget(self.btn_browse)
        l.addWidget(group)

        # 데이터 경로
        data_group = QGroupBox("데이터 경로")
        data_layout = QVBoxLayout(data_group)

        # 검색 데이터 경로
        h_parquet = QHBoxLayout()
        h_parquet.addWidget(QLabel("검색 데이터:"))
        self.parquet_dir_input = QLineEdit(PARQUET_DIR)
        h_parquet.addWidget(self.parquet_dir_input)
        btn_parquet = QPushButton("📂")
        btn_parquet.setFixedWidth(35)
        btn_parquet.clicked.connect(lambda: self._browse_data_path(self.parquet_dir_input))
        h_parquet.addWidget(btn_parquet)
        data_layout.addLayout(h_parquet)

        # 이벤트 데이터 경로
        h_event = QHBoxLayout()
        h_event.addWidget(QLabel("이벤트 데이터:"))
        self.event_parquet_dir_input = QLineEdit(EVENT_PARQUET_DIR)
        h_event.addWidget(self.event_parquet_dir_input)
        btn_event = QPushButton("📂")
        btn_event.setFixedWidth(35)
        btn_event.clicked.connect(lambda: self._browse_data_path(self.event_parquet_dir_input))
        h_event.addWidget(btn_event)
        data_layout.addLayout(h_event)

        l.addWidget(data_group)

        self.btn_save_storage = QPushButton("💾 설정 저장")
        self.btn_save_storage.clicked.connect(self.save_all_settings)
        l.addWidget(self.btn_save_storage)

        return w

    def _browse_data_path(self, line_edit: QLineEdit):
        """데이터 경로 폴더 선택"""
        folder = QFileDialog.getExistingDirectory(self, "데이터 폴더 선택")
        if folder:
            line_edit.setText(folder)

    def _create_web_page(self):
        """웹 브라우저 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("웹 브라우저 설정"))
        
        group = QGroupBox("기본 홈페이지")
        gl = QHBoxLayout(group)
        self.web_home_input = QLineEdit("https://danbooru.donmai.us/")
        gl.addWidget(self.web_home_input)
        l.addWidget(group)
        
        btn_apply = QPushButton("🌐 홈페이지 적용")
        btn_apply.clicked.connect(self._apply_web_settings)
        l.addWidget(btn_apply)
        
        self.btn_save_web = QPushButton("💾 설정 저장")
        self.btn_save_web.clicked.connect(self.save_all_settings)
        l.addWidget(self.btn_save_web)
        
        return w

    def _create_theme_page(self):
        """테마 설정 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("🎨 테마 설정"))

        from utils.theme_manager import get_theme_manager, ThemeManager
        tm = get_theme_manager()

        # UI 스타일 선택
        style_group = QGroupBox("UI 스타일")
        style_gl = QVBoxLayout(style_group)

        style_h = QHBoxLayout()
        style_h.addWidget(QLabel("UI 스타일:"))
        self.ui_style_combo = NoScrollComboBox()
        self.ui_style_combo.addItems(["Classic", "Modern (UI2)"])
        current_style = getattr(config, 'UI_STYLE', 'classic')
        self.ui_style_combo.setCurrentIndex(0 if current_style == 'classic' else 1)
        self.ui_style_combo.currentIndexChanged.connect(self._on_ui_style_changed)
        style_h.addWidget(self.ui_style_combo)
        style_h.addStretch()
        style_gl.addLayout(style_h)

        style_gl.addWidget(QLabel("※ UI 스타일 변경 시 앱을 재시작해야 적용됩니다."))
        l.addWidget(style_group)

        # 테마 선택
        group = QGroupBox("테마 선택")
        gl = QVBoxLayout(group)

        h = QHBoxLayout()
        h.addWidget(QLabel("테마:"))
        self.theme_combo = NoScrollComboBox()
        self.theme_combo.addItems(ThemeManager.available_themes())
        self.theme_combo.setCurrentText(tm.current_theme_name)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        h.addWidget(self.theme_combo)
        h.addStretch()
        gl.addLayout(h)

        gl.addWidget(QLabel("※ 테마 변경 시 즉시 적용됩니다."))
        l.addWidget(group)

        # 글꼴 설정
        font_group = QGroupBox("글꼴 설정")
        fl = QVBoxLayout(font_group)

        from widgets.font_combo import FontPreviewComboBox

        font_h = QHBoxLayout()
        font_h.addWidget(QLabel("글꼴:"))
        self.font_combo = FontPreviewComboBox()
        default_font = tm.get_font_family_name()
        self.font_combo.set_current_font(default_font)
        self.font_combo.currentTextChanged.connect(self._on_font_changed)
        font_h.addWidget(self.font_combo, stretch=1)
        fl.addLayout(font_h)

        size_h = QHBoxLayout()
        size_h.addWidget(QLabel("글꼴 크기:"))
        self.font_size_spin = NoScrollDoubleSpinBox()
        self.font_size_spin.setRange(8.0, 20.0)
        self.font_size_spin.setSingleStep(0.5)
        self.font_size_spin.setValue(tm.get_font_size_value())
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.valueChanged.connect(self._on_font_changed)
        size_h.addWidget(self.font_size_spin)
        size_h.addStretch()
        fl.addLayout(size_h)

        fl.addWidget(QLabel("※ 글꼴 변경 시 즉시 적용됩니다."))
        l.addWidget(font_group)

        btn_save = QPushButton("💾 설정 저장")
        btn_save.clicked.connect(self.save_all_settings)
        l.addWidget(btn_save)

        return w

    def _on_theme_changed(self, theme_name: str):
        """테마 변경 시 즉시 적용"""
        if self.parent_ui and hasattr(self.parent_ui, 'set_theme'):
            self.parent_ui.set_theme(theme_name)

    def _on_font_changed(self, *args):
        """글꼴 변경 시 즉시 적용"""
        font_name = self.font_combo.currentText()
        font_size = self.font_size_spin.value()
        from utils.theme_manager import get_theme_manager
        tm = get_theme_manager()
        tm.set_font(font_name, font_size)
        if self.parent_ui and hasattr(self.parent_ui, 'apply_stylesheet'):
            self.parent_ui.apply_stylesheet()

    def _on_ui_style_changed(self, index: int):
        """UI 스타일 변경 시 재시작 안내"""
        QMessageBox.information(
            self, "UI 스타일 변경",
            "UI 스타일을 변경하려면 앱을 재시작해야 합니다.\n"
            "설정을 저장한 후 앱을 다시 시작해주세요."
        )

    def apply_api_url(self):
        """API URL 적용"""
        import config
        from backends import set_backend, BackendType

        if hasattr(self, 'radio_comfyui') and self.radio_comfyui.isChecked():
            url = self.comfyui_api_input.text().strip()
            config.COMFYUI_API_URL = url
            if hasattr(self, 'comfyui_workflow_input'):
                config.COMFYUI_WORKFLOW_PATH = self.comfyui_workflow_input.text().strip()
            set_backend(BackendType.COMFYUI, url)
        else:
            url = self.api_input.text().strip()
            set_backend(BackendType.WEBUI, url)

        if self.parent_ui:
            self.parent_ui.retry_connection()

    def browse_folder(self):
        """폴더 선택 대화상자"""
        folder = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if folder:
            self.path_input.setText(folder)
            import config
            config.OUTPUT_DIR = folder

    def _apply_web_settings(self):
        """웹 설정 적용"""
        url = self.web_home_input.text().strip()
        if url and self.parent_ui and hasattr(self.parent_ui, 'web_tab'):
            self.parent_ui.web_tab.set_home_url(url)
            QMessageBox.information(self, "완료", "웹 설정이 적용되었습니다.")

    def save_all_settings(self):
        """모든 설정 저장"""
        self.apply_api_url()

        import os
        config.OUTPUT_DIR = self.path_input.text()

        # UI 스타일 저장
        if hasattr(self, 'ui_style_combo'):
            config.UI_STYLE = 'classic' if self.ui_style_combo.currentIndex() == 0 else 'modern'
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)

        # 데이터 경로 적용
        if hasattr(self, 'parquet_dir_input'):
            config.PARQUET_DIR = self.parquet_dir_input.text()
        if hasattr(self, 'event_parquet_dir_input'):
            config.EVENT_PARQUET_DIR = self.event_parquet_dir_input.text()

        # 에디터 기본값 즉시 적용
        if self.parent_ui and hasattr(self.parent_ui, 'mosaic_editor'):
            self.parent_ui.mosaic_editor.apply_defaults(self.get_editor_defaults())

        if self.parent_ui:
            self.parent_ui.save_settings()

        QMessageBox.information(self, "저장 완료", "설정이 저장 및 적용되었습니다.")

    def get_autocomplete_options(self) -> dict:
        """자동완성 옵션 반환"""
        return {
            'enabled': self.chk_autocomplete_enabled.isChecked(),
            'min_chars': self.spin_min_chars.value(),
            'max_suggestions': self.spin_max_suggestions.value(),
            'character': self.chk_ac_character.isChecked(),
            'copyright': self.chk_ac_copyright.isChecked(),
            'artist': self.chk_ac_artist.isChecked(),
            'general': self.chk_ac_general.isChecked(),
        }

    def get_cleaning_options(self) -> dict:
        """정리 옵션 반환"""
        return {
            'auto_comma': self.chk_auto_comma.isChecked(),
            'auto_space': self.chk_auto_space.isChecked(),
            'auto_escape': self.chk_auto_escape.isChecked(),
            'remove_duplicates': self.chk_remove_duplicates.isChecked(),
            'underscore_to_space': self.chk_underscore_to_space.isChecked(),
        }

    # ── 백업/복원 ──

    def _create_backup_page(self):
        """백업/복원 페이지"""
        w, l = self._create_container()
        l.addWidget(self._create_header("📦 설정 백업 / 복원"))

        # ── 프리셋 공유 섹션 ──
        preset_group = QGroupBox("프리셋 공유")
        pg_layout = QVBoxLayout(preset_group)
        pg_layout.setSpacing(8)

        pg_layout.addWidget(QLabel(
            "캐릭터 프리셋 또는 프롬프트 프리셋을\n"
            "JSON 파일로 내보내거나 가져올 수 있습니다."
        ))

        # 캐릭터 프리셋
        char_row = QHBoxLayout()
        btn_export_char = QPushButton("📤 캐릭터 프리셋 내보내기")
        btn_export_char.setFixedHeight(36)
        btn_export_char.setStyleSheet(
            "background-color: #5865F2; color: white; "
            "font-weight: bold; border-radius: 5px; font-size: 12px;"
        )
        btn_export_char.clicked.connect(self._export_character_presets)
        char_row.addWidget(btn_export_char)

        btn_import_char = QPushButton("📥 캐릭터 프리셋 가져오기")
        btn_import_char.setFixedHeight(36)
        btn_import_char.setStyleSheet(
            "background-color: #27ae60; color: white; "
            "font-weight: bold; border-radius: 5px; font-size: 12px;"
        )
        btn_import_char.clicked.connect(self._import_character_presets)
        char_row.addWidget(btn_import_char)
        pg_layout.addLayout(char_row)

        # 프롬프트 프리셋
        prompt_row = QHBoxLayout()
        btn_export_prompt = QPushButton("📤 프롬프트 프리셋 내보내기")
        btn_export_prompt.setFixedHeight(36)
        btn_export_prompt.setStyleSheet(
            "background-color: #5865F2; color: white; "
            "font-weight: bold; border-radius: 5px; font-size: 12px;"
        )
        btn_export_prompt.clicked.connect(self._export_prompt_presets)
        prompt_row.addWidget(btn_export_prompt)

        btn_import_prompt = QPushButton("📥 프롬프트 프리셋 가져오기")
        btn_import_prompt.setFixedHeight(36)
        btn_import_prompt.setStyleSheet(
            "background-color: #27ae60; color: white; "
            "font-weight: bold; border-radius: 5px; font-size: 12px;"
        )
        btn_import_prompt.clicked.connect(self._import_prompt_presets)
        prompt_row.addWidget(btn_import_prompt)
        pg_layout.addLayout(prompt_row)

        l.addWidget(preset_group)

        # ── ZIP 백업 섹션 ──
        group = QGroupBox("내보내기 / 가져오기")
        gl = QVBoxLayout(group)
        gl.setSpacing(10)

        gl.addWidget(QLabel(
            "앱 설정, 프리셋, 즐겨찾기 태그, 단축키 등을\n"
            "ZIP 파일로 백업하고 복원할 수 있습니다."
        ))

        btn_export = QPushButton("📤 설정 내보내기 (ZIP)")
        btn_export.setFixedHeight(40)
        btn_export.setStyleSheet(
            "background-color: #5865F2; color: white; "
            "font-weight: bold; border-radius: 5px; font-size: 13px;"
        )
        btn_export.clicked.connect(self._export_settings)
        gl.addWidget(btn_export)

        btn_import = QPushButton("📥 설정 가져오기 (ZIP)")
        btn_import.setFixedHeight(40)
        btn_import.setStyleSheet(
            "background-color: #27ae60; color: white; "
            "font-weight: bold; border-radius: 5px; font-size: 13px;"
        )
        btn_import.clicked.connect(self._import_settings)
        gl.addWidget(btn_import)

        l.addWidget(group)
        return w

    def _export_settings(self):
        """설정 파일들을 ZIP으로 내보내기"""
        import zipfile
        import os

        base = os.path.dirname(os.path.dirname(__file__))
        targets = [
            'prompt_settings.json',
            'prompt_presets.json',
            'favorite_tags.json',
            'favorites.json',
            'event_gen_settings.json',
            'search_tab_settings.json',
        ]
        # shortcuts
        shortcut_file = os.path.join(base, 'shortcuts.json')
        if os.path.exists(shortcut_file):
            targets.append('shortcuts.json')

        save_path, _ = QFileDialog.getSaveFileName(
            self, "설정 내보내기", "ai_studio_backup.zip", "ZIP (*.zip)"
        )
        if not save_path:
            return

        try:
            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fname in targets:
                    fpath = os.path.join(base, fname)
                    if os.path.exists(fpath):
                        zf.write(fpath, fname)
                # queue_presets 폴더
                qp_dir = os.path.join(base, 'queue_presets')
                if os.path.isdir(qp_dir):
                    for qf in os.listdir(qp_dir):
                        if qf.endswith('.json'):
                            zf.write(os.path.join(qp_dir, qf), f'queue_presets/{qf}')
            QMessageBox.information(self, "내보내기 완료", f"설정이 저장되었습니다:\n{save_path}")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"내보내기 실패: {e}")

    def _import_settings(self):
        """ZIP에서 설정 파일 복원"""
        import zipfile
        import os

        zip_path, _ = QFileDialog.getOpenFileName(
            self, "설정 가져오기", "", "ZIP (*.zip)"
        )
        if not zip_path:
            return

        reply = QMessageBox.question(
            self, "설정 복원",
            "현재 설정이 백업 파일의 내용으로 덮어씌워집니다.\n계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        base = os.path.dirname(os.path.dirname(__file__))
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    target = os.path.join(base, info.filename)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(info) as src, open(target, 'wb') as dst:
                        dst.write(src.read())
            QMessageBox.information(
                self, "복원 완료",
                "설정이 복원되었습니다.\n일부 설정은 앱을 재시작해야 적용됩니다."
            )
        except Exception as e:
            QMessageBox.warning(self, "오류", f"가져오기 실패: {e}")

    # ── 프리셋 공유 ──

    def _export_character_presets(self):
        """캐릭터 프리셋 내보내기"""
        import json
        import os
        base = os.path.dirname(os.path.dirname(__file__))
        src = os.path.join(base, 'character_presets.json')
        if not os.path.exists(src):
            QMessageBox.warning(self, "알림", "캐릭터 프리셋 파일이 없습니다.")
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "캐릭터 프리셋 내보내기", "character_presets.json", "JSON (*.json)"
        )
        if save_path:
            import shutil
            shutil.copy2(src, save_path)
            QMessageBox.information(self, "완료", f"캐릭터 프리셋이 저장되었습니다:\n{save_path}")

    def _import_character_presets(self):
        """캐릭터 프리셋 가져오기"""
        import json
        import os
        path, _ = QFileDialog.getOpenFileName(self, "캐릭터 프리셋 가져오기", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            if not isinstance(new_data, dict):
                QMessageBox.warning(self, "오류", "올바른 프리셋 파일이 아닙니다.")
                return

            base = os.path.dirname(os.path.dirname(__file__))
            target = os.path.join(base, 'character_presets.json')

            # 기존 파일이 있으면 병합 옵션 제공
            if os.path.exists(target):
                reply = QMessageBox.question(
                    self, "가져오기 방식",
                    f"새 프리셋 {len(new_data)}개를 발견했습니다.\n\n"
                    "Yes = 기존에 병합 (중복 시 새 것으로 교체)\n"
                    "No = 전체 덮어쓰기",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                if reply == QMessageBox.StandardButton.Yes:
                    # 병합
                    with open(target, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    existing.update(new_data)
                    new_data = existing

            with open(target, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "완료", f"캐릭터 프리셋을 가져왔습니다. ({len(new_data)}개)")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"가져오기 실패: {e}")

    def _export_prompt_presets(self):
        """프롬프트 프리셋 내보내기"""
        import json
        import os
        base = os.path.dirname(os.path.dirname(__file__))
        src = os.path.join(base, 'prompt_presets.json')
        if not os.path.exists(src):
            QMessageBox.warning(self, "알림", "프롬프트 프리셋 파일이 없습니다.")
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "프롬프트 프리셋 내보내기", "prompt_presets.json", "JSON (*.json)"
        )
        if save_path:
            import shutil
            shutil.copy2(src, save_path)
            QMessageBox.information(self, "완료", f"프롬프트 프리셋이 저장되었습니다:\n{save_path}")

    def _import_prompt_presets(self):
        """프롬프트 프리셋 가져오기"""
        import json
        import os
        path, _ = QFileDialog.getOpenFileName(self, "프롬프트 프리셋 가져오기", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            if not isinstance(new_data, dict):
                QMessageBox.warning(self, "오류", "올바른 프리셋 파일이 아닙니다.")
                return

            base = os.path.dirname(os.path.dirname(__file__))
            target = os.path.join(base, 'prompt_presets.json')

            # 기존 파일이 있으면 병합 옵션 제공
            if os.path.exists(target):
                reply = QMessageBox.question(
                    self, "가져오기 방식",
                    f"새 프리셋 {len(new_data)}개를 발견했습니다.\n\n"
                    "Yes = 기존에 병합 (중복 시 새 것으로 교체)\n"
                    "No = 전체 덮어쓰기",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                if reply == QMessageBox.StandardButton.Yes:
                    # 병합
                    with open(target, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    existing.update(new_data)
                    new_data = existing

            with open(target, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "완료", f"프롬프트 프리셋을 가져왔습니다. ({len(new_data)}개)")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"가져오기 실패: {e}")
# ui/generator_ui_v2.py
"""
모던 UI 레이아웃 (NAIS-style)
setup_modern_ui(self) 함수가 UISetupMixin._setup_ui()에서 호출됨.
classic UI와 동일한 self.* 위젯 속성을 모두 생성하되 레이아웃만 다르게 구성.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QGroupBox, QCheckBox, QTabWidget,
    QSplitter, QScrollArea, QListWidget, QMenu, QMessageBox,
    QSizePolicy, QListWidgetItem, QFrame, QStackedWidget,
    QSlider
)
from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QPixmap

from widgets.common_widgets import (
    NoScrollComboBox, AutomationWidget, ResolutionItemWidget, FlowLayout
)
from widgets.sliders import NumericSlider
from widgets.favorite_tags import FavoriteTagsBar
from widgets.character_preset_dialog import CharacterPresetDialog
from widgets.tag_input import TagInputWidget
from widgets.lora_panel import LoraActivePanel
from widgets.api_status_button import ApiStatusButton
from config import OUTPUT_DIR
from utils.theme_manager import get_color


# ---------------------------------------------------------------------------
# 헬퍼: 접이식 섹션 위젯
# ---------------------------------------------------------------------------
class _CollapsibleSection(QWidget):
    """접이식(collapsible) 카드 위젯"""

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        self._expanded = expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        # 헤더 버튼
        arrow = "▼" if expanded else "▶"
        self.toggle_btn = QPushButton(f"  {arrow}  {title}")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setFixedHeight(36)
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_secondary')};
                color: {get_color('text_secondary')};
                border: none;
                border-radius: 12px;
                text-align: left;
                font-weight: bold;
                font-size: 12px;
                padding-left: 12px;
            }}
            QPushButton:checked {{
                background-color: {get_color('bg_tertiary')};
                color: {get_color('text_primary')};
                border-left: 3px solid {get_color('accent')};
                border-radius: 0px 12px 12px 0px;
            }}
            QPushButton:hover {{
                background-color: {get_color('bg_button_hover')};
            }}
        """)
        layout.addWidget(self.toggle_btn)

        # 콘텐츠 컨테이너 (카드 스타일)
        self.content = QWidget()
        self.content.setStyleSheet(f"""
            QWidget {{
                background-color: {get_color('bg_secondary')};
                border-radius: 0 0 12px 12px;
            }}
        """)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 8, 12, 10)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)
        layout.addWidget(self.content)

        self.toggle_btn.toggled.connect(self._on_toggle)

    def _on_toggle(self, checked: bool):
        self._expanded = checked
        self.content.setVisible(checked)
        title_text = self.toggle_btn.text()
        if checked:
            self.toggle_btn.setText(title_text.replace("▶", "▼", 1))
        else:
            self.toggle_btn.setText(title_text.replace("▼", "▶", 1))

    def expand(self):
        """프로그래밍 방식으로 펼치기"""
        if not self._expanded:
            self.toggle_btn.setChecked(True)

    def collapse(self):
        """프로그래밍 방식으로 접기"""
        if self._expanded:
            self.toggle_btn.setChecked(False)

    def addWidget(self, w):
        self.content_layout.addWidget(w)

    def addLayout(self, lay):
        self.content_layout.addLayout(lay)


# ---------------------------------------------------------------------------
# 헬퍼: 섹션 라벨
# ---------------------------------------------------------------------------
def _section_label(text: str, color: str | None = None, size: int = 11) -> QLabel:
    """얇은 섹션 제목 라벨"""
    lbl = QLabel(text)
    c = color or get_color('text_muted')
    lbl.setStyleSheet(
        f"color: {c}; font-size: {size}px; font-weight: bold; "
        f"padding: 2px 0px; background: transparent;"
    )
    return lbl


def _card_widget() -> QWidget:
    """미묘한 배경을 가진 카드 컨테이너"""
    w = QWidget()
    w.setStyleSheet(f"""
        QWidget {{
            background-color: {get_color('bg_secondary')};
            border-radius: 14px;
        }}
    """)
    return w


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------
def setup_modern_ui(self):
    """
    모던 UI 구성 함수.
    self는 GeneratorMainUI 인스턴스.
    classic UI의 _setup_ui_classic()이 생성하는 모든 self.* 위젯을
    동일하게 생성하되, 레이아웃만 NAIS 스타일로 재구성.
    """
    self.setWindowTitle("AI Studio - Pro")
    self.setGeometry(100, 100, 1600, 950)

    central_widget = QWidget()
    self.setCentralWidget(central_widget)

    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # ── 상단 영역 ──
    upper_area = QWidget()
    upper_layout = QHBoxLayout(upper_area)
    upper_layout.setContentsMargins(0, 0, 0, 0)
    upper_layout.setSpacing(0)

    # ── 왼쪽 패널 (모던) ──
    self.left_panel_scroll = _build_modern_left_panel(self)

    # ── 중앙 탭 (기존 로직 재사용 + 모던 스타일 오버라이드) ──
    self.center_tabs = self._create_center_tabs()
    _apply_modern_center_styling(self)

    # ── 에디터 도구 패널 (center_tabs 이후에 생성) ──
    self.editor_tools_scroll = self._create_editor_tools_panel()

    # ── 왼쪽 스택 ──
    self.left_stack = QStackedWidget()
    self.left_stack.setFixedWidth(450)
    self.left_stack.addWidget(self.left_panel_scroll)       # 0: 생성 설정
    self.left_stack.addWidget(self.editor_tools_scroll)     # 1: 에디터 도구
    self.left_stack.addWidget(self.i2i_tab.left_scroll)     # 2: I2I 설정
    self.left_stack.addWidget(self.inpaint_tab.left_scroll) # 3: Inpaint 설정

    # ── 히스토리 패널 (모던 스타일) ──
    self.history_panel = _build_modern_history_panel(self)
    self.history_panel.setFixedWidth(240)

    upper_layout.addWidget(self.left_stack)
    upper_layout.addWidget(self.center_tabs)
    upper_layout.addWidget(self.history_panel)

    main_layout.addWidget(upper_area, 1)

    # ── 하단 컨테이너 (대기열 + 상태바) ──
    self._bottom_container = QWidget()
    self._bottom_layout = QVBoxLayout(self._bottom_container)
    self._bottom_layout.setContentsMargins(0, 0, 0, 0)
    self._bottom_layout.setSpacing(0)
    self._bottom_container.setFixedHeight(230)
    main_layout.addWidget(self._bottom_container, 0)

    # 상태 메시지 라벨
    self.status_message_label = QLabel("")
    self.status_message_label.setObjectName("statusMessageLabel")
    self.status_message_label.setFixedHeight(24)
    self.status_message_label.setStyleSheet(f"""
        #statusMessageLabel {{
            background-color: {get_color('bg_status_bar')};
            color: #8BC34A;
            padding-left: 10px;
            font-size: 10pt;
            border-top: 1px solid {get_color('border')};
        }}
    """)

    # VRAM 라벨
    self.vram_label = QLabel("")
    self.vram_label.setFixedHeight(24)
    self.vram_label.setStyleSheet(
        f"color: #44FF44; font-size: 10px; padding-right: 10px; "
        f"background: transparent;"
    )


# ===========================================================================
# 왼쪽 패널 구축 (모던 레이아웃)
# ===========================================================================
def _build_modern_left_panel(self) -> QWidget:
    """모던 스타일 왼쪽 패널 생성 — 3단 구조 (헤더/스크롤/하단바)"""

    # ─── 외부 컨테이너 ───
    outer = QWidget()
    outer.setMaximumWidth(450)
    outer_layout = QVBoxLayout(outer)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    # ─── generator_panel (다른 mixin에서 참조) ───
    self.generator_panel = QWidget()

    # ==================================================================
    # PART 1: 고정 헤더 바 (44px)
    # ==================================================================
    header_bar = QWidget()
    header_bar.setFixedHeight(48)
    header_bar.setObjectName("modernLeftHeader")
    header_bar.setStyleSheet(f"""
        #modernLeftHeader {{
            background-color: {get_color('bg_secondary')};
            border-bottom: 2px solid {get_color('border')};
        }}
    """)
    header_layout = QHBoxLayout(header_bar)
    header_layout.setContentsMargins(14, 0, 14, 0)

    _header_title = QLabel("기본")
    _header_title.setStyleSheet(
        f"font-weight: bold; font-size: 15px; "
        f"color: {get_color('text_primary')}; background: transparent;"
    )
    header_layout.addWidget(_header_title)

    _btn_folder = QPushButton("📂")
    _btn_folder.setFixedSize(28, 28)
    _btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
    _btn_folder.setToolTip("프리셋 불러오기")
    _btn_folder.setStyleSheet(f"""
        QPushButton {{ background: transparent; border: none; font-size: 14px; }}
        QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; border-radius: 14px; }}
    """)
    _btn_folder.clicked.connect(self._load_prompt_preset)
    header_layout.addWidget(_btn_folder)

    header_layout.addStretch()

    # 토큰 카운터 (금색, 헤더 우측)
    self.token_count_label = QLabel("🪙 0")
    self.token_count_label.setStyleSheet(
        "color: #E8A822; font-size: 13px; font-weight: bold; "
        "padding: 0 4px; background: transparent;"
    )
    self.token_count_label.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    header_layout.addWidget(self.token_count_label)

    outer_layout.addWidget(header_bar)

    # ==================================================================
    # PART 2: 스크롤 영역 (확장)
    # ==================================================================
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
    self._left_scroll_area = scroll  # 스크롤바 접근용

    container = QWidget()
    container.setMaximumWidth(440)
    root = QVBoxLayout(container)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(12)  # 넉넉한 간격 (레퍼런스)

    # ========== API 상태 버튼 ==========
    self.btn_api_manager = ApiStatusButton()
    self.btn_api_manager.clicked.connect(self._show_api_manager_popup)
    root.addWidget(self.btn_api_manager)

    # ====================================================================
    # 프롬프트 카드 — 배경 카드로 묶어 클래식과 차별화
    # ====================================================================
    prompt_card = QWidget()
    prompt_card.setObjectName("promptCard")
    prompt_card.setStyleSheet(f"""
        #promptCard {{
            background-color: {get_color('bg_secondary')};
            border-radius: 14px;
            border: 1px solid {get_color('border')};
        }}
    """)
    pc_layout = QVBoxLayout(prompt_card)
    pc_layout.setContentsMargins(12, 10, 12, 10)
    pc_layout.setSpacing(8)

    # ── 기본 프롬프트 (prefix) ──
    pc_layout.addWidget(_section_label("기본 프롬프트"))
    self.prefix_prompt_text = TagInputWidget()
    self.prefix_prompt_text.setMinimumHeight(60)
    self.prefix_prompt_text.setPlaceholderText("선행 고정 프롬프트...")
    pc_layout.addWidget(self.prefix_prompt_text)

    # 토글 버튼 (숨김 — 다른 mixin에서 참조하므로 생성 필수)
    self.prefix_toggle_button = QPushButton("▼ 선행 고정 프롬프트")
    self.prefix_toggle_button.setCheckable(True)
    self.prefix_toggle_button.setChecked(True)
    self.prefix_toggle_button.hide()
    self.prefix_toggle_button.toggled.connect(self._on_prefix_toggle)

    # ── 추가 프롬프트 (main) ──
    pc_layout.addWidget(_section_label("추가 프롬프트"))
    self.main_prompt_text = TagInputWidget()
    self.main_prompt_text.setMinimumHeight(80)
    self.main_prompt_text.setPlaceholderText("메인 프롬프트...")
    pc_layout.addWidget(self.main_prompt_text)

    # ── 세부 프롬프트 (total_prompt_display) ──
    pc_layout.addWidget(_section_label("세부 프롬프트"))
    self.total_prompt_display = QTextEdit()
    self.total_prompt_display.setReadOnly(False)
    self.total_prompt_display.setMinimumHeight(60)
    self.total_prompt_display.document().contentsChanged.connect(
        self._adjust_total_prompt_height
    )
    self.total_prompt_display.textChanged.connect(self._update_token_count)
    pc_layout.addWidget(self.total_prompt_display)

    # ── 네거티브 프롬프트 (카드 안) ──
    pc_layout.addWidget(_section_label("네거티브 프롬프트", color="#e74c3c"))
    self.neg_prompt_text = TagInputWidget()
    self.neg_prompt_text.setMinimumHeight(60)
    self.neg_prompt_text.setPlaceholderText("부정 프롬프트...")
    pc_layout.addWidget(self.neg_prompt_text)

    root.addWidget(prompt_card)  # 프롬프트 카드를 root에 추가

    # 숨김 토글 버튼 (다른 mixin 참조)
    self.neg_toggle_button = QPushButton("▼ 부정 프롬프트 (Negative)")
    self.neg_toggle_button.setCheckable(True)
    self.neg_toggle_button.setChecked(True)
    self.neg_toggle_button.hide()
    self.neg_toggle_button.toggled.connect(self._on_neg_toggle)

    # ====================================================================
    # 접이식 "추가 옵션" — 후행/제외/즐겨찾기/LoRA (메인에서 이동)
    # ====================================================================
    extra_section = _CollapsibleSection("추가 옵션")

    # 즐겨찾기 태그 바
    self.fav_tags_bar = FavoriteTagsBar()
    self.fav_tags_bar.tag_insert_requested.connect(self._insert_fav_tag)
    extra_section.addWidget(self.fav_tags_bar)

    # LoRA + 가중치 편집 버튼 행
    lora_row = QHBoxLayout()
    lora_row.setSpacing(4)

    self.btn_tag_weights = QPushButton("⚖️ 가중치")
    self.btn_tag_weights.setFixedHeight(32)
    self.btn_tag_weights.setStyleSheet(
        "QPushButton { background-color: #2C6B2F; color: white; border-radius: 16px; "
        "font-size: 12px; font-weight: bold; padding: 4px 14px; border: none; }"
        "QPushButton:hover { background-color: #38874A; }"
    )
    self.btn_tag_weights.setToolTip("메인 프롬프트 태그 가중치 슬라이더 편집")
    self.btn_tag_weights.clicked.connect(self._open_tag_weight_editor)

    self.btn_lora_manager = QPushButton("📦 LoRA")
    self.btn_lora_manager.setFixedHeight(32)
    self.btn_lora_manager.setStyleSheet(
        "QPushButton { background-color: #8A5CF5; color: white; border-radius: 16px; "
        "font-size: 12px; font-weight: bold; padding: 4px 14px; border: none; }"
        "QPushButton:hover { background-color: #9B73F6; }"
    )
    self.btn_lora_manager.setToolTip("LoRA 브라우저 열기")
    self.btn_lora_manager.clicked.connect(self._open_lora_manager)

    lora_row.addWidget(self.btn_tag_weights)
    lora_row.addWidget(self.btn_lora_manager)
    extra_section.addLayout(lora_row)

    # LoRA 활성 목록 패널
    self.lora_active_panel = LoraActivePanel()
    extra_section.addWidget(self.lora_active_panel)

    # 후행 프롬프트
    self.suffix_prompt_text = TagInputWidget()
    self.suffix_prompt_text.setMinimumHeight(60)
    self.suffix_prompt_text.setPlaceholderText("후행 고정 프롬프트...")
    self.suffix_toggle_button = QPushButton("▼ 후행 고정 프롬프트")
    self.suffix_toggle_button.setCheckable(True)
    self.suffix_toggle_button.setChecked(True)
    self.suffix_toggle_button.hide()
    self.suffix_toggle_button.toggled.connect(self._on_suffix_toggle)
    extra_section.addWidget(_section_label("후행 프롬프트"))
    extra_section.addWidget(self.suffix_prompt_text)

    # 제외 프롬프트
    self.exclude_prompt_local_input = TagInputWidget()
    self.exclude_prompt_local_input.setMinimumHeight(60)
    self.exclude_prompt_local_input.setPlaceholderText(
        "예: arms up, __hair, hair__, __username__, ~blue hair"
    )
    self.exclude_toggle_button = QPushButton("▼ 제외 프롬프트 (Local)")
    self.exclude_toggle_button.setCheckable(True)
    self.exclude_toggle_button.setChecked(True)
    self.exclude_toggle_button.hide()
    self.exclude_toggle_button.toggled.connect(self._on_exclude_toggle)
    extra_section.addWidget(_section_label("제외 프롬프트", color="#e67e22"))
    extra_section.addWidget(self.exclude_prompt_local_input)

    root.addWidget(extra_section)

    # ====================================================================
    # 접이식 "상세 설정" 섹션 (기본 펼침)
    # ====================================================================
    detail_section = _CollapsibleSection("상세 설정", expanded=True)

    # --- 인물 수 ---
    detail_section.addWidget(_section_label("인물 수"))
    self.char_count_input = QLineEdit()
    self.char_count_input.setPlaceholderText("예: 1")
    # 모던 QSS 템플릿의 QLineEdit 스타일 적용 (inline 제거)
    detail_section.addWidget(self.char_count_input)

    # --- 캐릭터 ---
    char_header = QHBoxLayout()
    char_header.addWidget(_section_label("캐릭터"))
    char_header.addStretch()

    self.chk_auto_char_features = QCheckBox("특징 자동 추가")
    self.chk_auto_char_features.setStyleSheet(
        f"QCheckBox {{ color: #FFA726; font-size: 11px; font-weight: bold; "
        f"background: transparent; }}"
    )
    self.chk_auto_char_features.setToolTip(
        "자동화 중 캐릭터 불러올 때 특징 태그 자동 삽입"
    )
    char_header.addWidget(self.chk_auto_char_features)

    self.combo_char_feature_mode = NoScrollComboBox()
    self.combo_char_feature_mode.addItems(["핵심만", "핵심+의상"])
    self.combo_char_feature_mode.setFixedSize(90, 24)
    self.combo_char_feature_mode.setStyleSheet(
        f"QComboBox {{ background-color: {get_color('bg_tertiary')}; "
        f"color: {get_color('text_primary')}; border: none; "
        f"border-radius: 12px; font-size: 11px; padding: 2px 8px; }}"
    )
    self.combo_char_feature_mode.setToolTip("핵심만: 눈색/머리색 등\n핵심+의상: 의상/소품 포함")
    char_header.addWidget(self.combo_char_feature_mode)

    self.btn_char_preset = QPushButton("특징 프리셋")
    self.btn_char_preset.setFixedHeight(28)
    self.btn_char_preset.setStyleSheet(
        f"QPushButton {{ background-color: {get_color('accent')}; color: white; "
        f"border-radius: 14px; font-weight: bold; font-size: 11px; "
        f"padding: 0 14px; border: none; }}"
        f"QPushButton:hover {{ background-color: #7289DA; }}"
    )
    self.btn_char_preset.clicked.connect(self._open_character_preset)
    char_header.addWidget(self.btn_char_preset)
    detail_section.addLayout(char_header)

    self.character_input = QLineEdit()
    # 모던 QSS 템플릿의 QLineEdit 스타일 적용 (inline 제거)
    detail_section.addWidget(self.character_input)

    # --- 작품 ---
    detail_section.addWidget(_section_label("작품 (Copyright)"))
    self.copyright_input = QLineEdit()
    # 모던 QSS 템플릿의 QLineEdit 스타일 적용 (inline 제거)
    detail_section.addWidget(self.copyright_input)

    # --- 작가 + 고정 버튼 ---
    artist_header = QHBoxLayout()
    artist_header.addWidget(_section_label("작가 (Artist)"))

    self.btn_lock_artist = QPushButton("🔒 고정")
    self.btn_lock_artist.setCheckable(True)
    self.btn_lock_artist.setFixedWidth(80)
    self.btn_lock_artist.setStyleSheet(f"""
        QPushButton {{
            border: none; border-radius: 14px;
            font-size: 11px; background-color: {get_color('bg_button')};
            color: {get_color('text_secondary')}; padding: 4px 10px;
        }}
        QPushButton:checked {{
            background-color: #d35400; color: white;
        }}
        QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
    """)
    artist_header.addStretch()
    artist_header.addWidget(self.btn_lock_artist)
    detail_section.addLayout(artist_header)

    self.artist_input = TagInputWidget()
    self.artist_input.setMinimumHeight(60)
    self.artist_input.document().contentsChanged.connect(
        self._adjust_artist_height
    )
    detail_section.addWidget(self.artist_input)

    # --- 제거 옵션 (체크박스 2줄) ---
    _chk_style = (
        f"font-weight: bold; color: {get_color('text_primary')}; font-size: 11px;"
    )

    remove_row1 = QHBoxLayout()
    remove_row1.setContentsMargins(0, 4, 0, 0)
    self.chk_remove_artist = QCheckBox("작가명 제거")
    self.chk_remove_copyright = QCheckBox("작품명 제거")
    self.chk_remove_character = QCheckBox("캐릭터 제거")
    remove_row1.addStretch()
    for chk in [self.chk_remove_artist, self.chk_remove_copyright,
                self.chk_remove_character]:
        chk.setStyleSheet(_chk_style)
        remove_row1.addWidget(chk)
    remove_row1.addStretch()
    detail_section.addLayout(remove_row1)

    remove_row2 = QHBoxLayout()
    remove_row2.setContentsMargins(0, 0, 0, 4)
    self.chk_remove_meta = QCheckBox("메타 제거")
    self.chk_remove_censorship = QCheckBox("검열 제거")
    self.chk_remove_text = QCheckBox("텍스트 제거")
    remove_row2.addStretch()
    for chk in [self.chk_remove_meta, self.chk_remove_censorship,
                self.chk_remove_text]:
        chk.setStyleSheet(_chk_style)
        remove_row2.addWidget(chk)
    remove_row2.addStretch()
    detail_section.addLayout(remove_row2)

    # --- 모델 선택 ---
    detail_section.addWidget(_section_label("모델"))
    self.model_combo = NoScrollComboBox()
    detail_section.addWidget(self.model_combo)

    # --- 샘플러 / 스케줄러 ---
    detail_section.addWidget(_section_label("샘플러 / 스케줄러"))
    self.sampler_combo = NoScrollComboBox()
    self.scheduler_combo = NoScrollComboBox()
    ss_row = QHBoxLayout()
    ss_row.setSpacing(5)
    ss_row.addWidget(self.sampler_combo)
    ss_row.addWidget(self.scheduler_combo)
    detail_section.addLayout(ss_row)

    # --- Steps, CFG (슬라이더) ---
    self.steps_input, steps_container = self._create_param_slider(
        None, "Steps", 1, 100, 25, 1
    )
    detail_section.addWidget(steps_container)

    self.cfg_input, cfg_container = self._create_param_slider(
        None, "CFG", 1, 20, 7, 0.5
    )
    detail_section.addWidget(cfg_container)

    # --- Seed ---
    detail_section.addWidget(_section_label("Seed"))
    seed_row = QHBoxLayout()
    self.seed_input = QLineEdit("-1")
    btn_seed = QPushButton("🎲")
    btn_seed.setFixedSize(36, 36)
    btn_seed.clicked.connect(lambda: self.seed_input.setText("-1"))
    seed_row.addWidget(self.seed_input)
    seed_row.addWidget(btn_seed)
    detail_section.addLayout(seed_row)

    # --- 해상도 ---
    detail_section.addWidget(_section_label("해상도"))
    res_row = QHBoxLayout()
    self.width_input = QLineEdit("1024")
    self.height_input = QLineEdit("1024")
    btn_swap_res = QPushButton("↔")
    btn_swap_res.setFixedSize(38, 36)
    btn_swap_res.setToolTip("W ↔ H 교환")
    btn_swap_res.setStyleSheet(
        f"QPushButton {{ background-color: {get_color('accent')}; color: white; border: none; "
        f"border-radius: 12px; font-size: 18px; font-weight: bold; "
        f"padding: 0px; }}"
        f"QPushButton:hover {{ background-color: #7289DA; }}"
    )
    btn_swap_res.clicked.connect(self._swap_resolution)
    res_row.addWidget(self.width_input)
    res_row.addWidget(btn_swap_res)
    res_row.addWidget(self.height_input)
    detail_section.addLayout(res_row)

    # --- 해상도 프리셋 버튼 ---
    from PyQt6.QtWidgets import QInputDialog
    self._DEFAULT_RES_PRESETS = [
        ("512²", 512, 512), ("512x768", 512, 768), ("768x512", 768, 512),
        ("1024²", 1024, 1024), ("832x1216", 832, 1216), ("1216x832", 1216, 832),
    ]
    self._res_presets = [list(p) for p in self._DEFAULT_RES_PRESETS]
    self._res_preset_btns: list[QPushButton] = []

    res_preset_row = QHBoxLayout()
    res_preset_row.setSpacing(3)
    res_preset_row.setContentsMargins(0, 0, 0, 0)
    _res_btn_style = (
        f"QPushButton {{ background-color: {get_color('bg_button')}; "
        f"color: {get_color('text_secondary')}; border: none; "
        f"border-radius: 12px; padding: 4px 8px; font-size: 10px; }}"
        f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
    )
    for i, (_label, _w, _h) in enumerate(self._res_presets):
        _btn = QPushButton(_label)
        _btn.setFixedHeight(26)
        _btn.setStyleSheet(_res_btn_style)
        _btn.clicked.connect(
            lambda _, idx=i: (
                self.width_input.setText(str(self._res_presets[idx][1])),
                self.height_input.setText(str(self._res_presets[idx][2]))
            )
        )
        _btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        _btn.customContextMenuRequested.connect(
            lambda pos, idx=i, b=_btn: self._on_res_preset_context(idx, b)
        )
        self._res_preset_btns.append(_btn)
        res_preset_row.addWidget(_btn)
    detail_section.addLayout(res_preset_row)

    # 랜덤/자동 해상도
    self.random_res_check = QCheckBox("랜덤 해상도")
    detail_section.addWidget(self.random_res_check)

    self.auto_res_check = QCheckBox("자동 해상도 (Parquet H/W)")
    self.auto_res_check.setToolTip(
        "자동화 시 parquet 데이터의 image_width/image_height로 해상도 자동 설정"
    )
    detail_section.addWidget(self.auto_res_check)

    self.random_res_label = QLabel()
    detail_section.addWidget(self.random_res_label)

    # 해상도 편집기
    self.resolution_editor_container = QWidget()
    res_edit_layout = QVBoxLayout(self.resolution_editor_container)
    input_res_layout = QHBoxLayout()
    self.res_width_input = QLineEdit()
    self.res_width_input.setPlaceholderText("W")
    self.res_height_input = QLineEdit()
    self.res_height_input.setPlaceholderText("H")
    self.btn_add_res = QPushButton("+")
    input_res_layout.addWidget(QLabel("W:"))
    input_res_layout.addWidget(self.res_width_input)
    input_res_layout.addWidget(QLabel("H:"))
    input_res_layout.addWidget(self.res_height_input)
    input_res_layout.addWidget(self.btn_add_res)
    res_edit_layout.addLayout(input_res_layout)
    self.resolution_list_widget = QListWidget()
    self.resolution_list_widget.setFixedHeight(100)
    res_edit_layout.addWidget(self.resolution_list_widget)
    detail_section.addWidget(self.resolution_editor_container)
    self.resolution_editor_container.hide()

    # --- Hires.fix (모던 카드 스타일) ---
    self.hires_options_group = QGroupBox("Hires.fix")
    self.hires_options_group.setCheckable(True)
    self.hires_options_group.setChecked(False)
    self.hires_options_group.setStyleSheet(f"""
        QGroupBox {{
            background-color: {get_color('bg_secondary')};
            border: none; border-radius: 16px;
            margin-top: 8px; padding: 20px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 16px; top: 4px;
            color: {get_color('text_primary')}; font-weight: bold;
            font-size: 11pt; background: transparent;
        }}
        QGroupBox::indicator {{ width: 18px; height: 18px; }}
    """)
    hires_l = QVBoxLayout(self.hires_options_group)

    self.upscaler_combo = NoScrollComboBox()
    hires_l.addWidget(self.upscaler_combo)

    self.hires_steps_input, hires_steps_c = self._create_param_slider(
        None, "Steps", 0, 50, 0, 1
    )
    hires_l.addWidget(hires_steps_c)

    self.hires_denoising_input, hires_dn_c = self._create_param_slider(
        None, "Denoise", 0, 1, 0.4, 0.01
    )
    hires_l.addWidget(hires_dn_c)

    self.hires_scale_input, hires_sc_c = self._create_param_slider(
        None, "Scale", 1, 4, 2, 0.05
    )
    hires_l.addWidget(hires_sc_c)

    self.hires_cfg_input, hires_cfg_c = self._create_param_slider(
        None, "CFG", 0, 30, 0, 0.5
    )
    hires_l.addWidget(hires_cfg_c)

    # Hires Checkpoint
    hr_ckpt_label = QLabel("Checkpoint")
    hr_ckpt_label.setStyleSheet(
        f"color: {get_color('text_muted')}; font-size: 11px;"
    )
    hires_l.addWidget(hr_ckpt_label)
    self.hires_checkpoint_combo = NoScrollComboBox()
    hires_l.addWidget(self.hires_checkpoint_combo)

    # Hires Sampler / Scheduler
    self.hires_sampler_combo = NoScrollComboBox()
    self.hires_scheduler_combo = NoScrollComboBox()
    hires_l.addWidget(
        self._make_hbox([self.hires_sampler_combo, self.hires_scheduler_combo])
    )

    # Hires Prompt
    hr_prompt_label = QLabel("Hires Prompt")
    hr_prompt_label.setStyleSheet(
        f"color: {get_color('text_muted')}; font-size: 11px;"
    )
    hires_l.addWidget(hr_prompt_label)
    self.hires_prompt_text = QTextEdit()
    self.hires_prompt_text.setFixedHeight(50)
    self.hires_prompt_text.setPlaceholderText("비워두면 메인 프롬프트 사용")
    # 모던 QSS 템플릿의 QTextEdit 스타일 적용
    hires_l.addWidget(self.hires_prompt_text)

    # Hires Negative Prompt
    hr_neg_label = QLabel("Hires Negative")
    hr_neg_label.setStyleSheet(
        f"color: {get_color('text_muted')}; font-size: 11px;"
    )
    hires_l.addWidget(hr_neg_label)
    self.hires_neg_prompt_text = QTextEdit()
    self.hires_neg_prompt_text.setFixedHeight(50)
    self.hires_neg_prompt_text.setPlaceholderText("비워두면 메인 네거티브 사용")
    # 모던 QSS 템플릿의 QTextEdit 스타일 적용
    hires_l.addWidget(self.hires_neg_prompt_text)
    detail_section.addWidget(self.hires_options_group)

    # --- NegPiP (모던 카드 스타일) ---
    self.negpip_group = QGroupBox("NegPiP 확장")
    self.negpip_group.setCheckable(True)
    self.negpip_group.setChecked(False)
    self.negpip_group.setStyleSheet(f"""
        QGroupBox {{
            background-color: {get_color('bg_secondary')};
            border: none; border-radius: 16px;
            margin-top: 8px; padding: 20px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 16px; top: 4px;
            color: {get_color('text_primary')}; font-weight: bold;
            font-size: 11pt; background: transparent;
        }}
        QGroupBox::indicator {{ width: 18px; height: 18px; }}
    """)
    np_layout = QVBoxLayout(self.negpip_group)
    np_layout.addWidget(
        QLabel("활성화 시 (keyword:-1.0) 네거티브 가중치 문법 사용 가능")
    )
    detail_section.addWidget(self.negpip_group)

    # --- ADetailer (모던 카드 스타일) ---
    self.adetailer_group = QGroupBox("ADetailer")
    self.adetailer_group.setCheckable(True)
    self.adetailer_group.setChecked(False)
    self.adetailer_group.setStyleSheet(f"""
        QGroupBox {{
            background-color: {get_color('bg_secondary')};
            border: none; border-radius: 16px;
            margin-top: 8px; padding: 20px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 16px; top: 4px;
            color: {get_color('text_primary')}; font-weight: bold;
            font-size: 11pt; background: transparent;
        }}
        QGroupBox::indicator {{ width: 18px; height: 18px; }}
    """)
    ad_layout = QVBoxLayout(self.adetailer_group)

    self.ad_toggle_button = QPushButton("설정 보기")
    self.ad_toggle_button.setCheckable(True)
    ad_layout.addWidget(self.ad_toggle_button)

    self.ad_settings_container = QWidget()
    self.ad_settings_container.hide()
    ad_sets = QVBoxLayout(self.ad_settings_container)

    # ADetailer Slot 1
    self.ad_slot1_group, self.s1_widgets = self._create_adetailer_slot_ui(
        "Slot 1", "face_yolov8n.pt"
    )
    # ADetailer Slot 2
    self.ad_slot2_group, self.s2_widgets = self._create_adetailer_slot_ui(
        "Slot 2", "hand_yolov8n.pt"
    )

    ad_sets.addWidget(self.ad_slot1_group)
    ad_sets.addWidget(self.ad_slot2_group)
    ad_layout.addWidget(self.ad_settings_container)
    detail_section.addWidget(self.adetailer_group)

    root.addWidget(detail_section)

    # ====================================================================
    # 유틸리티 버튼 행 (셔플, A/B, 프리셋 등)
    # ====================================================================
    util_section = _CollapsibleSection("유틸리티")

    # 저장 버튼
    top_btns = QHBoxLayout()
    top_btns.setSpacing(5)
    top_btns.setContentsMargins(0, 0, 0, 0)

    self.btn_save_settings = QPushButton("💾 설정 저장")
    self.btn_save_settings.setFixedHeight(36)
    self.btn_save_settings.setStyleSheet(
        f"QPushButton {{ background-color: {get_color('accent')}; color: white; "
        f"font-weight: bold; border-radius: 18px; padding: 4px 16px; border: none; }}"
        f"QPushButton:hover {{ background-color: #7289DA; }}"
    )
    self.btn_preset_save = QPushButton("📥 프리셋 저장")
    self.btn_preset_save.setFixedHeight(36)
    self.btn_preset_save.setStyleSheet(
        "QPushButton { background-color: #2A6A3A; color: white; "
        "font-weight: bold; border-radius: 18px; padding: 4px 16px; border: none; }"
        "QPushButton:hover { background-color: #38874A; }"
    )
    self.btn_preset_save.clicked.connect(self._save_prompt_preset)

    self.btn_preset_load = QPushButton("📤 프리셋 불러오기")
    self.btn_preset_load.setFixedHeight(36)
    self.btn_preset_load.setStyleSheet(
        "QPushButton { background-color: #8A5CF5; color: white; "
        "font-weight: bold; border-radius: 18px; padding: 4px 16px; border: none; }"
        "QPushButton:hover { background-color: #9B73F6; }"
    )
    self.btn_preset_load.clicked.connect(self._load_prompt_preset)

    top_btns.addWidget(self.btn_save_settings)
    top_btns.addWidget(self.btn_preset_save)
    top_btns.addWidget(self.btn_preset_load)
    util_section.addLayout(top_btns)

    # 셔플 + A/B 비교
    self.btn_shuffle = QPushButton("🔀 태그 셔플")
    self.btn_shuffle.setFixedHeight(36)
    self.btn_shuffle.setToolTip("메인 프롬프트 태그 순서 셔플")
    self.btn_shuffle.setStyleSheet(
        f"QPushButton {{ font-size: 12px; background-color: {get_color('bg_button')}; "
        f"color: {get_color('text_primary')}; border: none; "
        f"border-radius: 18px; font-weight: bold; padding: 4px 14px; }}"
        f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
    )
    self.btn_shuffle.clicked.connect(self._shuffle_main_prompt)

    self.btn_ab_test = QPushButton("A/B 비교")
    self.btn_ab_test.setFixedHeight(36)
    self.btn_ab_test.setToolTip("A/B 프롬프트 비교 테스트")
    self.btn_ab_test.setStyleSheet(
        f"QPushButton {{ font-size: 12px; font-weight: bold; "
        f"background-color: {get_color('bg_button')}; "
        f"color: {get_color('text_primary')}; "
        f"border: none; border-radius: 18px; padding: 4px 14px; }}"
        f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
    )
    self.btn_ab_test.clicked.connect(self._open_ab_test)

    util_btns_row = QHBoxLayout()
    util_btns_row.setSpacing(5)
    util_btns_row.addWidget(self.btn_shuffle)
    util_btns_row.addWidget(self.btn_ab_test)
    util_section.addLayout(util_btns_row)

    # 자동화 토글
    self.btn_auto_toggle = QPushButton("⏹️ 자동화 모드: 꺼짐 (OFF)")
    self.btn_auto_toggle.setCheckable(True)
    self.btn_auto_toggle.setFixedHeight(40)
    self.btn_auto_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_auto_toggle.setStyleSheet(f"""
        QPushButton {{
            background-color: {get_color('bg_tertiary')};
            color: {get_color('text_secondary')};
            border: none; border-radius: 20px;
            font-weight: bold; font-size: 13px; padding: 6px 16px;
        }}
        QPushButton:checked {{
            background-color: #27ae60; color: white;
        }}
        QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
    """)
    self.btn_auto_toggle.toggled.connect(self.toggle_automation_ui)
    util_section.addWidget(self.btn_auto_toggle)

    # 자동화 설정 위젯
    self.automation_widget = AutomationWidget()
    self.automation_widget.hide()
    util_section.addWidget(self.automation_widget)

    root.addWidget(util_section)

    root.addStretch()

    # ==================================================================
    # 스크롤 → outer 배치
    # ==================================================================
    scroll.setWidget(container)
    outer_layout.addWidget(scroll, 1)   # stretch=1 → 가용 공간 차지

    # ==================================================================
    # PART 3: 고정 하단 바
    # ==================================================================
    bottom_bar = QWidget()
    bottom_bar.setObjectName("modernBottomBar")
    bottom_bar.setStyleSheet(f"""
        #modernBottomBar {{
            background-color: {get_color('bg_secondary')};
            border-top: 2px solid {get_color('border')};
        }}
    """)
    bottom_layout = QVBoxLayout(bottom_bar)
    bottom_layout.setContentsMargins(10, 10, 10, 10)
    bottom_layout.setSpacing(10)

    # ── 5개 아이콘 버튼 행 (pill 스타일) ──
    icon_row = QHBoxLayout()
    icon_row.setSpacing(6)

    _icon_btn_style = (
        f"QPushButton {{ background-color: {get_color('bg_secondary')}; "
        f"color: {get_color('text_primary')}; border: none; border-radius: 16px; "
        f"font-size: 12px; font-weight: bold; padding: 6px 10px; }}"
        f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
    )

    self.btn_bottom_i2i = QPushButton("🖼 참조")
    self.btn_bottom_i2i.setFixedHeight(32)
    self.btn_bottom_i2i.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_bottom_i2i.setStyleSheet(_icon_btn_style)
    self.btn_bottom_i2i.setToolTip("이미지 참조 (I2I) 탭으로 이동")
    self.btn_bottom_i2i.clicked.connect(
        lambda: self.center_tabs.setCurrentIndex(1) if hasattr(self, 'center_tabs') else None
    )

    self.btn_bottom_char = QPushButton("👤 캐릭터")
    self.btn_bottom_char.setFixedHeight(32)
    self.btn_bottom_char.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_bottom_char.setStyleSheet(_icon_btn_style)
    self.btn_bottom_char.setToolTip("캐릭터 프리셋 열기")
    self.btn_bottom_char.clicked.connect(
        lambda: self._open_character_preset() if hasattr(self, '_open_character_preset') else None
    )

    self.btn_bottom_shuffle = QPushButton("🎨 조각")
    self.btn_bottom_shuffle.setFixedHeight(32)
    self.btn_bottom_shuffle.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_bottom_shuffle.setStyleSheet(_icon_btn_style)
    self.btn_bottom_shuffle.setToolTip("메인 프롬프트 태그 셔플")
    self.btn_bottom_shuffle.clicked.connect(
        lambda: self._shuffle_main_prompt() if hasattr(self, '_shuffle_main_prompt') else None
    )

    self.btn_bottom_lora = QPushButton("◆ LoRA")
    self.btn_bottom_lora.setFixedHeight(32)
    self.btn_bottom_lora.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_bottom_lora.setStyleSheet(_icon_btn_style)
    self.btn_bottom_lora.setToolTip("LoRA 브라우저 열기")
    self.btn_bottom_lora.clicked.connect(
        lambda: self._open_lora_manager() if hasattr(self, '_open_lora_manager') else None
    )

    self.btn_bottom_detail = QPushButton("⚙ 상세")
    self.btn_bottom_detail.setFixedHeight(32)
    self.btn_bottom_detail.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_bottom_detail.setStyleSheet(_icon_btn_style)
    self.btn_bottom_detail.setToolTip("상세 설정 펼치기")
    self.btn_bottom_detail.clicked.connect(
        lambda: detail_section.toggle_btn.click()
    )

    icon_row.addWidget(self.btn_bottom_i2i)
    icon_row.addWidget(self.btn_bottom_char)
    icon_row.addWidget(self.btn_bottom_shuffle)
    icon_row.addWidget(self.btn_bottom_lora)
    icon_row.addWidget(self.btn_bottom_detail)
    bottom_layout.addLayout(icon_row)

    # ── 생성 버튼 행: [🖌 이미지 생성] + [-] N [+] ──
    gen_row = QHBoxLayout()
    gen_row.setSpacing(8)

    self.btn_generate = QPushButton("🖌  이미지 생성")
    self.btn_generate.setFixedHeight(48)
    self.btn_generate.setEnabled(False)
    self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_generate.setStyleSheet(f"""
        QPushButton {{
            font-size: 15px; font-weight: bold;
            background-color: #E8822A;
            color: white; border: none;
            border-radius: 24px; padding: 4px 16px;
        }}
        QPushButton:hover {{ background-color: #F09030; }}
        QPushButton:disabled {{
            background-color: {get_color('disabled_bg')};
            color: {get_color('disabled_text')};
        }}
    """)
    gen_row.addWidget(self.btn_generate, 1)

    # 배치 카운트 [-] N [+]
    self._batch_count = 1
    _batch_btn_style = (
        f"QPushButton {{ background-color: {get_color('bg_secondary')}; "
        f"color: {get_color('text_primary')}; border: none; border-radius: 14px; "
        f"font-size: 14px; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
    )

    self.btn_batch_minus = QPushButton("−")
    self.btn_batch_minus.setFixedSize(28, 28)
    self.btn_batch_minus.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_batch_minus.setStyleSheet(_batch_btn_style)
    self.btn_batch_minus.clicked.connect(lambda: self._change_batch_count(-1))

    self.batch_count_label = QLabel("1")
    self.batch_count_label.setFixedWidth(24)
    self.batch_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.batch_count_label.setStyleSheet(
        f"color: {get_color('text_primary')}; font-size: 14px; font-weight: bold;"
    )

    self.btn_batch_plus = QPushButton("+")
    self.btn_batch_plus.setFixedSize(28, 28)
    self.btn_batch_plus.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_batch_plus.setStyleSheet(_batch_btn_style)
    self.btn_batch_plus.clicked.connect(lambda: self._change_batch_count(1))

    gen_row.addWidget(self.btn_batch_minus)
    gen_row.addWidget(self.batch_count_label)
    gen_row.addWidget(self.btn_batch_plus)
    bottom_layout.addLayout(gen_row)

    # ── 숨김 위젯 (ActionsMixin 호환용) ──
    self.btn_random_prompt = QPushButton("🎲")
    self.btn_random_prompt.setEnabled(False)
    self.btn_random_prompt.hide()

    self.btn_prompt_history = QPushButton("📋")
    self.btn_prompt_history.clicked.connect(self._show_prompt_history)
    self.btn_prompt_history.hide()

    outer_layout.addWidget(bottom_bar)
    return outer


def _change_batch_count(self, delta: int):
    """배치 카운트 증감 (1~16 범위)"""
    self._batch_count = max(1, min(16, self._batch_count + delta))
    self.batch_count_label.setText(str(self._batch_count))


def _update_history_count(self):
    """히스토리 이미지 수 갱신"""
    if not hasattr(self, 'history_count_label'):
        return
    count = len(self.gallery_items) if hasattr(self, 'gallery_items') else 0
    self.history_count_label.setText(f"{count}개" if count else "")


# ===========================================================================
# Phase 4: 모던 중앙 패널 스타일링
# ===========================================================================
def _apply_modern_center_styling(self):
    """중앙 탭과 뷰어에 모던 스타일 오버라이드 적용"""

    # ── 탭바: 인라인 스타일 제거 → 모던 QSS 템플릿이 pill 스타일 적용 ──
    self.center_tabs.setStyleSheet("")

    # ── 뷰어 라벨 모던 스타일 ──
    self.viewer_label.setStyleSheet(
        f"background-color: {get_color('bg_primary')}; "
        f"border-radius: 12px; color: {get_color('text_muted')};"
    )

    # ── EXIF 디스플레이 모던 스타일 ──
    self.exif_display.setStyleSheet(f"""
        QTextEdit {{
            background-color: {get_color('bg_secondary')};
            color: {get_color('text_secondary')};
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 9pt;
        }}
    """)

    # ── 프로그레스 바 모던 스타일 ──
    self.gen_progress_bar.setStyleSheet(f"""
        QProgressBar {{
            background-color: {get_color('bg_secondary')};
            border: none;
            border-radius: 4px;
            color: {get_color('text_primary')};
            font-size: 11px;
            font-weight: bold;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {get_color('accent')}, stop:1 #7289DA);
            border-radius: 4px;
        }}
    """)

    # ── 뷰어 정보 바 (이미지 아래, 해상도/시드 표시) ──
    viewer_container = self.viewer_panel.widget(0)
    vc_layout = viewer_container.layout()

    self.viewer_info_bar = QLabel("")
    self.viewer_info_bar.setFixedHeight(26)
    self.viewer_info_bar.setAlignment(
        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
    )
    self.viewer_info_bar.setStyleSheet(
        f"background-color: {get_color('bg_secondary')}; "
        f"color: {get_color('text_muted')}; font-size: 11px; "
        f"font-weight: bold; border-radius: 6px; margin: 2px 8px;"
    )
    self.viewer_info_bar.hide()
    # viewer_label(0) 과 progress_bar 사이에 삽입
    vc_layout.insertWidget(1, self.viewer_info_bar)


# ===========================================================================
# Phase 4: 모던 히스토리 패널
# ===========================================================================
def _build_modern_history_panel(self) -> QWidget:
    """모던 스타일 히스토리 패널"""

    panel = QWidget()
    panel.setObjectName("modernHistoryPanel")
    panel.setStyleSheet(f"""
        #modernHistoryPanel {{
            background-color: {get_color('bg_primary')};
            border-left: 1px solid {get_color('border')};
        }}
    """)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # ── 헤더 ──
    header_w = QWidget()
    header_w.setObjectName("histHeader")
    header_w.setFixedHeight(44)
    header_w.setStyleSheet(
        f"#histHeader {{ background-color: {get_color('bg_secondary')}; }}"
    )
    header_layout = QHBoxLayout(header_w)
    header_layout.setContentsMargins(12, 0, 8, 0)

    title = QLabel("히스토리")
    title.setStyleSheet(
        f"font-weight: bold; color: {get_color('text_primary')}; "
        f"font-size: 13px; background: transparent;"
    )
    header_layout.addWidget(title)

    self.history_count_label = QLabel("")
    self.history_count_label.setStyleSheet(
        f"color: {get_color('text_muted')}; font-size: 11px; "
        f"background: transparent; margin-left: 4px;"
    )
    header_layout.addWidget(self.history_count_label)
    header_layout.addStretch()

    self.btn_refresh_gallery = QPushButton("🔄")
    self.btn_refresh_gallery.setFixedSize(30, 30)
    self.btn_refresh_gallery.setToolTip("목록 새로고침")
    self.btn_refresh_gallery.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_refresh_gallery.setStyleSheet(f"""
        QPushButton {{
            background: transparent; border: none;
            border-radius: 15px; font-size: 14px;
        }}
        QPushButton:hover {{
            background-color: {get_color('bg_button_hover')};
        }}
    """)
    self.btn_refresh_gallery.clicked.connect(self._on_refresh_gallery)
    header_layout.addWidget(self.btn_refresh_gallery)
    layout.addWidget(header_w)

    # ── 이전 버튼 ──
    self.btn_history_up = QPushButton("▲")
    self.btn_history_up.setFixedHeight(24)
    self.btn_history_up.clicked.connect(self.select_prev_image)
    self.btn_history_up.setStyleSheet(f"""
        QPushButton {{
            background: transparent; border: none;
            color: {get_color('text_muted')}; font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: {get_color('bg_secondary')};
            color: {get_color('text_primary')};
        }}
    """)
    layout.addWidget(self.btn_history_up)

    # ── 갤러리 스크롤 ──
    self.gallery_scroll_area = QScrollArea()
    self.gallery_scroll_area.setWidgetResizable(True)
    self.gallery_scroll_area.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    self.gallery_scroll_area.setStyleSheet(f"""
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{
            width: 4px; background: transparent;
        }}
        QScrollBar::handle:vertical {{
            background: {get_color('scrollbar_handle')};
            border-radius: 2px; min-height: 40px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            height: 0px; background: none;
        }}
    """)

    scroll_content = QWidget()
    self.gallery_layout = QVBoxLayout(scroll_content)
    self.gallery_layout.setAlignment(
        Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
    )
    self.gallery_layout.setSpacing(8)
    self.gallery_layout.setContentsMargins(8, 6, 8, 6)
    self.gallery_scroll_area.setWidget(scroll_content)

    layout.addWidget(self.gallery_scroll_area, 1)

    # ── 다음 버튼 ──
    self.btn_history_down = QPushButton("▼")
    self.btn_history_down.setFixedHeight(24)
    self.btn_history_down.clicked.connect(self.select_next_image)
    self.btn_history_down.setStyleSheet(f"""
        QPushButton {{
            background: transparent; border: none;
            color: {get_color('text_muted')}; font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: {get_color('bg_secondary')};
            color: {get_color('text_primary')};
        }}
    """)
    layout.addWidget(self.btn_history_down)

    # ── 즐겨찾기 버튼 (pill 스타일) ──
    self.btn_add_favorite = QPushButton("⭐ 즐겨찾기 추가")
    self.btn_add_favorite.setCursor(Qt.CursorShape.PointingHandCursor)
    self.btn_add_favorite.setFixedHeight(34)
    self.btn_add_favorite.setEnabled(False)
    self.btn_add_favorite.setStyleSheet(f"""
        QPushButton {{
            background-color: transparent;
            border: 1px solid #FFC107;
            color: #FFC107;
            font-weight: bold;
            font-size: 12px;
            border-radius: 17px;
            margin: 4px 8px;
        }}
        QPushButton:hover {{
            background-color: #FFC107;
            color: {get_color('bg_primary')};
        }}
        QPushButton:disabled {{
            background-color: transparent;
            border: 1px solid {get_color('border')};
            color: {get_color('disabled_text')};
        }}
    """)
    layout.addWidget(self.btn_add_favorite)

    return panel

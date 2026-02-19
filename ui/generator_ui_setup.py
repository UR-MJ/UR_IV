# ui/generator_ui_setup.py
"""
GeneratorMainUI의 UI 구성 부분 (전체)
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QGroupBox, QCheckBox, QTabWidget,
    QSplitter, QScrollArea, QListWidget, QMenu, QMessageBox,
    QSizePolicy, QListWidgetItem, QFrame, QStackedWidget
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QPixmap
from widgets.common_widgets import (
    NoScrollComboBox, AutomationWidget, ResolutionItemWidget, FlowLayout
)
from widgets.sliders import NumericSlider
from widgets.favorite_tags import FavoriteTagsBar
from widgets.character_preset_dialog import CharacterPresetDialog
from widgets.common_widgets import NoScrollComboBox, AutomationWidget, ResolutionItemWidget
from config import OUTPUT_DIR
from widgets.tag_input import TagInputWidget

class UISetupMixin:
    """UI 구성을 담당하는 Mixin 클래스"""
    
    def _setup_ui(self):
        """UI 초기 구성"""
        self.setWindowTitle("AI Studio - Pro")
        self.setGeometry(100, 100, 1600, 950)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 상단 영역 (설정 + 탭 + 히스토리)
        upper_area = QWidget()
        upper_layout = QHBoxLayout(upper_area)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(0)

        # 왼쪽 패널 (생성 설정 / 에디터 도구 전환)
        self.left_panel_scroll = self._create_left_panel()

        # 중앙 탭 (mosaic_editor 등 생성)
        self.center_tabs = self._create_center_tabs()

        # 에디터 도구 패널 (center_tabs 생성 후 mosaic_editor 참조 가능)
        self.editor_tools_scroll = self._create_editor_tools_panel()

        # 왼쪽 패널 스택 (생성 설정 / 에디터 도구 / I2I / Inpaint)
        self.left_stack = QStackedWidget()
        self.left_stack.setFixedWidth(450)
        self.left_stack.addWidget(self.left_panel_scroll)    # index 0: 생성 설정
        self.left_stack.addWidget(self.editor_tools_scroll)  # index 1: 에디터 도구
        self.left_stack.addWidget(self.i2i_tab.left_scroll)  # index 2: I2I 설정
        self.left_stack.addWidget(self.inpaint_tab.left_scroll)  # index 3: Inpaint 설정

        # 오른쪽 히스토리
        self.history_panel = self._create_history_panel()
        self.history_panel.setFixedWidth(240)

        upper_layout.addWidget(self.left_stack)
        upper_layout.addWidget(self.center_tabs)
        upper_layout.addWidget(self.history_panel)

        # 메인 스플리터 (상단 작업 영역 + 하단 대기열)
        from PyQt6.QtWidgets import QSplitter as _Splitter
        self.main_splitter = _Splitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(5)
        self.main_splitter.setStyleSheet(
            "QSplitter::handle:vertical { background: #333; border-radius: 2px; }"
        )
        self.main_splitter.addWidget(upper_area)

        # 하단 컨테이너 (대기열 + 상태바, _setup_queue에서 채움)
        self._bottom_container = QWidget()
        self._bottom_layout = QVBoxLayout(self._bottom_container)
        self._bottom_layout.setContentsMargins(0, 0, 0, 0)
        self._bottom_layout.setSpacing(0)
        self._bottom_container.setMinimumHeight(100)
        self.main_splitter.addWidget(self._bottom_container)

        main_layout.addWidget(self.main_splitter)
        self.main_splitter.setSizes([700, 230])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)

        # 상태 메시지 라벨은 _setup_queue()에서 하단 컨테이너에 추가
        self.status_message_label = QLabel("")
        self.status_message_label.setObjectName("statusMessageLabel")
        self.status_message_label.setFixedHeight(24)
        self.status_message_label.setStyleSheet("""
            #statusMessageLabel {
                background-color: #1A1A1A;
                color: #8BC34A;
                padding-left: 10px;
                font-size: 10pt;
                border-top: 1px solid #2C2C2C;
            }
        """)

    def _create_left_panel(self):
        """왼쪽 생성 패널 생성"""
        left_panel_scroll = QScrollArea()
        left_panel_scroll.setWidgetResizable(True)
        left_panel_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        left_panel_scroll.setStyleSheet("""
            QScrollArea { 
                background-color: #181818; 
                border-right: 1px solid #2A2A2A; 
                border: none; 
            }
            QScrollBar:vertical { 
                width: 10px; background: #121212; 
            }
            QScrollBar::handle:vertical { 
                background: #333; border-radius: 5px; 
            }
        """)
        
        left_container = QWidget()
        left_container.setMaximumWidth(420)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(5, 10, 5, 10)
        left_layout.setSpacing(15)
        
        self.generator_panel = self._create_generator_panel()
        left_layout.addWidget(self.generator_panel)
        left_layout.addStretch()
        
        left_panel_scroll.setWidget(left_container)
        return left_panel_scroll

    def _create_editor_tools_panel(self):
        """에디터 도구 패널 (왼쪽 패널에 표시)"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #181818;
                border-right: 1px solid #2A2A2A;
                border: none;
            }
            QScrollBar:vertical {
                width: 10px; background: #121212;
            }
            QScrollBar::handle:vertical {
                background: #333; border-radius: 5px;
            }
        """)

        # mosaic_editor의 bottom_tabs를 스크롤 영역에 배치
        scroll.setWidget(self.mosaic_editor.bottom_tabs)
        return scroll

    def _create_center_tabs(self):
        """중앙 탭 위젯 생성"""
        from tabs.browser_tab import BrowserTab
        from tabs.settings_tab import SettingsTab
        from tabs.pnginfo_tab import PngInfoTab
        from tabs.search_tab import SearchTab
        from tabs.editor_tab import MosaicEditor
        from tabs.upscale_tab import UpscaleTab
        from tabs.gallery_tab import GalleryTab
        from tabs.event_gen_tab import EventGenTab
        from tabs.xyz_plot_tab import XYZPlotTab
        from tabs.i2i_tab import Img2ImgTab
        from tabs.inpaint_tab import InpaintTab
        from tabs.backend_ui_tab import BackendUITab

        center_tabs = QTabWidget()
        center_tabs.setStyleSheet("""
            QTabWidget::pane { 
                border: none; background-color: #121212; 
            }
            QTabBar::tab { 
                background: #1E1E1E; color: #888; 
                padding: 10px 20px; 
                border-top-left-radius: 8px; 
                border-top-right-radius: 8px; 
                margin-right: 2px; font-weight: bold; 
            }
            QTabBar::tab:selected { 
                background: #2A2A2A; color: #E0E0E0; 
                border-bottom: 2px solid #5865F2; 
            }
        """)
        
        # 1. 뷰어 패널 (T2I)
        self.viewer_panel = self._create_viewer_panel()
        center_tabs.addTab(self.viewer_panel, "🖼️ T2I")
        
        # 2. I2I 탭
        self.i2i_tab = Img2ImgTab(self)
        center_tabs.addTab(self.i2i_tab, "🖼️ I2I")

        # 3. Inpaint 탭
        self.inpaint_tab = InpaintTab(self)
        center_tabs.addTab(self.inpaint_tab, "🎨 Inpaint")
        
        # 3. 이벤트 생성 탭
        self.event_gen_tab = EventGenTab(self)
        # 시그널 연결은 connect_signals에서 처리
        center_tabs.addTab(self.event_gen_tab, "🎬 이벤트 생성")
        
        # 4. 검색 탭
        self.search_tab = SearchTab(self)
        center_tabs.addTab(self.search_tab, "🔍 Search")
        
        # 5. 브라우저 탭
        self.web_tab = BrowserTab(self)
        center_tabs.addTab(self.web_tab, "🌐 Web")
        
        # 6. 편집기 탭
        self.mosaic_editor = MosaicEditor()
        center_tabs.addTab(self.mosaic_editor, "🎨 Editor")

        # 6-1. 업스케일 탭
        self.upscale_tab = UpscaleTab(self)
        center_tabs.addTab(self.upscale_tab, "🔍 Upscale")

        # 6-2. 갤러리 탭
        self.gallery_tab = GalleryTab(self)
        center_tabs.addTab(self.gallery_tab, "🖼️ Gallery")

        # 7. XYZ plot 탭
        self.xyz_plot_tab = XYZPlotTab(self)
        center_tabs.addTab(self.xyz_plot_tab, "📊 XYZ Plot")        
        
        # 8. PNG Info 탭
        self.png_info_tab = PngInfoTab()
        # 시그널 연결은 connect_signals에서 처리
        center_tabs.addTab(self.png_info_tab, "ℹ️ PNG Info")
        
        # 9. 즐겨찾기 탭
        self.fav_tab = self._create_favorites_tab()
        center_tabs.addTab(self.fav_tab, "⭐ Favorites")
        
        # 10. 백엔드 UI 탭
        self.backend_ui_tab = BackendUITab(self)
        center_tabs.addTab(self.backend_ui_tab, "🖥️ Backend UI")

        # 11. 설정 탭
        self.settings_tab = SettingsTab(self)
        center_tabs.addTab(self.settings_tab, "⚙️ Setting")
        
        # 설정 위젯 링크 (조건부 프롬프트 등)
        self.cond_prompt_check = self.settings_tab.cond_prompt_check
        self.cond_prevent_dupe_check = self.settings_tab.cond_prevent_dupe_check
        self.cond_block_editor = self.settings_tab.cond_block_editor
        
        # 검색 결과 디스플레이 링크
        self.exclude_artist_checkbox = QCheckBox() 
        self.exclude_copyright_checkbox = QCheckBox()
        
        # ★★★ 탭 전환 시그널 연결 ★★★
        center_tabs.currentChanged.connect(self._on_center_tab_changed)

        # 드래그 중 탭 헤더 호버 시 자동 탭 전환
        center_tabs.tabBar().setAcceptDrops(True)
        center_tabs.tabBar().setChangeCurrentOnDrag(True)

        return center_tabs
    
    def _create_generator_panel(self):
        """생성 패널 (왼쪽 패널 내용)"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # API 백엔드 상태 버튼 (최상단, 애니메이션)
        from widgets.api_status_button import ApiStatusButton
        self.btn_api_manager = ApiStatusButton()
        self.btn_api_manager.clicked.connect(self._show_api_manager_popup)
        layout.addWidget(self.btn_api_manager)

        # 제목
        layout.addWidget(
            QLabel("이미지 생성 설정", font=QFont("Arial", 16, QFont.Weight.Bold))
        )

        # 상단 저장 버튼
        top_btns = QHBoxLayout()
        top_btns.setSpacing(5)
        top_btns.setContentsMargins(0, 0, 0, 0)
        
        self.btn_save_settings = QPushButton("💾 설정 저장")
        self.btn_save_settings.setFixedHeight(40)
        self.btn_save_settings.setStyleSheet(
            "background-color: #5865F2; color: white; "
            "font-weight: bold; border-radius: 5px; padding: 4px;"
        )
        self.btn_preset_save = QPushButton("📥 프리셋 저장")
        self.btn_preset_save.setFixedHeight(40)
        self.btn_preset_save.setStyleSheet(
            "background-color: #2A6A3A; color: white; "
            "font-weight: bold; border-radius: 5px; padding: 4px;"
        )
        self.btn_preset_save.clicked.connect(self._save_prompt_preset)

        self.btn_preset_load = QPushButton("📤 프리셋 불러오기")
        self.btn_preset_load.setFixedHeight(40)
        self.btn_preset_load.setStyleSheet(
            "background-color: #8A5CF5; color: white; "
            "font-weight: bold; border-radius: 5px; padding: 4px;"
        )
        self.btn_preset_load.clicked.connect(self._load_prompt_preset)

        top_btns.addWidget(self.btn_save_settings)
        top_btns.addWidget(self.btn_preset_save)
        top_btns.addWidget(self.btn_preset_load)
        layout.addLayout(top_btns)

        # 프롬프트 표시창
        self.total_prompt_display = QTextEdit()
        self.total_prompt_display.setReadOnly(False)
        self.total_prompt_display.setMinimumHeight(60)
        self.total_prompt_display.document().contentsChanged.connect(
            self._adjust_total_prompt_height
        )
        self.total_prompt_display.textChanged.connect(self._update_token_count)
        self._create_group(layout, "최종 프롬프트", self.total_prompt_display)

        # 토큰 카운터
        self.token_count_label = QLabel("토큰: 0 / 75")
        self.token_count_label.setStyleSheet(
            "color: #888; font-size: 11px; font-weight: bold; padding: 0 4px;"
        )
        self.token_count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.token_count_label)

        # 생성 버튼 그룹
        gen_btns = QHBoxLayout()
        gen_btns.setSpacing(5)
        gen_btns.setContentsMargins(0, 0, 0, 0)
        
        self.btn_random_prompt = QPushButton("🎲 랜덤 프롬프트")
        self.btn_random_prompt.setFixedHeight(45)
        self.btn_random_prompt.setEnabled(False)
        
        self.btn_generate = QPushButton("✨ 이미지 생성")
        self.btn_generate.setFixedHeight(45)
        self.btn_generate.setEnabled(False)
        self.btn_generate.setStyleSheet(
            "font-size: 15px; font-weight: bold; "
            "background-color: #4A90E2; color: white; "
            "border-radius: 5px; padding: 4px;"
        )
        
        self.btn_prompt_history = QPushButton("📋")
        self.btn_prompt_history.setFixedSize(45, 45)
        self.btn_prompt_history.setToolTip("최근 프롬프트 히스토리")
        self.btn_prompt_history.setStyleSheet(
            "font-size: 16px; background-color: #333; color: #DDD; "
            "border: 1px solid #555; border-radius: 5px;"
        )
        self.btn_prompt_history.clicked.connect(self._show_prompt_history)

        gen_btns.addWidget(self.btn_random_prompt, 1)
        gen_btns.addWidget(self.btn_prompt_history)
        gen_btns.addWidget(self.btn_generate, 1)
        layout.addLayout(gen_btns)

        # 자동화 토글
        self.btn_auto_toggle = QPushButton("⏹️ 자동화 모드: 꺼짐 (OFF)")
        self.btn_auto_toggle.setCheckable(True)
        self.btn_auto_toggle.setFixedHeight(45)
        self.btn_auto_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_toggle.setStyleSheet("""
            QPushButton { 
                background-color: #252525; color: #AAA; 
                border: 1px solid #444; border-radius: 5px; 
                font-weight: bold; font-size: 13px; padding: 4px; 
            }
            QPushButton:checked { 
                background-color: #27ae60; color: white; 
                border: 1px solid #2ecc71; 
            }
            QPushButton:hover { border: 1px solid #666; }
        """)
        self.btn_auto_toggle.toggled.connect(self.toggle_automation_ui)
        layout.addWidget(self.btn_auto_toggle)

        # 자동화 설정 위젯
        self.automation_widget = AutomationWidget()
        self.automation_widget.hide()
        layout.addWidget(self.automation_widget)

        # 셔플 + A/B 비교 버튼 행 (자동화 아래)
        self.btn_shuffle = QPushButton("🔀 태그 셔플")
        self.btn_shuffle.setFixedHeight(36)
        self.btn_shuffle.setToolTip("메인 프롬프트 태그 순서 셔플")
        self.btn_shuffle.setStyleSheet(
            "font-size: 12px; background-color: #333; color: #DDD; "
            "border: 1px solid #555; border-radius: 5px; font-weight: bold;"
        )
        self.btn_shuffle.clicked.connect(self._shuffle_main_prompt)

        self.btn_ab_test = QPushButton("A/B 비교")
        self.btn_ab_test.setFixedHeight(36)
        self.btn_ab_test.setToolTip("A/B 프롬프트 비교 테스트")
        self.btn_ab_test.setStyleSheet(
            "font-size: 12px; font-weight: bold; background-color: #333; color: #DDD; "
            "border: 1px solid #555; border-radius: 5px;"
        )
        self.btn_ab_test.clicked.connect(self._open_ab_test)

        util_btns = QHBoxLayout()
        util_btns.setSpacing(5)
        util_btns.setContentsMargins(0, 0, 0, 0)
        util_btns.addWidget(self.btn_shuffle)
        util_btns.addWidget(self.btn_ab_test)
        layout.addLayout(util_btns)

        # 제거 옵션 버튼
        remove_opts_layout = QHBoxLayout()
        remove_opts_layout.setContentsMargins(0, 5, 0, 0)

        self.chk_remove_artist = QCheckBox("작가명 제거")
        self.chk_remove_copyright = QCheckBox("작품명 제거")
        self.chk_remove_character = QCheckBox("캐릭터 제거")
        self.chk_remove_meta = QCheckBox("메타 제거")

        for chk in [self.chk_remove_artist, self.chk_remove_copyright,
                    self.chk_remove_character, self.chk_remove_meta]:
            chk.setStyleSheet("font-weight: bold; color: #DDD;")
            remove_opts_layout.addWidget(chk)
        remove_opts_layout.addStretch()
        layout.addLayout(remove_opts_layout)

        # 제거 옵션 2번째 줄
        remove_opts_layout2 = QHBoxLayout()
        remove_opts_layout2.setContentsMargins(0, 0, 0, 5)

        self.chk_remove_censorship = QCheckBox("검열 제거")
        self.chk_remove_text = QCheckBox("텍스트 제거")

        for chk in [self.chk_remove_censorship, self.chk_remove_text]:
            chk.setStyleSheet("font-weight: bold; color: #DDD;")
            remove_opts_layout2.addWidget(chk)
        
        remove_opts_layout2.addStretch()
        layout.addLayout(remove_opts_layout2)

        layout.addWidget(self._create_separator())

        # 입력 필드들
        self.char_count_input = self._create_group(layout, "인물 수", QLineEdit())
        # 캐릭터 입력 + 특징 프리셋 버튼 + 자동 추가 토글
        char_header = QHBoxLayout()
        char_header.addWidget(QLabel("캐릭터 (Character)"))
        char_header.addStretch()

        self.chk_auto_char_features = QCheckBox("특징 자동 추가")
        self.chk_auto_char_features.setStyleSheet(
            "QCheckBox { color: #FFA726; font-size: 11px; font-weight: bold; }"
        )
        self.chk_auto_char_features.setToolTip(
            "자동화 중 캐릭터 불러올 때 특징 태그 자동 삽입"
        )
        char_header.addWidget(self.chk_auto_char_features)

        self.combo_char_feature_mode = QComboBox()
        self.combo_char_feature_mode.addItems(["핵심만", "핵심+의상"])
        self.combo_char_feature_mode.setFixedSize(90, 24)
        self.combo_char_feature_mode.setStyleSheet(
            "QComboBox { background-color: #2A2A2A; color: #DDD; "
            "border: 1px solid #444; border-radius: 4px; font-size: 11px; padding: 1px 4px; }"
        )
        self.combo_char_feature_mode.setToolTip("핵심만: 눈색/머리색 등\n핵심+의상: 의상/소품 포함")
        char_header.addWidget(self.combo_char_feature_mode)

        self.btn_char_preset = QPushButton("특징 프리셋")
        self.btn_char_preset.setFixedHeight(28)
        self.btn_char_preset.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; "
            "border-radius: 4px; font-weight: bold; font-size: 11px; "
            "padding: 0 10px; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        self.btn_char_preset.clicked.connect(self._open_character_preset)
        char_header.addWidget(self.btn_char_preset)
        layout.addLayout(char_header)

        self.character_input = QLineEdit()
        self.character_input.setStyleSheet(
            "background-color: #252525; border: none; "
            "border-radius: 8px; padding: 8px 10px; color: #FFFFFF;"
        )
        layout.addWidget(self.character_input)

        self.copyright_input = self._create_group(layout, "작품 (Copyright)", QLineEdit())
        
        # 작가 입력창 + 고정 버튼
        artist_group = QWidget()
        artist_layout = QVBoxLayout(artist_group)
        artist_layout.setContentsMargins(0, 0, 0, 0)
        
        h_artist = QHBoxLayout()
        h_artist.addWidget(QLabel("작가 (Artist)"))
        
        self.btn_lock_artist = QPushButton("🔒 고정")
        self.btn_lock_artist.setCheckable(True)
        self.btn_lock_artist.setFixedWidth(80)
        self.btn_lock_artist.setStyleSheet("""
            QPushButton { 
                border: 1px solid #555; border-radius: 4px; 
                font-size: 11px; background-color: #333; color: #AAA; 
            }
            QPushButton:checked { 
                background-color: #d35400; color: white; 
                border: 1px solid #e67e22; 
            }
        """)
        h_artist.addStretch()
        h_artist.addWidget(self.btn_lock_artist)
        
        artist_layout.addLayout(h_artist)
        self.artist_input = QLineEdit() 
        self.artist_input.setStyleSheet(
            "background-color: #252525; border: none; "
            "border-radius: 8px; padding: 8px 10px; color: #FFFFFF;"
        )
        artist_layout.addWidget(self.artist_input)
        layout.addWidget(artist_group)

        # 선행 프롬프트 (자동완성 지원)
        self.prefix_prompt_text = TagInputWidget()
        self.prefix_prompt_text.setMinimumHeight(60)
        
        self.prefix_toggle_button = QPushButton("▼ 선행 고정 프롬프트")
        self.prefix_toggle_button.setCheckable(True)
        self.prefix_toggle_button.setChecked(True)
        self.prefix_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #5865F2;
                border: 1px solid #5865F2;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                padding: 8px;
                text-align: left;
            }
            QPushButton:!checked {
                background-color: #2A2A2A;
                color: #5865F2;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.prefix_toggle_button.toggled.connect(self._on_prefix_toggle)
        
        layout.addWidget(self.prefix_toggle_button)
        layout.addWidget(self.prefix_prompt_text)
        
        # 메인 프롬프트 (자동완성 지원)
        self.main_prompt_text = self._create_group(layout, "메인", TagInputWidget())
        self.main_prompt_text.setMinimumHeight(80)

        # 즐겨찾기 태그 바
        self.fav_tags_bar = FavoriteTagsBar()
        self.fav_tags_bar.tag_insert_requested.connect(self._insert_fav_tag)
        layout.addWidget(self.fav_tags_bar)

        # LoRA + 가중치 편집 버튼 행
        lora_row = QHBoxLayout()
        lora_row.setSpacing(4)

        self.btn_tag_weights = QPushButton("⚖️ 가중치")
        self.btn_tag_weights.setFixedHeight(32)
        self.btn_tag_weights.setStyleSheet(
            "background-color: #2C6B2F; color: white; border-radius: 4px; "
            "font-size: 12px; font-weight: bold; padding: 2px 10px;"
        )
        self.btn_tag_weights.setToolTip("메인 프롬프트 태그 가중치 슬라이더 편집")
        self.btn_tag_weights.clicked.connect(self._open_tag_weight_editor)

        # LoRA 삽입 버튼
        self.btn_lora_manager = QPushButton("📦 LoRA")
        self.btn_lora_manager.setFixedHeight(32)
        self.btn_lora_manager.setStyleSheet(
            "background-color: #8A5CF5; color: white; border-radius: 4px; "
            "font-size: 12px; font-weight: bold; padding: 2px 10px;"
        )
        self.btn_lora_manager.setToolTip("LoRA 브라우저 열기")
        self.btn_lora_manager.clicked.connect(self._open_lora_manager)

        lora_row.addWidget(self.btn_tag_weights)
        lora_row.addWidget(self.btn_lora_manager)
        layout.addLayout(lora_row)

        # LoRA 활성 목록 패널
        from widgets.lora_panel import LoraActivePanel
        self.lora_active_panel = LoraActivePanel()
        layout.addWidget(self.lora_active_panel)

        # 후행 프롬프트 (자동완성 지원)
        self.suffix_prompt_text = TagInputWidget()
        self.suffix_prompt_text.setMinimumHeight(60)
        
        self.suffix_toggle_button = QPushButton("▼ 후행 고정 프롬프트")
        self.suffix_toggle_button.setCheckable(True)
        self.suffix_toggle_button.setChecked(True)
        self.suffix_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                border: 1px solid #27ae60;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                padding: 8px;
                text-align: left;
            }
            QPushButton:!checked {
                background-color: #2A2A2A;
                color: #27ae60;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.suffix_toggle_button.toggled.connect(self._on_suffix_toggle)
        
        layout.addWidget(self.suffix_toggle_button)
        layout.addWidget(self.suffix_prompt_text)
        
        # 네거티브 프롬프트 (자동완성 지원)
        self.neg_prompt_text = TagInputWidget()
        self.neg_prompt_text.setMinimumHeight(60)

        self.neg_toggle_button = QPushButton("▼ 부정 프롬프트 (Negative)")
        self.neg_toggle_button.setCheckable(True)
        self.neg_toggle_button.setChecked(True)
        self.neg_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                border: 1px solid #e74c3c;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                padding: 8px;
                text-align: left;
            }
            QPushButton:!checked {
                background-color: #2A2A2A;
                color: #e74c3c;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.neg_toggle_button.toggled.connect(self._on_neg_toggle)

        layout.addWidget(self.neg_toggle_button)
        layout.addWidget(self.neg_prompt_text)

        # 제외 프롬프트 (자동완성 지원)
        self.exclude_prompt_local_input = TagInputWidget()
        self.exclude_prompt_local_input.setMinimumHeight(60)
        self.exclude_prompt_local_input.setPlaceholderText(
            "예: arms up, __hair, hair__, __username__, ~blue hair"
        )

        self.exclude_toggle_button = QPushButton("▼ 제외 프롬프트 (Local)")
        self.exclude_toggle_button.setCheckable(True)
        self.exclude_toggle_button.setChecked(True)
        self.exclude_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                border: 1px solid #e67e22;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                padding: 8px;
                text-align: left;
            }
            QPushButton:!checked {
                background-color: #2A2A2A;
                color: #e67e22;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.exclude_toggle_button.toggled.connect(self._on_exclude_toggle)

        layout.addWidget(self.exclude_toggle_button)
        layout.addWidget(self.exclude_prompt_local_input)


        # 모델 선택
        self.model_combo = self._create_group(layout, "모델", NoScrollComboBox())
        
        # 샘플러 / 스케줄러
        self.sampler_combo = NoScrollComboBox()
        self.scheduler_combo = NoScrollComboBox()
        self._create_group(
            layout, 
            "샘플러 / 스케줄러", 
            self._make_hbox([self.sampler_combo, self.scheduler_combo])
        )
        
        # Steps, CFG
        self.steps_input, _ = self._create_param_slider(layout, "Steps", 1, 100, 25, 1)
        self.cfg_input, _ = self._create_param_slider(layout, "CFG", 1, 20, 7, 0.5)
        
        # Seed
        seed_layout = QHBoxLayout()
        self.seed_input = QLineEdit("-1")
        btn_seed = QPushButton("🎲")
        btn_seed.clicked.connect(lambda: self.seed_input.setText("-1"))
        seed_layout.addWidget(self.seed_input)
        seed_layout.addWidget(btn_seed)
        self._create_group(layout, "Seed", seed_layout)
        
        # 해상도
        res_layout = QHBoxLayout()
        self.width_input = QLineEdit("1024")
        self.height_input = QLineEdit("1024")
        btn_swap_res = QPushButton("🔄")
        btn_swap_res.setFixedSize(36, 32)
        btn_swap_res.setToolTip("W ↔ H 교환")
        btn_swap_res.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; border: none; "
            "border-radius: 4px; font-size: 18px; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        btn_swap_res.clicked.connect(self._swap_resolution)
        res_layout.addWidget(self.width_input)
        res_layout.addWidget(btn_swap_res)
        res_layout.addWidget(self.height_input)
        self._create_group(layout, "해상도", res_layout)

        # 해상도 프리셋 버튼 (우클릭으로 커스텀 해상도 변경 가능)
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
            "QPushButton { background-color: #333; color: #CCC; border: 1px solid #555; "
            "border-radius: 3px; padding: 2px 4px; font-size: 10px; }"
            "QPushButton:hover { background-color: #444; border-color: #5865F2; }"
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
        layout.addLayout(res_preset_row)

        # 랜덤 해상도
        self.random_res_check = QCheckBox("랜덤 해상도")
        layout.addWidget(self.random_res_check)
        
        self.random_res_label = QLabel()
        layout.addWidget(self.random_res_label)
        
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
        
        layout.addWidget(self.resolution_editor_container)
        self.resolution_editor_container.hide()

        # Hires.fix
        self.hires_options_group = QGroupBox("Hires.fix")
        self.hires_options_group.setCheckable(True)
        self.hires_options_group.setChecked(False)
        hires_l = QVBoxLayout(self.hires_options_group)

        self.upscaler_combo = NoScrollComboBox()
        hires_l.addWidget(self.upscaler_combo)

        self.hires_steps_input, _ = self._create_param_slider(
            hires_l, "Steps", 0, 50, 0, 1
        )
        self.hires_denoising_input, _ = self._create_param_slider(
            hires_l, "Denoise", 0, 1, 0.4, 0.01
        )
        self.hires_scale_input, _ = self._create_param_slider(
            hires_l, "Scale", 1, 4, 2, 0.05
        )
        self.hires_cfg_input, _ = self._create_param_slider(
            hires_l, "CFG", 0, 30, 0, 0.5
        )

        # Hires Checkpoint
        hr_ckpt_label = QLabel("Checkpoint")
        hr_ckpt_label.setStyleSheet("color: #999; font-size: 11px;")
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
        hr_prompt_label.setStyleSheet("color: #999; font-size: 11px;")
        hires_l.addWidget(hr_prompt_label)
        self.hires_prompt_text = QTextEdit()
        self.hires_prompt_text.setFixedHeight(50)
        self.hires_prompt_text.setPlaceholderText("비워두면 메인 프롬프트 사용")
        self.hires_prompt_text.setStyleSheet(
            "background-color: #2C2C2C; color: #DDD; border: 1px solid #444; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        hires_l.addWidget(self.hires_prompt_text)

        # Hires Negative Prompt
        hr_neg_label = QLabel("Hires Negative")
        hr_neg_label.setStyleSheet("color: #999; font-size: 11px;")
        hires_l.addWidget(hr_neg_label)
        self.hires_neg_prompt_text = QTextEdit()
        self.hires_neg_prompt_text.setFixedHeight(50)
        self.hires_neg_prompt_text.setPlaceholderText("비워두면 메인 네거티브 사용")
        self.hires_neg_prompt_text.setStyleSheet(
            "background-color: #2C2C2C; color: #DDD; border: 1px solid #444; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        hires_l.addWidget(self.hires_neg_prompt_text)

        layout.addWidget(self.hires_options_group)

        # NegPiP 확장
        self.negpip_group = QGroupBox("NegPiP 확장")
        self.negpip_group.setCheckable(True)
        self.negpip_group.setChecked(False) 
        self.negpip_group.setStyleSheet(
            "QGroupBox::indicator { width: 16px; height: 16px; }"
        )
        np_layout = QVBoxLayout(self.negpip_group)
        np_layout.addWidget(
            QLabel("활성화 시 (keyword:-1.0) 네거티브 가중치 문법 사용 가능")
        )
        layout.addWidget(self.negpip_group)

        # ADetailer
        self.adetailer_group = QGroupBox("ADetailer")
        self.adetailer_group.setCheckable(True)
        self.adetailer_group.setChecked(False)
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
        layout.addWidget(self.adetailer_group)

        layout.addStretch()
        return panel
        
    def _create_adetailer_slot_ui(self, title, default_model):
        """ADetailer 슬롯 UI 생성"""
        slot_group = QGroupBox(title)
        slot_group.setCheckable(True)
        slot_layout = QVBoxLayout(slot_group)
        widgets = {}
        
        # Model
        slot_layout.addWidget(QLabel("Model"))
        widgets['model'] = QLineEdit(default_model)
        slot_layout.addWidget(widgets['model'])
        
        # Prompt
        slot_layout.addWidget(QLabel("Prompt"))
        widgets['prompt'] = QTextEdit()
        widgets['prompt'].setFixedHeight(60)
        slot_layout.addWidget(widgets['prompt'])
        
        # Mask Blur & Denoise
        row1_layout = QHBoxLayout()
        widgets['mask_blur'], blur_widget = self._create_param_slider(
            None, "인페인트 마스크 블러", 0, 64, 8, 1
        )
        row1_layout.addWidget(blur_widget)
        
        widgets['denoise'], denoise_widget = self._create_param_slider(
            None, "디노이징 강도", 0.0, 1.0, 0.4, 0.01
        )
        row1_layout.addWidget(denoise_widget)
        slot_layout.addLayout(row1_layout)
        
        # Confidence & Padding
        widgets['confidence'], _ = self._create_param_slider(
            slot_layout, "Detection Confidence", 0.0, 1.0, 0.3, 0.01
        )
        widgets['padding'], _ = self._create_param_slider(
            slot_layout, "Inpaint Padding (px)", 0, 256, 32, 1
        )
        
        # Inpaint Size
        widgets['use_inpaint_size_check'] = QCheckBox("별도의 너비/높이 사용")
        slot_layout.addWidget(widgets['use_inpaint_size_check'])
        
        widgets['inpaint_size_container'] = QWidget()
        s_inpaint_size_layout = QHBoxLayout(widgets['inpaint_size_container'])
        s_inpaint_size_layout.setContentsMargins(20, 0, 0, 0)
        
        widgets['inpaint_width'] = QLineEdit("1024")
        widgets['inpaint_height'] = QLineEdit("1024")
        s_inpaint_size_layout.addWidget(QLabel("ㄴ 너비:"))
        s_inpaint_size_layout.addWidget(widgets['inpaint_width'])
        s_inpaint_size_layout.addWidget(QLabel("높이:"))
        s_inpaint_size_layout.addWidget(widgets['inpaint_height'])
        widgets['inpaint_size_container'].hide()
        slot_layout.addWidget(widgets['inpaint_size_container'])
        
        # Options
        options = [
            ('use_steps_check', '별도의 단계 사용', 'steps', QLineEdit("32")),
            ('use_cfg_check', '별도의 CFG 스케일 사용', 'cfg', QLineEdit("5.0")),
            ('use_checkpoint_check', 'Use separate checkpoint', 
             'checkpoint_combo', NoScrollComboBox()), 
            ('use_vae_check', 'Use separate VAE', 'vae_combo', NoScrollComboBox()), 
        ]
        
        for check_key, text, widget_key, widget in options:
            widgets[check_key] = QCheckBox(text)
            slot_layout.addWidget(widgets[check_key])
            widget.hide()
            widgets[widget_key] = widget
            slot_layout.addWidget(widget)
            
        # Sampler
        widgets['use_sampler_check'] = QCheckBox("별도의 샘플러 사용")
        slot_layout.addWidget(widgets['use_sampler_check'])
        
        widgets['sampler_container'] = QWidget()
        s_sampler_layout = QHBoxLayout(widgets['sampler_container'])
        s_sampler_layout.setContentsMargins(0, 0, 0, 0)
        
        widgets['sampler_combo'] = NoScrollComboBox() 
        widgets['scheduler_combo'] = NoScrollComboBox()
        
        s_sampler_layout.addWidget(widgets['sampler_combo'])
        s_sampler_layout.addWidget(widgets['scheduler_combo'])
        widgets['sampler_container'].hide()
        slot_layout.addWidget(widgets['sampler_container'])
        
        return slot_group, widgets
    
    def _create_viewer_panel(self):
        """뷰어 패널 생성"""
        from PyQt6.QtWidgets import QProgressBar

        splitter = QSplitter(Qt.Orientation.Vertical)

        # 상단: 이미지 뷰어 + 프로그레스 바 컨테이너
        viewer_container = QWidget()
        vc_layout = QVBoxLayout(viewer_container)
        vc_layout.setContentsMargins(0, 0, 0, 0)
        vc_layout.setSpacing(0)

        self.viewer_label = QLabel("WebUI 정보를 불러오는 중...")
        self.viewer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_label.setMinimumSize(400, 400)
        self.viewer_label.setStyleSheet(
            "background-color: #1A1A1A; border-radius: 8px; color: #888;"
        )
        vc_layout.addWidget(self.viewer_label, 1)

        # 생성 진행률 바
        self.gen_progress_bar = QProgressBar()
        self.gen_progress_bar.setRange(0, 100)
        self.gen_progress_bar.setValue(0)
        self.gen_progress_bar.setFixedHeight(20)
        self.gen_progress_bar.setTextVisible(True)
        self.gen_progress_bar.setFormat("%v / %m steps")
        self.gen_progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 4px;
                color: #ddd;
                font-size: 11px;
                font-weight: bold;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5865F2, stop:1 #7289DA);
                border-radius: 3px;
            }
        """)
        self.gen_progress_bar.hide()
        vc_layout.addWidget(self.gen_progress_bar)

        # 하단: EXIF 정보
        self.exif_display = QTextEdit()
        self.exif_display.setReadOnly(True)
        self.exif_display.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E; color: #B0B0B0;
                border: 1px solid #333;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }
        """)

        splitter.addWidget(viewer_container)
        splitter.addWidget(self.exif_display)
        splitter.setSizes([800, 200])
        splitter.setStretchFactor(0, 1)

        return splitter
    
    def _create_history_panel(self):
        """히스토리 패널 생성"""
        panel = QWidget()
        panel.setStyleSheet(
            "background-color: #181818; border-left: 1px solid #2A2A2A;"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 헤더
        header = QLabel("📜 히스토리")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            "padding: 15px; font-weight: bold; color: #FFC107; "
            "font-size: 14px; background-color: #1E1E1E;"
        )
        layout.addWidget(header)
        
        # 이전 버튼
        self.btn_history_up = QPushButton("▲ 이전 이미지")
        self.btn_history_up.clicked.connect(self.select_prev_image)
        self.btn_history_up.setStyleSheet(
            "background-color: #2C2C2C; border: none; padding: 8px; color: #AAA;"
        )
        layout.addWidget(self.btn_history_up)

        # 갤러리 스크롤
        self.gallery_scroll_area = QScrollArea()
        self.gallery_scroll_area.setWidgetResizable(True)
        self.gallery_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.gallery_scroll_area.setStyleSheet(
            "border: none; background: transparent;"
        )
        
        scroll_content = QWidget()
        self.gallery_layout = QVBoxLayout(scroll_content)
        self.gallery_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self.gallery_layout.setSpacing(10)
        self.gallery_layout.setContentsMargins(10, 10, 10, 10)
        self.gallery_scroll_area.setWidget(scroll_content)
        
        layout.addWidget(self.gallery_scroll_area, 1)  # ← stretch factor 추가!
        
        # 다음 버튼
        self.btn_history_down = QPushButton("▼ 다음 이미지")
        self.btn_history_down.clicked.connect(self.select_next_image)
        self.btn_history_down.setStyleSheet(
            "background-color: #2C2C2C; border: none; padding: 8px; color: #AAA;"
        )
        layout.addWidget(self.btn_history_down)

        # 즐겨찾기 추가 버튼 (토글 아님!)
        self.btn_add_favorite = QPushButton("⭐ 즐겨찾기 추가 (FAV)")
        self.btn_add_favorite.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_favorite.setFixedHeight(40)
        self.btn_add_favorite.setEnabled(False)  # ← 기본 비활성화!
        self.btn_add_favorite.setStyleSheet("""
            QPushButton {
                background-color: #2C2C2C;
                border: 1px solid #FFC107;
                color: #FFC107;
                font-weight: bold;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #FFC107;
                color: #121212;
            }
            QPushButton:disabled {
                background-color: #1E1E1E;
                border: 1px solid #444;
                color: #666;
            }
        """)
        layout.addWidget(self.btn_add_favorite)
        
        # 새로고침 버튼 (클릭 피드백 추가)
        self.btn_refresh_gallery = QPushButton("🔄 목록 새로고침")
        self.btn_refresh_gallery.setFixedHeight(35)
        self.btn_refresh_gallery.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_gallery.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                border: none;
                padding: 8px;
                color: #AAA;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #333;
                color: #FFF;
            }
            QPushButton:pressed {
                background-color: #5865F2;
                color: white;
            }
        """)
        self.btn_refresh_gallery.clicked.connect(self._on_refresh_gallery)
        layout.addWidget(self.btn_refresh_gallery)
        
        return panel
    
    def _on_refresh_gallery(self):
        """갤러리 새로고침 (피드백 포함)"""
        self.btn_refresh_gallery.setText("🔄 새로고침 중...")
        self.btn_refresh_gallery.setEnabled(False)
        
        # 실제 새로고침 수행
        if hasattr(self, 'refresh_gallery'):
            self.refresh_gallery()
        
        # 버튼 복구 (0.5초 후)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, lambda: (
            self.btn_refresh_gallery.setText("🔄 목록 새로고침"),
            self.btn_refresh_gallery.setEnabled(True)
        ))
        
    def _save_prompt_preset(self):
        """현재 프롬프트를 프리셋으로 저장"""
        from PyQt6.QtWidgets import QInputDialog
        from utils.prompt_preset import save_preset, list_presets

        name, ok = QInputDialog.getText(self, "프리셋 저장", "프리셋 이름:")
        if not ok or not name.strip():
            return
        name = name.strip()

        data = {
            "character": self.character_input.text(),
            "copyright": self.copyright_input.text(),
            "artist": self.artist_input.text(),
            "main_prompt": self.main_prompt_text.toPlainText(),
            "prefix": self.prefix_prompt_text.toPlainText(),
            "suffix": self.suffix_prompt_text.toPlainText(),
            "negative": self.neg_prompt_text.toPlainText(),
        }
        save_preset(name, data)
        QMessageBox.information(self, "저장 완료", f"프리셋 '{name}'이 저장되었습니다.")

    def _load_prompt_preset(self):
        """저장된 프리셋 불러오기 (미리보기 다이얼로그)"""
        from utils.prompt_preset import list_presets
        from widgets.preset_preview_dialog import PresetPreviewDialog

        names = list_presets()
        if not names:
            QMessageBox.information(self, "프리셋", "저장된 프리셋이 없습니다.")
            return

        dlg = PresetPreviewDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        data = dlg.get_result()
        if not data:
            return

        _field_map = {
            "character":    lambda v: self.character_input.setText(v),
            "copyright":    lambda v: self.copyright_input.setText(v),
            "artist":       lambda v: self.artist_input.setText(v),
            "main_prompt":  lambda v: self.main_prompt_text.setPlainText(v),
            "prefix":       lambda v: self.prefix_prompt_text.setPlainText(v),
            "suffix":       lambda v: self.suffix_prompt_text.setPlainText(v),
            "negative":     lambda v: self.neg_prompt_text.setPlainText(v),
        }
        for key, setter in _field_map.items():
            if key in data:
                setter(data[key])

        self.show_status("프리셋 적용됨")

    def _show_prompt_history(self):
        """최근 프롬프트 히스토리 팝업"""
        from utils.prompt_history import get_history
        history = get_history()
        if not history:
            QMessageBox.information(self, "히스토리", "저장된 프롬프트가 없습니다.")
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a; color: #ddd; border: 1px solid #555;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 12px; border-radius: 3px;
            }
            QMenu::item:selected { background-color: #5865F2; }
        """)
        for i, entry in enumerate(history[:30]):
            prompt_preview = entry.get("prompt", "")[:80]
            if len(entry.get("prompt", "")) > 80:
                prompt_preview += "..."
            action = menu.addAction(f"{i+1}. {prompt_preview}")
            action.setData(entry)

        chosen = menu.exec(self.btn_prompt_history.mapToGlobal(
            self.btn_prompt_history.rect().bottomLeft()
        ))
        if chosen:
            data = chosen.data()
            self.main_prompt_text.setPlainText(data.get("prompt", ""))
            self.neg_prompt_text.setPlainText(data.get("negative", ""))

    def _adjust_total_prompt_height(self):
        """최종 프롬프트 칸 내용에 맞춰 높이 자동 조절"""
        doc = self.total_prompt_display.document()
        doc_height = int(doc.size().height()) + 10  # 여백
        new_h = max(60, min(doc_height, 600))
        current_h = self.total_prompt_display.height()
        # 높이 차이가 3px 이상일 때만 업데이트 (진동 방지)
        if abs(current_h - new_h) > 3:
            self.total_prompt_display.setFixedHeight(new_h)

    def _create_group(self, parent_layout, title, widget_or_layout):
        """그룹 생성 헬퍼"""
        parent_layout.addWidget(QLabel(title))
        if isinstance(widget_or_layout, QWidget):
            parent_layout.addWidget(widget_or_layout)
            return widget_or_layout
        elif isinstance(widget_or_layout, QHBoxLayout):
            parent_layout.addLayout(widget_or_layout)
            return widget_or_layout
    
    def _create_param_slider(self, parent_layout, name, min_val, max_val, 
                            default_val, step):
        """파라미터 슬라이더 생성"""
        is_float = isinstance(step, float)
        multiplier = int(1 / step) if is_float else 1
        
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        from PyQt6.QtWidgets import QSlider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        slider.wheelEvent = lambda event: event.ignore()
        slider.setRange(int(min_val * multiplier), int(max_val * multiplier))
        
        num_input = QLineEdit(
            f"{default_val:.2f}" if is_float else str(default_val)
        )
        num_input.setFixedWidth(60)
        num_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        def update_input():
            value = slider.value() / multiplier
            num_input.setText(
                f"{value:.2f}" if is_float else str(int(value))
            )
            
        def update_slider():
            try:
                value = float(num_input.text())
                slider.setValue(int(value * multiplier))
            except ValueError: 
                pass
            
        slider.valueChanged.connect(update_input)
        num_input.editingFinished.connect(update_slider)

        # 슬라이더 참조 저장 (load_settings 시 동기화용)
        num_input._slider = slider
        num_input._multiplier = multiplier

        slider.setValue(int(default_val * multiplier))
        if hasattr(self, 'wheel_filter'):
            slider.installEventFilter(self.wheel_filter)
        
        layout.addWidget(slider)
        layout.addWidget(num_input)

        if parent_layout is not None:
            if name: 
                parent_layout.addWidget(QLabel(name))
            parent_layout.addWidget(container)
            return num_input, container
        else:
            return num_input, container
    
    def _create_separator(self):
        """구분선 생성"""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        return separator
    
    def _make_hbox(self, widgets):
        """HBox 컨테이너 생성"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        for w in widgets:
            layout.addWidget(w)
        return container

    def _on_prefix_toggle(self, checked):
        """선행 프롬프트 토글"""
        self.prefix_prompt_text.setVisible(checked)
        self.prefix_toggle_button.setText(
            "▼ 선행 고정 프롬프트" if checked else "▶ 선행 고정 프롬프트"
        )
    
    def _on_suffix_toggle(self, checked):
        """후행 프롬프트 토글"""
        self.suffix_prompt_text.setVisible(checked)
        self.suffix_toggle_button.setText(
            "▼ 후행 고정 프롬프트" if checked else "▶ 후행 고정 프롬프트"
        )
    
    def _on_neg_toggle(self, checked):
        """네거티브 프롬프트 토글"""
        self.neg_prompt_text.setVisible(checked)
        self.neg_toggle_button.setText(
            "▼ 부정 프롬프트 (Negative)" if checked else "▶ 부정 프롬프트 (Negative)"
        )

    def _on_exclude_toggle(self, checked):
        """제외 프롬프트 토글"""
        self.exclude_prompt_local_input.setVisible(checked)
        self.exclude_toggle_button.setText(
            "▼ 제외 프롬프트 (Local)" if checked else "▶ 제외 프롬프트 (Local)"
        )
        
    def _on_res_preset_context(self, idx: int, btn):
        """해상도 프리셋 우클릭 메뉴"""
        from PyQt6.QtWidgets import QMenu, QDialog, QDialogButtonBox, QSpinBox
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #2C2C2C; color: #DDD; border: 1px solid #555; }"
            "QMenu::item { padding: 6px 16px; }"
            "QMenu::item:selected { background-color: #5865F2; }"
        )
        act_edit = menu.addAction("✏️ 해상도 변경")
        act_reset = menu.addAction("↩️ 기본값 복원")
        chosen = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if not chosen:
            return
        if chosen == act_edit:
            dlg = QDialog(self)
            dlg.setWindowTitle("해상도 변경")
            dlg.setFixedSize(280, 120)
            dlg.setStyleSheet("background-color: #1E1E1E; color: #EEE;")
            dl = QVBoxLayout(dlg)
            row = QHBoxLayout()
            w_spin = QSpinBox()
            w_spin.setRange(64, 4096)
            w_spin.setSingleStep(64)
            w_spin.setValue(self._res_presets[idx][1])
            w_spin.setStyleSheet("background:#2C2C2C; color:#EEE; border:1px solid #555; padding:4px;")
            h_spin = QSpinBox()
            h_spin.setRange(64, 4096)
            h_spin.setSingleStep(64)
            h_spin.setValue(self._res_presets[idx][2])
            h_spin.setStyleSheet("background:#2C2C2C; color:#EEE; border:1px solid #555; padding:4px;")
            swap_btn = QPushButton("⇄")
            swap_btn.setFixedSize(32, 32)
            swap_btn.setToolTip("W ↔ H 교환")
            swap_btn.setStyleSheet(
                "background:#5865F2; color:white; border:none; "
                "border-radius:4px; font-weight:bold; font-size:16px;"
            )
            swap_btn.clicked.connect(lambda: (
                w_spin.setValue(h_spin.value()) or True) if (
                    _tw := w_spin.value()) and (w_spin.setValue(h_spin.value()) or True) and h_spin.setValue(_tw) is None else None
            )
            # simpler swap
            def _swap_wh():
                _w, _h = w_spin.value(), h_spin.value()
                w_spin.setValue(_h)
                h_spin.setValue(_w)
            swap_btn.clicked.disconnect()
            swap_btn.clicked.connect(_swap_wh)
            row.addWidget(QLabel("W:"))
            row.addWidget(w_spin)
            row.addWidget(swap_btn)
            row.addWidget(QLabel("H:"))
            row.addWidget(h_spin)
            dl.addLayout(row)
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            dl.addWidget(bb)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                w, h = w_spin.value(), h_spin.value()
                label = f"{w}x{h}" if w != h else f"{w}\u00b2"
                self._res_presets[idx] = [label, w, h]
                btn.setText(label)
        elif chosen == act_reset:
            if idx < len(self._DEFAULT_RES_PRESETS):
                default = list(self._DEFAULT_RES_PRESETS[idx])
                self._res_presets[idx] = default
                btn.setText(default[0])

    def _swap_resolution(self):
        """W ↔ H 해상도 교환"""
        w, h = self.width_input.text(), self.height_input.text()
        self.width_input.setText(h)
        self.height_input.setText(w)

    def _open_lora_manager(self):
        """LoRA 브라우저 다이얼로그 열기"""
        from widgets.lora_manager import LoraManagerDialog
        from backends import get_backend
        try:
            backend = get_backend()
        except Exception:
            backend = None
        dlg = LoraManagerDialog(backend=backend, parent=self)
        dlg.lora_inserted.connect(self._on_lora_inserted)
        dlg.loras_batch_inserted.connect(self._on_lora_batch_inserted)
        dlg.exec()

    def _on_lora_inserted(self, lora_text: str):
        """LoRA를 활성 패널에 추가"""
        import re
        m = re.match(r'<lora:(.+?):([\d.]+)>', lora_text)
        if m:
            name, weight = m.group(1), float(m.group(2))
            self.lora_active_panel.add_lora(name, weight)

    def _on_lora_batch_inserted(self, text: str):
        """다이얼로그에서 일괄 붙여넣기된 LoRA 텍스트를 패널에 추가"""
        self.lora_active_panel.parse_and_add_loras(text)

    def _update_token_count(self):
        """최종 프롬프트 토큰 수 추정 (CLIP 기준 근사)"""
        text = self.total_prompt_display.toPlainText().strip()
        if not text:
            self.token_count_label.setText("토큰: 0 / 75")
            self.token_count_label.setStyleSheet(
                "color: #888; font-size: 11px; font-weight: bold; padding: 0 4px;"
            )
            return
        # CLIP 토큰 근사: 단어/서브워드 기준 (영어 ~0.75 토큰/단어, 태그 ~1 토큰/태그)
        import re
        tags = [t.strip() for t in text.split(",") if t.strip()]
        token_est = 0
        for tag in tags:
            words = re.findall(r'[a-zA-Z]+|[^ ,():\[\]]+', tag)
            token_est += max(1, len(words))
        if token_est <= 75:
            color = "#4CAF50"
        elif token_est <= 150:
            color = "#FFA726"
        else:
            color = "#E74C3C"
        self.token_count_label.setText(f"토큰: ~{token_est} / 75")
        self.token_count_label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: bold; padding: 0 4px;"
        )

    def _open_tag_weight_editor(self):
        """태그 가중치 슬라이더 편집"""
        from widgets.tag_weight_editor import TagWeightEditorDialog
        text = self.main_prompt_text.toPlainText().strip()
        if not text:
            return
        dlg = TagWeightEditorDialog(text, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            result = dlg.get_result()
            if result is not None:
                self.main_prompt_text.setPlainText(result)

    def _open_ab_test(self):
        """A/B 프롬프트 비교 테스트"""
        from widgets.ab_test_dialog import ABTestDialog
        prompt = self.main_prompt_text.toPlainText().strip()
        negative = self.neg_prompt_text.toPlainText().strip()
        dlg = ABTestDialog(prompt, negative, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        result = dlg.get_result()
        if not result:
            return
        # 프롬프트 A를 대기열에, 프롬프트 B를 대기열에 — 같은 시드
        for label, key in [("A", "prompt_a"), ("B", "prompt_b")]:
            payload = {
                'prompt': result[key],
                'negative_prompt': result['negative'],
                'seed': result['seed'],
            }
            if hasattr(self, 'queue_panel'):
                self.queue_panel.add_single_item(payload)
        self.show_status(f"A/B 테스트 대기열 추가 (시드: {result['seed']})")

    def _shuffle_main_prompt(self):
        """메인 프롬프트 태그 순서 랜덤 셔플"""
        import random
        text = self.main_prompt_text.toPlainText().strip()
        if not text:
            return
        tags = [t.strip() for t in text.split(",") if t.strip()]
        random.shuffle(tags)
        self.main_prompt_text.setPlainText(", ".join(tags))

    def _insert_fav_tag(self, tags: str):
        """즐겨찾기 태그를 메인 프롬프트에 삽입"""
        current = self.main_prompt_text.toPlainText().strip()
        if current:
            self.main_prompt_text.setPlainText(f"{current}, {tags}")
        else:
            self.main_prompt_text.setPlainText(tags)

    def _open_character_preset(self):
        """캐릭터 특징 프리셋 다이얼로그 열기"""
        # 기존 태그 수집 (중복 표시용) — 이스케이프/비이스케이프 모두 등록
        existing: set[str] = set()
        for src in (self.main_prompt_text.toPlainText(),
                    self.prefix_prompt_text.toPlainText(),
                    self.suffix_prompt_text.toPlainText(),
                    self.character_input.text()):
            for t in src.split(","):
                norm = t.strip().lower().replace("_", " ")
                if norm:
                    existing.add(norm)
                    # 이스케이프 제거 버전도 등록
                    unesc = norm.replace(r"\(", "(").replace(r"\)", ")")
                    if unesc != norm:
                        existing.add(unesc)

        current_char = self.character_input.text().strip()
        dlg = CharacterPresetDialog(
            existing_tags=existing,
            current_character=current_char,
            parent=self
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        result = dlg.get_result()
        if not result:
            return

        # 캐릭터 이름 설정
        char_name = result.get("character_name", "")
        if char_name:
            cur = self.character_input.text().strip()
            if cur:
                existing_chars = set()
                for c in cur.split(","):
                    n = c.strip().lower().replace("_", " ")
                    existing_chars.add(n)
                    existing_chars.add(
                        n.replace(r"\(", "(").replace(r"\)", ")")
                    )
                if char_name.lower().replace("_", " ") not in existing_chars:
                    self.character_input.setText(f"{cur}, {char_name}")
            else:
                self.character_input.setText(char_name)

        # 특징 태그 삽입 (중복 제거)
        tags = result.get("tags", [])
        if tags:
            # 삽입 시점의 전체 태그 재수집
            all_existing: set[str] = set()
            for src in (self.main_prompt_text.toPlainText(),
                        self.prefix_prompt_text.toPlainText(),
                        self.suffix_prompt_text.toPlainText(),
                        self.character_input.text()):
                for t in src.split(","):
                    n = t.strip().lower().replace("_", " ")
                    if n:
                        all_existing.add(n)
                        all_existing.add(
                            n.replace(r"\(", "(").replace(r"\)", ")")
                        )

            new_tags = [
                t for t in tags
                if t.strip().lower().replace("_", " ") not in all_existing
            ]
            if new_tags:
                insert_str = ", ".join(new_tags)
                current = self.main_prompt_text.toPlainText().strip()
                if current:
                    self.main_prompt_text.setPlainText(
                        f"{insert_str}, {current}"
                    )
                else:
                    self.main_prompt_text.setPlainText(insert_str)

    def _create_favorites_tab(self):
        """즐겨찾기 탭 생성"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 헤더
        header_layout = QHBoxLayout()
        header_label = QLabel("⭐ 즐겨찾기 목록")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFC107;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        self.btn_fav_refresh = QPushButton("🔄 새로고침")
        self.btn_fav_refresh.clicked.connect(self.refresh_favorites)
        self.btn_fav_refresh.setStyleSheet(
            "padding: 5px 10px; background-color: #333; border-radius: 4px;"
        )
        header_layout.addWidget(self.btn_fav_refresh)
        
        self.btn_fav_clear = QPushButton("🗑️ 전체 삭제")
        self.btn_fav_clear.clicked.connect(self.clear_all_favorites)
        self.btn_fav_clear.setStyleSheet(
            "padding: 5px 10px; background-color: #8B0000; color: white; border-radius: 4px;"
        )
        header_layout.addWidget(self.btn_fav_clear)
        
        layout.addLayout(header_layout)
        
        # 스크롤 영역 (썸네일 그리드)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: #1A1A1A;")
        
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(10, 10, 10, 10)
        scroll_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 플로우 레이아웃 (한 줄에 5개씩)
        self.fav_flow_widget = QWidget()
        self.fav_flow_layout = FlowLayout(self.fav_flow_widget)
        self.fav_flow_layout.setSpacing(10)
        
        scroll_content_layout.addWidget(self.fav_flow_widget)
        scroll_content_layout.addStretch()
        
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        return tab
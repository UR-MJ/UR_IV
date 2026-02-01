# ui/generator_ui_setup.py
"""
GeneratorMainUI의 UI 구성 부분 (전체)
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QGroupBox, QCheckBox, QTabWidget,
    QSplitter, QScrollArea, QListWidget,
    QSizePolicy, QListWidgetItem, QFrame, QStackedWidget
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QPixmap
from widgets.common_widgets import (
    NoScrollComboBox, AutomationWidget, ResolutionItemWidget, FlowLayout
)
from widgets.sliders import NumericSlider
from widgets.common_widgets import NoScrollComboBox, AutomationWidget, ResolutionItemWidget
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

        # 왼쪽 패널 스택 (생성 설정 ↔ 에디터 도구)
        self.left_stack = QStackedWidget()
        self.left_stack.setFixedWidth(450)
        self.left_stack.addWidget(self.left_panel_scroll)    # index 0: 생성 설정
        self.left_stack.addWidget(self.editor_tools_scroll)  # index 1: 에디터 도구

        # 오른쪽 히스토리
        self.history_panel = self._create_history_panel()
        self.history_panel.setFixedWidth(240)

        upper_layout.addWidget(self.left_stack)
        upper_layout.addWidget(self.center_tabs)
        upper_layout.addWidget(self.history_panel)

        main_layout.addWidget(upper_area, 1)

        # 상태 메시지 라벨은 _setup_queue()에서 큐 패널 아래에 추가
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
        
        # 10. 설정 탭
        self.settings_tab = SettingsTab(self)
        center_tabs.addTab(self.settings_tab, "⚙️ Setting")
        
        # 설정 위젯 링크 (조건부 프롬프트 등)
        self.cond_prompt_check = self.settings_tab.cond_prompt_check
        self.cond_prevent_dupe_check = self.settings_tab.cond_prevent_dupe_check
        self.cond_prompt_input = self.settings_tab.cond_prompt_input
        self.cond_neg_check = self.settings_tab.cond_neg_check
        self.cond_neg_input = self.settings_tab.cond_neg_input
        
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
        top_btns.addWidget(self.btn_save_settings) 
        layout.addLayout(top_btns)

        # 프롬프트 표시창
        self.total_prompt_display = QTextEdit()
        self.total_prompt_display.setReadOnly(False)
        self.total_prompt_display.setMinimumHeight(60)
        self.total_prompt_display.document().contentsChanged.connect(
            self._adjust_total_prompt_height
        )
        self._create_group(layout, "최종 프롬프트", self.total_prompt_display)
        
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
        
        gen_btns.addWidget(self.btn_random_prompt, 1)
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

        # 제거 옵션 버튼
        remove_opts_layout = QHBoxLayout()
        remove_opts_layout.setContentsMargins(0, 5, 0, 5)
        
        self.chk_remove_artist = QCheckBox("작가명 제거")
        self.chk_remove_copyright = QCheckBox("작품명 제거")
        self.chk_remove_meta = QCheckBox("메타 제거")
        
        for chk in [self.chk_remove_artist, self.chk_remove_copyright, 
                    self.chk_remove_meta]:
            chk.setStyleSheet("font-weight: bold; color: #DDD;")
            remove_opts_layout.addWidget(chk)
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
        self.character_input = self._create_group(layout, "캐릭터 (Character)", QLineEdit())
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

        # 선행 프롬프트 (QTextEdit 먼저 생성!)
        self.prefix_prompt_text = QTextEdit()
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

        # 후행 프롬프트 (QTextEdit 먼저 생성!)
        self.suffix_prompt_text = QTextEdit()
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
        
        # 네거티브 프롬프트
        self.neg_prompt_text = QTextEdit()
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

        # 제외 프롬프트
        self.exclude_prompt_local_input = QTextEdit()
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
        res_layout.addWidget(self.width_input)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.height_input)
        self._create_group(layout, "해상도", res_layout)
        
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
        self.res_height_input = QLineEdit()
        self.res_desc_input = QLineEdit()
        self.btn_add_res = QPushButton("+")
        
        input_res_layout.addWidget(self.res_desc_input)
        input_res_layout.addWidget(self.res_width_input)
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
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 상단: 이미지 뷰어
        self.viewer_label = QLabel("WebUI 정보를 불러오는 중...")
        self.viewer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_label.setMinimumSize(400, 400)
        self.viewer_label.setStyleSheet(
            "background-color: #1A1A1A; border-radius: 8px; color: #888;"
        )

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

        splitter.addWidget(self.viewer_label)
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
        
    def _adjust_total_prompt_height(self):
        """최종 프롬프트 칸 내용에 맞춰 높이 자동 조절"""
        doc = self.total_prompt_display.document()
        doc_height = int(doc.size().height()) + 10  # 여백
        new_h = max(60, min(doc_height, 600))
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
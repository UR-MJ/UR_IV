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
from utils.theme_manager import get_color

class UISetupMixin:
    """UI 구성을 담당하는 Mixin 클래스"""
    
    def _setup_ui(self):
        """UI: QWebEngineView(Vue SPA) 하나만 전체 화면"""
        self.setWindowTitle("AI Studio - Pro")
        self.setGeometry(100, 100, 1600, 950)

        # ── QWebEngineView 생성 (Vue SPA) ──
        from ui.vue_bridge import VueBridge
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineScript, QWebEnginePage
        from PyQt6.QtWebChannel import QWebChannel
        from PyQt6.QtCore import QUrl
        import os

        self.vue_bridge = VueBridge(self)

        class _DebugPage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                print(f"[Vue] {message}")

        from PyQt6.QtWebEngineCore import QWebEngineProfile
        
        # 캐시 및 데이터 경로 설정 (프로세스 간 충돌 방지 및 액세스 거부 방지)
        # 고정된 경로가 아닌 앱 전용 독립 경로 사용
        import tempfile
        base_cache_path = os.path.join(tempfile.gettempdir(), f'AIStudioPro_{os.getpid()}')
        os.makedirs(base_cache_path, exist_ok=True)
        
        # 독립적인 프로필 생성 (defaultProfile 대신 사용)
        self.web_profile = QWebEngineProfile("AIStudioProfile", self)
        self.web_profile.setPersistentStoragePath(os.path.join(base_cache_path, "Storage"))
        self.web_profile.setCachePath(os.path.join(base_cache_path, "Cache"))
        self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        
        self.vue_viewer = QWebEngineView()
        self.vue_viewer.setStyleSheet("border: none; background: transparent; margin: 0px; padding: 0px;")
        
        # 중요: 새로 만든 프로필로 페이지 생성
        page = _DebugPage(self.web_profile, self.vue_viewer)
        self.vue_viewer.setPage(page)

        channel = QWebChannel(page)
        channel.registerObject('backend', self.vue_bridge)
        page.setWebChannel(channel)

        qwc = QWebEngineScript()
        qwc.setName("qwebchannel")
        qwc.setSourceUrl(QUrl("qrc:///qtwebchannel/qwebchannel.js"))
        qwc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        qwc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        page.scripts().insert(qwc)

        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend_dist', 'index.html')
        if os.path.exists(frontend_path):
            self.vue_viewer.setUrl(QUrl.fromLocalFile(frontend_path))

        # QStackedWidget: 0=Vue SPA, 1=Web, 2=Backend
        from PyQt6.QtWidgets import QStackedWidget
        self._main_stack = QStackedWidget()
        self._main_stack.setContentsMargins(0, 0, 0, 0)
        self._main_stack.addWidget(self.vue_viewer)  # index 0

        # Web Browser (별도 QWebEngineView — iframe 보안 우회)
        from tabs.browser_tab import BrowserTab
        self.web_tab = BrowserTab(self)
        self._main_stack.addWidget(self.web_tab)  # index 1

        # Backend UI (별도 QWebEngineView)
        from tabs.backend_ui_tab import BackendUITab
        self.backend_ui_tab = BackendUITab(self)
        self._main_stack.addWidget(self.backend_ui_tab)  # index 2

        # Editor는 Vue에서 처리 (PyQt MosaicEditor 제거)
        from tabs.editor_tab import MosaicEditor
        self.mosaic_editor = MosaicEditor()
        self.mosaic_editor.setParent(None)  # 화면에 추가하지 않음

        self.setCentralWidget(self._main_stack)

        # ── 프록시 위젯 초기화 ──
        self._init_prompt_proxies()
        self._init_settings_proxies()
        self._init_button_proxies()

        # ── 호환성 더미 (Python 백엔드 코드에서 참조하는 속성들) ──
        self.vue_bridge.set_action_handler(self._handle_vue_action)

        _D = type('D', (), {
            '__getattr__': lambda s, n: lambda *a, **k: None
        })

        self.viewer_panel = self.vue_viewer
        self.center_tabs = _D()
        self.left_stack = _D()
        self._left_panel_container = _D()
        self.left_panel_scroll = _D()
        self.generator_panel = _D()
        self.editor_tools_scroll = _D()
        self._native_tab_bar = _D()
        self._native_tab_btns = {}
        self.history_panel = _D()
        self._tools_bar = _D()
        self._bottom_container = _D()
        self._bottom_layout = _D()
        self.status_message_label = _D()
        self.vram_label = _D()
        self.gallery_items = []
        self.gallery_layout = _D()

        # viewer_label 프록시
        class _VLP:
            def __getattr__(self, n): return lambda *a, **k: None
            def size(self):
                from PyQt6.QtCore import QSize
                return QSize(800, 600)
            class _Sig:
                def connect(self, *a): pass
            customContextMenuRequested = _Sig()
        self.viewer_label = _VLP()

        self.gen_progress_bar = _D()
        self.exif_display = _D()

        # 히스토리/갤러리 프록시
        from ui.widget_proxies import ButtonProxy
        b = self.vue_bridge
        self.btn_add_favorite = ButtonProxy(b, 'btn_add_favorite')
        self.btn_refresh_gallery = ButtonProxy(b, 'btn_refresh_gallery')

        # 기존 PyQt 탭 인스턴스 (Python 백엔드에서 참조)
        from tabs.settings_tab import SettingsTab
        from tabs.search_tab import SearchTab
        from tabs.event_gen_tab import EventGenTab
        from tabs.editor_tab import MosaicEditor
        from tabs.i2i_tab import Img2ImgTab
        from tabs.inpaint_tab import InpaintTab
        from tabs.upscale_tab import UpscaleTab
        from tabs.gallery_tab import GalleryTab
        from tabs.xyz_plot_tab import XYZPlotTab
        from tabs.pnginfo_tab import PngInfoTab
        from tabs.batch_tab import BatchTab
        from tabs.browser_tab import BrowserTab
        from tabs.backend_ui_tab import BackendUITab

        self.settings_tab = SettingsTab(self)
        self.settings_tab.setParent(None)
        self.search_tab = SearchTab(self)
        self.search_tab.setParent(None)
        self.event_gen_tab = EventGenTab(self)
        self.event_gen_tab.setParent(None)
        self.mosaic_editor = MosaicEditor()
        self.mosaic_editor.setParent(None)
        self.i2i_tab = Img2ImgTab(self)
        self.i2i_tab.setParent(None)
        self.inpaint_tab = InpaintTab(self)
        self.inpaint_tab.setParent(None)
        self.upscale_tab = UpscaleTab(self)
        self.upscale_tab.setParent(None)
        self.gallery_tab = GalleryTab(self)
        self.gallery_tab.setParent(None)
        self.xyz_plot_tab = XYZPlotTab(self)
        self.xyz_plot_tab.setParent(None)
        self.png_info_tab = PngInfoTab()
        self.png_info_tab.setParent(None)
        self.batch_tab = BatchTab(self)
        self.batch_tab.setParent(None)
        self.web_tab = BrowserTab(self)
        self.web_tab.setParent(None)
        self.backend_ui_tab = BackendUITab(self)
        self.backend_ui_tab.setParent(None)
        self._batch_upscale_tabs = _D()
        self.fav_tab = _D()

        # 설정 위젯 링크
        self.cond_prompt_check = self.settings_tab.cond_prompt_check
        self.cond_prevent_dupe_check = self.settings_tab.cond_prevent_dupe_check
        self.cond_block_editor_pos = self.settings_tab.cond_block_editor_pos
        self.cond_block_editor_neg = self.settings_tab.cond_block_editor_neg
        self.exclude_artist_checkbox = _D()
        self.exclude_copyright_checkbox = _D()

    def _get_tab_title(self, key: str) -> str:
        """테마에 따른 동적 탭 이름 반환"""
        from utils.theme_manager import get_theme_manager
        theme = get_theme_manager().current_theme_name
        use_minimal = theme == '모던'

        titles_minimal = {
            't2i': "T2I", 'i2i': "I2I", 'inpaint': "Inpaint",
            'event': "Event Gen", 'search': "Search", 'web': "Web",
            'editor': "Editor", 'batch': "Batch / Upscale",
            'gallery': "Gallery", 'xyz': "XYZ Plot", 'png': "PNG Info",
            'fav': "Favorites", 'backend': "Backend UI", 'settings': "Settings",
        }
        titles_emoji = {
            't2i': "🖼️ T2I", 'i2i': "🖼️ I2I", 'inpaint': "🎨 Inpaint",
            'event': "🎬 이벤트 생성", 'search': "🔍 Search", 'web': "🌐 Web",
            'editor': "🎨 Editor", 'batch': "📦 배치/업스케일",
            'gallery': "🖼️ Gallery", 'xyz': "📊 XYZ Plot", 'png': "ℹ️ PNG Info",
            'fav': "⭐ Favorites", 'backend': "🖥️ Backend UI", 'settings': "⚙️ Setting",
        }
        titles = titles_minimal if use_minimal else titles_emoji
        return titles.get(key, key)

    def _update_tab_titles(self):
        """테마 변경 시 모든 탭 이름 업데이트"""
        tab_keys = [
            't2i', 'i2i', 'inpaint', 'event', 'search', 'web', 'editor',
            'batch', 'gallery', 'xyz', 'png', 'fav', 'backend', 'settings'
        ]
        try:
            count = self.center_tabs.count()
            if count is None: return
            for i, key in enumerate(tab_keys):
                if i < count:
                    self.center_tabs.setTabText(i, self._get_tab_title(key))
        except (TypeError, AttributeError):
            pass  # Vue 모드에서는 center_tabs가 더미

    # ──────────────────────────────────────
    #  프록시 위젯 초기화 (Vue SPA 연동)
    # ──────────────────────────────────────

    def _init_prompt_proxies(self):
        """프롬프트 영역 프록시 위젯 초기화"""
        from ui.widget_proxies import LineEditProxy, TextEditProxy, CheckBoxProxy

        b = self.vue_bridge
        p = self  # 모든 프록시의 QObject 부모 (GC 방지)
        self.char_count_input = LineEditProxy(b, 'char_count_input')
        self.character_input = LineEditProxy(b, 'character_input')
        self.copyright_input = LineEditProxy(b, 'copyright_input')
        self.artist_input = TextEditProxy(b, 'artist_input')
        self.prefix_prompt_text = TextEditProxy(b, 'prefix_prompt_text')
        self.main_prompt_text = TextEditProxy(b, 'main_prompt_text')
        self.suffix_prompt_text = TextEditProxy(b, 'suffix_prompt_text')
        self.neg_prompt_text = TextEditProxy(b, 'neg_prompt_text')
        self.exclude_prompt_local_input = TextEditProxy(b, 'exclude_prompt_local_input')
        self.total_prompt_display = TextEditProxy(b, 'total_prompt_display')
        self.token_count_label = type('LabelProxy', (), {
            'setText': lambda self, t: None,
            'setAlignment': lambda self, a: None,
            'setStyleSheet': lambda self, s: None,
            'hide': lambda self: None,
            'show': lambda self: None,
            'setVisible': lambda self, v: None,
            'setFixedHeight': lambda self, h: None,
        })()

        # 즐겨찾기 태그 바 (Vue에서 렌더링 — 더미)
        self.fav_tags_bar = type('DummyFavBar', (), {
            'tag_insert_requested': type('Sig', (), {'connect': lambda *a: None})(),
            'hide': lambda self: None,
            'show': lambda self: None,
        })()

        # 호환성: 토글 버튼 더미
        class _AlwaysOn:
            def isChecked(self): return True
            def setChecked(self, v): pass
            toggled = type('', (), {'connect': lambda *a: None})()
        _d = _AlwaysOn()
        self.prefix_toggle_button = _d
        self.suffix_toggle_button = _d
        self.neg_toggle_button = _d
        self.exclude_toggle_button = _d

    def _init_settings_proxies(self):
        """설정 영역 프록시 위젯 초기화"""
        from ui.widget_proxies import (
            LineEditProxy, TextEditProxy, ComboBoxProxy, CheckBoxProxy,
            SliderProxy, GroupBoxProxy, ButtonProxy
        )

        b = self.vue_bridge
        self.chk_auto_char_features = CheckBoxProxy(b, 'chk_auto_char_features')
        self.combo_char_feature_mode = ComboBoxProxy(b, 'combo_char_feature_mode')
        self.combo_char_feature_mode.addItems(["핵심만", "핵심+의상"])
        self.btn_char_preset = ButtonProxy(b, 'btn_char_preset')

        self.model_combo = ComboBoxProxy(b, 'model_combo')
        self.vae_main_combo = ComboBoxProxy(b, 'vae_main_combo')
        self.te_main_input = LineEditProxy(b, 'te_main_input')
        self.sampler_combo = ComboBoxProxy(b, 'sampler_combo')
        self.scheduler_combo = ComboBoxProxy(b, 'scheduler_combo')

        self.steps_input = SliderProxy(b, 'steps_input')
        self.steps_input.setText('25')
        self.cfg_input = SliderProxy(b, 'cfg_input', multiplier=2)
        self.cfg_input.setText('7')
        self.shift_input = SliderProxy(b, 'shift_input', multiplier=2)
        self.shift_input.setText('0')

        self.seed_input = LineEditProxy(b, 'seed_input')
        self.seed_input.setText('-1')
        self.width_input = LineEditProxy(b, 'width_input')
        self.width_input.setText('1024')
        self.height_input = LineEditProxy(b, 'height_input')
        self.height_input.setText('1024')

        # 해상도 관련
        self.random_res_check = CheckBoxProxy(b, 'random_res_check')
        self.auto_res_check = CheckBoxProxy(b, 'auto_res_check')
        self.random_res_label = type('LblProxy', (), {
            'setText': lambda s, t: None, 'hide': lambda s: None, 'show': lambda s: None,
        })()
        self.resolution_editor_container = type('WProxy', (), {
            'hide': lambda s: None, 'show': lambda s: None,
        })()
        self.resolution_list_widget = type('LWProxy', (), {
            'clear': lambda s: None, 'addItem': lambda s, i: None,
            'count': lambda s: 0, 'item': lambda s, i: None,
            'setFixedHeight': lambda s, h: None,
        })()
        self.res_width_input = LineEditProxy(b, 'res_width_input')
        self.res_height_input = LineEditProxy(b, 'res_height_input')
        self.btn_add_res = ButtonProxy(b, 'btn_add_res')
        self._res_presets = [
            ["512 × 512", 512, 512], ["512 × 768", 512, 768], ["768 × 512", 768, 512],
            ["1024 × 1024", 1024, 1024], ["832 × 1216", 832, 1216], ["1216 × 832", 1216, 832],
        ]
        self._DEFAULT_RES_PRESETS = self._res_presets[:]
        self._res_preset_btns = []

        # Hires.fix
        self.hires_options_group = GroupBoxProxy(b, 'hires_options_group')
        self.upscaler_combo = ComboBoxProxy(b, 'upscaler_combo')
        self.hires_steps_input = SliderProxy(b, 'hires_steps_input')
        self.hires_denoising_input = SliderProxy(b, 'hires_denoising_input', multiplier=100)
        self.hires_denoising_input.setText('0.40')
        self.hires_scale_input = SliderProxy(b, 'hires_scale_input', multiplier=20)
        self.hires_scale_input.setText('2.00')
        self.hires_cfg_input = SliderProxy(b, 'hires_cfg_input', multiplier=2)
        self.hires_checkpoint_combo = ComboBoxProxy(b, 'hires_checkpoint_combo')
        self.hires_sampler_combo = ComboBoxProxy(b, 'hires_sampler_combo')
        self.hires_scheduler_combo = ComboBoxProxy(b, 'hires_scheduler_combo')
        self.hires_prompt_text = TextEditProxy(b, 'hires_prompt_text')
        self.hires_neg_prompt_text = TextEditProxy(b, 'hires_neg_prompt_text')

        # NegPiP / ADetailer
        self.negpip_group = GroupBoxProxy(b, 'negpip_group')
        self.adetailer_group = GroupBoxProxy(b, 'adetailer_group')
        self.ad_toggle_button = ButtonProxy(b, 'ad_toggle_button')
        self.ad_settings_container = type('WProxy', (), {
            'hide': lambda s: None, 'show': lambda s: None, 'setVisible': lambda s, v: None,
        })()
        # ADetailer 슬롯 체크박스 (Vue 연동)
        self.ad_slot1_group = CheckBoxProxy(b, 'ad_slot1_group')
        self.ad_slot2_group = CheckBoxProxy(b, 'ad_slot2_group')
        # ADetailer 슬롯 위젯 더미 (전체 키)
        def _ad_slot(prefix):
            _W = type('WProxy', (), {
                'setVisible': lambda s, v: None, 'hide': lambda s: None,
                'show': lambda s: None, 'isVisible': lambda s: False,
            })
            # SliderProxy 생성 후 기본값 설정 (Vue에도 push)
            confidence = SliderProxy(b, f'{prefix}_confidence')
            confidence.setText('0.3')
            mask_blur = SliderProxy(b, f'{prefix}_mask_blur')
            mask_blur.setText('4')
            denoise = SliderProxy(b, f'{prefix}_denoise')
            denoise.setText('0.4')
            padding = SliderProxy(b, f'{prefix}_padding')
            padding.setText('32')
            steps = SliderProxy(b, f'{prefix}_steps')
            steps.setText('28')
            cfg = SliderProxy(b, f'{prefix}_cfg')
            cfg.setText('7.0')
            dilate_erode = SliderProxy(b, f'{prefix}_dilate_erode')
            dilate_erode.setText('4')
            return {
                'prompt': TextEditProxy(b, f'{prefix}_prompt'),
                'neg_prompt': TextEditProxy(b, f'{prefix}_neg'),
                'model': ComboBoxProxy(b, f'{prefix}_model'),
                'confidence': confidence,
                'mask_blur': mask_blur,
                'denoise': denoise,
                'padding': padding,
                'steps': steps,
                'cfg': cfg,
                'dilate_erode': dilate_erode,
                'mask_merge_invert': ComboBoxProxy(b, f'{prefix}_mask_merge'),
                'use_inpaint_size_check': CheckBoxProxy(b, f'{prefix}_use_inp_size'),
                'use_steps_check': CheckBoxProxy(b, f'{prefix}_use_steps'),
                'use_cfg_check': CheckBoxProxy(b, f'{prefix}_use_cfg'),
                'use_checkpoint_check': CheckBoxProxy(b, f'{prefix}_use_ckpt'),
                'use_vae_check': CheckBoxProxy(b, f'{prefix}_use_vae'),
                'use_sampler_check': CheckBoxProxy(b, f'{prefix}_use_sampler'),
                'inpaint_size_container': _W(),
                'inpaint_width': LineEditProxy(b, f'{prefix}_inp_w'),
                'inpaint_height': LineEditProxy(b, f'{prefix}_inp_h'),
                'checkpoint_combo': ComboBoxProxy(b, f'{prefix}_ckpt'),
                'vae_combo': ComboBoxProxy(b, f'{prefix}_vae'),
                'sampler_combo': ComboBoxProxy(b, f'{prefix}_sampler'),
                'scheduler_combo': ComboBoxProxy(b, f'{prefix}_scheduler'),
                'sampler_container': _W(),
            }
        self.s1_widgets = _ad_slot('_ad_s1')
        self.s1_widgets['model'].setText('face_yolov8n.pt')
        self.s2_widgets = _ad_slot('_ad_s2')
        self.s2_widgets['model'].setText('hand_yolov8n.pt')

        self.sam3_group = GroupBoxProxy(b, 'sam3_group')
        self.sam3_toggle_button = ButtonProxy(b, 'sam3_toggle_button')
        self.sam3_settings_container = type('WProxy', (), {
            'hide': lambda s: None, 'show': lambda s: None, 'setVisible': lambda s, v: None,
        })()
        self.sam3_widgets = {
            'detect_prompt': TextEditProxy(b, '_sam3_detect_prompt'),
            'exclude_prompt': TextEditProxy(b, '_sam3_exclude_prompt'),
            'inpaint_prompt': TextEditProxy(b, '_sam3_inpaint_prompt'),
            'neg_prompt': TextEditProxy(b, '_sam3_neg_prompt'),
            'mode': ComboBoxProxy(b, '_sam3_mode'),
            'mask_mode': ComboBoxProxy(b, '_sam3_mask_mode'),
            'threshold': SliderProxy(b, '_sam3_threshold', multiplier=100),
            'mask_dilation': LineEditProxy(b, '_sam3_mask_dilation'),
            'mask_hull': CheckBoxProxy(b, '_sam3_mask_hull'),
            'mask_outline_px': LineEditProxy(b, '_sam3_mask_outline_px'),
            'mask_blur': SliderProxy(b, '_sam3_mask_blur'),
            'denoise': SliderProxy(b, '_sam3_denoise', multiplier=100),
            'padding': SliderProxy(b, '_sam3_padding'),
            'checkpoint': ComboBoxProxy(b, '_sam3_checkpoint'),
            'device': ComboBoxProxy(b, '_sam3_device'),
            'inpainting_fill': ComboBoxProxy(b, '_sam3_inpainting_fill'),
            'inpaint_only_masked': CheckBoxProxy(b, '_sam3_inpaint_only_masked'),
            'preview_overlay': CheckBoxProxy(b, '_sam3_preview_overlay'),
            'save_artifacts': CheckBoxProxy(b, '_sam3_save_artifacts'),
            'unload_after': CheckBoxProxy(b, '_sam3_unload_after'),
            'use_inpaint_size_check': CheckBoxProxy(b, '_sam3_use_inp_size'),
            'inpaint_size_container': type('WProxy', (), {
                'setVisible': lambda s, v: None, 'hide': lambda s: None, 'show': lambda s: None,
                'isVisible': lambda s: False,
            })(),
            'inpaint_width': LineEditProxy(b, '_sam3_inp_w'),
            'inpaint_height': LineEditProxy(b, '_sam3_inp_h'),
            'use_steps_check': CheckBoxProxy(b, '_sam3_use_steps'),
            'steps': SliderProxy(b, '_sam3_steps'),
            'use_cfg_check': CheckBoxProxy(b, '_sam3_use_cfg'),
            'cfg': SliderProxy(b, '_sam3_cfg', multiplier=10),
            'use_sampler_check': CheckBoxProxy(b, '_sam3_use_sampler'),
            'sampler': ComboBoxProxy(b, '_sam3_sampler'),
            'use_scheduler_check': CheckBoxProxy(b, '_sam3_use_scheduler'),
            'scheduler': ComboBoxProxy(b, '_sam3_scheduler'),
            'use_seed_check': CheckBoxProxy(b, '_sam3_use_seed'),
            'seed': LineEditProxy(b, '_sam3_seed'),
            'use_noise_multiplier_check': CheckBoxProxy(b, '_sam3_use_noise_mul'),
            'noise_multiplier': SliderProxy(b, '_sam3_noise_mul', multiplier=100),
            'restore_face': CheckBoxProxy(b, '_sam3_restore_face'),
            'sampler_container': type('WProxy', (), {
                'setVisible': lambda s, v: None, 'hide': lambda s: None, 'show': lambda s: None,
            })(),
        }
        self.sam3_widgets['threshold'].setText('0.40')
        self.sam3_widgets['mask_dilation'].setText('0')
        self.sam3_widgets['mask_outline_px'].setText('0')
        self.sam3_widgets['mask_blur'].setText('4')
        self.sam3_widgets['denoise'].setText('0.40')
        self.sam3_widgets['padding'].setText('32')
        self.sam3_widgets['checkpoint'].setText('sam3.pt')
        self.sam3_widgets['device'].setText('cuda')  # auto는 CPU로 떨어질 수 있어 검출 느려짐
        self.sam3_widgets['inpainting_fill'].setText('original')
        self.sam3_widgets['seed'].setText('-1')
        self.sam3_widgets['steps'].setText('28')
        self.sam3_widgets['cfg'].setText('7.0')
        self.sam3_widgets['noise_multiplier'].setText('1.0')
        self.sam3_widgets['save_artifacts'].setChecked(True)
        # 16GB GPU 권장 기본값 (Forge 확장 v0.6.1+ 디폴트와 동일)
        self.sam3_widgets['inpaint_only_masked'].setChecked(True)
        self.sam3_widgets['unload_after'].setChecked(True)

        # 제거 옵션
        self.chk_remove_artist = CheckBoxProxy(b, 'chk_remove_artist')
        self.chk_remove_copyright = CheckBoxProxy(b, 'chk_remove_copyright')
        self.chk_remove_character = CheckBoxProxy(b, 'chk_remove_character')
        self.chk_remove_character_features = CheckBoxProxy(b, 'chk_remove_character_features')
        self.chk_remove_meta = CheckBoxProxy(b, 'chk_remove_meta')
        self.chk_remove_censorship = CheckBoxProxy(b, 'chk_remove_censorship')
        self.chk_remove_text = CheckBoxProxy(b, 'chk_remove_text')

        # lock
        self.btn_lock_artist = CheckBoxProxy(b, 'btn_lock_artist')

    def _init_button_proxies(self):
        """하단 도구바 버튼 프록시 초기화"""
        from ui.widget_proxies import ButtonProxy, CheckBoxProxy

        b = self.vue_bridge

        self.btn_generate = ButtonProxy(b, 'btn_generate')
        self.btn_generate._text = "이미지 생성"
        self.btn_random_prompt = ButtonProxy(b, 'btn_random_prompt')
        self.btn_auto_toggle = ButtonProxy(b, 'btn_auto_toggle')
        self.btn_auto_toggle.setCheckable(True)
        self.btn_auto_toggle.toggled.connect(self.toggle_automation_ui)

        self.btn_save_settings = ButtonProxy(b, 'btn_save_settings')
        self.btn_preset_save = ButtonProxy(b, 'btn_preset_save')
        self.btn_preset_load = ButtonProxy(b, 'btn_preset_load')
        self.btn_prompt_history = ButtonProxy(b, 'btn_prompt_history')
        self.btn_lora_manager = ButtonProxy(b, 'btn_lora_manager')
        self.btn_tag_weights = ButtonProxy(b, 'btn_tag_weights')
        self.btn_shuffle = ButtonProxy(b, 'btn_shuffle')
        self.btn_ab_test = ButtonProxy(b, 'btn_ab_test')
        self.btn_api_manager = None

        self._vue_automation_settings = {
            'mode': 'count',
            'limit': 10,
            'repeat': 1,
            'delay': 1.0,
            'allowDupes': False,
            'maxRetries': 2,
        }

        def _get_vue_automation_settings():
            raw = getattr(self, '_vue_automation_settings', {}) or {}

            # PR 3: 'unlimited' 모드 추가 — 횟수/시간 제한 없이 사용자가 중지할 때까지
            mode = str(raw.get('mode', 'count'))
            if mode not in ('count', 'timer', 'unlimited'):
                mode = 'count'

            try:
                limit = float(raw.get('limit', 10))
            except (TypeError, ValueError):
                limit = 10.0

            try:
                repeat = int(raw.get('repeat', 1))
            except (TypeError, ValueError):
                repeat = 1

            try:
                delay = float(raw.get('delay', 1.0))
            except (TypeError, ValueError):
                delay = 1.0

            try:
                max_retries = int(raw.get('maxRetries', 2))
            except (TypeError, ValueError):
                max_retries = 2

            limit = max(1.0, limit)
            repeat = max(1, repeat)
            delay = max(0.0, delay)
            max_retries = max(0, min(max_retries, 10))

            if mode == 'unlimited':
                termination_limit = 0  # 무시됨
            else:
                termination_limit = int(limit) if mode == 'count' else limit * 60

            return {
                'termination_mode': mode,
                'termination_limit': termination_limit,
                'repeat_per_prompt': repeat,
                'delay': delay,
                'allow_duplicates': bool(raw.get('allowDupes', False)),
                'max_retries': max_retries,
            }

        # 자동화 위젯 (더미)
        self.automation_widget = type('AutoProxy', (), {
            'hide': lambda s: None, 'show': lambda s: None,
            'get_settings': lambda s: _get_vue_automation_settings(),
            'setVisible': lambda s, v: None,
        })()

        # LoRA 패널 (더미)
        from ui.widget_proxies import ButtonProxy as BP
        self.lora_active_panel = type('LoraProxy', (), {
            'hide': lambda s: None, 'show': lambda s: None,
            'get_active_loras': lambda s: [],
            'get_active_lora_text': lambda s: '',
            'clear_all': lambda s: None,
            'get_entries': lambda s: [],
            'set_entries': lambda s, e: None,
            'add_lora': lambda s, n, w: None,
            'parse_and_add_loras': lambda s, t: None,
        })()

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
            "artist": self.artist_input.toPlainText(),
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
            "artist":       lambda v: self.artist_input.setPlainText(v),
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
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 12px; border-radius: 3px;
            }}
            QMenu::item:selected {{ background-color: {get_color('accent')}; }}
        """)
        for i, entry in enumerate(history[:30]):
            prompt_preview = entry.get("prompt", "")[:80]
            if len(entry.get("prompt", "")) > 80:
                prompt_preview += "..."
            action = menu.addAction(f"{i+1}. {prompt_preview}")
            action.setData(entry)

        from PyQt6.QtGui import QCursor
        chosen = menu.exec(QCursor.pos())
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

    def _adjust_artist_height(self):
        """작가 입력칸 내용에 맞춰 높이 자동 조절"""
        doc = self.artist_input.document()
        doc_height = int(doc.size().height()) + 10
        new_h = max(60, min(doc_height, 200))
        current_h = self.artist_input.height()
        if abs(current_h - new_h) > 3:
            self.artist_input.setFixedHeight(new_h)

    def _create_group(self, parent_layout, title, widget_or_layout):
        """그룹 생성 헬퍼"""
        parent_layout.addWidget(QLabel(title))
        if isinstance(widget_or_layout, QWidget):
            parent_layout.addWidget(widget_or_layout)
            return widget_or_layout
        elif isinstance(widget_or_layout, QHBoxLayout):
            parent_layout.addLayout(widget_or_layout)
            return widget_or_layout
    
    def _create_separator(self):
        """구분선 생성"""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        return separator
    
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
            f"QMenu {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; }}"
            f"QMenu::item {{ padding: 6px 16px; }}"
            f"QMenu::item:selected {{ background-color: {get_color('accent')}; }}"
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
            dlg.setStyleSheet(f"background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')};")
            dl = QVBoxLayout(dlg)
            row = QHBoxLayout()
            w_spin = QSpinBox()
            w_spin.setRange(64, 4096)
            w_spin.setSingleStep(64)
            w_spin.setValue(self._res_presets[idx][1])
            w_spin.setStyleSheet(f"background:{get_color('bg_button')}; color:{get_color('text_primary')}; border:1px solid {get_color('border')}; padding:4px;")
            h_spin = QSpinBox()
            h_spin.setRange(64, 4096)
            h_spin.setSingleStep(64)
            h_spin.setValue(self._res_presets[idx][2])
            h_spin.setStyleSheet(f"background:{get_color('bg_button')}; color:{get_color('text_primary')}; border:1px solid {get_color('border')}; padding:4px;")
            swap_btn = QPushButton("⇄")
            swap_btn.setFixedSize(32, 32)
            swap_btn.setToolTip("W ↔ H 교환")
            swap_btn.setStyleSheet(
                f"background:{get_color('accent')}; color:white; border:none; "
                f"border-radius:4px; font-weight:bold; font-size:16px;"
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
        """LoRA를 활성 패널에 추가 + Vue로 전달"""
        import re, json as _json
        # 트리거 워드 분리 (||TRIGGER:[...] 포맷)
        trigger_words = []
        if '||TRIGGER:' in lora_text:
            parts = lora_text.split('||TRIGGER:', 1)
            lora_text = parts[0]
            try:
                trigger_words = _json.loads(parts[1])
            except Exception:
                pass
        m = re.match(r'<lora:(.+?):([-\d.]+)>', lora_text)
        if m:
            name, weight = m.group(1), float(m.group(2))
            self.lora_active_panel.add_lora(name, weight)
            # Vue LoRA Stack으로 전달 (트리거 워드 포함)
            if hasattr(self, 'vue_bridge'):
                payload = {'name': name, 'weight': weight}
                if trigger_words:
                    payload['trigger_words'] = trigger_words
                self.vue_bridge.loraInserted.emit(_json.dumps(payload))

    def _on_lora_batch_inserted(self, text: str):
        """다이얼로그에서 일괄 붙여넣기된 LoRA 텍스트를 패널에 추가"""
        import re
        self.lora_active_panel.parse_and_add_loras(text)
        # Vue로도 전달
        if hasattr(self, 'vue_bridge'):
            import json as _json
            for m in re.finditer(r'<lora:(.+?):([-\d.]+)>', text):
                self.vue_bridge.loraInserted.emit(_json.dumps({'name': m.group(1), 'weight': float(m.group(2))}))

    def _update_token_count(self):
        """최종 프롬프트 토큰 수 추정 (CLIP 기준 근사)"""
        import re
        text = self.total_prompt_display.toPlainText().strip()

        if not text:
            self.token_count_label.setText("토큰: 0 / 75")
            self.token_count_label.setStyleSheet(
                f"color: {get_color('text_muted')}; font-size: 11px; font-weight: bold; padding: 0 4px;"
            )
            return

        # CLIP 토큰 근사: 단어/서브워드 기준 (영어 ~0.75 토큰/단어, 태그 ~1 토큰/태그)
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
        header_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {get_color('accent')};")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        self.btn_fav_refresh = QPushButton("🔄 새로고침")
        self.btn_fav_refresh.clicked.connect(self.refresh_favorites)
        self.btn_fav_refresh.setStyleSheet(
            f"padding: 5px 10px; background-color: {get_color('bg_button')}; border-radius: 4px;"
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
        scroll.setStyleSheet(f"border: none; background: {get_color('bg_primary')};")
        
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

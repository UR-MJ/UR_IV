# tabs/upscale_tab.py
import os
from enum import IntEnum
import requests
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QComboBox, QListWidget, QGroupBox, QRadioButton, QButtonGroup,
    QProgressBar, QFileDialog, QMessageBox, QSplitter, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from widgets.sliders import NumericSlider
from workers.upscale_worker import BatchUpscaleWorker
from config import WEBUI_API_URL
from utils.theme_manager import get_color


class ProcessMode(IntEnum):
    """upscale_tab의 처리 모드 — 라디오 버튼 id와 1:1 대응."""
    UPSCALE_ONLY = 0
    ADETAILER_ONLY = 1
    SAM3_ONLY = 2
    BOTH = 3

    @property
    def slug(self) -> str:
        return {
            ProcessMode.UPSCALE_ONLY: "upscale_only",
            ProcessMode.ADETAILER_ONLY: "adetailer_only",
            ProcessMode.SAM3_ONLY: "sam3_only",
            ProcessMode.BOTH: "both",
        }[self]


class UpscaleTab(QWidget):
    """업스케일 + ADetailer/SAM3 탭"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        self._worker = None
        self._upscaler_list = []
        self._init_ui()
        self.setAcceptDrops(True)

    def _init_ui(self):
        """UI 초기화"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── 상단: 파일 입력 버튼 ──
        input_toolbar = QHBoxLayout()
        self.btn_open_files = QPushButton("📂 파일 열기")
        self.btn_open_folder = QPushButton("📁 폴더 열기")
        self.btn_clear = QPushButton("❌ 초기화")
        self.btn_load_upscalers = QPushButton("🔄 업스케일러 로드")

        for btn in [self.btn_open_files, self.btn_open_folder, self.btn_clear, self.btn_load_upscalers]:
            btn.setFixedHeight(35)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(
                f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
                "border-radius: 4px; font-size: 13px; font-weight: bold;"
            )

        self.lbl_count = QLabel("입력: 0개")
        self.lbl_count.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 12px;")

        input_toolbar.addWidget(self.btn_open_files)
        input_toolbar.addWidget(self.btn_open_folder)
        input_toolbar.addWidget(self.btn_clear)
        input_toolbar.addWidget(self.btn_load_upscalers)
        input_toolbar.addStretch()
        input_toolbar.addWidget(self.lbl_count)
        layout.addLayout(input_toolbar)

        # ── 중간: 파일 목록 + 설정 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 파일 목록
        self.file_list = QListWidget()
        self.file_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {get_color('bg_primary')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')};
                border-radius: 4px; font-size: 12px;
            }}
        """)
        splitter.addWidget(self.file_list)

        # 설정 패널
        settings_widget = QWidget()
        sl = QVBoxLayout(settings_widget)
        sl.setContentsMargins(5, 0, 0, 0)
        sl.setSpacing(8)

        # 업스케일러 선택
        upscaler_row = QHBoxLayout()
        upscaler_label = QLabel("업스케일러:")
        upscaler_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 13px; font-weight: bold;")
        self.combo_upscaler = QComboBox()
        self.combo_upscaler.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 6px; font-size: 12px;"
        )
        self.combo_upscaler.addItem("(로드 필요)")
        upscaler_row.addWidget(upscaler_label)
        upscaler_row.addWidget(self.combo_upscaler, 1)
        sl.addLayout(upscaler_row)

        # 스케일 모드
        scale_group = QGroupBox("스케일 모드")
        scale_group.setStyleSheet(f"""
            QGroupBox {{ border: 1px solid {get_color('border')}; border-radius: 6px;
                        margin-top: 12px; padding-top: 18px;
                        font-weight: bold; color: {get_color('text_muted')}; }}
            QGroupBox::title {{ subcontrol-origin: margin; padding: 0 6px; }}
        """)
        sg_layout = QVBoxLayout(scale_group)

        self.radio_factor = QRadioButton("배율")
        self.radio_factor.setChecked(True)
        self.radio_factor.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 13px;")
        self.radio_size = QRadioButton("크기 지정")
        self.radio_size.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 13px;")

        self.scale_btn_group = QButtonGroup(self)
        self.scale_btn_group.addButton(self.radio_factor, 0)
        self.scale_btn_group.addButton(self.radio_size, 1)

        self.slider_scale_factor = NumericSlider("배율", 1, 8, 2)
        self.spin_target_w = NumericSlider("W", 64, 8192, 1024)
        self.spin_target_h = NumericSlider("H", 64, 8192, 1024)

        size_row = QHBoxLayout()
        size_row.addWidget(self.spin_target_w)
        size_row.addWidget(self.spin_target_h)
        self.size_container = QWidget()
        self.size_container.setLayout(size_row)
        self.size_container.hide()

        sg_layout.addWidget(self.radio_factor)
        sg_layout.addWidget(self.slider_scale_factor)
        sg_layout.addWidget(self.radio_size)
        sg_layout.addWidget(self.size_container)
        sl.addWidget(scale_group)

        # 처리 모드
        mode_group = QGroupBox("처리 모드")
        mode_group.setStyleSheet(f"""
            QGroupBox {{ border: 1px solid {get_color('border')}; border-radius: 6px;
                        margin-top: 12px; padding-top: 18px;
                        font-weight: bold; color: {get_color('text_muted')}; }}
            QGroupBox::title {{ subcontrol-origin: margin; padding: 0 6px; }}
        """)
        mg_layout = QVBoxLayout(mode_group)

        self.radio_upscale_only = QRadioButton("업스케일만")
        self.radio_upscale_only.setChecked(True)
        self.radio_upscale_only.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 13px;")
        self.radio_ad_only = QRadioButton("ADetailer만")
        self.radio_ad_only.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 13px;")
        self.radio_sam3_only = QRadioButton("SAM3만")
        self.radio_sam3_only.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 13px;")
        self.radio_both = QRadioButton("둘 다 (업스케일 → ADetailer → SAM3)")
        self.radio_both.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 13px;")

        self.mode_btn_group = QButtonGroup(self)
        self.mode_btn_group.addButton(self.radio_upscale_only, int(ProcessMode.UPSCALE_ONLY))
        self.mode_btn_group.addButton(self.radio_ad_only, int(ProcessMode.ADETAILER_ONLY))
        self.mode_btn_group.addButton(self.radio_sam3_only, int(ProcessMode.SAM3_ONLY))
        self.mode_btn_group.addButton(self.radio_both, int(ProcessMode.BOTH))

        mg_layout.addWidget(self.radio_upscale_only)
        mg_layout.addWidget(self.radio_ad_only)
        mg_layout.addWidget(self.radio_sam3_only)
        mg_layout.addWidget(self.radio_both)
        sl.addWidget(mode_group)

        # ADetailer 설정 (접이식)
        self.ad_group = QGroupBox("ADetailer 설정")
        self.ad_group.setCheckable(True)
        self.ad_group.setChecked(False)
        self.ad_group.setStyleSheet(f"""
            QGroupBox {{ border: 1px solid {get_color('border')}; border-radius: 6px;
                        margin-top: 12px; padding-top: 18px;
                        font-weight: bold; color: {get_color('text_muted')}; }}
            QGroupBox::title {{ subcontrol-origin: margin; padding: 0 6px; }}
            QGroupBox::indicator {{ width: 16px; height: 16px; }}
        """)
        ad_layout = QVBoxLayout(self.ad_group)

        ad_model_row = QHBoxLayout()
        ad_model_label = QLabel("모델:")
        ad_model_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        self.txt_ad_model = QLineEdit("face_yolov8s.pt")
        self.txt_ad_model.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        ad_model_row.addWidget(ad_model_label)
        ad_model_row.addWidget(self.txt_ad_model)
        ad_layout.addLayout(ad_model_row)

        self.slider_ad_denoise = NumericSlider("Denoise", 1, 100, 25)
        self.slider_ad_confidence = NumericSlider("Confidence", 1, 100, 30)
        ad_layout.addWidget(self.slider_ad_denoise)
        ad_layout.addWidget(self.slider_ad_confidence)

        ad_prompt_row = QHBoxLayout()
        ad_prompt_label = QLabel("Prompt:")
        ad_prompt_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        self.txt_ad_prompt = QLineEdit()
        self.txt_ad_prompt.setPlaceholderText("(비워두면 원본 유지)")
        self.txt_ad_prompt.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        ad_prompt_row.addWidget(ad_prompt_label)
        ad_prompt_row.addWidget(self.txt_ad_prompt)
        ad_layout.addLayout(ad_prompt_row)

        sl.addWidget(self.ad_group)

        # SAM3 설정
        self.sam3_group = QGroupBox("SAM3 설정")
        self.sam3_group.setCheckable(True)
        self.sam3_group.setChecked(False)
        self.sam3_group.setStyleSheet(f"""
            QGroupBox {{ border: 1px solid {get_color('border')}; border-radius: 6px;
                        margin-top: 12px; padding-top: 18px;
                        font-weight: bold; color: {get_color('text_muted')}; }}
            QGroupBox::title {{ subcontrol-origin: margin; padding: 0 6px; }}
            QGroupBox::indicator {{ width: 16px; height: 16px; }}
        """)
        sam3_layout = QVBoxLayout(self.sam3_group)

        sam3_prompt_row = QHBoxLayout()
        sam3_prompt_label = QLabel("Detect:")
        sam3_prompt_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        self.txt_sam3_prompt = QLineEdit("face")
        self.txt_sam3_prompt.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        sam3_prompt_row.addWidget(sam3_prompt_label)
        sam3_prompt_row.addWidget(self.txt_sam3_prompt)
        sam3_layout.addLayout(sam3_prompt_row)

        sam3_inpaint_row = QHBoxLayout()
        sam3_inpaint_label = QLabel("Inpaint:")
        sam3_inpaint_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        self.txt_sam3_inpaint_prompt = QLineEdit()
        self.txt_sam3_inpaint_prompt.setPlaceholderText("(비워두면 원본 프롬프트 유지)")
        self.txt_sam3_inpaint_prompt.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        sam3_inpaint_row.addWidget(sam3_inpaint_label)
        sam3_inpaint_row.addWidget(self.txt_sam3_inpaint_prompt)
        sam3_layout.addLayout(sam3_inpaint_row)

        self.slider_sam3_threshold = NumericSlider("Threshold", 1, 100, 40)
        self.slider_sam3_denoise = NumericSlider("Denoise", 1, 100, 40)
        self.slider_sam3_mask_blur = NumericSlider("Mask Blur", 0, 64, 8)
        self.slider_sam3_padding = NumericSlider("Padding", 0, 256, 32)
        sam3_layout.addWidget(self.slider_sam3_threshold)
        sam3_layout.addWidget(self.slider_sam3_denoise)
        sam3_layout.addWidget(self.slider_sam3_mask_blur)
        sam3_layout.addWidget(self.slider_sam3_padding)

        sam3_checkpoint_row = QHBoxLayout()
        sam3_checkpoint_label = QLabel("Checkpoint:")
        sam3_checkpoint_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        self.txt_sam3_checkpoint = QLineEdit("sam3.pt")
        self.txt_sam3_checkpoint.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        sam3_checkpoint_row.addWidget(sam3_checkpoint_label)
        sam3_checkpoint_row.addWidget(self.txt_sam3_checkpoint)
        sam3_layout.addLayout(sam3_checkpoint_row)

        sam3_mode_row = QHBoxLayout()
        sam3_mode_label = QLabel("Mask:")
        sam3_mode_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        self.combo_sam3_mask_mode = QComboBox()
        self.combo_sam3_mask_mode.addItems(["Individual", "Combined"])
        self.combo_sam3_mask_mode.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px; font-size: 12px;"
        )
        self.chk_sam3_preview = QCheckBox("Overlay Preview")
        self.chk_sam3_preview.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 12px;")
        self.chk_sam3_save_artifacts = QCheckBox("Artifacts 저장")
        self.chk_sam3_save_artifacts.setChecked(True)
        self.chk_sam3_save_artifacts.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 12px;")
        sam3_mode_row.addWidget(sam3_mode_label)
        sam3_mode_row.addWidget(self.combo_sam3_mask_mode, 1)
        sam3_mode_row.addWidget(self.chk_sam3_preview)
        sam3_mode_row.addWidget(self.chk_sam3_save_artifacts)
        sam3_layout.addLayout(sam3_mode_row)

        self.chk_sam3_use_inpaint_size = QCheckBox("별도의 너비/높이 사용")
        self.chk_sam3_use_inpaint_size.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 12px;")
        sam3_layout.addWidget(self.chk_sam3_use_inpaint_size)

        sam3_size_row = QHBoxLayout()
        self.spin_sam3_width = NumericSlider("W", 64, 2048, 1024)
        self.spin_sam3_height = NumericSlider("H", 64, 2048, 1024)
        sam3_size_row.addWidget(self.spin_sam3_width)
        sam3_size_row.addWidget(self.spin_sam3_height)
        self.sam3_size_container = QWidget()
        self.sam3_size_container.setLayout(sam3_size_row)
        self.sam3_size_container.hide()
        sam3_layout.addWidget(self.sam3_size_container)

        sl.addWidget(self.sam3_group)
        sl.addStretch()

        splitter.addWidget(settings_widget)
        splitter.setSizes([250, 450])
        layout.addWidget(splitter, stretch=1)

        # ── 출력 폴더 ──
        output_row = QHBoxLayout()
        output_label = QLabel("출력 폴더:")
        output_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 13px; font-weight: bold;")
        self.txt_output_folder = QLineEdit()
        self.txt_output_folder.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 6px; font-size: 12px;"
        )
        self.txt_output_folder.setReadOnly(True)
        self.btn_select_output = QPushButton("📁 선택")
        self.btn_select_output.setFixedHeight(35)
        self.btn_select_output.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_select_output.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 13px; font-weight: bold;"
        )
        self.btn_open_output = QPushButton("📂 열기")
        self.btn_open_output.setFixedHeight(35)
        self.btn_open_output.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_open_output.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 13px; font-weight: bold;"
        )

        output_row.addWidget(output_label)
        output_row.addWidget(self.txt_output_folder, 1)
        output_row.addWidget(self.btn_select_output)
        output_row.addWidget(self.btn_open_output)
        layout.addLayout(output_row)

        # ── 진행률 ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')};
                           border-radius: 4px; text-align: center; color: {get_color('text_primary')}; font-size: 12px; }}
            QProgressBar::chunk {{ background-color: #5865F2; border-radius: 3px; }}
        """)
        self.progress_bar.setValue(0)
        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 12px;")

        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.lbl_progress)
        layout.addLayout(progress_row)

        # ── 실행 버튼 ──
        action_row = QHBoxLayout()
        self.btn_start = QPushButton("🚀 처리 시작")
        self.btn_start.setFixedHeight(40)
        self.btn_start.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_start.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 6px; "
            "font-size: 14px; font-weight: bold;"
        )
        self.btn_stop = QPushButton("⏹ 중지")
        self.btn_stop.setFixedHeight(40)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stop.setStyleSheet(
            "background-color: #8B0000; color: white; border-radius: 6px; "
            "font-size: 14px; font-weight: bold;"
        )

        action_row.addWidget(self.btn_start, 3)
        action_row.addWidget(self.btn_stop, 1)
        layout.addLayout(action_row)

        # ── 시그널 연결 ──
        self.btn_open_files.clicked.connect(self._open_files)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.btn_clear.clicked.connect(self._clear_input)
        self.btn_load_upscalers.clicked.connect(self._load_upscaler_list)
        self.btn_select_output.clicked.connect(self._select_output_folder)
        self.btn_open_output.clicked.connect(self._open_output_folder)
        self.btn_start.clicked.connect(self._start_processing)
        self.btn_stop.clicked.connect(self._stop_processing)

        self.radio_factor.toggled.connect(self._on_scale_mode_changed)
        self.radio_ad_only.toggled.connect(self._on_mode_changed)
        self.radio_sam3_only.toggled.connect(self._on_mode_changed)
        self.radio_both.toggled.connect(self._on_mode_changed)
        self.chk_sam3_use_inpaint_size.toggled.connect(self.sam3_size_container.setVisible)

    # ── 이미지 입력 ──

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                self._add_file(path)
            elif os.path.isdir(path):
                self._add_folder(path)
        self._update_count()

    def _open_files(self):
        """파일 선택 다이얼로그"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "이미지 선택", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        for p in paths:
            self._add_file(p)
        self._update_count()

    def _open_folder(self):
        """폴더 선택 → 내부 이미지 모두 추가"""
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if folder:
            self._add_folder(folder)
            self._update_count()

    def _add_file(self, path: str):
        """파일 목록에 추가 (중복 방지)"""
        for i in range(self.file_list.count()):
            if self.file_list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                return
        item = self.file_list.addItem(os.path.basename(path))
        self.file_list.item(self.file_list.count() - 1).setData(Qt.ItemDataRole.UserRole, path)

    def _add_folder(self, folder: str):
        """폴더 내 이미지 재귀 추가"""
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                    self._add_file(os.path.join(root, f))

    def _clear_input(self):
        """입력 목록 초기화"""
        self.file_list.clear()
        self._update_count()

    def _update_count(self):
        """파일 수 표시 갱신"""
        self.lbl_count.setText(f"입력: {self.file_list.count()}개")

    # ── 업스케일러 로드 ──

    def _load_upscaler_list(self):
        """WebUI API에서 업스케일러 목록 가져오기"""
        try:
            response = requests.get(
                f'{WEBUI_API_URL}/sdapi/v1/upscalers',
                headers={"accept": "application/json"}, timeout=10
            )
            response.raise_for_status()
            upscalers = response.json()
            self._upscaler_list = [u['name'] for u in upscalers if isinstance(u, dict) and 'name' in u]
            self.combo_upscaler.clear()
            self.combo_upscaler.addItems(self._upscaler_list)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"업스케일러 목록 로드 실패:\n{e}")

    # ── UI 상태 ──

    def _on_scale_mode_changed(self):
        """스케일 모드 토글"""
        if self.radio_factor.isChecked():
            self.slider_scale_factor.show()
            self.size_container.hide()
        else:
            self.slider_scale_factor.hide()
            self.size_container.show()

    def _on_mode_changed(self):
        """처리 모드 변경 시 후처리 그룹 자동 활성화"""
        if self.radio_ad_only.isChecked() or self.radio_both.isChecked():
            self.ad_group.setChecked(True)
        if self.radio_sam3_only.isChecked() or self.radio_both.isChecked():
            self.sam3_group.setChecked(True)

    # ── 출력 폴더 ──

    def _select_output_folder(self):
        """출력 폴더 선택"""
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if folder:
            self.txt_output_folder.setText(folder)

    def _open_output_folder(self):
        """출력 폴더 탐색기에서 열기"""
        folder = self.txt_output_folder.text()
        if folder and os.path.isdir(folder):
            os.startfile(folder)

    # ── 처리 ──

    def _get_settings(self) -> dict:
        """현재 UI에서 설정 딕셔너리 생성"""
        try:
            mode = ProcessMode(self.mode_btn_group.checkedId()).slug
        except ValueError:
            mode = ProcessMode.UPSCALE_ONLY.slug

        return {
            'mode': mode,
            'upscaler_name': self.combo_upscaler.currentText(),
            'scale_mode': 'factor' if self.radio_factor.isChecked() else 'size',
            'scale_factor': self.slider_scale_factor.value(),
            'target_width': self.spin_target_w.value(),
            'target_height': self.spin_target_h.value(),
            'ad_model': self.txt_ad_model.text(),
            'ad_confidence': self.slider_ad_confidence.value() / 100.0,
            'ad_denoise': self.slider_ad_denoise.value() / 100.0,
            'ad_prompt': self.txt_ad_prompt.text(),
            'ad_enabled': self.ad_group.isChecked(),
            'sam3_enabled': self.sam3_group.isChecked(),
            'sam3_mode': 'Inpaint',
            'sam3_mask_mode': self.combo_sam3_mask_mode.currentText(),
            'sam3_prompt': self.txt_sam3_prompt.text().strip() or 'face',
            'sam3_inpaint_prompt': self.txt_sam3_inpaint_prompt.text(),
            'sam3_threshold': self.slider_sam3_threshold.value() / 100.0,
            'sam3_checkpoint': self.txt_sam3_checkpoint.text().strip() or 'sam3.pt',
            'sam3_mask_blur': int(self.slider_sam3_mask_blur.value()),
            'sam3_denoising_strength': self.slider_sam3_denoise.value() / 100.0,
            'sam3_inpaint_only_masked': True,
            'sam3_inpaint_only_masked_padding': int(self.slider_sam3_padding.value()),
            'sam3_use_inpaint_width_height': self.chk_sam3_use_inpaint_size.isChecked(),
            'sam3_inpaint_width': int(self.spin_sam3_width.value()),
            'sam3_inpaint_height': int(self.spin_sam3_height.value()),
            'sam3_preview_overlay': self.chk_sam3_preview.isChecked(),
            'sam3_save_artifacts': self.chk_sam3_save_artifacts.isChecked(),
            'output_folder': self.txt_output_folder.text(),
        }

    def _vue_notify(self, kind, msg):
        mw = getattr(self, 'main_window', None)
        if mw and hasattr(mw, 'vue_bridge'):
            try:
                mw.vue_bridge.showNotification.emit(kind, msg)
            except Exception:
                pass

    def start_from_payload(self, payload: dict):
        """Vue BatchView 업스케일 페이로드로 처리 (files + upscaler + scale).
        업스케일러/배율은 가능하면 네이티브 컨트롤에 반영, 출력 폴더는 미설정 시 OUTPUT_DIR."""
        files = [p for p in (payload.get('files') or []) if p]
        if not files:
            self._vue_notify('error', '업스케일: 처리할 파일이 없습니다')
            return
        self.file_list.clear()
        for p in files:
            self._add_file(p)
        # 업스케일러/배율을 네이티브 컨트롤에 best-effort 반영
        try:
            up = payload.get('upscaler')
            if up and hasattr(self, 'combo_upscaler'):
                idx = self.combo_upscaler.findText(up)
                if idx >= 0:
                    self.combo_upscaler.setCurrentIndex(idx)
            sc = payload.get('scale')
            if sc and hasattr(self, 'spin_scale'):
                self.spin_scale.setValue(float(sc))
        except Exception:
            pass
        # 출력 폴더 기본값
        try:
            if not self.txt_output_folder.text().strip():
                import os as _os
                from config import OUTPUT_DIR
                _os.makedirs(OUTPUT_DIR, exist_ok=True)
                self.txt_output_folder.setText(OUTPUT_DIR)
        except Exception:
            pass
        self._start_processing()
        if getattr(self, '_worker', None) is not None:
            self._worker.all_finished.connect(lambda *a: self._vue_notify('success', '업스케일 완료'))
        self._vue_notify('info', f'업스케일 시작: {len(files)}개')

    def _start_processing(self):
        """처리 시작"""
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "알림", "입력 파일을 추가하세요.")
            return

        output_folder = self.txt_output_folder.text()
        if not output_folder or not os.path.isdir(output_folder):
            QMessageBox.warning(self, "알림", "출력 폴더를 선택하세요.")
            return

        settings = self._get_settings()

        # 파일 경로 수집
        paths = []
        for i in range(self.file_list.count()):
            path = self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            if path:
                paths.append(path)

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setMaximum(len(paths))
        self.progress_bar.setValue(0)

        self._cleanup_worker()
        self._worker = BatchUpscaleWorker(paths, settings)
        self._worker.progress.connect(self._on_progress)
        self._worker.single_finished.connect(self._on_single_finished)
        self._worker.all_finished.connect(self._on_all_finished)
        self._worker.start()

    def _cleanup_worker(self):
        """이전 BatchUpscaleWorker가 남아 있으면 시그널 해제 + 종료."""
        worker = getattr(self, '_worker', None)
        if worker is None:
            return
        for sig_name in ('progress', 'single_finished', 'all_finished'):
            try:
                sig = getattr(worker, sig_name, None)
                if sig is not None:
                    sig.disconnect()
            except (TypeError, RuntimeError):
                pass
        try:
            if worker.isRunning():
                worker.request_stop()
                worker.quit()
                worker.wait(2000)
        except RuntimeError:
            pass
        self._worker = None

    def _stop_processing(self):
        """처리 중지"""
        if self._worker:
            self._worker.request_stop()

    def _on_progress(self, current: int, total: int):
        """진행률 업데이트"""
        self.progress_bar.setValue(current)
        self.lbl_progress.setText(f"{current}/{total}")

    def _on_single_finished(self, index: int, success: bool, message: str):
        """단일 이미지 처리 완료"""
        item = self.file_list.item(index)
        if item:
            status = "✅" if success else "❌"
            item.setText(f"{status} {item.text()}")

    def _on_all_finished(self):
        """전체 처리 완료"""
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._worker = None
        QMessageBox.information(self, "완료", "모든 이미지 처리가 완료되었습니다.")

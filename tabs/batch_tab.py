# tabs/batch_tab.py
"""일괄 후처리 탭 — 리사이즈/포맷변환/워터마크/필터"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QFileDialog, QComboBox, QStackedWidget,
    QProgressBar, QMessageBox, QFrame, QAbstractItemView
)
from PyQt6.QtCore import Qt
from widgets.sliders import NumericSlider
from widgets.common_widgets import NoScrollSpinBox, NoScrollComboBox
from utils.theme_manager import get_color


class BatchTab(QWidget):
    """일괄 후처리 탭"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ═══ 좌측: 파일 목록 ═══
        left = QVBoxLayout()
        left.setSpacing(6)

        file_header = QLabel("처리할 파일")
        file_header.setStyleSheet(
            f"color: {get_color('text_secondary')}; font-size: 16px; font-weight: bold;"
        )
        left.addWidget(file_header)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setStyleSheet(
            f"QListWidget {{ background: {get_color('bg_primary')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 12px; }"
            "QListWidget::item { padding: 4px; }"
            "QListWidget::item:selected { background: #5865F2; }"
        )
        self.file_list.setAcceptDrops(True)
        left.addWidget(self.file_list, 1)

        # 파일 관리 버튼
        file_btn_row = QHBoxLayout()
        file_btn_row.setSpacing(4)

        _btn_style = (
            f"QPushButton {{ background: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 12px; font-weight: bold; }"
            f"QPushButton:hover {{ background: {get_color('bg_button_hover')}; }}"
        )

        btn_add_files = QPushButton("📂 파일 추가")
        btn_add_files.setFixedHeight(34)
        btn_add_files.setStyleSheet(_btn_style)
        btn_add_files.clicked.connect(self._add_files)

        btn_add_folder = QPushButton("📁 폴더 추가")
        btn_add_folder.setFixedHeight(34)
        btn_add_folder.setStyleSheet(_btn_style)
        btn_add_folder.clicked.connect(self._add_folder)

        btn_remove = QPushButton("🗑️ 선택 제거")
        btn_remove.setFixedHeight(34)
        btn_remove.setStyleSheet(_btn_style)
        btn_remove.clicked.connect(self._remove_selected)

        btn_clear = QPushButton("❌ 전체 비우기")
        btn_clear.setFixedHeight(34)
        btn_clear.setStyleSheet(_btn_style)
        btn_clear.clicked.connect(lambda: self.file_list.clear())

        file_btn_row.addWidget(btn_add_files)
        file_btn_row.addWidget(btn_add_folder)
        file_btn_row.addWidget(btn_remove)
        file_btn_row.addWidget(btn_clear)
        left.addLayout(file_btn_row)

        self.file_count_label = QLabel("0개 파일")
        self.file_count_label.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 11px;")
        left.addWidget(self.file_count_label)

        main_layout.addLayout(left, 3)

        # ═══ 우측: 작업 설정 ═══
        right = QVBoxLayout()
        right.setSpacing(8)

        op_header = QLabel("작업 설정")
        op_header.setStyleSheet(
            f"color: {get_color('text_secondary')}; font-size: 16px; font-weight: bold;"
        )
        right.addWidget(op_header)

        # 작업 유형 선택
        self.op_combo = NoScrollComboBox()
        self.op_combo.addItems(["리사이즈", "포맷 변환", "필터 적용", "워터마크"])
        self.op_combo.setFixedHeight(34)
        self.op_combo.setStyleSheet(
            f"background: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 13px; padding: 4px 8px;"
        )
        self.op_combo.currentIndexChanged.connect(self._on_op_changed)
        right.addWidget(self.op_combo)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {get_color('border')};")
        right.addWidget(line)

        # 작업별 설정 스택
        self.config_stack = QStackedWidget()
        self._create_resize_config()
        self._create_format_config()
        self._create_filter_config()
        self._create_watermark_config()
        right.addWidget(self.config_stack, 1)

        # 출력 폴더
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"color: {get_color('border')};")
        right.addWidget(line2)

        out_row = QHBoxLayout()
        out_label = QLabel("출력 폴더:")
        out_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 12px;")
        out_row.addWidget(out_label)

        self.output_path_label = QLabel("(선택 안 됨)")
        self.output_path_label.setStyleSheet(
            f"color: {get_color('text_primary')}; font-size: 12px; background: {get_color('bg_input')}; "
            f"border: 1px solid {get_color('border')}; border-radius: 4px; padding: 4px 8px;"
        )
        out_row.addWidget(self.output_path_label, 1)

        btn_out = QPushButton("📁")
        btn_out.setFixedSize(34, 34)
        btn_out.setStyleSheet(_btn_style)
        btn_out.clicked.connect(self._select_output_dir)
        out_row.addWidget(btn_out)
        right.addLayout(out_row)

        self._output_dir = ""

        # 프로그레스
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(24)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {get_color('bg_primary')}; border: 1px solid {get_color('border')};
                border-radius: 4px; text-align: center;
                color: {get_color('text_primary')}; font-size: 12px;
            }}
            QProgressBar::chunk {{ background: #5865F2; border-radius: 3px; }}
        """)
        self.progress_bar.setValue(0)
        right.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 11px;")
        right.addWidget(self.status_label)

        # 시작/취소 버튼
        action_row = QHBoxLayout()
        self.btn_start = QPushButton("▶ 시작")
        self.btn_start.setFixedHeight(40)
        self.btn_start.setStyleSheet(
            "QPushButton { background: #5865F2; color: white; border-radius: 6px; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #6975F3; }"
            f"QPushButton:disabled {{ background: {get_color('bg_button')}; color: {get_color('text_muted')}; }}"
        )
        self.btn_start.clicked.connect(self._start_batch)

        self.btn_cancel = QPushButton("■ 취소")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #8B0000; color: white; border-radius: 6px; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #A52A2A; }"
            f"QPushButton:disabled {{ background: {get_color('bg_button')}; color: {get_color('text_muted')}; }}"
        )
        self.btn_cancel.clicked.connect(self._cancel_batch)

        action_row.addWidget(self.btn_start, 2)
        action_row.addWidget(self.btn_cancel, 1)
        right.addLayout(action_row)

        main_layout.addLayout(right, 2)

    # ── 설정 패널 생성 ──

    def _create_resize_config(self):
        """리사이즈 설정"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.resize_mode_combo = NoScrollComboBox()
        self.resize_mode_combo.addItems(["고정 크기", "비율(%)", "장축 기준"])
        self.resize_mode_combo.setFixedHeight(30)
        self.resize_mode_combo.setStyleSheet(
            f"background: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 12px; padding: 2px 6px;"
        )
        layout.addWidget(self.resize_mode_combo)

        self.resize_width = NumericSlider("폭 (W)", 1, 8192, 1024)
        self.resize_height = NumericSlider("높이 (H)", 1, 8192, 1024)
        self.resize_percent = NumericSlider("비율 %", 1, 500, 100)
        self.resize_longest = NumericSlider("장축 px", 64, 8192, 1024)

        layout.addWidget(self.resize_width)
        layout.addWidget(self.resize_height)
        layout.addWidget(self.resize_percent)
        layout.addWidget(self.resize_longest)
        layout.addStretch()

        self.config_stack.addWidget(w)

    def _create_format_config(self):
        """포맷 변환 설정"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("출력 포맷:"))
        self.format_combo = NoScrollComboBox()
        self.format_combo.addItems(["PNG (.png)", "JPEG (.jpg)", "WebP (.webp)"])
        self.format_combo.setFixedHeight(30)
        self.format_combo.setStyleSheet(
            f"background: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 12px; padding: 2px 6px;"
        )
        layout.addWidget(self.format_combo)

        self.format_quality = NumericSlider("품질", 1, 100, 95)
        layout.addWidget(self.format_quality)

        layout.addStretch()
        self.config_stack.addWidget(w)

    def _create_filter_config(self):
        """필터 적용 설정"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("적용할 필터:"))
        self.filter_combo = NoScrollComboBox()
        filters = [
            "grayscale — 흑백",
            "sepia — 세피아",
            "sharpen — 선명하게",
            "warm — 따뜻하게",
            "cool — 차갑게",
            "soft — 소프트",
            "invert — 반전",
            "emboss — 엠보스",
            "sketch — 스케치",
            "posterize — 포스터",
            "vignette — 비네트",
            "denoise — 노이즈 제거",
        ]
        for f in filters:
            self.filter_combo.addItem(f, f.split(" — ")[0])
        self.filter_combo.setFixedHeight(30)
        self.filter_combo.setStyleSheet(
            f"background: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 12px; padding: 2px 6px;"
        )
        layout.addWidget(self.filter_combo)

        layout.addStretch()
        self.config_stack.addWidget(w)

    def _create_watermark_config(self):
        """워터마크 설정"""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("워터마크 텍스트:"))
        from PyQt6.QtWidgets import QLineEdit
        self.wm_text_input = QLineEdit()
        self.wm_text_input.setPlaceholderText("워터마크 텍스트 입력")
        self.wm_text_input.setStyleSheet(
            f"background: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 6px; font-size: 13px;"
        )
        layout.addWidget(self.wm_text_input)

        self.wm_font_size = NumericSlider("크기", 8, 200, 24)
        layout.addWidget(self.wm_font_size)

        self.wm_opacity = NumericSlider("투명도 %", 1, 100, 50)
        layout.addWidget(self.wm_opacity)

        layout.addWidget(QLabel("위치:"))
        self.wm_position_combo = NoScrollComboBox()
        self.wm_position_combo.addItems([
            "중앙", "좌상", "우상", "좌하", "우하"
        ])
        self.wm_position_combo.setFixedHeight(30)
        self.wm_position_combo.setStyleSheet(
            f"background: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 12px; padding: 2px 6px;"
        )
        layout.addWidget(self.wm_position_combo)

        layout.addStretch()
        self.config_stack.addWidget(w)

    # ── 파일 관리 ──

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "이미지 파일 추가", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        for p in paths:
            if not self._file_exists(p):
                self.file_list.addItem(p)
        self._update_file_count()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if folder:
            exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
            for f in os.listdir(folder):
                if f.lower().endswith(exts):
                    full = os.path.join(folder, f)
                    if not self._file_exists(full):
                        self.file_list.addItem(full)
            self._update_file_count()

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self._update_file_count()

    def _file_exists(self, path: str) -> bool:
        for i in range(self.file_list.count()):
            if self.file_list.item(i).text() == path:
                return True
        return False

    def _update_file_count(self):
        self.file_count_label.setText(f"{self.file_list.count()}개 파일")

    def _select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if folder:
            self._output_dir = folder
            self.output_path_label.setText(folder)

    def _on_op_changed(self, index: int):
        self.config_stack.setCurrentIndex(index)

    # ── 배치 실행 ──

    def _get_file_list(self) -> list:
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]

    def _build_config(self) -> tuple:
        """(operation, config) 반환"""
        idx = self.op_combo.currentIndex()

        if idx == 0:  # 리사이즈
            mode_idx = self.resize_mode_combo.currentIndex()
            modes = ['fixed', 'percent', 'longest']
            config = {
                'mode': modes[mode_idx],
                'width': self.resize_width.value(),
                'height': self.resize_height.value(),
                'percent': self.resize_percent.value(),
                'longest': self.resize_longest.value(),
            }
            return 'resize', config

        elif idx == 1:  # 포맷 변환
            fmt_map = ['.png', '.jpg', '.webp']
            config = {
                'target_format': fmt_map[self.format_combo.currentIndex()],
                'quality': self.format_quality.value(),
            }
            return 'format', config

        elif idx == 2:  # 필터
            config = {
                'filter_name': self.filter_combo.currentData(),
            }
            return 'filter', config

        elif idx == 3:  # 워터마크
            pos_map = {
                0: (50, 50),   # 중앙
                1: (10, 10),   # 좌상
                2: (90, 10),   # 우상
                3: (10, 90),   # 좌하
                4: (90, 90),   # 우하
            }
            x_pct, y_pct = pos_map.get(self.wm_position_combo.currentIndex(), (50, 50))
            config = {
                'watermark_config': {
                    'type': 'text',
                    'text': self.wm_text_input.text() or 'Watermark',
                    'font_family': '',
                    'font_size': self.wm_font_size.value(),
                    'color': (200, 200, 200),
                    'opacity': self.wm_opacity.value() / 100.0,
                    'rotation': 0,
                    'x_pct': x_pct,
                    'y_pct': y_pct,
                    'tile': False,
                }
            }
            return 'watermark', config

        return '', {}

    def _vue_notify(self, kind, msg):
        mw = getattr(self, 'main_window', None)
        if mw and hasattr(mw, 'vue_bridge'):
            try:
                mw.vue_bridge.showNotification.emit(kind, msg)
            except Exception:
                pass

    def start_from_payload(self, payload: dict):
        """Vue BatchView 페이로드로 배치 실행 (files + operation + settings)."""
        import os as _os
        from config import OUTPUT_DIR
        files = [p for p in (payload.get('files') or []) if p]
        if not files:
            self._vue_notify('error', '배치: 처리할 파일이 없습니다')
            return
        s = payload.get('settings') or {}
        op = (payload.get('operation') or 'resize').lower()
        if op == 'format':
            fmt = str(s.get('format', 'png')).lower().lstrip('.')
            operation, config = 'format', {'target_format': '.' + fmt, 'quality': 95}
        else:
            operation, config = 'resize', {
                'mode': 'fixed', 'width': int(s.get('width', 1024)),
                'height': int(s.get('height', 1024)), 'percent': 100, 'longest': 1024,
            }
        out_dir = self._output_dir or OUTPUT_DIR
        try:
            _os.makedirs(out_dir, exist_ok=True)
        except Exception:
            pass
        from tabs.editor.batch_worker import BatchWorker
        self._worker = BatchWorker(files, operation, config, out_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.error.connect(self._on_error)
        self._worker.all_done.connect(lambda *a: self._vue_notify('success', f'배치 완료 → {out_dir}'))
        self._worker.error.connect(lambda e: self._vue_notify('error', f'배치 오류: {e}'))
        self._worker.start()
        self._vue_notify('info', f'배치 시작: {len(files)}개')

    def _start_batch(self):
        files = self._get_file_list()
        if not files:
            QMessageBox.warning(self, "알림", "처리할 파일을 추가하세요.")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "알림", "출력 폴더를 선택하세요.")
            return

        operation, config = self._build_config()
        if not operation:
            return

        from tabs.editor.batch_worker import BatchWorker
        self._worker = BatchWorker(files, operation, config, self._output_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.error.connect(self._on_error)

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("처리 중...")

        self._worker.start()

    def _cancel_batch(self):
        if self._worker:
            self._worker.cancel()

    def _on_progress(self, current: int, total: int):
        pct = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"처리 중... {current}/{total}")

    def _on_file_done(self, name: str, success: bool):
        pass  # 개별 파일 결과는 로그에만 기록

    def _on_all_done(self, success: int, fail: int):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"완료: 성공 {success}개, 실패 {fail}개")
        QMessageBox.information(
            self, "배치 처리 완료",
            f"처리 완료\n성공: {success}개\n실패: {fail}개\n\n출력 폴더: {self._output_dir}"
        )

    def _on_error(self, msg: str):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "오류", msg)

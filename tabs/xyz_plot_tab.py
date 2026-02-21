# tabs/xyz_plot_tab.py
"""
XYZ Plot 탭 - 파라미터 조합 생성 + 결과 그리드
"""
import os
import uuid
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QGroupBox, QCheckBox, QTextEdit,
    QScrollArea, QFrame, QTabWidget, QGridLayout
)
from PyQt6.QtGui import QPixmap, QPainter, QFont, QColor, QImage
from PyQt6.QtCore import Qt, pyqtSignal
from utils.theme_manager import get_color


class XYZPlotTab(QWidget):
    """XYZ Plot 탭"""

    # 시그널
    add_to_queue_requested = pyqtSignal(list)  # payload 리스트
    start_generation_requested = pyqtSignal(list)  # 바로 생성

    # 사용 가능한 축 옵션
    AXIS_OPTIONS = {
        'None': {'type': 'none', 'description': '사용 안 함'},
        'Prompt S/R': {'type': 'prompt_sr', 'key': 'prompt'},
        'Negative S/R': {'type': 'prompt_sr', 'key': 'negative_prompt'},
        'Sampler': {'type': 'list', 'key': 'sampler_name'},
        'Scheduler': {'type': 'list', 'key': 'scheduler'},
        'Steps': {'type': 'range', 'key': 'steps'},
        'CFG Scale': {'type': 'range', 'key': 'cfg_scale'},
        'Width': {'type': 'range', 'key': 'width'},
        'Height': {'type': 'range', 'key': 'height'},
        'Seed': {'type': 'range', 'key': 'seed'},
        'Denoise (Hires)': {'type': 'range', 'key': 'denoising_strength'},
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_ui = parent
        self.base_payload = {}

        # 배치 추적
        self._current_batch_id: str = ''
        self._batch_results: list[tuple[str, dict]] = []  # (filepath, xyz_info)

        self._setup_ui()

    def _setup_ui(self):
        """UI 구성 — 내부 QTabWidget (설정 + 결과)"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.inner_tabs = QTabWidget()
        main_layout.addWidget(self.inner_tabs)

        # ── 설정 탭 ──
        settings_page = QWidget()
        self._setup_settings_ui(settings_page)
        self.inner_tabs.addTab(settings_page, "설정")

        # ── 결과 탭 ──
        results_page = QWidget()
        self._setup_results_ui(results_page)
        self.inner_tabs.addTab(results_page, "결과")

    # ========== 설정 탭 UI ==========

    def _setup_settings_ui(self, page: QWidget):
        """설정 탭 UI"""
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 제목
        title = QLabel("<h2>XYZ Plot</h2>")
        layout.addWidget(title)

        desc = QLabel("파라미터 조합을 생성하여 다양한 설정을 비교할 수 있습니다.")
        desc.setStyleSheet(f"color: {get_color('text_muted')}; margin-bottom: 10px;")
        layout.addWidget(desc)

        # 기본 설정 불러오기
        load_group = QGroupBox("기본 설정")
        load_layout = QHBoxLayout(load_group)

        self.btn_load_current = QPushButton("현재 T2I 설정 불러오기")
        self.btn_load_current.setFixedHeight(40)
        self.btn_load_current.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white;
                font-weight: bold; border-radius: 5px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.btn_load_current.clicked.connect(self._load_current_settings)
        load_layout.addWidget(self.btn_load_current)

        self.lbl_base_status = QLabel("기본 설정이 로드되지 않았습니다.")
        self.lbl_base_status.setStyleSheet("color: #e74c3c;")
        load_layout.addWidget(self.lbl_base_status)
        load_layout.addStretch()

        layout.addWidget(load_group)

        # X/Y/Z 축 설정
        self.x_group = self._create_axis_group("X축", "x")
        layout.addWidget(self.x_group)

        self.y_group = self._create_axis_group("Y축", "y")
        layout.addWidget(self.y_group)

        self.z_group = self._create_axis_group("Z축", "z")
        layout.addWidget(self.z_group)

        # 미리보기
        preview_group = QGroupBox("조합 미리보기")
        preview_layout = QVBoxLayout(preview_group)

        self.lbl_combination_count = QLabel("총 0개 조합")
        self.lbl_combination_count.setStyleSheet("""
            font-size: 14px; font-weight: bold; color: #FFC107; padding: 10px;
        """)
        preview_layout.addWidget(self.lbl_combination_count)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')};
                border-radius: 5px; color: {get_color('text_secondary')}; font-size: 11px;
            }}
        """)
        preview_layout.addWidget(self.preview_text)

        layout.addWidget(preview_group)

        # 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_add_queue = QPushButton("대기열에 추가")
        self.btn_add_queue.setFixedHeight(45)
        self.btn_add_queue.setEnabled(False)
        self.btn_add_queue.setStyleSheet(f"""
            QPushButton {{
                background-color: #27ae60; color: white;
                font-weight: bold; font-size: 13px; border-radius: 5px;
            }}
            QPushButton:hover {{ background-color: #2ecc71; }}
            QPushButton:disabled {{ background-color: {get_color('border')}; color: {get_color('text_muted')}; }}
        """)
        self.btn_add_queue.clicked.connect(self._on_add_to_queue)

        self.btn_start_now = QPushButton("바로 생성 시작")
        self.btn_start_now.setFixedHeight(45)
        self.btn_start_now.setEnabled(False)
        self.btn_start_now.setStyleSheet(f"""
            QPushButton {{
                background-color: #9b59b6; color: white;
                font-weight: bold; font-size: 13px; border-radius: 5px;
            }}
            QPushButton:hover {{ background-color: #8e44ad; }}
            QPushButton:disabled {{ background-color: {get_color('border')}; color: {get_color('text_muted')}; }}
        """)
        self.btn_start_now.clicked.connect(self._on_start_now)

        btn_layout.addWidget(self.btn_add_queue)
        btn_layout.addWidget(self.btn_start_now)
        layout.addLayout(btn_layout)

        layout.addStretch()

    # ========== 결과 탭 UI ==========

    def _setup_results_ui(self, page: QWidget):
        """결과 탭 UI"""
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 헤더
        header = QHBoxLayout()
        self.results_title = QLabel("결과 이미지 (0)")
        self.results_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFC107;")
        header.addWidget(self.results_title)
        header.addStretch()

        self.btn_export_grid = QPushButton("그리드 이미지 저장")
        self.btn_export_grid.setStyleSheet(f"""
            QPushButton {{
                background-color: #2980b9; color: white; border-radius: 4px;
                padding: 5px 10px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #3498db; }}
            QPushButton:disabled {{ background-color: {get_color('border')}; color: {get_color('text_muted')}; }}
        """)
        self.btn_export_grid.setEnabled(False)
        self.btn_export_grid.clicked.connect(self._export_grid_image)
        header.addWidget(self.btn_export_grid)

        btn_clear_results = QPushButton("결과 비우기")
        btn_clear_results.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button')}; color: {get_color('text_secondary')}; border-radius: 4px;
                padding: 5px 10px; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: #5A2A2A; }}
        """)
        btn_clear_results.clicked.connect(self._clear_results)
        header.addWidget(btn_clear_results)

        layout.addLayout(header)

        # 축 라벨 행 (동적으로 채워짐)
        self.axis_label = QLabel("")
        self.axis_label.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 11px;")
        layout.addWidget(self.axis_label)

        # 스크롤 영역 + 그리드
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')}; border-radius: 4px; }}
        """)

        self.results_container = QWidget()
        self.results_grid = QGridLayout(self.results_container)
        self.results_grid.setSpacing(6)
        self.results_grid.setContentsMargins(8, 8, 8, 8)

        self.results_scroll.setWidget(self.results_container)
        layout.addWidget(self.results_scroll, stretch=1)

        # 빈 상태
        self.results_empty_label = QLabel("결과가 없습니다. '바로 생성 시작'을 눌러 XYZ 조합을 생성하세요.")
        self.results_empty_label.setStyleSheet(f"color: {get_color('text_muted')}; padding: 40px;")
        self.results_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_grid.addWidget(self.results_empty_label, 0, 0)

    # ========== 축 설정 ==========

    def _create_axis_group(self, title: str, axis_id: str) -> QGroupBox:
        """축 설정 그룹 생성"""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("파라미터:"))

        combo = QComboBox()
        combo.addItems(self.AXIS_OPTIONS.keys())
        combo.setFixedWidth(150)
        combo.currentTextChanged.connect(self._update_preview)
        param_layout.addWidget(combo)

        param_layout.addStretch()
        layout.addLayout(param_layout)

        value_layout = QHBoxLayout()
        value_layout.addWidget(QLabel("값:"))

        value_input = QLineEdit()
        value_input.setPlaceholderText("예: 5, 7, 9, 11 또는 20-40:5 (시작-끝:간격)")
        value_input.textChanged.connect(self._update_preview)
        value_layout.addWidget(value_input)

        layout.addLayout(value_layout)

        hint = QLabel("쉼표로 구분, 범위 (시작-끝:간격), S/R: 검색어, 대체1, 대체2")
        hint.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 10px;")
        layout.addWidget(hint)

        combo.currentTextChanged.connect(
            lambda text, vi=value_input: self._update_placeholder(text, vi)
        )

        setattr(self, f'{axis_id}_combo', combo)
        setattr(self, f'{axis_id}_input', value_input)

        return group

    def _update_placeholder(self, param_name: str, value_input: QLineEdit):
        """파라미터 종류에 따라 placeholder 변경"""
        info = self.AXIS_OPTIONS.get(param_name, {})
        if info.get('type') == 'prompt_sr':
            value_input.setPlaceholderText("검색어, 대체1, 대체2, ... (첫 항목이 검색 대상)")
        elif info.get('type') == 'range':
            value_input.setPlaceholderText("예: 5, 7, 9, 11 또는 20-40:5 (시작-끝:간격)")
        elif info.get('type') == 'list':
            value_input.setPlaceholderText("예: Euler a, DPM++ 2M, DDIM")
        else:
            value_input.setPlaceholderText("")

    def _load_current_settings(self):
        """현재 T2I 설정 불러오기"""
        if self.parent_ui and hasattr(self.parent_ui, '_build_current_payload'):
            self.base_payload = self.parent_ui._build_current_payload()
            self.lbl_base_status.setText("기본 설정 로드됨")
            self.lbl_base_status.setStyleSheet("color: #27ae60;")
            self._update_preview()
        else:
            self.lbl_base_status.setText("설정을 불러올 수 없습니다.")
            self.lbl_base_status.setStyleSheet("color: #e74c3c;")

    def _parse_values(self, text: str) -> list:
        """값 문자열 파싱"""
        text = text.strip()
        if not text:
            return []

        values = []

        # 범위 형식: 20-40:5
        if '-' in text and ':' in text:
            try:
                range_part, step = text.split(':')
                start, end = range_part.split('-')
                start, end, step = float(start), float(end), float(step)

                current = start
                while current <= end:
                    values.append(current if '.' in text else int(current))
                    current += step
                return values
            except Exception:
                pass

        for v in text.split(','):
            v = v.strip()
            if not v:
                continue
            try:
                if '.' in v:
                    values.append(float(v))
                else:
                    values.append(int(v))
            except ValueError:
                values.append(v)

        return values

    def _parse_sr_values(self, text: str) -> tuple:
        """Prompt S/R 값 파싱"""
        parts = [v.strip() for v in text.split(',') if v.strip()]
        if len(parts) < 2:
            return ('', [])
        return (parts[0], parts[1:])

    def _generate_combinations(self) -> list:
        """모든 조합 생성"""
        if not self.base_payload:
            return []

        axes = []

        for axis_id in ['x', 'y', 'z']:
            combo = getattr(self, f'{axis_id}_combo')
            input_field = getattr(self, f'{axis_id}_input')

            param_name = combo.currentText()
            if param_name == 'None':
                continue

            axis_info = self.AXIS_OPTIONS.get(param_name, {})
            key = axis_info.get('key')
            if not key:
                continue

            if axis_info.get('type') == 'prompt_sr':
                search, replacements = self._parse_sr_values(input_field.text())
                if not search or not replacements:
                    continue
                axes.append({
                    'key': key, 'values': replacements,
                    'name': param_name, 'sr': True, 'search': search
                })
            else:
                values = self._parse_values(input_field.text())
                if not values:
                    continue
                axes.append({
                    'key': key, 'values': values,
                    'name': param_name, 'sr': False
                })

        if not axes:
            return []

        from itertools import product

        value_lists = [axis['values'] for axis in axes]
        combinations = list(product(*value_lists))

        # 새 배치 ID 생성
        self._current_batch_id = str(uuid.uuid4())[:8]

        payloads = []
        for combo_vals in combinations:
            payload = self.base_payload.copy()

            # _xyz_info 메타데이터 주입
            payload['_xyz_info'] = {
                'batch_id': self._current_batch_id,
                'axes': [(axis['name'], str(combo_vals[i])) for i, axis in enumerate(axes)]
            }

            for i, axis in enumerate(axes):
                if axis['sr']:
                    original = payload.get(axis['key'], '')
                    payload[axis['key']] = original.replace(axis['search'], str(combo_vals[i]))
                else:
                    payload[axis['key']] = combo_vals[i]
            payloads.append(payload)

        return payloads

    def _update_preview(self):
        """미리보기 업데이트"""
        payloads = self._generate_combinations()
        count = len(payloads)

        self.lbl_combination_count.setText(f"총 {count}개 조합")

        enabled = count > 0 and bool(self.base_payload)
        self.btn_add_queue.setEnabled(enabled)
        self.btn_start_now.setEnabled(enabled)

        if payloads:
            preview_lines = []
            for i, p in enumerate(payloads[:10]):
                changes = []
                for axis_id in ['x', 'y', 'z']:
                    combo_widget = getattr(self, f'{axis_id}_combo')
                    param_name = combo_widget.currentText()
                    if param_name != 'None':
                        info = self.AXIS_OPTIONS.get(param_name, {})
                        key = info.get('key')
                        if key and key in p:
                            val = p[key]
                            if info.get('type') == 'prompt_sr':
                                val_str = str(val)[:50] + ('...' if len(str(val)) > 50 else '')
                                changes.append(f"{param_name}: {val_str}")
                            else:
                                changes.append(f"{param_name}={val}")

                preview_lines.append(f"{i+1}. {', '.join(changes)}")

            if count > 10:
                preview_lines.append(f"... 외 {count - 10}개")

            self.preview_text.setPlainText('\n'.join(preview_lines))
        else:
            self.preview_text.setPlainText("조합이 없습니다. 축 설정을 확인하세요.")

    def _on_add_to_queue(self):
        """대기열에 추가"""
        payloads = self._generate_combinations()
        if payloads:
            self.add_to_queue_requested.emit(payloads)

    def _on_start_now(self):
        """바로 생성 시작"""
        payloads = self._generate_combinations()
        if payloads:
            # 결과 초기화
            self._batch_results.clear()
            self._refresh_results_grid()
            self.start_generation_requested.emit(payloads)

    # ========== 결과 관련 ==========

    def add_result_image(self, filepath: str, xyz_info: dict):
        """생성 완료된 이미지를 결과 그리드에 추가"""
        if xyz_info.get('batch_id') != self._current_batch_id:
            return

        self._batch_results.append((filepath, xyz_info))
        self._refresh_results_grid()

        # 결과 탭으로 자동 전환
        self.inner_tabs.setCurrentIndex(1)

    def _refresh_results_grid(self):
        """결과 그리드 재구성"""
        # 기존 위젯 제거
        while self.results_grid.count():
            item = self.results_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        count = len(self._batch_results)
        self.results_title.setText(f"결과 이미지 ({count})")
        self.btn_export_grid.setEnabled(count > 0)

        if not self._batch_results:
            self.results_empty_label = QLabel("결과가 없습니다.")
            self.results_empty_label.setStyleSheet(f"color: {get_color('text_muted')}; padding: 40px;")
            self.results_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_grid.addWidget(self.results_empty_label, 0, 0)
            self.axis_label.setText("")
            return

        # 축 정보 표시
        first_info = self._batch_results[0][1]
        axes = first_info.get('axes', [])
        axis_text = "  |  ".join([f"{name}: {val}" for name, val in axes])
        self.axis_label.setText(f"축: {', '.join([a[0] for a in axes])}")

        # 그리드 열 수 결정 (최대 6열)
        cols = min(6, max(1, count))
        if axes:
            # X축 값 개수를 열 수로 사용
            x_values = set()
            for _, info in self._batch_results:
                if info.get('axes'):
                    x_values.add(info['axes'][0][1])
            if x_values:
                cols = len(x_values)

        THUMB_SIZE = 200

        for idx, (filepath, xyz_info) in enumerate(self._batch_results):
            row = idx // cols
            col = idx % cols

            # 이미지 + 라벨 컨테이너
            container = QFrame()
            container.setStyleSheet(f"""
                QFrame {{
                    background-color: {get_color('bg_tertiary')}; border: 1px solid {get_color('border')};
                    border-radius: 4px;
                }}
            """)
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(4, 4, 4, 4)
            c_layout.setSpacing(2)

            # 이미지
            img_label = QLabel()
            img_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_label.setStyleSheet(f"background-color: {get_color('bg_primary')}; border-radius: 4px;")

            if os.path.exists(filepath):
                pix = QPixmap(filepath)
                if not pix.isNull():
                    img_label.setPixmap(pix.scaled(
                        THUMB_SIZE, THUMB_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    ))
            c_layout.addWidget(img_label)

            # 축 값 라벨
            axes_info = xyz_info.get('axes', [])
            label_parts = [f"{val}" for _, val in axes_info]
            info_label = QLabel(" | ".join(label_parts))
            info_label.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 10px;")
            info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_label.setWordWrap(True)
            c_layout.addWidget(info_label)

            self.results_grid.addWidget(container, row, col)

        self.results_container.adjustSize()

    def _export_grid_image(self):
        """결과 그리드를 하나의 이미지로 내보내기"""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        if not self._batch_results:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "그리드 이미지 저장", "xyz_grid.png",
            "PNG (*.png);;JPEG (*.jpg)"
        )
        if not file_path:
            return

        try:
            # 축 정보 파악
            first_info = self._batch_results[0][1]
            axes = first_info.get('axes', [])

            # X축 값 / Y축 값 수집 (순서 유지)
            x_vals, y_vals = [], []
            seen_x, seen_y = set(), set()
            for _, info in self._batch_results:
                ax = info.get('axes', [])
                if ax:
                    xv = ax[0][1]
                    if xv not in seen_x:
                        seen_x.add(xv)
                        x_vals.append(xv)
                if len(ax) >= 2:
                    yv = ax[1][1]
                    if yv not in seen_y:
                        seen_y.add(yv)
                        y_vals.append(yv)

            if not y_vals:
                y_vals = ['']

            cols = len(x_vals) if x_vals else len(self._batch_results)
            rows = len(y_vals)

            # 셀 크기 결정 (원본 이미지 기준)
            cell_w, cell_h = 256, 256
            sample_path = self._batch_results[0][0]
            if os.path.exists(sample_path):
                sp = QPixmap(sample_path)
                if not sp.isNull():
                    cell_w = min(sp.width(), 512)
                    cell_h = min(sp.height(), 512)

            # 라벨 영역
            label_h = 30  # X축 라벨 (상단)
            label_w = 80  # Y축 라벨 (좌측)
            has_y = len(axes) >= 2
            left_margin = label_w if has_y else 0
            padding = 4

            total_w = left_margin + cols * (cell_w + padding) + padding
            total_h = label_h + rows * (cell_h + padding) + padding

            # QImage 생성
            grid_img = QImage(total_w, total_h, QImage.Format.Format_RGB32)
            grid_img.fill(QColor(30, 30, 30))

            painter = QPainter(grid_img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # X축 라벨 (상단)
            font = QFont("Arial", 10, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(200, 200, 200))

            for ci, xv in enumerate(x_vals):
                x = left_margin + padding + ci * (cell_w + padding)
                painter.drawText(x, 0, cell_w, label_h,
                                 Qt.AlignmentFlag.AlignCenter, str(xv))

            # Y축 라벨 (좌측)
            if has_y:
                for ri, yv in enumerate(y_vals):
                    y = label_h + padding + ri * (cell_h + padding)
                    painter.drawText(0, y, label_w, cell_h,
                                     Qt.AlignmentFlag.AlignCenter, str(yv))

            # 이미지 배치 (lookup by xyz_info)
            result_map: dict[tuple, str] = {}
            for filepath, info in self._batch_results:
                ax = info.get('axes', [])
                key_x = ax[0][1] if ax else ''
                key_y = ax[1][1] if len(ax) >= 2 else ''
                result_map[(key_x, key_y)] = filepath

            for ri, yv in enumerate(y_vals):
                for ci, xv in enumerate(x_vals):
                    fp = result_map.get((xv, yv), '')
                    if not fp or not os.path.exists(fp):
                        continue

                    pix = QPixmap(fp)
                    if pix.isNull():
                        continue

                    scaled = pix.scaled(
                        cell_w, cell_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )

                    x = left_margin + padding + ci * (cell_w + padding)
                    y = label_h + padding + ri * (cell_h + padding)

                    # 중앙 정렬
                    ox = x + (cell_w - scaled.width()) // 2
                    oy = y + (cell_h - scaled.height()) // 2
                    painter.drawPixmap(ox, oy, scaled)

            painter.end()
            grid_img.save(file_path)
            QMessageBox.information(self, "저장 완료",
                                    f"그리드 이미지가 저장되었습니다.\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"그리드 이미지 저장 실패: {e}")

    def _clear_results(self):
        """결과 비우기"""
        self._batch_results.clear()
        self._refresh_results_grid()

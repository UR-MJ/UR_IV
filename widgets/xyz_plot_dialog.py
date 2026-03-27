# widgets/xyz_plot_dialog.py
"""
XYZ Plot 다이얼로그 UI
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit,
    QGroupBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from utils.xyz_plot import XYZPlotGenerator, AxisConfig, AxisType
from utils.theme_manager import get_color


class XYZPlotDialog(QDialog):
    """XYZ Plot 다이얼로그"""
    
    # 시그널
    add_to_queue_requested = pyqtSignal(list)  # 대기열에 추가
    
    def __init__(self, base_payload: dict = None, parent=None):
        super().__init__(parent)
        self.base_payload = base_payload or {}
        self.generator = XYZPlotGenerator()
        
        self.setWindowTitle("🔄 XYZ Plot - 변형 생성")
        self.setMinimumSize(700, 600)
        self._setup_ui()
        
        if base_payload:
            self.generator.set_base_payload(base_payload)
            self._update_base_prompt_display()
    
    def _setup_ui(self):
        """UI 구성"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 기본 프롬프트 표시
        prompt_group = QGroupBox("📝 기본 프롬프트")
        prompt_layout = QVBoxLayout(prompt_group)
        
        self.base_prompt_text = QTextEdit()
        self.base_prompt_text.setMaximumHeight(80)
        self.base_prompt_text.setPlaceholderText("현재 설정의 프롬프트가 표시됩니다...")
        self.base_prompt_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color('bg_secondary')};
                border: 1px solid {get_color('bg_button_hover')};
                border-radius: 4px;
                color: {get_color('text_secondary')};
                font-size: 11px;
            }}
        """)
        prompt_layout.addWidget(self.base_prompt_text)
        layout.addWidget(prompt_group)
        
        # 축 설정
        axes_group = QGroupBox("🔧 변형 축 설정")
        axes_layout = QVBoxLayout(axes_group)
        
        # X축
        x_layout = self._create_axis_row("X축", 'x')
        axes_layout.addLayout(x_layout)
        
        # Y축
        y_layout = self._create_axis_row("Y축", 'y')
        axes_layout.addLayout(y_layout)
        
        # Z축
        z_layout = self._create_axis_row("Z축", 'z')
        axes_layout.addLayout(z_layout)
        
        layout.addWidget(axes_group)
        
        # 옵션
        options_layout = QHBoxLayout()
        
        self.chk_fix_seed = QCheckBox("시드 고정")
        self.chk_fix_seed.setToolTip("모든 변형에 동일한 시드 사용")
        options_layout.addWidget(self.chk_fix_seed)
        
        options_layout.addStretch()
        
        self.lbl_total = QLabel("총 생성 예정: 0장")
        self.lbl_total.setStyleSheet(f"font-weight: bold; color: {get_color('accent')};")
        options_layout.addWidget(self.lbl_total)
        
        layout.addLayout(options_layout)
        
        # 미리보기 테이블
        preview_group = QGroupBox("📋 미리보기")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels(['#', 'X', 'Y', 'Z', '프롬프트 미리보기'])
        self.preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.preview_table.setMaximumHeight(200)
        self.preview_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {get_color('bg_secondary')};
                border: 1px solid {get_color('bg_button_hover')};
                gridline-color: {get_color('bg_button_hover')};
            }}
            QTableWidget::item {{
                padding: 5px;
            }}
            QHeaderView::section {{
                background-color: {get_color('bg_tertiary')};
                padding: 5px;
                border: none;
                border-right: 1px solid {get_color('bg_button_hover')};
            }}
        """)
        preview_layout.addWidget(self.preview_table)
        
        layout.addWidget(preview_group)
        
        # 버튼
        btn_layout = QHBoxLayout()
        
        self.btn_refresh = QPushButton("🔄 미리보기 갱신")
        self.btn_refresh.clicked.connect(self._refresh_preview)
        self.btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button_hover')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                padding: 8px 15px;
                color: {get_color('text_primary')};
            }}
            QPushButton:hover {{ background-color: {get_color('border')}; }}
        """)
        btn_layout.addWidget(self.btn_refresh)
        
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('border')};
                border-radius: 4px;
                padding: 8px 20px;
                color: {get_color('text_primary')};
            }}
            QPushButton:hover {{ background-color: {get_color('text_muted')}; }}
        """)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_add_queue = QPushButton("📋 대기열에 추가")
        self.btn_add_queue.clicked.connect(self._on_add_to_queue)
        self.btn_add_queue.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                border-radius: 4px;
                padding: 8px 20px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5dade2; }
        """)
        btn_layout.addWidget(self.btn_add_queue)
        
        layout.addLayout(btn_layout)
    
    def _create_axis_row(self, label: str, axis_key: str) -> QHBoxLayout:
        """축 설정 행 생성"""
        layout = QHBoxLayout()
        
        # 축 라벨
        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(40)
        lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl)
        
        # 타입 선택
        combo = QComboBox()
        combo.setFixedWidth(180)
        for axis_type in AxisType:
            combo.addItem(axis_type.value, axis_type)
        combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {get_color('bg_tertiary')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        layout.addWidget(combo)
        
        # 대상 단어 (프롬프트 변형용)
        target_label = QLabel("대상:")
        target_label.setFixedWidth(35)
        layout.addWidget(target_label)
        
        target_input = QLineEdit()
        target_input.setFixedWidth(100)
        target_input.setPlaceholderText("교체할 단어")
        target_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {get_color('bg_tertiary')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        layout.addWidget(target_input)
        
        # 값 입력
        values_label = QLabel("값:")
        values_label.setFixedWidth(25)
        layout.addWidget(values_label)
        
        values_input = QLineEdit()
        values_input.setPlaceholderText("값1, 값2, 값3 또는 5-10:1")
        values_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {get_color('bg_tertiary')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        layout.addWidget(values_input, 1)
        
        # 위젯 저장
        setattr(self, f'{axis_key}_combo', combo)
        setattr(self, f'{axis_key}_target', target_input)
        setattr(self, f'{axis_key}_values', values_input)
        
        # 타입 변경 시 대상 입력 표시/숨김
        combo.currentIndexChanged.connect(
            lambda: self._on_axis_type_changed(axis_key)
        )
        
        # 값 변경 시 미리보기 갱신
        values_input.textChanged.connect(self._update_total_count)
        combo.currentIndexChanged.connect(self._update_total_count)
        
        return layout
    
    def _on_axis_type_changed(self, axis_key: str):
        """축 타입 변경 시"""
        combo = getattr(self, f'{axis_key}_combo')
        target_input = getattr(self, f'{axis_key}_target')
        
        axis_type = combo.currentData()
        
        # 프롬프트 변형 타입만 대상 입력 필요
        needs_target = axis_type in [
            AxisType.PROMPT_SR,
            AxisType.PROMPT_REPLACE,
            AxisType.PROMPT_REMOVE,
        ]
        
        target_input.setEnabled(needs_target)
        target_input.setVisible(needs_target)
    
    def _update_base_prompt_display(self):
        """기본 프롬프트 표시 업데이트"""
        prompt = self.base_payload.get('prompt', '')
        self.base_prompt_text.setPlainText(prompt)
    
    def _update_total_count(self):
        """총 생성 수 업데이트"""
        self._apply_axis_configs()
        total = self.generator.get_total_count()
        self.lbl_total.setText(f"총 생성 예정: {total}장")
        
        # 너무 많으면 경고
        if total > 100:
            self.lbl_total.setStyleSheet(f"font-weight: bold; color: {get_color('error')};")
        elif total > 50:
            self.lbl_total.setStyleSheet(f"font-weight: bold; color: {get_color('accent')};")
        else:
            self.lbl_total.setStyleSheet(f"font-weight: bold; color: {get_color('accent')};")
    
    def _apply_axis_configs(self):
        """축 설정 적용"""
        for axis_key in ['x', 'y', 'z']:
            combo = getattr(self, f'{axis_key}_combo')
            target_input = getattr(self, f'{axis_key}_target')
            values_input = getattr(self, f'{axis_key}_values')
            
            config = AxisConfig(combo.currentData())
            config.target_word = target_input.text().strip()
            config.set_values_from_string(values_input.text())
            
            self.generator.set_axis(axis_key, config)
    
    def _refresh_preview(self):
        """미리보기 갱신"""
        self._apply_axis_configs()
        
        previews = self.generator.generate_preview(max_items=20)
        
        self.preview_table.setRowCount(len(previews))
        
        for row, preview in enumerate(previews):
            self.preview_table.setItem(row, 0, QTableWidgetItem(str(preview['index'])))
            self.preview_table.setItem(row, 1, QTableWidgetItem(preview['x']))
            self.preview_table.setItem(row, 2, QTableWidgetItem(preview['y']))
            self.preview_table.setItem(row, 3, QTableWidgetItem(preview['z']))
            self.preview_table.setItem(row, 4, QTableWidgetItem(preview['prompt_preview']))
    
    def _on_add_to_queue(self):
        """대기열에 추가"""
        self._apply_axis_configs()
        
        total = self.generator.get_total_count()
        
        if total == 0:
            QMessageBox.warning(self, "알림", "생성할 항목이 없습니다.")
            return
        
        if total > 100:
            reply = QMessageBox.question(
                self, "확인",
                f"총 {total}개의 항목이 생성됩니다.\n계속하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # 모든 조합 생성
        payloads = self.generator.generate_all()
        
        # 시드 고정 옵션
        if self.chk_fix_seed.isChecked():
            base_seed = self.base_payload.get('seed', -1)
            for payload in payloads:
                payload['seed'] = base_seed
        
        self.add_to_queue_requested.emit(payloads)
        self.accept()
    
    def set_base_payload(self, payload: dict):
        """기본 payload 설정"""
        self.base_payload = payload.copy()
        self.generator.set_base_payload(payload)
        self._update_base_prompt_display()
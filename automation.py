# automation.py

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QPushButton,
    QGroupBox, QRadioButton, QHBoxLayout, QFormLayout, QDialogButtonBox, QCheckBox
)
from widgets.common_widgets import NoScrollSpinBox

class AutomationWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("자동화 설정")
        self.setMinimumWidth(450)

        main_layout = QVBoxLayout(self)
        
        # --- 기본 설정 ---
        form_layout = QFormLayout()
        
        self.delay_spinbox = NoScrollSpinBox()
        self.delay_spinbox.setRange(0, 3600)
        self.delay_spinbox.setValue(1)
        form_layout.addRow("이미지 생성 후 지연 (초):", self.delay_spinbox)

        self.repeat_spinbox = NoScrollSpinBox()
        self.repeat_spinbox.setRange(1, 100)
        self.repeat_spinbox.setValue(1)
        form_layout.addRow("동일 프롬프트 반복 생성:", self.repeat_spinbox)
        
        # --- ▼▼▼▼▼ 중복 허용 체크박스 추가 ▼▼▼▼▼ ---
        self.allow_duplicates_checkbox = QCheckBox("랜덤 프롬프트 중복 허용")
        self.allow_duplicates_checkbox.setToolTip("체크 시 전체 검색 결과에서 매번 새로 뽑습니다 (중복 가능).\n체크 해제 시 한 번 뽑은 프롬롬프트는 다시 뽑지 않습니다 (덱 방식).")
        form_layout.addRow(self.allow_duplicates_checkbox)
        # --- ▲▲▲▲▲ 추가 완료 ▲▲▲▲▲ ---

        main_layout.addLayout(form_layout)

        # --- 종료 조건 ---
        termination_group = QGroupBox("자동화 종료 조건")
        group_layout = QVBoxLayout(termination_group)

        self.radio_unlimited = QRadioButton("무제한 (수동으로 중지)")
        self.radio_unlimited.setChecked(True)
        group_layout.addWidget(self.radio_unlimited)

        timer_layout = QHBoxLayout()
        self.radio_timer = QRadioButton("타이머:")
        self.timer_spinbox = NoScrollSpinBox()
        self.timer_spinbox.setRange(1, 1440)
        self.timer_spinbox.setValue(60)
        self.timer_spinbox.setEnabled(False)
        timer_layout.addWidget(self.radio_timer)
        timer_layout.addWidget(self.timer_spinbox)
        timer_layout.addWidget(QLabel("분 후 종료"))
        group_layout.addLayout(timer_layout)
        
        count_layout = QHBoxLayout()
        self.radio_count = QRadioButton("생성 갯수:")
        self.count_spinbox = NoScrollSpinBox()
        self.count_spinbox.setRange(1, 9999)
        self.count_spinbox.setValue(100)
        self.count_spinbox.setEnabled(False)
        count_layout.addWidget(self.radio_count)
        count_layout.addWidget(self.count_spinbox)
        count_layout.addWidget(QLabel("개 생성 후 종료"))
        group_layout.addLayout(count_layout)

        main_layout.addWidget(termination_group)
        
        self.radio_timer.toggled.connect(self.timer_spinbox.setEnabled)
        self.radio_count.toggled.connect(self.count_spinbox.setEnabled)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("자동화 시작")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
    
    def get_settings(self):
        """사용자가 설정한 값들을 딕셔너리 형태로 반환합니다."""
        mode = 'unlimited'
        limit = 0
        if self.radio_timer.isChecked():
            mode = 'timer'
            limit = self.timer_spinbox.value() * 60
        elif self.radio_count.isChecked():
            mode = 'count'
            limit = self.count_spinbox.value()
            
        return {
            "delay": self.delay_spinbox.value(),
            "repeat_per_prompt": self.repeat_spinbox.value(),
            "allow_duplicates": self.allow_duplicates_checkbox.isChecked(), # <-- 설정값 추가
            "termination_mode": mode,
            "termination_limit": limit
        }

    @staticmethod
    def get_automation_settings(parent=None):
        dialog = AutomationWindow(parent)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            return dialog.get_settings()
        return None
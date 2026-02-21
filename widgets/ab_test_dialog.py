# widgets/ab_test_dialog.py
"""프롬프트 A/B 테스트 다이얼로그"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSpinBox, QGroupBox
)
from PyQt6.QtCore import Qt
from utils.theme_manager import get_color


def _get_style():
    return f"""
QDialog {{ background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')}; }}
QLabel {{ color: {get_color('text_primary')}; }}
QTextEdit {{
    background-color: {get_color('bg_input')}; color: {get_color('text_primary')};
    border: 1px solid {get_color('border')}; border-radius: 4px;
    font-size: 12px; padding: 4px;
}}
QTextEdit:focus {{ border: 1px solid {get_color('accent')}; }}
QGroupBox {{
    color: {get_color('text_secondary')}; font-weight: bold; border: 1px solid {get_color('border')};
    border-radius: 6px; margin-top: 6px; padding-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; padding: 0 6px;
}}
QSpinBox {{
    background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')};
    border-radius: 4px; padding: 4px;
}}
"""


class ABTestDialog(QDialog):
    """A/B 프롬프트 테스트 설정 다이얼로그"""

    def __init__(self, current_prompt: str = "", current_negative: str = "",
                 current_seed: int = -1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("A/B 프롬프트 테스트")
        self.setMinimumSize(700, 500)
        self.resize(750, 550)
        self.setStyleSheet(_get_style())

        self._result = None
        self._init_ui(current_prompt, current_negative, current_seed)

    def _init_ui(self, prompt: str, negative: str, seed: int):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("A/B 프롬프트 테스트")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {get_color('text_primary')};")
        root.addWidget(title)

        desc = QLabel("동일한 시드로 두 프롬프트를 생성하여 비교합니다.")
        desc.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 12px;")
        root.addWidget(desc)

        # 시드
        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("시드:"))
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(-1, 2147483647)
        self.spin_seed.setValue(seed if seed > 0 else 12345)
        self.spin_seed.setSpecialValueText("랜덤")
        self.spin_seed.setFixedWidth(150)
        seed_row.addWidget(self.spin_seed)
        seed_row.addStretch()
        root.addLayout(seed_row)

        # 프롬프트 A
        group_a = QGroupBox("프롬프트 A")
        la = QVBoxLayout(group_a)
        self.prompt_a = QTextEdit()
        self.prompt_a.setPlainText(prompt)
        self.prompt_a.setMaximumHeight(100)
        la.addWidget(self.prompt_a)
        root.addWidget(group_a)

        # 프롬프트 B
        group_b = QGroupBox("프롬프트 B")
        lb = QVBoxLayout(group_b)
        self.prompt_b = QTextEdit()
        self.prompt_b.setPlainText(prompt)
        self.prompt_b.setMaximumHeight(100)
        lb.addWidget(self.prompt_b)
        root.addWidget(group_b)

        # 공통 네거티브
        group_neg = QGroupBox("공통 네거티브")
        ln = QVBoxLayout(group_neg)
        self.negative = QTextEdit()
        self.negative.setPlainText(negative)
        self.negative.setMaximumHeight(60)
        ln.addWidget(self.negative)
        root.addWidget(group_neg)

        # 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_run = QPushButton("생성 시작")
        btn_run.setFixedSize(130, 38)
        btn_run.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; border-radius: 6px; "
            "font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        btn_run.clicked.connect(self._on_run)
        btn_row.addWidget(btn_run)

        btn_close = QPushButton("취소")
        btn_close.setFixedSize(100, 38)
        btn_close.setStyleSheet(
            f"QPushButton {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; border-radius: 6px; "
            f"font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
        )
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        root.addLayout(btn_row)

    def _on_run(self):
        import random
        seed = self.spin_seed.value()
        if seed <= 0:
            seed = random.randint(1, 2147483647)

        self._result = {
            'seed': seed,
            'prompt_a': self.prompt_a.toPlainText().strip(),
            'prompt_b': self.prompt_b.toPlainText().strip(),
            'negative': self.negative.toPlainText().strip(),
        }
        self.accept()

    def get_result(self) -> dict | None:
        return self._result

# widgets/sliders.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSlider, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal
from utils.theme_manager import get_color

class NumericSlider(QWidget):
    """숫자 입력 슬라이더 위젯"""
    valueChanged = pyqtSignal(int)

    def __init__(self, label_text, min_val, max_val, default_val, parent=None):
        super().__init__(parent)
        self.setObjectName("numericSlider")

        # 위젯 자체에 배경색 추가 (ID 셀렉터로 자식 위젯 간섭 방지)
        self.setStyleSheet(f"""
            QWidget#numericSlider {{
                background-color: {get_color('bg_tertiary')};
                border-radius: 6px;
                padding: 5px;
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)  # 여백 추가
        layout.setSpacing(10)

        # 라벨
        self.label = QLabel(f"{label_text}: {default_val}")
        self.label.setMinimumWidth(120)
        self.label.setStyleSheet(
            f"color: {get_color('text_primary')}; font-weight: bold; background: transparent;"
        )
        self.base_text = label_text

        # 슬라이더 (휠 이벤트 비활성화)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider.wheelEvent = lambda event: event.ignore()
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default_val)
        self.slider.setStyleSheet(f"""
            QSlider {{
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                background: {get_color('bg_secondary')};
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #5865F2;
                width: 18px;
                height: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #7289DA;
            }}
        """)
        
        # 입력창
        self.input = QLineEdit(str(default_val))
        self.input.setFixedWidth(60)
        self.input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {get_color('bg_secondary')};
                color: {get_color('text_primary')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }}
            QLineEdit:focus {{
                border: 1px solid #5865F2;
            }}
        """)

        layout.addWidget(self.label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.input)

        self.slider.valueChanged.connect(self._on_slider_change)
        self.input.editingFinished.connect(self._on_text_change)
    def _on_slider_change(self, val):
        self.input.setText(str(val))
        self.label.setText(f"{self.base_text}: {val}")
        self.valueChanged.emit(val)

    def _on_text_change(self):
        try:
            val = int(self.input.text())
            val = max(self.slider.minimum(), min(val, self.slider.maximum()))
            self.slider.setValue(val)
            self.input.setText(str(val))
        except ValueError:
            self.input.setText(str(self.slider.value()))

    def value(self):
        return self.slider.value()

    def setValue(self, val):
        self.slider.setValue(val)

    def setLabel(self, text):
        self.base_text = text
        self.label.setText(f"{text}: {self.slider.value()}")

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.input.setEnabled(enabled)
        if not enabled:
            self.setStyleSheet(f"QWidget#numericSlider {{ background-color: {get_color('bg_tertiary')}; border-radius: 6px; padding: 5px; opacity: 0.5; }}")
        else:
            self.setStyleSheet(f"QWidget#numericSlider {{ background-color: {get_color('bg_tertiary')}; border-radius: 6px; padding: 5px; }}")
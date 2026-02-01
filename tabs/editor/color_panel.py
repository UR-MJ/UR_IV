# tabs/editor/color_panel.py
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from widgets.sliders import NumericSlider


class ColorAdjustPanel(QWidget):
    """색감 조절 패널 - 밝기/대비/채도 + 필터 프리셋"""

    adjustment_changed = pyqtSignal(int, int, int)
    apply_requested = pyqtSignal(int, int, int)
    reset_requested = pyqtSignal()
    filter_apply_requested = pyqtSignal(str)
    auto_correct_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """UI 초기화"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # ── 슬라이더 ──
        self.slider_brightness = NumericSlider("☀️ 밝기", -100, 100, 0)
        self.slider_contrast = NumericSlider("🔲 대비", -100, 100, 0)
        self.slider_saturation = NumericSlider("🎨 채도", -100, 100, 0)

        layout.addWidget(self.slider_brightness)
        layout.addWidget(self.slider_contrast)
        layout.addWidget(self.slider_saturation)

        # 적용/초기화 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_apply = QPushButton("🎨 조정 적용")
        self.btn_apply.setFixedHeight(35)
        self.btn_apply.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_apply.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )

        self.btn_reset = QPushButton("↩️ 초기화")
        self.btn_reset.setFixedHeight(35)
        self.btn_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_reset.setStyleSheet(
            "background-color: #333; color: #AAA; border-radius: 4px; "
            "font-size: 13px;"
        )

        btn_row.addWidget(self.btn_apply, 2)
        btn_row.addWidget(self.btn_reset, 1)
        layout.addLayout(btn_row)

        # 자동 보정
        self.btn_auto_correct = QPushButton("✨ 자동 보정")
        self.btn_auto_correct.setFixedHeight(35)
        self.btn_auto_correct.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_auto_correct.setStyleSheet(
            "background-color: #2D8C4E; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        self.btn_auto_correct.clicked.connect(lambda: self.auto_correct_requested.emit())
        layout.addWidget(self.btn_auto_correct)

        # ── 필터 프리셋 ──
        preset_label = QLabel("필터 프리셋")
        preset_label.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
        layout.addWidget(preset_label)

        preset_grid = QGridLayout()
        preset_grid.setSpacing(6)

        presets = [
            ("🔲 흑백", "grayscale"),
            ("🟤 세피아", "sepia"),
            ("🔪 선명하게", "sharpen"),
            ("🔥 따뜻하게", "warm"),
            ("❄️ 차갑게", "cool"),
            ("🌫️ 소프트", "soft"),
        ]

        for i, (label, name) in enumerate(presets):
            btn = QPushButton(label)
            btn.setFixedHeight(35)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2C2C2C; color: #DDD; border: 1px solid #555;
                    border-radius: 4px; font-size: 13px; font-weight: bold;
                }
                QPushButton:hover { background-color: #3C3C3C; border: 1px solid #777; }
            """)
            btn.clicked.connect(lambda checked, n=name: self.filter_apply_requested.emit(n))
            preset_grid.addWidget(btn, i // 3, i % 3)

        layout.addLayout(preset_grid)
        layout.addStretch()

        # ── 시그널 연결 ──
        self.slider_brightness.valueChanged.connect(self._on_slider_changed)
        self.slider_contrast.valueChanged.connect(self._on_slider_changed)
        self.slider_saturation.valueChanged.connect(self._on_slider_changed)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_reset.clicked.connect(self._on_reset)

    def _on_slider_changed(self):
        """슬라이더 변경 → 프리뷰 시그널"""
        b = self.slider_brightness.value()
        c = self.slider_contrast.value()
        s = self.slider_saturation.value()
        self.adjustment_changed.emit(b, c, s)

    def _on_apply(self):
        """조정 적용"""
        b = self.slider_brightness.value()
        c = self.slider_contrast.value()
        s = self.slider_saturation.value()
        if b == 0 and c == 0 and s == 0:
            return
        self.apply_requested.emit(b, c, s)
        self._reset_sliders()

    def _on_reset(self):
        """슬라이더 초기화"""
        self._reset_sliders()
        self.reset_requested.emit()

    def _reset_sliders(self):
        """슬라이더 값 0으로 리셋"""
        self.slider_brightness.setValue(0)
        self.slider_contrast.setValue(0)
        self.slider_saturation.setValue(0)

    @staticmethod
    def apply_filter(img: np.ndarray, filter_name: str) -> np.ndarray:
        """필터 프리셋 적용 (정적 메서드)"""
        if filter_name == "grayscale":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        elif filter_name == "sepia":
            kernel = np.array([
                [0.272, 0.534, 0.131],
                [0.349, 0.686, 0.168],
                [0.393, 0.769, 0.189]
            ], dtype=np.float32)
            sepia = cv2.transform(img, kernel)
            return np.clip(sepia, 0, 255).astype(np.uint8)

        elif filter_name == "sharpen":
            kernel = np.array([
                [0, -1, 0],
                [-1, 5, -1],
                [0, -1, 0]
            ], dtype=np.float32)
            return cv2.filter2D(img, -1, kernel)

        elif filter_name == "warm":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 0] = np.clip(hsv[:, :, 0] - 10, 0, 179)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.15, 0, 255)
            result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
            # 약간의 붉은 틴트
            result[:, :, 2] = np.clip(result[:, :, 2].astype(np.int16) + 10, 0, 255).astype(np.uint8)
            return result

        elif filter_name == "cool":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 0] = np.clip(hsv[:, :, 0] + 10, 0, 179)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 0.9, 0, 255)
            result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
            # 약간의 파란 틴트
            result[:, :, 0] = np.clip(result[:, :, 0].astype(np.int16) + 15, 0, 255).astype(np.uint8)
            return result

        elif filter_name == "soft":
            return cv2.GaussianBlur(img, (5, 5), 0)

        return img

    @staticmethod
    def auto_correct(img: np.ndarray) -> np.ndarray:
        """자동 색감 보정 (CLAHE + 화이트밸런스)"""
        # LAB 색공간에서 CLAHE 적용 (밝기 + 대비 보정)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # 간단한 화이트밸런스 (Gray World)
        avg_b = np.mean(result[:, :, 0])
        avg_g = np.mean(result[:, :, 1])
        avg_r = np.mean(result[:, :, 2])
        avg_gray = (avg_b + avg_g + avg_r) / 3.0
        if avg_b > 0 and avg_g > 0 and avg_r > 0:
            result[:, :, 0] = np.clip(result[:, :, 0] * (avg_gray / avg_b), 0, 255).astype(np.uint8)
            result[:, :, 1] = np.clip(result[:, :, 1] * (avg_gray / avg_g), 0, 255).astype(np.uint8)
            result[:, :, 2] = np.clip(result[:, :, 2] * (avg_gray / avg_r), 0, 255).astype(np.uint8)

        return result

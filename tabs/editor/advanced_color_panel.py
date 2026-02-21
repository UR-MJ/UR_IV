# tabs/editor/advanced_color_panel.py
"""고급 색감 조절 패널 — 커브/레벨/히스토그램/색온도"""
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from widgets.sliders import NumericSlider
from tabs.editor.histogram_widget import HistogramWidget
from tabs.editor.curves_widget import CurvesWidget
from utils.theme_manager import get_color


class AdvancedColorPanel(QWidget):
    """고급 색감 조절 패널"""

    adjustment_preview = pyqtSignal(object)   # np.ndarray (프리뷰 이미지)
    apply_requested = pyqtSignal(object)      # np.ndarray (적용할 이미지)
    reset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_image = None  # 원본 이미지 참조
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # ── 히스토그램 ──
        hist_header = QLabel("히스토그램")
        hist_header.setStyleSheet(
            f"color: {get_color('text_muted')}; font-size: 14px; font-weight: bold; padding: 2px 2px;"
        )
        layout.addWidget(hist_header)

        self.histogram = HistogramWidget()
        layout.addWidget(self.histogram)

        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet(f"color: {get_color('border')};")
        layout.addWidget(line1)

        # ── 커브 ──
        curves_header = QLabel("커브 (Curves)")
        curves_header.setStyleSheet(
            f"color: {get_color('text_muted')}; font-size: 14px; font-weight: bold; padding: 2px 2px;"
        )
        layout.addWidget(curves_header)

        self.curves = CurvesWidget()
        self.curves.curve_changed.connect(self._on_preview)
        layout.addWidget(self.curves)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"color: {get_color('border')};")
        layout.addWidget(line2)

        # ── 레벨 (Levels) ──
        levels_header = QLabel("레벨 (Levels)")
        levels_header.setStyleSheet(
            f"color: {get_color('text_muted')}; font-size: 14px; font-weight: bold; padding: 2px 2px;"
        )
        layout.addWidget(levels_header)

        self.slider_black = NumericSlider("블랙 포인트", 0, 255, 0)
        self.slider_white = NumericSlider("화이트 포인트", 0, 255, 255)
        self.slider_gamma = NumericSlider("감마 ×10", 1, 30, 10)

        self.slider_black.valueChanged.connect(self._on_preview)
        self.slider_white.valueChanged.connect(self._on_preview)
        self.slider_gamma.valueChanged.connect(self._on_preview)

        layout.addWidget(self.slider_black)
        layout.addWidget(self.slider_white)
        layout.addWidget(self.slider_gamma)

        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.HLine)
        line3.setStyleSheet(f"color: {get_color('border')};")
        layout.addWidget(line3)

        # ── 색온도 / 틴트 ──
        temp_header = QLabel("색온도 / 틴트")
        temp_header.setStyleSheet(
            f"color: {get_color('text_muted')}; font-size: 14px; font-weight: bold; padding: 2px 2px;"
        )
        layout.addWidget(temp_header)

        self.slider_temperature = NumericSlider("🔥 색온도", -100, 100, 0)
        self.slider_tint = NumericSlider("🌿 틴트", -100, 100, 0)

        self.slider_temperature.valueChanged.connect(self._on_preview)
        self.slider_tint.valueChanged.connect(self._on_preview)

        layout.addWidget(self.slider_temperature)
        layout.addWidget(self.slider_tint)

        # ── 적용/초기화 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_apply = QPushButton("🎨 적용")
        self.btn_apply.setFixedHeight(36)
        self.btn_apply.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_apply.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        self.btn_apply.clicked.connect(self._on_apply)

        self.btn_reset = QPushButton("↩ 초기화")
        self.btn_reset.setFixedHeight(36)
        self.btn_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_reset.setStyleSheet(
            f"background-color: {get_color('bg_button_hover')}; color: {get_color('text_secondary')}; border-radius: 4px; font-size: 13px;"
        )
        self.btn_reset.clicked.connect(self._on_reset)

        btn_row.addWidget(self.btn_apply, 2)
        btn_row.addWidget(self.btn_reset, 1)
        layout.addLayout(btn_row)

        layout.addStretch()

    def set_source_image(self, cv_img: np.ndarray):
        """원본 이미지 설정 + 히스토그램 갱신"""
        self._source_image = cv_img
        self.histogram.update_histogram(cv_img)

    def _build_adjusted(self) -> np.ndarray:
        """현재 설정으로 조정된 이미지 생성"""
        if self._source_image is None:
            return None

        img = self._source_image.copy()

        # 1. 커브 적용
        if not self.curves.is_identity():
            lut_r, lut_g, lut_b = self.curves.get_luts()
            img = CurvesWidget.apply_curves(img, lut_r, lut_g, lut_b)

        # 2. 레벨 적용
        black = self.slider_black.value()
        white = self.slider_white.value()
        gamma = self.slider_gamma.value() / 10.0

        if black != 0 or white != 255 or gamma != 1.0:
            img = self._apply_levels(img, black, white, gamma)

        # 3. 색온도 적용
        temp = self.slider_temperature.value()
        tint = self.slider_tint.value()
        if temp != 0 or tint != 0:
            img = self._apply_temp_tint(img, temp, tint)

        return img

    def _on_preview(self, *args):
        """실시간 프리뷰"""
        adjusted = self._build_adjusted()
        if adjusted is not None:
            self.adjustment_preview.emit(adjusted)

    def _on_apply(self):
        """조정 적용"""
        adjusted = self._build_adjusted()
        if adjusted is not None:
            self.apply_requested.emit(adjusted)
            self._reset_controls()

    def _on_reset(self):
        """모든 설정 초기화"""
        self._reset_controls()
        self.reset_requested.emit()

    def _reset_controls(self):
        """UI 컨트롤 초기화"""
        self.slider_black.setValue(0)
        self.slider_white.setValue(255)
        self.slider_gamma.setValue(10)
        self.slider_temperature.setValue(0)
        self.slider_tint.setValue(0)
        # 커브는 개별 리셋으로 처리

    @staticmethod
    def _apply_levels(img: np.ndarray, black: int, white: int,
                      gamma: float) -> np.ndarray:
        """레벨 조정 — 블랙포인트/화이트포인트/감마"""
        if white <= black:
            white = black + 1

        # 입력 범위 스케일링
        inv_range = 255.0 / max(1, white - black)
        table = np.arange(256, dtype=np.float32)
        table = np.clip((table - black) * inv_range, 0, 255)

        # 감마 보정
        if gamma != 1.0:
            table = 255.0 * np.power(table / 255.0, 1.0 / gamma)

        table = np.clip(table, 0, 255).astype(np.uint8)
        return cv2.LUT(img, table)

    @staticmethod
    def _apply_temp_tint(img: np.ndarray, temp: int, tint: int) -> np.ndarray:
        """색온도(blue↔yellow) / 틴트(green↔magenta) 적용"""
        result = img.astype(np.float32)

        if temp != 0:
            # 따뜻한(+): 빨간 증가 + 파란 감소 / 차가운(-): 반대
            factor = temp / 100.0 * 30
            result[:, :, 2] = np.clip(result[:, :, 2] + factor, 0, 255)  # R
            result[:, :, 0] = np.clip(result[:, :, 0] - factor, 0, 255)  # B

        if tint != 0:
            # 틴트(+): 마젠타(R+) / 틴트(-): 초록(G+)
            factor = tint / 100.0 * 20
            result[:, :, 1] = np.clip(result[:, :, 1] - factor, 0, 255)  # G
            result[:, :, 2] = np.clip(result[:, :, 2] + factor * 0.5, 0, 255)  # R

        return result.astype(np.uint8)

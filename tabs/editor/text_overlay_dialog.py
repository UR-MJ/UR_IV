# tabs/editor/text_overlay_dialog.py
"""텍스트 오버레이 설정 다이얼로그"""
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFontComboBox, QColorDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from widgets.sliders import NumericSlider
from utils.theme_manager import get_color


class TextOverlayDialog(QDialog):
    """텍스트 오버레이 설정 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("텍스트 오버레이")
        self.setFixedSize(380, 400)
        self._color = QColor("#FFFFFF")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 텍스트 입력
        layout.addWidget(QLabel("텍스트:"))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("표시할 텍스트를 입력하세요")
        self.text_input.setStyleSheet(
            f"background: {get_color('bg_button')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 6px; font-size: 14px;"
        )
        layout.addWidget(self.text_input)

        # 폰트
        layout.addWidget(QLabel("폰트:"))
        self.font_combo = QFontComboBox()
        self.font_combo.setStyleSheet(
            f"background: {get_color('bg_button')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self.font_combo)

        # 크기
        self.slider_size = NumericSlider("크기", 8, 200, 32)
        layout.addWidget(self.slider_size)

        # 색상
        color_row = QHBoxLayout()
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(32, 32)
        self._update_color_preview()
        color_row.addWidget(self.color_preview)

        btn_color = QPushButton("색상 선택")
        btn_color.setFixedHeight(32)
        btn_color.setStyleSheet(
            f"background: {get_color('bg_button')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 12px;"
        )
        btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(btn_color)
        color_row.addStretch()
        layout.addLayout(color_row)

        # 회전
        self.slider_rotation = NumericSlider("회전", -180, 180, 0)
        layout.addWidget(self.slider_rotation)

        # 투명도
        self.slider_opacity = NumericSlider("투명도 %", 1, 100, 100)
        layout.addWidget(self.slider_opacity)

        layout.addStretch()

        # 버튼
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("적용")
        btn_ok.setFixedHeight(36)
        btn_ok.setStyleSheet(
            f"background-color: {get_color('accent')}; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        btn_ok.clicked.connect(self.accept)

        btn_cancel = QPushButton("취소")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            f"background-color: {get_color('bg_button_hover')}; color: {get_color('text_secondary')}; border-radius: 4px; font-size: 13px;"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_ok, 2)
        btn_row.addWidget(btn_cancel, 1)
        layout.addLayout(btn_row)

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "텍스트 색상")
        if color.isValid():
            self._color = color
            self._update_color_preview()

    def _update_color_preview(self):
        self.color_preview.setStyleSheet(
            f"background-color: {self._color.name()}; border: 2px solid {get_color('text_muted')}; border-radius: 4px;"
        )

    def get_config(self) -> dict:
        """설정값 반환"""
        return {
            'text': self.text_input.text(),
            'font_family': self.font_combo.currentFont().family(),
            'font_size': self.slider_size.value(),
            'color': (self._color.red(), self._color.green(), self._color.blue()),
            'rotation': self.slider_rotation.value(),
            'opacity': self.slider_opacity.value() / 100.0,
        }

    @staticmethod
    def render_text_on_image(cv_img: np.ndarray, config: dict,
                             x_pct: float, y_pct: float) -> np.ndarray:
        """이미지 위에 텍스트 합성"""
        from tabs.editor.watermark_panel import WatermarkPanel

        text = config['text']
        if not text.strip():
            return cv_img

        font_family = config.get('font_family', '')
        font_size = config['font_size']
        color = config['color']  # RGB tuple
        opacity = config['opacity']
        rotation = config['rotation']

        # PIL로 텍스트 렌더링 (BGRA)
        text_bgra = WatermarkPanel._render_text_pil(
            text, font_family, font_size, (color[2], color[1], color[0])
        )

        # 알파에 opacity 적용
        text_bgra[:, :, 3] = (
            text_bgra[:, :, 3].astype(np.float32) * opacity
        ).astype(np.uint8)

        # 회전
        if rotation != 0:
            rh, rw = text_bgra.shape[:2]
            center = (rw // 2, rh // 2)
            M = cv2.getRotationMatrix2D(center, rotation, 1.0)
            cos_v, sin_v = np.abs(M[0, 0]), np.abs(M[0, 1])
            nw = int(rh * sin_v + rw * cos_v)
            nh = int(rh * cos_v + rw * sin_v)
            M[0, 2] += (nw / 2) - center[0]
            M[1, 2] += (nh / 2) - center[1]
            text_bgra = cv2.warpAffine(
                text_bgra, M, (nw, nh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0, 0)
            )

        # 배치 위치 계산
        img_h, img_w = cv_img.shape[:2]
        th, tw = text_bgra.shape[:2]
        cx = int(img_w * x_pct / 100.0)
        cy = int(img_h * y_pct / 100.0)
        x1 = cx - tw // 2
        y1 = cy - th // 2

        # 클리핑
        sx = max(0, -x1)
        sy = max(0, -y1)
        dx = max(0, x1)
        dy = max(0, y1)
        ew = min(tw - sx, img_w - dx)
        eh = min(th - sy, img_h - dy)
        if ew <= 0 or eh <= 0:
            return cv_img

        result = cv_img.copy()
        overlay = text_bgra[sy:sy+eh, sx:sx+ew]
        alpha = overlay[:, :, 3:4].astype(np.float32) / 255.0
        fg = overlay[:, :, :3].astype(np.float32)
        bg = result[dy:dy+eh, dx:dx+ew].astype(np.float32)
        result[dy:dy+eh, dx:dx+ew] = (fg * alpha + bg * (1.0 - alpha)).astype(np.uint8)

        return result

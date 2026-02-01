# tabs/editor/watermark_panel.py
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QComboBox, QCheckBox, QFileDialog, QGroupBox, QColorDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase
from widgets.sliders import NumericSlider


_PRESETS = {
    "좌상": (5, 5), "우상": (95, 5), "중앙": (50, 50),
    "좌하": (5, 95), "우하": (95, 95),
}


class WatermarkPanel(QWidget):
    """워터마크 패널 - 텍스트 + 이미지 워터마크 (자유 위치 지원)"""

    text_watermark_requested = pyqtSignal(dict)
    image_watermark_requested = pyqtSignal(dict)
    preview_requested = pyqtSignal(dict)   # 미리보기 갱신
    preview_cleared = pyqtSignal()         # 미리보기 해제
    clamp_changed = pyqtSignal(bool)       # 영역 제한 토글

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watermark_color = QColor(255, 255, 255)
        self._watermark_image_path = ""
        self._init_ui()

    def _init_ui(self):
        """UI 초기화"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # ── 텍스트 워터마크 ──
        text_group = QGroupBox("텍스트 워터마크")
        text_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444; border-radius: 6px;
                margin-top: 8px; padding-top: 5px;
                font-weight: bold; color: #888;
            }
        """)
        tl = QVBoxLayout(text_group)
        tl.setContentsMargins(8, 15, 8, 8)
        tl.setSpacing(6)

        self.txt_watermark = QLineEdit()
        self.txt_watermark.setPlaceholderText("워터마크 텍스트 입력...")
        self.txt_watermark.setStyleSheet(
            "background-color: #2C2C2C; color: #DDD; border: 1px solid #555; "
            "border-radius: 4px; padding: 6px; font-size: 13px;"
        )
        tl.addWidget(self.txt_watermark)

        # 폰트 + 색상
        font_color_row = QHBoxLayout()
        self.combo_font = QComboBox()
        self.combo_font.setStyleSheet(
            "background-color: #2C2C2C; color: #DDD; border: 1px solid #555; "
            "border-radius: 4px; padding: 4px;"
        )
        families = QFontDatabase.families()
        self.combo_font.addItems(families[:50] if len(families) > 50 else families)
        font_color_row.addWidget(self.combo_font, 2)

        self.btn_color = QPushButton("⬜ 색상")
        self.btn_color.setFixedHeight(35)
        self.btn_color.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_color.setStyleSheet(
            "background-color: #FFFFFF; color: #000; border: 1px solid #555; "
            "border-radius: 4px; font-size: 13px; font-weight: bold;"
        )
        self.btn_color.clicked.connect(self._pick_color)
        font_color_row.addWidget(self.btn_color, 1)
        tl.addLayout(font_color_row)

        self.slider_font_size = NumericSlider("크기", 8, 200, 36)
        tl.addWidget(self.slider_font_size)

        # 위치: 프리셋 버튼 + X/Y 슬라이더
        tl.addWidget(self._build_position_section("text"))

        self.slider_text_opacity = NumericSlider("투명도", 0, 100, 50)
        tl.addWidget(self.slider_text_opacity)

        self.slider_text_rotation = NumericSlider("회전", -180, 180, 0)
        tl.addWidget(self.slider_text_rotation)

        self.chk_tile = QCheckBox("타일 반복")
        self.chk_tile.setStyleSheet("color: #AAA; font-size: 12px;")
        tl.addWidget(self.chk_tile)

        self.btn_apply_text = QPushButton("✅ 텍스트 워터마크 적용")
        self.btn_apply_text.setFixedHeight(35)
        self.btn_apply_text.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_apply_text.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        self.btn_apply_text.clicked.connect(self._on_apply_text)
        tl.addWidget(self.btn_apply_text)
        tl.addStretch()

        layout.addWidget(text_group)

        # ── 이미지 워터마크 ──
        img_group = QGroupBox("이미지 워터마크")
        img_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444; border-radius: 6px;
                margin-top: 8px; padding-top: 5px;
                font-weight: bold; color: #888;
            }
        """)
        il = QVBoxLayout(img_group)
        il.setContentsMargins(8, 15, 8, 8)
        il.setSpacing(6)

        self.btn_load_wm_img = QPushButton("📂 이미지 불러오기")
        self.btn_load_wm_img.setFixedHeight(35)
        self.btn_load_wm_img.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_load_wm_img.setStyleSheet(
            "background-color: #2C2C2C; color: #DDD; border: 1px solid #555; "
            "border-radius: 4px; font-size: 13px; font-weight: bold;"
        )
        self.btn_load_wm_img.clicked.connect(self._load_watermark_image)
        il.addWidget(self.btn_load_wm_img)

        self.lbl_wm_preview = QLabel("이미지 없음")
        self.lbl_wm_preview.setStyleSheet("color: #666; font-size: 11px;")
        self.lbl_wm_preview.setFixedHeight(20)
        il.addWidget(self.lbl_wm_preview)

        # 위치: 프리셋 버튼 + X/Y 슬라이더
        il.addWidget(self._build_position_section("img"))

        self.slider_img_opacity = NumericSlider("투명도", 0, 100, 50)
        il.addWidget(self.slider_img_opacity)

        self.slider_img_scale = NumericSlider("크기 (%)", 10, 500, 100)
        il.addWidget(self.slider_img_scale)

        self.btn_apply_img = QPushButton("✅ 이미지 워터마크 적용")
        self.btn_apply_img.setFixedHeight(35)
        self.btn_apply_img.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_apply_img.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        self.btn_apply_img.clicked.connect(self._on_apply_image)
        il.addWidget(self.btn_apply_img)
        il.addStretch()

        layout.addWidget(img_group)

        # ── 공통 옵션 ──
        self.chk_clamp = QCheckBox("이미지 영역 내 제한")
        self.chk_clamp.setChecked(True)
        self.chk_clamp.setStyleSheet("color: #AAA; font-size: 12px; font-weight: bold;")
        self.chk_clamp.setToolTip("워터마크가 이미지 밖으로 나가지 않게 제한합니다")
        self.chk_clamp.toggled.connect(lambda v: self.clamp_changed.emit(v))
        layout.addWidget(self.chk_clamp)
        layout.addStretch()

        # 슬라이더 변경 시 미리보기 갱신 연결
        for slider in [self.slider_font_size, self.slider_text_opacity,
                       self.slider_text_rotation, self.slider_text_x,
                       self.slider_text_y]:
            slider.valueChanged.connect(self._emit_preview_if_active)
        self.txt_watermark.textChanged.connect(self._emit_preview_if_active)
        self.chk_tile.toggled.connect(self._emit_preview_if_active)

        for slider in [self.slider_img_opacity, self.slider_img_scale,
                       self.slider_img_x, self.slider_img_y]:
            slider.valueChanged.connect(self._emit_preview_if_active)

    # ── 위치 섹션 빌더 ──

    def _build_position_section(self, prefix: str) -> QWidget:
        """프리셋 버튼 + X/Y 슬라이더 위치 섹션"""
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(4)

        # 프리셋 버튼
        preset_row = QHBoxLayout()
        preset_row.setSpacing(3)
        btn_style = (
            "background-color: #333; color: #DDD; border: 1px solid #555; "
            "border-radius: 3px; padding: 3px 6px; font-size: 11px;"
        )
        for name, (px, py) in _PRESETS.items():
            btn = QPushButton(name)
            btn.setFixedHeight(26)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, _px=px, _py=py, _pf=prefix: self._set_position(_pf, _px, _py))
            preset_row.addWidget(btn)
        vl.addLayout(preset_row)

        # X / Y 슬라이더 (0~100 %)
        sx = NumericSlider("X 위치 (%)", 0, 100, 95)
        sy = NumericSlider("Y 위치 (%)", 0, 100, 95)
        vl.addWidget(sx)
        vl.addWidget(sy)

        setattr(self, f'slider_{prefix}_x', sx)
        setattr(self, f'slider_{prefix}_y', sy)

        return container

    def _set_position(self, prefix: str, x: int, y: int):
        """프리셋 위치 클릭 → 슬라이더 업데이트"""
        getattr(self, f'slider_{prefix}_x').setValue(x)
        getattr(self, f'slider_{prefix}_y').setValue(y)

    # ── 미리보기 (워터마크 탭 활성 시 자동) ──

    _preview_active = False  # 에디터에서 워터마크 탭이 보일 때 True

    def set_preview_active(self, active: bool):
        """에디터가 워터마크 서브탭 활성/비활성 시 호출"""
        self._preview_active = active
        if active:
            self._emit_preview_if_active()
        else:
            self.preview_cleared.emit()

    def _emit_preview_if_active(self):
        """미리보기가 활성이면 preview_requested 시그널 발행"""
        if not self._preview_active:
            return
        # 텍스트 워터마크가 입력되어 있으면 텍스트 우선
        text = self.txt_watermark.text().strip()
        if text:
            self.preview_requested.emit(self._build_text_config())
            return
        # 이미지 워터마크가 로드되어 있으면
        if self._watermark_image_path and os.path.isfile(self._watermark_image_path):
            self.preview_requested.emit(self._build_image_config())
            return
        # 둘 다 없으면 미리보기 해제
        self.preview_cleared.emit()

    def _active_type(self) -> str:
        """현재 활성 워터마크 타입 ('text' / 'image' / '')"""
        if self.txt_watermark.text().strip():
            return 'text'
        if self._watermark_image_path and os.path.isfile(self._watermark_image_path):
            return 'image'
        return ''

    def set_position_from_image(self, x_pct: float, y_pct: float):
        """InteractiveLabel에서 드래그/클릭으로 위치 변경 시 호출"""
        x_val = max(0, min(100, int(x_pct)))
        y_val = max(0, min(100, int(y_pct)))
        atype = self._active_type()
        if atype == 'text':
            self.slider_text_x.setValue(x_val)
            self.slider_text_y.setValue(y_val)
        elif atype == 'image':
            self.slider_img_x.setValue(x_val)
            self.slider_img_y.setValue(y_val)

    # ── config 빌더 ──

    def _build_text_config(self) -> dict:
        return {
            'type': 'text',
            'text': self.txt_watermark.text().strip(),
            'font_family': self.combo_font.currentText(),
            'font_size': self.slider_font_size.value(),
            'color': (self._watermark_color.blue(), self._watermark_color.green(), self._watermark_color.red()),
            'x_pct': self.slider_text_x.value(),
            'y_pct': self.slider_text_y.value(),
            'opacity': self.slider_text_opacity.value() / 100.0,
            'rotation': self.slider_text_rotation.value(),
            'tile': self.chk_tile.isChecked(),
        }

    def _build_image_config(self) -> dict:
        return {
            'type': 'image',
            'image_path': self._watermark_image_path,
            'x_pct': self.slider_img_x.value(),
            'y_pct': self.slider_img_y.value(),
            'opacity': self.slider_img_opacity.value() / 100.0,
            'scale': self.slider_img_scale.value() / 100.0,
        }

    # ── 이벤트 핸들러 ──

    def _pick_color(self):
        """색상 선택 다이얼로그"""
        color = QColorDialog.getColor(self._watermark_color, self, "워터마크 색상 선택")
        if color.isValid():
            self._watermark_color = color
            self.btn_color.setStyleSheet(
                f"background-color: {color.name()}; color: {'#000' if color.lightness() > 128 else '#FFF'}; "
                "border: 1px solid #555; border-radius: 4px; font-size: 13px; font-weight: bold;"
            )
            self._emit_preview_if_active()

    def _load_watermark_image(self):
        """워터마크 이미지 파일 로드"""
        path, _ = QFileDialog.getOpenFileName(
            self, "워터마크 이미지 선택", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            self._watermark_image_path = path
            self.lbl_wm_preview.setText(os.path.basename(path))
            self._emit_preview_if_active()

    def _on_apply_text(self):
        """텍스트 워터마크 적용"""
        text = self.txt_watermark.text().strip()
        if not text:
            return
        self.preview_cleared.emit()
        self.text_watermark_requested.emit(self._build_text_config())

    def _on_apply_image(self):
        """이미지 워터마크 적용"""
        if not self._watermark_image_path or not os.path.isfile(self._watermark_image_path):
            return
        self.preview_cleared.emit()
        self.image_watermark_requested.emit(self._build_image_config())

    # ── 렌더링 (정적 메서드) ──

    @staticmethod
    def _pct_to_xy(x_pct: float, y_pct: float, img_w: int, img_h: int, wm_w: int, wm_h: int) -> tuple:
        """퍼센트 위치를 픽셀 좌표로 변환 (중심 기준)"""
        cx = int(img_w * x_pct / 100.0)
        cy = int(img_h * y_pct / 100.0)
        x = cx - wm_w // 2
        y = cy - wm_h // 2
        return x, y

    @staticmethod
    def _render_text_pil(text: str, font_family: str, font_size: int, color_bgr: tuple) -> np.ndarray:
        """PIL로 텍스트를 BGRA numpy 이미지로 렌더링"""
        from PIL import Image, ImageDraw, ImageFont

        # 폰트 로드
        pil_font = None
        if font_family:
            try:
                # 시스템 폰트에서 검색
                from matplotlib import font_manager
                font_path = font_manager.findfont(
                    font_manager.FontProperties(family=font_family),
                    fallback_to_default=True
                )
                if font_path:
                    pil_font = ImageFont.truetype(font_path, font_size)
            except Exception:
                pass
        if pil_font is None:
            try:
                pil_font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                pil_font = ImageFont.load_default()

        # 텍스트 크기 측정
        dummy = Image.new('RGBA', (1, 1))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.textbbox((0, 0), text, font=pil_font)
        tw = bbox[2] - bbox[0] + 20
        th = bbox[3] - bbox[1] + 20

        # RGBA 캔버스에 텍스트 그리기
        canvas = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        # BGR → RGB 변환
        r, g, b = color_bgr[2], color_bgr[1], color_bgr[0]
        draw.text((10 - bbox[0], 10 - bbox[1]), text, font=pil_font, fill=(r, g, b, 255))

        # numpy BGRA로 변환
        arr = np.array(canvas)  # RGBA
        bgra = np.zeros_like(arr)
        bgra[:, :, 0] = arr[:, :, 2]  # B
        bgra[:, :, 1] = arr[:, :, 1]  # G
        bgra[:, :, 2] = arr[:, :, 0]  # R
        bgra[:, :, 3] = arr[:, :, 3]  # A
        return bgra

    @staticmethod
    def render_text_watermark(img: np.ndarray, config: dict) -> np.ndarray:
        """텍스트 워터마크를 이미지에 렌더링 (PIL 기반)"""
        h, w = img.shape[:2]
        text = config['text']
        font_size = config['font_size']
        font_family = config.get('font_family', '')
        color = config['color']  # BGR tuple
        opacity = config['opacity']
        rotation = config['rotation']
        tile = config.get('tile', False)
        x_pct = config.get('x_pct', 50)
        y_pct = config.get('y_pct', 50)

        # PIL로 텍스트 렌더링
        text_bgra = WatermarkPanel._render_text_pil(text, font_family, font_size, color)
        th_t, tw_t = text_bgra.shape[:2]

        if tile:
            # 타일 배치: 회전 시 빈 공간이 생기지 않도록 대각선 길이만큼 확장
            diag = int(np.sqrt(w * w + h * h))
            pad = (diag - min(w, h)) // 2 + max(tw_t, th_t)
            ow = w + pad * 2
            oh = h + pad * 2

            overlay = np.zeros((oh, ow, 4), dtype=np.uint8)
            spacing_x = tw_t + 40
            spacing_y = th_t + 40
            for ty_i in range(0, oh, spacing_y):
                for tx_i in range(0, ow, spacing_x):
                    # 클리핑하여 복사
                    ex = min(tx_i + tw_t, ow)
                    ey = min(ty_i + th_t, oh)
                    sw = ex - tx_i
                    sh = ey - ty_i
                    overlay[ty_i:ey, tx_i:ex] = text_bgra[:sh, :sw]

            if rotation != 0:
                center = (ow // 2, oh // 2)
                M = cv2.getRotationMatrix2D(center, rotation, 1.0)
                overlay = cv2.warpAffine(overlay, M, (ow, oh),
                                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

            # 중앙 크롭 (원본 크기로)
            cx = (ow - w) // 2
            cy = (oh - h) // 2
            overlay = overlay[cy:cy + h, cx:cx + w]

            # 합성
            alpha = overlay[:, :, 3].astype(np.float32) / 255.0 * opacity
            alpha = np.stack([alpha] * 3, axis=-1)
            wm_bgr = overlay[:, :, :3].astype(np.float32)
            result = img.astype(np.float32) * (1 - alpha) + wm_bgr * alpha
            return np.clip(result, 0, 255).astype(np.uint8)

        # 단일 워터마크
        text_bgr = text_bgra[:, :, :3]
        text_alpha = text_bgra[:, :, 3]

        if rotation != 0:
            center = (tw_t // 2, th_t // 2)
            M = cv2.getRotationMatrix2D(center, rotation, 1.0)
            cos_v = np.abs(M[0, 0])
            sin_v = np.abs(M[0, 1])
            nw = int(th_t * sin_v + tw_t * cos_v)
            nh = int(th_t * cos_v + tw_t * sin_v)
            M[0, 2] += (nw / 2) - center[0]
            M[1, 2] += (nh / 2) - center[1]
            text_bgr = cv2.warpAffine(text_bgr, M, (nw, nh))
            text_alpha = cv2.warpAffine(text_alpha, M, (nw, nh))
            tw_t, th_t = nw, nh

        rh, rw = text_bgr.shape[:2]
        x, y = WatermarkPanel._pct_to_xy(x_pct, y_pct, w, h, rw, rh)

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + rw)
        y2 = min(h, y + rh)
        sx1 = x1 - x
        sy1 = y1 - y
        sx2 = sx1 + (x2 - x1)
        sy2 = sy1 + (y2 - y1)

        if x2 <= x1 or y2 <= y1:
            return img

        roi = img[y1:y2, x1:x2].astype(np.float32)
        wm_roi = text_bgr[sy1:sy2, sx1:sx2].astype(np.float32)
        alpha = text_alpha[sy1:sy2, sx1:sx2].astype(np.float32) / 255.0 * opacity
        alpha = np.stack([alpha] * 3, axis=-1)

        blended = roi * (1 - alpha) + wm_roi * alpha
        result = img.copy()
        result[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)
        return result

    @staticmethod
    def render_image_watermark(img: np.ndarray, config: dict) -> np.ndarray:
        """이미지 워터마크를 렌더링"""
        h, w = img.shape[:2]
        wm_path = config['image_path']
        opacity = config['opacity']
        scale_val = config['scale']
        x_pct = config.get('x_pct', 50)
        y_pct = config.get('y_pct', 50)

        wm_img = cv2.imread(wm_path, cv2.IMREAD_UNCHANGED)
        if wm_img is None:
            return img

        wm_h, wm_w = wm_img.shape[:2]
        new_w = max(1, int(wm_w * scale_val))
        new_h = max(1, int(wm_h * scale_val))
        wm_img = cv2.resize(wm_img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        if wm_img.shape[2] == 4:
            wm_bgr = wm_img[:, :, :3]
            wm_alpha = wm_img[:, :, 3].astype(np.float32) / 255.0 * opacity
        else:
            wm_bgr = wm_img
            wm_alpha = np.ones((new_h, new_w), dtype=np.float32) * opacity

        x, y = WatermarkPanel._pct_to_xy(x_pct, y_pct, w, h, new_w, new_h)

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + new_w)
        y2 = min(h, y + new_h)
        sx1 = x1 - x
        sy1 = y1 - y
        sx2 = sx1 + (x2 - x1)
        sy2 = sy1 + (y2 - y1)

        if x2 <= x1 or y2 <= y1:
            return img

        roi = img[y1:y2, x1:x2].astype(np.float32)
        wm_roi = wm_bgr[sy1:sy2, sx1:sx2].astype(np.float32)
        alpha = wm_alpha[sy1:sy2, sx1:sx2]
        alpha = np.stack([alpha] * 3, axis=-1)

        blended = roi * (1 - alpha) + wm_roi * alpha
        result = img.copy()
        result[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)
        return result

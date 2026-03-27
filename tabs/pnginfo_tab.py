# tabs/pnginfo_tab.py
import os
import json
import base64
from io import BytesIO
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTextEdit,
    QFileDialog, QMessageBox, QSplitter, QGroupBox, QGridLayout, QFrame,
    QCheckBox, QTabWidget, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QThread
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QImage
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from utils.theme_manager import get_color


# ──────────────────────────────────────────────────────
#  슬라이더 오버레이 위젯
# ──────────────────────────────────────────────────────

class CompareOverlayWidget(QWidget):
    """두 이미지를 겹쳐놓고 슬라이더로 Before/After 비교"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap_a = None  # 왼쪽 (Before)
        self.pixmap_b = None  # 오른쪽 (After)
        self.slider_ratio = 0.5  # 0.0 ~ 1.0
        self._dragging = False
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)
        self.setStyleSheet(f"background-color: {get_color('bg_primary')};")

    def set_image_a(self, pixmap: QPixmap):
        self.pixmap_a = pixmap
        self.slider_ratio = 0.5
        self.update()

    def set_image_b(self, pixmap: QPixmap):
        self.pixmap_b = pixmap
        self.slider_ratio = 0.5
        self.update()

    def paintEvent(self, event):
        if not self.pixmap_a and not self.pixmap_b:
            painter = QPainter(self)
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "이미지 A, B를 로드하세요")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self.width(), self.height()

        # 이미지를 위젯 크기에 맞게 스케일
        scaled_a = self._scale_pixmap(self.pixmap_a, w, h) if self.pixmap_a else None
        scaled_b = self._scale_pixmap(self.pixmap_b, w, h) if self.pixmap_b else None

        # 이미지 중앙 배치 오프셋
        def get_offset(pm):
            if pm is None:
                return 0, 0
            return (w - pm.width()) // 2, (h - pm.height()) // 2

        split_x = int(w * self.slider_ratio)

        # A 이미지 (왼쪽 영역)
        if scaled_a:
            ox, oy = get_offset(scaled_a)
            painter.setClipRect(QRect(0, 0, split_x, h))
            painter.drawPixmap(ox, oy, scaled_a)

        # B 이미지 (오른쪽 영역)
        if scaled_b:
            ox, oy = get_offset(scaled_b)
            painter.setClipRect(QRect(split_x, 0, w - split_x, h))
            painter.drawPixmap(ox, oy, scaled_b)
        elif scaled_a:
            # B가 없으면 A를 오른쪽에도 표시
            ox, oy = get_offset(scaled_a)
            painter.setClipRect(QRect(split_x, 0, w - split_x, h))
            painter.drawPixmap(ox, oy, scaled_a)

        painter.setClipping(False)

        # 분할선
        pen = QPen(QColor(255, 60, 60), 2)
        painter.setPen(pen)
        painter.drawLine(split_x, 0, split_x, h)

        # 분할선 핸들 (삼각형)
        handle_y = h // 2
        painter.setBrush(QColor(255, 60, 60))
        painter.setPen(Qt.PenStyle.NoPen)
        # 왼쪽 삼각형
        painter.drawPolygon([
            QPoint(split_x - 8, handle_y - 8),
            QPoint(split_x - 8, handle_y + 8),
            QPoint(split_x - 2, handle_y),
        ])
        # 오른쪽 삼각형
        painter.drawPolygon([
            QPoint(split_x + 8, handle_y - 8),
            QPoint(split_x + 8, handle_y + 8),
            QPoint(split_x + 2, handle_y),
        ])

        # A/B 라벨
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.setOpacity(0.7)
        if self.pixmap_a:
            painter.drawText(15, 30, "A")
        if self.pixmap_b:
            painter.drawText(w - 25, 30, "B")

        painter.end()

    def _scale_pixmap(self, pm, w, h):
        if pm is None:
            return None
        return pm.scaled(w, h,
                         Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_slider(event.pos().x())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_slider(event.pos().x())
        # 슬라이더 근처에서 커서 변경
        split_x = int(self.width() * self.slider_ratio)
        if abs(event.pos().x() - split_x) < 15:
            self.setCursor(Qt.CursorShape.SplitHCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def _update_slider(self, x):
        self.slider_ratio = max(0.0, min(1.0, x / max(1, self.width())))
        self.update()


# ──────────────────────────────────────────────────────
#  비교 GIF 생성 워커
# ──────────────────────────────────────────────────────

class CompareGifWorker(QThread):
    """비교 이미지를 GIF 애니메이션으로 저장하는 워커"""
    progress = pyqtSignal(int)   # 진행률 (0~100)
    finished = pyqtSignal(str)   # 완료 시 저장 경로
    error = pyqtSignal(str)

    def __init__(self, pixmap_a: QPixmap, pixmap_b: QPixmap,
                 save_path: str, duration_ms: int = 80):
        super().__init__()
        self._pixmap_a = pixmap_a
        self._pixmap_b = pixmap_b
        self._save_path = save_path
        self._duration = duration_ms

    def _render_frame(self, ratio: float, w: int, h: int) -> Image.Image:
        """특정 slider_ratio에서 비교 프레임을 렌더링"""
        img = QImage(w, h, QImage.Format.Format_RGB32)
        img.fill(QColor(26, 26, 26))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        scaled_a = self._pixmap_a.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ) if self._pixmap_a else None
        scaled_b = self._pixmap_b.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ) if self._pixmap_b else None

        def offset(pm):
            if pm is None:
                return 0, 0
            return (w - pm.width()) // 2, (h - pm.height()) // 2

        split_x = int(w * ratio)

        if scaled_a:
            ox, oy = offset(scaled_a)
            p.setClipRect(QRect(0, 0, split_x, h))
            p.drawPixmap(ox, oy, scaled_a)
        if scaled_b:
            ox, oy = offset(scaled_b)
            p.setClipRect(QRect(split_x, 0, w - split_x, h))
            p.drawPixmap(ox, oy, scaled_b)

        p.setClipping(False)

        # 분할선
        pen = QPen(QColor(255, 60, 60), max(2, w // 400))
        p.setPen(pen)
        p.drawLine(split_x, 0, split_x, h)
        p.end()

        # QImage → PIL Image
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        pil_img = Image.frombytes("RGBA", (w, h), bytes(ptr), "raw", "BGRA")
        return pil_img.convert("RGB")

    def run(self):
        try:
            ref = self._pixmap_a or self._pixmap_b
            if ref is None:
                self.error.emit("이미지가 없습니다.")
                return

            # 원본 해상도 사용
            w = ref.width()
            h = ref.height()
            # 짝수로 맞춤
            w = w if w % 2 == 0 else w + 1
            h = h if h % 2 == 0 else h + 1

            # 0→1→0 스윕 (총 50프레임: 25 정방향 + 25 역방향)
            steps_half = 25
            total = steps_half * 2
            frames = []

            for i in range(steps_half):
                ratio = i / (steps_half - 1)
                frames.append(self._render_frame(ratio, w, h))
                self.progress.emit(int((i + 1) / total * 100))

            for i in range(steps_half):
                ratio = 1.0 - i / (steps_half - 1)
                frames.append(self._render_frame(ratio, w, h))
                self.progress.emit(int((steps_half + i + 1) / total * 100))

            # GIF 저장
            frames[0].save(
                self._save_path,
                save_all=True,
                append_images=frames[1:],
                duration=self._duration,
                loop=0,
                optimize=True
            )
            self.finished.emit(self._save_path)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────
#  드롭 가능한 이미지 라벨
# ──────────────────────────────────────────────────────

class DropImageLabel(QLabel):
    """드래그 앤 드롭으로 이미지를 받을 수 있는 QLabel"""
    image_dropped = pyqtSignal(str)  # 파일 경로

    def __init__(self, placeholder="이미지를 드래그하거나\n'열기' 버튼을 누르세요", parent=None):
        super().__init__(placeholder, parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"border: 2px dashed {get_color('border')}; border-radius: 10px; color: {get_color('text_muted')};"
        )
        self.setMinimumSize(200, 200)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                self.image_dropped.emit(path)
                break


# ──────────────────────────────────────────────────────
#  이미지 비교 위젯
# ──────────────────────────────────────────────────────

class ImageCompareWidget(QWidget):
    """이미지 비교 탭 - 슬라이더 오버레이 / 나란히 보기"""

    MODE_SLIDER = 0
    MODE_SIDE_BY_SIDE = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap_a = None
        self.pixmap_b = None
        self.path_a = ""
        self.path_b = ""
        self.current_mode = self.MODE_SLIDER

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)

        # 비교 영역 + diff를 스플리터로 배치
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)

        # 상단: 기존 비교 영역
        compare_container = QWidget()
        layout = QVBoxLayout(compare_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # ── 상단 툴바 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_open_ab = QPushButton("📂 이미지 A·B 열기")
        self.btn_open_ab.setFixedHeight(35)
        self.btn_open_ab.setStyleSheet("""
            QPushButton {
                background-color: #5865F2; color: white;
                border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #6975FF; }
        """)
        self.btn_open_ab.setToolTip("이미지 2개를 한 번에 선택")
        self.btn_open_ab.clicked.connect(self._open_images_ab)

        self.btn_swap = QPushButton("🔄 A↔B")
        self.btn_swap.setFixedHeight(35)
        self.btn_swap.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button')}; color: {get_color('text_primary')};
                border: 1px solid {get_color('border')}; border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
        """)
        self.btn_swap.clicked.connect(self._swap_images)

        self.btn_mode = QPushButton("📐 나란히 보기")
        self.btn_mode.setFixedHeight(35)
        self.btn_mode.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button')}; color: {get_color('text_primary')};
                border: 1px solid {get_color('border')}; border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
        """)
        self.btn_mode.clicked.connect(self._toggle_mode)

        _save_btn_style = f"""
            QPushButton {{
                background-color: #2A6A3A; color: white;
                border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #3A7A4A; }}
            QPushButton:disabled {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; }}
        """
        self.btn_save_png = QPushButton("💾 비교 저장")
        self.btn_save_png.setFixedHeight(35)
        self.btn_save_png.setToolTip("현재 비교 화면을 PNG로 저장")
        self.btn_save_png.setStyleSheet(_save_btn_style)
        self.btn_save_png.clicked.connect(self._save_compare_png)

        self.btn_save_gif = QPushButton("🎞️ GIF 저장")
        self.btn_save_gif.setFixedHeight(35)
        self.btn_save_gif.setToolTip("슬라이더 스윕 비교 GIF 저장")
        self.btn_save_gif.setStyleSheet(_save_btn_style)
        self.btn_save_gif.clicked.connect(self._save_compare_gif)

        toolbar.addWidget(self.btn_open_ab)
        toolbar.addWidget(self.btn_swap)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_save_png)
        toolbar.addWidget(self.btn_save_gif)
        toolbar.addWidget(self.btn_mode)
        layout.addLayout(toolbar)

        # ── 비교 영역 (스택) ──
        self.view_stack = QStackedWidget()

        # 모드 0: 슬라이더 오버레이
        self.overlay_widget = CompareOverlayWidget()
        self.view_stack.addWidget(self.overlay_widget)

        # 모드 1: 나란히 보기
        self.side_widget = QWidget()
        side_layout = QHBoxLayout(self.side_widget)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(5)

        self.side_label_a = DropImageLabel("A: 이미지를 드래그\n또는 '이미지 A 열기'")
        self.side_label_a.image_dropped.connect(lambda p: self._load_image(p, 'a'))

        self.side_label_b = DropImageLabel("B: 이미지를 드래그\n또는 '이미지 B 열기'")
        self.side_label_b.image_dropped.connect(lambda p: self._load_image(p, 'b'))

        side_splitter = QSplitter(Qt.Orientation.Horizontal)
        side_splitter.addWidget(self.side_label_a)
        side_splitter.addWidget(self.side_label_b)
        side_layout.addWidget(side_splitter)

        self.view_stack.addWidget(self.side_widget)
        layout.addWidget(self.view_stack, stretch=1)

        # 슬라이더 모드에서도 드래그 앤 드롭 지원
        self.setAcceptDrops(True)

        # ── 하단 정보 ──
        info_layout = QHBoxLayout()
        self.info_a = QLabel("A: -")
        self.info_a.setStyleSheet("color: #6AA0D0; font-size: 11px;")
        self.info_b = QLabel("B: -")
        self.info_b.setStyleSheet("color: #D06A6A; font-size: 11px;")
        info_layout.addWidget(self.info_a)
        info_layout.addStretch()
        info_layout.addWidget(self.info_b)
        layout.addLayout(info_layout)

        # 상단 비교 영역을 스플리터에 추가
        self.main_splitter.addWidget(compare_container)

        # 하단: 파라미터 Diff 위젯
        self.param_diff_widget = ParamDiffWidget()
        self.main_splitter.addWidget(self.param_diff_widget)

        self.main_splitter.setSizes([500, 200])
        main_layout.addWidget(self.main_splitter)

    def _open_images_ab(self):
        """이미지 2개를 한 번에 선택하여 A·B로 로드"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "비교할 이미지 2개 선택", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if len(paths) >= 2:
            self._load_image(paths[0], 'a')
            self._load_image(paths[1], 'b')
        elif len(paths) == 1:
            # 1개만 선택한 경우 A가 비어있으면 A에, 아니면 B에
            if self.pixmap_a is None:
                self._load_image(paths[0], 'a')
            else:
                self._load_image(paths[0], 'b')

    def _load_image(self, path, which):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return

        name = os.path.basename(path)
        w, h = pixmap.width(), pixmap.height()
        info_text = f"{which.upper()}: {name} ({w}x{h})"

        if which == 'a':
            self.pixmap_a = pixmap
            self.path_a = path
            self.info_a.setText(info_text)
            self.overlay_widget.set_image_a(pixmap)
            self._update_side_label(self.side_label_a, pixmap)
        else:
            self.pixmap_b = pixmap
            self.path_b = path
            self.info_b.setText(info_text)
            self.overlay_widget.set_image_b(pixmap)
            self._update_side_label(self.side_label_b, pixmap)

        # 두 이미지가 모두 로드되면 파라미터 diff 갱신
        if self.path_a and self.path_b:
            self.param_diff_widget.load_from_paths(self.path_a, self.path_b)

    def _update_side_label(self, label: QLabel, pixmap: QPixmap):
        scaled = pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        label.setPixmap(scaled)
        label.setStyleSheet("border: none;")

    def _swap_images(self):
        self.pixmap_a, self.pixmap_b = self.pixmap_b, self.pixmap_a
        self.path_a, self.path_b = self.path_b, self.path_a

        # 정보 라벨 교체
        text_a, text_b = self.info_a.text(), self.info_b.text()
        if text_a.startswith("A:"):
            text_a = "A:" + text_a[2:]
        if text_b.startswith("B:"):
            text_b = "B:" + text_b[2:]
        # swap the content after the label prefix
        a_content = self.info_a.text()[2:] if len(self.info_a.text()) > 2 else " -"
        b_content = self.info_b.text()[2:] if len(self.info_b.text()) > 2 else " -"
        self.info_a.setText(f"A:{b_content}")
        self.info_b.setText(f"B:{a_content}")

        # 뷰 갱신
        self.overlay_widget.set_image_a(self.pixmap_a)
        self.overlay_widget.set_image_b(self.pixmap_b)
        if self.pixmap_a:
            self._update_side_label(self.side_label_a, self.pixmap_a)
        if self.pixmap_b:
            self._update_side_label(self.side_label_b, self.pixmap_b)

    def _toggle_mode(self):
        if self.current_mode == self.MODE_SLIDER:
            self.current_mode = self.MODE_SIDE_BY_SIDE
            self.view_stack.setCurrentIndex(1)
            self.btn_mode.setText("🔀 슬라이더 비교")
            # 나란히 모드 이미지 갱신
            if self.pixmap_a:
                self._update_side_label(self.side_label_a, self.pixmap_a)
            if self.pixmap_b:
                self._update_side_label(self.side_label_b, self.pixmap_b)
        else:
            self.current_mode = self.MODE_SLIDER
            self.view_stack.setCurrentIndex(0)
            self.btn_mode.setText("📐 나란히 보기")

    # ── 저장 기능 ──

    def _save_compare_png(self):
        """현재 비교 화면을 원본 해상도 PNG로 저장"""
        if not self.pixmap_a and not self.pixmap_b:
            QMessageBox.warning(self, "저장 실패", "비교할 이미지가 없습니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "비교 이미지 저장", "compare.png",
            "PNG (*.png);;JPEG (*.jpg)"
        )
        if not path:
            return

        # 원본 해상도로 렌더링
        ref = self.pixmap_a or self.pixmap_b
        w, h = ref.width(), ref.height()
        ratio = self.overlay_widget.slider_ratio

        result = QImage(w, h, QImage.Format.Format_RGB32)
        result.fill(QColor(26, 26, 26))
        p = QPainter(result)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        split_x = int(w * ratio)

        if self.pixmap_a:
            sa = self.pixmap_a.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
            ox, oy = (w - sa.width()) // 2, (h - sa.height()) // 2
            p.setClipRect(QRect(0, 0, split_x, h))
            p.drawPixmap(ox, oy, sa)

        if self.pixmap_b:
            sb = self.pixmap_b.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
            ox, oy = (w - sb.width()) // 2, (h - sb.height()) // 2
            p.setClipRect(QRect(split_x, 0, w - split_x, h))
            p.drawPixmap(ox, oy, sb)

        p.setClipping(False)
        pen = QPen(QColor(255, 60, 60), max(2, w // 400))
        p.setPen(pen)
        p.drawLine(split_x, 0, split_x, h)
        p.end()

        QPixmap.fromImage(result).save(path)
        QMessageBox.information(self, "저장 완료", f"비교 이미지를 저장했습니다.\n{path}")

    def _save_compare_gif(self):
        """슬라이더 스윕 비교 GIF 저장"""
        if not self.pixmap_a or not self.pixmap_b:
            QMessageBox.warning(self, "저장 실패", "이미지 A, B가 모두 필요합니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "비교 GIF 저장", "compare.gif",
            "GIF (*.gif)"
        )
        if not path:
            return

        self.btn_save_gif.setEnabled(False)
        self.btn_save_gif.setText("🎞️ 생성 중...")

        self._gif_worker = CompareGifWorker(
            self.pixmap_a, self.pixmap_b, path, duration_ms=80
        )
        self._gif_worker.progress.connect(
            lambda v: self.btn_save_gif.setText(f"🎞️ {v}%")
        )
        self._gif_worker.finished.connect(self._on_gif_saved)
        self._gif_worker.error.connect(self._on_gif_error)
        self._gif_worker.start()

    def _on_gif_saved(self, path: str):
        self.btn_save_gif.setEnabled(True)
        self.btn_save_gif.setText("🎞️ GIF 저장")
        QMessageBox.information(self, "저장 완료", f"비교 GIF를 저장했습니다.\n{path}")

    def _on_gif_error(self, msg: str):
        self.btn_save_gif.setEnabled(True)
        self.btn_save_gif.setText("🎞️ GIF 저장")
        QMessageBox.critical(self, "저장 실패", f"GIF 생성 중 오류: {msg}")

    # 슬라이더 모드에서의 드래그 앤 드롭
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                # A가 비어있으면 A에, 아니면 B에
                if self.pixmap_a is None:
                    self._load_image(path, 'a')
                else:
                    self._load_image(path, 'b')
                break


# ──────────────────────────────────────────────────────
#  파라미터 Diff 위젯
# ──────────────────────────────────────────────────────

class ParamDiffWidget(QWidget):
    """두 이미지의 생성 파라미터를 비교하여 Diff 표시"""

    COMPARE_KEYS = [
        'Model', 'Steps', 'CFG scale', 'Sampler', 'Schedule type',
        'Scheduler', 'Seed', 'Size', 'Denoising strength',
        'Hires upscaler', 'Hires upscale', 'Hires steps',
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.params_a: dict = {}
        self.params_b: dict = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        header = QLabel("📊 파라미터 비교 (Diff)")
        header.setStyleSheet(f"color: {get_color('text_primary')}; font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

        self.diff_text = QTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setStyleSheet(
            f"background-color: {get_color('bg_primary')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-family: 'Consolas'; font-size: 11px; padding: 6px;"
        )
        layout.addWidget(self.diff_text)

    def set_params(self, params_a: dict, params_b: dict):
        """두 이미지의 파라미터를 설정하고 diff를 렌더링"""
        self.params_a = params_a
        self.params_b = params_b
        self._render_diff()

    def _parse_metadata(self, path: str) -> dict:
        """이미지 파일에서 생성 파라미터를 파싱"""
        params: dict = {}
        try:
            img = Image.open(path)
            if 'prompt' in img.info or 'workflow' in img.info:
                # ComfyUI 형식 — 간략 파싱
                if 'prompt' in img.info:
                    import json as _json
                    prompt_data = _json.loads(img.info['prompt'])
                    for nid, node in prompt_data.items():
                        if not isinstance(node, dict):
                            continue
                        cls = node.get('class_type', '')
                        inp = node.get('inputs', {})
                        if cls in ('KSampler', 'KSamplerAdvanced'):
                            params['Steps'] = str(inp.get('steps', ''))
                            params['CFG scale'] = str(inp.get('cfg', ''))
                            params['Sampler'] = str(inp.get('sampler_name', ''))
                            params['Scheduler'] = str(inp.get('scheduler', ''))
                            params['Seed'] = str(inp.get('seed', inp.get('noise_seed', '')))
                            params['Denoising strength'] = str(inp.get('denoise', ''))
                        elif cls == 'CheckpointLoaderSimple':
                            params['Model'] = str(inp.get('ckpt_name', ''))
                        elif cls == 'EmptyLatentImage':
                            w = inp.get('width', '')
                            h = inp.get('height', '')
                            if w and h:
                                params['Size'] = f"{w}x{h}"
                        elif cls == 'CLIPTextEncode':
                            text = inp.get('text', '')
                            if isinstance(text, str) and text.strip():
                                if 'prompt' not in params:
                                    params['prompt'] = text
                                elif 'negative_prompt' not in params:
                                    params['negative_prompt'] = text
            elif 'parameters' in img.info:
                raw = img.info['parameters']
                parts = raw.split('\nNegative prompt: ')
                prompt = parts[0].strip()
                negative = ""
                params_line = ""
                if len(parts) > 1:
                    sub = parts[1].split('\nSteps: ')
                    negative = sub[0].strip()
                    if len(sub) > 1:
                        params_line = "Steps: " + sub[1].strip()
                else:
                    for line in raw.split('\n'):
                        if line.startswith("Steps: "):
                            params_line = line
                params['prompt'] = prompt
                params['negative_prompt'] = negative
                if params_line:
                    items = []
                    current = ""
                    in_quotes = False
                    for ch in params_line:
                        if ch == '"':
                            in_quotes = not in_quotes
                            current += ch
                        elif ch == ',' and not in_quotes:
                            items.append(current.strip())
                            current = ""
                        else:
                            current += ch
                    if current.strip():
                        items.append(current.strip())
                    for item in items:
                        if ':' in item:
                            k, v = item.split(':', 1)
                            params[k.strip()] = v.strip().strip('"')
        except Exception:
            pass
        return params

    def load_from_paths(self, path_a: str, path_b: str):
        """경로에서 파라미터를 파싱하고 diff 렌더링"""
        self.params_a = self._parse_metadata(path_a)
        self.params_b = self._parse_metadata(path_b)
        self._render_diff()

    def _render_diff(self):
        """HTML 기반 diff 렌더링"""
        a, b = self.params_a, self.params_b
        if not a and not b:
            self.diff_text.setHtml(f"<span style='color:{get_color('text_muted')};'>파라미터 정보 없음</span>")
            return

        html = "<table style='width:100%; border-collapse:collapse;'>"
        html += (
            f"<tr style='border-bottom:1px solid {get_color('border')};'>"
            f"<th style='text-align:left; padding:4px; color:{get_color('text_secondary')};'>항목</th>"
            "<th style='text-align:left; padding:4px; color:#6AA0D0;'>A</th>"
            "<th style='text-align:left; padding:4px; color:#D06A6A;'>B</th>"
            "</tr>"
        )

        # 고정 키 + 양쪽에만 있는 추가 키
        all_keys = list(self.COMPARE_KEYS)
        for k in set(list(a.keys()) + list(b.keys())):
            if k not in all_keys and k not in ('prompt', 'negative_prompt'):
                all_keys.append(k)

        for key in all_keys:
            va = a.get(key, '')
            vb = b.get(key, '')
            if not va and not vb:
                continue

            if va == vb:
                color_a = color_b = get_color('text_muted')
            else:
                color_a = "#6AA0D0"
                color_b = "#D06A6A"

            html += (
                f"<tr style='border-bottom:1px solid {get_color('border')};'>"
                f"<td style='padding:3px 6px; color:{get_color('text_secondary')};'>{key}</td>"
                f"<td style='padding:3px 6px; color:{color_a};'>{va or '-'}</td>"
                f"<td style='padding:3px 6px; color:{color_b};'>{vb or '-'}</td>"
                f"</tr>"
            )

        # 프롬프트 태그별 diff
        prompt_a = [t.strip() for t in a.get('prompt', '').split(',') if t.strip()]
        prompt_b = [t.strip() for t in b.get('prompt', '').split(',') if t.strip()]
        if prompt_a or prompt_b:
            set_a, set_b = set(prompt_a), set(prompt_b)
            only_a = set_a - set_b
            only_b = set_b - set_a
            common = set_a & set_b

            _muted = get_color('text_muted')
            prompt_html = ""
            for tag in prompt_a:
                if tag in only_a:
                    prompt_html += f"<span style='color:#6AA0D0;'>{tag}</span>, "
                else:
                    prompt_html += f"<span style='color:{_muted};'>{tag}</span>, "

            prompt_html_b = ""
            for tag in prompt_b:
                if tag in only_b:
                    prompt_html_b += f"<span style='color:#D06A6A;'>{tag}</span>, "
                else:
                    prompt_html_b += f"<span style='color:{_muted};'>{tag}</span>, "

            html += (
                f"<tr style='border-bottom:1px solid {get_color('border')};'>"
                f"<td style='padding:3px 6px; color:{get_color('text_secondary')}; vertical-align:top;'>Prompt</td>"
                f"<td style='padding:3px 6px; font-size:10px;'>{prompt_html.rstrip(', ')}</td>"
                f"<td style='padding:3px 6px; font-size:10px;'>{prompt_html_b.rstrip(', ')}</td>"
                f"</tr>"
            )

        html += "</table>"
        self.diff_text.setHtml(html)


# ──────────────────────────────────────────────────────
#  PNG Info 탭 (메인)
# ──────────────────────────────────────────────────────

class PngInfoTab(QWidget):
    """PNG Info 탭 - EXIF 정보 확인 및 전송 + 이미지 비교"""
    generate_signal = pyqtSignal(dict)        # Payload 전송
    send_prompt_signal = pyqtSignal(str, str) # 프롬프트 전송
    send_to_i2i_signal = pyqtSignal(dict)    # I2I로 이미지+설정 전송
    send_to_inpaint_signal = pyqtSignal(dict) # Inpaint로 이미지+설정 전송
    send_to_queue_signal = pyqtSignal(dict)  # 대기열에 추가

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Child 탭 위젯
        self.child_tabs = QTabWidget()
        self.child_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {get_color('border')}; background: {get_color('bg_primary')}; border-radius: 5px;
            }}
            QTabBar::tab {{
                background: {get_color('bg_tertiary')}; color: {get_color('text_muted')}; padding: 8px 20px;
                border-top-left-radius: 5px; border-top-right-radius: 5px;
            }}
            QTabBar::tab:selected {{
                background: {get_color('bg_button')}; color: {get_color('text_primary')};
                border-bottom: 2px solid #5865F2;
            }}
            QTabBar::tab:hover {{ background: {get_color('bg_input')}; }}
        """)

        # ── Tab 1: PNG Info (기존) ──
        png_info_widget = QWidget()
        png_info_widget.setAcceptDrops(True)
        self._setup_pnginfo_ui(png_info_widget)
        self.child_tabs.addTab(png_info_widget, "ℹ️ PNG Info")

        # ── Tab 2: 이미지 비교 ──
        self.compare_widget = ImageCompareWidget()
        self.child_tabs.addTab(self.compare_widget, "🔍 이미지 비교")

        main_layout.addWidget(self.child_tabs)

        self.current_params = {}
        self.current_image_path = None

    def load_compare_images(self, path_a: str, path_b: str):
        """외부에서 두 이미지를 비교 탭에 로드"""
        self.child_tabs.setCurrentIndex(1)  # 이미지 비교 탭으로 전환
        self.compare_widget._load_image(path_a, 'a')
        self.compare_widget._load_image(path_b, 'b')

    def _setup_pnginfo_ui(self, container):
        """기존 PNG Info UI를 container 위젯에 구성"""
        layout = QHBoxLayout(container)

        # --- 왼쪽: 이미지 미리보기 ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        self.image_label = QLabel("이미지를 드래그하거나\n더블클릭 또는 '열기' 버튼을 누르세요.")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(
            f"border: 2px dashed {get_color('border')}; border-radius: 10px; color: {get_color('text_muted')};"
        )
        self.image_label.setMinimumSize(300, 300)
        self.image_label.mouseDoubleClickEvent = lambda e: self.open_image_dialog()

        self.btn_open = QPushButton("📂 이미지 열기")
        self.btn_open.clicked.connect(self.open_image_dialog)
        self.btn_open.setFixedHeight(40)

        left_layout.addWidget(self.image_label)
        left_layout.addWidget(self.btn_open)

        # --- 오른쪽: 정보 및 실행 메뉴 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet(
            "font-family: 'Consolas'; font-size: 10pt; line-height: 1.4;"
        )

        # 실행 메뉴
        btn_group = QGroupBox("실행 메뉴")
        group_layout = QVBoxLayout(btn_group)
        group_layout.setSpacing(10)

        self.btn_gen_now = QPushButton("🚀 T2I로 즉시 생성")
        self.btn_gen_now.setFixedHeight(45)
        self.btn_gen_now.setStyleSheet("""
            QPushButton {
                background-color: #5865F2; color: white; border-radius: 6px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #4752C4; }
        """)
        self.btn_gen_now.setToolTip(
            "이 이미지의 설정(프롬프트, 시드, 모델 등) 그대로 바로 생성합니다."
        )
        self.btn_gen_now.clicked.connect(self.on_generate_immediately)

        self.chk_random_seed = QCheckBox("🎲 랜덤 시드 적용 (Random Seed)")
        self.chk_random_seed.setChecked(True)
        self.chk_random_seed.setStyleSheet(
            f"color: {get_color('text_primary')}; font-weight: bold; margin-left: 5px;"
        )

        self.btn_add_queue = QPushButton("📋 대기열에 추가")
        self.btn_add_queue.setFixedHeight(45)
        self.btn_add_queue.setStyleSheet("""
            QPushButton {
                background-color: #E67E22; color: white; border-radius: 6px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #D35400; }
        """)
        self.btn_add_queue.setToolTip("이 이미지의 설정을 대기열에 추가합니다.")
        self.btn_add_queue.clicked.connect(self.on_add_to_queue)

        group_layout.addWidget(self.btn_gen_now)
        group_layout.addWidget(self.btn_add_queue)
        group_layout.addWidget(self.chk_random_seed)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background-color: {get_color('border')}; margin: 5px 0;")
        group_layout.addWidget(line)

        transfer_layout = QGridLayout()
        transfer_layout.setSpacing(8)

        self.btn_send_t2i = QPushButton("📝 T2I로 보내기")
        self.btn_send_i2i = QPushButton("🖼️ I2I로 보내기")
        self.btn_send_inpaint = QPushButton("🎨 INPAINT로 보내기")

        for btn in [self.btn_send_t2i, self.btn_send_i2i, self.btn_send_inpaint]:
            btn.setFixedHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-weight: bold; background-color: {get_color('bg_button')};
                    border: 1px solid {get_color('border')}; border-radius: 5px;
                }}
                QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
            """)

        self.btn_send_t2i.clicked.connect(self.on_send_to_prompt)
        self.btn_send_t2i.setToolTip(
            "프롬프트와 네거티브 프롬프트만 T2I 입력창으로 복사합니다."
        )
        self.btn_send_i2i.clicked.connect(self.on_send_to_i2i)
        self.btn_send_i2i.setToolTip("이미지와 프롬프트를 I2I(img2img) 탭으로 전송합니다.")
        self.btn_send_inpaint.clicked.connect(self.on_send_to_inpaint)
        self.btn_send_inpaint.setToolTip("이미지와 프롬프트를 Inpaint 탭으로 전송합니다.")

        transfer_layout.addWidget(self.btn_send_t2i, 0, 0, 1, 2)
        transfer_layout.addWidget(self.btn_send_i2i, 1, 0)
        transfer_layout.addWidget(self.btn_send_inpaint, 1, 1)

        group_layout.addLayout(transfer_layout)

        right_layout.addWidget(QLabel("<h2>📋 PNG Info (EXIF)</h2>"))
        right_layout.addWidget(self.info_text)

        # 메타데이터 편집 버튼
        edit_bar = QHBoxLayout()
        edit_bar.setSpacing(8)

        self.btn_edit_meta = QPushButton("✏️ 편집")
        self.btn_edit_meta.setFixedHeight(32)
        self.btn_edit_meta.setCheckable(True)
        self.btn_edit_meta.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button')}; color: {get_color('text_primary')};
                border: 1px solid {get_color('border')}; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
            QPushButton:checked {{
                background-color: #5865F2; color: white; border-color: #5865F2;
            }}
        """)
        self.btn_edit_meta.toggled.connect(self._toggle_edit_mode)

        self.btn_save_meta = QPushButton("💾 메타데이터 저장")
        self.btn_save_meta.setFixedHeight(32)
        self.btn_save_meta.setEnabled(False)
        self.btn_save_meta.setStyleSheet(f"""
            QPushButton {{
                background-color: #2A8A2A; color: white;
                border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #3A9A3A; }}
            QPushButton:disabled {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; }}
        """)
        self.btn_save_meta.clicked.connect(self._save_metadata)

        edit_bar.addWidget(self.btn_edit_meta)
        edit_bar.addWidget(self.btn_save_meta)
        edit_bar.addStretch()
        right_layout.addLayout(edit_bar)

        right_layout.addWidget(btn_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 600])

        layout.addWidget(splitter)

    # ──────────────────────────────────────────────────
    #  드래그 앤 드롭 (PNG Info 탭)
    # ──────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                self.process_image(f)
                break

    # ──────────────────────────────────────────────────
    #  PNG Info 기능
    # ──────────────────────────────────────────────────

    def open_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "이미지 열기", "",
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.process_image(path)

    def process_image(self, path):
        self.current_image_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.image_label.setPixmap(
                pixmap.scaled(
                    self.image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
            self.image_label.setStyleSheet("border: none;")

        try:
            img = Image.open(path)
            self.current_params = {}

            # ComfyUI 형식 감지 (prompt 또는 workflow 키가 있으면 ComfyUI)
            if 'prompt' in img.info or 'workflow' in img.info:
                self._parse_comfyui_info(img.info)
            elif 'parameters' in img.info:
                # WebUI (A1111/Forge) 형식
                raw_info = img.info['parameters']
                self.parse_generation_info(raw_info)
                self._display_webui_formatted()
            else:
                # PNG Info가 없으면 EXIF UserComment 시도 (JPEG 등)
                exif_text = self._read_exif_usercomment(img)
                if exif_text:
                    self.parse_generation_info(exif_text)
                    self._display_webui_formatted()
                else:
                    self.info_text.setPlainText("표준 PNG Info가 없습니다.")
        except Exception as e:
            self.info_text.setPlainText(f"이미지 읽기 오류: {e}")

    def _read_exif_usercomment(self, img) -> str | None:
        """EXIF UserComment 태그에서 생성 정보 텍스트 추출 (JPEG 등)"""
        try:
            exif_data = img.getexif()
            if not exif_data:
                return None
            # EXIF IFD 내 UserComment (tag 0x9286)
            from PIL.ExifTags import IFD
            ifd = exif_data.get_ifd(IFD.Exif)
            user_comment = ifd.get(0x9286)
            if user_comment:
                if isinstance(user_comment, str) and user_comment.strip():
                    return user_comment.strip()
                if isinstance(user_comment, bytes):
                    # A1111/piexif: UNICODE prefix + UTF-16 인코딩
                    if user_comment.startswith(b'UNICODE\x00'):
                        payload = user_comment[8:]
                        # BOM으로 endian 판별, 없으면 UTF-16-BE (piexif 기본)
                        if payload.startswith(b'\xff\xfe'):
                            text = payload.decode('utf-16-le', errors='replace')
                        elif payload.startswith(b'\xfe\xff'):
                            text = payload.decode('utf-16-be', errors='replace')
                        else:
                            # piexif 기본은 UTF-16-BE, 실패 시 UTF-16-LE 시도
                            try:
                                text = payload.decode('utf-16-be')
                            except UnicodeDecodeError:
                                text = payload.decode('utf-16-le', errors='replace')
                        return text.strip('\x00').strip() or None
                    elif user_comment.startswith(b'ASCII\x00\x00\x00'):
                        return user_comment[8:].decode('ascii', errors='replace').strip('\x00').strip() or None
                    else:
                        # prefix 없음 — null 바이트 포함 시 UTF-16 시도
                        if b'\x00' in user_comment[:8]:
                            try:
                                text = user_comment.decode('utf-16', errors='replace')
                                return text.strip('\x00').strip() or None
                            except Exception:
                                pass
                        return user_comment.decode('utf-8', errors='replace').strip('\x00').strip() or None
        except Exception:
            pass
        return None

    def parse_generation_info(self, text):
        try:
            parts = text.split('\nNegative prompt: ')
            prompt = parts[0].strip()
            negative = ""
            params_line = ""

            if len(parts) > 1:
                sub_parts = parts[1].split('\nSteps: ')
                negative = sub_parts[0].strip()
                if len(sub_parts) > 1:
                    params_line = "Steps: " + sub_parts[1].strip()
            else:
                lines = text.split('\n')
                prompt = ""
                for line in lines:
                    if line.startswith("Steps: "):
                        params_line = line
                    else:
                        prompt += line + "\n"
                prompt = prompt.strip()

            self.current_params['prompt'] = prompt
            self.current_params['negative_prompt'] = negative

            if params_line:
                # 따옴표 안의 쉼표를 보호하여 파싱 (Lora hashes 등)
                # \" 이스케이프 시퀀스도 올바르게 처리
                items = []
                current = ""
                in_quotes = False
                i = 0
                while i < len(params_line):
                    ch = params_line[i]
                    if ch == '\\' and i + 1 < len(params_line) and params_line[i + 1] == '"':
                        # \" 이스케이프 — 따옴표 상태 변경 없이 그대로 추가
                        current += params_line[i:i + 2]
                        i += 2
                        continue
                    elif ch == '"':
                        in_quotes = not in_quotes
                        current += ch
                    elif ch == ',' and not in_quotes:
                        items.append(current.strip())
                        current = ""
                    else:
                        current += ch
                    i += 1
                if current.strip():
                    items.append(current.strip())

                for item in items:
                    if ':' in item:
                        k, v = item.split(':', 1)
                        self.current_params[k.strip()] = v.strip().strip('"')
        except Exception as e:
            print(f"⚠️ PNG Info 파싱 실패: {e}")
            self.current_params['prompt'] = text.strip()
            self.current_params['negative_prompt'] = ""

    def _display_webui_formatted(self):
        """WebUI 파라미터를 깔끔하게 포맷팅하여 표시"""
        p = self.current_params

        display_lines = [
            "═══════════════════════════════════════════",
            "  🎨 WebUI (A1111/Forge) 메타데이터",
            "═══════════════════════════════════════════",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📝 Positive Prompt",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            p.get('prompt', '(없음)'),
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🚫 Negative Prompt",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            p.get('negative_prompt', '(없음)'),
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "⚙️ 생성 파라미터",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        # 기본 파라미터
        if 'Model' in p:
            display_lines.append(f"  🎯 Model: {p['Model']}")
        if 'Model hash' in p:
            display_lines.append(f"  🔑 Model Hash: {p['Model hash']}")
        if 'Seed' in p:
            display_lines.append(f"  🎲 Seed: {p['Seed']}")
        if 'Steps' in p:
            display_lines.append(f"  📊 Steps: {p['Steps']}")
        if 'CFG scale' in p:
            display_lines.append(f"  ⚡ CFG Scale: {p['CFG scale']}")
        if 'Sampler' in p:
            display_lines.append(f"  🔄 Sampler: {p['Sampler']}")
        if 'Schedule type' in p:
            display_lines.append(f"  📅 Scheduler: {p['Schedule type']}")
        if 'Size' in p:
            display_lines.append(f"  📐 Size: {p['Size']}")

        # Hires.fix 파라미터
        hires_params = []
        if 'Hires upscale' in p:
            hires_params.append(f"Scale: {p['Hires upscale']}")
        if 'Hires upscaler' in p:
            hires_params.append(f"Upscaler: {p['Hires upscaler']}")
        if 'Hires steps' in p:
            hires_params.append(f"Steps: {p['Hires steps']}")
        if 'Denoising strength' in p:
            hires_params.append(f"Denoise: {p['Denoising strength']}")

        if hires_params:
            display_lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "🔍 Hires.fix",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ])
            for param in hires_params:
                display_lines.append(f"  • {param}")

        # LoRA 파라미터 — 프롬프트에서 <lora:...> 추출 + Lora hashes
        import re as _re
        lora_entries = []
        seen_lora_names = set()

        prompt_text = p.get('prompt', '')
        for m in _re.finditer(r'<lora:\s*([^:>]+):([^>]+)>', prompt_text):
            name = m.group(1).strip()
            lora_entries.append(f"{name}  (weight: {m.group(2).strip()})")
            seen_lora_names.add(name)
        neg_text = p.get('negative_prompt', '')
        for m in _re.finditer(r'<lora:\s*([^:>]+):([^>]+)>', neg_text):
            name = m.group(1).strip()
            lora_entries.append(f"{name}  (weight: {m.group(2).strip()}, negative)")
            seen_lora_names.add(name)
        # Lora hashes 키에서 추가 정보
        lora_hashes = p.get('Lora hashes', '')
        if lora_hashes:
            for part in lora_hashes.split(', '):
                part = part.strip()
                if ':' in part:
                    name, hash_val = part.split(':', 1)
                    name = name.strip()
                    hash_val = hash_val.strip()
                    if name not in seen_lora_names:
                        lora_entries.append(f"{name}  (hash: {hash_val})")
                        seen_lora_names.add(name)

        if lora_entries:
            display_lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "🔗 LoRA",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ])
            for entry in lora_entries:
                display_lines.append(f"  • {entry}")

        # ADetailer 파라미터
        adetailer_params = []
        for key, val in p.items():
            if key.startswith('ADetailer'):
                adetailer_params.append(f"{key}: {val}")

        if adetailer_params:
            display_lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "🎭 ADetailer",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ])
            for param in adetailer_params:
                display_lines.append(f"  • {param}")

        # 기타 파라미터
        known_keys = {
            'prompt', 'negative_prompt', 'Model', 'Model hash', 'Seed', 'Steps',
            'CFG scale', 'Sampler', 'Schedule type', 'Size', 'Hires upscale',
            'Hires upscaler', 'Hires steps', 'Denoising strength', 'Lora hashes',
            'TI hashes',
        }
        other_params = []
        for key, val in p.items():
            if key not in known_keys and not key.startswith('ADetailer'):
                other_params.append(f"{key}: {val}")

        if other_params:
            display_lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "📦 기타 파라미터",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ])
            for param in other_params:
                display_lines.append(f"  • {param}")

        display_lines.extend([
            "",
            "═══════════════════════════════════════════",
        ])

        self.info_text.setPlainText('\n'.join(display_lines))

    def _parse_comfyui_info(self, info: dict):
        """ComfyUI 형식의 메타데이터 파싱"""
        try:
            prompt_data = {}
            workflow_data = {}

            # prompt (API 형식) 파싱
            if 'prompt' in info:
                try:
                    prompt_data = json.loads(info['prompt'])
                except json.JSONDecodeError:
                    pass

            # workflow (웹 형식) 파싱
            if 'workflow' in info:
                try:
                    workflow_data = json.loads(info['workflow'])
                except json.JSONDecodeError:
                    pass

            # 노드에서 정보 추출
            extracted = self._extract_comfyui_params(prompt_data)

            # current_params 설정
            self.current_params = {
                'prompt': extracted.get('positive_prompt', ''),
                'negative_prompt': extracted.get('negative_prompt', ''),
                'Steps': str(extracted.get('steps', 20)),
                'Seed': str(extracted.get('seed', -1)),
                'CFG scale': str(extracted.get('cfg', 7.0)),
                'Sampler': extracted.get('sampler', 'euler'),
                'Scheduler': extracted.get('scheduler', 'normal'),
                'Size': f"{extracted.get('width', 1024)}x{extracted.get('height', 1024)}",
                'Model': extracted.get('checkpoint', ''),
                'Denoising strength': str(extracted.get('denoise', 1.0)),
            }

            # 표시용 텍스트 생성
            display_lines = [
                "═══════════════════════════════════════════",
                "  📦 ComfyUI 워크플로우 메타데이터",
                "═══════════════════════════════════════════",
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "📝 Positive Prompt",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                extracted.get('positive_prompt', '(없음)'),
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "🚫 Negative Prompt",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                extracted.get('negative_prompt', '(없음)'),
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "⚙️ 생성 파라미터",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"  🎯 Checkpoint: {extracted.get('checkpoint', '(감지 불가)')}",
                f"  🎲 Seed: {extracted.get('seed', -1)}",
                f"  📊 Steps: {extracted.get('steps', 20)}",
                f"  ⚡ CFG: {extracted.get('cfg', 7.0)}",
                f"  🔄 Sampler: {extracted.get('sampler', 'euler')}",
                f"  📅 Scheduler: {extracted.get('scheduler', 'normal')}",
                f"  📐 Size: {extracted.get('width', 1024)} x {extracted.get('height', 1024)}",
                f"  🎨 Denoise: {extracted.get('denoise', 1.0)}",
            ]

            # KSampler 타입 표시
            if extracted.get('ksampler_type'):
                display_lines.append(f"  🔧 KSampler Type: {extracted['ksampler_type']}")

            # 추가 노드 정보
            if extracted.get('extra_nodes'):
                display_lines.extend([
                    "",
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    "📦 감지된 주요 노드",
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                ])
                for node_type, count in extracted['extra_nodes'].items():
                    display_lines.append(f"  • {node_type}: {count}개")

            # 워크플로우 정보
            if workflow_data:
                node_count = len(workflow_data.get('nodes', []))
                link_count = len(workflow_data.get('links', []))
                display_lines.extend([
                    "",
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    "📊 워크플로우 통계",
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    f"  📦 전체 노드 수: {node_count}",
                    f"  🔗 연결 수: {link_count}",
                ])

            display_lines.extend([
                "",
                "═══════════════════════════════════════════",
            ])

            self.info_text.setPlainText('\n'.join(display_lines))

        except Exception as e:
            self.info_text.setPlainText(f"ComfyUI 메타데이터 파싱 오류: {e}")
            import traceback
            traceback.print_exc()

    def _extract_comfyui_params(self, prompt_data: dict) -> dict:
        """ComfyUI prompt JSON에서 파라미터 추출"""
        result = {
            'positive_prompt': '',
            'negative_prompt': '',
            'seed': -1,
            'steps': 20,
            'cfg': 7.0,
            'sampler': 'euler',
            'scheduler': 'normal',
            'width': 1024,
            'height': 1024,
            'checkpoint': '',
            'denoise': 1.0,
            'ksampler_type': '',
            'extra_nodes': {},
        }

        if not prompt_data:
            return result

        # 노드 타입별 분류
        clip_encode_nodes = {}  # node_id -> node_data
        ksampler_nodes = {}     # node_id -> inputs
        checkpoint_nodes = {}   # node_id -> inputs
        latent_nodes = {}       # node_id -> inputs

        for node_id, node_data in prompt_data.items():
            class_type = node_data.get('class_type', '')
            inputs = node_data.get('inputs', {})

            # 노드 타입 카운트
            if class_type not in ['Reroute', 'Note', 'PrimitiveNode']:
                result['extra_nodes'][class_type] = result['extra_nodes'].get(class_type, 0) + 1

            if class_type == 'CLIPTextEncode':
                clip_encode_nodes[node_id] = node_data
            elif class_type in ['KSampler', 'KSamplerAdvanced', 'SamplerCustom']:
                ksampler_nodes[node_id] = inputs
                result['ksampler_type'] = class_type
            elif class_type in ['CheckpointLoaderSimple', 'CheckpointLoader']:
                checkpoint_nodes[node_id] = inputs
            elif class_type in ['EmptyLatentImage', 'EmptySD3LatentImage']:
                latent_nodes[node_id] = inputs

        # Checkpoint 추출
        for node_id, inputs in checkpoint_nodes.items():
            if 'ckpt_name' in inputs:
                result['checkpoint'] = inputs['ckpt_name']
                break

        # KSampler에서 파라미터 추출 + positive/negative 연결 추적
        for node_id, inputs in ksampler_nodes.items():
            if 'seed' in inputs:
                seed_val = inputs['seed']
                if isinstance(seed_val, (int, float)):
                    result['seed'] = int(seed_val)
            if 'steps' in inputs:
                result['steps'] = int(inputs['steps'])
            if 'cfg' in inputs:
                result['cfg'] = float(inputs['cfg'])
            if 'sampler_name' in inputs:
                result['sampler'] = inputs['sampler_name']
            if 'scheduler' in inputs:
                result['scheduler'] = inputs['scheduler']
            if 'denoise' in inputs:
                result['denoise'] = float(inputs['denoise'])

            # positive/negative 연결 추적 (CLIPTextEncode -> text 입력 재귀 추적)
            positive_ref = inputs.get('positive')
            negative_ref = inputs.get('negative')

            if isinstance(positive_ref, list) and len(positive_ref) >= 1:
                pos_node_id = str(positive_ref[0])
                if pos_node_id in clip_encode_nodes:
                    text_input = clip_encode_nodes[pos_node_id].get('inputs', {}).get('text', '')
                    result['positive_prompt'] = self._resolve_text_value(text_input, prompt_data)

            if isinstance(negative_ref, list) and len(negative_ref) >= 1:
                neg_node_id = str(negative_ref[0])
                if neg_node_id in clip_encode_nodes:
                    text_input = clip_encode_nodes[neg_node_id].get('inputs', {}).get('text', '')
                    result['negative_prompt'] = self._resolve_text_value(text_input, prompt_data)

        # EmptyLatentImage에서 width/height 추출
        for node_id, inputs in latent_nodes.items():
            if 'width' in inputs:
                result['width'] = int(inputs['width'])
            if 'height' in inputs:
                result['height'] = int(inputs['height'])
            break

        # 프롬프트가 없으면 모든 CLIPTextEncode 노드에서 추출 시도
        if not result['positive_prompt'] and not result['negative_prompt']:
            prompts = []
            for node_id, node_data in clip_encode_nodes.items():
                text_input = node_data.get('inputs', {}).get('text', '')
                text = self._resolve_text_value(text_input, prompt_data)
                if text.strip():
                    prompts.append(text)
            if len(prompts) >= 1:
                result['positive_prompt'] = prompts[0]
            if len(prompts) >= 2:
                result['negative_prompt'] = prompts[1]

        return result

    def _resolve_text_value(self, value, prompt_data: dict, visited: set = None) -> str:
        """
        텍스트 값을 재귀적으로 추적하여 최종 문자열 반환.
        Text Concatenate, String, Text Multiline 등의 노드를 따라감.
        """
        if visited is None:
            visited = set()

        # 직접 문자열인 경우
        if isinstance(value, str):
            return value

        # 노드 연결 참조인 경우: [node_id, output_index]
        if isinstance(value, list) and len(value) >= 1:
            ref_node_id = str(value[0])

            # 순환 참조 방지
            if ref_node_id in visited:
                return ''
            visited.add(ref_node_id)

            if ref_node_id not in prompt_data:
                return ''

            ref_node = prompt_data[ref_node_id]
            class_type = ref_node.get('class_type', '')
            inputs = ref_node.get('inputs', {})

            # Text Concatenate 노드 처리 (가장 먼저 체크)
            concat_node_types = [
                'Text Concatenate', 'TextConcatenate', 'String Concatenate',
                'StringConcatenate', 'Concat Text', 'ConcatText',
                'Text Concat', 'StringConcat', 'easy string concat',
            ]

            if class_type in concat_node_types:
                parts = []
                # 다양한 입력 키 패턴 처리
                concat_keys = [
                    'text_a', 'text_b', 'text_c', 'text_d', 'text_e',  # WAS 노드 스타일
                    'text1', 'text2', 'text3', 'text4', 'text5',       # 숫자 스타일
                    'string1', 'string2', 'string3', 'string4',
                    'string_a', 'string_b', 'string_c', 'string_d',
                    'input1', 'input2', 'input3', 'input4',
                    'a', 'b', 'c', 'd', 'e',
                ]
                for key in concat_keys:
                    if key in inputs:
                        part = self._resolve_text_value(inputs[key], prompt_data, visited.copy())
                        if part.strip():
                            parts.append(part)
                # delimiter 처리
                delimiter = inputs.get('delimiter', inputs.get('separator', ', '))
                if isinstance(delimiter, list):
                    delimiter = ', '
                return delimiter.join(parts)

            # Text Multiline / 텍스트 노드 처리
            text_node_types = [
                'String', 'Text', 'Text Multiline', 'TextMultiline',
                'String Literal', 'StringLiteral', 'Text box',
                'Text Input', 'TextInput', 'easy string',
                'String (WLSH)', 'ShowText', 'Note',
            ]

            if class_type in text_node_types:
                for text_key in ['text', 'string', 'value', 'Text', 'STRING', 'content']:
                    if text_key in inputs:
                        return self._resolve_text_value(inputs[text_key], prompt_data, visited.copy())

            # SDXL CLIP 인코더 처리
            if class_type == 'CLIPTextEncodeSDXL':
                text_g = self._resolve_text_value(inputs.get('text_g', ''), prompt_data, visited.copy())
                text_l = self._resolve_text_value(inputs.get('text_l', ''), prompt_data, visited.copy())
                if text_g and text_l and text_g != text_l:
                    return f"{text_g}\n[L]: {text_l}"
                return text_g or text_l

            # 기타 노드 - 일반적인 텍스트 키로 시도
            for text_key in ['text', 'string', 'value', 'Text', 'STRING', 'content']:
                if text_key in inputs:
                    return self._resolve_text_value(inputs[text_key], prompt_data, visited.copy())

        return ''

    def on_generate_immediately(self):
        if not self.current_params:
            QMessageBox.warning(self, "오류", "생성 정보가 없습니다.")
            return

        w, h = 1024, 1024
        if 'Size' in self.current_params:
            try:
                w, h = map(int, self.current_params['Size'].split('x'))
            except Exception:
                pass

        seed = int(self.current_params.get('Seed', -1))
        if self.chk_random_seed.isChecked():
            seed = -1

        payload = {
            "prompt": self.current_params.get('prompt', ''),
            "negative_prompt": self.current_params.get('negative_prompt', ''),
            "steps": int(self.current_params.get('Steps', 20)),
            "sampler_name": self.current_params.get('Sampler', 'Euler a'),
            "cfg_scale": float(self.current_params.get('CFG scale', 7.0)),
            "seed": seed,
            "width": w,
            "height": h,
            "send_images": True,
            "save_images": True
        }

        if 'Hires upscale' in self.current_params:
            payload.update({
                "enable_hr": True,
                "hr_upscaler": self.current_params.get('Hires upscaler', 'Latent'),
                "hr_second_pass_steps": int(self.current_params.get('Hires steps', 0)),
                "denoising_strength": float(
                    self.current_params.get('Denoising strength', 0.7)
                ),
                "hr_additional_modules": [],
            })

        self.generate_signal.emit(payload)

    def on_add_to_queue(self):
        """현재 파라미터를 대기열에 추가"""
        if not self.current_params:
            QMessageBox.warning(self, "오류", "생성 정보가 없습니다.")
            return

        w, h = 1024, 1024
        if 'Size' in self.current_params:
            try:
                w, h = map(int, self.current_params['Size'].split('x'))
            except Exception:
                pass

        seed = int(self.current_params.get('Seed', -1))
        if self.chk_random_seed.isChecked():
            seed = -1

        payload = {
            "prompt": self.current_params.get('prompt', ''),
            "negative_prompt": self.current_params.get('negative_prompt', ''),
            "steps": int(self.current_params.get('Steps', 20)),
            "sampler_name": self.current_params.get('Sampler', 'Euler a'),
            "cfg_scale": float(self.current_params.get('CFG scale', 7.0)),
            "seed": seed,
            "width": w,
            "height": h,
            "send_images": True,
            "save_images": True,
        }

        if 'Hires upscale' in self.current_params:
            payload.update({
                "enable_hr": True,
                "hr_upscaler": self.current_params.get('Hires upscaler', 'Latent'),
                "hr_second_pass_steps": int(self.current_params.get('Hires steps', 0)),
                "denoising_strength": float(
                    self.current_params.get('Denoising strength', 0.7)
                ),
            })

        self.send_to_queue_signal.emit(payload)

    def on_send_to_prompt(self):
        if not self.current_params:
            return
        p = self.current_params.get('prompt', '')
        n = self.current_params.get('negative_prompt', '')
        self.send_prompt_signal.emit(p, n)
        QMessageBox.information(self, "완료", "프롬프트를 T2I로 전송했습니다. (토글 적용됨)")

    def _encode_image_base64(self, path: str) -> str:
        img = Image.open(path)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def _build_i2i_payload(self) -> dict:
        w, h = 1024, 1024
        if 'Size' in self.current_params:
            try:
                w, h = map(int, self.current_params['Size'].split('x'))
            except Exception:
                pass

        seed = int(self.current_params.get('Seed', -1))
        if self.chk_random_seed.isChecked():
            seed = -1

        encoded = self._encode_image_base64(self.current_image_path)

        return {
            "init_images": [encoded],
            "prompt": self.current_params.get('prompt', ''),
            "negative_prompt": self.current_params.get('negative_prompt', ''),
            "steps": int(self.current_params.get('Steps', 20)),
            "sampler_name": self.current_params.get('Sampler', 'Euler a'),
            "cfg_scale": float(self.current_params.get('CFG scale', 7.0)),
            "denoising_strength": float(self.current_params.get('Denoising strength', 0.75)),
            "seed": seed,
            "width": w,
            "height": h,
            "send_images": True,
            "save_images": True,
            "image_path": self.current_image_path,
        }

    def on_send_to_i2i(self):
        if not self.current_image_path:
            QMessageBox.warning(self, "오류", "먼저 이미지를 열어주세요.")
            return
        try:
            payload = self._build_i2i_payload()
            self.send_to_i2i_signal.emit(payload)
            QMessageBox.information(self, "완료", "이미지와 설정을 I2I 탭으로 전송했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"I2I 전송 실패:\n{e}")

    def on_send_to_inpaint(self):
        if not self.current_image_path:
            QMessageBox.warning(self, "오류", "먼저 이미지를 열어주세요.")
            return
        try:
            payload = self._build_i2i_payload()
            payload['inpaint_mode'] = True
            self.send_to_inpaint_signal.emit(payload)
            QMessageBox.information(self, "완료", "이미지와 설정을 Inpaint 탭으로 전송했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"Inpaint 전송 실패:\n{e}")

    # ──────────────────────────────────────────────────
    #  메타데이터 편집/저장
    # ──────────────────────────────────────────────────

    def _toggle_edit_mode(self, checked: bool):
        """편집 모드 토글"""
        self.info_text.setReadOnly(not checked)
        self.btn_save_meta.setEnabled(checked)
        if checked:
            self.info_text.setStyleSheet(
                f"font-family: 'Consolas'; font-size: 10pt; line-height: 1.4;"
                f"border: 2px solid {get_color('accent')}; background-color: {get_color('bg_secondary')};"
            )
        else:
            self.info_text.setStyleSheet(
                "font-family: 'Consolas'; font-size: 10pt; line-height: 1.4;"
            )

    def _save_metadata(self):
        """편집된 메타데이터를 PNG 파일에 저장"""
        if not self.current_image_path:
            QMessageBox.warning(self, "오류", "먼저 이미지를 열어주세요.")
            return

        path = self.current_image_path
        if not path.lower().endswith('.png'):
            QMessageBox.warning(
                self, "오류",
                "PNG 파일만 메타데이터 저장이 가능합니다.\n"
                f"현재 파일: {os.path.basename(path)}"
            )
            return

        new_text = self.info_text.toPlainText().strip()
        if not new_text:
            QMessageBox.warning(self, "오류", "메타데이터 내용이 비어있습니다.")
            return

        reply = QMessageBox.question(
            self, "확인",
            f"'{os.path.basename(path)}'의 메타데이터를 덮어쓸까요?\n"
            "원본 파일이 수정됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            img = Image.open(path)
            png_meta = PngInfo()
            png_meta.add_text("parameters", new_text)

            # 기존 다른 메타데이터 유지
            for k, v in img.info.items():
                if k != "parameters" and isinstance(v, str):
                    png_meta.add_text(k, v)

            img.save(path, pnginfo=png_meta)

            # 파싱 갱신
            self.parse_generation_info(new_text)

            self.btn_edit_meta.setChecked(False)
            QMessageBox.information(self, "완료", "메타데이터가 저장되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"메타데이터 저장 실패:\n{e}")

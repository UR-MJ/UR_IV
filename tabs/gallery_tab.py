# tabs/gallery_tab.py
import os
import hashlib
import subprocess
import threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QScrollArea, QProgressBar,
    QSizePolicy, QFrame, QMenu, QApplication, QDialog,
    QTextEdit, QSplitter
)
from PyQt6.QtGui import QPixmap, QFont, QCursor, QAction, QDrag

try:
    from sip import isdeleted as _sip_isdeleted
except ImportError:
    try:
        from PyQt6.sip import isdeleted as _sip_isdeleted
    except ImportError:
        def _sip_isdeleted(obj):
            try:
                obj.objectName()
                return False
            except RuntimeError:
                return True
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThread, QTimer, QEvent, QMimeData, QUrl, QPoint

from widgets.common_widgets import FlowLayout, NoScrollComboBox
from core.database import MetadataManager, normalize_path
from workers.gallery_worker import GalleryScanWorker, GalleryCacheWorker, IMAGE_EXTENSIONS

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


def _get_thumb_path(image_path: str, thumb_dir: str) -> str:
    """썸네일 경로 생성"""
    h = hashlib.sha1(normalize_path(image_path).encode('utf-8')).hexdigest()
    return os.path.join(thumb_dir, f"{h}.jpg")


def _parse_generation_info(text: str) -> dict:
    """PNG parameters 문자열을 파싱하여 dict 반환"""
    params = {}
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

        params['prompt'] = prompt
        params['negative_prompt'] = negative

        if params_line:
            items = params_line.split(', ')
            for item in items:
                if ':' in item:
                    k, v = item.split(':', 1)
                    params[k.strip()] = v.strip()
    except Exception:
        params['prompt'] = text.strip()
        params['negative_prompt'] = ""
    return params


# ─────────────────────────────────────────────────────────
# 이미지 미리보기 다이얼로그
# ─────────────────────────────────────────────────────────
class ImagePreviewDialog(QDialog):
    """이미지 크게 보기 + EXIF 정보 + T2I 전송"""
    send_prompt_signal = pyqtSignal(str, str)    # prompt, negative
    generate_signal = pyqtSignal(dict)           # payload
    send_to_editor_signal = pyqtSignal(str)      # image_path
    send_to_queue_signal = pyqtSignal(dict)      # payload → 대기열

    def __init__(self, image_path: str, exif_text: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.exif_text = exif_text or ""
        self.parsed_params = _parse_generation_info(self.exif_text) if self.exif_text else {}

        self.setWindowTitle(os.path.basename(image_path))
        self.setMinimumSize(1000, 700)
        self.resize(1400, 900)
        self.setStyleSheet("background-color: #1E1E1E; color: #EEE;")

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 스플리터: 좌=이미지, 우=정보
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 좌: 이미지 ──
        img_container = QWidget()
        img_layout = QVBoxLayout(img_container)
        img_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #111; border-radius: 6px;")
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        pix = QPixmap(self.image_path)
        if not pix.isNull():
            self._original_pixmap = pix

        img_layout.addWidget(self.image_label)

        # 파일 경로 표시
        path_label = QLabel(self.image_path)
        path_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        img_layout.addWidget(path_label)

        splitter.addWidget(img_container)

        # ── 우: EXIF 정보 ──
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(8)

        info_header = QLabel("생성 정보 (EXIF)")
        info_header.setStyleSheet(
            "color: #AAA; font-size: 13px; font-weight: bold; padding: 4px;"
        )
        info_layout.addWidget(info_header)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet(
            "background-color: #252525; color: #DDD; border: 1px solid #444; "
            "border-radius: 4px; font-size: 12px; padding: 8px;"
        )
        if self.exif_text:
            self.info_text.setPlainText(self.exif_text)
        else:
            self.info_text.setPlainText("생성 정보가 없습니다.")
        info_layout.addWidget(self.info_text, stretch=1)

        # ── 버튼 영역 ──
        has_prompt = bool(self.parsed_params.get('prompt', '').strip())

        btn_send = QPushButton("📝 프롬프트 전송 (T2I)")
        btn_send.setFixedHeight(38)
        btn_send.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_send.setEnabled(has_prompt)
        btn_send.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
            if has_prompt else
            "background-color: #333; color: #666; border-radius: 4px; "
            "font-size: 13px;"
        )
        btn_send.clicked.connect(self._on_send_prompt)
        info_layout.addWidget(btn_send)

        btn_gen = QPushButton("🚀 즉시 생성 (T2I)")
        btn_gen.setFixedHeight(38)
        btn_gen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_gen.setEnabled(has_prompt)
        btn_gen.setStyleSheet(
            "background-color: #43B581; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
            if has_prompt else
            "background-color: #333; color: #666; border-radius: 4px; "
            "font-size: 13px;"
        )
        btn_gen.clicked.connect(self._on_generate)
        info_layout.addWidget(btn_gen)

        btn_queue = QPushButton("📋 대기열에 추가")
        btn_queue.setFixedHeight(38)
        btn_queue.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_queue.setEnabled(has_prompt)
        btn_queue.setStyleSheet(
            "background-color: #E67E22; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
            if has_prompt else
            "background-color: #333; color: #666; border-radius: 4px; "
            "font-size: 13px;"
        )
        btn_queue.clicked.connect(self._on_send_to_queue)
        info_layout.addWidget(btn_queue)

        btn_editor = QPushButton("🎨 에디터로 보내기")
        btn_editor.setFixedHeight(38)
        btn_editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_editor.setStyleSheet(
            "background-color: #8A5CF5; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        btn_editor.clicked.connect(self._on_send_to_editor)
        info_layout.addWidget(btn_editor)

        btn_close = QPushButton("닫기")
        btn_close.setFixedHeight(35)
        btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_close.setStyleSheet(
            "background-color: #333; color: #AAA; border-radius: 4px; font-size: 13px;"
        )
        btn_close.clicked.connect(self.close)
        info_layout.addWidget(btn_close)

        splitter.addWidget(info_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def _on_send_prompt(self):
        """프롬프트만 T2I로 전송"""
        p = self.parsed_params.get('prompt', '')
        n = self.parsed_params.get('negative_prompt', '')
        self.send_prompt_signal.emit(p, n)
        self.close()

    def _on_send_to_editor(self):
        """에디터 탭으로 이미지 전송"""
        self.send_to_editor_signal.emit(self.image_path)
        self.close()

    def _on_generate(self):
        """즉시 생성 요청"""
        p = self.parsed_params
        w, h = 1024, 1024
        if 'Size' in p:
            try:
                w, h = map(int, p['Size'].split('x'))
            except Exception:
                pass

        payload = {
            "prompt": p.get('prompt', ''),
            "negative_prompt": p.get('negative_prompt', ''),
            "steps": int(p.get('Steps', 20)),
            "sampler_name": p.get('Sampler', 'Euler a'),
            "cfg_scale": float(p.get('CFG scale', 7.0)),
            "seed": -1,
            "width": w,
            "height": h,
            "send_images": True,
            "save_images": True,
        }

        if 'Hires upscale' in p:
            payload.update({
                "enable_hr": True,
                "hr_upscaler": p.get('Hires upscaler', 'Latent'),
                "hr_second_pass_steps": int(p.get('Hires steps', 0)),
                "denoising_strength": float(p.get('Denoising strength', 0.7)),
            })

        self.generate_signal.emit(payload)
        self.close()

    def _on_send_to_queue(self):
        """대기열에 추가"""
        p = self.parsed_params
        w, h = 1024, 1024
        if 'Size' in p:
            try:
                w, h = map(int, p['Size'].split('x'))
            except Exception:
                pass

        payload = {
            "prompt": p.get('prompt', ''),
            "negative_prompt": p.get('negative_prompt', ''),
            "steps": int(p.get('Steps', 20)),
            "sampler_name": p.get('Sampler', 'Euler a'),
            "cfg_scale": float(p.get('CFG scale', 7.0)),
            "seed": -1,
            "width": w,
            "height": h,
            "send_images": True,
            "save_images": True,
        }

        if 'Hires upscale' in p:
            payload.update({
                "enable_hr": True,
                "hr_upscaler": p.get('Hires upscaler', 'Latent'),
                "hr_second_pass_steps": int(p.get('Hires steps', 0)),
                "denoising_strength": float(p.get('Denoising strength', 0.7)),
            })

        self.send_to_queue_signal.emit(payload)
        self.close()

    def _fit_image(self):
        """이미지를 라벨 크기에 맞게 스케일링"""
        if hasattr(self, '_original_pixmap') and not self._original_pixmap.isNull():
            self.image_label.setPixmap(self._original_pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

    def showEvent(self, event):
        super().showEvent(event)
        # 레이아웃 완료 후 이미지 맞춤
        QTimer.singleShot(0, self._fit_image)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_image()


# ─────────────────────────────────────────────────────────
# 썸네일 위젯
# ─────────────────────────────────────────────────────────
class ThumbnailWidget(QFrame):
    """개별 썸네일 위젯"""
    clicked = pyqtSignal(str)  # image_path
    double_clicked = pyqtSignal(str)
    context_action = pyqtSignal(str, str)  # action_name, image_path

    THUMB_SIZE = 180
    LABEL_H = 22
    MARGIN = 4
    SPACING = 2

    def __init__(self, image_path: str, thumb_dir: str, thumb_size: int = 0, parent=None):
        super().__init__(parent)
        self.image_path = image_path

        ts = thumb_size if thumb_size > 0 else self.THUMB_SIZE
        total_h = self.MARGIN * 2 + ts + self.SPACING + self.LABEL_H
        self.setFixedSize(ts + self.MARGIN * 2, total_h)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            ThumbnailWidget {
                background-color: #2C2C2C; border: 2px solid transparent;
                border-radius: 6px;
            }
            ThumbnailWidget:hover {
                border: 2px solid #5865F2;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
        layout.setSpacing(self.SPACING)

        # 썸네일 이미지
        self.image_label = QLabel()
        self.image_label.setFixedSize(ts, ts)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1E1E1E; border-radius: 4px;")

        thumb_path = _get_thumb_path(image_path, thumb_dir)
        pix = None
        if os.path.exists(thumb_path):
            pix = QPixmap(thumb_path)
        if pix is None or pix.isNull():
            pix = QPixmap(image_path)
        if pix and not pix.isNull():
            self.image_label.setPixmap(pix.scaled(
                ts, ts,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        layout.addWidget(self.image_label)

        # 파일명
        fname = os.path.basename(image_path)
        name_label = QLabel(fname)
        name_label.setFixedHeight(self.LABEL_H)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(
            "color: #AAA; font-size: 10px; background: transparent;"
        )
        name_label.setToolTip(image_path)
        layout.addWidget(name_label)

    def mousePressEvent(self, event):
        if _sip_isdeleted(self):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.clicked.emit(self.image_path)

    def mouseMoveEvent(self, event):
        if _sip_isdeleted(self):
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, '_drag_start_pos'):
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self.image_path)])
        drag.setMimeData(mime)

        pix = self.image_label.pixmap()
        if pix and not pix.isNull():
            drag.setPixmap(pix.scaled(64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            drag.setHotSpot(QPoint(32, 32))

        drag.exec(Qt.DropAction.CopyAction)

    def mouseDoubleClickEvent(self, event):
        if _sip_isdeleted(self):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.image_path)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2C2C2C; color: #EEE; border: 1px solid #555;
                font-size: 13px; padding: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #5865F2; }
            QMenu::separator { height: 1px; background: #555; margin: 4px 8px; }
        """)

        act_open_explorer = menu.addAction("📂 탐색기에서 열기")
        act_copy_path = menu.addAction("📋 경로 복사")
        act_copy_image = menu.addAction("🖼️ 이미지 복사")
        menu.addSeparator()
        act_compare = menu.addAction("🔍 비교하기")
        act_favorite = menu.addAction("⭐ 즐겨찾기 토글")
        act_queue = menu.addAction("📋 대기열에 추가")
        menu.addSeparator()

        # 탭 이동 서브메뉴
        send_menu = menu.addMenu("📤 다른 탭으로 보내기")
        send_menu.setStyleSheet(menu.styleSheet())
        act_to_editor = send_menu.addAction("🎨 에디터")
        act_to_i2i = send_menu.addAction("🖼️ I2I")
        act_to_inpaint = send_menu.addAction("🎨 Inpaint")
        act_to_upscale = send_menu.addAction("🔍 Upscale")

        menu.addSeparator()
        act_delete = menu.addAction("🗑️ 삭제")

        action = menu.exec(event.globalPos())
        if not action:
            return
        if action == act_open_explorer:
            self._open_in_explorer()
        elif action == act_copy_path:
            QApplication.clipboard().setText(os.path.normpath(self.image_path))
        elif action == act_copy_image:
            pix = QPixmap(self.image_path)
            if not pix.isNull():
                QApplication.clipboard().setPixmap(pix)
        elif action == act_compare:
            self.context_action.emit("compare", self.image_path)
        elif action == act_favorite:
            self.context_action.emit("favorite", self.image_path)
        elif action == act_queue:
            self.context_action.emit("send_queue", self.image_path)
        elif action == act_to_editor:
            self.context_action.emit("send_editor", self.image_path)
        elif action == act_to_i2i:
            self.context_action.emit("send_i2i", self.image_path)
        elif action == act_to_inpaint:
            self.context_action.emit("send_inpaint", self.image_path)
        elif action == act_to_upscale:
            self.context_action.emit("send_upscale", self.image_path)
        elif action == act_delete:
            self.context_action.emit("delete", self.image_path)

    def _open_in_explorer(self):
        norm = os.path.normpath(self.image_path)
        if os.path.exists(norm):
            subprocess.Popen(['explorer', '/select,', norm])

    def sizeHint(self):
        w = self.width()
        h = self.height()
        return QSize(w, h)


# ─────────────────────────────────────────────────────────
# 갤러리 탭
# ─────────────────────────────────────────────────────────
class GalleryTab(QWidget):
    """태그/키워드 기반 이미지 갤러리 탭"""
    image_selected = pyqtSignal(str)
    open_in_editor = pyqtSignal(str)
    send_to_i2i = pyqtSignal(str)               # → I2I 탭
    send_to_inpaint = pyqtSignal(str)            # → Inpaint 탭
    send_to_upscale = pyqtSignal(str)            # → Upscale 탭
    send_prompt_signal = pyqtSignal(str, str)    # → T2I 프롬프트 전송
    generate_signal = pyqtSignal(dict)           # → T2I 즉시 생성
    send_to_queue_signal = pyqtSignal(dict)     # → 대기열에 추가
    send_to_compare = pyqtSignal(str, str)      # → PNG Info 비교 (path_a, path_b)

    COLS = 10
    ROWS = 4
    IMAGES_PER_PAGE = COLS * ROWS

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_folder = ""
        self._all_paths: list[str] = []
        self._filtered_paths: list[str] = []
        self._current_page = 0
        self._total_pages = 0
        self._thumb_widgets: list[ThumbnailWidget] = []
        self._compare_first_path: str | None = None

        from config import DB_FILE, THUMB_DIR
        self._thumb_dir = THUMB_DIR
        self._db = MetadataManager(DB_FILE)

        self._scan_worker: GalleryScanWorker | None = None
        self._cache_worker: GalleryCacheWorker | None = None

        # 파일 시스템 감시
        self._watcher_observer = None
        self._pending_lock = threading.Lock()
        self._pending_add: list[str] = []
        self._pending_del: list[str] = []
        self._watcher_timer = QTimer(self)
        self._watcher_timer.setInterval(500)
        self._watcher_timer.timeout.connect(self._flush_watcher_events)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── 상단: 폴더 선택 ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_folder = QPushButton("📁 폴더 선택")
        self.btn_folder.setFixedHeight(35)
        self.btn_folder.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_folder.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold; padding: 0 12px;"
        )
        self.btn_folder.clicked.connect(self._on_select_folder)
        top_bar.addWidget(self.btn_folder)

        self.label_folder = QLabel("폴더를 선택하세요")
        self.label_folder.setStyleSheet("color: #888; font-size: 12px;")
        self.label_folder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_bar.addWidget(self.label_folder)

        self.btn_stats = QPushButton("📊 통계")
        self.btn_stats.setFixedHeight(35)
        self.btn_stats.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stats.setStyleSheet(
            "background-color: #8A5CF5; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold; padding: 0 12px;"
        )
        self.btn_stats.clicked.connect(self._on_open_stats)
        top_bar.addWidget(self.btn_stats)

        self.btn_organize = QPushButton("🗂️ 폴더 정리")
        self.btn_organize.setFixedHeight(35)
        self.btn_organize.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_organize.setStyleSheet(
            "background-color: #E67E22; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold; padding: 0 12px;"
        )
        self.btn_organize.clicked.connect(self._on_open_organizer)
        top_bar.addWidget(self.btn_organize)

        layout.addLayout(top_bar)

        # ── 검색 바 ──
        search_bar = QHBoxLayout()
        search_bar.setSpacing(6)

        search_icon = QLabel("🔍")
        search_icon.setFixedWidth(24)
        search_bar.addWidget(search_icon)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("검색 (파일명 + EXIF, 공백으로 AND 검색)...")
        self.search_input.setFixedHeight(35)
        self.search_input.setStyleSheet(
            "background-color: #2C2C2C; color: #EEE; border: 1px solid #555; "
            "border-radius: 4px; padding: 0 8px; font-size: 13px;"
        )
        self.search_input.returnPressed.connect(self._on_search)
        search_bar.addWidget(self.search_input)

        self.btn_search = QPushButton("검색")
        self.btn_search.setFixedSize(70, 35)
        self.btn_search.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_search.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        self.btn_search.clicked.connect(self._on_search)
        search_bar.addWidget(self.btn_search)

        self.btn_reset = QPushButton("초기화")
        self.btn_reset.setFixedSize(70, 35)
        self.btn_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_reset.setStyleSheet(
            "background-color: #333; color: #AAA; border-radius: 4px; font-size: 13px;"
        )
        self.btn_reset.clicked.connect(self._on_reset_search)
        search_bar.addWidget(self.btn_reset)

        layout.addLayout(search_bar)

        # ── 태그 필터 바 ──
        self.filter_bar = QWidget()
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)

        filter_layout.addWidget(QLabel("필터:"))

        self.filter_character_combo = NoScrollComboBox()
        self.filter_character_combo.addItem("캐릭터 (전체)")
        self.filter_character_combo.setMinimumWidth(140)
        filter_layout.addWidget(self.filter_character_combo)

        self.filter_copyright_combo = NoScrollComboBox()
        self.filter_copyright_combo.addItem("작품 (전체)")
        self.filter_copyright_combo.setMinimumWidth(140)
        filter_layout.addWidget(self.filter_copyright_combo)

        self.filter_artist_combo = NoScrollComboBox()
        self.filter_artist_combo.addItem("작가 (전체)")
        self.filter_artist_combo.setMinimumWidth(140)
        filter_layout.addWidget(self.filter_artist_combo)

        self.btn_apply_filter = QPushButton("적용")
        self.btn_apply_filter.setFixedSize(60, 30)
        self.btn_apply_filter.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 12px; font-weight: bold;"
        )
        self.btn_apply_filter.clicked.connect(self._on_apply_tag_filter)
        filter_layout.addWidget(self.btn_apply_filter)

        self.btn_reset_filter = QPushButton("초기화")
        self.btn_reset_filter.setFixedSize(60, 30)
        self.btn_reset_filter.setStyleSheet(
            "background-color: #333; color: #AAA; border-radius: 4px; font-size: 12px;"
        )
        self.btn_reset_filter.clicked.connect(self._on_reset_tag_filter)
        filter_layout.addWidget(self.btn_reset_filter)

        filter_layout.addStretch()
        layout.addWidget(self.filter_bar)

        # ── 진행률 바 ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2C2C2C; border: 1px solid #555;
                border-radius: 4px; text-align: center; color: #AAA; font-size: 11px;
            }
            QProgressBar::chunk { background-color: #5865F2; border-radius: 3px; }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # ── 썸네일 그리드 ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background-color: #1E1E1E; border: 1px solid #333; border-radius: 4px; }
        """)

        self.grid_container = QWidget()
        self.flow_layout = FlowLayout(self.grid_container)
        self.flow_layout.setSpacing(8)
        self.scroll_area.setWidget(self.grid_container)

        # 스크롤 영역 휠 이벤트를 가로채서 페이지 전환으로 처리
        self.scroll_area.installEventFilter(self)
        self.grid_container.installEventFilter(self)

        layout.addWidget(self.scroll_area, stretch=1)

        # ── 하단: 페이지네이션 ──
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self.btn_prev = QPushButton("◀ 이전")
        self.btn_prev.setFixedSize(80, 35)
        self.btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_prev.setStyleSheet(
            "background-color: #333; color: #DDD; border-radius: 4px; font-size: 13px;"
        )
        self.btn_prev.clicked.connect(self._on_prev_page)
        bottom_bar.addWidget(self.btn_prev)

        bottom_bar.addStretch()

        self.label_page = QLabel("페이지 0/0 (총 0개)")
        self.label_page.setStyleSheet("color: #AAA; font-size: 13px;")
        self.label_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom_bar.addWidget(self.label_page)

        bottom_bar.addStretch()

        self.btn_next = QPushButton("다음 ▶")
        self.btn_next.setFixedSize(80, 35)
        self.btn_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_next.setStyleSheet(
            "background-color: #333; color: #DDD; border-radius: 4px; font-size: 13px;"
        )
        self.btn_next.clicked.connect(self._on_next_page)
        bottom_bar.addWidget(self.btn_next)

        layout.addLayout(bottom_bar)

    # ── 폴더 선택 / 로드 ──
    def load_folder(self, folder: str):
        """외부에서 폴더 경로를 지정하여 로드 (설정 복원용)"""
        if not folder or not os.path.isdir(folder):
            return
        self._current_folder = folder
        self.label_folder.setText(folder)
        self.label_folder.setStyleSheet("color: #DDD; font-size: 12px;")
        self._start_scan(folder)

    def _on_select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "갤러리 폴더 선택")
        if not folder:
            return
        self._current_folder = folder
        self.label_folder.setText(folder)
        self.label_folder.setStyleSheet("color: #DDD; font-size: 12px;")
        self._start_scan(folder)

    def _start_scan(self, folder: str):
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.request_stop()
            self._scan_worker.wait(2000)
        if self._cache_worker and self._cache_worker.isRunning():
            self._cache_worker.request_stop()
            self._cache_worker.wait(2000)

        self._stop_watcher()
        self._all_paths.clear()
        self._filtered_paths.clear()
        self._current_page = 0
        self._clear_grid()

        self.progress_bar.show()
        self.progress_bar.setFormat("폴더 스캔 중...")
        self.progress_bar.setRange(0, 0)

        self._scan_worker = GalleryScanWorker(folder)
        self._scan_worker.paths_found.connect(self._on_paths_found)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_paths_found(self, paths: list):
        self._all_paths.extend(paths)
        self.progress_bar.setFormat(f"스캔 중... {len(self._all_paths)}개 발견")

    def _on_scan_finished(self):
        self._filtered_paths = list(self._all_paths)
        self._update_pagination()
        self._display_current_page()

        if self._all_paths:
            self.progress_bar.setRange(0, len(self._all_paths))
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("캐싱 중... 0/%v")

            self._cache_worker = GalleryCacheWorker(
                list(self._all_paths), self._db, self._thumb_dir
            )
            self._cache_worker.progress.connect(self._on_cache_progress)
            self._cache_worker.finished.connect(self._on_cache_finished)
            self._cache_worker.start()
        else:
            self.progress_bar.hide()

    def _on_cache_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"캐싱 중... {current}/{total}")

    def _on_cache_finished(self):
        self.progress_bar.hide()
        self._display_current_page()
        # 캐싱 완료 후 파일 감시 시작
        self._start_watcher(self._current_folder)
        # 태그 필터 콤보 채우기
        self._populate_filter_combos()

    # ── 태그 필터 ──
    def _populate_filter_combos(self):
        """캐싱 완료 후 EXIF에서 태그를 추출하여 필터 콤보 채우기"""
        characters = set()
        copyrights = set()
        artists = set()

        try:
            from core.tag_classifier import TagClassifier
            classifier = TagClassifier()
        except Exception:
            classifier = None

        norm_folder = normalize_path(self._current_folder)

        for path in self._all_paths:
            norm = normalize_path(path)
            data = self._db.get_image_data(norm)
            if not data or not data[0]:
                continue
            exif_text = data[0]
            params = _parse_generation_info(exif_text)
            prompt = params.get('prompt', '')
            if not prompt:
                continue

            tags = [t.strip() for t in prompt.split(',') if t.strip()]
            if classifier:
                for tag in tags:
                    cat = classifier.classify_tag(tag)
                    if cat == 'character':
                        characters.add(tag)
                    elif cat == 'copyright':
                        copyrights.add(tag)
                    elif cat == 'artist':
                        artists.add(tag)

        # 콤보 갱신
        self.filter_character_combo.clear()
        self.filter_character_combo.addItem("캐릭터 (전체)")
        for c in sorted(characters):
            self.filter_character_combo.addItem(c)

        self.filter_copyright_combo.clear()
        self.filter_copyright_combo.addItem("작품 (전체)")
        for c in sorted(copyrights):
            self.filter_copyright_combo.addItem(c)

        self.filter_artist_combo.clear()
        self.filter_artist_combo.addItem("작가 (전체)")
        for a in sorted(artists):
            self.filter_artist_combo.addItem(a)

    def _on_apply_tag_filter(self):
        """태그 필터 적용"""
        char_filter = self.filter_character_combo.currentText()
        copy_filter = self.filter_copyright_combo.currentText()
        artist_filter = self.filter_artist_combo.currentText()

        # "전체" 선택이면 필터 없음
        has_filter = False
        if char_filter != "캐릭터 (전체)":
            has_filter = True
        if copy_filter != "작품 (전체)":
            has_filter = True
        if artist_filter != "작가 (전체)":
            has_filter = True

        if not has_filter:
            self._filtered_paths = list(self._all_paths)
        else:
            matched = []
            for path in self._all_paths:
                norm = normalize_path(path)
                data = self._db.get_image_data(norm)
                if not data or not data[0]:
                    continue
                exif_text = data[0]
                params = _parse_generation_info(exif_text)
                prompt = params.get('prompt', '').lower()

                ok = True
                if char_filter != "캐릭터 (전체)" and char_filter.lower() not in prompt:
                    ok = False
                if copy_filter != "작품 (전체)" and copy_filter.lower() not in prompt:
                    ok = False
                if artist_filter != "작가 (전체)" and artist_filter.lower() not in prompt:
                    ok = False

                if ok:
                    matched.append(path)
            self._filtered_paths = matched

        self._current_page = 0
        self._update_pagination()
        self._display_current_page()

    def _on_reset_tag_filter(self):
        """태그 필터 초기화"""
        self.filter_character_combo.setCurrentIndex(0)
        self.filter_copyright_combo.setCurrentIndex(0)
        self.filter_artist_combo.setCurrentIndex(0)
        self._filtered_paths = list(self._all_paths)
        self._current_page = 0
        self._update_pagination()
        self._display_current_page()

    # ── 파일 시스템 감시 (watchdog) ──
    def _start_watcher(self, folder: str):
        """폴더 변경 감시 시작"""
        self._stop_watcher()
        if not HAS_WATCHDOG or not folder:
            return
        try:
            handler = _GalleryFSHandler(self)
            self._watcher_observer = Observer()
            self._watcher_observer.schedule(handler, folder, recursive=True)
            self._watcher_observer.daemon = True
            self._watcher_observer.start()
            self._watcher_timer.start()
        except Exception as e:
            print(f"[Gallery] 파일 감시 시작 실패: {e}")

    def _stop_watcher(self):
        """파일 감시 중지"""
        self._watcher_timer.stop()
        if self._watcher_observer and self._watcher_observer.is_alive():
            self._watcher_observer.stop()
            self._watcher_observer.join(timeout=2)
        self._watcher_observer = None
        with self._pending_lock:
            self._pending_add.clear()
            self._pending_del.clear()

    def _flush_watcher_events(self):
        """타이머로 모은 파일 이벤트를 한꺼번에 반영"""
        changed = False

        with self._pending_lock:
            del_snapshot = list(self._pending_del)
            self._pending_del.clear()
            add_snapshot = list(self._pending_add)
            self._pending_add.clear()

        # 삭제된 파일 제거
        if del_snapshot:
            del_set = set(del_snapshot)
            before = len(self._all_paths)
            self._all_paths = [p for p in self._all_paths if p not in del_set]
            self._filtered_paths = [p for p in self._filtered_paths if p not in del_set]
            if len(self._all_paths) != before:
                changed = True

        # 추가된 파일 반영
        if add_snapshot:
            new_paths = add_snapshot
            existing = set(self._all_paths)
            added = [p for p in new_paths if p not in existing]
            if added:
                self._all_paths.extend(added)
                self._filtered_paths.extend(added)
                changed = True

        if changed:
            self._update_pagination()
            self._display_current_page()

    # ── 검색 (파일명 + EXIF) ──
    def _on_search(self):
        text = self.search_input.text().strip()
        if not text or not self._current_folder:
            return
        keywords = text.split()
        norm_folder = normalize_path(self._current_folder)

        # 1) EXIF 검색 (DB)
        exif_results = set(self._db.search_exif(keywords, norm_folder))

        # 2) 파일명 검색 (메모리)
        name_results = set()
        for p in self._all_paths:
            fname = os.path.basename(p).lower()
            if all(kw.lower() in fname for kw in keywords):
                name_results.add(p)

        # 합집합 (EXIF 결과는 normalized path, 파일명 결과는 원본 path)
        # EXIF 결과를 원본 path로 매핑
        norm_to_orig = {normalize_path(p): p for p in self._all_paths}
        combined = set()
        for np_ in exif_results:
            if np_ in norm_to_orig:
                combined.add(norm_to_orig[np_])
        combined |= name_results

        # 원래 순서 유지
        self._filtered_paths = [p for p in self._all_paths if p in combined]
        self._current_page = 0
        self._update_pagination()
        self._display_current_page()

    def _on_reset_search(self):
        self.search_input.clear()
        self._filtered_paths = list(self._all_paths)
        self._current_page = 0
        self._update_pagination()
        self._display_current_page()

    # ── 페이지 크기 / 썸네일 크기 계산 ──
    def _calc_items_per_page(self) -> int:
        """고정 10열 × 4행 = 40"""
        return self.COLS * self.ROWS

    def _calc_thumb_size(self) -> int:
        """뷰포트 너비에 맞춰 10개가 들어가는 썸네일 크기 계산"""
        vp = self.scroll_area.viewport().size()
        if vp.width() < 50:
            return 120
        spacing = self.flow_layout.spacing()
        margin = ThumbnailWidget.MARGIN
        available = vp.width() - spacing * (self.COLS - 1)
        ts = max(60, available // self.COLS - margin * 2)
        return ts

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._filtered_paths:
            self._display_current_page()

    # ── 페이지네이션 ──
    def _update_pagination(self):
        total = len(self._filtered_paths)
        self._total_pages = max(1, (total + self.IMAGES_PER_PAGE - 1) // self.IMAGES_PER_PAGE)
        if self._current_page >= self._total_pages:
            self._current_page = self._total_pages - 1
        self._update_page_label()

    def _update_page_label(self):
        total = len(self._filtered_paths)
        self.label_page.setText(
            f"페이지 {self._current_page + 1}/{self._total_pages} (총 {total}개)"
        )
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._total_pages - 1)

    def _on_prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._update_page_label()
            self._display_current_page()

    def _on_next_page(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._update_page_label()
            self._display_current_page()

    def wheelEvent(self, event):
        """마우스 휠로 페이지 전환 (스크롤 대신)"""
        delta = event.angleDelta().y()
        if delta < 0:
            self._on_next_page()
        elif delta > 0:
            self._on_prev_page()
        event.accept()

    def eventFilter(self, obj, event):
        """스크롤 영역/그리드 컨테이너의 휠 이벤트를 가로채서 페이지 전환"""
        if event.type() == QEvent.Type.Wheel and obj in (self.scroll_area, self.grid_container):
            delta = event.angleDelta().y()
            if delta < 0:
                self._on_next_page()
            elif delta > 0:
                self._on_prev_page()
            return True  # 이벤트 소비 (스크롤 방지)
        return super().eventFilter(obj, event)

    # ── 그리드 표시 ──
    def _clear_grid(self):
        for w in self._thumb_widgets:
            w.setParent(None)
            w.deleteLater()
        self._thumb_widgets.clear()

    def _display_current_page(self):
        self._clear_grid()

        start = self._current_page * self.IMAGES_PER_PAGE
        end = min(start + self.IMAGES_PER_PAGE, len(self._filtered_paths))
        page_paths = self._filtered_paths[start:end]

        ts = self._calc_thumb_size()
        for path in page_paths:
            tw = ThumbnailWidget(path, self._thumb_dir, thumb_size=ts)
            tw.clicked.connect(self._on_thumb_clicked)
            tw.double_clicked.connect(self._on_thumb_double_clicked)
            tw.context_action.connect(self._on_context_action)
            self.flow_layout.addWidget(tw)
            self._thumb_widgets.append(tw)

        self.grid_container.adjustSize()
        self._update_page_label()

    # ── 썸네일 클릭 → 미리보기 다이얼로그 ──
    def _on_thumb_clicked(self, path: str):
        """썸네일 클릭 → 이미지 미리보기 + EXIF + T2I 전송"""
        norm = normalize_path(path)
        exif_text = ""
        data = self._db.get_image_data(norm)
        if data and data[0]:
            exif_text = data[0]

        dlg = ImagePreviewDialog(path, exif_text, self)
        dlg.send_prompt_signal.connect(
            lambda p, n: self.send_prompt_signal.emit(p, n)
        )
        dlg.generate_signal.connect(
            lambda payload: self.generate_signal.emit(payload)
        )
        dlg.send_to_editor_signal.connect(
            lambda p: self.open_in_editor.emit(p)
        )
        dlg.send_to_queue_signal.connect(
            lambda payload: self.send_to_queue_signal.emit(payload)
        )
        dlg.exec()

    def _on_thumb_double_clicked(self, path: str):
        """썸네일 더블클릭 → 탐색기에서 열기"""
        norm = os.path.normpath(path)
        if os.path.exists(norm):
            subprocess.Popen(['explorer', '/select,', norm])

    def _on_context_action(self, action: str, path: str):
        if action == "send_editor":
            self.open_in_editor.emit(path)
        elif action == "send_i2i":
            self.send_to_i2i.emit(path)
        elif action == "send_inpaint":
            self.send_to_inpaint.emit(path)
        elif action == "send_upscale":
            self.send_to_upscale.emit(path)
        elif action == "send_queue":
            self._send_to_queue(path)
        elif action == "favorite":
            self._toggle_favorite(path)
        elif action == "delete":
            self._delete_image(path)
        elif action == "compare":
            self._handle_compare(path)

    def _handle_compare(self, path: str):
        """비교하기: 첫 번째 선택 시 저장, 두 번째 선택 시 비교 시그널 발사"""
        if self._compare_first_path is None:
            self._compare_first_path = path
            # 상태 표시 (부모가 show_status를 가지면 사용)
            parent = self.parent()
            while parent:
                if hasattr(parent, 'show_status'):
                    parent.show_status(
                        f"🔍 비교 A 선택: {os.path.basename(path)} — 두 번째 이미지를 우클릭하세요"
                    )
                    break
                parent = parent.parent() if hasattr(parent, 'parent') else None
        else:
            first = self._compare_first_path
            self._compare_first_path = None
            self.send_to_compare.emit(first, path)

    def _send_to_queue(self, path: str):
        """이미지 EXIF 정보로 대기열에 추가"""
        norm = normalize_path(path)
        exif_text = ""
        data = self._db.get_image_data(norm)
        if data and data[0]:
            exif_text = data[0]

        if not exif_text:
            # EXIF 없으면 PIL로 시도
            try:
                from PIL import Image
                img = Image.open(path)
                if 'parameters' in img.info:
                    exif_text = img.info['parameters']
            except Exception:
                pass

        if not exif_text:
            return

        params = _parse_generation_info(exif_text)
        if not params.get('prompt', '').strip():
            return

        w, h = 1024, 1024
        if 'Size' in params:
            try:
                w, h = map(int, params['Size'].split('x'))
            except Exception:
                pass

        payload = {
            "prompt": params.get('prompt', ''),
            "negative_prompt": params.get('negative_prompt', ''),
            "steps": int(params.get('Steps', 20)),
            "sampler_name": params.get('Sampler', 'Euler a'),
            "cfg_scale": float(params.get('CFG scale', 7.0)),
            "seed": -1,
            "width": w,
            "height": h,
            "send_images": True,
            "save_images": True,
        }

        if 'Hires upscale' in params:
            payload.update({
                "enable_hr": True,
                "hr_upscaler": params.get('Hires upscaler', 'Latent'),
                "hr_second_pass_steps": int(params.get('Hires steps', 0)),
                "denoising_strength": float(params.get('Denoising strength', 0.7)),
            })

        self.send_to_queue_signal.emit(payload)

    def _on_open_stats(self):
        """통계 대시보드 열기"""
        if not self._current_folder:
            return
        from widgets.stats_panel import StatsPanel
        dlg = StatsPanel(self._db, self._current_folder, self)
        dlg.exec()

    def _on_open_organizer(self):
        """폴더 정리 도구 열기"""
        if not self._current_folder:
            return
        from widgets.folder_organizer import FolderOrganizerDialog
        dlg = FolderOrganizerDialog(self._db, self._current_folder, self)
        dlg.exec()
        # 정리 후 갤러리 새로고침
        self._start_scan(self._current_folder)

    def _toggle_favorite(self, path: str):
        """즐겨찾기 토글 (JSON 파일 기반)"""
        import json
        from config import FAVORITES_FILE

        favorites = []
        try:
            if os.path.exists(FAVORITES_FILE):
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    favorites = json.load(f)
        except Exception:
            favorites = []

        norm = os.path.normpath(path)
        if norm in favorites:
            favorites.remove(norm)
        else:
            favorites.append(norm)

        try:
            with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
                json.dump(favorites, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Gallery] 즐겨찾기 저장 실패: {e}")

    def _delete_image(self, path: str):
        try:
            from core.image_utils import move_to_trash
            move_to_trash(path)
        except Exception:
            try:
                os.remove(path)
            except Exception:
                return

        norm = os.path.normpath(path)
        self._all_paths = [p for p in self._all_paths if os.path.normpath(p) != norm]
        self._filtered_paths = [p for p in self._filtered_paths if os.path.normpath(p) != norm]
        self._update_pagination()
        self._display_current_page()


# ─────────────────────────────────────────────────────────
# 파일 시스템 이벤트 핸들러 (watchdog)
# ─────────────────────────────────────────────────────────
if HAS_WATCHDOG:
    class _GalleryFSHandler(FileSystemEventHandler):
        """Gallery 폴더 변경 감지 핸들러"""

        def __init__(self, gallery_tab: GalleryTab):
            super().__init__()
            self._tab = gallery_tab

        def on_created(self, event):
            if event.is_directory:
                return
            if event.src_path.lower().endswith(IMAGE_EXTENSIONS):
                with self._tab._pending_lock:
                    self._tab._pending_add.append(event.src_path)

        def on_deleted(self, event):
            if event.is_directory:
                return
            with self._tab._pending_lock:
                self._tab._pending_del.append(event.src_path)

        def on_moved(self, event):
            if event.is_directory:
                return
            with self._tab._pending_lock:
                self._tab._pending_del.append(event.src_path)
                if event.dest_path.lower().endswith(IMAGE_EXTENSIONS):
                    self._tab._pending_add.append(event.dest_path)

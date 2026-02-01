import sys, os, json, shutil, hashlib, sqlite3, re, subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QSplitter, QSizePolicy, QMessageBox, QCheckBox, QLineEdit, QInputDialog, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTreeWidget, QTreeWidgetItem, QProgressBar, QMenu,
    QTreeWidgetItemIterator
)
from PyQt5.QtGui import QPixmap, QFont, QBrush, QColor, QIcon, QCursor
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer, QEvent

from PIL import Image, PngImagePlugin
import exifread

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ----- 설정 경로/파일 -----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'photodata.sqlite') # 모든 메타데이터를 저장할 DB 파일
CACHE_DIR = os.path.join(BASE_DIR, 'image_cache')
THUMB_DIR = os.path.join(CACHE_DIR, 'thumbs')
os.makedirs(THUMB_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(BASE_DIR, 'settings.json') # UI 설정 등은 유지

def normalize_path(path):
    return Path(path).resolve().as_posix()
    
def normalize_windows_path(path):
    # '\\\\?\\' 또는 '//?/' 등 prefix 제거
    if path.startswith('\\\\?\\') or path.startswith('//?/'):
        # ex) '\\\\?\\C:\\Users\\...' → 'C:\\Users\\...'
        path = re.sub(r'^\\\\\?\\', '', path)
        path = re.sub(r'^//\?/', '', path)
    return os.path.normpath(path)    

def get_thumb_path(image_path):
    h = hashlib.sha1(normalize_path(image_path).encode('utf-8')).hexdigest()
    return os.path.join(THUMB_DIR, f"{h}.jpg")

def move_to_trash(path):
    try:
        from send2trash import send2trash
        # long path prefix 제거
        path = normalize_windows_path(path)
        if os.path.exists(path):
            send2trash(path)
        else:
            print(f"휴지통 이동 실패: 파일이 존재하지 않음 {path}")
    except ImportError:
        try:
            path = normalize_windows_path(path)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"파일 삭제 실패: {e}")

def exif_for_display(exif_raw):
    if not exif_raw: return ""
    lines = exif_raw.splitlines()
    out = []
    for line in lines:
        lstrip = line.lstrip()
        if lstrip.lower().startswith("parameters:"):
            line = lstrip[len("parameters:"):].lstrip()
            if line: out.append(line)
            continue
        if lstrip.startswith("Negative prompt:"):
            if out and out[-1] != "":
                out.append("")
            out.append(line)
            continue
        if lstrip.startswith("Steps:"):
            if out and out[-1] != "":
                out.append("")
            key, val = line.split(":", 1)
            parts = [p.strip() for p in val.split(",") if p.strip()]
            out.append(f"Steps: {parts[0]}")
            for p in parts[1:]:
                out.append(p)
            continue
        out.append(line)
    return "\n".join(out)

def read_exif(path):
    ext = os.path.splitext(path)[-1].lower()
    try:
        if ext == ".png":
            img = Image.open(path)
            return "\n".join([f"{k}: {v}" for k, v in img.info.items() if isinstance(v, str)])
        elif ext in [".jpg", ".jpeg"]:
            with open(path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
            return "\n".join([f"{k}: {tags[k]}" for k in tags if k not in ("JPEGThumbnail", "TIFFThumbnail")])
        else:
            return ""
    except Exception as e:
        print(f"    [EXIF] READ ERROR {path}: {e}")
        return ""

class MetadataManager:
    """SQLite DB를 사용하여 모든 메타데이터를 관리하는 클래스"""
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    path TEXT PRIMARY KEY,
                    exif TEXT,
                    is_favorite INTEGER DEFAULT 0,
                    pending_command INTEGER DEFAULT 0,
                    pending_delete INTEGER DEFAULT 0
                )
            """)
    
    def get_image_data(self, path):
        cur = self.conn.cursor()
        cur.execute("SELECT exif, is_favorite, pending_command, pending_delete FROM images WHERE path=?", (path,))
        return cur.fetchone()

    def add_or_update_exif(self, path, exif):
        with self.conn:
            self.conn.execute("""
                INSERT INTO images (path, exif) VALUES (?, ?)
                ON CONFLICT(path) DO UPDATE SET exif=excluded.exif
            """, (path, exif))
            
    def toggle_status(self, path, field):
        # is_favorite, pending_command, pending_delete 상태를 토글
        with self.conn:
            # 먼저 데이터가 있는지 확인하고 없으면 삽입
            self.conn.execute("INSERT OR IGNORE INTO images (path) VALUES (?)", (path,))
            self.conn.execute(f"UPDATE images SET {field} = 1 - {field} WHERE path=?", (path,))
        self.conn.commit()
    def get_all_paths_in_folder(self, folder_path):
        cur = self.conn.cursor()
        # ✅ SQL 쿼리 수정: 폴더 경로 뒤에 반드시 '/'가 오도록 하여 다른 폴더가 겹치지 않게 함
        # ex) 'C:/folder' -> 'C:/folder/%' 가 아닌 'C:/folder/%' 와 'C:/folder//%' 로 조회
        # 'C:/folder' 로 검색시 'C:/folder-old' 가 함께 검색되는 문제 방지.
        query_path = folder_path.rstrip('/') + '/'
        cur.execute("SELECT path FROM images WHERE path LIKE ?", (query_path + '%',))
        return [row[0] for row in cur.fetchall()]
        
    def search_exif(self, keywords, folder_path):
        cur = self.conn.cursor()
        
        # 기본 쿼리: 현재 폴더 내의 파일들만 대상으로 함
        query = "SELECT path FROM images WHERE path LIKE ? AND "
        
        # '%keyword%' 형태로 파라미터 생성
        params = [folder_path + '%'] + [f'%{kw}%' for kw in keywords]
        
        # 각 키워드에 대해 LIKE 조건 추가
        conditions = " AND ".join(["exif LIKE ?"] * len(keywords))
        query += conditions
        
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]

    def get_all_favorites(self):
        cur = self.conn.cursor()
        cur.execute("SELECT path, exif FROM images WHERE is_favorite = 1")
        return cur.fetchall() # (경로, EXIF) 튜플의 리스트를 반환 
        
    def update_exif(self, path, exif):
        with self.conn:
            self.conn.execute("UPDATE images SET exif = ? WHERE path = ?", (exif, path))       

class ImageLoaderThread(QThread):
    image_loaded = pyqtSignal(str, QPixmap)

    def __init__(self):
        super().__init__()
        self.path_to_load = None

    def run(self):
        if self.path_to_load:
            try:
                pixmap = QPixmap(self.path_to_load)
                self.image_loaded.emit(self.path_to_load, pixmap)
            except Exception as e:
                print(f"이미지 로딩 스레드 오류: {e}")

    # ✅ 아래 load_image 메서드를 다시 추가합니다.
    def load_image(self, path):
        """이미지 경로를 설정하고 스레드를 시작하는 메서드"""
        self.path_to_load = path
        self.start()

class FileSystemWatcher(QThread):
    file_created = pyqtSignal(str)
    file_deleted = pyqtSignal(str)
    file_moved = pyqtSignal(str, str)

    class ChangeHandler(FileSystemEventHandler):
        def __init__(self, signals):
            super().__init__()
            self.signals = signals

        def on_created(self, event):
            if not event.is_directory and event.src_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                self.signals.file_created.emit(normalize_path(event.src_path))
        
        def on_deleted(self, event):
            if not event.is_directory:
                self.signals.file_deleted.emit(normalize_path(event.src_path))

        def on_moved(self, event):
            if not event.is_directory:
                self.signals.file_moved.emit(normalize_path(event.src_path), normalize_path(event.dest_path))

    def __init__(self):
        super().__init__()
        self.observer = Observer()
        self.path_to_watch = None
    
    def run(self):
        if self.path_to_watch:
            event_handler = self.ChangeHandler(self)
            self.observer.schedule(event_handler, self.path_to_watch, recursive=True)
            self.observer.start()
            self.observer.join()

    def start_watching(self, path):
        self.stop_watching()
        self.path_to_watch = path
        self.observer = Observer()
        self.start()

    def stop_watching(self):
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            
class CacheWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list) # 새로 추가된 파일 목록을 반환
    
    def __init__(self, image_paths, db_manager):
        super().__init__()
        self.image_paths = image_paths
        self.db = db_manager
        
    def run(self):
        total = len(self.image_paths)
        newly_cached = []
        for idx, path in enumerate(self.image_paths):
            thumb_path = get_thumb_path(path)
            if not os.path.exists(thumb_path):
                try:
                    img = Image.open(path)
                    img.thumbnail((128,128), Image.LANCZOS)
                    img.convert("RGB").save(thumb_path, "JPEG")
                except Exception:
                    pass
            
            exif = read_exif(path)
            self.db.add_or_update_exif(path, exif)
            newly_cached.append(path)
            self.progress.emit(idx + 1, total)
        self.finished.emit(newly_cached)

class ImageListWorker(QThread):
    paths_found = pyqtSignal(list)
    finished = pyqtSignal()
    
    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        
    def run(self):
        batch = []
        for root, _, files in os.walk(self.folder):
            for file in files:
                if file.lower().endswith(('.png','.jpg','.jpeg','.webp')):
                    batch.append(os.path.join(root, file))
                    if len(batch) >= 1000:
                        self.paths_found.emit(batch)
                        batch = []
        if batch:
            self.paths_found.emit(batch)
        self.finished.emit()

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setFocusPolicy(Qt.ClickFocus)
        
    def mousePressEvent(self, event):
        self.clicked.emit()
        tb = self.parentWidget()
        if tb and hasattr(tb, "setFocus"):
            tb.setFocus(Qt.OtherFocusReason)
        super().mousePressEvent(event)

class ThumbnailBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.images = []
        self.thumb_cache = {}
        self.selected = 0
        self.start_index = 0
        self.setFocusPolicy(Qt.StrongFocus)
        self.installEventFilter(parent)

        thumb_width = 130
        thumb_height = 130
        button_height = 30

        self.btn_up = QPushButton('▲', self)
        self.btn_down = QPushButton('▼', self)
        
        font = QFont()
        font.setPointSize(10)
        self.btn_up.setFont(font)
        self.btn_down.setFont(font)

        self.btn_up.setFixedSize(thumb_width, button_height)
        self.btn_down.setFixedSize(thumb_width, button_height)

        # --- 클릭 핸들러 연결 수정 ---
        self.btn_up.clicked.connect(self.on_up_button_clicked)
        self.btn_down.clicked.connect(self.on_down_button_clicked)

        self.thumb_layout = QVBoxLayout()
        self.thumb_layout.setSpacing(5)
        self.thumb_layout.setContentsMargins(0,0,0,0)
        self.thumbs = []
        for i in range(5):
            box = QWidget(self)
            box.setFixedSize(thumb_width, thumb_height) 
            vbox = QVBoxLayout(box)
            vbox.setContentsMargins(0,0,0,0)
            vbox.setSpacing(4)
            box.setLayout(vbox)
            self.thumb_layout.addWidget(box)
            self.thumbs.append(box)

        vlay = QVBoxLayout(self)
        vlay.setSpacing(0)
        vlay.setContentsMargins(0, 5, 0, 5)
        vlay.addWidget(self.btn_up, alignment=Qt.AlignHCenter)
        vlay.addLayout(self.thumb_layout)
        vlay.addWidget(self.btn_down, alignment=Qt.AlignHCenter)
        self.setLayout(vlay)

    def on_up_button_clicked(self):
        """위쪽 버튼 클릭 시 Shift 키 상태를 확인하여 동작"""
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.ShiftModifier:
            self.move_to_top()
        else:
            self.move_up()

    def on_down_button_clicked(self):
        """아래쪽 버튼 클릭 시 Shift 키 상태를 확인하여 동작"""
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.ShiftModifier:
            self.move_down_fast()
        else:
            self.move_down()

    def set_shift_mode(self, enabled):
        """Shift 키 상태에 따라 버튼 스타일을 변경하는 메서드"""
        shift_style = """
            QPushButton { background-color: #5D3FD3; border: 1px solid #7b68ee; }
            QPushButton:hover { background-color: #7b68ee; }
        """
        if enabled:
            self.btn_up.setStyleSheet(shift_style)
            self.btn_down.setStyleSheet(shift_style)
        else:
            self.btn_up.setStyleSheet("")
            self.btn_down.setStyleSheet("")

    def move_to_top(self):
        """목록의 가장 처음으로 이동합니다."""
        if self.images:
            self.set_selected(0)

    def move_down_fast(self):
        """목록에서 100개 아래로 이동합니다."""
        if not self.images: return
        total_images = len(self.images)
        new_index = self.selected + 100
        if new_index >= total_images:
            new_index = total_images - 1
        self.set_selected(new_index)

    def set_images(self, image_paths):
        self.images = image_paths

    def update_thumbs(self):
        thumb_label_size = 120
        for i in range(5):
            box = self.thumbs[i]
            vbox = box.layout()
            while vbox.count():
                child = vbox.takeAt(0)
                w = child.widget()
                if w: w.deleteLater()
            
            vbox.addStretch(1)
            idx = self.start_index + i
            if not self.images or idx >= len(self.images):
                box.setStyleSheet("border: none; background: #232323;")
                vbox.addWidget(QLabel(""))
            else:
                path = self.images[idx]
                thumb_path = get_thumb_path(path)
                icons, _, _ = self.parent._get_status_icons_and_style(path)
                pix = QPixmap(thumb_path)
                
                thumb_label = ClickableLabel()
                thumb_label.setContextMenuPolicy(Qt.CustomContextMenu)
                thumb_label.customContextMenuRequested.connect(lambda _, p=path: self.parent.show_context_menu_for_path(p))
                thumb_label.setAlignment(Qt.AlignCenter)
                thumb_label.setFixedSize(thumb_label_size, thumb_label_size) 
                if os.path.exists(thumb_path) and not pix.isNull():
                    thumb_label.setPixmap(pix.scaled(thumb_label_size, thumb_label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    thumb_label.setText('No Img')
                thumb_label.clicked.connect(lambda checked=False, x=idx: self.set_selected(x))
                vbox.addWidget(thumb_label, alignment=Qt.AlignCenter)
                
                icons_label = QLabel(icons)
                icons_label.setAlignment(Qt.AlignRight)
                icons_label.setStyleSheet("padding-right: 5px;")
                vbox.addWidget(icons_label)
                
                if idx == self.selected:
                    box.setStyleSheet("border: 2px solid #41B0FF; border-radius: 6px; background: #202c34;")
                else:
                    box.setStyleSheet("border: 1px solid #444; border-radius: 6px; background: #232323;")
            vbox.addStretch(1)

    def move_up(self):
        if self.selected > 0:
            self.selected -= 1
            if self.selected < self.start_index:
                self.start_index = self.selected
            self.update_thumbs()
            self.parent.on_thumb_selected(self.selected)

    def move_down(self):
        if self.selected < len(self.images) - 1:
            self.selected += 1
            if self.selected >= self.start_index + 5:
                self.start_index = self.selected - 4
            self.update_thumbs()
            self.parent.on_thumb_selected(self.selected)

    def set_selected(self, idx, notify=True):
        if 0 <= idx < len(self.images):
            self.selected = idx
            if self.selected < self.start_index:
                self.start_index = self.selected
            elif self.selected >= self.start_index + 5:
                self.start_index = self.selected - 4
            self.update_thumbs()
            if notify and hasattr(self.parent, 'on_thumb_selected'):
                self.parent.on_thumb_selected(self.selected)
 
    def get_selected_path(self):
        if 0 <= self.selected < len(self.images):
            return self.images[self.selected]
        return None     

class FavoriteItemWidget(QWidget):
    """즐겨찾기 목록의 각 아이템을 표시하는 커스텀 위젯"""
    remove_favorite = pyqtSignal(str)
    path_renamed = pyqtSignal(str, str)

    def __init__(self, path, exif, parent=None):
        super().__init__(parent)
        self.path = path
        self.exif = exif
        self.parent_window = parent
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # 썸네일 위젯 (고화질 원본 로딩)
        self.thumb_container = QWidget()
        self.thumb_container.setFixedSize(138, 138)
        self.thumb_container.setStyleSheet("background-color: #2c2c2c; border-radius: 6px;")
        thumb_layout = QVBoxLayout(self.thumb_container)
        
        pix = QPixmap(self.path) # 원본 이미지 로드
        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignCenter)
        if not pix.isNull():
            thumb_label.setPixmap(pix.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            thumb_label.setText("No Image")
        thumb_layout.addWidget(thumb_label)
        main_layout.addWidget(self.thumb_container)

        # 파일명/EXIF 위젯
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)
        
        self.filename_label = QLabel(os.path.basename(self.path))
        self.filename_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.filename_label.setWordWrap(True)

        exif_display_text = exif_for_display(self.exif)
        if "Negative prompt:" in exif_display_text:
            exif_display_text = exif_display_text.split("Negative prompt:")[0].strip()
        exif_label = QLabel(exif_display_text)
        exif_label.setWordWrap(True)

        info_layout.addWidget(self.filename_label)
        info_layout.addWidget(exif_label)
        main_layout.addLayout(info_layout, 1)

        # 삭제 버튼
        remove_button = QPushButton("X")
        remove_button.setFixedSize(24, 24)
        remove_button.setStyleSheet("QPushButton { border-radius: 12px; background-color: #555; color: white; }"
                                    "QPushButton:hover { background-color: #E57373; }")
        remove_button.clicked.connect(lambda: self.remove_favorite.emit(self.path))
        main_layout.addWidget(remove_button)

    def mouseDoubleClickEvent(self, event):
        # 파일명 영역을 더블클릭했을 때만 이름 변경 함수 호출
        if self.filename_label.geometry().contains(event.pos()):
            self.rename_filename()
        else:
            super().mouseDoubleClickEvent(event)
            
    def rename_filename(self):
        old_path = self.path
        base = os.path.basename(old_path)
        name, ext = os.path.splitext(base)
        
        new_name, ok = QInputDialog.getText(self, "파일명 변경", "새 파일명:", text=name)
        
        if ok and new_name and new_name != name:
            new_path = os.path.join(os.path.dirname(old_path), new_name + ext)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "오류", "같은 이름의 파일이 이미 존재합니다.")
                return
            
            self.path_renamed.emit(old_path, new_path)
            
class FavoritesWindow(QWidget):
    """새롭게 디자인된 즐겨찾기 목록 창"""
    def __init__(self, parent=None):
        super().__init__()
        self.parent_window = parent
        self.all_favorites = []
        self.current_page = 0
        self.items_per_page = 5

        self.init_ui()
        self.load_favorites()

    def init_ui(self):
        self.setWindowTitle('즐겨찾기 목록')
        self.resize(1200, 800)
        self.setStyleSheet("background-color: #232323; color: #ddd;")

        main_layout = QVBoxLayout(self)

        # 상단 컨트롤 패널 (검색, 페이지네이션)
        control_layout = QHBoxLayout()
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("EXIF로 즐겨찾기 내에서 검색...")
        self.search_box.textChanged.connect(self.filter_favorites)
        
        self.prev_button = QPushButton("< 이전")
        self.prev_button.clicked.connect(self.prev_page)
        self.page_label = QLabel("1 / 1")
        self.next_button = QPushButton("다음 >")
        self.next_button.clicked.connect(self.next_page)
        
        control_layout.addWidget(self.search_box, 1)
        control_layout.addStretch(1)
        control_layout.addWidget(self.prev_button)
        control_layout.addWidget(self.page_label)
        control_layout.addWidget(self.next_button)
        
        main_layout.addLayout(control_layout)
        
        # 즐겨찾기 목록
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("QListWidget::item { border: 1px solid #444; border-radius: 8px; margin-bottom: 5px; }")
        main_layout.addWidget(self.list_widget)

    def load_favorites(self):
        # PhotoManager의 DB 인스턴스를 통해 데이터 로드
        self.all_favorites = self.parent_window.db.get_all_favorites()
        self.filter_favorites()

    def filter_favorites(self):
        keyword = self.search_box.text().lower().strip()
        if not keyword:
            self.filtered_favorites = self.all_favorites
        else:
            self.filtered_favorites = [
                (path, exif) for path, exif in self.all_favorites 
                if keyword in exif_for_display(exif).lower()
            ]
        self.current_page = 0
        self.update_list()

    def update_list(self):
        self.list_widget.clear()
        
        start_index = self.current_page * self.items_per_page
        end_index = start_index + self.items_per_page
        
        for path, exif in self.filtered_favorites[start_index:end_index]:
            item_widget = FavoriteItemWidget(path, exif, self) # self를 부모로 전달
            item_widget.remove_favorite.connect(self.remove_item)
            # 파일명 변경 신호를 PhotoManager의 처리 함수와 연결
            item_widget.path_renamed.connect(self.parent_window.rename_favorite_path)
            
            list_item = QListWidgetItem(self.list_widget)
            list_item.setSizeHint(item_widget.sizeHint())
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, item_widget)
            
        self.update_page_label()

    def remove_item(self, path):
        # 1. DB에서 즐겨찾기 상태 변경
        self.parent_window.db.toggle_status(path, 'is_favorite')
        
        # 2. 메인 UI의 아이콘 즉시 업데이트
        self.parent_window._update_item_display(path)
        
        # 3. 즐겨찾기 창 목록 새로고침
        self.load_favorites()
        
    def update_page_label(self):
        total_items = len(self.filtered_favorites)
        total_pages = (total_items - 1) // self.items_per_page + 1
        if total_pages == 0: total_pages = 1
        
        self.page_label.setText(f"{self.current_page + 1} / {total_pages}")
        self.prev_button.setEnabled(self.current_page > 0)
        self.next_button.setEnabled(self.current_page < total_pages - 1)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_list()

    def next_page(self):
        total_items = len(self.filtered_favorites)
        total_pages = (total_items - 1) // self.items_per_page + 1
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.update_list()
            
class PhotoManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = MetadataManager(DB_FILE)
        self.image_loader = ImageLoaderThread()
        self.image_loader.image_loaded.connect(self.on_image_loaded)
        self.fs_watcher = FileSystemWatcher()
        self.fs_watcher.file_created.connect(self.on_file_created)
        self.fs_watcher.file_deleted.connect(self.on_file_deleted)
        
        self.image_paths = []
        self.thumb_cache = {}
        self.last_selected = None
        self.current_path = ""
        self.delete_mode = False
        self.view_mode = "thumb"
        self._is_flat_tree = False
        self._flat_paths = []
        self.exif_undo_cache = {}
        
        self.setWindowTitle("PhotoManager Pro")
        self.setMinimumSize(1500, 1200)

        # --- 레이아웃 설정 시작 ---

        # 1. 메인 central 위젯과 전체 레이아웃 생성
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 2. 상단 컨트롤 UI 생성 (버튼, 검색창)
        top_controls_layout = QVBoxLayout()
        button_row_layout = QHBoxLayout()
        search_row_layout = QHBoxLayout()

        btn = lambda txt, cb: QPushButton(txt, clicked=cb)

        self.btn_open = btn("폴더 열기", self.open_folder)
        self.btn_switch = btn("뷰 전환", self.toggle_view)
        self.btn_fav = btn("+FAV", self.toggle_fav)
        self.btn_del = btn("즉시 삭제", self.instant_delete)
        self.btn_save = btn("설정 저장", self.save_config)
        self.btn_exif_edit = btn("EXIF 편집", self.edit_exif)
        self.btn_exif_clear_undo = btn("EXIF 지우기", self.clear_exif)
        self.btn_refresh = btn("새로고침", self.refresh_images)
        self.btn_favlist = btn("즐겨찾기", self.show_favorites)
        self.btn_clean_cache = btn("캐시 정리", self.clean_cache) 
        self.chk_delete = QCheckBox("삭제 모드")
        self.chk_delete.stateChanged.connect(self.toggle_delete_mode)
        
        buttons = [
            self.btn_open, self.btn_switch, self.btn_fav, self.btn_del, 
            self.btn_save, self.btn_exif_edit, self.btn_exif_clear_undo, 
            self.btn_refresh, self.btn_favlist
        ]
        
        for button in buttons:
            button.setFixedSize(120, 32)
            button_row_layout.addWidget(button)
        button_row_layout.addWidget(self.btn_clean_cache) 
        button_row_layout.addWidget(self.chk_delete)    
        button_row_layout.addStretch(1)
        button_row_layout.addWidget(self.chk_delete)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("EXIF 검색 (쉼표로 구분하여 AND 검색)")
        self.search_box.setFixedHeight(32)
        self.search_box.textChanged.connect(self.search_exif)
        search_row_layout.addWidget(QLabel("EXIF 검색:"))
        search_row_layout.addWidget(self.search_box)
        
        top_controls_layout.addLayout(button_row_layout)
        top_controls_layout.addLayout(search_row_layout)

        # 3. 진행률 표시줄 생성
        self.progress = QProgressBar()
        self.progress.hide()
        self.progress.setMaximumHeight(10)

        # 4. 메인 콘텐츠 영역(Splitter) 위젯 생성
        self.tree = QTreeWidget() 
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.display_image)
        self.tree.currentItemChanged.connect(self.display_image)
        self.tree.setMinimumWidth(80)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_tree_context)
        self.tree.installEventFilter(self)

        self.thumb_list = QListWidget() 
        self.thumb_list.hide()
        self.thumb_list.setIconSize(QSize(112, 112))
        self.thumb_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.thumb_list.currentItemChanged.connect(self.display_image_thumb)
        self.thumb_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.thumb_list.installEventFilter(self)

        self.viewer = QLabel("이미지를 선택하세요") 
        self.viewer.setAlignment(Qt.AlignCenter)
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.exif_text = QTextEdit() 
        self.exif_text.setReadOnly(True)
        self.exif_text.setMaximumWidth(400)
        
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.viewer)
        self.splitter.addWidget(self.exif_text)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setSizes([200, 800, 400])

        # 5. 모든 UI 요소를 메인 레이아웃에 순서대로 추가
        main_layout.addLayout(top_controls_layout)
        main_layout.addWidget(self.progress)
        main_layout.addWidget(self.splitter)
        
        # 6. 오버레이 위젯과 썸네일 바 설정 (메인 레이아웃 설정 후)
        self.cache_overlay = QLabel("캐싱중! UI를 클릭 시 프리징 현상이 나타날 수 있습니다", self)
        self.cache_overlay.setStyleSheet("""
            background:rgba(40,30,0,180); color:#ffe066; font-size:22px;
            font-weight:bold; border-radius:24px; padding:36px 50px;
            qproperty-alignment: AlignCenter;
        """)
        self.cache_overlay.setAlignment(Qt.AlignCenter)
        self.cache_overlay.hide()
        self.cache_overlay.raise_()

        self.thumbnail_bar = ThumbnailBar(self)
        self.thumbnail_bar.hide()
        self.thumbnail_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.thumbnail_bar.customContextMenuRequested.connect(self.open_thumb_bar_context)


        # 7. 설정 로드 및 초기 UI 상태 설정
        self.load_config()
        
        if self.current_path:
            self.load_images(self.current_path)

        self.tree.hide()
        if self.splitter.indexOf(self.thumbnail_bar) == -1:
            self.splitter.insertWidget(0, self.thumbnail_bar)
        self.thumbnail_bar.show()
        self.btn_switch.setText("트리")
        self.populate_thumbs()

    def focus_main_window(self):
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)
        
    def on_thumbnail_clicked(self, idx):
        self.set_selected(idx)
        self.parent.focus_main_window()  
        
    def on_image_loaded(self, path, pixmap):
        # 지연 로딩된 이미지를 표시
        if path == self.last_selected and not pixmap.isNull():
            self.viewer.setPixmap(pixmap.scaled(self.viewer.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def on_file_created(self, path):
        print(f"파일 생성 감지: {path}")
        # ✅ 중복 추가를 방지하는 로직
        if path not in self.image_paths:
            self.image_paths.append(path)
            self.image_paths.sort()
            self.start_caching([path]) # 새로 생긴 파일만 캐싱
        else:
            print(f"이미 목록에 존재하는 파일입니다: {path}")

    def on_file_deleted(self, path):
        print(f"파일 삭제 감지: {path}")
        if path in self.image_paths:
            self.image_paths.remove(path)
        # UI에서 해당 아이템 제거 (효율적인 방식 필요, 일단은 전체 리로드)
        self.refresh_views()
    
    def refresh_views(self):
        # 현재 뷰만 새로고침하는 간소화된 함수
        if self.view_mode == "tree":
            self.populate_tree(selected_path=self.last_selected)
        else:
            self.populate_thumbs()        

    # --- 파일/폴더/이미지 목록 ---
    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "이미지 폴더 선택")
        if folder:
            self.load_images(folder)
            
    def load_images(self, folder):
        print("\n" + "="*50)
        print(f"새 폴더 로딩 시작: {folder}")
        
        # --- 1. 이전 작업 중지 및 모든 데이터 초기화 ---
        if hasattr(self, 'fs_watcher'):
            self.fs_watcher.stop_watching()
        if hasattr(self, 'cache_worker') and self.cache_worker.isRunning():
            self.cache_worker.quit()
            self.cache_worker.wait()

        print(f"초기화 전 self.image_paths 개수: {len(self.image_paths)}")
        self.image_paths = []
        self._flat_paths = []
        self.last_selected = None
        self.viewer.clear()
        self.exif_text.clear()
        self.tree.clear()
        self.thumbnail_bar.set_images([])
        self.thumbnail_bar.update_thumbs()
        print(f"초기화 후 self.image_paths 개수: {len(self.image_paths)}")
        # --- 초기화 끝 ---

        self.current_path = normalize_path(folder)
        self.setWindowTitle(f"PhotoManager Pro - {self.current_path}")
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        try:
            current_files_on_disk = set()
            for root, _, files in os.walk(self.current_path):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        current_files_on_disk.add(normalize_path(os.path.join(root, file)))

            db_files_in_folder = set(self.db.get_all_paths_in_folder(self.current_path))
            
            new_files = list(current_files_on_disk - db_files_in_folder)
            deleted_files = list(db_files_in_folder - current_files_on_disk)

            if deleted_files:
                print(f"존재하지 않는 파일 {len(deleted_files)}개 정리 중...")
                for path in deleted_files:
                    self.db.conn.execute("DELETE FROM images WHERE path=?", (path,))
                    thumb_path = get_thumb_path(path)
                    if os.path.exists(thumb_path):
                        try: os.remove(thumb_path)
                        except OSError as e: print(f"썸네일 삭제 실패: {e}")
                self.db.conn.commit()

            self.image_paths = sorted(list(current_files_on_disk))
            print(f"디스크 스캔 후 self.image_paths 개수: {len(self.image_paths)}")

            if new_files:
                print(f"새 파일 {len(new_files)}개 캐싱 시작...")
                self.start_caching(new_files)
            else:
                print("새 파일 없음. UI를 즉시 로드합니다.")
                self.refresh_views()

        finally:
            QApplication.restoreOverrideCursor()
            
        self.fs_watcher.start_watching(self.current_path)
        print("="*50 + "\n")
        
    # 오버레이 위치/크기를 로딩 ProgressBar 밑에 맞춤
    def update_cache_overlay(self):
        # 버튼바 + progressBar 높이 구하기
        bar_y = self.progress.y() + self.progress.height()
        # splitter 전체 영역 가져오기 (progressBar 밑~아래까지)
        x = self.splitter.x()
        y = bar_y
        w = self.splitter.width()
        h = self.splitter.height()
        self.cache_overlay.setGeometry(x, y, w, h)

    # 윈도우 리사이즈될 때마다 오버레이도 같이 크기 맞춤
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'cache_overlay'):
            self.update_cache_overlay()
            
    # --- 썸네일/EXIF 캐싱 ---
    def start_caching(self, paths):
        if not paths: return
        self.progress.setMaximum(len(paths))
        self.progress.setValue(0)
        self.progress.show()
        
        # CacheWorker가 이제 DB 매니저를 인자로 받음
        self.cache_worker = CacheWorker(paths, self.db)
        self.cache_worker.progress.connect(self.progress.setValue)
        self.cache_worker.finished.connect(self.on_caching_finished)
        self.cache_worker.start()
        
    def on_caching_finished(self, newly_cached_paths):
        print(f"{len(newly_cached_paths)}개 파일 캐싱 완료.")
        self.progress.hide()
        
        # ✅ 중요: self.image_paths는 load_images에서 이미 완벽하게 설정되었습니다.
        # 따라서 여기서는 데이터를 추가하지 않고, 썸네일이 생성된 UI만 새로고침합니다.
        print("캐싱 완료 후 UI만 새로고침합니다.")
        self.refresh_views()  
        
    # --- 트리/썸네일 뷰 전환 ---
    def toggle_view(self):
        # 현재 선택된 아이템을 기억합니다.
        current_selection = self.last_selected

        # 1. 뷰 모드 전환
        if self.view_mode == "tree":
            self.view_mode = "thumb"
            self.tree.hide()
            self.thumbnail_bar.show()
            self.btn_switch.setText("트리뷰로 전환")
            # 썸네일 뷰의 목록을 현재 파일 목록으로 설정합니다.
            self.populate_thumbs()
        else: # thumb -> tree
            self.view_mode = "tree"
            self.thumbnail_bar.hide()
            self.tree.show()
            self.btn_switch.setText("썸네일뷰로 전환")
            # 트리 뷰의 목록을 현재 파일 목록으로 설정합니다.
            self.populate_tree(selected_path=current_selection)

        # 뷰 전환 후, 이전에 선택했던 아이템을 다시 선택해줍니다.
        # (populate 함수가 이미 처리하므로 이 부분은 필요 없을 수 있으나, 안전을 위해 추가)
        if current_selection:
            self._perform_selection()
            
    def on_thumb_selected(self, idx):
        if not (0 <= idx < len(self.thumbnail_bar.images)):
            return
        
        path = self.thumbnail_bar.images[idx]
        self.last_selected = path
        
        # 1. 썸네일을 즉시 표시
        thumb_path = get_thumb_path(path)
        if os.path.exists(thumb_path):
            pix = QPixmap(thumb_path)
            self.viewer.setPixmap(pix.scaled(self.viewer.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.viewer.setText("썸네일 없음...")
            
        # 2. EXIF 정보는 DB에서 바로 가져옴
        data = self.db.get_image_data(path)
        exif = data[0] if data else ""
        self.exif_text.setPlainText(exif_for_display(exif))

        # 3. 고화질 이미지를 백그라운드에서 로딩
        self.image_loader.load_image(path)
        self.update_exif_buttons(path)

    def _get_status_icon(self, path):
        # ✎ > 🗑 > 🌠 > 일반
        if path in self.pending_command:
            font = QFont("Segoe UI", 11, weight=QFont.Bold)
            return "✎", font, QColor("#A259E6")
        elif path in self.pending_delete:
            font = QFont("Segoe UI", 11, weight=QFont.Bold)
            font.setItalic(True)
            return "🗑", font, QColor("red")
        elif path in self.fav_set:
            return "🌠", QFont("Segoe UI", 11), QColor("#ffe066")
        else:
            return "", QFont("Segoe UI", 11), QColor("#ddd")
 
    def _get_status_icons_and_style(self, path):
        icons_html = ""
        font = QFont("Segoe UI", 11)
        color = QColor("#ddd")
        icon_size = 16  # 아이콘 크기 (px)

        data = self.db.get_image_data(path)
        
        if data:
            _, is_favorite, pending_command, pending_delete = data
            
            # 아이콘 파일 경로를 URI 형식으로 변환 (파일 경로에 공백 등이 있어도 안전)
            edit_icon_uri = Path(os.path.join(BASE_DIR, 'edit_icon.png')).as_uri()
            trash_icon_uri = Path(os.path.join(BASE_DIR, 'trash_icon.png')).as_uri()
            star_icon_uri = Path(os.path.join(BASE_DIR, 'star_icon.png')).as_uri()

            # 상태에 따라 아이콘 HTML 태그를 추가
            if pending_command:
                icons_html += f'<img src="{edit_icon_uri}" width="{icon_size}" height="{icon_size}">&nbsp;'
                font.setBold(True)
                color = QColor("#A259E6")
            
            if pending_delete:
                icons_html += f'<img src="{trash_icon_uri}" width="{icon_size}" height="{icon_size}">&nbsp;'
                font.setBold(True)
                font.setItalic(True)
                if not pending_command:
                    color = QColor("red")
            
            if is_favorite:
                icons_html += f'<img src="{star_icon_uri}" width="{icon_size}" height="{icon_size}">&nbsp;'
                if not pending_command and not pending_delete:
                    color = QColor("#ffe066")
        
        return icons_html.strip(), font, color
 
    def _create_tree_item_widget(self, path):
        """경로에 해당하는 아이템 위젯(아이콘 + 파일명)을 생성하여 반환합니다."""
        filename = os.path.basename(path)
        icons_html, font, color = self._get_status_icons_and_style(path)

        # 아이콘과 텍스트를 담을 컨테이너 위젯
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6) # 아이콘과 텍스트 사이 간격
        
        # 아이콘을 표시할 라벨 (HTML 지원)
        icon_label = QLabel(icons_html)
        
        # 파일명을 표시할 라벨
        text_label = QLabel(filename)
        text_label.setFont(font)
        text_label.setStyleSheet(f"color: {color.name()}; background-color: transparent;")
        # 나중에 쉽게 찾을 수 있도록 객체 이름 설정
        text_label.setObjectName("treeItemTextLabel") 
        
        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addStretch()
        
        return widget
 
    def update_thumbs(self):
        for i in range(5):
            box = self.thumbs[i]
            vbox = box.layout()
            while vbox.count():
                child = vbox.takeAt(0)
                w = child.widget()
                if w: w.deleteLater()

            idx = self.start_index + i
            if not self.images or idx >= len(self.images):
                box.setStyleSheet("border: none; background: #232323;")
                vbox.addStretch(1)
                vbox.addWidget(QLabel(""))
                vbox.addStretch(1)
                continue
            
            path = self.images[idx]
            
            # --- 아래 로직 수정 ---
            # 부모(PhotoManager)의 DB 조회 함수를 통해 아이콘 정보를 가져옵니다.
            icons, _, icon_color = self.parent._get_status_icons_and_style(path)
            # ---------------------

            thumb_path = get_thumb_path(path) # thumb_cache에서 찾는 것보다 get_thumb_path가 더 안정적
            pix = QPixmap(thumb_path)
            
            vbox.addStretch(1)
            
            thumb_label = ClickableLabel()
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setFixedSize(100, 100)
            if os.path.exists(thumb_path) and not pix.isNull():
                thumb_label.setPixmap(pix.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb_label.setText('No Img')
            thumb_label.clicked.connect(lambda checked=False, x=idx: self.set_selected(x))
            vbox.addWidget(thumb_label, alignment=Qt.AlignCenter)
            
            # 상태 아이콘 표시
            icons_label = QLabel(icons)
            icons_label.setAlignment(Qt.AlignRight)
            # 아이콘 색상을 DB 조회 결과에 따라 동적으로 설정
            icons_label.setStyleSheet(f'font-size: 17px; color: {icon_color.name()};')
            vbox.addWidget(icons_label)
            
            vbox.addStretch(1)
            
            if idx == self.selected:
                box.setStyleSheet("border: 2px solid #41B0FF; border-radius: 6px; background: #202c34;")
            else:
                box.setStyleSheet("border: 1px solid #444; border-radius: 6px; background: #232323;")
                
    def populate_tree(self, selected_path=None):
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()

        try:
            paths_to_show = self._flat_paths if self._is_flat_tree else self.image_paths

            if self._is_flat_tree:
                for path in paths_to_show:
                    item = QTreeWidgetItem(self.tree)
                    item.setData(0, Qt.UserRole, path)
                    widget = self._create_tree_item_widget(path) # ✅ 변경된 부분
                    self.tree.setItemWidget(item, 0, widget)
            else:
                dir_structure = {}
                root_len = len(self.current_path.split('/'))
                for path in paths_to_show:
                    parts = path.split('/')[root_len:]
                    current_level = dir_structure
                    for part in parts:
                        if part not in current_level: current_level[part] = {}
                        current_level = current_level[part]
                
                def build_tree_recursively(parent_item, structure, current_path_parts):
                    folders = sorted([name for name, children in structure.items() if children])
                    files = sorted([name for name, children in structure.items() if not children])

                    for name in folders + files:
                        children = structure[name]
                        current_path = "/".join(current_path_parts + [name])
                        item = QTreeWidgetItem(parent_item)
                        
                        if not children: # 파일인 경우
                            item.setData(0, Qt.UserRole, current_path)
                            widget = self._create_tree_item_widget(current_path) # ✅ 변경된 부분
                            self.tree.setItemWidget(item, 0, widget)
                        else: # 폴더인 경우
                            item.setText(0, name)
                            item.setData(0, Qt.UserRole, current_path)
                            build_tree_recursively(item, children, current_path_parts + [name])

                build_tree_recursively(self.tree, dir_structure, self.current_path.split('/'))

            if selected_path:
                item_to_select = self._find_item_by_path_in_tree(selected_path)
                if item_to_select:
                    self.tree.setCurrentItem(item_to_select)
                    self.tree.scrollToItem(item_to_select, QAbstractItemView.PositionAtCenter)
        finally:
            self.tree.setUpdatesEnabled(True)
    
    def populate_tree_for_paths(self, paths):
        self.tree.clear()
        parent_cache = {}
        for path in paths:
            rel = os.path.relpath(path, self.current_path)
            parts = rel.split(os.sep)
            parent = self.tree
            path_acc = self.current_path
            for i, part in enumerate(parts):
                path_acc = os.path.join(path_acc, part)
                cache_key = (normalize_path(path_acc), part)    # ← parent 대신 path_acc!
                if cache_key in parent_cache:
                    item = parent_cache[cache_key]
                else:
                    item = QTreeWidgetItem([part])
                    if isinstance(parent, QTreeWidget):
                        parent.addTopLevelItem(item)
                    else:
                        parent.addChild(item)
                    parent_cache[cache_key] = item
                parent = item

    def batch_populate_tree_for_paths(self, paths, batch_size=100):
        self.tree.clear()
        parent_cache = {}
        idx = 0
        def add_batch():
            nonlocal idx
            count = 0
            while idx < len(paths) and count < batch_size:
                # 위와 같은 아이템 추가 로직
                idx += 1
                count += 1
            if idx < len(paths):
                QTimer.singleShot(1, add_batch)
        add_batch()
    
    def _on_tree_item_expanded(self, item):
        # 이미 하위 노드 있으면 생략
        if item.childCount() > 0 and item.child(0).data(0, Qt.UserRole) != "DUMMY":
            return
        while item.childCount() > 0:
            item.removeChild(item.child(0))
        # 현재 item까지의 경로 (폴더 or 파일)
        names = []
        parent = item
        while parent:
            names.insert(0, parent.text(0))
            parent = parent.parent()
        base_path = os.path.join(self.current_path, *names)
        # 1. 폴더라면(하위 탐색)만
        if os.path.isdir(base_path):
            # 자식 집합
            added = set()
            for path in self.cached_paths:
                # 하위 아이템만
                parent_dir = os.path.dirname(path)
                if os.path.normpath(parent_dir) != os.path.normpath(base_path):
                    continue
                leaf_name = os.path.basename(path)
                # 파일/폴더 표시 (상태 아이콘 붙이기)
                icons, font, color = self._get_status_icons_and_style(path)
                label = (icons + " " if icons else "") + leaf_name
                child_item = QTreeWidgetItem([label])
                child_item.setFont(0, font)
                child_item.setForeground(0, QBrush(color))
                item.addChild(child_item)
        # 2. 파일이면 하위 없음

        # 자식 없으면 dummy
        if item.childCount() == 0:
            dummy = QTreeWidgetItem(["<비어있음>"])
            dummy.setData(0, Qt.UserRole, "DUMMY")
            item.addChild(dummy)

    def _find_item_by_path_in_tree(self, target_path):
        """
        (개선됨) UserRole 데이터를 사용하여 트리에서 경로에 해당하는 아이템을 찾습니다.
        QTreeWidgetItemIterator를 사용해 모든 아이템을 효율적으로 탐색합니다.
        """
        if not target_path:
            return None
        
        # 이터레이터를 생성하여 트리의 모든 아이템을 순회합니다.
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            item_path = item.data(0, Qt.UserRole) # 아이템에 저장된 파일 경로
            
            # 아이템의 경로와 찾으려는 경로가 일치하면 해당 아이템을 반환합니다.
            if item_path and item_path == target_path:
                return item
            
            iterator += 1
            
        return None
        def walk(item, curr_path):
            # (이하 기존 walk 함수 로직과 동일)
            item_part = item.text(0)
            for emo in ["✎", "🗑", "🌠"]:
                item_part = item_part.replace(emo, "")
            new_path = os.path.join(curr_path, item_part.strip())
            
            # 실제 파일 아이템이고 경로가 일치하는 경우
            is_file_node = (item.data(0, Qt.UserRole) is not None)
            if is_file_node and normalize_path(new_path) == normalize_path(target_path):
                return item

            # 폴더인 경우 하위 탐색
            for i in range(item.childCount()):
                found = walk(item.child(i), new_path)
                if found: return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            # 최상위 아이템부터 탐색 시작
            item = self.tree.topLevelItem(i)
            item_part = item.text(0)
            for emo in ["✎", "🗑", "🌠"]:
                item_part = item_part.replace(emo, "")
            
            # 최상위 아이템이 파일인 경우 바로 체크
            is_file_node = (item.data(0, Qt.UserRole) is not None)
            path = os.path.join(self.current_path, item_part.strip())
            if is_file_node and normalize_path(path) == normalize_path(target_path):
                return item

            found = walk(item, self.current_path)
            if found: return found
        
        return None 
        
    def get_tree_state(self):
        expanded = set()
        def collect(item, curr_path):
            for i in range(item.childCount()):
                child = item.child(i)
                name = child.text(0)
                for emo in ["✎", "🗑", "🌠"]:
                    name = name.replace(emo, "")
                path = os.path.join(curr_path, name.strip())
                if child.isExpanded():
                    expanded.add(normalize_path(path))
                collect(child, path)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            name = item.text(0)
            for emo in ["✎", "🗑", "🌠"]:
                name = name.replace(emo, "")
            path = os.path.join(self.current_path, name.strip())
            if item.isExpanded():
                expanded.add(normalize_path(path))
            collect(item, path)
        selected = None
        curr = self.tree.currentItem()
        if curr:
            names = []
            temp = curr
            while temp:
                txt = temp.text(0)
                for emo in ["✎", "🗑", "🌠"]:
                    txt = txt.replace(emo, "")
                names.insert(0, txt.strip())
                temp = temp.parent()
            selected = normalize_path(os.path.join(self.current_path, *names))
        scroll = self.tree.verticalScrollBar().value()
        return {'expanded': expanded, 'selected': selected, 'scroll': scroll}

    def refresh_images(self):
        """(수정됨) 파일 시스템의 변경사항을 DB와 캐시에 정확히 반영하며 새로고침합니다."""
        if not self.current_path or not os.path.isdir(self.current_path):
            return
        
        print("스마트 새로고침 시작...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        try:
            # 1. 현재 파일 시스템의 파일 목록을 새로 가져옵니다.
            current_files = set()
            for root, _, files in os.walk(self.current_path):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        current_files.add(normalize_path(os.path.join(root, file)))

            # 2. 기존에 알던 파일 목록과 비교합니다.
            old_files = set(self.image_paths)
            new_files = list(current_files - old_files)
            deleted_files = list(old_files - current_files)

            # 3. 변경 사항을 처리합니다.
            if new_files or deleted_files:
                print(f"추가된 파일: {len(new_files)}개, 삭제된 파일: {len(deleted_files)}개")

                # 3a. 삭제된 파일의 DB 레코드와 썸네일 캐시를 제거합니다.
                if deleted_files:
                    for path in deleted_files:
                        # DB에서 레코드 삭제
                        self.db.conn.execute("DELETE FROM images WHERE path=?", (path,))
                        
                        # 썸네일 캐시 파일 삭제
                        thumb_path = get_thumb_path(path)
                        if os.path.exists(thumb_path):
                            try:
                                os.remove(thumb_path)
                            except OSError as e:
                                print(f"썸네일 삭제 실패: {e}")
                    self.db.conn.commit()

                # 3b. 내부 데이터 모델을 현재 파일 시스템 상태로 업데이트합니다.
                self.image_paths = sorted(list(current_files))
                
                # 3c. 새로 추가된 파일만 캐싱 작업을 수행합니다.
                if new_files:
                    self.start_caching(new_files)
                else: # 새로 추가된 파일이 없으면 (삭제만 된 경우) 바로 UI 갱신
                    self.refresh_views()
            else:
                print("변경 사항 없음.")

        finally:
            QApplication.restoreOverrideCursor()

    def restore_tree_state(self, state):
        expanded_set = set([normalize_path(p) for p in state.get('expanded', set())])
        def walk(item, curr_path):
            for i in range(item.childCount()):
                child = item.child(i)
                name = child.text(0)
                for emo in ["✎", "🗑", "🌠"]:
                    name = name.replace(emo, "")
                path = os.path.join(curr_path, name.strip())
                if normalize_path(path) in expanded_set:
                    child.setExpanded(True)
                walk(child, path)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            name = item.text(0)
            for emo in ["✎", "🗑", "🌠"]:
                name = name.replace(emo, "")
            path = os.path.join(self.current_path, name.strip())
            if normalize_path(path) in expanded_set:
                item.setExpanded(True)
            walk(item, path)
        # selection
        if state.get('selected'):
            target_path = normalize_path(state['selected'])
            def find_and_select(item, curr_path, target_path):
                for i in range(item.childCount()):
                    child = item.child(i)
                    name = child.text(0)
                    for emo in ["✎", "🗑", "🌠"]:
                        name = name.replace(emo, "")
                    next_path = os.path.join(curr_path, name.strip())
                    if normalize_path(next_path) == target_path:
                        self.tree.setCurrentItem(child)
                        return True
                    if find_and_select(child, next_path, target_path):
                        return True
                return False
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                name = item.text(0)
                for emo in ["✎", "🗑", "🌠"]:
                    name = name.replace(emo, "")
                path = os.path.join(self.current_path, name.strip())
                if normalize_path(path) == target_path:
                    self.tree.setCurrentItem(item)
                    break
                if find_and_select(item, path, target_path):
                    break
        if state.get('scroll') is not None:
            self.tree.verticalScrollBar().setValue(state['scroll'])
            
    def populate_thumbs(self):
        # 검색 중인지 확인
        is_searching = bool(self.search_box.text().strip())
        
        # 검색 중이면 필터링된 목록(_flat_paths)을, 아니면 전체 목록(image_paths)을 사용
        paths_to_show = self._flat_paths if is_searching else self.image_paths
        
        # ThumbnailBar에 현재 보여줄 이미지 목록을 설정
        self.thumbnail_bar.set_images(paths_to_show)
        
        # 선택 복원 로직
        current_selection = self.last_selected
        idx = None
        if current_selection and current_selection in paths_to_show:
            idx = paths_to_show.index(current_selection)
        
        if idx is not None:
            self.thumbnail_bar.set_selected(idx, notify=False)
        else:
            # 선택된 것이 없으면 맨 처음으로
            self.thumbnail_bar.set_selected(0, notify=True)

        self.thumbnail_bar.update_thumbs()

    # --- 이미지/EXIF 표시 ---
    def display_image(self, item, prev=None):
        # 이전에 선택된 아이템의 위젯을 재생성하여 선택 효과를 제거하고 원래 스타일로 복원
        if prev:
            path = prev.data(0, Qt.UserRole)
            if path:
                prev_widget = self._create_tree_item_widget(path)
                self.tree.setItemWidget(prev, 0, prev_widget)

        # 새로 선택된 아이템에 선택 스타일을 적용
        if item:
            current_widget = self.tree.itemWidget(item, 0)
            if current_widget:
                current_widget.setStyleSheet("background-color: #385078;")
                text_label = current_widget.findChild(QLabel, "treeItemTextLabel")
                if text_label:
                    text_label.setStyleSheet("color: #ffe066; background-color: transparent;")
        
        if item is None:
            self.viewer.setText("이미지 없음")
            self.last_selected = None
            return
            
        path = item.data(0, Qt.UserRole)
        if not path or not os.path.isfile(path):
            self.viewer.setText("폴더 선택됨")
            self.exif_text.setText("")
            self.last_selected = None
            return

        self.last_selected = path
        
        thumb_path = get_thumb_path(path)
        if os.path.exists(thumb_path):
            pix = QPixmap(thumb_path)
            self.viewer.setPixmap(pix.scaled(self.viewer.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.viewer.setText("썸네일 없음...")
            
        data = self.db.get_image_data(path)
        exif = data[0] if data else ""
        self.exif_text.setPlainText(exif_for_display(exif))

        self.image_loader.load_image(path)
        self.update_exif_buttons(path)
    
    def _update_item_display(self, path):
        """(개선됨) 특정 경로(path)의 위젯을 재생성하여 표시를 갱신합니다."""
        if self.view_mode == "tree":
            item = self._find_item_by_path_in_tree(path)
            if item:
                # 위젯을 새로 만들어서 교체하는 것이 가장 확실한 방법
                new_widget = self._create_tree_item_widget(path)
                self.tree.setItemWidget(item, 0, new_widget)
                
                # 만약 업데이트하는 아이템이 현재 선택된 아이템이라면, 선택 효과를 다시 적용
                if self.tree.currentItem() == item:
                    new_widget.setStyleSheet("background-color: #385078;")
                    text_label = new_widget.findChild(QLabel, "treeItemTextLabel")
                    if text_label:
                        text_label.setStyleSheet("color: #ffe066; background-color: transparent;")

        elif self.view_mode == "thumb":
            self.thumbnail_bar.update_thumbs()
        
    def display_image_thumb(self, curr, prev=None):
        if curr is None: return
        path = curr.data(Qt.UserRole)
        self.last_selected = path
        if not os.path.isfile(path): return
        try:
            print(f"[ThumbViewer] QPixmap 로드: {path}")
            pix = QPixmap(path)
            self.viewer.setPixmap(pix.scaled(self.viewer.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            print(f"[ThumbViewer] 이미지 표시 실패: {path}, {e}")
            self.viewer.setText("이미지 로딩 실패")
        self.exif_text.setPlainText(exif_for_display(self.exif_cache.get(path, "")))

    # --- 삭제/즐겨찾기/EXIF 편집 ---
    def toggle_fav(self):
        """상단 버튼 클릭 시 현재 선택된 아이템의 즐겨찾기 상태를 변경"""
        if self.last_selected:
            self.toggle_fav_from_path(self.last_selected)
    def toggle_fav_from_path(self, path):
        """주어진 경로의 파일에 대한 즐겨찾기 상태를 변경"""
        self.db.toggle_status(path, 'is_favorite')
        self._update_item_display(path)            
        
    def toggle_delete_mode(self, state): 
        self.delete_mode = (state == Qt.Checked)
        
    def instant_delete(self):
        cur = self.db.conn.cursor()
        cur.execute("SELECT path FROM images WHERE pending_delete = 1")
        paths_to_delete = [row[0] for row in cur.fetchall()]

        if not paths_to_delete:
            QMessageBox.information(self, "알림", "삭제 대기 중인 파일이 없습니다.")
            return

        reply = QMessageBox.question(
            self, "즉시 삭제",
            f"{len(paths_to_delete)}개의 파일을 정말 삭제할까요? (휴지통으로 이동)",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            deleted_count = 0
            for path in paths_to_delete:
                # 썸네일 캐시 파일 삭제
                thumb_path = get_thumb_path(path)
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except Exception as e:
                        print(f"썸네일 삭제 실패: {e}")
                
                # 원본 파일 휴지통으로 이동
                if os.path.exists(path):
                    move_to_trash(path)
                
                # DB에서 해당 레코드 완전 삭제
                self.db.conn.execute("DELETE FROM images WHERE path=?", (path,))
                deleted_count += 1
            
            self.db.conn.commit()
            
            QMessageBox.information(self, "완료", f"{deleted_count}개 파일을 삭제했습니다.")
            
            # ✅ 가장 확실한 방법: 폴더를 처음부터 다시 로드하여 UI와 데이터를 완벽하게 동기화합니다.
            self.load_images(self.current_path)
            
    def clean_cache(self):
        """
        현재 폴더의 파일 시스템과 DB를 비교하여 불일치하는 캐시와 DB 기록을 정리합니다.
        """
        if not self.current_path or not os.path.isdir(self.current_path):
            QMessageBox.information(self, "알림", "먼저 폴더를 열어주세요.")
            return

        reply = QMessageBox.question(
            self, "캐시 정리",
            "현재 폴더의 캐시를 정리하시겠습니까?\n(실제 파일이 없는 데이터와 썸네일이 삭제됩니다.)",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # 파일 시스템의 실제 파일 목록
            current_files = set()
            for root, _, files in os.walk(self.current_path):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        current_files.add(normalize_path(os.path.join(root, file)))
            
            # DB에 기록된 파일 목록
            db_files = set(self.db.get_all_paths_in_folder(self.current_path))

            # DB에는 있지만 실제 파일은 없는 '유령 데이터' 찾기
            deleted_files = list(db_files - current_files)

            if not deleted_files:
                QMessageBox.information(self, "알림", "정리할 캐시가 없습니다.")
                return

            # 유령 데이터 삭제 작업
            for path in deleted_files:
                # DB에서 레코드 삭제
                self.db.conn.execute("DELETE FROM images WHERE path=?", (path,))
                
                # 썸네일 캐시 파일 삭제
                thumb_path = get_thumb_path(path)
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except OSError as e:
                        print(f"썸네일 삭제 실패: {e}")
            
            self.db.conn.commit()
            
            QMessageBox.information(self, "완료", f"{len(deleted_files)}개의 불필요한 캐시를 정리했습니다.")

        finally:
            QApplication.restoreOverrideCursor()
            # UI를 완전히 새로고침
            self.load_images(self.current_path)

    def move_to_top(self):
        if not self.cached_paths:
            return
        # 트리뷰
        if self.view_mode == "tree":
            first_path = self.cached_paths[0]
            # 트리에서 해당 경로에 해당하는 아이템 찾아서 선택
            item = self._find_item_by_path_in_tree(first_path)
            if item:
                self.tree.setCurrentItem(item)
                self.display_image(item)
                self.tree.scrollToItem(item, QAbstractItemView.PositionAtTop)
            self.last_selected = first_path
        # 썸네일뷰
        elif self.view_mode == "thumb":
            self.thumbnail_bar.set_selected(0)
            self.thumbnail_bar.update_thumbs()
            self.last_selected = self.image_paths[0]        
            
    def edit_exif(self):
        path = self.last_selected
        if not path: return
        
        # DB에서 현재 EXIF 데이터를 가져옵니다.
        data = self.db.get_image_data(path)
        old_exif = data[0] if data else ""
        
        new_text, ok = QInputDialog.getMultiLineText(self, 'EXIF 편집', '수정된 EXIF 입력:', old_exif)
        
        if ok:
            # DB에 새로운 EXIF 데이터를 업데이트합니다.
            self.db.update_exif(path, new_text)
            self.exif_text.setPlainText(exif_for_display(new_text))
            
    def clear_exif(self):
        path = self.last_selected
        if not path: return

        # 1. DB에서 현재 EXIF 데이터를 가져와 undo 캐시에 저장
        data = self.db.get_image_data(path)
        old_exif = data[0] if data else ""
        self.exif_undo_cache[path] = old_exif

        # 2. DB의 EXIF를 비움
        self.db.update_exif(path, "")
        self.exif_text.setText("")
        
        # 3. 버튼 상태를 '되돌리기'로 즉시 변경
        self.update_exif_buttons(path)
        
    def undo_exif(self):
        path = self.last_selected
        if not path or path not in self.exif_undo_cache:
            return

        # 1. undo 캐시에서 이전 EXIF 데이터를 가져오고 캐시에서 제거
        previous_exif = self.exif_undo_cache.pop(path)

        # 2. DB에 이전 EXIF 데이터 복원
        self.db.update_exif(path, previous_exif)
        self.exif_text.setPlainText(exif_for_display(previous_exif))
        
        # 3. 버튼 상태를 '지우기'로 즉시 변경
        self.update_exif_buttons(path)    

    def update_exif_buttons(self, path):
        """선택된 파일에 따라 EXIF 지우기/되돌리기 버튼의 상태를 업데이트합니다."""
        if not path: return
        
        # 기존 연결을 끊어 중복 연결 방지
        try:
            self.btn_exif_clear_undo.clicked.disconnect()
        except TypeError:
            pass # 연결이 없는 경우 무시

        if path in self.exif_undo_cache:
            self.btn_exif_clear_undo.setText("EXIF 되돌리기")
            self.btn_exif_clear_undo.clicked.connect(self.undo_exif)
        else:
            self.btn_exif_clear_undo.setText("EXIF 지우기")
            self.btn_exif_clear_undo.clicked.connect(self.clear_exif)        

    # --- 우클릭 메뉴 (트리/썸네일 동일) ---
    def open_tree_context(self, pos):
        item = self.tree.itemAt(pos)
        if not item: return
        
        path = item.data(0, Qt.UserRole)
        self.show_context_menu_for_path(path)
        
    def open_thumb_bar_context(self, pos):
        clicked_thumb_index = -1
        for i, thumb_box in enumerate(self.thumbnail_bar.thumbs):
            if thumb_box.geometry().contains(pos):
                clicked_thumb_index = self.thumbnail_bar.start_index + i
                break

        if clicked_thumb_index == -1 or clicked_thumb_index >= len(self.thumbnail_bar.images):
            return

        path = self.thumbnail_bar.images[clicked_thumb_index]
        self.show_context_menu_for_path(path)
        
    def show_context_menu_for_path(self, path):
        """주어진 경로(path)에 대한 공통 우클릭 메뉴를 생성하고 표시합니다."""
        if not path or not os.path.isfile(path):
            return

        menu = QMenu(self)
        menu.addAction("파일 위치 열기", lambda: self.open_file_location(path))
        menu.addSeparator() 
        menu.addAction("이름변경", lambda: self.rename_image(path))
        ext_menu = menu.addMenu("확장자변경")
        for ext in ['.png','.jpg','.jpeg','.webp']:
            ext_menu.addAction(ext.upper(), lambda _, e=ext: self.convert_image(path, e))

        data = self.db.get_image_data(path)
        is_favorite = data[1] if data else 0

        if not is_favorite:
            menu.addAction("+FAV", lambda: self.toggle_fav_from_path(path))
        else:
            menu.addAction("즐겨찾기 해제", lambda: self.toggle_fav_from_path(path))

        # 전역 마우스 커서 위치에 메뉴를 표시
        menu.exec_(QCursor.pos())

    def open_file_location(self, path):
        """주어진 경로의 파일을 시스템 탐색기에서 열고 선택합니다."""
        if not os.path.exists(path):
            QMessageBox.warning(self, "오류", "파일을 찾을 수 없습니다.")
            return
        
        if sys.platform == "win32":
            # 윈도우에서는 explorer의 /select 옵션을 사용해 파일을 바로 선택
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        elif sys.platform == "darwin": # macOS
            subprocess.Popen(['open', '-R', path])
        else: # Linux 등
            folder_path = os.path.dirname(path)
            subprocess.Popen(['xdg-open', folder_path])
            
    def rename_image(self, path):
        base = os.path.basename(path)
        name, ext = os.path.splitext(base)
        new_name, ok = QInputDialog.getText(self, "이름 변경", "새 파일명:", text=name)
        
        if ok and new_name and new_name != name:
            new_path = os.path.join(os.path.dirname(path), new_name + ext)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "중복", "동일 이름의 파일이 이미 존재합니다!")
                return
            
            # DB에서 이전 데이터 가져오기
            data = self.db.get_image_data(path)
            
            # 1. 파일 시스템에서 이름 변경
            os.rename(path, new_path)
            
            # 2. DB 업데이트 (이전 경로 삭제, 새 경로로 데이터 추가)
            if data:
                self.db.conn.execute("DELETE FROM images WHERE path=?", (path,))
                self.db.conn.execute("""
                    INSERT INTO images (path, exif, is_favorite, pending_command, pending_delete)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_path, data[0], data[1], data[2], data[3]))
                self.db.conn.commit()

            # 3. 내부 데이터 모델(image_paths) 업데이트
            self.image_paths[self.image_paths.index(path)] = new_path
            self.last_selected = new_path
            
            # 4. UI 갱신 (전체 새로고침)
            self.refresh_views()

    def rename_favorite_path(self, old_path, new_path):
        """즐겨찾기 창에서 요청된 파일명 변경을 처리하고 모든 UI를 동기화합니다."""
        print(f"이름 변경: {old_path} -> {new_path}")
        # 1. 실제 파일 이름 변경
        try:
            os.rename(old_path, new_path)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일명 변경에 실패했습니다: {e}")
            return

        # 2. DB 업데이트
        data = self.db.get_image_data(old_path)
        if data:
            self.db.conn.execute("DELETE FROM images WHERE path=?", (old_path,))
            self.db.conn.execute("""
                INSERT INTO images (path, exif, is_favorite, pending_command, pending_delete)
                VALUES (?, ?, ?, ?, ?)
            """, (new_path, data[0], data[1], data[2], data[3]))
            self.db.conn.commit()

        # 3. 메인창의 내부 데이터 모델 업데이트
        if old_path in self.image_paths:
            self.image_paths[self.image_paths.index(old_path)] = new_path
        if self.last_selected == old_path:
            self.last_selected = new_path

        # 4. 메인창 UI 새로고침 (트리/썸네일)
        self.refresh_views()
        
        # 5. 열려있는 즐겨찾기 창도 새로고침
        if hasattr(self, 'fav_win') and self.fav_win.isVisible():
            self.fav_win.load_favorites()
            
    def convert_image(self, path, ext):
        dirname, old_filename = os.path.dirname(path), os.path.basename(path)
        name, old_ext = os.path.splitext(old_filename)
        if old_ext.lower() == ext.lower():
            QMessageBox.information(self, "확장자 변경", "이미 같은 확장자입니다.")
            return
        new_path = os.path.join(dirname, name + ext)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "확장자 변경", "동일 이름의 파일이 이미 존재합니다.")
            return
        try:
            img = Image.open(path)
            img.save(new_path)
            # EXIF 복사(PNG만)
            if path in self.exif_cache and ext.lower() == ".png":
                meta = PngImagePlugin.PngInfo()
                for line in self.exif_cache[path].split('\n'):
                    if ': ' in line:
                        k, v = line.split(': ', 1)
                        meta.add_text(k, v)
                img = Image.open(new_path)
                img.save(new_path, pnginfo=meta)
            self.cached_paths[self.cached_paths.index(path)] = new_path
            self.thumb_cache[new_path] = self.thumb_cache.pop(path,"")
            self.exif_cache[new_path] = self.exif_cache.pop(path,"")
            for s in [self.fav_set, self.pending_delete, self.pending_command]:
                if path in s: 
                    s.remove(path)
                    s.add(new_path)
            reply = QMessageBox.question(self, "원본 삭제?", f"{path} 삭제할까요?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes: 
                os.remove(path)
            self.last_selected = new_path
            self.populate_tree()
            self.populate_thumbs()
        except Exception as e:
            QMessageBox.critical(self, "확장자 변경 오류", f"실패: {e}")

    # --- 단축키/키보드 이벤트 ---
    def keyPressEvent(self, event):
        """Shift 키가 눌렸을 때 버튼 색상 변경"""
        if event.key() == Qt.Key_Shift and self.view_mode == "thumb":
            self.thumbnail_bar.set_shift_mode(True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Shift 키를 떼었을 때 버튼 색상 복원"""
        if event.key() == Qt.Key_Shift and self.view_mode == "thumb":
            self.thumbnail_bar.set_shift_mode(False)
        super().keyReleaseEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = QApplication.keyboardModifiers()

            # --- 썸네일 뷰 키보드 이동 ---
            if self.view_mode == "thumb" and key in (Qt.Key_Up, Qt.Key_Down):
                if modifiers == Qt.ShiftModifier:
                    if key == Qt.Key_Up: self.thumbnail_bar.move_to_top()
                    else: self.thumbnail_bar.move_down_fast()
                else:
                    if key == Qt.Key_Up: self.thumbnail_bar.move_up()
                    else: self.thumbnail_bar.move_down()
                return True

            # --- 기타 단축키 ---
            if key == Qt.Key_Delete and self.delete_mode:
                self._toggle_item_status("delete")
                return True

            if key == Qt.Key_Control:
                self._toggle_item_status("command")
                return True
            
            if self.view_mode == "tree" and self._is_flat_tree and key in (Qt.Key_Up, Qt.Key_Down):
                paths = self._flat_paths
                if not paths: return True
                idx = paths.index(self.last_selected) if self.last_selected in paths else 0
                if key == Qt.Key_Up and idx > 0: idx -= 1
                elif key == Qt.Key_Down and idx < len(paths) - 1: idx += 1
                
                path = paths[idx]
                item = self.tree.topLevelItem(idx)
                if item:
                    self.tree.setCurrentItem(item)
                    self.last_selected = path
                    self.display_image(item)
                return True

        return super().eventFilter(obj, event)

    def _toggle_item_status(self, status_type):
        if self.last_selected:
            field_map = {'command': 'pending_command', 'delete': 'pending_delete'}
            if status_type in field_map:
                self.db.toggle_status(self.last_selected, field_map[status_type])
                self._update_item_display(self.last_selected)
    
    def _tree_item_to_path(self, item):
        names = []
        while item: 
            names.insert(0, item.text(0).replace("✎","").replace("🗑","").replace("🌠","").strip())
            item=item.parent()
        return os.path.join(self.current_path, *names)
        
    def _tree_find_item(self, idx):
        # 현재 트리의 idx번째 leaf 아이템 반환
        stack, result = [], []
        for i in range(self.tree.topLevelItemCount()):
            stack.append(self.tree.topLevelItem(i))
        while stack:
            node = stack.pop(0)
            if node.childCount()==0: 
                result.append(node)
            else: 
                stack=[node.child(j) for j in range(node.childCount())]+stack
        return result[idx] if 0<=idx<len(result) else None

    # --- EXIF 검색 ---
    def search_exif(self, keyword):
        keyword = keyword.lower().strip()
        keywords = [kw.strip() for kw in keyword.split(',') if kw.strip()]
        
        if not keywords:
            self._is_flat_tree = False
            self._flat_paths = []
            self.refresh_views()
            return

        # ✅ 검색 시 현재 폴더 경로(self.current_path)를 함께 전달
        matched = self.db.search_exif(keywords, self.current_path)
        
        self._is_flat_tree = True
        self._flat_paths = sorted(matched)
        self.refresh_views()   

    def show_flat_tree(self, paths):
        self.tree.clear()
        for i, path in enumerate(paths):
            filename = os.path.basename(path)
            icons, font, color = self._get_status_icons_and_style(path)
            label = (icons + " " if icons else "") + filename
            item = QTreeWidgetItem([label])
            item.setFont(0, font)
            item.setForeground(0, QBrush(color))
            item.setData(0, Qt.UserRole, path)  # 반드시!
            self.tree.addTopLevelItem(item)
    
    # --- 설정/상태 저장 & 로드 ---
    def save_config(self):
        config = {
            'path': self.current_path,
            'splitter': self.splitter.saveState().data().hex(),
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False)
        QMessageBox.information(self, "현재 설정 저장", "현재 설정 저장 완료!")    
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.current_path = config.get('path', '')
            splitter_state = config.get('splitter')
            if splitter_state:
                try:
                    self.splitter.restoreState(bytes.fromhex(splitter_state))
                except Exception as e:
                    print(f"splitter 상태 복원 실패: {e}")
                           
    # --- 즐겨찾기 창 ---
    def show_favorites(self):
        # 새롭게 디자인된 FavoritesWindow를 부모(self) 정보만 넘겨서 생성합니다.
        # 창이 내부적으로 데이터를 로드합니다.
        if not hasattr(self, 'fav_win') or not self.fav_win.isVisible():
            self.fav_win = FavoritesWindow(parent=self)
            self.fav_win.show()
            self.fav_win.raise_()
        else:
             self.fav_win.raise_() # 이미 열려있으면 맨 앞으로 가져오기
        
    def select_image(self, image_path):
        """외부에서 특정 이미지를 선택하도록 요청받는 메서드."""
        target_path = normalize_path(image_path)
        target_dir = normalize_path(os.path.dirname(target_path))

        self.pending_selection = target_path

        # 만약 현재 보고 있는 폴더와 다르면, 해당 폴더를 새로 로드
        if self.current_path != target_dir:
            self.load_images(target_dir)
        # 같은 폴더에 있다면, 바로 선택 실행
        else:
            self._perform_selection()

    def _perform_selection(self):
        """self.last_selected에 저장된 경로의 아이템을 실제로 선택합니다."""
        target_path = self.last_selected
        if not target_path:
            return

        if self.view_mode == "thumb":
            # self.thumbnail_bar.images가 현재 표시중인 목록입니다.
            image_list = self.thumbnail_bar.images
            if target_path in image_list:
                index = image_list.index(target_path)
                self.thumbnail_bar.set_selected(index)
        
        elif self.view_mode == "tree":
            item_to_select = self._find_item_by_path_in_tree(target_path)
            if item_to_select:
                self.tree.setCurrentItem(item_to_select)
                self.tree.scrollToItem(item_to_select, QAbstractItemView.PositionAtCenter)

    def batch_populate_tree(self, batch_size=500):
        # 전체 아이템 리스트를 만든 뒤 QTimer로 batch 추가
        if not hasattr(self, '_tree_batch_items'):
            # 첫 호출 시: 전체 경로 저장
            self._tree_batch_items = list(self.cached_paths)
            self.tree.clear()
            self._tree_batch_idx = 0

        def add_batch():
            count = 0
            while (self._tree_batch_idx < len(self._tree_batch_items)) and (count < batch_size):
                path = self._tree_batch_items[self._tree_batch_idx]
                rel = os.path.relpath(path, self.current_path)
                parts = rel.split(os.sep)
                parent = self.tree
                path_acc = self.current_path
                for i, part in enumerate(parts):
                    path_acc = os.path.join(path_acc, part)
                    found = None
                    items = [parent.topLevelItem(j) if isinstance(parent, QTreeWidget) else parent.child(j)
                            for j in range(parent.topLevelItemCount() if isinstance(parent, QTreeWidget) else parent.childCount())]
                    for item in items:
                        item_part = item.text(0)
                        for emo in ["✎", "🗑", "🌠"]:
                            item_part = item_part.replace(emo, "")
                        if item_part.strip() == part:
                            found = item
                            break
                    if not found:
                        if i == len(parts)-1:
                            icons, font, color = self._get_status_icons_and_style(path_acc)
                            label = (icons + " " if icons else "") + part
                        else:
                            label = part
                            font = QFont()
                            color = QColor("#ddd")
                        item = QTreeWidgetItem([label])
                        item.setFont(0, font)
                        item.setForeground(0, QBrush(color))
                        if isinstance(parent, QTreeWidget):
                            parent.addTopLevelItem(item)
                        else:
                            parent.addChild(item)
                        found = item
                    if i == len(parts)-1:
                        icons, font, color = self._get_status_icons_and_style(path_acc)
                        found.setText(0, (icons + " " if icons else "") + part)
                        found.setFont(0, font)
                        found.setForeground(0, QBrush(color))
                    parent = found
                self._tree_batch_idx += 1
                count += 1

            # 더 남았으면 다음 batch 예약
            if self._tree_batch_idx < len(self._tree_batch_items):
                QTimer.singleShot(1, add_batch)
            else:
                # cleanup
                del self._tree_batch_items
                del self._tree_batch_idx

        add_batch()        

    def _tree_find_item(self, idx):
        # flat 트리(검색) 모드
        if self._is_flat_tree:
            if 0 <= idx < self.tree.topLevelItemCount():
                return self.tree.topLevelItem(idx)
                self.tree.setUpdatesEnabled(True)
            return None
        # 기존 트리
        stack, result = [], []
        for i in range(self.tree.topLevelItemCount()):
            stack.append(self.tree.topLevelItem(i))
        while stack:
            node = stack.pop(0)
            if node.childCount() == 0:
                result.append(node)
            else:
                stack = [node.child(j) for j in range(node.childCount())] + stack
        return result[idx] if 0 <= idx < len(result) else None

# ---------- 실행 ----------
if __name__ == '__main__':
    # 고해상도 디스플레이 지원을 위한 속성 설정
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyleSheet("""
    QWidget {background-color: #232323; color: #ddd;}
    QPushButton, QLineEdit, QTextEdit, QListWidget {
        background-color: #2d2d30;
        border: 1px solid #3e3e42;
        border-radius: 4px;
        color: white;
    }
    QPushButton:hover {
        background-color: #38383f;
    }
    QLabel {color: #ddd;}
    QCheckBox {padding: 4px;}
    QMenu {background-color: #2d2d30; color: white;}

    /* --- 선택 효과를 명확히 추가 --- */
    QTreeWidget::item:selected, QTreeView::item:selected {
        background: #385078;         /* 원하는 색상 */
        color: #ffe066;              /* 선택시 글자색 */
        border: 1px solid #41B0FF;   /* 선택 라인 강조 */
    }

    QTreeWidget::item:hover, QTreeView::item:hover {
        background: #34475a;
    }

    QTreeWidget, QTreeView {
        selection-background-color: #385078;
        selection-color: #ffe066;
    }
    """)
    win = PhotoManager()
    win.show()
    app.exec_()
# widgets/folder_organizer.py
"""이미지 폴더 정리 도구"""
import os
import hashlib
import shutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QProgressBar, QMessageBox,
    QTabWidget, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.database import normalize_path


class HashScanWorker(QThread):
    """이미지 해시 계산 워커"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, db, folder: str):
        super().__init__()
        self._db = db
        self._folder = folder

    def run(self):
        norm_folder = normalize_path(self._folder)
        paths = self._db.get_all_paths_in_folder(norm_folder)
        total = len(paths)

        for i, norm_path in enumerate(paths):
            if i % 20 == 0:
                self.progress.emit(i, total)

            # 원본 경로 복원
            try:
                from pathlib import Path
                real_path = str(Path(norm_path))
                if not os.path.exists(real_path):
                    # Windows 경로 시도
                    real_path = norm_path.replace('/', '\\')
                    if real_path.startswith('\\'):
                        real_path = real_path[1:]  # leading slash 제거
                if not os.path.exists(real_path):
                    continue

                with open(real_path, 'rb') as f:
                    data = f.read()
                h = hashlib.md5(data).hexdigest()
                self._db.update_image_hash(norm_path, h)
            except Exception:
                continue

        self.finished.emit()


class FolderOrganizerDialog(QDialog):
    """폴더 정리 도구 다이얼로그"""

    def __init__(self, db, folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("폴더 정리 도구")
        self.setMinimumSize(600, 500)
        self.resize(700, 600)
        self.setStyleSheet("background-color: #1E1E1E; color: #EEE;")

        self._db = db
        self._folder = folder
        self._worker: HashScanWorker | None = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel("🗂️ 폴더 정리 도구")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #E67E22;")
        layout.addWidget(header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2C2C2C; border: 1px solid #555;
                border-radius: 4px; text-align: center; color: #AAA; font-size: 11px;
            }
            QProgressBar::chunk { background-color: #E67E22; border-radius: 3px; }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # 탭
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; background: #1E1E1E; }
            QTabBar::tab { background: #252525; color: #888; padding: 8px 16px; }
            QTabBar::tab:selected { background: #333; color: #E0E0E0; border-bottom: 2px solid #E67E22; }
        """)

        # 중복 탭
        dup_tab = QWidget()
        dup_layout = QVBoxLayout(dup_tab)

        btn_scan = QPushButton("🔍 중복 스캔")
        btn_scan.setFixedHeight(35)
        btn_scan.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        btn_scan.clicked.connect(self._start_scan)
        dup_layout.addWidget(btn_scan)

        self.dup_list = QListWidget()
        self.dup_list.setStyleSheet(
            "QListWidget { background-color: #252525; border: 1px solid #444; border-radius: 4px; }"
            "QListWidget::item { padding: 4px; }"
            "QListWidget::item:selected { background-color: #5865F2; }"
        )
        dup_layout.addWidget(self.dup_list, stretch=1)

        self.dup_status = QLabel("")
        self.dup_status.setStyleSheet("color: #888; font-size: 11px;")
        dup_layout.addWidget(self.dup_status)

        btn_delete_dups = QPushButton("🗑️ 선택 그룹의 중복 삭제 (첫 번째 유지)")
        btn_delete_dups.setFixedHeight(35)
        btn_delete_dups.setStyleSheet(
            "background-color: #E74C3C; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        btn_delete_dups.clicked.connect(self._delete_selected_duplicates)
        dup_layout.addWidget(btn_delete_dups)

        tabs.addTab(dup_tab, "중복 검색")

        # 즐겨찾기 복사 탭
        fav_tab = QWidget()
        fav_layout = QVBoxLayout(fav_tab)

        fav_label = QLabel("즐겨찾기 이미지를 별도 폴더로 복사합니다.")
        fav_label.setStyleSheet("color: #AAA; font-size: 12px;")
        fav_layout.addWidget(fav_label)

        btn_copy_favs = QPushButton("⭐ 즐겨찾기 이미지 복사")
        btn_copy_favs.setFixedHeight(40)
        btn_copy_favs.setStyleSheet(
            "background-color: #FFC107; color: #1E1E1E; border-radius: 4px; "
            "font-size: 14px; font-weight: bold;"
        )
        btn_copy_favs.clicked.connect(self._copy_favorites)
        fav_layout.addWidget(btn_copy_favs)

        self.fav_status = QLabel("")
        self.fav_status.setStyleSheet("color: #888; font-size: 12px;")
        fav_layout.addWidget(self.fav_status)
        fav_layout.addStretch()

        tabs.addTab(fav_tab, "즐겨찾기 정리")

        layout.addWidget(tabs, stretch=1)

        btn_close = QPushButton("닫기")
        btn_close.setFixedHeight(35)
        btn_close.setStyleSheet(
            "background-color: #333; color: #AAA; border-radius: 4px; font-size: 13px;"
        )
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def _start_scan(self):
        """해시 스캔 시작"""
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self.dup_status.setText("해시 계산 중...")

        self._worker = HashScanWorker(self._db, self._folder)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.start()

    def _on_scan_progress(self, current: int, total: int):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)

    def _on_scan_finished(self):
        self.progress_bar.hide()
        norm_folder = normalize_path(self._folder)
        dups = self._db.find_duplicates_in_folder(norm_folder)

        self.dup_list.clear()
        total_dup_count = 0
        for hash_val, paths in dups:
            total_dup_count += len(paths) - 1
            group_text = f"[{hash_val[:8]}] {len(paths)}개 — " + ", ".join(
                os.path.basename(p) for p in paths[:3]
            )
            if len(paths) > 3:
                group_text += f" 외 {len(paths) - 3}개"
            item = QListWidgetItem(group_text)
            item.setData(Qt.ItemDataRole.UserRole, paths)
            self.dup_list.addItem(item)

        self.dup_status.setText(
            f"중복 그룹: {len(dups)}개, 삭제 가능: {total_dup_count}개"
        )

    def _delete_selected_duplicates(self):
        """선택된 중복 그룹에서 첫 번째를 제외한 나머지 삭제"""
        item = self.dup_list.currentItem()
        if not item:
            QMessageBox.information(self, "알림", "삭제할 중복 그룹을 선택하세요.")
            return

        paths = item.data(Qt.ItemDataRole.UserRole)
        if not paths or len(paths) < 2:
            return

        reply = QMessageBox.question(
            self, "확인",
            f"{len(paths) - 1}개의 중복 파일을 휴지통으로 이동합니까?\n"
            f"유지: {os.path.basename(paths[0])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        for p in paths[1:]:
            try:
                # 경로 복원
                real = p.replace('/', os.sep)
                if real.startswith(os.sep) and os.name == 'nt':
                    real = real[1:]
                if os.path.exists(real):
                    try:
                        from core.image_utils import move_to_trash
                        move_to_trash(real)
                    except Exception:
                        os.remove(real)
                    deleted += 1
            except Exception:
                continue

        QMessageBox.information(self, "완료", f"{deleted}개 파일 삭제됨")
        # 목록에서 제거
        row = self.dup_list.row(item)
        self.dup_list.takeItem(row)

    def _copy_favorites(self):
        """즐겨찾기 이미지를 별도 폴더로 복사"""
        fav_dir = os.path.join(self._folder, "_favorites")
        os.makedirs(fav_dir, exist_ok=True)

        favorites = self._db.get_all_favorites()
        norm_folder = normalize_path(self._folder)

        copied = 0
        for fav_path in favorites:
            if not fav_path.startswith(norm_folder):
                continue
            # 경로 복원
            real = fav_path.replace('/', os.sep)
            if real.startswith(os.sep) and os.name == 'nt':
                real = real[1:]
            if not os.path.exists(real):
                continue
            dest = os.path.join(fav_dir, os.path.basename(real))
            if os.path.exists(dest):
                continue
            try:
                shutil.copy2(real, dest)
                copied += 1
            except Exception:
                continue

        self.fav_status.setText(f"✅ {copied}개 파일을 {fav_dir}로 복사했습니다.")

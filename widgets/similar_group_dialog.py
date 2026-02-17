# widgets/similar_group_dialog.py
"""유사 이미지 그룹핑 다이얼로그"""
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QProgressBar, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap


def _dhash(image_path: str, hash_size: int = 16) -> int | None:
    """Difference Hash (dHash) 계산"""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        resized = cv2.resize(img, (hash_size + 1, hash_size))
        diff = resized[:, 1:] > resized[:, :-1]
        return int.from_bytes(np.packbits(diff.flatten()).tobytes(), byteorder='big')
    except Exception:
        return None


def _hamming(h1: int, h2: int) -> int:
    """해밍 거리 계산"""
    return bin(h1 ^ h2).count('1')


class HashWorker(QThread):
    """이미지 해시 계산 워커"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)  # [(path, hash), ...]

    def __init__(self, paths: list[str]):
        super().__init__()
        self._paths = paths

    def run(self):
        results = []
        total = len(self._paths)
        for i, path in enumerate(self._paths):
            if i % 5 == 0:
                self.progress.emit(i, total)
            h = _dhash(path)
            if h is not None:
                results.append((path, h))
        self.finished.emit(results)


_STYLE = """
QDialog { background-color: #1E1E1E; color: #DDD; }
QLabel { color: #CCC; }
QProgressBar {
    background-color: #2C2C2C; border: 1px solid #444;
    border-radius: 4px; text-align: center; color: #AAA;
}
QProgressBar::chunk { background-color: #5865F2; border-radius: 3px; }
"""


class SimilarGroupDialog(QDialog):
    """유사 이미지 그룹핑"""

    def __init__(self, image_paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("유사 이미지 그룹")
        self.setMinimumSize(800, 600)
        self.resize(900, 650)
        self.setStyleSheet(_STYLE)

        self._paths = image_paths
        self._hashes: list[tuple[str, int]] = []
        self._worker: HashWorker | None = None
        self._init_ui()
        self._start_hash()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("유사 이미지 그룹")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #EEE;")
        root.addWidget(title)

        # 유사도 임계값 슬라이더
        thresh_row = QHBoxLayout()
        thresh_row.addWidget(QLabel("유사도 임계값:"))
        self._slider_thresh = QSlider(Qt.Orientation.Horizontal)
        self._slider_thresh.setRange(1, 30)
        self._slider_thresh.setValue(10)
        self._slider_thresh.setFixedWidth(200)
        thresh_row.addWidget(self._slider_thresh)
        self._thresh_label = QLabel("10")
        self._thresh_label.setFixedWidth(30)
        self._thresh_label.setStyleSheet("color: #5865F2; font-weight: bold;")
        thresh_row.addWidget(self._thresh_label)
        self._slider_thresh.valueChanged.connect(
            lambda v: self._thresh_label.setText(str(v))
        )

        btn_regroup = QPushButton("다시 그룹핑")
        btn_regroup.setFixedHeight(28)
        btn_regroup.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-weight: bold; padding: 0 12px;"
        )
        btn_regroup.clicked.connect(self._run_grouping)
        thresh_row.addWidget(btn_regroup)
        thresh_row.addStretch()
        root.addLayout(thresh_row)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(18)
        root.addWidget(self._progress)

        # 결과 영역
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")
        self._result_container = QWidget()
        self._result_layout = QVBoxLayout(self._result_container)
        self._result_layout.setContentsMargins(4, 4, 4, 4)
        self._result_layout.setSpacing(10)
        self._result_layout.addStretch()
        self._scroll.setWidget(self._result_container)
        root.addWidget(self._scroll, 1)

        # 닫기
        btn_close = QPushButton("닫기")
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet(
            "background-color: #444; color: #DDD; border-radius: 6px; font-weight: bold;"
        )
        btn_close.clicked.connect(self.reject)
        root.addWidget(btn_close)

    def _start_hash(self):
        self._progress.setRange(0, len(self._paths))
        self._worker = HashWorker(self._paths)
        self._worker.progress.connect(lambda i, t: self._progress.setValue(i))
        self._worker.finished.connect(self._on_hash_done)
        self._worker.start()

    def _on_hash_done(self, results: list):
        self._hashes = results
        self._progress.hide()
        self._run_grouping()

    def _run_grouping(self):
        """해밍 거리 기반 그룹핑"""
        threshold = self._slider_thresh.value()
        n = len(self._hashes)
        visited = [False] * n
        groups: list[list[str]] = []

        for i in range(n):
            if visited[i]:
                continue
            group = [self._hashes[i][0]]
            visited[i] = True
            for j in range(i + 1, n):
                if visited[j]:
                    continue
                dist = _hamming(self._hashes[i][1], self._hashes[j][1])
                if dist <= threshold:
                    group.append(self._hashes[j][0])
                    visited[j] = True
            if len(group) >= 2:
                groups.append(group)

        self._display_groups(groups)

    def _display_groups(self, groups: list[list[str]]):
        """그룹 결과 표시"""
        # 기존 위젯 제거
        while self._result_layout.count() > 1:
            item = self._result_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not groups:
            lbl = QLabel("유사한 이미지 그룹이 없습니다.")
            lbl.setStyleSheet("color: #888; font-size: 14px; padding: 20px;")
            self._result_layout.insertWidget(0, lbl)
            return

        for gi, group in enumerate(groups):
            frame = QWidget()
            frame.setStyleSheet(
                "background-color: #252525; border-radius: 6px; padding: 4px;"
            )
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 8, 8, 8)
            fl.setSpacing(4)

            header = QLabel(f"그룹 {gi+1} ({len(group)}장)")
            header.setStyleSheet("color: #5865F2; font-weight: bold; font-size: 13px;")
            fl.addWidget(header)

            row = QHBoxLayout()
            row.setSpacing(6)
            for path in group[:10]:  # 최대 10장
                thumb = QLabel()
                thumb.setFixedSize(100, 100)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb.setStyleSheet("background-color: #1A1A1A; border-radius: 4px;")
                pix = QPixmap(path)
                if not pix.isNull():
                    thumb.setPixmap(pix.scaled(
                        96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    ))
                thumb.setToolTip(os.path.basename(path))
                row.addWidget(thumb)
            if len(group) > 10:
                more = QLabel(f"+{len(group) - 10}장")
                more.setStyleSheet("color: #888;")
                row.addWidget(more)
            row.addStretch()
            fl.addLayout(row)

            self._result_layout.insertWidget(self._result_layout.count() - 1, frame)

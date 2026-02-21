# widgets/similar_group_dialog.py
"""유사 이미지 그룹핑 다이얼로그 — dHash + EXIF 메타데이터 비교"""
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QProgressBar, QSlider, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from utils.theme_manager import get_color


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


def _extract_prompt(image_path: str) -> str:
    """이미지에서 프롬프트 텍스트 추출 (PNG parameters / EXIF)"""
    try:
        from PIL import Image
        img = Image.open(image_path)
        # PNG text chunks
        if hasattr(img, 'text'):
            params = img.text.get('parameters', '')
            if params:
                # 첫 줄이 프롬프트 (Negative prompt: 앞까지)
                lines = params.split('\n')
                prompt_parts = []
                for line in lines:
                    if line.startswith('Negative prompt:') or line.startswith('Steps:'):
                        break
                    prompt_parts.append(line)
                return ' '.join(prompt_parts).strip()
        # EXIF UserComment
        exif = img.getexif()
        if exif:
            user_comment = exif.get(0x9286, '')  # UserComment tag
            if isinstance(user_comment, bytes):
                user_comment = user_comment.decode('utf-8', errors='ignore')
            if user_comment:
                return user_comment[:500]
    except Exception:
        pass
    return ''


def _prompt_similarity(p1: str, p2: str) -> float:
    """두 프롬프트의 Jaccard 유사도 (0~1)"""
    if not p1 or not p2:
        return 0.0
    # 태그 단위 분리 (쉼표 + 공백)
    tokens1 = set(t.strip().lower() for t in p1.replace(',', ' ').split() if t.strip())
    tokens2 = set(t.strip().lower() for t in p2.replace(',', ' ').split() if t.strip())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


class HashWorker(QThread):
    """이미지 해시 + 메타데이터 계산 워커"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)  # [(path, hash, prompt), ...]

    def __init__(self, paths: list[str], extract_meta: bool = False):
        super().__init__()
        self._paths = paths
        self._extract_meta = extract_meta

    def run(self):
        results = []
        total = len(self._paths)
        for i, path in enumerate(self._paths):
            if i % 5 == 0:
                self.progress.emit(i, total)
            h = _dhash(path)
            if h is not None:
                prompt = _extract_prompt(path) if self._extract_meta else ''
                results.append((path, h, prompt))
        self.finished.emit(results)


def _get_style():
    return f"""
QDialog {{ background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')}; }}
QLabel {{ color: {get_color('text_primary')}; }}
QProgressBar {{
    background-color: {get_color('bg_tertiary')}; border: 1px solid {get_color('border')};
    border-radius: 4px; text-align: center; color: {get_color('text_secondary')};
}}
QProgressBar::chunk {{ background-color: {get_color('accent')}; border-radius: 3px; }}
"""


class SimilarGroupDialog(QDialog):
    """유사 이미지 그룹핑 — 시각 유사도 + 메타데이터 비교"""

    def __init__(self, image_paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("유사 이미지 그룹")
        self.setMinimumSize(800, 600)
        self.resize(900, 650)
        self.setStyleSheet(_get_style())

        self._paths = image_paths
        self._hashes: list[tuple[str, int, str]] = []  # (path, hash, prompt)
        self._worker: HashWorker | None = None
        self._init_ui()
        self._start_hash()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("유사 이미지 그룹")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {get_color('text_primary')};")
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

        # EXIF 비교 토글
        self._chk_exif = QCheckBox("메타데이터(프롬프트) 비교")
        self._chk_exif.setChecked(True)
        self._chk_exif.setStyleSheet(
            "QCheckBox { color: #FFA726; font-weight: bold; font-size: 12px; }"
        )
        self._chk_exif.setToolTip(
            "활성화 시 이미지의 프롬프트 메타데이터도 비교하여\n"
            "같은 프롬프트로 생성된 이미지끼리 더 잘 묶입니다"
        )
        thresh_row.addWidget(self._chk_exif)

        btn_regroup = QPushButton("다시 그룹핑")
        btn_regroup.setFixedHeight(28)
        btn_regroup.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-weight: bold; padding: 0 12px;"
        )
        btn_regroup.clicked.connect(self._on_regroup_clicked)
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
            f"background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; border-radius: 6px; font-weight: bold;"
        )
        btn_close.clicked.connect(self.reject)
        root.addWidget(btn_close)

    def _start_hash(self):
        self._progress.setRange(0, len(self._paths))
        self._progress.show()
        self._worker = HashWorker(self._paths, extract_meta=True)
        self._worker.progress.connect(lambda i, t: self._progress.setValue(i))
        self._worker.finished.connect(self._on_hash_done)
        self._worker.start()

    def _on_hash_done(self, results: list):
        self._hashes = results
        self._progress.hide()
        self._run_grouping()

    def _on_regroup_clicked(self):
        """다시 그룹핑 — 메타데이터 옵션 변경 시 해시 재계산"""
        if self._hashes:
            self._run_grouping()

    def _run_grouping(self):
        """해밍 거리 + 프롬프트 유사도 기반 그룹핑"""
        threshold = self._slider_thresh.value()
        use_exif = self._chk_exif.isChecked()
        n = len(self._hashes)
        visited = [False] * n
        groups: list[list[tuple[str, str]]] = []  # [(path, reason), ...]

        for i in range(n):
            if visited[i]:
                continue
            group = [(self._hashes[i][0], "기준")]
            visited[i] = True
            for j in range(i + 1, n):
                if visited[j]:
                    continue
                # 시각 유사도
                dist = _hamming(self._hashes[i][1], self._hashes[j][1])
                is_visual_similar = dist <= threshold

                # 프롬프트 유사도
                is_prompt_similar = False
                prompt_sim = 0.0
                if use_exif and self._hashes[i][2] and self._hashes[j][2]:
                    prompt_sim = _prompt_similarity(
                        self._hashes[i][2], self._hashes[j][2]
                    )
                    # 프롬프트 유사도 70% 이상이면 유사로 판단
                    is_prompt_similar = prompt_sim >= 0.7

                if is_visual_similar and is_prompt_similar:
                    reason = f"시각+프롬프트 (거리:{dist}, 유사:{prompt_sim:.0%})"
                    group.append((self._hashes[j][0], reason))
                    visited[j] = True
                elif is_visual_similar:
                    reason = f"시각 유사 (거리:{dist})"
                    group.append((self._hashes[j][0], reason))
                    visited[j] = True
                elif is_prompt_similar:
                    # 프롬프트만 유사한 경우 — 시각 거리가 많이 다르면 묶지 않음
                    # 시각 거리 임계값의 2배 이내일 때만 프롬프트 유사도로 묶음
                    if dist <= threshold * 2:
                        reason = f"프롬프트 유사 ({prompt_sim:.0%}, 거리:{dist})"
                        group.append((self._hashes[j][0], reason))
                        visited[j] = True

            if len(group) >= 2:
                groups.append(group)

        self._display_groups(groups)

    def _display_groups(self, groups: list[list[tuple[str, str]]]):
        """그룹 결과 표시"""
        # 기존 위젯 제거
        while self._result_layout.count() > 1:
            item = self._result_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not groups:
            lbl = QLabel("유사한 이미지 그룹이 없습니다.")
            lbl.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 14px; padding: 20px;")
            self._result_layout.insertWidget(0, lbl)
            return

        for gi, group in enumerate(groups):
            frame = QWidget()
            frame.setStyleSheet(
                f"background-color: {get_color('bg_tertiary')}; border-radius: 6px; padding: 4px;"
            )
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 8, 8, 8)
            fl.setSpacing(4)

            header = QLabel(f"그룹 {gi+1} ({len(group)}장)")
            header.setStyleSheet("color: #5865F2; font-weight: bold; font-size: 13px;")
            fl.addWidget(header)

            row = QHBoxLayout()
            row.setSpacing(6)
            for path, reason in group[:10]:  # 최대 10장
                thumb = QLabel()
                thumb.setFixedSize(100, 100)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb.setStyleSheet(f"background-color: {get_color('bg_primary')}; border-radius: 4px;")
                pix = QPixmap(path)
                if not pix.isNull():
                    thumb.setPixmap(pix.scaled(
                        96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    ))
                tooltip = f"{os.path.basename(path)}\n{reason}"
                thumb.setToolTip(tooltip)
                row.addWidget(thumb)
            if len(group) > 10:
                more = QLabel(f"+{len(group) - 10}장")
                more.setStyleSheet(f"color: {get_color('text_muted')};")
                row.addWidget(more)
            row.addStretch()
            fl.addLayout(row)

            self._result_layout.insertWidget(self._result_layout.count() - 1, frame)

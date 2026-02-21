# widgets/param_diff_dialog.py
"""생성 파라미터 diff 비교 다이얼로그"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QSplitter, QWidget, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont
from PIL import Image
from utils.theme_manager import get_color


def _parse_png_params(path: str) -> dict:
    """PNG 파일에서 생성 파라미터 파싱"""
    params = {}
    try:
        img = Image.open(path)
        info_text = img.info.get("parameters", "")
        if not info_text:
            return params

        parts = info_text.split("\nNegative prompt: ")
        params["prompt"] = parts[0].strip()
        negative = ""
        params_line = ""

        if len(parts) > 1:
            sub = parts[1].split("\nSteps: ")
            negative = sub[0].strip()
            if len(sub) > 1:
                params_line = "Steps: " + sub[1].strip()
        else:
            lines = info_text.split("\n")
            prompt_lines = []
            for line in lines:
                if line.startswith("Steps: "):
                    params_line = line
                else:
                    prompt_lines.append(line)
            params["prompt"] = "\n".join(prompt_lines).strip()

        params["negative_prompt"] = negative
        if params_line:
            for item in params_line.split(", "):
                if ":" in item:
                    k, v = item.split(":", 1)
                    params[k.strip()] = v.strip()
    except Exception:
        pass
    return params


def _get_style():
    return f"""
QDialog {{ background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')}; }}
QLabel {{ color: {get_color('text_primary')}; }}
QTextEdit {{
    background-color: {get_color('bg_tertiary')}; color: {get_color('text_primary')};
    border: 1px solid {get_color('border')}; border-radius: 4px;
    font-family: Consolas, monospace; font-size: 12px;
}}
"""


class ParamDiffDialog(QDialog):
    """이미지 2장의 생성 파라미터 diff 비교"""

    def __init__(self, path_a: str = "", path_b: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("생성 파라미터 비교")
        self.setMinimumSize(900, 600)
        self.resize(1000, 650)
        self.setStyleSheet(_get_style())

        self._path_a = path_a
        self._path_b = path_b
        self._init_ui()

        if path_a:
            self._load_side("A", path_a)
        if path_b:
            self._load_side("B", path_b)
        if path_a and path_b:
            self._run_diff()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("생성 파라미터 비교")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {get_color('text_primary')};")
        root.addWidget(title)

        # 상단: 이미지 A / B 선택
        top = QHBoxLayout()
        top.setSpacing(10)

        for side in ("A", "B"):
            col = QVBoxLayout()
            col.setSpacing(4)

            btn = QPushButton(f"이미지 {side} 선택...")
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
                f"border-radius: 4px; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
            )
            btn.clicked.connect(lambda _, s=side: self._pick_image(s))

            thumb = QLabel()
            thumb.setFixedSize(120, 120)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet(f"background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')}; border-radius: 4px;")

            name_lbl = QLabel("파일 없음")
            name_lbl.setStyleSheet(f"font-size: 11px; color: {get_color('text_muted')};")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            col.addWidget(btn)
            col.addWidget(thumb, 0, Qt.AlignmentFlag.AlignCenter)
            col.addWidget(name_lbl)
            top.addLayout(col)

            if side == "A":
                self._thumb_a = thumb
                self._name_a = name_lbl
            else:
                self._thumb_b = thumb
                self._name_b = name_lbl

        root.addLayout(top)

        # diff 결과
        self._diff_text = QTextEdit()
        self._diff_text.setReadOnly(True)
        self._diff_text.setMinimumHeight(300)
        root.addWidget(self._diff_text, 1)

        # 하단 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_compare = QPushButton("비교 실행")
        btn_compare.setFixedSize(120, 36)
        btn_compare.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; border-radius: 6px; "
            "font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        btn_compare.clicked.connect(self._run_diff)
        btn_row.addWidget(btn_compare)

        btn_close = QPushButton("닫기")
        btn_close.setFixedSize(100, 36)
        btn_close.setStyleSheet(
            f"QPushButton {{ background-color: {get_color('bg_button')}; color: {get_color('text_primary')}; border-radius: 6px; "
            f"font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}"
        )
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        root.addLayout(btn_row)

    def _pick_image(self, side: str):
        path, _ = QFileDialog.getOpenFileName(
            self, f"이미지 {side} 선택", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            if side == "A":
                self._path_a = path
            else:
                self._path_b = path
            self._load_side(side, path)

    def _load_side(self, side: str, path: str):
        thumb = self._thumb_a if side == "A" else self._thumb_b
        name_lbl = self._name_a if side == "A" else self._name_b

        pix = QPixmap(path)
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(
                120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        name_lbl.setText(os.path.basename(path))

    def _run_diff(self):
        if not self._path_a or not self._path_b:
            self._diff_text.setHtml("<span style='color:#E74C3C;'>이미지 2장을 모두 선택하세요.</span>")
            return

        params_a = _parse_png_params(self._path_a)
        params_b = _parse_png_params(self._path_b)

        if not params_a and not params_b:
            self._diff_text.setHtml("<span style='color:#E74C3C;'>두 이미지 모두 생성 정보가 없습니다.</span>")
            return

        all_keys = list(dict.fromkeys(list(params_a.keys()) + list(params_b.keys())))
        lines = []

        for key in all_keys:
            val_a = params_a.get(key, "")
            val_b = params_b.get(key, "")
            if val_a == val_b:
                lines.append(
                    f"<div style='margin:2px 0; padding:4px 8px; background:{get_color('bg_tertiary')}; border-radius:4px;'>"
                    f"<b style='color:{get_color('text_muted')};'>{key}</b>: "
                    f"<span style='color:{get_color('text_secondary')};'>{_escape(val_a)}</span></div>"
                )
            else:
                lines.append(
                    f"<div style='margin:2px 0; padding:4px 8px; background:#2A1A1A; "
                    f"border-left:3px solid #E74C3C; border-radius:4px;'>"
                    f"<b style='color:#E74C3C;'>{key}</b><br>"
                    f"  <span style='color:#FF6B6B;'>A: {_escape(val_a)}</span><br>"
                    f"  <span style='color:#6BCB77;'>B: {_escape(val_b)}</span></div>"
                )

        self._diff_text.setHtml("".join(lines))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

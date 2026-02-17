# widgets/tag_weight_editor.py
"""태그 가중치 슬라이더 편집 다이얼로그"""
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSlider, QFrame
)
from PyQt6.QtCore import Qt


_STYLE = """
QDialog { background-color: #1E1E1E; color: #DDD; }
QLabel { color: #CCC; }
QSlider::groove:horizontal {
    height: 6px; background: #333; border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -4px 0;
    background: #5865F2; border-radius: 7px;
}
QSlider::sub-page:horizontal { background: #5865F2; border-radius: 3px; }
"""


def _parse_tags_with_weights(text: str) -> list[tuple[str, float]]:
    """프롬프트 텍스트에서 (태그, 가중치) 리스트 추출"""
    result = []
    parts = [t.strip() for t in text.split(",") if t.strip()]
    weight_re = re.compile(r'^\((.+?):([\d.]+)\)$')

    for part in parts:
        m = weight_re.match(part)
        if m:
            result.append((m.group(1).strip(), float(m.group(2))))
        else:
            # 괄호 레벨로 가중치 추정
            depth = 0
            inner = part
            while inner.startswith('(') and inner.endswith(')') and len(inner) > 2:
                inner = inner[1:-1]
                depth += 1
            weight = round(1.1 ** depth, 2) if depth > 0 else 1.0

            # 중괄호 (NovelAI)
            d2 = 0
            inner2 = part
            while inner2.startswith('{') and inner2.endswith('}') and len(inner2) > 2:
                inner2 = inner2[1:-1]
                d2 += 1
            if d2 > 0:
                weight = round(1.05 ** d2, 2)
                inner = inner2

            result.append((inner.strip(), weight))
    return result


def _rebuild_prompt(tags: list[tuple[str, float]]) -> str:
    """(태그, 가중치) → 프롬프트 문자열"""
    parts = []
    for tag, w in tags:
        if abs(w - 1.0) < 0.01:
            parts.append(tag)
        else:
            parts.append(f"({tag}:{w:.2f})")
    return ", ".join(parts)


class TagWeightEditorDialog(QDialog):
    """태그별 가중치 슬라이더 편집"""

    def __init__(self, prompt_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("태그 가중치 편집")
        self.setMinimumSize(600, 400)
        self.resize(650, 500)
        self.setStyleSheet(_STYLE)

        self._tags = _parse_tags_with_weights(prompt_text)
        self._sliders: list[tuple[str, QSlider, QLabel]] = []
        self._result: str | None = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("태그 가중치 편집")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #EEE;")
        root.addWidget(title)

        desc = QLabel("슬라이더로 각 태그의 가중치를 조절하세요. (0.50 ~ 2.00)")
        desc.setStyleSheet("color: #888; font-size: 12px;")
        root.addWidget(desc)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        container = QWidget()
        self._form = QVBoxLayout(container)
        self._form.setContentsMargins(4, 4, 4, 4)
        self._form.setSpacing(4)

        for tag, weight in self._tags:
            row = QHBoxLayout()
            row.setSpacing(8)

            lbl_tag = QLabel(tag)
            lbl_tag.setFixedWidth(200)
            lbl_tag.setStyleSheet("font-size: 12px; color: #DDD;")
            lbl_tag.setToolTip(tag)
            row.addWidget(lbl_tag)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(50, 200)
            slider.setValue(int(weight * 100))
            slider.setFixedHeight(20)
            row.addWidget(slider, 1)

            lbl_val = QLabel(f"{weight:.2f}")
            lbl_val.setFixedWidth(45)
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #5865F2;")
            row.addWidget(lbl_val)

            slider.valueChanged.connect(
                lambda v, l=lbl_val: l.setText(f"{v/100:.2f}")
            )

            self._form.addLayout(row)
            self._sliders.append((tag, slider, lbl_val))

        self._form.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # 버튼
        btn_row = QHBoxLayout()

        btn_reset = QPushButton("모두 1.0으로")
        btn_reset.setFixedHeight(34)
        btn_reset.setStyleSheet(
            "QPushButton { background-color: #555; color: #DDD; border-radius: 4px; "
            "font-weight: bold; }"
            "QPushButton:hover { background-color: #666; }"
        )
        btn_reset.clicked.connect(self._reset_all)
        btn_row.addWidget(btn_reset)

        btn_row.addStretch()

        btn_apply = QPushButton("적용")
        btn_apply.setFixedSize(120, 38)
        btn_apply.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; border-radius: 6px; "
            "font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(btn_apply)

        btn_close = QPushButton("취소")
        btn_close.setFixedSize(100, 38)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #444; color: #DDD; border-radius: 6px; "
            "font-weight: bold; }"
            "QPushButton:hover { background-color: #555; }"
        )
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        root.addLayout(btn_row)

    def _reset_all(self):
        for _tag, slider, lbl in self._sliders:
            slider.setValue(100)
            lbl.setText("1.00")

    def _on_apply(self):
        tags = []
        for tag, slider, _lbl in self._sliders:
            weight = slider.value() / 100.0
            tags.append((tag, weight))
        self._result = _rebuild_prompt(tags)
        self.accept()

    def get_result(self) -> str | None:
        return self._result

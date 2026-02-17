# widgets/character_feature_panel.py
"""캐릭터 특징 자동 감지 패널"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from widgets.common_widgets import FlowLayout


_TAG_CHECKED = (
    "QPushButton { background-color: #5865F2; color: white; "
    "border: none; border-radius: 10px; padding: 3px 10px; "
    "font-size: 11px; font-weight: bold; }"
    "QPushButton:hover { background-color: #6975F3; }"
)
_TAG_UNCHECKED = (
    "QPushButton { background-color: #333; color: #888; "
    "border: none; border-radius: 10px; padding: 3px 10px; "
    "font-size: 11px; text-decoration: line-through; }"
    "QPushButton:hover { background-color: #444; }"
)
_TAG_EXISTS = (
    "QPushButton { background-color: #2C2C2C; color: #555; "
    "border: 1px solid #3A3A3A; border-radius: 10px; padding: 3px 10px; "
    "font-size: 11px; }"
)


class CharacterFeaturePanel(QWidget):
    """캐릭터 특징 태그 패널 — 캐릭터 입력 아래에 표시"""

    insert_requested = pyqtSignal(list)  # [tag, tag, ...]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: list[tuple[QPushButton, str, bool]] = []  # (btn, tag, is_existing)
        self._init_ui()
        self.hide()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(4)

        # 컨텐츠 프레임
        self._frame = QFrame()
        self._frame.setStyleSheet(
            "QFrame { background-color: #1A1A1A; border-radius: 6px; }"
        )
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(8, 6, 8, 6)
        frame_layout.setSpacing(4)

        # 헤더
        header = QHBoxLayout()
        header.setSpacing(6)
        self._title_label = QLabel()
        self._title_label.setStyleSheet(
            "color: #5865F2; font-weight: bold; font-size: 12px; "
            "background: transparent;"
        )
        header.addWidget(self._title_label)
        header.addStretch()

        btn_insert = QPushButton("삽입")
        btn_insert.setFixedHeight(28)
        btn_insert.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; "
            "border-radius: 4px; font-weight: bold; font-size: 11px; "
            "padding: 0 14px; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        btn_insert.clicked.connect(self._on_insert)
        header.addWidget(btn_insert)

        btn_clear = QPushButton("X")
        btn_clear.setFixedSize(28, 28)
        btn_clear.setStyleSheet(
            "QPushButton { background-color: #444; color: #AAA; "
            "border-radius: 4px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background-color: #555; }"
        )
        btn_clear.clicked.connect(self.hide_features)
        header.addWidget(btn_clear)

        frame_layout.addLayout(header)

        # 태그 영역 (스크롤)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMaximumHeight(150)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QWidget { background: transparent; }"
        )
        self._tag_container = QWidget()
        self._tag_layout = QVBoxLayout(self._tag_container)
        self._tag_layout.setContentsMargins(0, 0, 0, 0)
        self._tag_layout.setSpacing(6)
        self._scroll.setWidget(self._tag_container)
        frame_layout.addWidget(self._scroll)

        root.addWidget(self._frame)

    def show_features(self, results: dict[str, tuple[str, int]],
                      existing_tags: set[str]):
        """캐릭터 특징 표시.
        Args:
            results: {표시이름: (특징문자열, 게시물수)}
            existing_tags: 이미 프롬프트에 존재하는 태그 (정규화됨)
        """
        self._clear_tags()
        self._buttons.clear()

        if not results:
            self.hide()
            return

        # 타이틀 업데이트
        names = list(results.keys())
        self._title_label.setText(
            f"캐릭터 특징 ({len(names)}명 감지)"
        )

        for char_name, (features_str, count) in results.items():
            # 캐릭터 이름 헤더
            name_label = QLabel(f"{char_name}  ({count:,})")
            name_label.setStyleSheet(
                "color: #CCC; font-weight: bold; font-size: 11px; "
                "background: transparent; padding: 2px 0;"
            )
            self._tag_layout.addWidget(name_label)

            # 태그 FlowLayout
            flow_container = QWidget()
            flow = FlowLayout(flow_container)
            flow.setSpacing(4)

            tags = [t.strip() for t in features_str.split(",") if t.strip()]
            for tag in tags:
                norm = tag.strip().lower().replace("_", " ")
                is_existing = norm in existing_tags

                btn = QPushButton(tag if not is_existing else f"{tag} (존재)")
                btn.setCheckable(True)
                btn.setChecked(not is_existing)
                btn.setEnabled(not is_existing)

                if is_existing:
                    btn.setStyleSheet(_TAG_EXISTS)
                else:
                    btn.setStyleSheet(_TAG_CHECKED)
                    btn.toggled.connect(
                        lambda checked, b=btn: b.setStyleSheet(
                            _TAG_CHECKED if checked else _TAG_UNCHECKED
                        )
                    )

                flow.addWidget(btn)
                self._buttons.append((btn, tag, is_existing))

            self._tag_layout.addWidget(flow_container)

        self._tag_layout.addStretch()
        self.show()

    def hide_features(self):
        """패널 숨기기"""
        self._clear_tags()
        self._buttons.clear()
        self.hide()

    def _clear_tags(self):
        """기존 태그 위젯 제거"""
        while self._tag_layout.count():
            item = self._tag_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_insert(self):
        """체크된 태그만 삽입 요청"""
        tags = []
        for btn, tag, is_existing in self._buttons:
            if not is_existing and btn.isChecked():
                tags.append(tag)
        if tags:
            self.insert_requested.emit(tags)

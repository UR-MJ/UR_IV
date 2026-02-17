# widgets/favorite_tags.py
"""즐겨찾기 태그 원클릭 삽입 위젯"""
import os
import json
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QInputDialog, QMenu, QScrollArea, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

_FAV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "favorite_tags.json")


def _load_favs() -> list[dict]:
    """[{name: str, tags: str}, ...]"""
    if not os.path.exists(_FAV_FILE):
        return []
    try:
        with open(_FAV_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_favs(favs: list[dict]):
    try:
        with open(_FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class FavoriteTagsBar(QWidget):
    """즐겨찾기 태그 바 — 클릭 시 대상 텍스트 위젯에 태그 삽입"""

    tag_insert_requested = pyqtSignal(str)  # 삽입할 태그 문자열

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._refresh_buttons()

    def _init_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(4)

        lbl = QLabel("⭐")
        lbl.setFixedWidth(20)
        lbl.setStyleSheet("font-size: 14px;")
        outer.addWidget(lbl)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(34)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._container = QWidget()
        self._btn_layout = QHBoxLayout(self._container)
        self._btn_layout.setContentsMargins(0, 0, 0, 0)
        self._btn_layout.setSpacing(4)
        self._btn_layout.addStretch(1)

        scroll.setWidget(self._container)
        outer.addWidget(scroll, 1)

        # + 추가 버튼
        btn_add = QPushButton("+")
        btn_add.setFixedSize(28, 28)
        btn_add.setToolTip("즐겨찾기 태그 추가")
        btn_add.setStyleSheet(
            "QPushButton { background-color: #5865F2; color: white; border-radius: 14px; "
            "font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #6975F3; }"
        )
        btn_add.clicked.connect(self._on_add)
        outer.addWidget(btn_add)

    def _refresh_buttons(self):
        """저장된 즐겨찾기로 버튼 재생성"""
        # 기존 버튼 제거 (stretch 제외)
        while self._btn_layout.count() > 1:
            item = self._btn_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        favs = _load_favs()
        for i, fav in enumerate(favs):
            btn = QPushButton(fav.get("name", "?"))
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                "QPushButton { background-color: #2C2C2C; color: #DDD; "
                "border: 1px solid #555; border-radius: 12px; "
                "padding: 0 10px; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background-color: #444; border-color: #5865F2; }"
            )
            btn.setToolTip(fav.get("tags", ""))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, t=fav["tags"]: self.tag_insert_requested.emit(t))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, idx=i, b=btn: self._on_context(idx, b)
            )
            self._btn_layout.insertWidget(self._btn_layout.count() - 1, btn)

    def _on_add(self):
        """새 즐겨찾기 태그 추가"""
        name, ok = QInputDialog.getText(self, "즐겨찾기 추가", "버튼 이름 (짧게):")
        if not ok or not name.strip():
            return
        tags, ok2 = QInputDialog.getText(self, "즐겨찾기 추가", "삽입할 태그:")
        if not ok2 or not tags.strip():
            return
        favs = _load_favs()
        favs.append({"name": name.strip(), "tags": tags.strip()})
        _save_favs(favs)
        self._refresh_buttons()

    def _on_context(self, idx: int, btn: QPushButton):
        """우클릭 메뉴: 편집, 삭제"""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #2a2a2a; color: #ddd; border: 1px solid #555; }"
            "QMenu::item { padding: 6px 16px; }"
            "QMenu::item:selected { background-color: #5865F2; }"
        )
        act_edit = menu.addAction("편집")
        act_del = menu.addAction("삭제")
        chosen = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if not chosen:
            return

        favs = _load_favs()
        if idx >= len(favs):
            return

        if chosen == act_edit:
            fav = favs[idx]
            name, ok = QInputDialog.getText(self, "편집", "버튼 이름:", text=fav["name"])
            if not ok:
                return
            tags, ok2 = QInputDialog.getText(self, "편집", "태그:", text=fav["tags"])
            if not ok2:
                return
            favs[idx] = {"name": name.strip() or fav["name"], "tags": tags.strip() or fav["tags"]}
            _save_favs(favs)
            self._refresh_buttons()
        elif chosen == act_del:
            favs.pop(idx)
            _save_favs(favs)
            self._refresh_buttons()

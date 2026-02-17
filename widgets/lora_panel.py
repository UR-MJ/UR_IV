# widgets/lora_panel.py
"""LoRA 활성 목록 패널 — 선택된 LoRA를 토글/삭제할 수 있는 위젯"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel
)
from PyQt6.QtCore import Qt


class LoraActivePanel(QWidget):
    """활성 LoRA 목록 패널

    각 항목: [☑ name (weight)] [×]
    - 체크 ON: 생성 시 포함
    - 체크 OFF: 생성 시 제외
    - × 버튼: 목록에서 제거
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[dict] = []  # {'name': str, 'weight': float, 'enabled': bool}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(2)
        self.hide()  # 비어있으면 숨김

    def add_lora(self, name: str, weight: float):
        """LoRA 추가. 이미 있으면 weight만 업데이트"""
        for entry in self._entries:
            if entry['name'] == name:
                entry['weight'] = weight
                entry['enabled'] = True
                self._rebuild_ui()
                return
        self._entries.append({'name': name, 'weight': weight, 'enabled': True})
        self._rebuild_ui()

    def remove_lora(self, name: str):
        """LoRA 제거"""
        self._entries = [e for e in self._entries if e['name'] != name]
        self._rebuild_ui()

    def get_active_lora_text(self) -> str:
        """활성(enabled) LoRA들의 문법 문자열 반환"""
        parts = []
        for e in self._entries:
            if e['enabled']:
                parts.append(f"<lora:{e['name']}:{e['weight']:.2f}>")
        return ", ".join(parts)

    def get_entries(self) -> list[dict]:
        """전체 목록 반환 (설정 저장용)"""
        return [dict(e) for e in self._entries]

    def set_entries(self, entries: list[dict]):
        """목록 복원 (설정 로드용)"""
        self._entries = []
        for e in entries:
            self._entries.append({
                'name': e.get('name', ''),
                'weight': e.get('weight', 0.8),
                'enabled': e.get('enabled', True),
            })
        self._rebuild_ui()

    def _rebuild_ui(self):
        """위젯 전체 재구성"""
        # 기존 위젯 제거
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._entries:
            self.hide()
            return

        self.show()
        for entry in self._entries:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 0, 4, 0)
            row_layout.setSpacing(4)

            chk = QCheckBox(f"{entry['name']}  ({entry['weight']:.2f})")
            chk.setChecked(entry['enabled'])
            chk.setStyleSheet(
                "QCheckBox { color: #DDD; font-size: 11px; }"
                "QCheckBox::indicator { width: 14px; height: 14px; }"
            )
            chk.toggled.connect(
                lambda checked, name=entry['name']: self._on_toggle(name, checked)
            )
            row_layout.addWidget(chk, 1)

            btn_del = QPushButton("×")
            btn_del.setFixedSize(20, 20)
            btn_del.setStyleSheet(
                "QPushButton { background: #444; color: #AAA; border: none; "
                "border-radius: 10px; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background: #C0392B; color: white; }"
            )
            btn_del.clicked.connect(
                lambda _, name=entry['name']: self.remove_lora(name)
            )
            row_layout.addWidget(btn_del)

            row.setStyleSheet(
                "QWidget { background-color: #252525; border-radius: 4px; }"
            )
            self._layout.addWidget(row)

    def _on_toggle(self, name: str, checked: bool):
        """체크박스 토글"""
        for e in self._entries:
            if e['name'] == name:
                e['enabled'] = checked
                break

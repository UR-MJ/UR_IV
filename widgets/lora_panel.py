# widgets/lora_panel.py
"""LoRA 활성 목록 패널 — 선택된 LoRA를 토글/삭제/강도 조절할 수 있는 위젯"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton,
    QLabel, QSlider, QMessageBox, QLineEdit, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
import re


class ClickableWeightLabel(QStackedWidget):
    """더블클릭으로 직접 편집 가능한 가중치 라벨"""
    value_changed = pyqtSignal(float)

    def __init__(self, value: float, parent=None):
        super().__init__(parent)
        self.setFixedWidth(44)
        self.setFixedHeight(20)

        # 라벨 (표시용)
        self._label = QLabel(f"{value:.2f}")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #AAA; font-size: 11px;")

        # 입력 필드 (편집용)
        self._edit = QLineEdit(f"{value:.2f}")
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setStyleSheet(
            "background: #333; color: #FFF; border: 1px solid #5865F2; "
            "border-radius: 2px; font-size: 11px; padding: 0px;"
        )
        self._edit.editingFinished.connect(self._finish_edit)

        self.addWidget(self._label)
        self.addWidget(self._edit)
        self.setCurrentIndex(0)

    def mouseDoubleClickEvent(self, event):
        """더블클릭 시 편집 모드 진입"""
        self._edit.setText(self._label.text())
        self.setCurrentIndex(1)
        self._edit.setFocus()
        self._edit.selectAll()

    def set_text(self, text: str):
        """외부에서 값 업데이트 (슬라이더 연동)"""
        self._label.setText(text)
        if self.currentIndex() == 0:
            self._edit.setText(text)

    def _finish_edit(self):
        """편집 완료 — 값 검증 후 시그널 발사"""
        try:
            val = float(self._edit.text())
            val = max(-5.0, min(10.0, val))
        except ValueError:
            val = float(self._label.text())
        self._label.setText(f"{val:.2f}")
        self._edit.setText(f"{val:.2f}")
        self.setCurrentIndex(0)
        self.value_changed.emit(val)


class LoraActivePanel(QWidget):
    """활성 LoRA 목록 패널

    각 항목: [☑ name] [슬라이더 weight] [✕ 삭제]
    - 체크 ON: 생성 시 포함
    - 체크 OFF: 생성 시 제외
    - 슬라이더: 강도 조절 (-5.00~10.00)
    - ✕ 버튼: 확인 후 제거
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[dict] = []  # {'name': str, 'weight': float, 'enabled': bool}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(3)
        self.hide()  # 비어있으면 숨김

    def add_lora(self, name: str, weight: float):
        """LoRA 추가. 이미 있으면 weight만 업데이트"""
        for entry in self._entries:
            if entry['name'] == name:
                entry['weight'] = weight
                entry['enabled'] = True
                self._rebuild_ui()
                return
        self._entries.append({'name': name, 'weight': weight, 'enabled': True, 'locked': False})
        self._rebuild_ui()

    def parse_and_add_loras(self, text: str) -> int:
        """텍스트에서 <lora:name:weight> 패턴을 파싱하여 일괄 추가. 추가된 개수 반환"""
        pattern = re.compile(r'<lora:([^:>]+):([\d.]+)>')
        matches = pattern.findall(text)
        count = 0
        for name, weight_str in matches:
            try:
                weight = float(weight_str)
            except ValueError:
                continue
            self.add_lora(name.strip(), weight)
            count += 1
        return count

    def remove_lora(self, name: str):
        """LoRA 제거 (확인 후)"""
        reply = QMessageBox.question(
            self, "LoRA 제거",
            f"'{name}'을(를) 제거하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
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
                'locked': e.get('locked', False),
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
            row.setFixedHeight(32)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 2, 6, 2)
            row_layout.setSpacing(6)

            # 체크박스 (이름만)
            chk = QCheckBox(entry['name'])
            chk.setChecked(entry['enabled'])
            chk.setStyleSheet(
                "QCheckBox { color: #DDD; font-size: 12px; font-weight: bold; }"
                "QCheckBox::indicator { width: 16px; height: 16px; }"
            )
            chk.toggled.connect(
                lambda checked, name=entry['name']: self._on_toggle(name, checked)
            )
            row_layout.addWidget(chk)

            # 강도 슬라이더
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-500, 1000)
            slider.setValue(int(entry['weight'] * 100))
            slider.setFixedWidth(80)
            slider.setStyleSheet(
                "QSlider::groove:horizontal { background: #333; height: 4px; border-radius: 2px; }"
                "QSlider::handle:horizontal { background: #5865F2; width: 10px; "
                "margin: -3px 0; border-radius: 5px; }"
            )
            row_layout.addWidget(slider)

            # 강도 라벨 (더블클릭 편집 가능)
            weight_label = ClickableWeightLabel(entry['weight'])
            row_layout.addWidget(weight_label)

            # 슬라이더 → 라벨/데이터 연동
            slider.valueChanged.connect(
                lambda val, name=entry['name'], lbl=weight_label: (
                    lbl.set_text(f"{val / 100:.2f}"),
                    self._on_weight_change(name, val / 100.0),
                )
            )

            # 라벨 직접 편집 → 슬라이더/데이터 연동
            weight_label.value_changed.connect(
                lambda val, name=entry['name'], sl=slider: (
                    sl.blockSignals(True),
                    sl.setValue(int(val * 100)),
                    sl.blockSignals(False),
                    self._on_weight_change(name, val),
                )
            )

            # 잠금 버튼
            locked = entry.get('locked', False)
            btn_lock = QPushButton("\U0001F512" if locked else "\U0001F513")
            btn_lock.setFixedSize(24, 24)
            btn_lock.setToolTip("가중치 잠금")
            lock_base = (
                "QPushButton { background: transparent; border: none; "
                "font-family: 'Segoe UI Emoji'; font-size: 14px; }"
                "QPushButton:hover { background: #333; border-radius: 4px; }"
            )
            btn_lock.setStyleSheet(lock_base)
            if locked:
                slider.setEnabled(False)
            btn_lock.clicked.connect(
                lambda _, name=entry['name'], btn=btn_lock, sl=slider: self._on_lock_toggle(name, btn, sl)
            )
            row_layout.addWidget(btn_lock)

            # ✕ 삭제 버튼
            btn_del = QPushButton("✕")
            btn_del.setFixedSize(24, 24)
            btn_del.setToolTip("LoRA 제거")
            btn_del.setStyleSheet(
                "QPushButton { background: transparent; color: #666; border: none; "
                "font-size: 14px; font-weight: bold; }"
                "QPushButton:hover { color: #E74C3C; }"
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

    def _on_lock_toggle(self, name: str, btn: QPushButton, slider: QSlider):
        """가중치 잠금 토글"""
        for e in self._entries:
            if e['name'] == name:
                e['locked'] = not e.get('locked', False)
                if e['locked']:
                    btn.setText("\U0001F512")
                    slider.setEnabled(False)
                else:
                    btn.setText("\U0001F513")
                    slider.setEnabled(True)
                break

    def _on_weight_change(self, name: str, weight: float):
        """슬라이더로 강도 변경"""
        for e in self._entries:
            if e['name'] == name:
                e['weight'] = weight
                break

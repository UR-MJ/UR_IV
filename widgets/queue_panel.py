# widgets/queue_panel.py
"""
대기열 패널 위젯 (가로 스크롤 카드 목록)
"""
import os
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox, QInputDialog,
    QDialog, QTextEdit, QLineEdit, QDialogButtonBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from widgets.queue_item import QueueItemCard
from utils.theme_manager import get_color

PRESET_DIR = "queue_presets"


class QueueItemEditDialog(QDialog):
    """대기열 아이템 편집 다이얼로그"""

    def __init__(self, item_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("대기열 항목 편집")
        self.setMinimumSize(700, 600)
        self.resize(750, 650)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')}; }}
            QLabel {{ color: {get_color('text_secondary')}; font-size: 12px; }}
            QLineEdit, QTextEdit {{
                background-color: {get_color('bg_input')}; border: 1px solid {get_color('border')};
                border-radius: 6px; padding: 6px; color: {get_color('text_primary')}; font-size: 12px;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {get_color('accent')};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Prompt (큰 영역)
        prompt_label = QLabel("Prompt")
        prompt_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {get_color('text_primary')};")
        layout.addWidget(prompt_label)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(item_data.get('prompt', ''))
        layout.addWidget(self.prompt_edit, stretch=3)

        # Negative (중간 영역)
        neg_label = QLabel("Negative Prompt")
        neg_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {get_color('text_primary')};")
        layout.addWidget(neg_label)
        self.neg_edit = QTextEdit()
        self.neg_edit.setPlainText(item_data.get('negative_prompt', ''))
        layout.addWidget(self.neg_edit, stretch=2)

        # 파라미터 (2줄로 압축)
        param_group = QFrame()
        param_group.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('bg_tertiary')}; border: 1px solid {get_color('border')};
                border-radius: 6px; padding: 4px;
            }}
        """)
        param_layout = QVBoxLayout(param_group)
        param_layout.setContentsMargins(10, 8, 10, 8)
        param_layout.setSpacing(6)

        # 1행: Steps, CFG, Seed
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(QLabel("Steps"))
        self.steps_edit = QLineEdit(str(item_data.get('steps', 20)))
        self.steps_edit.setFixedWidth(70)
        row1.addWidget(self.steps_edit)
        row1.addWidget(QLabel("CFG"))
        self.cfg_edit = QLineEdit(str(item_data.get('cfg_scale', 7.0)))
        self.cfg_edit.setFixedWidth(70)
        row1.addWidget(self.cfg_edit)
        row1.addWidget(QLabel("Seed"))
        self.seed_edit = QLineEdit(str(item_data.get('seed', -1)))
        self.seed_edit.setFixedWidth(100)
        row1.addWidget(self.seed_edit)
        row1.addStretch()
        param_layout.addLayout(row1)

        # 2행: Width, Height
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(QLabel("Width"))
        self.width_edit = QLineEdit(str(item_data.get('width', 1024)))
        self.width_edit.setFixedWidth(70)
        row2.addWidget(self.width_edit)
        row2.addWidget(QLabel("Height"))
        self.height_edit = QLineEdit(str(item_data.get('height', 1024)))
        self.height_edit.setFixedWidth(70)
        row2.addWidget(self.height_edit)
        row2.addStretch()
        param_layout.addLayout(row2)

        layout.addWidget(param_group)

        # 버튼
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet("""
            QPushButton {
                background-color: #5865F2; color: white;
                padding: 8px 24px; border-radius: 6px; font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #4752C4; }
        """)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        """편집된 데이터 반환"""
        return {
            'prompt': self.prompt_edit.toPlainText(),
            'negative_prompt': self.neg_edit.toPlainText(),
            'steps': int(self.steps_edit.text() or 20),
            'cfg_scale': float(self.cfg_edit.text() or 7.0),
            'width': int(self.width_edit.text() or 1024),
            'height': int(self.height_edit.text() or 1024),
            'seed': int(self.seed_edit.text() or -1),
        }


class DropCardContainer(QWidget):
    """드래그 앤 드롭을 지원하는 카드 컨테이너"""

    item_dropped = pyqtSignal(str, int)  # item_id, drop_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        # 드롭 위치 표시 인디케이터
        self._drop_indicator = QFrame(self)
        self._drop_indicator.setFixedWidth(3)
        self._drop_indicator.setStyleSheet("background-color: #5865F2; border-radius: 1px;")
        self._drop_indicator.hide()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        drop_x = event.position().x()

        # 드롭 위치 계산 및 인디케이터 표시
        layout = self.layout()
        if not layout:
            return

        indicator_x = 0
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget and widget.isVisible():
                widget_center = widget.x() + widget.width() / 2
                if drop_x < widget_center:
                    indicator_x = widget.x() - 2
                    break
                indicator_x = widget.x() + widget.width() + 2

        self._drop_indicator.setFixedHeight(self.height() - 10)
        self._drop_indicator.move(int(indicator_x), 5)
        self._drop_indicator.show()
        self._drop_indicator.raise_()

    def dragLeaveEvent(self, event):
        self._drop_indicator.hide()

    def dropEvent(self, event: QDropEvent):
        self._drop_indicator.hide()
        item_id = event.mimeData().text()
        drop_x = event.position().x()

        # 드롭 위치에서 인덱스 계산
        layout = self.layout()
        drop_index = layout.count()  # 기본: 맨 끝

        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget and widget.isVisible():
                widget_center = widget.x() + widget.width() / 2
                if drop_x < widget_center:
                    drop_index = i
                    break

        self.item_dropped.emit(item_id, drop_index)
        event.acceptProposedAction()


class QueuePanel(QWidget):
    """대기열 패널"""

    # 시그널
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    item_edit_requested = pyqtSignal(dict)
    queue_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue_items = []
        self.card_widgets = {}
        self.is_processing = False
        self.current_processing_id = None
        self._group_counter = 0
        self._total_for_progress = 0
        self._completed_for_progress = 0

        self._setup_ui()

    def _setup_ui(self):
        """UI 구성"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 헤더
        header_layout = QHBoxLayout()

        self.title_label = QLabel("⏳ 대기열 (0)")
        self.title_label.setStyleSheet("""
            font-weight: bold; font-size: 14px; color: #FFC107;
        """)
        header_layout.addWidget(self.title_label)

        # 진행률
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #5865F2; font-weight: bold; font-size: 12px;")
        header_layout.addWidget(self.progress_label)

        header_layout.addStretch()

        # 프리셋 버튼
        self.btn_save_preset = QPushButton("💾")
        self.btn_save_preset.setToolTip("프리셋 저장")
        self.btn_save_preset.setFixedWidth(35)
        self.btn_save_preset.setStyleSheet(self._small_btn_style())
        self.btn_save_preset.clicked.connect(self._save_preset_dialog)
        header_layout.addWidget(self.btn_save_preset)

        self.btn_load_preset = QPushButton("📂")
        self.btn_load_preset.setToolTip("프리셋 불러오기")
        self.btn_load_preset.setFixedWidth(35)
        self.btn_load_preset.setStyleSheet(self._small_btn_style())
        self.btn_load_preset.clicked.connect(self._load_preset_dialog)
        header_layout.addWidget(self.btn_load_preset)

        # 시작/중지
        self.btn_start = QPushButton("▶ 자동 시작")
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: #27ae60; color: white;
                border-radius: 4px; padding: 5px 15px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #2ecc71; }}
            QPushButton:disabled {{ background-color: {get_color('border')}; color: {get_color('text_muted')}; }}
        """)
        self.btn_start.clicked.connect(self._on_start_clicked)
        header_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ 중지")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; color: white;
                border-radius: 4px; padding: 5px 15px; font-weight: bold;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        self.btn_stop.clicked.connect(lambda: self.stop_requested.emit())
        self.btn_stop.hide()
        header_layout.addWidget(self.btn_stop)

        # 비우기
        self.btn_clear = QPushButton("🧹")
        self.btn_clear.setToolTip("전체 비우기")
        self.btn_clear.setFixedWidth(35)
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button')}; border: 1px solid {get_color('border')};
                border-radius: 4px; padding: 5px;
            }}
            QPushButton:hover {{ background-color: #5A2A2A; }}
        """)
        self.btn_clear.clicked.connect(self.clear_all)
        header_layout.addWidget(self.btn_clear)

        layout.addLayout(header_layout)

        # 카드 스크롤 영역 (가로)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFixedHeight(140)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {get_color('bg_secondary')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
            }}
        """)

        # 드롭 가능한 카드 컨테이너
        self.card_container = DropCardContainer()
        self.card_container.item_dropped.connect(self._on_item_dropped)
        self.card_layout = QHBoxLayout(self.card_container)
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.card_layout.setContentsMargins(5, 5, 5, 5)
        self.card_layout.setSpacing(8)

        self.empty_label = QLabel("대기열이 비어있습니다")
        self.empty_label.setStyleSheet(f"color: {get_color('text_muted')}; padding: 20px;")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_layout.addWidget(self.empty_label)

        self.scroll_area.setWidget(self.card_container)
        layout.addWidget(self.scroll_area)

        # 하단 정보
        bottom_layout = QHBoxLayout()

        self.info_label = QLabel("총 0장 예정")
        self.info_label.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 11px;")
        bottom_layout.addWidget(self.info_label)

        bottom_layout.addStretch()

        self.btn_add_current = QPushButton("➕ 현재 설정")
        self.btn_add_current.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button')}; border: 1px solid {get_color('border')};
                border-radius: 4px; padding: 5px 10px;
                color: {get_color('text_primary')}; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
        """)
        bottom_layout.addWidget(self.btn_add_current)

        layout.addLayout(bottom_layout)

    def _small_btn_style(self):
        return f"""
            QPushButton {{
                background-color: {get_color('bg_button')}; border: 1px solid {get_color('border')};
                border-radius: 4px; padding: 5px;
            }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
        """

    # ========== ID 생성 ==========

    def _generate_id(self):
        import uuid
        return str(uuid.uuid4())[:8]

    def _generate_group_id(self):
        self._group_counter += 1
        n = self._group_counter
        result = ''
        while n > 0:
            n -= 1
            result = chr(ord('A') + n % 26) + result
            n //= 26
        return result

    # ========== 아이템 추가/삭제 ==========

    def add_item(self, item_data: dict, group_id: str = None,
                 group_index: int = 1, group_total: int = 1,
                 is_last_of_group: bool = True):
        item_id = self._generate_id()
        item = {
            'id': item_id,
            'group_id': group_id or '',
            'group_index': group_index,
            'group_total': group_total,
            'is_last_of_group': is_last_of_group,
            **item_data
        }
        self.queue_items.append(item)
        self._refresh_display()
        self.queue_changed.emit(len(self.queue_items))
        return item_id

    def add_items_as_group(self, items_data: list, repeat_count: int = 1):
        for item_data in items_data:
            group_id = self._generate_group_id()
            for i in range(repeat_count):
                is_last = (i == repeat_count - 1)
                self.add_item(
                    item_data.copy(),
                    group_id=group_id,
                    group_index=i + 1,
                    group_total=repeat_count,
                    is_last_of_group=is_last
                )

    def add_single_item(self, item_data: dict):
        self.add_item(item_data, group_id='', is_last_of_group=True)

    def remove_item(self, item_id: str):
        self.queue_items = [item for item in self.queue_items if item['id'] != item_id]
        self._refresh_display()
        self.queue_changed.emit(len(self.queue_items))

    def remove_first_item(self):
        if self.queue_items:
            removed = self.queue_items.pop(0)
            self._refresh_display()
            self.queue_changed.emit(len(self.queue_items))
            return removed
        return None

    def get_first_item(self):
        return self.queue_items[0] if self.queue_items else None

    def get_item_by_id(self, item_id: str):
        for item in self.queue_items:
            if item['id'] == item_id:
                return item
        return None

    def clear_all(self):
        if not self.queue_items:
            return
        reply = QMessageBox.question(
            self, "확인",
            f"대기열의 {len(self.queue_items)}개 항목을 모두 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.queue_items.clear()
            self._refresh_display()
            self.queue_changed.emit(0)

    def count(self):
        return len(self.queue_items)

    def is_empty(self):
        return len(self.queue_items) == 0

    def get_all_items(self):
        return self.queue_items.copy()

    # ========== 디스플레이 ==========

    def _refresh_display(self):
        for card in self.card_widgets.values():
            self.card_layout.removeWidget(card)
            card.deleteLater()
        self.card_widgets.clear()

        if not self.queue_items:
            self.empty_label.show()
            self.title_label.setText("⏳ 대기열 (0)")
            self.info_label.setText("총 0장 예정")
            self.btn_start.setEnabled(False)
            self.progress_label.setText("")
            return

        self.empty_label.hide()
        self.title_label.setText(f"⏳ 대기열 ({len(self.queue_items)})")
        self.info_label.setText(f"총 {len(self.queue_items)}장 예정")
        self.btn_start.setEnabled(not self.is_processing)

        for item in self.queue_items:
            card = QueueItemCard(item)
            card.delete_requested.connect(self._on_delete_requested)
            card.edit_requested.connect(self._on_edit_requested)
            card.duplicate_requested.connect(self._on_duplicate_requested)

            if item['id'] == self.current_processing_id:
                card.set_processing(True)

            self.card_layout.addWidget(card)
            self.card_widgets[item['id']] = card

    # ========== 이벤트 핸들러 ==========

    def _on_delete_requested(self, item_id: str):
        self.remove_item(item_id)

    def _on_edit_requested(self, item_id: str):
        """편집 다이얼로그 표시"""
        item = self.get_item_by_id(item_id)
        if not item:
            return

        dialog = QueueItemEditDialog(item, self)
        if dialog.exec():
            updated = dialog.get_data()
            # 기존 항목에 편집된 필드 덮어쓰기
            for key, val in updated.items():
                item[key] = val
            # 카드 UI 갱신
            if item_id in self.card_widgets:
                self.card_widgets[item_id].update_data(item)

    def _on_duplicate_requested(self, item_id: str):
        """항목 복제"""
        item = self.get_item_by_id(item_id)
        if not item:
            return
        new_data = {k: v for k, v in item.items() if k != 'id'}
        self.add_item(
            new_data,
            group_id=item.get('group_id', ''),
            group_index=item.get('group_index', 1),
            group_total=item.get('group_total', 1),
            is_last_of_group=item.get('is_last_of_group', True)
        )

    def _on_start_clicked(self):
        if self.queue_items:
            self.start_requested.emit()

    def _on_item_dropped(self, item_id: str, drop_index: int):
        """드래그 앤 드롭으로 순서 변경"""
        # 원래 위치 찾기
        src_index = None
        for i, item in enumerate(self.queue_items):
            if item['id'] == item_id:
                src_index = i
                break

        if src_index is None:
            return

        # 아이템 이동
        item = self.queue_items.pop(src_index)
        # 소스 제거 후 인덱스 조정
        if drop_index > src_index:
            drop_index -= 1
        drop_index = max(0, min(drop_index, len(self.queue_items)))
        self.queue_items.insert(drop_index, item)
        self._refresh_display()

    # ========== 처리 상태 ==========

    def set_processing(self, is_processing: bool, item_id: str = None):
        self.is_processing = is_processing
        self.current_processing_id = item_id if is_processing else None

        self.btn_start.setVisible(not is_processing)
        self.btn_stop.setVisible(is_processing)
        self.btn_clear.setEnabled(not is_processing)
        self.btn_add_current.setEnabled(not is_processing)

        for card_id, card in self.card_widgets.items():
            card.set_processing(card_id == item_id and is_processing)

    # ========== 진행률 ==========

    def update_progress(self, completed: int, total: int):
        """진행률 업데이트"""
        self._completed_for_progress = completed
        self._total_for_progress = total
        if total > 0:
            self.progress_label.setText(f"{completed}/{total} 완료")
        else:
            self.progress_label.setText("")

    def reset_progress(self):
        self._completed_for_progress = 0
        self._total_for_progress = 0
        self.progress_label.setText("")

    # ========== 프리셋 ==========

    def _save_preset_dialog(self):
        if not self.queue_items:
            QMessageBox.information(self, "알림", "대기열이 비어있습니다.")
            return

        name, ok = QInputDialog.getText(self, "프리셋 저장", "프리셋 이름:")
        if not ok or not name.strip():
            return

        os.makedirs(PRESET_DIR, exist_ok=True)
        clean_items = []
        for item in self.queue_items:
            clean = {k: v for k, v in item.items()
                     if k not in ('id', 'current_processing_id')}
            clean_items.append(clean)

        path = os.path.join(PRESET_DIR, f"{name.strip()}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(clean_items, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "완료", f"프리셋 '{name.strip()}'이 저장되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패: {e}")

    def _load_preset_dialog(self):
        os.makedirs(PRESET_DIR, exist_ok=True)
        presets = [f[:-5] for f in os.listdir(PRESET_DIR) if f.endswith('.json')]

        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return

        name, ok = QInputDialog.getItem(
            self, "프리셋 불러오기", "프리셋:", presets, editable=False
        )
        if not ok:
            return

        path = os.path.join(PRESET_DIR, f"{name}.json")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                items = json.load(f)
            for item_data in items:
                self.add_single_item(item_data)
            QMessageBox.information(self, "완료", f"{len(items)}개 항목이 추가되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"불러오기 실패: {e}")

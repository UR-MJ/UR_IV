# widgets/queue_item.py
"""
대기열 개별 카드 위젯
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QMimeData
from PyQt6.QtGui import QFont, QDrag, QPixmap, QPainter


class QueueItemCard(QFrame):
    """대기열 카드 위젯"""

    # 시그널
    delete_requested = pyqtSignal(str)     # item_id
    edit_requested = pyqtSignal(str)       # item_id
    duplicate_requested = pyqtSignal(str)  # item_id

    def __init__(self, item_data: dict, parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.item_id = item_data.get('id', '')
        self._drag_start_pos: QPoint | None = None
        self._setup_ui()

    def _setup_ui(self):
        """UI 구성"""
        self.setFixedSize(100, 120)
        self.setStyleSheet(self._get_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(2)

        # 상단: 그룹 색상 바
        self.color_bar = QFrame()
        self.color_bar.setFixedHeight(4)
        self.color_bar.setStyleSheet(f"background-color: {self._get_group_color()};")
        layout.addWidget(self.color_bar)

        # 중앙: 캐릭터명 또는 특징
        self.char_label = QLabel(self._get_display_name())
        self.char_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.char_label.setWordWrap(True)
        self.char_label.setStyleSheet("""
            color: #EEE;
            font-size: 11px;
            font-weight: bold;
        """)
        self.char_label.setMaximumHeight(50)
        layout.addWidget(self.char_label, 1)

        # 하단: 그룹 정보
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(2)

        group_text = self._get_group_badge()
        self.group_label = QLabel(group_text)
        self.group_label.setStyleSheet("""
            color: #AAA;
            font-size: 9px;
            background-color: #333;
            padding: 1px 4px;
            border-radius: 3px;
        """)
        bottom_layout.addWidget(self.group_label)

        if self.item_data.get('is_last_of_group', False):
            end_label = QLabel("🔚")
            end_label.setStyleSheet("font-size: 10px;")
            bottom_layout.addWidget(end_label)

        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)

        # 삭제 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(2)

        self.btn_delete = QPushButton("✕")
        self.btn_delete.setFixedSize(24, 24)
        self.btn_delete.setToolTip("삭제")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #3A2A2A;
                border: 1px solid #5A3A3A;
                border-radius: 12px;
                color: #E74C3C;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #E74C3C;
                color: white;
                border: 1px solid #E74C3C;
            }
        """)
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.item_id))

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

    # ========== 드래그 지원 ==========

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            from PyQt6.QtWidgets import QApplication
            if distance >= QApplication.startDragDistance():
                self._start_drag()
        super().mouseMoveEvent(event)

    def _start_drag(self):
        """드래그 시작"""
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.item_id)

        # 미니 스냅샷
        pixmap = self.grab()
        drag.setPixmap(pixmap.scaled(80, 96, Qt.AspectRatioMode.KeepAspectRatio))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    # ========== 더블클릭 편집 ==========

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self.item_id)

    # ========== 우클릭 컨텍스트 메뉴 ==========

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2A2A2A;
                border: 1px solid #444;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                color: #DDD;
            }
            QMenu::item:selected {
                background-color: #5865F2;
            }
        """)

        action_edit = menu.addAction("✏️ 편집")
        action_dup = menu.addAction("📋 복제")
        menu.addSeparator()
        action_del = menu.addAction("🗑️ 삭제")

        action = menu.exec(event.globalPos())
        if action == action_edit:
            self.edit_requested.emit(self.item_id)
        elif action == action_dup:
            self.duplicate_requested.emit(self.item_id)
        elif action == action_del:
            self.delete_requested.emit(self.item_id)

    # ========== 스타일 / 표시 ==========

    def _get_style(self):
        return """
            QFrame {
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-radius: 6px;
            }
            QFrame:hover {
                border: 1px solid #5865F2;
            }
        """

    def _get_group_color(self):
        group_id = self.item_data.get('group_id', '')
        colors = [
            '#5865F2', '#57F287', '#FEE75C', '#EB459E',
            '#ED4245', '#9B59B6', '#E67E22', '#1ABC9C',
        ]
        if not group_id:
            return '#666'
        return colors[hash(group_id) % len(colors)]

    def _get_display_name(self):
        character = self.item_data.get('character', '')
        if character and character != 'nan' and character.strip():
            chars = [c.strip() for c in character.split(',')]
            name = chars[0].replace('_', '\n')
            if len(name) > 20:
                name = name[:18] + '...'
            return name

        features = self.item_data.get('features', [])
        if features:
            return '\n'.join(features[:3])

        prompt = self.item_data.get('prompt', '')
        if prompt:
            extracted = self._extract_features(prompt)
            if extracted:
                return '\n'.join(extracted[:3])

        return '(no info)'

    def _extract_features(self, prompt):
        feature_keywords = [
            'blonde hair', 'blue hair', 'pink hair', 'red hair', 'white hair',
            'black hair', 'brown hair', 'green hair', 'purple hair', 'silver hair',
            'twintails', 'ponytail', 'short hair', 'long hair', 'braid',
            'blue eyes', 'red eyes', 'green eyes', 'yellow eyes', 'purple eyes',
            'animal ears', 'cat ears', 'fox ears', 'horns', 'wings', 'tail',
        ]
        prompt_lower = prompt.lower()
        found = []
        for keyword in feature_keywords:
            if keyword in prompt_lower:
                found.append(keyword)
                if len(found) >= 3:
                    break
        return found

    def _get_group_badge(self):
        group_id = self.item_data.get('group_id', '')
        group_index = self.item_data.get('group_index', 0)
        group_total = self.item_data.get('group_total', 1)
        if not group_id:
            return '단독'
        group_letter = group_id[0].upper() if group_id else '?'
        return f'{group_letter} {group_index}/{group_total}'

    def set_processing(self, is_processing: bool):
        if is_processing:
            self.setStyleSheet("""
                QFrame {
                    background-color: #1A3A1A;
                    border: 2px solid #27ae60;
                    border-radius: 6px;
                }
            """)
            self.char_label.setText("⏳ 생성중...")
        else:
            self.setStyleSheet(self._get_style())
            self.char_label.setText(self._get_display_name())

    def set_completed(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #2A2A2A;
                border: 1px solid #27ae60;
                border-radius: 6px;
                opacity: 0.7;
            }
        """)
        self.color_bar.setStyleSheet("background-color: #27ae60;")

    def update_data(self, item_data: dict):
        self.item_data = item_data
        self.char_label.setText(self._get_display_name())
        self.group_label.setText(self._get_group_badge())
        self.color_bar.setStyleSheet(f"background-color: {self._get_group_color()};")

# widgets/common_widgets.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QComboBox, QCheckBox,
    QRadioButton, QButtonGroup, QFileDialog, QDialog, QLayout,
    QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QObject, QEvent, pyqtSignal, QRect, QSize
from utils.theme_manager import get_color

class WheelEventFilter(QObject):
    """마우스 휠 이벤트 필터"""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return super().eventFilter(obj, event)


class NoScrollComboBox(QComboBox):
    """스크롤 방지 콤보박스"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        event.ignore()


class NoScrollSpinBox(QSpinBox):
    """스크롤 방지 스핀박스"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        event.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    """스크롤 방지 더블 스핀박스"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        event.ignore()


class ResolutionItemWidget(QWidget):
    """해상도 아이템 위젯"""
    delete_requested = pyqtSignal(int)
    
    def __init__(self, width, height, description, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.setMinimumHeight(40)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        delete_button = QPushButton("-")
        delete_button.setFixedSize(30, 30)
        delete_button.setStyleSheet(
            "background-color: #c0392b; color: white; "
            "border-radius: 4px; font-weight: bold;"
        )
        delete_button.clicked.connect(self.on_delete)
        
        text = f"{description} ({width}x{height})"
        self.info_label = QLabel(text)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet(
            f"font-size: 10pt; color: {get_color('text_secondary')}; border: 1px solid {get_color('border')}; "
            f"border-radius: 6px; background-color: {get_color('bg_tertiary')};"
        )
        
        layout.addWidget(delete_button)
        layout.addWidget(self.info_label)

    def on_delete(self):
        self.delete_requested.emit(self.index)


class AutomationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {get_color('bg_tertiary')}; border-radius: 8px;
            }}
            QLabel {{
                font-size: 12px; color: {get_color('text_secondary')}; border: none;
            }}
            QLineEdit {{
                padding: 4px; border-radius: 4px;
                background-color: {get_color('bg_button')}; color: {get_color('text_primary')};
                border: 1px solid {get_color('border')}; font-size: 12px;
            }}
            QCheckBox {{
                font-size: 12px; spacing: 5px; color: {get_color('text_secondary')};
            }}
            QPushButton {{
                font-size: 12px; font-weight: bold; padding: 6px;
                border-radius: 4px; background-color: {get_color('bg_button')};
                color: {get_color('text_secondary')}; border: 1px solid {get_color('border')};
            }}
            QPushButton:checked {{
                background-color: #27ae60; color: white;
                border: 1px solid #2ecc71;
            }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
        """)

        layout = QVBoxLayout(self)  # ← self.layout 대신 layout 사용
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 종료 조건 토글
        term_layout = QHBoxLayout()
        term_layout.setSpacing(5)
        
        self.btn_limit_count = QPushButton("횟수 제한")
        self.btn_limit_count.setCheckable(True)
        self.btn_limit_count.setChecked(True)
        
        self.btn_limit_time = QPushButton("시간 제한 (분)")
        self.btn_limit_time.setCheckable(True)
        
        self.term_group = QButtonGroup(self)
        self.term_group.addButton(self.btn_limit_count, 1)
        self.term_group.addButton(self.btn_limit_time, 2)
        
        term_layout.addWidget(self.btn_limit_count)
        term_layout.addWidget(self.btn_limit_time)
        layout.addLayout(term_layout)
        
        # 제한 값 입력
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("설정값:"))
        self.limit_input = QLineEdit("10")
        self.limit_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        input_layout.addWidget(self.limit_input)
        layout.addLayout(input_layout)
        
        # 반복 설정
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("프롬프트 당 반복:"))
        self.repeat_per_prompt = QLineEdit("1")
        self.repeat_per_prompt.setFixedWidth(50)
        self.repeat_per_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row1.addWidget(self.repeat_per_prompt)
        row1.addStretch()
        layout.addLayout(row1)
        
        # 대기 시간
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("생성 후 대기(초):"))
        self.delay_input = QLineEdit("1.0")
        self.delay_input.setFixedWidth(50)
        self.delay_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row2.addWidget(self.delay_input)
        row2.addStretch()
        layout.addLayout(row2)
        
        # 중복 허용
        self.chk_allow_duplicate = QCheckBox("중복 프롬프트 허용")
        self.chk_allow_duplicate.setChecked(False)
        layout.addWidget(self.chk_allow_duplicate)

    def get_settings(self):
        """설정 반환"""
        try: 
            limit = float(self.limit_input.text())
        except ValueError: 
            limit = 10
            
        try: 
            repeat = int(self.repeat_per_prompt.text())
        except ValueError: 
            repeat = 1
            
        try: 
            delay = float(self.delay_input.text())
        except ValueError: 
            delay = 1.0

        mode = 'count' if self.btn_limit_count.isChecked() else 'timer'
        if mode == 'timer': 
            limit = limit * 60 

        return {
            'termination_mode': mode,
            'termination_limit': int(limit) if mode == 'count' else limit,
            'repeat_per_prompt': repeat,
            'delay': delay,
            'allow_duplicates': self.chk_allow_duplicate.isChecked()  # ← 수정!
        }
    
    def get_delay(self):
        """대기 시간 반환"""
        try:
            return float(self.delay_input.text())
        except ValueError:
            return 1.0
            
class SettingsDialog(QDialog):
    """설정 대화상자"""
    def __init__(self, parent=None, current_path=""):
        super().__init__(parent)
        self.setWindowTitle("환경 설정")
        self.setFixedSize(400, 200)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('bg_secondary')}; color: {get_color('text_primary')};
            }}
            QLabel {{
                color: {get_color('text_primary')}; font-weight: bold;
            }}
            QLineEdit {{
                background-color: {get_color('bg_input')}; border: 1px solid {get_color('border')};
                color: {get_color('text_primary')}; padding: 5px; border-radius: 4px;
            }}
            QPushButton {{
                background-color: {get_color('accent')}; color: white;
                border-radius: 4px; padding: 8px;
            }}
            QPushButton:hover {{ background-color: #4752C4; }}
        """)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("이미지 저장 경로:"))
        path_layout = QHBoxLayout()
        
        self.path_input = QLineEdit(current_path)
        self.btn_browse = QPushButton("📂")
        self.btn_browse.setFixedWidth(40)
        self.btn_browse.clicked.connect(self.browse_folder)
        
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.btn_browse)
        layout.addLayout(path_layout)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("저장")
        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet(f"background-color: {get_color('bg_button')};")
        
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if folder:
            self.path_input.setText(folder)

    def get_data(self):
        return self.path_input.text()
        
class FlowLayout(QLayout):
    """플로우 레이아웃 (자동 줄바꿈, heightForWidth 지원)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._spacing = 10

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def setSpacing(self, spacing):
        self._spacing = spacing

    def spacing(self):
        return self._spacing

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), apply_geometry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply_geometry=True)

    def _do_layout(self, rect, apply_geometry=True):
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget is None:
                continue

            space = self._spacing
            item_w = widget.sizeHint().width()
            item_h = widget.sizeHint().height()
            next_x = x + item_w + space

            if next_x - space > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space
                next_x = x + item_w + space
                line_height = 0

            if apply_geometry:
                item.setGeometry(QRect(x, y, item_w, item_h))

            x = next_x
            line_height = max(line_height, item_h)

        return y + line_height - rect.y()
            
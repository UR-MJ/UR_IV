# widgets/tag_input.py
"""
태그 자동완성 입력창 위젯
"""
from PyQt6.QtWidgets import (
    QTextEdit, QListWidget, QListWidgetItem, QVBoxLayout,
    QWidget, QFrame, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QKeyEvent, QFocusEvent
from utils.tag_completer import get_tag_completer


class TagInputWidget(QTextEdit):
    """태그 자동완성 지원 입력창"""
    
    tag_inserted = pyqtSignal(str)  # 태그 삽입 시
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.completer = get_tag_completer()
        self.popup = None
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._show_suggestions)
        
        # 설정
        self.enable_autocomplete = True
        self.debounce_ms = 150  # 입력 후 대기 시간
        self.max_suggestions = 10
        
        # 시그널 연결
        self.textChanged.connect(self._on_text_changed)
        
        self._create_popup()
    
    def _create_popup(self):
        """자동완성 팝업 생성"""
        self.popup = QListWidget()
        self.popup.setWindowFlags(
            Qt.WindowType.Popup | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.popup.setMaximumHeight(200)
        self.popup.setStyleSheet("""
            QListWidget {
                background-color: #2A2A2A;
                border: 1px solid #5865F2;
                border-radius: 4px;
                padding: 2px;
            }
            QListWidget::item {
                color: #EEE;
                padding: 5px 10px;
                border-radius: 2px;
            }
            QListWidget::item:hover {
                background-color: #3A3A3A;
            }
            QListWidget::item:selected {
                background-color: #5865F2;
                color: white;
            }
        """)
        
        self.popup.itemClicked.connect(self._on_item_clicked)
        self.popup.hide()
    
    def _on_text_changed(self):
        """텍스트 변경 시"""
        if not self.enable_autocomplete:
            return
        
        # 디바운스
        self.debounce_timer.stop()
        self.debounce_timer.start(self.debounce_ms)
    
    def _show_suggestions(self):
        """자동완성 제안 표시"""
        if not self.enable_autocomplete:
            self.popup.hide()
            return
        
        # 현재 입력 중인 단어 추출
        current_word = self._get_current_word()
        
        if not current_word or len(current_word) < 2:
            self.popup.hide()
            return
        
        # 추천 가져오기
        suggestions = self.completer.get_suggestions(current_word, self.max_suggestions)
        
        if not suggestions:
            self.popup.hide()
            return
        
        # 팝업 업데이트
        self.popup.clear()
        for tag in suggestions:
            item = QListWidgetItem(tag)
            self.popup.addItem(item)
        
        # 첫 번째 항목 선택
        self.popup.setCurrentRow(0)
        
        # 팝업 위치 설정
        self._position_popup()
        self.popup.show()
    
    def _get_current_word(self) -> str:
        """현재 커서 위치의 단어 추출"""
        cursor = self.textCursor()
        text = self.toPlainText()
        pos = cursor.position()
        
        if pos == 0:
            return ""
        
        # 쉼표로 구분된 마지막 단어 찾기
        before_cursor = text[:pos]
        
        # 마지막 쉼표 이후 텍스트
        last_comma = before_cursor.rfind(',')
        if last_comma == -1:
            current_word = before_cursor
        else:
            current_word = before_cursor[last_comma + 1:]
        
        return current_word.strip()
    
    def _position_popup(self):
        """팝업 위치 설정"""
        cursor_rect = self.cursorRect()
        global_pos = self.mapToGlobal(cursor_rect.bottomLeft())
        
        # 팝업 너비 설정
        popup_width = max(200, self.width())
        self.popup.setFixedWidth(popup_width)
        
        # 위치 조정
        self.popup.move(global_pos.x(), global_pos.y() + 5)
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """항목 클릭 시"""
        self._insert_suggestion(item.text())
    
    def _insert_suggestion(self, tag: str):
        """추천 태그 삽입"""
        cursor = self.textCursor()
        text = self.toPlainText()
        pos = cursor.position()
        
        # 현재 단어 범위 찾기
        before_cursor = text[:pos]
        last_comma = before_cursor.rfind(',')
        
        if last_comma == -1:
            start_pos = 0
        else:
            start_pos = last_comma + 1
            # 쉼표 뒤 공백 건너뛰기
            while start_pos < pos and text[start_pos] == ' ':
                start_pos += 1
        
        # 현재 단어 대체
        cursor.setPosition(start_pos)
        cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
        cursor.insertText(tag + ", ")

        self.setTextCursor(cursor)
        self.popup.hide()
        
        self.tag_inserted.emit(tag)
    
    def keyPressEvent(self, event: QKeyEvent):
        """키 이벤트 처리"""
        if self.popup.isVisible():
            # 팝업이 보이는 상태
            
            if event.key() == Qt.Key.Key_Down:
                # 아래 화살표: 다음 항목
                current = self.popup.currentRow()
                if current < self.popup.count() - 1:
                    self.popup.setCurrentRow(current + 1)
                return
            
            elif event.key() == Qt.Key.Key_Up:
                # 위 화살표: 이전 항목
                current = self.popup.currentRow()
                if current > 0:
                    self.popup.setCurrentRow(current - 1)
                return
            
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                # Enter/Tab: 선택 항목 삽입
                current_item = self.popup.currentItem()
                if current_item:
                    self._insert_suggestion(current_item.text())
                return
            
            elif event.key() == Qt.Key.Key_Escape:
                # Escape: 팝업 닫기
                self.popup.hide()
                return
        
        # 기본 처리
        super().keyPressEvent(event)
    
    def focusOutEvent(self, event: QFocusEvent):
        """포커스 잃을 때"""
        # 팝업 클릭 시에는 닫지 않음
        QTimer.singleShot(100, self._check_hide_popup)
        super().focusOutEvent(event)
    
    def _check_hide_popup(self):
        """팝업 숨김 체크"""
        if not self.hasFocus() and not self.popup.hasFocus():
            self.popup.hide()
    
    def set_autocomplete_enabled(self, enabled: bool):
        """자동완성 활성화/비활성화"""
        self.enable_autocomplete = enabled
        if not enabled:
            self.popup.hide()
    
    def hideEvent(self, event):
        """위젯 숨길 때"""
        self.popup.hide()
        super().hideEvent(event)
    
    def closeEvent(self, event):
        """위젯 닫을 때"""
        self.popup.close()
        super().closeEvent(event)
# widgets/image_viewer.py
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QLabel
from PyQt6.QtCore import Qt, QEvent, QPoint, QTimer
from PyQt6.QtGui import QPixmap
from utils.theme_manager import get_color

class FullScreenImageViewer(QDialog):
    """전체 화면 이미지 뷰어"""
    
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.pixmap = None 
        self.is_dragging = False
        self.last_mouse_pos = QPoint()
        self.scale_factor = 1.0
        
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle("Image Viewer")
        self.resize(1200, 900)
        self.setStyleSheet(f"background-color: {get_color('bg_primary')};")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 스크롤 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        self.label.setScaledContents(True)
        
        self.scroll_area.setWidget(self.label)
        layout.addWidget(self.scroll_area)
        
        # 이벤트 필터
        self.scroll_area.viewport().installEventFilter(self)
        
        if os.path.exists(image_path):
            self.pixmap = QPixmap(image_path)
        else:
            self.pixmap = QPixmap()

        if self.pixmap.isNull():
            self.label.setText("이미지를 불러올 수 없습니다.")
            self.label.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 20px;")
            self.label.adjustSize()
        
        self.show()

    def showEvent(self, event):
        """창 표시 이벤트"""
        super().showEvent(event)
        if not self.pixmap.isNull():
            QTimer.singleShot(0, self.fit_to_screen)

    def fit_to_screen(self):
        """화면에 맞춤"""
        if self.pixmap.isNull(): 
            return
        
        viewport_size = self.scroll_area.viewport().size()
        screen_w = viewport_size.width()
        screen_h = viewport_size.height()
        
        img_w = self.pixmap.width()
        img_h = self.pixmap.height()
        
        if img_w > 0 and img_h > 0:
            scale_w = screen_w / img_w
            scale_h = screen_h / img_h
            self.scale_factor = min(scale_w, scale_h)
        else:
            self.scale_factor = 1.0
            
        self.update_view()
        self.center_image()

    def update_view(self):
        """뷰 업데이트"""
        if self.pixmap.isNull(): 
            return
        
        new_w = int(self.pixmap.width() * self.scale_factor)
        new_h = int(self.pixmap.height() * self.scale_factor)
        
        self.label.setFixedSize(new_w, new_h)
        self.label.setPixmap(self.pixmap)

    def center_image(self):
        """이미지 중앙 정렬"""
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue((h_bar.maximum() + h_bar.minimum()) // 2)
        v_bar.setValue((v_bar.maximum() + v_bar.minimum()) // 2)

    def wheelEvent(self, event):
        """마우스 휠 줌"""
        angle = event.angleDelta().y()
        if angle > 0:
            self.scale_factor *= 1.1
        else:
            self.scale_factor *= 0.9
        
        if self.scale_factor < 0.05: 
            self.scale_factor = 0.05
        if self.scale_factor > 20.0: 
            self.scale_factor = 20.0
        
        self.update_view()

    def eventFilter(self, source, event):
        """이벤트 필터"""
        if source == self.scroll_area.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.is_dragging = False
                    self.last_mouse_pos = event.globalPosition().toPoint()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
            
            elif event.type() == QEvent.Type.MouseMove:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.is_dragging = True
                    delta = event.globalPosition().toPoint() - self.last_mouse_pos
                    self.last_mouse_pos = event.globalPosition().toPoint()
                    
                    h_bar = self.scroll_area.horizontalScrollBar()
                    v_bar = self.scroll_area.verticalScrollBar()
                    h_bar.setValue(h_bar.value() - delta.x())
                    v_bar.setValue(v_bar.value() - delta.y())
                    return True
            
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    self.is_dragging = False
                    return True
                    
        return super().eventFilter(source, event)
    
    def keyPressEvent(self, event):
        """ESC로 닫기"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
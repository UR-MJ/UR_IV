# widgets/search_preview.py
"""
검색 결과 미리보기 카드 위젯
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from utils.theme_manager import get_color


class SearchPreviewCard(QWidget):
    """검색 결과 미리보기 카드"""

    # 시그널
    apply_clicked = pyqtSignal(dict)       # 즉시 적용
    add_to_queue_clicked = pyqtSignal(dict) # 대기열 추가
    next_clicked = pyqtSignal()             # 다음 결과 보기

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_bundle = None
        self._feature_extractor = None
        self._setup_ui()

    @property
    def feature_extractor(self):
        """FeatureExtractor 지연 로드"""
        if self._feature_extractor is None:
            from utils.feature_extractor import get_feature_extractor
            self._feature_extractor = get_feature_extractor()
        return self._feature_extractor
    
    def _setup_ui(self):
        """UI 구성"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 헤더
        header_label = QLabel("📋 미리보기")
        header_label.setStyleSheet("""
            font-weight: bold;
            font-size: 13px;
            color: #FFC107;
        """)
        layout.addWidget(header_label)
        
        # 카드 프레임
        self.card_frame = QFrame()
        self.card_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('bg_tertiary')};
                border: 1px solid {get_color('border')};
                border-radius: 8px;
            }}
        """)
        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)
        
        # 캐릭터
        char_row = QHBoxLayout()
        char_icon = QLabel("🎭")
        char_icon.setFixedWidth(20)
        char_row.addWidget(char_icon)
        
        self.char_value = QLabel("-")
        self.char_value.setStyleSheet("""
            color: #5DADE2;
            font-weight: bold;
            font-size: 12px;
        """)
        self.char_value.setWordWrap(True)
        char_row.addWidget(self.char_value, 1)
        card_layout.addLayout(char_row)
        
        # 작품
        copyright_row = QHBoxLayout()
        copyright_icon = QLabel("📺")
        copyright_icon.setFixedWidth(20)
        copyright_row.addWidget(copyright_icon)
        
        self.copyright_value = QLabel("-")
        self.copyright_value.setStyleSheet("""
            color: #82E0AA;
            font-size: 11px;
        """)
        self.copyright_value.setWordWrap(True)
        copyright_row.addWidget(self.copyright_value, 1)
        card_layout.addLayout(copyright_row)
        
        # 작가
        artist_row = QHBoxLayout()
        artist_icon = QLabel("🎨")
        artist_icon.setFixedWidth(20)
        artist_row.addWidget(artist_icon)
        
        self.artist_value = QLabel("-")
        self.artist_value.setStyleSheet("""
            color: #F9E79F;
            font-size: 11px;
        """)
        artist_row.addWidget(self.artist_value, 1)
        card_layout.addLayout(artist_row)
        
        # 구분선 1
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet(f"background-color: {get_color('border')};")
        line1.setFixedHeight(1)
        card_layout.addWidget(line1)
        
        # 인물 수
        count_row = QHBoxLayout()
        count_icon = QLabel("👤")
        count_icon.setFixedWidth(20)
        count_row.addWidget(count_icon)
        
        self.count_value = QLabel("-")
        self.count_value.setStyleSheet("""
            color: #BB8FCE;
            font-size: 11px;
        """)
        count_row.addWidget(self.count_value, 1)
        card_layout.addLayout(count_row)
        
        # 특징
        feature_row = QHBoxLayout()
        feature_icon = QLabel("✨")
        feature_icon.setFixedWidth(20)
        feature_row.addWidget(feature_icon)
        
        self.feature_value = QLabel("-")
        self.feature_value.setStyleSheet("""
            color: #AEB6BF;
            font-size: 11px;
        """)
        self.feature_value.setWordWrap(True)
        feature_row.addWidget(self.feature_value, 1)
        card_layout.addLayout(feature_row)
        
        # 구분선 2
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"background-color: {get_color('border')};")
        line2.setFixedHeight(1)
        card_layout.addWidget(line2)
        
        # 일반 태그 헤더
        tags_header = QLabel("📝 일반 태그:")
        tags_header.setStyleSheet(f"""
            color: {get_color('text_muted')};
            font-size: 10px;
        """)
        card_layout.addWidget(tags_header)
        
        # 일반 태그 내용
        self.tags_text = QTextEdit()
        self.tags_text.setReadOnly(True)
        self.tags_text.setMaximumHeight(80)
        self.tags_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color('bg_secondary')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                color: {get_color('text_secondary')};
                font-size: 10px;
                padding: 5px;
            }}
        """)
        card_layout.addWidget(self.tags_text)
        
        layout.addWidget(self.card_frame)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)
        
        # 다른 결과 보기
        self.btn_next = QPushButton("👁️ 다른 결과")
        self.btn_next.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('bg_button')};
                border: 1px solid {get_color('border')};
                border-radius: 4px;
                padding: 6px 10px;
                color: {get_color('text_primary')};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {get_color('bg_button_hover')};
                border-color: {get_color('accent')};
            }}
        """)
        self.btn_next.clicked.connect(lambda: self.next_clicked.emit())
        btn_layout.addWidget(self.btn_next)
        
        # 즉시 적용
        self.btn_apply = QPushButton("✅ 적용")
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                border-radius: 4px;
                padding: 6px 12px;
                color: white;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.btn_apply)
        
        # 대기열 추가
        self.btn_add_queue = QPushButton("➕ 대기열")
        self.btn_add_queue.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                border-radius: 4px;
                padding: 6px 12px;
                color: white;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5dade2;
            }
        """)
        self.btn_add_queue.clicked.connect(self._on_add_queue_clicked)
        btn_layout.addWidget(self.btn_add_queue)
        
        layout.addLayout(btn_layout)
        
        # 빈 상태 라벨
        self.empty_label = QLabel("검색 후 결과를 미리볼 수 있습니다.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"""
            color: {get_color('text_muted')};
            padding: 30px;
            font-size: 11px;
        """)
        layout.addWidget(self.empty_label)
        
        # 초기 상태: 카드 숨김
        self._show_empty_state()
    
    def _show_empty_state(self):
        """빈 상태 표시"""
        self.card_frame.hide()
        self.btn_next.hide()
        self.btn_apply.hide()
        self.btn_add_queue.hide()
        self.empty_label.show()
    
    def _show_card_state(self):
        """카드 상태 표시"""
        self.empty_label.hide()
        self.card_frame.show()
        self.btn_next.show()
        self.btn_apply.show()
        self.btn_add_queue.show()
    
    def set_bundle(self, bundle: dict):
        """번들 데이터 설정"""
        if not bundle:
            self.clear()
            return
        
        self.current_bundle = bundle
        self._show_card_state()  # 카드 표시!
        
        # 데이터 추출
        character = str(bundle.get('character', '') or '')
        copyright_str = str(bundle.get('copyright', '') or '')
        artist = str(bundle.get('artist', '') or '')
        general = str(bundle.get('general', '') or '')
        
        # nan 처리
        if character.lower() == 'nan': character = ''
        if copyright_str.lower() == 'nan': copyright_str = ''
        if artist.lower() == 'nan': artist = ''
        if general.lower() == 'nan': general = ''
        
        # 캐릭터 (char_value 사용!)
        self.char_value.setText(character.replace('_', ' ') if character else '-')
        
        # 작품 (copyright_value 사용!)
        self.copyright_value.setText(copyright_str.replace('_', ' ') if copyright_str else '-')
        
        # 작가 (artist_value 사용!)
        if artist:
            clean_artist = artist.replace('artist:', '').strip()
            self.artist_value.setText(clean_artist.replace('_', ' '))
        else:
            self.artist_value.setText('-')
        
        # 일반 태그 처리
        if general:
            general_tags = [t.strip() for t in general.split(',') if t.strip()]
            
            # 인물 수 태그 분리
            person_tags = []
            other_tags = []
            
            person_count_set = {
                '1girl', '2girls', '3girls', '4girls', '5girls', '6+girls',
                '1boy', '2boys', '3boys', '4boys', '5boys', '6+boys',
                '1other', '2others', '3others', '4others', '5others', '6+others',
            }
            
            # 이미 분류된 태그들 (중복 제거용)
            classified_tags = set()
            
            if character:
                for c in character.split(','):
                    classified_tags.add(c.strip().lower())
            
            if copyright_str:
                for c in copyright_str.split(','):
                    classified_tags.add(c.strip().lower())
            
            if artist:
                clean_artist = artist.replace('artist:', '').strip()
                classified_tags.add(clean_artist.lower())
            
            for tag in general_tags:
                tag_lower = tag.lower()
                
                if tag_lower in classified_tags:
                    continue
                
                if tag_lower in person_count_set:
                    person_tags.append(tag)
                else:
                    other_tags.append(tag)
            
            # 인물 수 (count_value 사용!)
            self.count_value.setText(', '.join(person_tags) if person_tags else '-')
            
            # 특징 추출 (feature_value 사용!)
            features = self.feature_extractor.extract_features(', '.join(other_tags), max_count=5)
            self.feature_value.setText(', '.join(features) if features else '-')
            
            # 일반 태그 (tags_text 사용!)
            if other_tags:
                display_tags = other_tags[:30]
                if len(other_tags) > 30:
                    display_text = ', '.join(display_tags) + f'\n... (+{len(other_tags) - 30}개)'
                else:
                    display_text = ', '.join(display_tags)
                self.tags_text.setPlainText(display_text)
            else:
                self.tags_text.setPlainText('-')
        else:
            self.count_value.setText('-')
            self.feature_value.setText('-')
            self.tags_text.setPlainText('-')
        
    def clear(self):
        """미리보기 초기화"""
        self.current_bundle = None
        self._show_empty_state()
    
    def _on_apply_clicked(self):
        """적용 버튼 클릭"""
        if self.current_bundle:
            self.apply_clicked.emit(self.current_bundle)
    
    def _on_add_queue_clicked(self):
        """대기열 추가 버튼 클릭"""
        if self.current_bundle:
            self.add_to_queue_clicked.emit(self.current_bundle)
    
    def get_current_bundle(self):
        """현재 번들 반환"""
        return self.current_bundle
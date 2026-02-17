# ui/generator_base.py
"""
GeneratorMainUI의 기본 구조 및 초기화
"""
import os
import json
import time
import random
from pathlib import Path
from PIL import Image

from PyQt6.QtWidgets import QMainWindow, QWidget, QMessageBox
from PyQt6.QtCore import Qt, QTimer

from config import *
from core.database import MetadataManager
from core.image_utils import get_thumb_path
from widgets.common_widgets import WheelEventFilter

class GeneratorBase(QMainWindow):
    def __init__(self):
        super().__init__()

        # 데이터베이스 & 분류기
        self.db = MetadataManager(DB_FILE)
        self._tag_classifier = None  # 지연 로드
        self.wheel_filter = WheelEventFilter()
        
        # 상태 변수들
        self.current_image_path = None
        self.generation_data = {}
        self.gallery_items = []
        self.loaded_settings = {}
        self.filtered_results = []
        self.search_worker = None
        self.shuffled_prompt_deck = []
        self.is_automating = False    
        self.is_programmatic_change = False
        
        # 베이스 프롬프트
        self.base_prefix_prompt = ""
        self.base_suffix_prompt = ""
        self.base_neg_prompt = ""
        
        # 랜덤 해상도
        self.random_resolutions = [
            (1024, 1024, "1:1 Square"), 
            (960, 1088, "Portrait"), 
            (896, 1152, "Portrait"),
            (832, 1216, "Tall Portrait"), 
            (1088, 960, "Landscape"), 
            (1152, 896, "Landscape"),
            (1216, 832, "Wide Landscape")
        ]      
    
    @property
    def tag_classifier(self):
        """TagClassifier 지연 로드 — 첫 접근 시 초기화"""
        if self._tag_classifier is None:
            from core.tag_classifier import TagClassifier
            self._tag_classifier = TagClassifier()
        return self._tag_classifier

    def _create_thumbnail(self, image_path):
        """썸네일 생성"""
        thumb_path = get_thumb_path(image_path)
        try:
            img = Image.open(image_path)
            img.thumbnail((150, 150), Image.LANCZOS)
            img.convert("RGB").save(thumb_path, "JPEG")
        except Exception as e:
            print(f"썸네일 생성 실패 {image_path}: {e}")
    
    def _auto_adjust_text_edit_height(self, text_edit):
        """텍스트 에디트 높이 자동 조절"""
        doc = text_edit.document()
        layout = doc.documentLayout()
        layout.blockBoundingRect(doc.firstBlock()) 
        doc_height = layout.documentSize().height()
        margins = text_edit.contentsMargins()
        new_height = doc_height + margins.top() + margins.bottom() + 15
        min_h = text_edit.minimumHeight()
        final_height = max(min_h, new_height)
        text_edit.setFixedHeight(int(final_height))
    
    def showEvent(self, event):
        """창 표시 이벤트"""
        super().showEvent(event)
        
        # 모든 텍스트 에디트 높이 조절
        all_text_edits = []
        if hasattr(self, 'total_prompt_display'):
            all_text_edits.append(self.total_prompt_display)
        if hasattr(self, 'prefix_prompt_text'):
            all_text_edits.append(self.prefix_prompt_text)
        if hasattr(self, 'main_prompt_text'):
            all_text_edits.append(self.main_prompt_text)
        if hasattr(self, 'suffix_prompt_text'):
            all_text_edits.append(self.suffix_prompt_text)
        if hasattr(self, 'neg_prompt_text'):
            all_text_edits.append(self.neg_prompt_text)
        if hasattr(self, 'exclude_prompt_local_input'):
            all_text_edits.append(self.exclude_prompt_local_input)
            
        for editor in all_text_edits:
            QTimer.singleShot(
                100, 
                lambda w=editor: self._auto_adjust_text_edit_height(w)
            )
def _apply_removal_filters(self, tags_list):
        """제거 옵션 적용 (공통)"""
        result = []
        
        # 메타 태그 목록
        meta_tags = {
            'original', 'highres', 'absurdres', 'incredibly_absurdres', 
            'huge_filesize', 'commentary', 'commentary_request',
            'translated', 'translation_request', 'check_translation',
            'partial_commentary', 'english_commentary', 'japanese_commentary',
            'bad_id', 'bad_pixiv_id', 'bad_twitter_id'
        }
        
        for tag in tags_list:
            tag_lower = tag.lower().strip()
            
            # 작가명 제거
            if self.chk_remove_artist.isChecked():
                if tag_lower in self.tag_classifier.artists:
                    continue
                if tag_lower.startswith('artist:'):
                    continue
            
            # 작품명 제거
            if self.chk_remove_copyright.isChecked():
                if tag_lower in self.tag_classifier.copyrights:
                    continue
            
            # 메타 제거 (original 포함!)
            if self.chk_remove_meta.isChecked():
                if tag_lower in meta_tags:
                    continue
                if self.tag_classifier.classify_tag(tag) == "art_style":
                    continue
            
            # 검열 제거
            if hasattr(self, 'chk_remove_censorship') and self.chk_remove_censorship.isChecked():
                if self.tag_classifier.is_censorship_tag(tag):
                    continue
            
            # 텍스트 제거
            if hasattr(self, 'chk_remove_text') and self.chk_remove_text.isChecked():
                if self.tag_classifier.is_text_tag(tag):
                    continue
            
            result.append(tag)
        
        return result        
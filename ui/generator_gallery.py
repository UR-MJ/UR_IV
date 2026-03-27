# ui/generator_gallery.py
"""
갤러리 및 이미지 관리 로직
"""
import os
import json
from PyQt6.QtWidgets import QListWidgetItem, QMessageBox, QMenu
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QGuiApplication, QAction

from config import OUTPUT_DIR, FAVORITES_FILE
from utils.theme_manager import get_color
from core.image_utils import exif_for_display, move_to_trash
from widgets.thumbnail import ThumbnailItem
from widgets.image_viewer import FullScreenImageViewer
from tabs.gallery_tab import ImagePreviewDialog


class GalleryMixin:
    """갤러리 관련 로직을 담당하는 Mixin"""
    
    # ==================== 갤러리 기본 ====================
    
    def setup_viewer_context_menu(self):
        """뷰어 라벨에 우클릭 메뉴 설정"""
        self.viewer_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.viewer_label.customContextMenuRequested.connect(self._on_viewer_context_menu)

    def _on_viewer_context_menu(self, pos):
        """T2I 뷰어 우클릭 메뉴"""
        if not hasattr(self, 'current_image_path') or not self.current_image_path:
            return
        if not os.path.exists(self.current_image_path):
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {get_color('bg_button')}; border: 1px solid {get_color('border')}; color: {get_color('text_primary')};
            }}
            QMenu::item {{ padding: 6px 24px; }}
            QMenu::item:selected {{ background-color: {get_color('accent')}; }}
        """)

        action_i2i = QAction("🖼️ I2I로 보내기", self)
        action_inpaint = QAction("🎨 Inpaint로 보내기", self)
        action_editor = QAction("✏️ Editor로 보내기", self)

        action_i2i.triggered.connect(lambda: self._send_to_tab("i2i"))
        action_inpaint.triggered.connect(lambda: self._send_to_tab("inpaint"))
        action_editor.triggered.connect(lambda: self._send_to_tab("editor"))

        menu.addAction(action_i2i)
        menu.addAction(action_inpaint)
        menu.addAction(action_editor)

        menu.exec(self.viewer_label.mapToGlobal(pos))

    def _send_to_tab(self, target: str):
        """현재 이미지를 대상 탭으로 전송"""
        path = self.current_image_path
        if not path or not os.path.exists(path):
            return

        if target == "i2i":
            self.i2i_tab._load_image(path)
            idx = self.center_tabs.indexOf(self.i2i_tab)
        elif target == "inpaint":
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.inpaint_tab.set_image_and_mask(pixmap)
            idx = self.center_tabs.indexOf(self.inpaint_tab)
        elif target == "editor":
            self.mosaic_editor.load_image(path)
            idx = self.center_tabs.indexOf(self.mosaic_editor)
        else:
            return

        if idx >= 0:
            self.center_tabs.setCurrentIndex(idx)

    def add_image_to_gallery(self, filepath):
        """갤러리에 이미지 추가"""
        thumb = ThumbnailItem(filepath, hover_enabled=False)
        thumb.clicked.connect(self.on_thumbnail_clicked)
        thumb.action_triggered.connect(self.on_thumbnail_action)
        
        self.gallery_items.insert(0, thumb)
        self.gallery_layout.insertWidget(0, thumb)
        
        if len(self.gallery_items) > 100:
            old_thumb = self.gallery_items.pop()
            self.gallery_layout.removeWidget(old_thumb)
            old_thumb.deleteLater()

    def on_thumbnail_clicked(self, filepath):
        """썸네일 클릭"""
        for item in self.gallery_items:
            item.set_selected(False)
        
        for item in self.gallery_items:
            if item.filepath == filepath:
                item.set_selected(True)
                break
        
        self.display_image(filepath)
    
    def on_thumbnail_action(self, action_type, filepath):
        """썸네일 액션"""
        if action_type == "load":
            self.load_generation_settings(filepath)
        elif action_type == "delete":
            self.delete_image(filepath)
        elif action_type == "view":
            self.display_image(filepath)
    
    def display_image(self, filepath):
        """이미지 표시"""
        if not os.path.exists(filepath):
            return
        
        self.current_image_path = filepath
        
        if hasattr(self, 'btn_add_favorite'):
            self.btn_add_favorite.setEnabled(True)
        
        pixmap = QPixmap(filepath)
        self.viewer_label.setPixmap(
            pixmap.scaled(
                self.viewer_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
        )
        
        # EXIF 표시
        gen_info = self.generation_data.get(filepath, {})
        if not gen_info:
            from PIL import Image
            try:
                img = Image.open(filepath)
                if 'parameters' in img.info:
                    gen_info = {"prompt": img.info['parameters']}
            except Exception:
                pass

        self.exif_display.setPlainText(exif_for_display(gen_info))

        # 뷰어 정보 바 업데이트 (모던 UI)
        if hasattr(self, 'viewer_info_bar') and isinstance(gen_info, dict):
            w = gen_info.get('width', 0)
            h = gen_info.get('height', 0)
            seed = gen_info.get('seed', '')
            info_parts = []
            if w and h:
                info_parts.append(f"해상도 {w}×{h}")
            if seed:
                info_parts.append(f"시드 {seed}")
            if info_parts:
                self.viewer_info_bar.setText("  |  ".join(info_parts))
                self.viewer_info_bar.show()

        # 즐겨찾기 상태 업데이트
        self._load_favorites_from_file()
        is_favorite = filepath in self.favorites_list
        self._update_favorite_button(is_favorite)
        
        # 선택 표시
        for item in self.gallery_items:
            if hasattr(item, 'filepath') and item.filepath == filepath:
                item.set_selected(True)
            else:
                item.set_selected(False)

    def clear_gallery(self):
        """갤러리 초기화"""
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.current_image_path = None
        
        if hasattr(self, 'btn_add_favorite'):
            self.btn_add_favorite.setEnabled(False)
    
    def delete_image(self, filepath):
        """이미지 삭제"""
        reply = QMessageBox.question(
            self, "확인", 
            f"{os.path.basename(filepath)}을(를) 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            move_to_trash(filepath)
            
            for i, item in enumerate(self.gallery_items):
                if item.filepath == filepath:
                    self.gallery_layout.removeWidget(item)
                    self.gallery_items.pop(i)
                    item.deleteLater()
                    break
            if hasattr(self, '_update_history_count'):
                self._update_history_count()

            if self.current_image_path == filepath:
                self.viewer_label.clear()
                self.viewer_label.setText("이미지가 삭제되었습니다.")
                self.exif_display.clear()
                self.current_image_path = None
    
    def select_prev_image(self):
        """이전 이미지 선택"""
        if not self.current_image_path or not self.gallery_items:
            return
        
        current_idx = -1
        for i, item in enumerate(self.gallery_items):
            if item.filepath == self.current_image_path:
                current_idx = i
                break
        
        if current_idx > 0:
            prev_item = self.gallery_items[current_idx - 1]
            self.on_thumbnail_clicked(prev_item.filepath)
    
    def select_next_image(self):
        """다음 이미지 선택"""
        if not self.current_image_path or not self.gallery_items:
            return
        
        current_idx = -1
        for i, item in enumerate(self.gallery_items):
            if item.filepath == self.current_image_path:
                current_idx = i
                break
        
        if current_idx < len(self.gallery_items) - 1:
            next_item = self.gallery_items[current_idx + 1]
            self.on_thumbnail_clicked(next_item.filepath)
    
    def copy_image_to_clipboard(self):
        """이미지를 클립보드에 복사"""
        if not self.current_image_path:
            return
        
        pixmap = QPixmap(self.current_image_path)
        clipboard = QGuiApplication.clipboard()
        clipboard.setPixmap(pixmap)
        
        self.show_status("📋 이미지가 클립보드에 복사되었습니다.", 2000)
    
    def open_fullscreen_viewer(self):
        """전체 화면 뷰어 열기"""
        if not self.current_image_path:
            return
        
        viewer = FullScreenImageViewer(self.current_image_path, self)
        viewer.exec()

    # ==================== 즐겨찾기 ====================
    
    def _load_favorites_from_file(self):
        """즐겨찾기 파일에서 로드"""
        if not hasattr(self, 'favorites_list'):
            self.favorites_list = []
        
        try:
            if os.path.exists(FAVORITES_FILE):
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    self.favorites_list = json.load(f)
                self.favorites_list = [p for p in self.favorites_list if os.path.exists(p)]
        except Exception as e:
            print(f"즐겨찾기 로드 실패: {e}")
            self.favorites_list = []

    def _save_favorites_to_file(self):
        """즐겨찾기 파일에 저장"""
        try:
            with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.favorites_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"즐겨찾기 저장 실패: {e}")

    def add_to_favorites(self):
        """현재 이미지를 즐겨찾기에 추가/제거"""
        if not self.current_image_path:
            QMessageBox.warning(self, "알림", "선택된 이미지가 없습니다.")
            return
        
        self._load_favorites_from_file()
        
        if self.current_image_path in self.favorites_list:
            self.favorites_list.remove(self.current_image_path)
            self._save_favorites_to_file()
            self._update_favorite_button(False)
            QMessageBox.information(self, "완료", "즐겨찾기에서 제거되었습니다.")
        else:
            self.favorites_list.append(self.current_image_path)
            self._save_favorites_to_file()
            self._update_favorite_button(True)
            QMessageBox.information(self, "완료", "즐겨찾기에 추가되었습니다.")

    def _update_favorite_button(self, is_favorite):
        """즐겨찾기 버튼 상태 업데이트"""
        if is_favorite:
            self.btn_add_favorite.setText("💛 즐겨찾기 제거")
            self.btn_add_favorite.setStyleSheet(f"""
                QPushButton {{
                    background-color: #FFC107;
                    border: 1px solid #FFA000;
                    color: {get_color('bg_primary')};
                    font-weight: bold;
                    border-radius: 0px;
                }}
                QPushButton:hover {{ background-color: #FFD54F; }}
            """)
        else:
            self.btn_add_favorite.setText("⭐ 즐겨찾기 추가 (FAV)")
            self.btn_add_favorite.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color('bg_button')};
                    border: 1px solid #FFC107;
                    color: #FFC107;
                    font-weight: bold;
                    border-radius: 0px;
                }}
                QPushButton:hover {{
                    background-color: #FFC107;
                    color: {get_color('bg_primary')};
                }}
            """)

    def _add_favorite_thumbnail(self, filepath):
        """즐겨찾기에 썸네일 추가"""
        thumb = ThumbnailItem(filepath, size=150)
        thumb.clicked.connect(self._on_fav_clicked)
        thumb.action_triggered.connect(self._on_fav_action)

        if hasattr(self, 'fav_flow_layout'):
            self.fav_flow_layout.addWidget(thumb)

    def _on_fav_clicked(self, filepath):
        """즐겨찾기 아이템 클릭 - 이미지 미리보기 + EXIF"""
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "오류", "파일이 존재하지 않습니다.")
            return

        self.current_image_path = filepath

        # EXIF 읽기
        exif_text = ""
        try:
            from PIL import Image
            img = Image.open(filepath)
            if 'parameters' in img.info:
                exif_text = img.info['parameters']
            elif img.info:
                exif_text = "\n".join(
                    f"{k}: {v}" for k, v in img.info.items() if isinstance(v, str)
                )
        except Exception:
            pass

        dlg = ImagePreviewDialog(filepath, exif_text, self)
        # T2I 전송 시그널 연결 (Gallery 탭과 동일)
        if hasattr(self, 'gallery_tab'):
            dlg.send_prompt_signal.connect(
                lambda p, n: self.gallery_tab.send_prompt_signal.emit(p, n)
            )
            dlg.generate_signal.connect(
                lambda payload: self.gallery_tab.generate_signal.emit(payload)
            )
            dlg.send_to_queue_signal.connect(
                lambda payload: self.gallery_tab.send_to_queue_signal.emit(payload)
            )
        dlg.exec()

    def _on_fav_action(self, action_type, filepath):
        """즐겨찾기 썸네일 우클릭 액션"""
        if action_type == "load":
            self.load_generation_settings(filepath)
        elif action_type == "delete":
            self._remove_from_favorites(filepath)
        elif action_type == "view":
            self._on_fav_clicked(filepath)

    def _remove_from_favorites(self, filepath):
        """즐겨찾기에서 제거"""
        self._load_favorites_from_file()
        if filepath in self.favorites_list:
            self.favorites_list.remove(filepath)
            self._save_favorites_to_file()
            self.refresh_favorites()

    def refresh_favorites(self):
        """즐겨찾기 새로고침"""
        self._load_favorites_from_file()
        
        if hasattr(self, 'fav_flow_layout'):
            while self.fav_flow_layout.count():
                item = self.fav_flow_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            for filepath in self.favorites_list:
                if os.path.exists(filepath):
                    self._add_favorite_thumbnail(filepath)

    def clear_all_favorites(self):
        """모든 즐겨찾기 삭제"""
        self._load_favorites_from_file()
        
        if not self.favorites_list:
            QMessageBox.information(self, "알림", "삭제할 항목이 없습니다.")
            return
        
        reply = QMessageBox.question(
            self, "확인",
            f"즐겨찾기 {len(self.favorites_list)}개를 모두 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.favorites_list = []
            self._save_favorites_to_file()
            self.refresh_favorites()
            QMessageBox.information(self, "완료", "모든 즐겨찾기가 삭제되었습니다.")

    # ==================== 설정 불러오기 ====================
    
    def load_generation_settings(self, filepath):
        """생성 설정 불러오기"""
        gen_info = self.generation_data.get(filepath, {})
        
        if not gen_info:
            from PIL import Image
            try:
                img = Image.open(filepath)
                if 'parameters' in img.info:
                    raw_info = img.info['parameters']
                    self._parse_and_apply_prompt_filtered(raw_info)
                    return
            except Exception:
                pass

            QMessageBox.warning(self, "알림", "이 이미지의 생성 정보가 없습니다.")
            return
        
        prompt = gen_info.get('prompt', '')
        self._apply_filtered_prompt(prompt)
        
        QMessageBox.information(self, "완료", "프롬프트를 불러왔습니다. (작가/선행/후행 제외)")
        
    def _apply_filtered_prompt(self, prompt):
        """필터링된 프롬프트 적용"""
        tags = [t.strip() for t in prompt.split(',') if t.strip()]
        
        classified = self.tag_classifier.classify_tags_for_event(tags)
        filtered_tags = self._apply_removal_filters(tags)
        classified = self.tag_classifier.classify_tags_for_event(filtered_tags)
        
        self.is_programmatic_change = True
        
        self.char_count_input.setText(", ".join(classified["count"]))
        self.character_input.setText(", ".join(classified["character"]))
        self.copyright_input.setText(", ".join(classified["copyright"]))
        
        main_tags = (
            classified["appearance"] + 
            classified["expression"] + 
            classified["action"] + 
            classified["background"] + 
            classified["composition"] + 
            classified["effect"] + 
            classified["objects"] + 
            classified["costume"] +
            classified["general"]
        )
        self.main_prompt_text.setPlainText(", ".join(main_tags))
        
        self.is_programmatic_change = False
        self.update_total_prompt_display()

    def _parse_and_apply_prompt_filtered(self, raw_text):
        """Raw 텍스트에서 프롬프트만 추출"""
        parts = raw_text.split('\nNegative prompt:')
        prompt = parts[0].strip()
        self._apply_filtered_prompt(prompt)
            
    def _apply_removal_filters(self, tags: list) -> list:
        """제거 토글에 따라 태그 필터링"""
        filtered = []

        for tag in tags:
            tag_lower = tag.lower().strip()

            if self.chk_remove_artist.isChecked():
                if tag_lower.startswith('artist:') or tag_lower in self._get_known_artists():
                    continue

            if self.chk_remove_copyright.isChecked():
                if self.tag_classifier.classify_tag(tag) == "copyright":
                    continue

            if hasattr(self, 'chk_remove_character') and self.chk_remove_character.isChecked():
                if tag_lower in self.tag_classifier.characters:
                    continue

            if self.chk_remove_meta.isChecked():
                if self.tag_classifier.is_meta_tag(tag):
                    continue

            if hasattr(self, 'chk_remove_censorship') and self.chk_remove_censorship.isChecked():
                if self.tag_classifier.is_censorship_tag(tag):
                    continue

            if hasattr(self, 'chk_remove_text') and self.chk_remove_text.isChecked():
                if self.tag_classifier.is_text_tag(tag):
                    continue

            filtered.append(tag)

        return filtered

    def _get_known_artists(self) -> set:
        """알려진 작가 목록 반환"""
        current_artist = self.artist_input.toPlainText().strip().lower()
        artists = set()
        if current_artist:
            artists.add(current_artist)
        return artists
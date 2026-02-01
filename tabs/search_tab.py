# tabs/search_tab.py
import os
import json
import random
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QGroupBox, QCheckBox, QFileDialog, QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt
from workers.search_worker import PandasSearchWorker
from widgets.search_preview import SearchPreviewCard  # ← 추가!
from config import PARQUET_DIR


class SearchTab(QWidget):
    """Danbooru 검색 탭"""


    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_ui = parent
        self.search_worker = None
        self.current_preview_index = 0
        self.preview_results = []
        self.original_results = []
        
        # 메인 레이아웃 (스크롤 영역)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 스크롤 영역 생성
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        # 스크롤 내용 컨테이너
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # === 기존 UI 코드 (layout에 추가) ===
        # 1. 제목
        layout.addWidget(QLabel("<h2>🔍 Danbooru Pro Search</h2>"))
        
        # 2. 등급 선택
        rating_group = QGroupBox("검색 범위 (Rating)")
        rating_layout = QHBoxLayout(rating_group)
        
        self.chk_g = QCheckBox("General (g)")
        self.chk_g.setChecked(True)
        self.chk_s = QCheckBox("Sensitive (s)")
        self.chk_q = QCheckBox("Questionable (q)")
        self.chk_e = QCheckBox("Explicit (e)")
        
        for chk in [self.chk_g, self.chk_s, self.chk_q, self.chk_e]:
            chk.setStyleSheet("font-weight: bold; font-size: 14px; margin-right: 10px;")
            rating_layout.addWidget(chk)
        rating_layout.addStretch()
        layout.addWidget(rating_group)
        
        # 3. 포함 검색
        search_group = QGroupBox("검색 (포함)") 
        grid = QVBoxLayout(search_group) 
        
        row1 = QHBoxLayout()
        self.input_copyright = QLineEdit()
        self.input_copyright.setPlaceholderText(
            "Copyright (예: pokemon, [genshin|honkai])"
        )
        self.input_character = QLineEdit()
        self.input_character.setPlaceholderText("Character (예: hatsune_miku)")
        
        row1.addWidget(QLabel("저작권:"))
        row1.addWidget(self.input_copyright)
        row1.addWidget(QLabel(" 캐릭터:"))
        row1.addWidget(self.input_character)
        grid.addLayout(row1)
        
        row2 = QHBoxLayout()
        self.input_artist = QLineEdit()
        self.input_artist.setPlaceholderText("Artist (작가명)")
        self.input_general = QLineEdit()
        self.input_general.setPlaceholderText(
            "General (예: 1boy, [blue_hair|red_hair])"
        )
        
        row2.addWidget(QLabel("작가명:"))
        row2.addWidget(self.input_artist)
        row2.addWidget(QLabel(" 일반태그:"))
        row2.addWidget(self.input_general)
        grid.addLayout(row2)
        layout.addWidget(search_group)

        # 4. 제외 검색
        exclude_group = QGroupBox("제외할 태그 (제외)")
        exclude_group.setStyleSheet(
            "QGroupBox { border: 1px solid #c0392b; } "
            "QGroupBox::title { color: #e74c3c; }"
        )
        grid_ex = QVBoxLayout(exclude_group)
        
        row1_ex = QHBoxLayout()
        self.exclude_copyright = QLineEdit()
        self.exclude_copyright.setPlaceholderText("제외할 Copyright")
        self.exclude_character = QLineEdit()
        self.exclude_character.setPlaceholderText("제외할 Character")
        
        row1_ex.addWidget(QLabel("저작권:"))
        row1_ex.addWidget(self.exclude_copyright)
        row1_ex.addWidget(QLabel(" 캐릭터:"))
        row1_ex.addWidget(self.exclude_character)
        grid_ex.addLayout(row1_ex)
        
        row2_ex = QHBoxLayout()
        self.exclude_artist = QLineEdit()
        self.exclude_artist.setPlaceholderText("제외할 Artist")
        self.exclude_general = QLineEdit()
        self.exclude_general.setPlaceholderText(
            "제외할 General (예: comic, [monochrome|greyscale])"
        )
        
        row2_ex.addWidget(QLabel("작가명:"))
        row2_ex.addWidget(self.exclude_artist)
        row2_ex.addWidget(QLabel(" 일반태그:"))
        row2_ex.addWidget(self.exclude_general)
        grid_ex.addLayout(row2_ex)
        layout.addWidget(exclude_group)
        
        # 엔터키 연결
        inputs = [
            self.input_copyright, self.input_character, 
            self.input_artist, self.input_general,
            self.exclude_copyright, self.exclude_character, 
            self.exclude_artist, self.exclude_general
        ]
        for inp in inputs:
            inp.returnPressed.connect(self.start_pandas_search)
        
        # 5. 검색 버튼
        btn_layout = QHBoxLayout()
        
        self.btn_search = QPushButton("🚀 고속 검색 시작")
        self.btn_search.setFixedHeight(45)
        self.btn_search.setStyleSheet(
            "background-color: #4CAF50; color: white; "
            "font-weight: bold; font-size: 15px; border-radius: 6px;"
        )
        self.btn_search.clicked.connect(self.start_pandas_search)

        btn_layout.addWidget(self.btn_search, 2)
        layout.addLayout(btn_layout)
        
        # 6. 상태 표시
        self.lbl_status = QLabel("준비 완료")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(
            "color: #FFD700; font-weight: bold; margin: 5px;"
        )
        layout.addWidget(self.lbl_status)
        
        # 7. 미리보기 (카드 형식으로 변경!)
        preview_group = QGroupBox("검색 결과 확인")
        pv_layout = QVBoxLayout(preview_group)
        
        tip_label = QLabel(
            "💡 <b>검색 팁:</b> 쉼표(,)는 <b>AND</b>, "
            "[A|B]는 <b>OR (A 또는 B)</b> 입니다. "
            "제외 칸에 입력 시 해당 조건이 <b>포함된</b> 결과가 제외됩니다."
        )
        tip_label.setStyleSheet("color: #AAA; font-size: 12px; margin-bottom: 5px;")
        tip_label.setWordWrap(True)
        pv_layout.addWidget(tip_label)

        # 인덱스 표시
        self.lbl_preview_index = QLabel("[ 0 / 0 ]")
        self.lbl_preview_index.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_index.setStyleSheet("color: #888; font-size: 12px;")
        pv_layout.addWidget(self.lbl_preview_index)

        # 카드형 미리보기 위젯
        self.search_preview_card = SearchPreviewCard()
        self.search_preview_card.setMinimumHeight(250)  # 최소 높이 추가
        self.search_preview_card.setMaximumHeight(400)  # 최대 높이 제한
        self.search_preview_card.apply_clicked.connect(self.apply_current_preview)
        self.search_preview_card.add_to_queue_clicked.connect(self._on_add_to_queue)
        self.search_preview_card.next_clicked.connect(self.show_random_preview)
        pv_layout.addWidget(self.search_preview_card)

        # 네비게이션 버튼
        nav_btn_layout = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 이전")
        self.btn_random_view = QPushButton("🎲 랜덤 보기")
        self.btn_next = QPushButton("다음 ▶")
        
        for btn in [self.btn_prev, self.btn_random_view, self.btn_next]:
            btn.setFixedHeight(35)
            btn.setEnabled(False)
            nav_btn_layout.addWidget(btn)

        self.btn_prev.clicked.connect(self.show_prev_preview)
        self.btn_random_view.clicked.connect(self.show_random_preview)
        self.btn_next.clicked.connect(self.show_next_preview)
        pv_layout.addLayout(nav_btn_layout)
        layout.addWidget(preview_group)

        # 8. 집중 검색 (결과 내 필터링)
        focus_group = QGroupBox("집중 검색 (결과 내 필터링)")
        focus_layout = QHBoxLayout(focus_group)
        
        self.focus_include = QLineEdit()
        self.focus_include.setPlaceholderText(
            "포함할 태그 (예: 1boy, [blue_hair|red_hair])"
        )
        self.focus_exclude = QLineEdit()
        self.focus_exclude.setPlaceholderText("제외할 태그")
        
        self.btn_focus_search = QPushButton("필터링 적용")
        self.btn_focus_search.clicked.connect(self.apply_focus_search)
        
        focus_layout.addWidget(QLabel("포함:"))
        focus_layout.addWidget(self.focus_include)
        focus_layout.addWidget(QLabel("제외:"))
        focus_layout.addWidget(self.focus_exclude)
        focus_layout.addWidget(self.btn_focus_search)
        layout.addWidget(focus_group)
        
        # 9. 데이터 관리
        bottom_group = QGroupBox("데이터 관리")
        bl = QHBoxLayout(bottom_group)
        
        self.btn_export = QPushButton("결과 내보내기 (.parquet)")
        self.btn_export.clicked.connect(self.export_results)
        self.btn_export.setEnabled(False)
        
        self.btn_import = QPushButton("결과 불러오기 (.parquet)")
        self.btn_import.clicked.connect(self.import_results)
        
        bl.addWidget(self.btn_export)
        bl.addWidget(self.btn_import)
        layout.addWidget(bottom_group)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def _get_criteria_dict(self) -> dict:
        """현재 검색 조건을 딕셔너리로 반환"""
        return {
            "include": {
                "copyright": self.input_copyright.text(),
                "character": self.input_character.text(),
                "artist": self.input_artist.text(),
                "general": self.input_general.text()
            },
            "exclude": {
                "copyright": self.exclude_copyright.text(),
                "character": self.exclude_character.text(),
                "artist": self.exclude_artist.text(),
                "general": self.exclude_general.text()
            },
            "focus": {
                "include": self.focus_include.text(),
                "exclude": self.focus_exclude.text()
            },
            "ratings": {
                "g": self.chk_g.isChecked(),
                "s": self.chk_s.isChecked(),
                "q": self.chk_q.isChecked(),
                "e": self.chk_e.isChecked()
            }
        }

    def _apply_criteria_dict(self, criteria: dict):
        """딕셔너리에서 검색 조건을 UI에 적용"""
        inc = criteria.get("include", {})
        self.input_copyright.setText(inc.get("copyright", ""))
        self.input_character.setText(inc.get("character", ""))
        self.input_artist.setText(inc.get("artist", ""))
        self.input_general.setText(inc.get("general", ""))

        exc = criteria.get("exclude", {})
        self.exclude_copyright.setText(exc.get("copyright", ""))
        self.exclude_character.setText(exc.get("character", ""))
        self.exclude_artist.setText(exc.get("artist", ""))
        self.exclude_general.setText(exc.get("general", ""))

        focus = criteria.get("focus", {})
        self.focus_include.setText(focus.get("include", ""))
        self.focus_exclude.setText(focus.get("exclude", ""))

        ratings = criteria.get("ratings", {})
        self.chk_g.setChecked(ratings.get("g", True))
        self.chk_s.setChecked(ratings.get("s", False))
        self.chk_q.setChecked(ratings.get("q", False))
        self.chk_e.setChecked(ratings.get("e", False))

    def start_pandas_search(self):
        """검색 시작"""
        ratings = []
        if self.chk_g.isChecked(): ratings.append('g')
        if self.chk_s.isChecked(): ratings.append('s')
        if self.chk_q.isChecked(): ratings.append('q')
        if self.chk_e.isChecked(): ratings.append('e')
        
        if not ratings:
            QMessageBox.warning(self, "경고", "최소 하나의 등급(Rating)을 선택해주세요.")
            return

        queries = {
            'copyright': self.input_copyright.text().strip(),
            'character': self.input_character.text().strip(),
            'artist': self.input_artist.text().strip(),
            'general': self.input_general.text().strip()
        }
        
        exclude_queries = {
            'copyright': self.exclude_copyright.text().strip(),
            'character': self.exclude_character.text().strip(),
            'artist': self.exclude_artist.text().strip(),
            'general': self.exclude_general.text().strip()
        }
        
        if not any(queries.values()) and not any(exclude_queries.values()):
            QMessageBox.warning(self, "경고", "검색 조건을 하나 이상 입력해주세요.")
            return

        self.btn_search.setEnabled(False)
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.terminate()
            self.search_worker.wait()
            
        self.search_worker = PandasSearchWorker(
            PARQUET_DIR, ratings, queries, exclude_queries
        )
        self.search_worker.status_update.connect(self.lbl_status.setText)
        self.search_worker.results_ready.connect(self.on_search_finished)
        self.search_worker.start()

    def on_search_finished(self, results, total_count):
        """검색 완료 처리"""
        self.btn_search.setEnabled(True)
        self.original_results = results 
        self.preview_results = results  
        self.current_preview_index = 0
        
        # 부모 UI에 결과 전달
        self._update_parent_results(results)
            
        if results:
            self.update_preview_display()
            self.btn_export.setEnabled(True)
            self._set_nav_buttons_enabled(True)
            self.lbl_status.setText(f"✅ 검색 완료: {total_count:,} 건")
        else:
            self.search_preview_card.clear()
            self.lbl_preview_index.setText("[ 0 / 0 ]")
            self.btn_export.setEnabled(False)
            self._set_nav_buttons_enabled(False)
            
    def _set_nav_buttons_enabled(self, enabled):
        """네비게이션 버튼 활성화/비활성화"""
        for btn in [self.btn_prev, self.btn_random_view, self.btn_next]:
            btn.setEnabled(enabled)

    def apply_focus_search(self):
        """결과 내 재검색 (집중 검색)"""
        if not self.original_results:
            QMessageBox.warning(
                self, "알림", 
                "먼저 기본 검색을 수행하여 데이터를 불러와야 합니다."
            )
            return

        inc_text = self.focus_include.text().strip()
        exc_text = self.focus_exclude.text().strip()
        
        if not inc_text and not exc_text:
            self.preview_results = self.original_results
            self._update_parent_results(self.preview_results)
            self.on_search_finished(self.preview_results, len(self.preview_results))
            return

        try:
            df = pd.DataFrame(self.original_results)
            
            df['__all_text__'] = (
                df['general'].astype(str) + " " +
                df['character'].astype(str) + " " +
                df['copyright'].astype(str) + " " +
                df['artist'].astype(str)
            )

            total_mask = pd.Series(True, index=df.index)
            
            if inc_text:
                mask_inc = PandasSearchWorker._parse_condition(
                    df, '__all_text__', inc_text
                )
                total_mask &= mask_inc
            
            if exc_text:
                mask_exc = PandasSearchWorker._parse_condition(
                    df, '__all_text__', exc_text
                )
                total_mask &= ~mask_exc
            
            filtered_df = df[total_mask]
            
            if '__all_text__' in filtered_df.columns:
                filtered_df = filtered_df.drop(columns=['__all_text__'])
                
            filtered_results = filtered_df.to_dict('records')
            
            self.preview_results = filtered_results
            self.current_preview_index = 0
            
            self._update_parent_results(filtered_results)
            
            self.lbl_status.setText(
                f"🔎 집중 검색 결과: {len(filtered_results):,} 건 "
                f"(원본 {len(self.original_results):,} 건)"
            )
            
            if filtered_results:
                self.update_preview_display()
                self._set_nav_buttons_enabled(True)
            else:
                self.search_preview_card.clear()
                self.lbl_preview_index.setText("[ 0 / 0 ]")
                self._set_nav_buttons_enabled(False)
                
        except Exception as e:
            QMessageBox.warning(self, "오류", f"집중 검색 중 오류 발생: {e}")
            
    def _update_parent_results(self, results):
        """부모 UI에 결과 전달 및 버튼 업데이트"""
        if self.parent_ui:
            import random
            self.parent_ui.filtered_results = results
            self.parent_ui.shuffled_prompt_deck = results.copy()
            random.shuffle(self.parent_ui.shuffled_prompt_deck)
            
            count = len(results)
            self.parent_ui.btn_random_prompt.setText(f"🎲 랜덤 프롬프트 ({count})")
            self.parent_ui.btn_random_prompt.setEnabled(count > 0)
            
    def show_prev_preview(self):
        """이전 미리보기"""
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            self.update_preview_display()

    def show_next_preview(self):
        """다음 미리보기"""
        if self.current_preview_index < len(self.preview_results) - 1:
            self.current_preview_index += 1
            self.update_preview_display()

    def show_random_preview(self):
        """랜덤 미리보기"""
        if self.preview_results:
            self.current_preview_index = random.randint(0, len(self.preview_results) - 1)
            self.update_preview_display()

    def apply_current_preview(self, bundle: dict = None):
        """현재 미리보기 적용"""
        if bundle is None:
            if not self.preview_results: 
                return
            bundle = self.preview_results[self.current_preview_index]
        
        if self.parent_ui:
            self.parent_ui.apply_prompt_from_data(bundle)
            self.parent_ui.show_status("✅ 프롬프트가 적용되었습니다.")
    
    def _on_add_to_queue(self, bundle: dict):
        """대기열에 추가"""
        if not self.parent_ui:
            return
        
        # 먼저 적용
        self.parent_ui.apply_prompt_from_data(bundle)
        
        # payload 생성 후 대기열에 추가
        if hasattr(self.parent_ui, '_build_current_payload') and hasattr(self.parent_ui, 'queue_panel'):
            payload = self.parent_ui._build_current_payload()
            repeat_count = self.parent_ui.automation_widget.get_settings().get('repeat_per_prompt', 1)
            self.parent_ui.queue_panel.add_items_as_group([payload], repeat_count)
            self.parent_ui.show_status(f"✅ 대기열에 {repeat_count}개 추가됨")

    def export_results(self):
        """결과 내보내기"""
        if not self.preview_results: 
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "검색 결과 저장", "", "Parquet Files (*.parquet)"
        )
        if file_path:
            try:
                df = pd.DataFrame(self.preview_results)
                df.to_parquet(file_path)
                QMessageBox.information(self, "성공", "저장 완료")
            except Exception as e: 
                QMessageBox.critical(self, "오류", f"저장 실패: {e}")

    def import_results(self):
        """결과 불러오기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "결과 불러오기", "", "Parquet Files (*.parquet)"
        )
        if file_path:
            try:
                df = pd.read_parquet(file_path)
                results = df.to_dict('records')
                self.original_results = results
                self.on_search_finished(results, len(results))
                QMessageBox.information(self, "성공", f"{len(results)}건 불러옴")
            except Exception as e: 
                QMessageBox.critical(self, "오류", f"실패: {e}")
                
    def update_preview_display(self):
        """미리보기 업데이트 (카드 형식)"""
        if not self.preview_results:
            self.search_preview_card.clear()
            self.lbl_preview_index.setText("[ 0 / 0 ]")
            return
        
        data = self.preview_results[self.current_preview_index]
        total = len(self.preview_results)
        
        # 인덱스 표시
        self.lbl_preview_index.setText(f"[ {self.current_preview_index + 1} / {total} ]")
        
        # 카드에 데이터 설정
        self.search_preview_card.set_bundle(data)
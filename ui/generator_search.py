# ui/generator_search.py
"""
검색 결과 관련 로직
"""
import random
from PyQt6.QtWidgets import QMessageBox
from widgets.search_preview import SearchPreviewCard


class SearchMixin:
    """검색 기능 Mixin"""
    
    def _setup_search_preview(self, layout):
        """검색 미리보기 위젯 설정 (검색 탭 UI에서 호출)"""
        self.search_preview = SearchPreviewCard()
        self.search_preview.apply_clicked.connect(self._on_preview_apply)
        self.search_preview.add_to_queue_clicked.connect(self._on_preview_add_queue)
        self.search_preview.next_clicked.connect(self.show_random_preview)
        
        layout.addWidget(self.search_preview)
    
    def show_random_preview(self):
        """랜덤 미리보기 표시"""
        if not self.filtered_results:
            QMessageBox.warning(self, "알림", "검색 결과가 없습니다.")
            return
        
        bundle = random.choice(self.filtered_results)
        self.search_preview.set_bundle(bundle)
    
    def _on_preview_apply(self, bundle: dict):
        """미리보기에서 적용 클릭"""
        self.apply_prompt_from_data(bundle)
        self.show_status("✅ 프롬프트가 적용되었습니다.")
    
    def _on_preview_add_queue(self, bundle: dict):
        """미리보기에서 대기열 추가 클릭"""
        # payload 생성
        self.apply_prompt_from_data(bundle)
        payload = self._build_current_payload()
        
        # 반복 횟수 가져오기
        repeat_count = self.automation_widget.get_settings().get('repeat_per_prompt', 1)
        
        # 대기열에 추가
        self.queue_panel.add_items_as_group([payload], repeat_count)
        self.show_status(f"✅ 대기열에 {repeat_count}개 추가되었습니다.")
    
    def update_search_results_ui(self):
        """검색 결과 UI 업데이트"""
        if self.filtered_results:
            self.shuffled_prompt_deck = self.filtered_results.copy()
            random.shuffle(self.shuffled_prompt_deck)
            
            self.btn_random_prompt.setEnabled(True)
            self.btn_random_prompt.setText(
                f"🎲 랜덤 프롬프트 ({len(self.filtered_results)})"
            )
            self.show_status(
                f"✅ 검색 완료: {len(self.filtered_results):,}건의 프롬프트 로드됨"
            )
            
            # 미리보기도 첫 번째 결과로 업데이트
            if hasattr(self, 'search_preview'):
                self.show_random_preview()
        else:
            self.btn_random_prompt.setEnabled(False)
            self.btn_random_prompt.setText("🎲 랜덤 프롬프트")
            self.shuffled_prompt_deck = []
            
            # 미리보기 초기화
            if hasattr(self, 'search_preview'):
                self.search_preview.clear()
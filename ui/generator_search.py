# ui/generator_search.py
"""
검색 결과 관련 로직
"""
import random
from PyQt6.QtWidgets import QMessageBox


class SearchMixin:
    """검색 기능 Mixin"""
    
    def show_random_preview(self):
        """랜덤 미리보기 표시"""
        if not self.filtered_results:
            QMessageBox.warning(self, "알림", "검색 결과가 없습니다.")
            return
        
        bundle = random.choice(self.filtered_results)
        self.search_preview.set_bundle(bundle)
    
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
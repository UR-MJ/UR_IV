# ui/generator_prompts.py
"""
프롬프트 처리 관련 로직
"""
import re
import random
import pandas as pd
from PyQt6.QtWidgets import QMessageBox
from utils.app_logger import get_logger

_logger = get_logger('prompts')

class PromptHandlingMixin:
    """프롬프트 처리를 담당하는 Mixin 클래스"""
    
    def update_total_prompt_display(self):
        """최종 프롬프트 디스플레이 업데이트"""
        parts = []
        
        # 1. 인물 수
        if self.char_count_input.text().strip(): 
            parts.append(self.char_count_input.text().strip())
            
        # 2. 캐릭터
        if self.character_input.text().strip():
            parts.append(self.character_input.text().strip())

        # 3. 작품 (Copyright)
        if self.copyright_input.text().strip():
            parts.append(self.copyright_input.text().strip())

        # 4. 작가 (Artist) - 작가 필드 내용 추가!
        if self.artist_input.text().strip():
            parts.append(self.artist_input.text().strip())

        # 5. 선행 (Prefix) - 접기와 무관하게 항상 포함
        if self.prefix_prompt_text.toPlainText().strip():
            parts.append(self.prefix_prompt_text.toPlainText().strip())

        # 6. 메인
        if self.main_prompt_text.toPlainText().strip():
            parts.append(self.main_prompt_text.toPlainText().strip())

        # 7. 후행 (Suffix) - 접기와 무관하게 항상 포함
        if self.suffix_prompt_text.toPlainText().strip():
            parts.append(self.suffix_prompt_text.toPlainText().strip())

        # 최종 반영
        self.total_prompt_display.setPlainText(", ".join(parts))
    
    def apply_prompt_from_data(self, bundle):
        """검색 결과 데이터를 프롬프트 입력창에 적용"""
        # 1. 데이터 추출
        general_str = str(bundle.get('general', ''))
        artist_str = str(bundle.get('artist', ''))
        copyright_str = str(bundle.get('copyright', ''))
        character_str = str(bundle.get('character', ''))
        
        if artist_str == 'nan': artist_str = ''
        if copyright_str == 'nan': copyright_str = ''
        if character_str == 'nan': character_str = ''
        if general_str == 'nan': general_str = ''
        
        def to_list(text): 
            return [t.strip() for t in text.split(',') if t.strip()]
        
        # 2. 기본 리스트 생성
        artist_list = [artist_str.replace('artist:', '').strip()] if artist_str else []
        copyright_list = to_list(copyright_str)
        character_list = to_list(character_str)
        general_list = to_list(general_str)

        # ★★★ 'original'은 작품명이 아니므로 제외 ★★★
        copyright_list = [c for c in copyright_list if c.lower() != 'original']
        
        # ★★★ 디버그: 원본 general_list 개수 ★★★
        _logger.debug(f"원본 general_list: {len(general_list)}개")
        
        # 3. 제외 프롬프트 적용
        exclude_text = self.exclude_prompt_local_input.toPlainText()
        exclude_rules = to_list(exclude_text)
        
        # 문법:
        #   keyword        → 정확히 일치하는 태그 제거
        #   __keyword      → keyword로 끝나는 태그 제거  (예: __hair → blue hair)
        #   keyword__      → keyword로 시작하는 태그 제거 (예: hair__ → hair ornament)
        #   __keyword__    → keyword를 포함하는 태그 제거 (예: __username__ → patreon username)
        #   ~keyword       → 예외 (다른 규칙에 걸려도 유지)
        contains_exc, prefix_exc, suffix_exc, exact_exc, excepts = [], [], [], set(), set()
        for r in exclude_rules:
            if r.startswith('~'):
                excepts.add(r[1:].strip())
            elif r.startswith('__') and r.endswith('__') and len(r) > 4:
                contains_exc.append(r[2:-2])
            elif r.startswith('__'):
                prefix_exc.append(r[2:])
            elif r.endswith('__'):
                suffix_exc.append(r[:-2])
            else:
                exact_exc.add(r)

        def _normalize(tag):
            """비교용 정규화: 밑줄 → 공백, 소문자"""
            return tag.replace('_', ' ').strip().lower()

        norm_exact = {_normalize(e) for e in exact_exc}
        norm_excepts = {_normalize(e) for e in excepts}
        norm_contains = [_normalize(c) for c in contains_exc]
        norm_prefix = [_normalize(p) for p in prefix_exc]
        norm_suffix = [_normalize(s) for s in suffix_exc]

        def filter_tags(tags):
            res = []
            for t in tags:
                nt = _normalize(t)
                # 예외 규칙: ~keyword → 무조건 유지
                if nt in norm_excepts:
                    res.append(t)
                    continue
                # 정확히 일치
                if nt in norm_exact:
                    continue
                # 포함 (__keyword__)
                if any(c in nt for c in norm_contains):
                    continue
                # 끝 일치 (__keyword)
                if any(nt.endswith(p) for p in norm_prefix):
                    continue
                # 시작 일치 (keyword__)
                if any(nt.startswith(s) for s in norm_suffix):
                    continue
                res.append(t)
            return res

        artist_list = filter_tags(artist_list)
        copyright_list = filter_tags(copyright_list)
        character_list = filter_tags(character_list)
        general_list = filter_tags(general_list)

        # 4. 제거 토글 적용
        
        # 작가 처리 (고정 vs 제거 vs 적용)
        keep_current_artist = False
        if self.btn_lock_artist.isChecked():
            keep_current_artist = True
            artist_list = []
        elif self.chk_remove_artist.isChecked():
            artist_list = []
        
        # 작품명 제거
        if self.chk_remove_copyright.isChecked(): 
            copyright_list = []

        # 캐릭터 제거
        if hasattr(self, 'chk_remove_character') and self.chk_remove_character.isChecked():
            character_list = []
        
        # ★★★ 디버그: 토글 상태 및 태그 개수 ★★★
        _logger.debug(f"=== 토글 상태 ===")
        _logger.debug(f"메타 제거: {self.chk_remove_meta.isChecked()}")
        _logger.debug(f"검열 제거: {self.chk_remove_censorship.isChecked()}")
        _logger.debug(f"텍스트 제거: {self.chk_remove_text.isChecked()}")
        _logger.debug(f"tag_classifier 존재: {hasattr(self, 'tag_classifier')}")
        _logger.debug(f"censorship_tags 개수: {len(self.tag_classifier.censorship_tags)}")
        _logger.debug(f"text_tags 개수: {len(self.tag_classifier.text_tags)}")
        
        # 메타 제거 (original 포함)
        if self.chk_remove_meta.isChecked():
            before = len(general_list)
            meta_tags = {'original', 'highres', 'absurdres', 'incredibly_absurdres', 
                        'huge_filesize', 'commentary', 'commentary_request',
                        'translated', 'translation_request', 'check_translation',
                        'partial_commentary', 'english_commentary', 'japanese_commentary'}
            general_list = [t for t in general_list if t.lower() not in meta_tags]
            general_list = [t for t in general_list 
                           if self.tag_classifier.classify_tag(t) != "art_style"]
            _logger.debug(f"메타 제거: {before} → {len(general_list)}")

        # 검열 제거
        if self.chk_remove_censorship.isChecked():
            before = len(general_list)
            removed = []
            new_list = []
            for t in general_list:
                if self.tag_classifier.is_censorship_tag(t):
                    removed.append(t)
                else:
                    new_list.append(t)
            general_list = new_list
            _logger.debug(f"검열 제거: {before} → {len(general_list)}, 제거된 태그: {removed}")

        # 텍스트 제거
        if self.chk_remove_text.isChecked():
            before = len(general_list)
            removed = []
            new_list = []
            for t in general_list:
                if self.tag_classifier.is_text_tag(t):
                    removed.append(t)
                else:
                    new_list.append(t)
            general_list = new_list
            _logger.debug(f"텍스트 제거: {before} → {len(general_list)}, 제거된 태그: {removed}")

        # 4.5. general_list에서 이미 분류된 태그 중복 제거
        classified_tags = set()
        
        for c in character_list:
            classified_tags.add(c.lower())
        
        for c in copyright_list:
            classified_tags.add(c.lower())
        
        for a in artist_list:
            classified_tags.add(a.lower())
        
        general_list = [t for t in general_list if t.lower() not in classified_tags]

        # 5. 인물 수 분류
        count_tags = {
            "1boy", "2boys", "3boys", "4boys", "5boys", "6+boys", 
            "1girl", "2girls", "3girls", "4girls", "5girls", "6+girls",
            "1other", "2others", "3others", "4others", "5others", "6+others"
        }
        
        final_count = []
        final_general = []
        
        for t in general_list:
            if t.lower() in count_tags: 
                final_count.append(t)
            else: 
                final_general.append(t)
        
        _logger.debug(f"최종 general: {len(final_general)}개")
        
        # 6. 선행/후행 프롬프트와 중복 제거
        def _norm(tag: str) -> str:
            return tag.replace('_', ' ').strip().lower()

        fixed_tags = set()
        for src in (self.prefix_prompt_text.toPlainText(),
                    self.suffix_prompt_text.toPlainText()):
            for t in src.split(','):
                nt = _norm(t)
                if nt:
                    fixed_tags.add(nt)

        if fixed_tags:
            final_general = [t for t in final_general if _norm(t) not in fixed_tags]
            _logger.debug(f"고정프롬프트 중복 제거 후 general: {len(final_general)}개")

        # 6.5. general 내부 중복 제거
        seen_tags = set()
        deduped_general = []
        for t in final_general:
            nt = _norm(t)
            if nt not in seen_tags:
                seen_tags.add(nt)
                deduped_general.append(t)
        final_general = deduped_general

        # 7. 이스케이프 (가중치 괄호 보존)
        from utils.prompt_cleaner import escape_parentheses
        def escape(tags):
            result = []
            for t in tags:
                if r'\(' in t or r'\)' in t:
                    result.append(t)
                else:
                    result.append(escape_parentheses(t))
            return result

        # 8. UI 업데이트
        self.is_programmatic_change = True
        
        self.char_count_input.setText(", ".join(escape(final_count)))
        self.character_input.setText(", ".join(escape(character_list)))
        self.copyright_input.setText(", ".join(escape(copyright_list)))
        
        if not keep_current_artist:
            self.artist_input.setText(", ".join(escape(artist_list)))
        
        self.main_prompt_text.setPlainText(", ".join(escape(final_general)))

        self.is_programmatic_change = False
        
        # 8. 최종 프롬프트 업데이트
        self.update_total_prompt_display()
        
    def apply_random_prompt(self):
        """랜덤 프롬프트 적용"""
        if not self.shuffled_prompt_deck:
            if self.filtered_results:
                QMessageBox.information(
                    self, "Notice", 
                    "All prompts used once. Reshuffling deck."
                )
                self.shuffled_prompt_deck = self.filtered_results.copy()
                random.shuffle(self.shuffled_prompt_deck)
            else:
                QMessageBox.warning(
                    self, "Error", 
                    "No prompts available. Run a search first."
                )
                return

        random_bundle = self.shuffled_prompt_deck.pop()
        remaining_count = len(self.shuffled_prompt_deck)
        self.show_status(
            f"Prompt selected. Remaining: {remaining_count}"
        )
        
        # 버튼 텍스트 업데이트
        self.btn_random_prompt.setText(f"🎲 랜덤 프롬프트 ({remaining_count})")
        
        # apply_prompt_from_data 호출 (토글 적용됨)
        self.apply_prompt_from_data(random_bundle)
    
    def on_base_prompts_changed(self):
        """베이스 프롬프트 변경 이벤트"""
        if self.is_programmatic_change:
            return
        self.base_prefix_prompt = self.prefix_prompt_text.toPlainText()
        self.base_suffix_prompt = self.suffix_prompt_text.toPlainText()
        self.base_neg_prompt = self.neg_prompt_text.toPlainText()
    
    def load_base_prompt_to_event(self):
        """현재 메인 프롬프트를 이벤트 탭으로 복사"""
        parts = []
        
        if self.char_count_input.text().strip(): 
            parts.append(self.char_count_input.text().strip())
            
        if self.character_input.text().strip():
            parts.append(self.character_input.text().strip())

        if self.copyright_input.text().strip():
            parts.append(self.copyright_input.text().strip())

        if self.artist_input.text().strip():
            parts.append(self.artist_input.text().strip())
            
        if self.main_prompt_text.toPlainText().strip():
            parts.append(self.main_prompt_text.toPlainText().strip())

        base_prompt = ", ".join(parts)
        self.event_gen_tab.base_prompt_view.setPlainText(base_prompt)
    
    def get_prompts_from_bundle(self, bundle):
        """자동화용 프롬프트 생성"""
        general_tags_str = str(bundle.get('general', ''))
        artist = str(bundle.get('artist', ''))
        copyright_tags = str(bundle.get('copyright', ''))
        character_tags = str(bundle.get('character', ''))
        
        if general_tags_str == 'nan': general_tags_str = ''
        if artist == 'nan': artist = ''
        if copyright_tags == 'nan': copyright_tags = ''
        if character_tags == 'nan': character_tags = ''

        def escape_tags(tag_str):
            if not tag_str: 
                return []
            tags = [t.strip() for t in tag_str.split(',') if t.strip()]
            return [t.replace('(', r'\(').replace(')', r'\)') for t in tags]

        artist_list = []
        if not self.chk_remove_artist.isChecked() and artist:
            clean_artist = artist.replace('artist:', '').strip()
            artist_list = escape_tags(clean_artist)

        copyright_list = []
        if not self.chk_remove_copyright.isChecked() and copyright_tags:
            copyright_list = escape_tags(copyright_tags)

        character_list = escape_tags(character_tags)
        general_list = escape_tags(general_tags_str)

        person_count_tags = {
            "1boy", "2boys", "3boys", "4boys", "5boys", "6+boys", 
            "1girl", "2girls", "3girls", "4girls", "5girls", "6+girls",
            "1other", "2others", "3others", "4others", "5others", "6+others"
        }
        
        count_list = []
        main_list = []
        
        for tag in general_list:
            if tag in person_count_tags:
                count_list.append(tag)
            else:
                main_list.append(tag)

        final_parts = []
        
        if count_list: 
            final_parts.append(", ".join(count_list))
        if character_list: 
            final_parts.append(", ".join(character_list))
        if copyright_list: 
            final_parts.append(", ".join(copyright_list))
        if artist_list: 
            final_parts.append(", ".join(artist_list))
        
        prefix = self.prefix_prompt_text.toPlainText().strip()
        if prefix: 
            final_parts.append(prefix)
        
        if main_list: 
            final_parts.append(", ".join(main_list))
        
        suffix = self.suffix_prompt_text.toPlainText().strip()
        if suffix: 
            final_parts.append(suffix)

        final_prompt = ", ".join(final_parts)
        final_neg = self.neg_prompt_text.toPlainText().strip()

        # 와일드카드 치환
        wc_enabled = (hasattr(self, 'settings_tab') and
                      hasattr(self.settings_tab, 'chk_wildcard_enabled') and
                      self.settings_tab.chk_wildcard_enabled.isChecked())
        if wc_enabled:
            from utils.file_wildcard import resolve_file_wildcards
            from utils.wildcard import process_wildcards
            final_prompt = resolve_file_wildcards(final_prompt)
            final_prompt = process_wildcards(final_prompt)
            final_neg = resolve_file_wildcards(final_neg)
            final_neg = process_wildcards(final_neg)

        return final_prompt, final_neg
        
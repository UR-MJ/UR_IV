# utils/prompt_cleaner.py
"""
프롬프트 자동 정리
- 쉼표/공백 정리
- 괄호 이스케이프
- 중복 제거
- 밑줄 처리
"""
import re
from typing import Tuple, List, Optional


class PromptCleaner:
    """프롬프트 자동 정리기"""
    
    def __init__(self):
        # 설정 (기본값)
        self.auto_comma = True           # 쉼표 정리
        self.auto_space = True           # 공백 정리
        self.auto_escape = False         # 괄호 이스케이프
        self.remove_duplicates = False   # 중복 제거
        self.underscore_to_space = True  # 밑줄 → 공백
        self.remove_empty_parens = True  # 빈 괄호 제거
        self.trim_trailing_comma = True  # 마지막 쉼표 제거
    
    def clean(self, text: str) -> str:
        """전체 정리 실행"""
        if not text:
            return ""
        
        result = text
        
        # 1. 공백 정리
        if self.auto_space:
            result = self._clean_spaces(result)
        
        # 2. 쉼표 정리
        if self.auto_comma:
            result = self._clean_commas(result)
        
        # 3. 빈 괄호 제거
        if self.remove_empty_parens:
            result = self._remove_empty_parentheses(result)
        
        # 4. 밑줄 → 공백
        if self.underscore_to_space:
            result = self._convert_underscores(result)
        
        # 5. 중복 제거
        if self.remove_duplicates:
            result = self._remove_duplicate_tags(result)
        
        # 6. 괄호 이스케이프
        if self.auto_escape:
            result = self._escape_parentheses(result)
        
        # 7. 마지막 쉼표 제거
        if self.trim_trailing_comma:
            result = result.rstrip().rstrip(',').strip()
        
        return result
    
    def _clean_spaces(self, text: str) -> str:
        """공백 정리"""
        # 여러 공백 → 단일 공백
        text = re.sub(r' +', ' ', text)
        # 탭, 줄바꿈 → 공백
        text = re.sub(r'[\t\n\r]+', ' ', text)
        return text.strip()
    
    def _clean_commas(self, text: str) -> str:
        """쉼표 정리"""
        # 쉼표 앞 공백 제거
        text = re.sub(r'\s+,', ',', text)
        # 쉼표 뒤 공백 통일
        text = re.sub(r',\s*', ', ', text)
        # 연속 쉼표 제거
        text = re.sub(r',(\s*,)+', ',', text)
        return text
    
    def _remove_empty_parentheses(self, text: str) -> str:
        """빈 괄호 제거"""
        # (), ( ), (,), ( , ) 등 제거
        text = re.sub(r'\(\s*,?\s*\)', '', text)
        text = re.sub(r'\[\s*,?\s*\]', '', text)
        text = re.sub(r'\{\s*,?\s*\}', '', text)
        # 정리 후 연속 공백/쉼표 처리
        text = re.sub(r',\s*,', ',', text)
        text = re.sub(r'\s+', ' ', text)
        return text
    
    def _convert_underscores(self, text: str) -> str:
        """밑줄을 공백으로 변환 (태그 내부만)"""
        # 이스케이프된 밑줄은 유지
        # 단순히 _ → 공백
        # 단, \_ 는 유지
        result = []
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text) and text[i + 1] == '_':
                result.append('_')  # \_ → _
                i += 2
            elif text[i] == '_':
                result.append(' ')
                i += 1
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)
    
    def _remove_duplicate_tags(self, text: str) -> str:
        """중복 태그 제거"""
        tags = [t.strip() for t in text.split(',')]
        seen = set()
        unique_tags = []
        
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower and tag_lower not in seen:
                seen.add(tag_lower)
                unique_tags.append(tag)
        
        return ', '.join(unique_tags)
    
    def _escape_parentheses(self, text: str) -> str:
        """
        괄호 이스케이프 (쉼표 구분 태그 단위로 판단):
        - 태그 전체가 (...)로 감싸진 경우 → SD 가중치/강조 → 바깥 유지, 안쪽 중첩만 이스케이프
          예) (tag:1.2) → (tag:1.2)
              (a (b)) → (a \(b\))
        - 태그 일부에 (...)가 있는 경우 → 수식어 괄호 → 전부 이스케이프
          예) ike (fire emblem) → ike \(fire emblem\)
              kafka (honkai: star rail) (cosplay) → kafka \(honkai: star rail\) \(cosplay\)
        """
        tags = self._split_by_top_level_commas(text)
        escaped = [self._escape_tag(t) for t in tags]
        return ','.join(escaped)

    def _escape_tag(self, tag: str) -> str:
        """개별 태그의 괄호 이스케이프"""
        stripped = tag.strip()
        if not stripped:
            return tag

        # 태그 전체가 (...)로 감싸진 경우 → SD 구문, 바깥 유지
        if stripped.startswith('(') and stripped.endswith(')'):
            close_idx = self._find_matching_close_paren(stripped, 0)
            if close_idx == len(stripped) - 1:
                inner = stripped[1:-1]
                escaped_inner = self._escape_inner_parens(inner)
                lead = tag[:len(tag) - len(tag.lstrip())]
                return f'{lead}({escaped_inner})'

        # 태그 일부에 괄호 → 수식어, 전부 이스케이프
        return self._escape_inner_parens(tag)

    def _split_by_top_level_commas(self, text: str) -> list:
        """괄호 깊이를 고려하여 최상위 쉼표로 분리"""
        parts = []
        current = []
        depth = 0
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text) and text[i + 1] in '()':
                current.append(text[i:i + 2])
                i += 2
                continue
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            if text[i] == ',' and depth <= 0:
                parts.append(''.join(current))
                current = []
                depth = 0
            else:
                current.append(text[i])
            i += 1
        parts.append(''.join(current))
        return parts

    def _escape_inner_parens(self, text: str) -> str:
        """안쪽 내용의 모든 괄호를 이스케이프 (이미 이스케이프된 건 건너뛰기)"""
        result = []
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text) and text[i + 1] in '()':
                result.append(text[i:i + 2])
                i += 2
            elif text[i] == '(':
                result.append(r'\(')
                i += 1
            elif text[i] == ')':
                result.append(r'\)')
                i += 1
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)

    @staticmethod
    def _find_matching_close_paren(text: str, open_idx: int) -> int:
        """깊이 기반으로 대응하는 닫는 괄호 위치를 찾는다"""
        depth = 0
        i = open_idx
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text) and text[i + 1] in '()':
                i += 2  # 이스케이프된 괄호 건너뛰기
                continue
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return -1
    
    def unescape_parentheses(self, text: str) -> str:
        """이스케이프 해제: \(\) → ()"""
        return text.replace(r'\(', '(').replace(r'\)', ')')
    
    def set_options(self, **kwargs):
        """옵션 설정"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def get_options(self) -> dict:
        """현재 옵션 반환"""
        return {
            'auto_comma': self.auto_comma,
            'auto_space': self.auto_space,
            'auto_escape': self.auto_escape,
            'remove_duplicates': self.remove_duplicates,
            'underscore_to_space': self.underscore_to_space,
            'remove_empty_parens': self.remove_empty_parens,
            'trim_trailing_comma': self.trim_trailing_comma,
        }


# 싱글톤
_cleaner_instance = None

def get_prompt_cleaner() -> PromptCleaner:
    global _cleaner_instance
    if _cleaner_instance is None:
        _cleaner_instance = PromptCleaner()
    return _cleaner_instance


def clean_prompt(text: str) -> str:
    """간편 함수: 프롬프트 정리"""
    return get_prompt_cleaner().clean(text)


def escape_parentheses(text: str) -> str:
    """간편 함수: 괄호 이스케이프"""
    cleaner = PromptCleaner()
    return cleaner._escape_parentheses(text)


def unescape_parentheses(text: str) -> str:
    """간편 함수: 이스케이프 해제"""
    return text.replace(r'\(', '(').replace(r'\)', ')')
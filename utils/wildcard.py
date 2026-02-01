# utils/wildcard.py
"""
와일드카드 시스템
- 기본: {A|B|C} → 랜덤 선택
- 가중치: {A:3|B:1|C:1} → A가 60% 확률
- 중첩: {{red|blue} hair|ponytail}
- 범위: {1-10} → 1~10 중 랜덤 숫자
"""
import re
import random
from typing import List, Tuple, Optional


class WildcardProcessor:
    """와일드카드 처리기"""
    
    # 와일드카드 패턴: {내용}
    PATTERN = re.compile(r'\{([^{}]+)\}')
    
    # 범위 패턴: {1-10} 또는 {1-10:2} (step 포함)
    RANGE_PATTERN = re.compile(r'^(\d+)-(\d+)(?::(\d+))?$')
    
    def __init__(self):
        self.history = []  # 최근 선택 기록
        self.max_history = 100
    
    def process(self, text: str) -> str:
        """
        와일드카드 처리 (랜덤 선택)
        중첩된 와일드카드도 처리
        """
        if not text:
            return text
        
        # 중첩 처리를 위해 반복
        prev_text = None
        while prev_text != text:
            prev_text = text
            text = self.PATTERN.sub(self._replace_wildcard, text)
        
        return text
    
    def _replace_wildcard(self, match) -> str:
        """단일 와일드카드 교체"""
        content = match.group(1)
        
        # 범위 체크 {1-10}
        range_match = self.RANGE_PATTERN.match(content.strip())
        if range_match:
            return self._process_range(range_match)
        
        # 일반 옵션 {A|B|C} 또는 {A:3|B:1}
        return self._process_options(content)
    
    def _process_range(self, match) -> str:
        """범위 처리: {1-10} → 랜덤 숫자"""
        start = int(match.group(1))
        end = int(match.group(2))
        step = int(match.group(3)) if match.group(3) else 1
        
        if start > end:
            start, end = end, start
        
        options = list(range(start, end + 1, step))
        result = str(random.choice(options))
        
        self._add_history(f"{start}-{end}", result)
        return result
    
    def _process_options(self, content: str) -> str:
        """옵션 처리: {A|B|C} 또는 {A:3|B:1}"""
        parts = content.split('|')
        
        options = []
        weights = []
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 가중치 확인 {A:3|B:1}
            if ':' in part:
                # 마지막 : 이후가 숫자인지 확인
                last_colon = part.rfind(':')
                weight_str = part[last_colon + 1:]
                
                try:
                    weight = int(weight_str)
                    option = part[:last_colon].strip()
                    options.append(option)
                    weights.append(weight)
                except ValueError:
                    # 숫자가 아니면 그냥 옵션으로
                    options.append(part)
                    weights.append(1)
            else:
                options.append(part)
                weights.append(1)
        
        if not options:
            return ''
        
        # 가중치 기반 선택
        result = random.choices(options, weights=weights, k=1)[0]
        
        self._add_history(content[:30], result)
        return result
    
    def _add_history(self, wildcard: str, result: str):
        """선택 기록 추가"""
        self.history.append({
            'wildcard': wildcard,
            'result': result
        })
        
        # 최대 개수 유지
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def expand_all(self, text: str) -> List[str]:
        """
        모든 조합 반환 (XYZ Plot용)
        주의: 조합이 매우 많아질 수 있음
        """
        if not text:
            return [text]
        
        match = self.PATTERN.search(text)
        if not match:
            return [text]
        
        content = match.group(1)
        
        # 범위인 경우
        range_match = self.RANGE_PATTERN.match(content.strip())
        if range_match:
            options = self._get_range_options(range_match)
        else:
            options = self._get_options(content)
        
        results = []
        for option in options:
            # 해당 와일드카드를 옵션으로 교체
            replaced = text[:match.start()] + option + text[match.end():]
            # 재귀적으로 나머지 와일드카드 처리
            results.extend(self.expand_all(replaced))
        
        return results
    
    def _get_range_options(self, match) -> List[str]:
        """범위에서 모든 옵션 반환"""
        start = int(match.group(1))
        end = int(match.group(2))
        step = int(match.group(3)) if match.group(3) else 1
        
        if start > end:
            start, end = end, start
        
        return [str(n) for n in range(start, end + 1, step)]
    
    def _get_options(self, content: str) -> List[str]:
        """옵션 목록 반환 (가중치 무시)"""
        parts = content.split('|')
        options = []
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 가중치 제거
            if ':' in part:
                last_colon = part.rfind(':')
                weight_str = part[last_colon + 1:]
                try:
                    int(weight_str)
                    option = part[:last_colon].strip()
                except ValueError:
                    option = part
            else:
                option = part
            
            if option:
                options.append(option)
        
        return options
    
    def get_history(self) -> List[dict]:
        """선택 기록 반환"""
        return self.history.copy()
    
    def clear_history(self):
        """기록 초기화"""
        self.history.clear()
    
    def count_combinations(self, text: str) -> int:
        """예상 조합 수 계산"""
        if not text:
            return 1
        
        count = 1
        
        for match in self.PATTERN.finditer(text):
            content = match.group(1)
            
            range_match = self.RANGE_PATTERN.match(content.strip())
            if range_match:
                options = self._get_range_options(range_match)
            else:
                options = self._get_options(content)
            
            count *= len(options) if options else 1
        
        return count
    
    def validate(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        와일드카드 문법 검증
        Returns: (유효 여부, 에러 메시지)
        """
        if not text:
            return True, None
        
        # 괄호 짝 확인
        open_count = text.count('{')
        close_count = text.count('}')
        
        if open_count != close_count:
            return False, f"괄호 짝이 맞지 않습니다 (열림: {open_count}, 닫힘: {close_count})"
        
        # 빈 와일드카드 확인
        if '{}' in text:
            return False, "빈 와일드카드 {{}}가 있습니다"
        
        # 옵션 없는 와일드카드 확인
        for match in self.PATTERN.finditer(text):
            content = match.group(1).strip()
            if not content:
                return False, "빈 와일드카드가 있습니다"
            
            # 범위가 아니고 | 도 없으면 경고
            if not self.RANGE_PATTERN.match(content) and '|' not in content:
                return True, f"경고: '{{{content}}}'는 단일 옵션입니다. 와일드카드가 아닌 고정 값으로 처리됩니다."

        return True, None


# 싱글톤 인스턴스
_processor_instance = None

def get_wildcard_processor() -> WildcardProcessor:
    """싱글톤 인스턴스 반환"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = WildcardProcessor()
    return _processor_instance


def process_wildcards(text: str) -> str:
    """간편 함수: 와일드카드 처리"""
    return get_wildcard_processor().process(text)


def expand_wildcards(text: str) -> List[str]:
    """간편 함수: 모든 조합 반환"""
    return get_wildcard_processor().expand_all(text)


def count_wildcard_combinations(text: str) -> int:
    """간편 함수: 조합 수 계산"""
    return get_wildcard_processor().count_combinations(text)
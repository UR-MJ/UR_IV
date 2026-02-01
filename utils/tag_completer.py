# utils/tag_completer.py
"""
태그 자동완성 시스템
tags_db/auto_tags.csv 활용
"""
from pathlib import Path
from typing import List, Optional


class TagCompleter:
    """태그 자동완성"""
    
    def __init__(self, tags_db_path: str = None):
        self.tags_db_path = Path(tags_db_path) if tags_db_path else self._find_tags_db_path()
        self.all_tags: List[str] = []
        self.tags_set: set = set()  # 빠른 검색용
        
        self._load_tags()
    
    def _find_tags_db_path(self) -> Path:
        """tags_db 경로 찾기"""
        candidates = [
            Path(__file__).parent.parent / "tags_db",
            Path("tags_db"),
            Path("../tags_db"),
        ]
        
        for path in candidates:
            if path.exists():
                return path
        
        return Path("tags_db")
    
    def _load_tags(self):
        """auto_tags.csv 로드"""
        csv_file = self.tags_db_path / "auto_tags.csv"
        
        if not csv_file.exists():
            print(f"⚠️ auto_tags.csv not found: {csv_file}")
            return
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                for line in f:
                    tag = line.strip()
                    if tag:
                        self.all_tags.append(tag)
                        self.tags_set.add(tag.lower())
            
            print(f"✅ auto_tags.csv: {len(self.all_tags)}개 태그 로드")
        except Exception as e:
            print(f"❌ auto_tags.csv 로드 실패: {e}")
    
    def get_suggestions(self, prefix: str, max_count: int = 10) -> List[str]:
        """
        입력 접두사로 태그 추천
        
        Args:
            prefix: 입력된 텍스트
            max_count: 최대 추천 개수
        
        Returns:
            추천 태그 리스트
        """
        if not prefix or not self.all_tags:
            return []
        
        prefix_lower = prefix.lower().strip()
        if not prefix_lower:
            return []
        
        suggestions = []
        
        # 1. 접두사로 시작하는 태그 (우선)
        for tag in self.all_tags:
            if tag.lower().startswith(prefix_lower):
                suggestions.append(tag)
                if len(suggestions) >= max_count:
                    return suggestions
        
        # 2. 접두사를 포함하는 태그 (차선)
        if len(suggestions) < max_count:
            for tag in self.all_tags:
                tag_lower = tag.lower()
                if prefix_lower in tag_lower and not tag_lower.startswith(prefix_lower):
                    suggestions.append(tag)
                    if len(suggestions) >= max_count:
                        return suggestions
        
        return suggestions
    
    def get_fuzzy_suggestions(self, query: str, max_count: int = 10) -> List[str]:
        """
        퍼지 매칭으로 태그 추천 (오타 허용)
        
        Args:
            query: 입력된 텍스트
            max_count: 최대 추천 개수
        
        Returns:
            추천 태그 리스트
        """
        if not query or not self.all_tags:
            return []
        
        query_lower = query.lower().strip()
        if not query_lower:
            return []
        
        # 단어 분리 (밑줄, 공백 기준)
        query_parts = query_lower.replace('_', ' ').split()
        
        scored = []
        
        for tag in self.all_tags:
            tag_lower = tag.lower()
            tag_parts = tag_lower.replace('_', ' ').split()
            
            score = 0
            
            # 정확히 시작하면 높은 점수
            if tag_lower.startswith(query_lower):
                score += 100
            
            # 포함하면 점수
            if query_lower in tag_lower:
                score += 50
            
            # 각 단어 매칭
            for qp in query_parts:
                for tp in tag_parts:
                    if tp.startswith(qp):
                        score += 30
                    elif qp in tp:
                        score += 10
            
            if score > 0:
                scored.append((tag, score))
        
        # 점수순 정렬
        scored.sort(key=lambda x: -x[1])
        
        return [tag for tag, _ in scored[:max_count]]
    
    def is_valid_tag(self, tag: str) -> bool:
        """태그가 유효한지 확인"""
        return tag.lower().strip() in self.tags_set
    
    def get_all_tags(self) -> List[str]:
        """전체 태그 목록 반환"""
        return self.all_tags.copy()
    
    def count(self) -> int:
        """태그 개수"""
        return len(self.all_tags)


# 싱글톤
_completer_instance = None

def get_tag_completer() -> TagCompleter:
    global _completer_instance
    if _completer_instance is None:
        _completer_instance = TagCompleter()
    return _completer_instance
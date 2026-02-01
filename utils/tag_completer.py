# utils/tag_completer.py
"""
태그 자동완성 시스템
tags_db/auto_tags.csv 활용
형식: tag_name,weight,count,"alias1,alias2,..."
"""
import csv
from pathlib import Path
from typing import List, Optional


class TagCompleter:
    """태그 자동완성"""

    def __init__(self, tags_db_path: str = None):
        self.tags_db_path = Path(tags_db_path) if tags_db_path else self._find_tags_db_path()
        self.all_tags: List[str] = []
        self.tags_set: set = set()
        self.alias_map: dict = {}  # alias → tag_name

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
        """auto_tags.csv 또는 auto tags.csv 로드"""
        csv_file = self.tags_db_path / "auto_tags.csv"
        if not csv_file.exists():
            csv_file = self.tags_db_path / "auto tags.csv"

        if not csv_file.exists():
            print(f"⚠️ auto_tags.csv not found: {csv_file}")
            return

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    tag_name = row[0].strip()
                    if not tag_name:
                        continue

                    self.all_tags.append(tag_name)
                    self.tags_set.add(tag_name.lower())

                    # aliases (4번째 컬럼)
                    if len(row) >= 4 and row[3].strip():
                        aliases = [a.strip() for a in row[3].split(',') if a.strip()]
                        for alias in aliases:
                            self.alias_map[alias.lower()] = tag_name

            print(f"✅ auto_tags.csv: {len(self.all_tags)}개 태그, {len(self.alias_map)}개 별칭 로드")
        except Exception as e:
            print(f"❌ auto_tags.csv 로드 실패: {e}")

    def get_suggestions(self, prefix: str, max_count: int = 10) -> List[str]:
        """입력 접두사로 태그 추천 (별칭 포함)"""
        if not prefix or not self.all_tags:
            return []

        prefix_lower = prefix.lower().strip().replace(' ', '_')
        if not prefix_lower:
            return []

        seen = set()
        suggestions = []

        # 1. 접두사로 시작하는 태그 (우선)
        for tag in self.all_tags:
            if tag.lower().startswith(prefix_lower):
                if tag.lower() not in seen:
                    seen.add(tag.lower())
                    suggestions.append(tag)
                    if len(suggestions) >= max_count:
                        return suggestions

        # 2. 별칭으로 시작하는 태그
        for alias, tag_name in self.alias_map.items():
            if alias.startswith(prefix_lower) and tag_name.lower() not in seen:
                seen.add(tag_name.lower())
                suggestions.append(tag_name)
                if len(suggestions) >= max_count:
                    return suggestions

        # 3. 접두사를 포함하는 태그 (차선)
        for tag in self.all_tags:
            tag_lower = tag.lower()
            if prefix_lower in tag_lower and tag_lower not in seen:
                seen.add(tag_lower)
                suggestions.append(tag)
                if len(suggestions) >= max_count:
                    return suggestions

        return suggestions

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

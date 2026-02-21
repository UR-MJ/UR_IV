# utils/tag_completer.py
"""
태그 자동완성 시스템
TagData(parquet) 기반 + CSV 별칭 폴백
"""
import bisect
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
        self._sorted_lower_tags: List[tuple] = []  # (lowercase_tag, original_tag)
        self._lower_keys: List[str] = []  # lowercase keys only (for bisect)

        self._load_tags()
        self._build_sorted_index()

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
        """TagData에서 general 태그 로드, 별칭은 CSV에서 보충"""
        # 1. TagData에서 general 태그 가져오기
        try:
            from utils.tag_data import get_tag_data
            td = get_tag_data()
            if td.is_loaded and td.general_tags:
                self.all_tags = td.general_tags.copy()
                self.tags_set = {t.lower() for t in self.all_tags}
                print(f"✅ TagCompleter: TagData에서 {len(self.all_tags):,}개 general 태그 로드")
                # 별칭은 CSV에서 보충
                self._load_aliases_from_csv()
                return
        except Exception as e:
            print(f"⚠️ TagData 로드 실패, CSV 폴백: {e}")

        # 2. 폴백: auto_tags.csv
        self._load_from_csv()

    def _load_aliases_from_csv(self):
        """CSV에서 별칭만 로드"""
        csv_file = self.tags_db_path / "auto_tags.csv"
        if not csv_file.exists():
            csv_file = self.tags_db_path / "auto tags.csv"
        if not csv_file.exists():
            return

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    if len(row) >= 4 and row[3].strip():
                        tag_name = row[0].strip()
                        aliases = [a.strip() for a in row[3].split(',') if a.strip()]
                        for alias in aliases:
                            self.alias_map[alias.lower()] = tag_name
            if self.alias_map:
                print(f"✅ TagCompleter: {len(self.alias_map)}개 별칭 로드 (CSV)")
        except Exception:
            pass

    def _load_from_csv(self):
        """폴백: auto_tags.csv에서 전체 로드"""
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

                    if len(row) >= 4 and row[3].strip():
                        aliases = [a.strip() for a in row[3].split(',') if a.strip()]
                        for alias in aliases:
                            self.alias_map[alias.lower()] = tag_name

            print(f"✅ TagCompleter(CSV 폴백): {len(self.all_tags)}개 태그, {len(self.alias_map)}개 별칭")
        except Exception as e:
            print(f"❌ auto_tags.csv 로드 실패: {e}")

    def _build_sorted_index(self):
        """이진 검색용 정렬된 인덱스 생성"""
        pairs = [(tag.lower().replace(' ', '_'), tag) for tag in self.all_tags]
        pairs.sort(key=lambda x: x[0])
        self._sorted_lower_tags = pairs
        self._lower_keys = [p[0] for p in pairs]

    def get_suggestions(self, prefix: str, max_count: int = 10) -> List[str]:
        """입력 접두사로 태그 추천 (별칭 포함)"""
        if not prefix or not self.all_tags:
            return []

        prefix_lower = prefix.lower().strip().replace(' ', '_')
        if not prefix_lower:
            return []

        seen = set()
        suggestions = []

        # 1. 접두사로 시작하는 태그 (이진 검색, O(log n + k))
        start = bisect.bisect_left(self._lower_keys, prefix_lower)
        for i in range(start, len(self._lower_keys)):
            lower_tag = self._lower_keys[i]
            if not lower_tag.startswith(prefix_lower):
                break
            orig_tag = self._sorted_lower_tags[i][1]
            tag_key = orig_tag.lower()
            if tag_key not in seen:
                seen.add(tag_key)
                suggestions.append(orig_tag)
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
            tag_lower = tag.lower().replace(' ', '_')
            if prefix_lower in tag_lower and tag.lower() not in seen:
                seen.add(tag.lower())
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

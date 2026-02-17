# utils/character_features.py
"""캐릭터 특징 조회 유틸리티 (danbooru_character.py 기반)"""
import os
import re


class CharacterFeatureLookup:
    """캐릭터 이름 → 외형 특징 태그 조회 (lazy loading, singleton)"""

    def __init__(self):
        self._dict: dict[str, str] | None = None
        self._count: dict[str, int] | None = None
        self._norm_index: dict[str, str] = {}  # normalized → original key
        self._short_index: dict[str, str] = {}  # 괄호 제거 이름 → original key

    def _ensure_loaded(self):
        """첫 호출 시 danbooru_character.py 로드"""
        if self._dict is not None:
            return

        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tags_db")
        path = os.path.join(base, "danbooru_character.py")

        ns: dict = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                exec(f.read(), ns)
        except Exception:
            self._dict = {}
            self._count = {}
            return

        self._dict = ns.get("character_dict", {})
        self._count = ns.get("character_dict_count", {})

        # 정규화 인덱스 빌드
        paren_re = re.compile(r'\s*\([^)]*\)\s*$')
        for key in self._dict:
            norm = key.strip().lower().replace("_", " ")
            self._norm_index[norm] = key
            # 괄호 제거 버전도 등록 (짧은 이름으로 검색 가능)
            short = paren_re.sub("", norm).strip()
            if short and short != norm and short not in self._short_index:
                self._short_index[short] = key

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower().replace("_", " ")

    def lookup(self, name: str) -> tuple[str, int] | None:
        """캐릭터 이름으로 (특징 문자열, 게시물 수) 조회. 없으면 None."""
        self._ensure_loaded()
        norm = self._normalize(name)

        # 1) 정규화 인덱스 직접 매칭
        orig = self._norm_index.get(norm)
        if orig is None:
            # 2) 괄호 없는 이름으로 매칭
            orig = self._short_index.get(norm)
        if orig is None:
            return None

        features = self._dict.get(orig, "")
        count = self._count.get(orig, 0) if self._count else 0
        return (features, count)

    def lookup_multiple(self, text: str) -> dict[str, tuple[str, int]]:
        """쉼표 구분 캐릭터 이름들을 다중 조회.
        Returns: {표시이름: (특징 문자열, 게시물 수)}
        """
        self._ensure_loaded()
        results: dict[str, tuple[str, int]] = {}
        for part in text.split(","):
            name = part.strip()
            if not name:
                continue
            result = self.lookup(name)
            if result:
                results[name] = result
        return results


    def search(self, query: str, limit: int = 50) -> list[tuple[str, str, int]]:
        """캐릭터 이름 검색. Returns: [(원본키, 특징문자열, 게시물수), ...]"""
        self._ensure_loaded()
        if not query.strip():
            return []

        q = self._normalize(query)
        results: list[tuple[str, str, int, int]] = []  # (key, features, count, priority)

        for norm_key, orig_key in self._norm_index.items():
            if q in norm_key:
                features = self._dict.get(orig_key, "")
                count = self._count.get(orig_key, 0) if self._count else 0
                # 우선순위: 정확 매칭 > 시작 매칭 > 포함 매칭, 그 안에서 count 내림차순
                if norm_key == q:
                    priority = 0
                elif norm_key.startswith(q):
                    priority = 1
                else:
                    priority = 2
                results.append((orig_key, features, count, priority))

        results.sort(key=lambda x: (x[3], -x[2]))
        return [(r[0], r[1], r[2]) for r in results[:limit]]

    def all_keys(self) -> list[str]:
        """모든 캐릭터 키 반환 (정규화 이전 원본)"""
        self._ensure_loaded()
        return list(self._dict.keys()) if self._dict else []


_instance: CharacterFeatureLookup | None = None


def get_character_features() -> CharacterFeatureLookup:
    """싱글턴 인스턴스 반환"""
    global _instance
    if _instance is None:
        _instance = CharacterFeatureLookup()
    return _instance

# utils/character_features.py
"""캐릭터 특징 조회 유틸리티
메인: characterization.json (핵심 특징)
보충: danbooru_character.py (의상/추가 특징)
"""
import os
import re
import json
from typing import Optional


class CharacterFeatureLookup:
    """캐릭터 이름 → 핵심/의상 특징 분리 조회 (lazy loading, singleton)"""

    def __init__(self):
        # 핵심 특징 (characterization.json)
        self._core_dict: dict[str, list[str]] | None = None   # name → core_tags
        self._copyright: dict[str, str] = {}                    # name → copyright
        self._gender: dict[str, dict] = {}                      # name → {boy, girl}
        self._post_count: dict[str, int] = {}                   # name → post_count

        # 전체 특징 (danbooru_character.py)
        self._full_dict: dict[str, str] | None = None           # name → features_str
        self._full_count: dict[str, int] | None = None

        # 인덱스
        self._norm_index: dict[str, str] = {}   # normalized → original key
        self._short_index: dict[str, str] = {}  # 괄호 제거 → original key

    def _ensure_loaded(self):
        """첫 호출 시 데이터 로드"""
        if self._core_dict is not None:
            return

        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tags_db")
        self._core_dict = {}
        self._full_dict = {}
        self._full_count = {}

        # 1. characterization.json 로드 (메인 — 핵심 특징)
        json_path = os.path.join(base, "characterization.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for entry in data:
                    tag = entry.get("tag", "")
                    name = tag.replace("_", " ").strip().lower()
                    if not name:
                        continue
                    core_tags = [t.replace("_", " ") for t in entry.get("core_tags", [])]
                    self._core_dict[name] = core_tags
                    self._post_count[name] = entry.get("post_count", 0)
                    copyright_val = entry.get("copyright", "")
                    if copyright_val:
                        self._copyright[name] = copyright_val.replace("_", " ")
                    gender = entry.get("gender")
                    if gender:
                        self._gender[name] = gender
                print(f"✅ characterization.json: {len(self._core_dict)}개 캐릭터 (핵심 특징)")
            except Exception as e:
                print(f"⚠️ characterization.json 로드 실패: {e}")

        # 2. danbooru_character.py 로드 (보충 — 의상 포함 전체)
        py_path = os.path.join(base, "danbooru_character.py")
        if os.path.exists(py_path):
            try:
                ns: dict = {}
                with open(py_path, "r", encoding="utf-8") as f:
                    exec(f.read(), ns)
                self._full_dict = ns.get("character_dict", {})
                self._full_count = ns.get("character_dict_count", {})
                print(f"✅ danbooru_character.py: {len(self._full_dict)}개 캐릭터 (전체 특징)")
            except Exception as e:
                print(f"⚠️ danbooru_character.py 로드 실패: {e}")

        # 3. 인덱스 빌드 (양쪽 소스 병합)
        all_keys = set()
        if self._core_dict:
            all_keys.update(self._core_dict.keys())
        if self._full_dict:
            all_keys.update(k.strip().lower().replace("_", " ") for k in self._full_dict.keys())

        paren_re = re.compile(r'\s*\([^)]*\)\s*$')
        for key in all_keys:
            norm = key.strip().lower().replace("_", " ")
            if norm not in self._norm_index:
                self._norm_index[norm] = key
            short = paren_re.sub("", norm).strip()
            if short and short != norm and short not in self._short_index:
                self._short_index[short] = key

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower().replace("_", " ")

    def _resolve_key(self, name: str) -> str | None:
        """이름 → 정규화 키 해석"""
        norm = self._normalize(name)
        if norm in self._norm_index:
            return self._norm_index[norm]
        if norm in self._short_index:
            return self._short_index[norm]
        return None

    def _get_full_features_for(self, key: str) -> str:
        """danbooru_character.py에서 전체 특징 문자열 가져오기"""
        if not self._full_dict:
            return ""
        # 직접 키 매칭
        if key in self._full_dict:
            return self._full_dict[key]
        # 정규화 매칭
        for k, v in self._full_dict.items():
            if k.strip().lower().replace("_", " ") == key:
                return v
        return ""

    def lookup_core(self, name: str) -> tuple[str, int] | None:
        """핵심 특징만 조회 (characterization.json core_tags)"""
        self._ensure_loaded()
        key = self._resolve_key(name)
        if key is None:
            return None
        core_tags = self._core_dict.get(key, [])
        if not core_tags:
            return None
        count = self._post_count.get(key, 0)
        return (", ".join(core_tags), count)

    def lookup_costume(self, name: str) -> tuple[str, int] | None:
        """의상/추가 특징만 조회 (full에서 core를 빈 나머지)"""
        self._ensure_loaded()
        key = self._resolve_key(name)
        if key is None:
            return None

        # core 태그 set (정규화)
        core_tags = self._core_dict.get(key, [])
        core_set = {t.strip().lower() for t in core_tags}

        # full 태그 파싱
        full_str = self._get_full_features_for(key)
        if not full_str:
            return None

        full_tags = [t.strip() for t in full_str.split(",") if t.strip()]
        # full에서 core와 캐릭터명 자체를 제외
        costume_tags = []
        for t in full_tags:
            t_norm = t.strip().lower()
            if t_norm in core_set:
                continue
            if t_norm == key:
                continue
            costume_tags.append(t)

        if not costume_tags:
            return None
        count = self._post_count.get(key, 0)
        return (", ".join(costume_tags), count)

    def lookup(self, name: str) -> tuple[str, int] | None:
        """전체 특징 조회 (기존 호환). full 우선, 없으면 core."""
        self._ensure_loaded()
        key = self._resolve_key(name)
        if key is None:
            return None

        # full에서 가져오기
        full_str = self._get_full_features_for(key)
        if full_str:
            count = self._post_count.get(key, 0)
            if not count and self._full_count:
                for k, v in self._full_count.items():
                    if k.strip().lower().replace("_", " ") == key:
                        count = v
                        break
            return (full_str, count)

        # core만 있는 경우
        core_tags = self._core_dict.get(key, [])
        if core_tags:
            count = self._post_count.get(key, 0)
            return (", ".join(core_tags), count)

        return None

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

    def lookup_multiple_split(self, text: str) -> dict[str, dict]:
        """쉼표 구분 캐릭터 → 핵심/의상 분리 조회.
        Returns: {표시이름: {"core": (str, count), "costume": (str, count) | None}}
        """
        self._ensure_loaded()
        results: dict[str, dict] = {}
        for part in text.split(","):
            name = part.strip()
            if not name:
                continue
            core = self.lookup_core(name)
            costume = self.lookup_costume(name)
            full = self.lookup(name)
            if core or full:
                count = (core[1] if core else 0) or (full[1] if full else 0)
                results[name] = {
                    "core": core,
                    "costume": costume,
                    "count": count,
                }
        return results

    def get_copyright(self, name: str) -> str | None:
        """캐릭터 → 작품명"""
        self._ensure_loaded()
        key = self._resolve_key(name)
        return self._copyright.get(key) if key else None

    def get_gender(self, name: str) -> dict | None:
        """캐릭터 → gender 확률 {boy: float, girl: float}"""
        self._ensure_loaded()
        key = self._resolve_key(name)
        return self._gender.get(key) if key else None

    def search(self, query: str, limit: int = 50) -> list[tuple[str, str, int]]:
        """캐릭터 이름 검색. Returns: [(원본키, 특징문자열, 게시물수), ...]"""
        self._ensure_loaded()
        if not query.strip():
            return []

        q = self._normalize(query)
        results: list[tuple[str, str, int, int]] = []

        for norm_key, orig_key in self._norm_index.items():
            if q in norm_key:
                # lookup으로 특징 가져오기
                result = self.lookup(orig_key)
                features = result[0] if result else ""
                count = result[1] if result else self._post_count.get(orig_key, 0)
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
        """모든 캐릭터 키 반환"""
        self._ensure_loaded()
        return list(self._norm_index.values())


_instance: CharacterFeatureLookup | None = None


def get_character_features() -> CharacterFeatureLookup:
    """싱글턴 인스턴스 반환"""
    global _instance
    if _instance is None:
        _instance = CharacterFeatureLookup()
    return _instance

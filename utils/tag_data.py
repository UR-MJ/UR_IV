# utils/tag_data.py
"""
danbooru2025-alltime-tag-counts.parquet 기반 통합 태그 데이터 로더.
tag_type별 list(자동완성) / set(제거 토글) 제공.
"""
import os
from pathlib import Path
from typing import List, Set, Optional


class TagData:
    """parquet 기반 통합 태그 데이터 (싱글톤)"""

    def __init__(self, parquet_path: str = None):
        if parquet_path is None:
            parquet_path = str(
                Path(__file__).parent.parent / "danbooru2025-alltime-tag-counts.parquet"
            )
        self._parquet_path = parquet_path

        # tag_type별 리스트 (count 내림차순, 자동완성용)
        self.general_tags: List[str] = []
        self.character_tags: List[str] = []
        self.copyright_tags: List[str] = []
        self.artist_tags: List[str] = []
        self.meta_tags: List[str] = []

        # tag_type별 set (lowercase, 제거 토글 lookup용)
        self.general_set: Set[str] = set()
        self.character_set: Set[str] = set()
        self.copyright_set: Set[str] = set()
        self.artist_set: Set[str] = set()
        self.meta_set: Set[str] = set()

        self._loaded = False
        self._load()

    def _load(self):
        """parquet 파일 로드 → tag_type별 분리"""
        if not os.path.exists(self._parquet_path):
            print(f"⚠️ tag-counts parquet 없음: {self._parquet_path}")
            return

        try:
            import pandas as pd
            df = pd.read_parquet(
                self._parquet_path,
                columns=["tag_string", "tag_type", "tag_count"]
            )

            # count 내림차순 정렬
            df = df.sort_values("tag_count", ascending=False)

            # underscore → space 변환
            df["tag_display"] = df["tag_string"].str.replace("_", " ", regex=False)

            type_map = {
                "general": (self.general_tags, self.general_set),
                "character": (self.character_tags, self.character_set),
                "copyright": (self.copyright_tags, self.copyright_set),
                "artist": (self.artist_tags, self.artist_set),
                "meta": (self.meta_tags, self.meta_set),
            }

            for tag_type, (tag_list, tag_set) in type_map.items():
                subset = df[df["tag_type"] == tag_type]
                tags = subset["tag_display"].dropna().tolist()
                tag_list.extend(tags)
                tag_set.update(t.lower() for t in tags)

            self._loaded = True
            total = sum(len(v[0]) for v in type_map.values())
            print(
                f"✅ TagData 로드: {total:,}개 태그 "
                f"(general={len(self.general_tags):,}, "
                f"character={len(self.character_tags):,}, "
                f"copyright={len(self.copyright_tags):,}, "
                f"artist={len(self.artist_tags):,}, "
                f"meta={len(self.meta_tags):,})"
            )
        except Exception as e:
            print(f"❌ TagData 로드 실패: {e}")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get_tags_by_type(self, tag_type: str) -> List[str]:
        """tag_type별 태그 리스트 반환 (자동완성용, count 내림차순)"""
        mapping = {
            "general": self.general_tags,
            "character": self.character_tags,
            "copyright": self.copyright_tags,
            "artist": self.artist_tags,
            "meta": self.meta_tags,
        }
        return mapping.get(tag_type, [])

    def get_set_by_type(self, tag_type: str) -> Set[str]:
        """tag_type별 태그 set 반환 (제거 토글용, lowercase)"""
        mapping = {
            "general": self.general_set,
            "character": self.character_set,
            "copyright": self.copyright_set,
            "artist": self.artist_set,
            "meta": self.meta_set,
        }
        return mapping.get(tag_type, set())

    def is_tag_type(self, tag: str, tag_type: str) -> bool:
        """태그가 특정 tag_type인지 확인"""
        return tag.strip().lower().replace("_", " ") in self.get_set_by_type(tag_type)


# ── 싱글톤 ──
_tag_data_instance: Optional[TagData] = None


def get_tag_data() -> TagData:
    """싱글톤 인스턴스 반환"""
    global _tag_data_instance
    if _tag_data_instance is None:
        _tag_data_instance = TagData()
    return _tag_data_instance

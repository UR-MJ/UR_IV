# utils/tag_completer.py
"""
태그 자동완성 시스템

TagData(parquet) 4개 카테고리(general / character / copyright / artist) 모두
활용. 결과는 카테고리 우선순위 + 접두사 일치 우선으로 정렬.

기본 우선순위: general → character → copyright → artist
(사용자가 쓰는 빈도 기준)
"""
import bisect
import csv
from pathlib import Path
from typing import List


# 카테고리 우선순위 — 작을수록 먼저 노출
CATEGORY_PRIORITY = {
    "general":   0,
    "character": 1,
    "copyright": 2,
    "artist":    3,
}


class TagCompleter:
    """태그 자동완성 — 카테고리별 분리 인덱스로 우선순위 보장."""

    def __init__(self, tags_db_path: str = None):
        self.tags_db_path = Path(tags_db_path) if tags_db_path else self._find_tags_db_path()
        # 카테고리별 정렬된 (lower_key, original_tag) 리스트
        self._cat_indices: dict[str, list[tuple[str, str]]] = {
            k: [] for k in CATEGORY_PRIORITY
        }
        # 카테고리별 lower_keys (bisect용)
        self._cat_lower_keys: dict[str, list[str]] = {
            k: [] for k in CATEGORY_PRIORITY
        }
        # 별칭 → 태그
        self.alias_map: dict[str, str] = {}
        # is_valid_tag()용
        self.tags_set: set[str] = set()
        # 태그 인기도 (lower+underscore 키 → count) — 접두사 매칭 결과 정렬용
        self._counts: dict[str, int] = {}

        self._load_tags()
        self._build_indices()

    def _find_tags_db_path(self) -> Path:
        candidates = [
            Path(__file__).parent.parent / "tags_db",
            Path("tags_db"),
            Path("../tags_db"),
        ]
        for path in candidates:
            if path.exists():
                return path
        return Path("tags_db")

    # ────────────────────────────────────────
    # 로드
    # ────────────────────────────────────────

    def _load_tags(self):
        """TagData에서 4개 카테고리 모두 로드. 실패 시 CSV 폴백."""
        try:
            from utils.tag_data import get_tag_data
            td = get_tag_data()
            if td.is_loaded:
                self._counts = getattr(td, 'tag_counts', {}) or {}
                counts: dict[str, int] = {}
                for cat in CATEGORY_PRIORITY:
                    tags = getattr(td, f"{cat}_tags", None) or []
                    for t in tags:
                        if not t:
                            continue
                        self._cat_indices[cat].append(
                            (t.lower().replace(" ", "_"), t)
                        )
                        self.tags_set.add(t.lower())
                    counts[cat] = len(tags)
                if any(counts.values()):
                    parts = ", ".join(f"{k}={v:,}" for k, v in counts.items())
                    print(f"✅ TagCompleter: TagData 4-카테고리 로드 ({parts})")
                    self._load_aliases_from_csv()
                    return
        except Exception as e:
            print(f"⚠️ TagData 로드 실패, CSV 폴백: {e}")

        # 폴백: auto_tags.csv (general 단일 카테고리로)
        self._load_from_csv_fallback()

    def _load_aliases_from_csv(self):
        csv_file = self.tags_db_path / "auto_tags.csv"
        if not csv_file.exists():
            csv_file = self.tags_db_path / "auto tags.csv"
        if not csv_file.exists():
            return
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    if len(row) >= 4 and row[3].strip():
                        tag_name = row[0].strip()
                        aliases = [a.strip() for a in row[3].split(",") if a.strip()]
                        for alias in aliases:
                            self.alias_map[alias.lower()] = tag_name
            if self.alias_map:
                print(f"✅ TagCompleter: {len(self.alias_map):,}개 별칭 로드")
        except Exception:
            pass

    def _load_from_csv_fallback(self):
        """auto_tags.csv 폴백 — general에만 채움."""
        csv_file = self.tags_db_path / "auto_tags.csv"
        if not csv_file.exists():
            csv_file = self.tags_db_path / "auto tags.csv"
        if not csv_file.exists():
            print(f"⚠️ auto_tags.csv not found: {csv_file}")
            return
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    tag_name = row[0].strip()
                    if not tag_name:
                        continue
                    self._cat_indices["general"].append(
                        (tag_name.lower().replace(" ", "_"), tag_name)
                    )
                    self.tags_set.add(tag_name.lower())
                    if len(row) >= 4 and row[3].strip():
                        aliases = [a.strip() for a in row[3].split(",") if a.strip()]
                        for alias in aliases:
                            self.alias_map[alias.lower()] = tag_name
            print(f"✅ TagCompleter(CSV): {len(self._cat_indices['general']):,}개 태그")
        except Exception as e:
            print(f"❌ auto_tags.csv 로드 실패: {e}")

    def _build_indices(self):
        """카테고리별로 정렬 + lower_keys 분리 (bisect용)."""
        for cat in CATEGORY_PRIORITY:
            self._cat_indices[cat].sort(key=lambda x: x[0])
            self._cat_lower_keys[cat] = [p[0] for p in self._cat_indices[cat]]

    # ────────────────────────────────────────
    # 검색
    # ────────────────────────────────────────

    def get_suggestions(self, prefix: str, max_count: int = 10) -> List[str]:
        """접두사로 태그 추천.

        결과 순서: general → character → copyright → artist
        각 카테고리 내에서는 접두사 일치 우선, 그 다음 별칭 일치, 그 다음 포함 일치.
        """
        if not prefix:
            return []
        prefix_lower = prefix.lower().strip().replace(" ", "_")
        if not prefix_lower:
            return []

        seen: set[str] = set()
        results: list[str] = []

        # 1. 카테고리별 접두사 매칭 (general → character → copyright → artist)
        for cat in sorted(CATEGORY_PRIORITY, key=lambda c: CATEGORY_PRIORITY[c]):
            if len(results) >= max_count:
                return results
            results += self._prefix_match(cat, prefix_lower, max_count - len(results), seen)

        # 2. 별칭 매칭 (모든 카테고리 통합)
        if len(results) < max_count:
            for alias, tag_name in self.alias_map.items():
                if alias.startswith(prefix_lower):
                    tl = tag_name.lower()
                    if tl not in seen:
                        seen.add(tl)
                        results.append(tag_name)
                        if len(results) >= max_count:
                            return results

        # 3. 포함 매칭 (general에서만 — 너무 많아지지 않게)
        if len(results) < max_count:
            for tag in (p[1] for p in self._cat_indices["general"]):
                tag_lower = tag.lower().replace(" ", "_")
                if prefix_lower in tag_lower and tag.lower() not in seen:
                    seen.add(tag.lower())
                    results.append(tag)
                    if len(results) >= max_count:
                        return results

        return results

    # 접두사 매칭 후보 최대 스캔 수 — 인기도 정렬을 위해 후보를 모은 뒤 count로 정렬.
    # 너무 크면 1글자 접두사에서 느려지고, 너무 작으면 인기 태그를 놓침. 3000이면
    # 대부분의 접두사를 커버하면서 정렬 비용도 무시할 만함.
    _PREFIX_SCAN_CAP = 3000

    def _prefix_match(self, cat: str, prefix_lower: str,
                      remaining: int, seen: set) -> list[str]:
        """카테고리 내 접두사 매칭 — bisect로 후보 수집 후 인기도(count) 내림차순 정렬.

        기존엔 알파벳순이라 '1g' → '1girl'이 위로 안 왔음. count 정렬로 자주 쓰는
        태그가 먼저 노출됨.
        """
        if remaining <= 0:
            return []
        keys = self._cat_lower_keys[cat]
        if not keys:
            return []
        start = bisect.bisect_left(keys, prefix_lower)
        # 1) 접두사 일치 후보 수집 (최대 _PREFIX_SCAN_CAP)
        matched: list[str] = []
        for i in range(start, min(len(keys), start + self._PREFIX_SCAN_CAP)):
            if not keys[i].startswith(prefix_lower):
                break
            orig = self._cat_indices[cat][i][1]
            if orig.lower() in seen:
                continue
            matched.append(orig)
        if not matched:
            return []
        # 2) 인기도(count) 내림차순 정렬 — count 동률이면 짧은 태그 우선(더 일반적)
        c = self._counts
        matched.sort(key=lambda t: (-c.get(t.lower().replace(" ", "_"), 0), len(t)))
        # 3) 상위 remaining개 반환 + seen 갱신
        out: list[str] = []
        for orig in matched[:remaining]:
            seen.add(orig.lower())
            out.append(orig)
        return out

    # ────────────────────────────────────────
    # 유틸
    # ────────────────────────────────────────

    def is_valid_tag(self, tag: str) -> bool:
        return tag.lower().strip() in self.tags_set

    def get_all_tags(self) -> List[str]:
        out: list[str] = []
        for cat in CATEGORY_PRIORITY:
            out.extend(p[1] for p in self._cat_indices[cat])
        return out

    def count(self) -> int:
        return sum(len(self._cat_indices[c]) for c in CATEGORY_PRIORITY)


# 싱글톤
_completer_instance = None


def get_tag_completer() -> TagCompleter:
    global _completer_instance
    if _completer_instance is None:
        _completer_instance = TagCompleter()
    return _completer_instance


def reset_tag_completer() -> None:
    """싱글톤 캐시 비우기 — 데이터 갱신 후 강제 재로드용."""
    global _completer_instance
    _completer_instance = None

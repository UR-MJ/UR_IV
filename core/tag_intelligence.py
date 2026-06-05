# core/tag_intelligence.py
"""NAIA 데이터 기반 태그 인텔리전스 — 분류 / 노이즈 필터 / NSFW 판별.

데이터 (tags_db/):
  - KR_tags.parquet                       : tag, count, category("패션 > 헤어스타일" 등), keywords
  - danbooru_tag_counts_by_rating.json    : {tag: [g, s, q, e]} + _meta.total_posts
  - naia_clothes_list.txt (11k)           : 의류 태그 사전
  - naia_characteristic_list.txt          : 외견 특징 태그 사전
  - naia_color.txt                        : 색상/패턴 단어

지연 로딩 + 싱글턴. 모든 조회는 정규화(소문자 + 언더스코어→공백) 기준.
"""
import os
import json


def _norm(t: str) -> str:
    return (t or "").strip().lower().replace("_", " ").replace(r"\(", "(").replace(r"\)", ")")


# danbooru 실태그는 아니지만 프롬프트에서 흔히 쓰는 품질/메타 태그 (노이즈 필터에서 보존)
_PROMPT_ALLOW = {
    "masterpiece", "best quality", "high quality", "normal quality", "low quality",
    "worst quality", "amazing quality", "great quality", "good quality", "high resolution",
    "very aesthetic", "aesthetic", "very awa", "newest", "recent", "oldest", "early", "mid",
    "ultra-detailed", "ultra detailed", "highly detailed", "detailed", "best aesthetic",
    "score_9", "score_8_up", "score_7_up", "source anime", "nsfw", "sfw",
}


class TagIntelligence:
    def __init__(self):
        self._loaded = False
        self._cat: dict[str, str] = {}     # norm → category 문자열
        self._count: dict[str, int] = {}   # norm → 빈도
        self._rating: dict[str, tuple] = {}  # norm → (g, s, q, e)
        self._clothes: set[str] = set()
        self._charac: set[str] = set()
        self._colors: set[str] = set()
        self._totals = None

    def _base(self) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "tags_db")

    def _load_txt(self, name: str) -> set:
        out: set[str] = set()
        try:
            with open(os.path.join(self._base(), name), "r", encoding="utf-8") as f:
                for line in f:
                    n = _norm(line)
                    if n:
                        out.add(n)
        except Exception:
            pass
        return out

    def _ensure(self):
        if self._loaded:
            return
        self._loaded = True
        base = self._base()
        # 1) KR_tags.parquet — category + count
        try:
            import pandas as pd
            df = pd.read_parquet(os.path.join(base, "KR_tags.parquet"))
            cats = df["category"] if "category" in df.columns else [None] * len(df)
            cnts = df["count"] if "count" in df.columns else [0] * len(df)
            for tag, cat, cnt in zip(df["tag"], cats, cnts):
                n = _norm(str(tag))
                if not n:
                    continue
                self._cat[n] = str(cat) if cat is not None else ""
                try:
                    self._count[n] = int(cnt)
                except (ValueError, TypeError):
                    self._count[n] = 0
        except Exception as e:
            print(f"[TagIntel] KR_tags 로드 실패: {e}")
        # 2) 레이팅 분포
        try:
            with open(os.path.join(base, "danbooru_tag_counts_by_rating.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            self._totals = (data.get("_meta") or {}).get("total_posts")
            for k, v in data.items():
                if k == "_meta":
                    continue
                if isinstance(v, list) and len(v) == 4:
                    self._rating[_norm(k)] = tuple(int(x) for x in v)
        except Exception as e:
            print(f"[TagIntel] rating 로드 실패: {e}")
        # 3) 텍스트 사전
        self._clothes = self._load_txt("naia_clothes_list.txt")
        self._charac = self._load_txt("naia_characteristic_list.txt")
        self._colors = self._load_txt("naia_color.txt")
        print(f"[TagIntel] KR태그 {len(self._cat):,} · 레이팅 {len(self._rating):,} · "
              f"의류 {len(self._clothes):,} · 특징 {len(self._charac):,} · 색상 {len(self._colors):,}")

    # ── 분류 ──
    def category_of(self, tag: str) -> str:
        self._ensure()
        return self._cat.get(_norm(tag), "")

    def top_category(self, tag: str) -> str:
        c = self.category_of(tag)
        return c.split(">")[0].strip() if c else ""

    def is_clothing(self, tag: str) -> bool:
        self._ensure()
        n = _norm(tag)
        if n in self._clothes:
            return True
        c = self._cat.get(n, "")
        return c.startswith("패션") and "헤어" not in c or "의류" in c or "의상" in c

    def is_appearance(self, tag: str) -> bool:
        """외견(신체/머리 등) 특징 태그인지."""
        self._ensure()
        n = _norm(tag)
        if n in self._charac:
            return True
        c = self._cat.get(n, "")
        return c.startswith("신체") or c.startswith("패션 > 헤어")

    def is_color(self, tag: str) -> bool:
        self._ensure()
        n = _norm(tag)
        if n in self._colors:
            return True
        return bool(set(n.split()) & self._colors)

    # ── 노이즈 / 검증 ──
    def is_known(self, tag: str) -> bool:
        self._ensure()
        n = _norm(tag)
        return (n in _PROMPT_ALLOW or n in self._cat or n in self._rating or
                n in self._clothes or n in self._charac)

    def tag_freq(self, tag: str) -> int:
        self._ensure()
        n = _norm(tag)
        if n in self._count:
            return self._count[n]
        r = self._rating.get(n)
        return sum(r) if r else 0

    def filter_noise(self, tags, min_count: int = 0, drop_unknown: bool = True):
        """리스트에서 가짜(미등록)/저빈도 태그 제거. Returns (kept, dropped)."""
        self._ensure()
        kept, dropped = [], []
        for t in tags:
            n = _norm(t)
            if not n:
                continue
            if drop_unknown and not self.is_known(t):
                dropped.append(t)
                continue
            if min_count and self.tag_freq(t) < min_count:
                dropped.append(t)
                continue
            kept.append(t)
        return kept, dropped

    # ── NSFW / 레이팅 ──
    def nsfw_ratio(self, tag: str):
        """questionable+explicit 비중 (0~1). 데이터 없으면 None."""
        self._ensure()
        r = self._rating.get(_norm(tag))
        if not r:
            return None
        tot = sum(r)
        if not tot:
            return None
        g, s, q, e = r
        return (q + e) / tot

    def is_nsfw(self, tag: str, threshold: float = 0.6) -> bool:
        ratio = self.nsfw_ratio(tag)
        return ratio is not None and ratio >= threshold


_instance = None


def get_tag_intelligence() -> TagIntelligence:
    global _instance
    if _instance is None:
        _instance = TagIntelligence()
    return _instance

# core/tag_intelligence.py
"""NAIA 데이터 기반 태그 인텔리전스 — 분류 / 노이즈 필터 / NSFW 판별.

데이터 (tags_db/):
  - KR_tags.parquet                       : tag, count, category("패션 > 헤어스타일" 등), keywords
  - danbooru_tag_counts_by_rating.json    : {tag: [g, s, q, e]} + _meta.total_posts
  - naia_clothes_list.txt (11k)           : 의류 태그 사전
  - naia_characteristic_list.txt          : 외견 특징 태그 사전
  - naia_color.txt                        : 색상/패턴 단어
  - clothing_regions.json                 : 의류 → 부위(region) 매핑
  - copyright_groups.json                 : copyright(시리즈) → 캐릭터 (역인덱스: 캐릭터→시리즈)
  - expression_tags.json / location_tags.json / pose_action_tags.json
    / object_tags.json / meta_tags.json   : 카테고리 사전 (분리 토글용)

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

# 의류 부위(region) → 한국어 라벨 (UI 그룹 표시용)
REGION_LABELS = {
    "HEAD_NECK_FACE": "머리·목·얼굴",
    "UPPER_BODY": "상의",
    "WAIST_HIP": "허리·하의",
    "ARMS_HANDS": "팔·손",
    "LEGS_FEET": "다리·발",
    "FULL_BODY": "전신",
    "STYLE": "스타일",
    "UNASSIGNED": "기타",
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
        # 신규: region / copyright / 카테고리 사전
        self._regions: dict[str, str] = {}      # norm 의류태그 → REGION 키
        self._region_order: list[str] = []      # region 표시 순서
        self._copyright: dict[str, str] = {}    # norm 캐릭터/별칭 → 시리즈(copyright)
        self._copyright_vals = None              # copyright 값 집합(지연 생성)
        self._expression: set[str] = set()
        self._location: set[str] = set()
        self._pose: set[str] = set()
        self._object: set[str] = set()
        self._meta: set[str] = set()

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
        # 4) 의류 region 매핑 (의류 화이트리스트도 보강)
        try:
            with open(os.path.join(base, "clothing_regions.json"), "r", encoding="utf-8") as f:
                cr = json.load(f)
            for region, tags in (cr.get("regions") or {}).items():
                self._region_order.append(region)
                for t in tags:
                    n = _norm(t)
                    if n:
                        self._regions[n] = region
                        self._clothes.add(n)   # 명시 의류 → high-confidence
        except Exception as e:
            print(f"[TagIntel] clothing_regions 로드 실패: {e}")
        # 5) copyright 역인덱스 (캐릭터 → copyright).
        #    1순위: characterization.json 의 copyright 필드 (단부루 원본, 정확).
        #    2순위(폴백): copyright_groups.json 에서 '단일 소속'인 누락 캐릭터만 (크로스오버 오염 회피).
        try:
            with open(os.path.join(base, "characterization.json"), "r", encoding="utf-8") as f:
                chars = json.load(f)
            for e in chars:
                tag = _norm(e.get("tag") or "")
                cp = _norm(e.get("copyright") or "")
                if tag and cp and tag not in self._copyright:
                    self._copyright[tag] = cp
        except Exception as e:
            print(f"[TagIntel] characterization(copyright) 로드 실패: {e}")
        try:
            with open(os.path.join(base, "copyright_groups.json"), "r", encoding="utf-8") as f:
                cg = json.load(f)
            multi: dict[str, list[str]] = {}
            for series, groups in cg.items():
                if series.startswith("_") or not isinstance(groups, dict):
                    continue
                for gender in ("girl", "boy", "other"):
                    for ch in (groups.get(gender) or []):
                        if not isinstance(ch, dict):
                            continue
                        for k in [ch.get("name", "")] + list(ch.get("aliases") or []):
                            kn = _norm(k)
                            if not kn:
                                continue
                            lst = multi.setdefault(kn, [])
                            if series not in lst:
                                lst.append(series)
            for kn, serieslist in multi.items():
                if kn not in self._copyright and len(serieslist) == 1:   # 단일 소속만 신뢰
                    self._copyright[kn] = _norm(serieslist[0])
        except Exception as e:
            print(f"[TagIntel] copyright_groups 로드 실패: {e}")
        # 6) 카테고리 사전 (분리 토글용)
        self._expression = self._load_tagset("expression_tags.json")
        self._location = self._load_tagset("location_tags.json")
        self._pose = self._load_tagset("pose_action_tags.json")
        self._object = self._load_tagset("object_tags.json")
        self._meta = self._load_tagset("meta_tags.json")
        print(f"[TagIntel] KR태그 {len(self._cat):,} · 레이팅 {len(self._rating):,} · "
              f"의류 {len(self._clothes):,} · 특징 {len(self._charac):,} · 색상 {len(self._colors):,} · "
              f"region {len(self._regions):,} · copyright {len(self._copyright):,} · "
              f"표정 {len(self._expression):,} · 장소 {len(self._location):,} · "
              f"포즈 {len(self._pose):,} · 사물 {len(self._object):,} · 메타 {len(self._meta):,}")

    def _load_tagset(self, name: str) -> set:
        """다양한 형태(tags / modifiers / groups / categories)의 JSON에서 태그 집합 추출."""
        out: set[str] = set()
        try:
            with open(os.path.join(self._base(), name), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[TagIntel] {name} 로드 실패: {e}")
            return out

        def _collect(v):
            if isinstance(v, str):
                n = _norm(v)
                if n:
                    out.add(n)
            elif isinstance(v, list):
                for x in v:
                    _collect(x)
            elif isinstance(v, dict):
                for k, x in v.items():
                    if k in ("version", "description"):
                        continue
                    _collect(x)

        for key in ("tags", "modifiers", "groups", "categories"):
            if key in data:
                _collect(data[key])
        if not out:   # 알려진 키가 없으면 전체 수집
            _collect(data)
        return out

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

    # ── ④ 의류 region (부위) ──
    def region_of(self, tag: str) -> str:
        """의류 태그의 부위(region) 키. 매핑 없으면 ''."""
        self._ensure()
        return self._regions.get(_norm(tag), "")

    def region_label(self, region: str) -> str:
        return REGION_LABELS.get(region, region)

    def group_by_region(self, tags):
        """의류 태그들을 region별로 그룹화. Returns [{region, label, tags:[...]}] (표시순)."""
        self._ensure()
        buckets: dict[str, list] = {}
        for t in tags:
            r = self._regions.get(_norm(t), "UNASSIGNED")
            buckets.setdefault(r, []).append(t)
        out = []
        for r in self._region_order + ["UNASSIGNED"]:
            if r in buckets:
                out.append({"region": r, "label": REGION_LABELS.get(r, r), "tags": buckets.pop(r)})
        for r, ts in buckets.items():   # order에 없던 나머지
            out.append({"region": r, "label": REGION_LABELS.get(r, r), "tags": ts})
        return out

    # ── ③ copyright (캐릭터 → 시리즈) ──
    def copyright_of(self, character: str) -> str:
        """캐릭터명/별칭 → 대표 copyright(시리즈) 태그. 없으면 ''."""
        self._ensure()
        return self._copyright.get(_norm(character), "")

    def is_character(self, tag: str) -> bool:
        """characterization.json(34k)에 등록된 캐릭터 태그인지 (wiki 분류기 보강용)."""
        self._ensure()
        return _norm(tag) in self._copyright

    def is_copyright(self, tag: str) -> bool:
        """알려진 copyright(시리즈) 태그인지."""
        self._ensure()
        if self._copyright_vals is None:
            self._copyright_vals = set(self._copyright.values())
        return _norm(tag) in self._copyright_vals

    # ── ⑤ 카테고리 판별 ──
    def is_expression(self, tag: str) -> bool:
        self._ensure()
        return _norm(tag) in self._expression

    def is_location(self, tag: str) -> bool:
        self._ensure()
        return _norm(tag) in self._location

    def is_pose(self, tag: str) -> bool:
        self._ensure()
        return _norm(tag) in self._pose

    def is_object(self, tag: str) -> bool:
        self._ensure()
        return _norm(tag) in self._object

    def is_meta(self, tag: str) -> bool:
        self._ensure()
        return _norm(tag) in self._meta

    def _cat_check(self, cat: str):
        return {
            "expression": self.is_expression, "location": self.is_location,
            "pose": self.is_pose, "object": self.is_object, "meta": self.is_meta,
            "clothing": self.is_clothing, "appearance": self.is_appearance,
            "color": self.is_color,
        }.get(cat, lambda t: False)

    def tag_group(self, tag: str) -> str:
        """단일 카테고리 분류(우선순위). UI 색상/그룹용."""
        self._ensure()
        n = _norm(tag)
        if n in _PROMPT_ALLOW:
            return "quality"
        # 표정/포즈/장소/사물이 외견 사전의 오분류보다 우선 (예: 'sitting'이 특징DB에 섞여있음)
        for cat in ("meta", "clothing", "expression", "pose",
                    "location", "object", "appearance", "color"):
            if self._cat_check(cat)(n):
                return cat
        return "other"

    def split_by_categories(self, tags, categories):
        """태그를 지정 카테고리로 분리. 각 태그는 categories 순서상 첫 매칭으로 들어감.
        Returns {'rest': [...], 'groups': {cat: [...]}}."""
        self._ensure()
        groups = {c: [] for c in categories}
        checks = {c: self._cat_check(c) for c in categories}
        rest = []
        for t in tags:
            for c in categories:
                if checks[c](t):
                    groups[c].append(t)
                    break
            else:
                rest.append(t)
        return {"rest": rest, "groups": groups}

    def remove_redundant_subtags(self, tags):
        """덜 구체적인 태그 제거 — 어떤 태그 A의 단어들이 다른 '더 긴' 태그 B의 단어집합에
        진부분집합으로 포함되면 A 제거 (더 구체적인 B만 남김).
        예: muscular ⊂ muscular male → muscular 제거; dress ⊂ blue dress → dress 제거.
        Returns (kept, removed)."""
        items = []
        for t in tags:
            ws = frozenset(_norm(t).split())
            items.append((t, ws))
        kept, removed = [], []
        for i, (t, w) in enumerate(items):
            if not w:
                kept.append(t)
                continue
            if any(j != i and w < w2 for j, (_t2, w2) in enumerate(items)):
                removed.append(t)
            else:
                kept.append(t)
        return kept, removed

    # ── ② color 페어링 결합 ──
    def pair_colors(self, tags):
        """분리된 단일 색상 단어를 바로 뒤 태그와 결합 (결합 결과가 실재 태그일 때만).
        예: ['blue','dress'] → ['blue dress']; ['red','xyz'] → 그대로(미존재)."""
        self._ensure()
        out = []
        i, n = 0, len(tags)
        while i < n:
            cur = tags[i]
            cn = _norm(cur)
            if i + 1 < n and cn in self._colors and len(cn.split()) == 1:
                combo = f"{cur} {tags[i + 1]}".strip()
                if self.is_known(combo):
                    out.append(combo)
                    i += 2
                    continue
            out.append(cur)
            i += 1
        return out


_instance = None


def get_tag_intelligence() -> TagIntelligence:
    global _instance
    if _instance is None:
        _instance = TagIntelligence()
    return _instance

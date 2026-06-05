# tools/refresh_character_tags.py
# -*- coding: utf-8 -*-
"""danbooru 라이브 태그로 tags_db/characterization.json 의 외견(core_tags)을 일괄 교정/갱신.

밤새 돌려놓는 용도. 중단(Ctrl+C)/재개 가능, rate-limit 준수(기본 0.7s/건),
인기 캐릭터(post_count) 우선, scene/meta 노이즈 제거 후 외견 태그만 갱신.

사용 (앱 종료 상태에서 실행 권장):
  python tools/refresh_character_tags.py                 # 전체(34k, ~6시간)
  python tools/refresh_character_tags.py --min-count 100 # post_count 100+ 만 (~14.5k)
  python tools/refresh_character_tags.py --limit 500     # 인기 상위 500개만 (테스트)
  python tools/refresh_character_tags.py --delay 1.0     # 더 느리게(안전)

중단해도 진행도가 _refresh_progress.json 에 저장되어, 다시 실행하면 이어서 진행.
원본은 characterization.json.refresh_bak 으로 1회 백업됩니다.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
CHAR_JSON = os.path.join(BASE, "tags_db", "characterization.json")
PROGRESS = os.path.join(BASE, "tags_db", "_refresh_progress.json")
BACKUP = CHAR_JSON + ".refresh_bak"
HDR = {"User-Agent": "UR_IV/1.0 character tag refresh (personal)"}

_COUNT_RE = re.compile(r"^\d+\+?(girl|boy|other)s?$")
_EXTRA_COUNT = {"solo", "solo focus", "multiple girls", "multiple boys",
                "multiple others", "no humans"}


def is_count_tag(n):
    return bool(_COUNT_RE.match(n)) or n in _EXTRA_COUNT


def make_filter():
    """tag_intelligence 로 외견 태그 판별기 구성 (없으면 느슨한 폴백)."""
    try:
        from core.tag_intelligence import get_tag_intelligence
        ti = get_tag_intelligence(); ti._ensure()

        def keep(tn):
            if is_count_tag(tn):
                return False
            cat = ti.category_of(tn)
            top = cat.split(">")[0].strip() if cat else ""
            if top in ("신체", "패션"):
                return True
            if cat.startswith("인물 > 눈") or cat.startswith("인물 > 머리"):
                return True
            return ti.is_appearance(tn) or ti.is_clothing(tn)
        return keep
    except Exception as e:
        print(f"[warn] tag_intelligence 로드 실패({e}) — 느슨한 폴백 사용")
        return lambda tn: not is_count_tag(tn)


def fetch_features(tag, keep, delay):
    """danbooru에서 캐릭터의 외견 핵심 태그 (frac>=0.2, 상위 28개). 실패 시 None."""
    for q in (f"{tag} solo", tag):
        for attempt in range(3):
            try:
                r = requests.get(
                    "https://danbooru.donmai.us/posts.json",
                    params={"tags": q, "limit": 100, "only": "tag_string_general"},
                    timeout=20, headers=HDR,
                )
                if r.status_code in (429, 500, 502, 503):
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                posts = r.json()
                if not isinstance(posts, list) or not posts:
                    break  # 다음 q
                cnt, n = Counter(), 0
                for p in posts:
                    g = p.get("tag_string_general") if isinstance(p, dict) else ""
                    if not g:
                        continue
                    n += 1
                    for t in g.split():
                        cnt[t] += 1
                if not n:
                    break
                feats = []
                for t, c in cnt.most_common(70):
                    if c / n < 0.2:
                        break
                    tn = t.replace("_", " ")
                    if keep(tn):
                        feats.append(tn)
                if len(feats) >= 3:
                    return feats[:28]
                break
            except requests.RequestException:
                time.sleep(3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-count", type=int, default=0, help="이 post_count 이상만 갱신")
    ap.add_argument("--limit", type=int, default=0, help="인기 상위 N개만 (0=전체)")
    ap.add_argument("--delay", type=float, default=0.7, help="요청 간 대기(초)")
    args = ap.parse_args()

    with open(CHAR_JSON, encoding="utf-8") as f:
        data = json.load(f)
    if not os.path.exists(BACKUP):
        import shutil
        shutil.copy2(CHAR_JSON, BACKUP)
        print(f"백업: {BACKUP}")

    done = set()
    if os.path.exists(PROGRESS):
        try:
            done = set(json.load(open(PROGRESS, encoding="utf-8")))
        except Exception:
            pass

    targets = [e for e in data if e.get("tag") and e["tag"] not in done
               and (e.get("post_count") or 0) >= args.min_count]
    targets.sort(key=lambda e: -(e.get("post_count") or 0))
    if args.limit:
        targets = targets[:args.limit]

    keep = make_filter()
    total = len(targets)
    print(f"대상 {total:,}개 (완료 {len(done):,}) · delay {args.delay}s · "
          f"예상 ~{total * (args.delay + 0.8) / 3600:.1f}시간")
    updated = 0
    t0 = time.time()
    try:
        for i, e in enumerate(targets):
            tag = e["tag"].strip().lower()
            feats = fetch_features(tag, keep, args.delay)
            if feats:
                e["core_tags"] = feats
                updated += 1
            done.add(e["tag"])
            if (i + 1) % 50 == 0 or (i + 1) == total:
                with open(CHAR_JSON, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
                with open(PROGRESS, "w", encoding="utf-8") as f:
                    json.dump(sorted(done), f)
                el = time.time() - t0
                eta = (total - i - 1) * (el / (i + 1)) / 3600
                print(f"  {i+1:,}/{total:,} · 갱신 {updated:,} · ETA {eta:.1f}h · 저장됨")
            time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\n중단됨 — 진행도 저장 중...")
        with open(CHAR_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        with open(PROGRESS, "w", encoding="utf-8") as f:
            json.dump(sorted(done), f)
        print("저장 완료. 다시 실행하면 이어서 진행됩니다.")
        return
    print(f"\n완료: {updated:,}개 갱신 / {total:,}개 처리")
    print("앱 재시작하면 갱신된 캐릭터 외견이 반영됩니다.")


if __name__ == "__main__":
    main()

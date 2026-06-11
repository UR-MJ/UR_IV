# core/prompt_for_nl.py
"""nl_caption(태그→자연어) LLM 입력 정리 — 순수 함수(Qt 의존 없음, 테스트 가능).

LLM에는 '묘사할 내용'만 보내야 정확하다. 다음은 묘사 대상이 아니거나(오히려
네거티브를 *있는 것*으로 묘사하게 만들어) 작은 모델을 혼란시키므로 제거한다:
  - 네거티브 가중치 그룹: (tag, tag:-1.0)  ← 빼고 싶은 것 (음수 weight)
  - LoRA: <lora:name:0.8>, 그리고 @트리거(화풍/로라 태그) @enast 등
  - 선행/후행 고정 품질·메타: masterpiece, best quality, score_9, highres,
    absurdres, newest/oldest, year2025, rating: 등

유지: 인물수(1boy/2girls), 캐릭터(시리즈 괄호 'alex (stardew valley)' 포함),
작품(copyright), 일반(메인) 태그. 양수 가중치 괄호 (tag:1.2)는 내용만 남기고 weight 제거.
"""
import re

# 묘사 대상이 아닌 품질/메타 태그 (정확히 일치 시 제거, 소문자 비교)
_META_EXACT = {
    'masterpiece', 'best quality', 'high quality', 'normal quality', 'low quality',
    'worst quality', 'bad quality', 'highres', 'absurdres', 'lowres', 'high resolution',
    'very aesthetic', 'aesthetic', 'official art', 'newest', 'recent', 'mid', 'early',
    'oldest', 'ai-generated', 'ai generated',
}
# 접두 일치 시 제거 (score_9, year2025, rating:safe, source_anime 등)
_META_PREFIX = ('score_', 'year ', 'year2', 'year1', 'rating:', 'source_')

# 네거티브 가중치 그룹: (...:-N) — 내부 콤마 포함 통째로 제거
_RE_NEG_GROUP = re.compile(r'\([^()]*:\s*-\d+(?:\.\d+)?\s*\)')
# 양수 가중치 그룹: (content:N) → content (weight 제거). 'char (series)'는 콜론 없어 미해당
_RE_POS_GROUP = re.compile(r'\(([^()]*?):\s*\d+(?:\.\d+)?\s*\)')
# <lora:...>
_RE_LORA = re.compile(r'<lora:[^>]*>', re.IGNORECASE)


def clean_tags_for_nl(prompt: str) -> str:
    """nl_caption LLM 입력용으로 태그 문자열 정리. 인물수/캐릭터/작품/메인만 남긴다."""
    if not prompt:
        return ''
    s = prompt
    s = _RE_LORA.sub('', s)
    s = _RE_NEG_GROUP.sub('', s)        # 네거티브 그룹 먼저 (내부 콤마 포함) 제거
    s = _RE_POS_GROUP.sub(r'\1', s)     # 양수 가중치 → 내용만

    out = []
    for raw in s.split(','):
        t = raw.strip()
        if not t:
            continue
        low = t.lower()
        if t.startswith('@'):           # 화풍/LoRA 트리거 태그
            continue
        if low in _META_EXACT:
            continue
        if any(low.startswith(p) for p in _META_PREFIX):
            continue
        out.append(t)
    return ', '.join(out)

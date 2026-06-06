# core/tag_matcher.py
"""통합 태그 매칭 엔진 — Search / Event Gen 공용

문법:
  word      → 포함 매칭 (tag에 word가 포함된 모든 것)
  *word     → 완전 일치 (정확히 word인 태그만)
  _word     → 접미 매칭 (word로 끝나는 태그, e.g. short hair, long hair)
  word_     → 접두 매칭 (word로 시작하는 태그, e.g. hair ornament)
  _word_    → 포함 매칭 (명시적, word와 동일)
  [A, B]    → AND 그룹 (A와 B 모두 존재)
  [A|B]     → OR 그룹 (A 또는 B 중 하나 이상)
  쉼표(,)   → AND (대괄호 밖에서)
"""
import re
import pandas as pd


def _normalize(text: str) -> str:
    """밑줄을 공백으로, 소문자"""
    return text.strip().lower().replace('_', ' ')


def parse_query(query: str) -> list:
    """쿼리 문자열을 파싱하여 조건 리스트로 변환

    Returns: [ {'type': 'and'|'or'|'single', 'terms': [str, ...], 'has_wildcard'?: bool} ]

    특수 케이스: OR 그룹 안에 빈 토큰이 있으면 (`[A|B|]` 처럼 trailing |)
      → has_wildcard=True 로 표시 → '이 필드 조건은 매칭 안 되어도 통과'
      → 즉 이 OR 그룹이 항상 True를 반환하므로 AND 모드에서도 해당 필드 면제 효과
      예) AND 모드, copyright=`[tears of themis|alchemy stars|]`
          → '작품이 TOT 또는 AS 또는 작품 무관' (copyright 조건 사실상 면제)
    """
    if not query or not query.strip():
        return []

    # 대괄호 밖의 쉼표로 분리
    parts = re.split(r',\s*(?![^\[]*\])', query.strip())
    conditions = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # [A|B|C] → OR 그룹
        m = re.match(r'^\[(.+)\]$', part)
        if m:
            inner = m.group(1)
            if '|' in inner:
                raw = [t.strip() for t in inner.split('|')]
                # 와일드카드는 trailing 빈 토큰(`|]` 직전)에서만 인식 — 명시적 신호로 한정.
                # 중간 `||`(이중 파이프)는 사용자 오타/정렬 흔적이라 와일드카드 발동 X,
                # 그냥 빈 토큰은 필터링하여 정리. 양 끝의 leading `|`도 동일하게 무시.
                #   예) [A|B|]     → has_wildcard=True  (trailing empty)
                #   예) [A||B]     → has_wildcard=False (중간 || 는 그냥 정리)
                #   예) [|A|B]     → has_wildcard=False (leading empty 는 무시)
                #   예) [|A|B|]    → has_wildcard=True  (trailing empty 가 있으면 wildcard)
                has_wildcard = len(raw) > 0 and raw[-1] == ''
                terms = [t for t in raw if t]
                conditions.append({
                    'type': 'or',
                    'terms': terms,
                    'has_wildcard': has_wildcard,
                })
            elif ',' in inner:
                # AND 그룹 — 빈 토큰은 그냥 무시 (AND에서 True&X=X 이므로 영향 없음)
                terms = [t.strip() for t in inner.split(',') if t.strip()]
                conditions.append({'type': 'and', 'terms': terms})
            else:
                conditions.append({'type': 'single', 'terms': [inner.strip()]})
        else:
            conditions.append({'type': 'single', 'terms': [part]})

    return conditions


def _eval_condition(col_lower: pd.Series, cond: dict, index) -> pd.Series:
    """단일 조건(dict)을 평가하여 Boolean mask 반환.
    cond['type']: 'or' | 'and' | 'single'
    """
    if cond['type'] == 'or':
        # has_wildcard=True 면 [A|B|] 같은 빈 토큰 포함 그룹 → 무조건 통과
        if cond.get('has_wildcard'):
            return pd.Series(True, index=index)
        # [A|B] — 명시적 OR
        cm = pd.Series(False, index=index)
        for term in cond['terms']:
            cm |= _apply_pattern(col_lower, term)
        return cm
    elif cond['type'] == 'and':
        # [A,B] — 명시적 AND 그룹
        cm = pd.Series(True, index=index)
        for term in cond['terms']:
            cm &= _apply_pattern(col_lower, term)
        return cm
    else:
        # single — bare 콤마 토큰
        return _apply_pattern(col_lower, cond['terms'][0])


def filter_dataframe(df: pd.DataFrame, col: str, query: str,
                     default_combine: str = 'and',
                     col_lower: pd.Series = None) -> pd.Series:
    """DataFrame에 쿼리를 적용하여 Boolean mask 반환

    :param df: DataFrame
    :param col: 태그 문자열이 있는 컬럼명
    :param query: 사용자 입력 쿼리
    :param default_combine: 'and' (콤마=AND, 기본) | 'or' (콤마=OR)
        - 명시적 대괄호 그룹은 모드 무관:
          [A|B] → 항상 OR, [A,B] → 항상 AND
        - bare 콤마(대괄호 밖) 토큰 결합 방식만 모드에 따라 변경
    :param col_lower: 미리 lowercase한 시리즈 (성능 최적화용).
        넘기면 .str.lower() 호출 생략. None이면 내부에서 계산.

    구현: 누적식 평가 (마스크를 한 번에 들고 다니지 않음).
      AND 모드: True에서 시작해 &= 누적 → short-circuit 비슷한 효과
      OR  모드: False에서 시작해 |= 누적
    """
    conditions = parse_query(query)
    if not conditions:
        return pd.Series(True, index=df.index)

    if col_lower is None:
        col_lower = df[col].fillna('').str.lower()
    use_or = (str(default_combine).lower() == 'or')

    if use_or:
        # OR 모드: False에서 시작해 누적 |=
        result = pd.Series(False, index=df.index)
        for cond in conditions:
            result |= _eval_condition(col_lower, cond, df.index)
        return result
    else:
        # AND 모드: True에서 시작해 누적 &= (기존과 동일한 메모리 패턴)
        result = pd.Series(True, index=df.index)
        for cond in conditions:
            result &= _eval_condition(col_lower, cond, df.index)
        return result


def _apply_pattern(col_series: pd.Series, pattern: str) -> pd.Series:
    """단일 패턴을 Series에 적용하여 Boolean mask 반환
    col_series: 소문자 변환된 원본 (danbooru: 공백+밑줄, SD: 콤마+공백)
    양쪽 형식 모두 지원: 패턴을 공백/밑줄 양쪽으로 매칭
    """
    pattern = pattern.strip()
    if not pattern:
        return pd.Series(True, index=col_series.index)

    def _both(text):
        """공백과 밑줄 양쪽 버전의 정규식 OR 패턴"""
        t1 = re.escape(text.lower().replace('_', ' '))
        t2 = re.escape(text.lower().replace(' ', '_'))
        return f'(?:{t1}|{t2})' if t1 != t2 else t1

    # 태그 경계: 시작/끝 또는 구분자(콤마, 공백)
    SEP_L = r'(?:^|[,\s]\s*)'
    SEP_R = r'(?:\s*[,\s]|$)'

    # *word → 완전 일치
    if pattern.startswith('*'):
        target = pattern[1:].strip()
        pat = SEP_L + _both(target) + SEP_R
        return col_series.str.contains(pat, regex=True, na=False)

    # _word_ → 포함 (명시적)
    if pattern.startswith('_') and pattern.endswith('_') and len(pattern) > 2:
        target = pattern[1:-1].strip()
        t1 = target.lower().replace('_', ' ')
        t2 = target.lower().replace(' ', '_')
        return col_series.str.contains(t1, regex=False, na=False) | col_series.str.contains(t2, regex=False, na=False)

    # _word → 접미 (태그가 word로 끝남)
    if pattern.startswith('_') and not pattern.endswith('_'):
        target = pattern[1:].strip()
        pat = _both(target) + SEP_R
        return col_series.str.contains(pat, regex=True, na=False)

    # word_ → 접두 (태그가 word로 시작)
    if pattern.endswith('_') and not pattern.startswith('_'):
        target = pattern[:-1].strip()
        pat = SEP_L + _both(target)
        return col_series.str.contains(pat, regex=True, na=False)

    # 기본: 포함 매칭 (양쪽 형식)
    t1 = pattern.lower().replace('_', ' ')
    t2 = pattern.lower().replace(' ', '_')
    return col_series.str.contains(t1, regex=False, na=False) | col_series.str.contains(t2, regex=False, na=False)

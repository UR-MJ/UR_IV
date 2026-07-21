# core/resolution_guard.py
"""해상도 가드 — 순수 함수(테스트 가능). UI/Qt 의존 없음.

ANIMA 모델은 면적(1536×1536) 이내에서 안정적이므로, 고해상도/자동해상도 모드에서
최종 해상도의 '면적'을 한도 이내로 제한한다. (한 변이 1536을 넘어도 면적이 한도
이내면 허용 — 세로/가로로 긴 비율 지원.)
"""

ANIMA_MAX_AREA_SIDE = 1536
ANIMA_MAX_AREA = ANIMA_MAX_AREA_SIDE * ANIMA_MAX_AREA_SIDE  # = 2,359,296 px
ANIMA_MAX_SIDE = 2048          # 한 변 최대 (실측: 한 변 2048까지 안전, 그 이상은 OOM/아티팩트)
ANIMA_GUARD_MIN_DIMENSION = 256
ANIMA_GUARD_MAX_DIMENSION = 8192


def _normalize_dimension(value, default: int) -> int:
    """설정에서 받은 해상도 값을 안전 범위의 8배수로 정규화."""
    try:
        dimension = int(float(value))
    except (TypeError, ValueError, OverflowError):
        dimension = default
    dimension = max(ANIMA_GUARD_MIN_DIMENSION,
                    min(ANIMA_GUARD_MAX_DIMENSION, dimension))
    return (dimension // 8) * 8


def normalize_anima_guard_prefs(prefs=None) -> dict:
    """ui_prefs 값을 검증해 런타임에서 바로 쓸 수 있는 Guard 설정으로 반환."""
    prefs = prefs if isinstance(prefs, dict) else {}
    enabled = prefs.get('animaGuardEnabled', True)
    if not isinstance(enabled, bool):
        enabled = str(enabled).strip().lower() not in ('0', 'false', 'no', 'off', '')

    area_side = _normalize_dimension(
        prefs.get('animaGuardMaxAreaSide'), ANIMA_MAX_AREA_SIDE)
    max_side = _normalize_dimension(
        prefs.get('animaGuardMaxSide'), ANIMA_MAX_SIDE)
    return {
        'animaGuardEnabled': enabled,
        'animaGuardMaxAreaSide': area_side,
        'animaGuardMaxSide': max_side,
    }


def _floor8(v: float) -> int:
    """8 배수로 내림 정렬(최소 8). SD/Forge 호환."""
    return max(8, (int(v) // 8) * 8)


def apply_anima_resolution(base_w, base_h, hr_factor=1.0,
                           auto_res=False, max_area=ANIMA_MAX_AREA,
                           max_side=ANIMA_MAX_SIDE, enabled=True):
    """고해상도(hr_factor)·자동해상도(auto_res)에서 ANIMA 면적/한변 캡을 적용.

    규칙:
      - hr_factor > 1.0 이면 base × factor 로 확대(8배수 정렬).
      - Guard가 켜진 자동해상도(auto_res)에서 확대본 면적이 한도를 넘으면
        '이번엔 고해상도 스킵'(base 사용).
      - Guard가 켜진 상태에서 면적이 한도를 넘으면 비율 유지하며 축소.
      - 면적은 한도 이내여도 '한 변'이 max_side를 넘으면 비율 유지하며 양쪽 축소.
      - 수동 해상도 + 고해상도 OFF(hr_factor==1.0) 는 사용자 의도 존중 → 캡 미적용.
      - enabled=False이면 고해상도 배율만 적용하고 면적/한변 캡은 건너뜀.

    :return: (width, height) — 8 배수 정렬된 정수.
    """
    width, height = int(base_w), int(base_h)

    if hr_factor > 1.0:
        cand_w = _floor8(base_w * hr_factor)
        cand_h = _floor8(base_h * hr_factor)
        if enabled and auto_res and (cand_w * cand_h > max_area):
            width, height = int(base_w), int(base_h)   # 자동: 고해상도 스킵
        else:
            width, height = cand_w, cand_h

    capped = auto_res or hr_factor > 1.0

    # 면적 캡 (비율 유지)
    if enabled and capped and (width * height > max_area):
        scale = (max_area / float(width * height)) ** 0.5
        width = _floor8(width * scale)
        height = _floor8(height * scale)

    # 한 변 캡 (비율 유지) — 긴 변을 max_side에 맞추고 짧은 변도 같은 비율로 축소
    if enabled and capped and max_side and max(width, height) > max_side:
        scale = max_side / float(max(width, height))
        width = _floor8(width * scale)
        height = _floor8(height * scale)

    return width, height

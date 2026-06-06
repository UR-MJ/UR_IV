# core/resolution_guard.py
"""해상도 가드 — 순수 함수(테스트 가능). UI/Qt 의존 없음.

ANIMA 모델은 면적(1536×1536) 이내에서 안정적이므로, 고해상도/자동해상도 모드에서
최종 해상도의 '면적'을 한도 이내로 제한한다. (한 변이 1536을 넘어도 면적이 한도
이내면 허용 — 세로/가로로 긴 비율 지원.)
"""

ANIMA_MAX_AREA = 1536 * 1536  # = 2,359,296 px


def _floor8(v: float) -> int:
    """8 배수로 내림 정렬(최소 8). SD/Forge 호환."""
    return max(8, (int(v) // 8) * 8)


def apply_anima_resolution(base_w, base_h, hr_factor=1.0,
                           auto_res=False, max_area=ANIMA_MAX_AREA):
    """고해상도(hr_factor)·자동해상도(auto_res)에서 ANIMA 면적캡을 적용.

    규칙:
      - hr_factor > 1.0 이면 base × factor 로 확대(8배수 정렬).
      - 자동해상도(auto_res)에서 확대본 면적이 한도를 넘으면 '이번엔 고해상도 스킵'(base 사용).
      - 자동해상도 또는 고해상도 모드에서 최종 면적이 한도를 넘으면 비율 유지하며 축소.
      - 수동 해상도 + 고해상도 OFF(hr_factor==1.0) 는 사용자 의도 존중 → 캡 미적용.

    :return: (width, height) — 8 배수 정렬된 정수.
    """
    width, height = int(base_w), int(base_h)

    if hr_factor > 1.0:
        cand_w = _floor8(base_w * hr_factor)
        cand_h = _floor8(base_h * hr_factor)
        if auto_res and (cand_w * cand_h > max_area):
            width, height = int(base_w), int(base_h)   # 자동: 고해상도 스킵
        else:
            width, height = cand_w, cand_h

    if (auto_res or hr_factor > 1.0) and (width * height > max_area):
        scale = (max_area / float(width * height)) ** 0.5
        width = _floor8(width * scale)
        height = _floor8(height * scale)

    return width, height

# -*- coding: utf-8 -*-
"""``core/theme_presets.py`` → Vue 쪽 사본 3종을 다시 만든다.

프리셋을 고쳤으면 이걸 돌린다. 안 돌리면 ``tests/test_theme_contract.py`` 가 잡는다.

  - ``frontend/src/theme/presets.ts``          색 표 사본
  - ``frontend/src/theme/__golden__.json``     계산 결과 golden (vitest 가 대조)
  - ``frontend/src/styles/theme-fallback.css`` 스크립트 실패 시 안전망

실행: ``venv\\Scripts\\python.exe tools/gen_theme_css.py``
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.theme_presets import (  # noqa: E402
    PRESETS,
    EDITABLE_KEYS,
    TAG_HUES,
    DEFAULT_PRESET,
    resolve,
    derive_accent,
    contrast_ratio,
    shift_lightness,
    css_variables,
)

#: golden 에 넣을 표본. 경계 사례를 일부러 섞는다 —
#: ``#D14747`` 은 흰 글자도 검은 글자도 4.5:1 이 안 나오는 중간 밝기 색이다.
SAMPLES = [
    '#C9A227', '#FACC15', '#8A6A00', '#7FA8D6', '#FFFFFF',
    '#000000', '#E18E94', '#2C8549', '#D14747',
]

_HEADER = """/**
 * 테마 프리셋 — `core/theme_presets.py` 의 사본.
 *
 * **원본은 Python 이다.** 앱은 Vue 가 뜨기 전에 PyQt 다이얼로그(백엔드 선택·스플래시)를
 * 먼저 그리므로 색을 시작 시점에 Python 이 읽을 수 있어야 한다. 여기는 브라우저가
 * 첫 페인트 전에 색을 넣기 위한 사본이고, 두 벌이 갈라지지 않는지는
 * `tests/test_theme_contract.py` 가 정적으로 검증한다.
 *
 * **이 파일을 직접 고치지 말 것** — `core/theme_presets.py` 를 고치고
 * `tools/gen_theme_css.py` 를 다시 돌린다.
 */
"""

_CSS_HEADER = """/* 테마 폴백 — `core/theme_presets.py` 의 '{preset}' 프리셋에서 생성.
 *
 * 실제 색은 `theme/applyTheme.ts` 가 첫 페인트 전에 `documentElement` 인라인
 * 스타일로 넣는다(인라인이 :root 규칙보다 우선한다). 여기 값은 **스크립트가
 * 실패했을 때 앱이 색 없이 뜨지 않게** 하는 안전망이고, 동시에 토큰의 전체 목록이다.
 *
 * 손으로 고치지 말 것 — `core/theme_presets.py` 를 고치고
 * `tools/gen_theme_css.py` 를 다시 돌린다.
 */
"""


def _ts_entries(data: dict[str, str], indent: int) -> str:
    pad = ' ' * indent
    lines = []
    for key, value in data.items():
        name = key if key.replace('_', '').isalnum() else f"'{key}'"
        lines.append(f'{pad}{name}: {json.dumps(value, ensure_ascii=False)},')
    return '\n'.join(lines)


def write_presets_ts() -> pathlib.Path:
    body = '\n'.join(
        f'  {name}: {{\n{_ts_entries(colors, 4)}\n  }},'
        for name, colors in PRESETS.items()
    )
    out = (
        _HEADER
        + "\nexport type ThemeMode = 'dark' | 'light'\n"
        + "\n/** 색 표. `mode`/`label` 은 색이 아니라 메타데이터다. */\n"
        + 'export type ThemeColors = Record<string, string>\n'
        + '\n/** 사용자가 설정에서 직접 바꿀 수 있는 색. 나머지는 프리셋이 정한다. */\n'
        + f'export const EDITABLE_KEYS = {json.dumps(list(EDITABLE_KEYS))} as const\n'
        + 'export type EditableKey = (typeof EDITABLE_KEYS)[number]\n'
        + '\n/** 태그 분류의 색상각(도) — 프리셋이 바뀌어도 고정. */\n'
        + f'export const TAG_HUES: Record<string, number> = {json.dumps(TAG_HUES)}\n'
        + f"\nexport const DEFAULT_PRESET = '{DEFAULT_PRESET}'\n"
        + '\nexport const PRESETS: Record<string, ThemeColors> = {\n'
        + body
        + '\n}\n'
        + '\nexport const PRESET_IDS = Object.keys(PRESETS)\n'
    )
    path = ROOT / 'frontend' / 'src' / 'theme' / 'presets.ts'
    path.write_text(out, encoding='utf-8')
    return path


def write_golden() -> pathlib.Path:
    golden = {
        'derive': {
            f'{color}|{mode}': derive_accent(color, mode)
            for color in SAMPLES for mode in ('dark', 'light')
        },
        'contrast': {
            f'{a}|{b}': round(contrast_ratio(a, b), 6)
            for a in SAMPLES[:5] for b in ('#0A0A0A', '#FFFFFF', '#F4F4F2')
        },
        'shift': {
            f'{color}|{delta}': shift_lightness(color, delta)
            for color in SAMPLES for delta in (0.10, -0.08, 0.25)
        },
        'resolve': {name: resolve(name) for name in PRESETS},
        'resolve_override': resolve(
            'light', {'accent': '#2563eb', 'state-ok': 'bad', 'bg-primary': '#FF0000'}
        ),
    }
    path = ROOT / 'frontend' / 'src' / 'theme' / '__golden__.json'
    path.write_text(
        json.dumps(golden, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8'
    )
    return path


def write_fallback_css() -> pathlib.Path:
    colors = resolve(DEFAULT_PRESET)
    out = (
        _CSS_HEADER.format(preset=DEFAULT_PRESET)
        + '\n:root {\n'
        + css_variables(colors)
        + '\n}\n'
    )
    path = ROOT / 'frontend' / 'src' / 'styles' / 'theme-fallback.css'
    path.write_text(out, encoding='utf-8')
    return path


if __name__ == '__main__':
    for generated in (write_presets_ts(), write_golden(), write_fallback_css()):
        print('생성:', generated.relative_to(ROOT).as_posix())

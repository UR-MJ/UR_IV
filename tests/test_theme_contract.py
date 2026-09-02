# -*- coding: utf-8 -*-
"""테마 계약 회귀 테스트 — 색의 단일 출처가 조용히 갈라지는 것을 막는다.

`core/theme_presets.py` 가 원본이고, `frontend/src/theme/presets.ts` 와
`frontend/src/styles/theme-fallback.css` 는 `tools/gen_theme_css.py` 가 만든 사본이다.
사본이 낡아도 **예외는 안 난다** — 파이썬이 그린 시작 다이얼로그와 Vue 화면의 색이
서로 다를 뿐이라 앱이 두 개처럼 보인다. 이 저장소의 단골 실패 방식이라 정적으로 잡는다.
(`test_bridge_contract.py` · `test_editor_tools_contract.py` 와 같은 방식 — Qt 비의존.)

대비 검사를 여기 두는 이유도 같다. 프리셋에 색 하나를 새로 넣거나 명도를 조금 옮기는
일은 화면에서 티가 안 나지만, 그 색으로 쓴 글자는 특정 배경에서만 안 읽히게 된다.
숫자로 못박아 두면 프리셋을 손댈 때 바로 걸린다.
"""

from __future__ import annotations

import colorsys
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
PRESETS_TS = SRC / "theme" / "presets.ts"
FALLBACK_CSS = SRC / "styles" / "theme-fallback.css"

from core.theme_presets import (  # noqa: E402
    DEFAULT_PRESET,
    EDITABLE_KEYS,
    PRESETS,
    TAG_HUES,
    contrast_ratio,
    css_variables,
    derive_accent,
    resolve,
)

#: 사본이 어긋났을 때 무엇을 하면 되는지. 메시지마다 붙인다.
REGEN = "→ `venv\\Scripts\\python.exe tools/gen_theme_css.py` 를 다시 돌려라."

# ── 대비 기준 ──────────────────────────────────────────────────────────────
#: 글이 얹히는 면. 버튼 채움도 글자를 이고 있으므로 본문 검사에는 포함한다.
ALL_BACKGROUNDS = (
    "bg-primary", "bg-secondary", "bg-card", "bg-input", "bg-button", "bg-button-hover",
)
#: 태그칩·상태문구·경계도 **버튼 위에 앉는다**. 처음엔 여기서 버튼 면을 뺐다가
#: 놓쳤다 — 라이트 프리셋이 페이지(#F4F4F2)에서는 통과하고 버튼 hover(#DDDDD9)
#: 에서만 4.1:1 로 무너져, 브라우저에서 26곳이 잡혔다. 면은 하나도 빼지 않는다.
SURFACES = ALL_BACKGROUNDS

MIN_BODY = 4.5      # 본문 글자
MIN_LABEL = 4.5     # 라벨·보조 글자(text-muted) — 아래 주석 참조
MIN_EDGE = 3.0      # 보여야 하는 경계(비텍스트 UI 요소 기준)
MIN_STATE = 4.5     # 상태 글자색
MIN_TAG = 4.5       # 태그 글자색

STATE_ROLES = ("info", "alert", "ok", "warn")
#: 4.5:1 을 지켜야 하는 태그 7색. `tag-wild-edge` 는 **일부러 흐린** 색이라 뺀다
#: (와일드카드 테두리를 눈에 덜 띄게 하는 게 목적이다 — 글자로 읽힐 필요가 없다).
TAG_TEXT_KEYS = (
    "tag-person", "tag-scene", "tag-pose", "tag-wear", "tag-fx", "tag-nsfw", "tag-neutral",
)

#: 태그끼리 최소 색상각 이격. 이보다 붙으면 칩 색으로 분류를 구분할 수 없다.
MIN_TAG_HUE_GAP = 30
#: 강조색과의 최소 이격. 태그가 '선택됨' 표시처럼 보이면 안 된다.
MIN_ACCENT_HUE_GAP = 40

#: `<style>` 안에 남은 하드코딩 hex 상한.
#: **이 숫자는 줄어들기만 해야 한다.** 리디자인 시작 시점 747곳에서 토큰으로 옮기는 중이고,
#: 그림자·캔버스 기본색 같은 정당한 예외가 남으므로 0 은 될 수 없다.
#: 새 하드코딩을 막는 게 목적이니 올리지 말고, 정리가 끝나면 실제 수치까지 내려라.
MAX_HARDCODED_HEX = 120

_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S)
#: 3·4·6·8 자리 모두 — 알파를 붙인 `#0A0A0A80` 도 하드코딩이다.
_HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")

# ── TS 사본 파싱 ───────────────────────────────────────────────────────────
# 생성기가 찍는 리터럴이라 JSON 에 가깝다. 키만 `'bg-primary'` 처럼 따옴표가 붙는다.
_TS_PRESET = re.compile(r"^  (?P<name>\w+): \{\n(?P<body>.*?)^  \},$", re.M | re.S)
_TS_ENTRY = re.compile(r"^\s*'?(?P<key>[\w-]+)'?:\s*\"(?P<value>[^\"]*)\",\s*$", re.M)
_TS_EDITABLE = re.compile(r"export const EDITABLE_KEYS = (\[[^\]]*\])")
_TS_HUES = re.compile(r"export const TAG_HUES: Record<string, number> = (\{[^}]*\})")
_TS_DEFAULT = re.compile(r"export const DEFAULT_PRESET = '([\w-]+)'")

_CSS_VAR = re.compile(r"^\s*--([\w-]+):\s*(.+?);\s*$", re.M)


def _ts_presets(text: str) -> dict[str, dict[str, str]]:
    """`export const PRESETS = { ... }` 본문만 잘라 파싱한다.

    타입 주석(`Record<string, ThemeColors>`)에 중괄호가 없어 안전하지만, 뒤따르는
    `PRESET_IDS` 까지 먹지 않도록 **줄 맨 앞의 `}`** 를 끝으로 본다.
    """
    after = text.split("export const PRESETS", 1)[1]
    body = after.split("= {", 1)[1].split("\n}", 1)[0]
    return {
        m.group("name"): {
            e.group("key"): e.group("value") for e in _TS_ENTRY.finditer(m.group("body"))
        }
        for m in _TS_PRESET.finditer(body)
    }


def _hue(hex_color: str) -> float:
    """색상각(도). 무채색이면 0 — 이 파일에서 무채색 강조색은 검사 대상이 아니다."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def _hue_gap(a: float, b: float) -> float:
    """색상환은 원형이라 356°와 4°는 8° 떨어진 것이다."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _worst(color: str, backgrounds, colors: dict[str, str]) -> tuple[float, str]:
    """가장 불리한 배경과 그때의 대비비."""
    pairs = [(contrast_ratio(color, colors[bg]), bg) for bg in backgrounds]
    return min(pairs)


class ThemeCopySyncTests(unittest.TestCase):
    """파이썬 원본 ↔ Vue 사본. 어긋나면 앱의 두 절반이 다른 색을 쓴다."""

    @classmethod
    def setUpClass(cls):
        cls.ts_text = PRESETS_TS.read_text(encoding="utf-8")
        cls.ts_presets = _ts_presets(cls.ts_text)
        cls.css_text = FALLBACK_CSS.read_text(encoding="utf-8")

    def test_parsing_is_not_silently_empty(self):
        # 안전장치 — 정규식이 깨지면 '전부 일치'로 거짓 통과한다
        self.assertGreaterEqual(len(self.ts_presets), 3, f"presets.ts 를 파싱하지 못했다. {REGEN}")
        for name, colors in self.ts_presets.items():
            self.assertGreaterEqual(len(colors), 20, f"presets.ts 의 '{name}' 이 거의 비었다")
        self.assertGreaterEqual(len(_CSS_VAR.findall(self.css_text)), 20, "폴백 CSS 를 파싱하지 못했다")

    def test_preset_names_match(self):
        self.assertEqual(
            sorted(self.ts_presets), sorted(PRESETS),
            f"프리셋 목록이 파이썬과 다르다. {REGEN}")

    def test_every_preset_color_matches_python(self):
        for name, expected in PRESETS.items():
            actual = self.ts_presets.get(name, {})
            self.assertEqual(
                sorted(actual), sorted(expected),
                f"'{name}' 프리셋의 키 집합이 다르다. {REGEN}")
            for key, value in expected.items():
                self.assertEqual(
                    actual.get(key), value,
                    f"'{name}.{key}' 가 파이썬({value}) 과 TS({actual.get(key)}) 에서 다르다. {REGEN}")

    def test_editable_keys_match(self):
        raw = _TS_EDITABLE.search(self.ts_text)
        self.assertIsNotNone(raw, f"presets.ts 에서 EDITABLE_KEYS 를 찾지 못했다. {REGEN}")
        self.assertEqual(
            json.loads(raw.group(1)), list(EDITABLE_KEYS),
            f"사용자가 바꿀 수 있는 색 목록이 두 벌에서 다르다 — "
            f"설정 화면이 저장한 값을 파이썬이 무시하게 된다. {REGEN}")

    def test_tag_hues_match(self):
        raw = _TS_HUES.search(self.ts_text)
        self.assertIsNotNone(raw, f"presets.ts 에서 TAG_HUES 를 찾지 못했다. {REGEN}")
        parsed = json.loads(raw.group(1))
        self.assertEqual(parsed, dict(TAG_HUES), f"태그 색상각이 두 벌에서 다르다. {REGEN}")

    def test_default_preset_matches(self):
        raw = _TS_DEFAULT.search(self.ts_text)
        self.assertIsNotNone(raw, f"presets.ts 에서 DEFAULT_PRESET 을 찾지 못했다. {REGEN}")
        self.assertEqual(
            raw.group(1), DEFAULT_PRESET,
            f"기본 프리셋이 다르다 — 설정이 없는 첫 실행에서 두 절반이 다른 테마로 뜬다. {REGEN}")

    def test_fallback_css_matches_resolved_default(self):
        """폴백 CSS 는 토큰의 전체 목록이기도 하다 — 낡으면 없는 토큰이 생긴다."""
        expected = dict(
            line.strip().lstrip("-").split(": ", 1)
            for line in css_variables(resolve(DEFAULT_PRESET)).splitlines()
        )
        expected = {k: v.rstrip(";") for k, v in expected.items()}
        actual = {name: value for name, value in _CSS_VAR.findall(self.css_text)}

        self.assertEqual(
            sorted(actual), sorted(expected),
            f"폴백 CSS 의 토큰 목록이 resolve('{DEFAULT_PRESET}') 과 다르다. {REGEN}")
        for key, value in expected.items():
            self.assertEqual(
                actual.get(key), value,
                f"폴백 CSS 의 --{key} 가 {actual.get(key)} 인데 파이썬은 {value} 다. {REGEN}")

    def test_derived_accent_tokens_are_in_the_fallback(self):
        """`accent-fill`·`on-accent` 는 프리셋에 없고 계산으로 생긴다.

        생성기가 `resolve()` 대신 `PRESETS[...]` 를 쓰면 이 토큰들이 폴백에서 통째로
        빠지고, 스크립트가 실패한 화면에서 주 버튼이 배경도 글자색도 없이 뜬다.
        """
        for token in ("accent-hover", "accent-dim", "accent-fill", "accent-fill-hover", "on-accent"):
            self.assertIn(f"--{token}:", self.css_text, f"폴백 CSS 에 --{token} 이 없다. {REGEN}")


class PresetShapeTests(unittest.TestCase):
    """프리셋끼리 모양이 같아야 한다."""

    def test_all_presets_have_the_same_keys(self):
        """한 프리셋에만 있는 색은 다른 테마에서 **빈 값**이 된다.

        `var(--tag-fx)` 가 폴백 없이 비면 브라우저는 그 속성 자체를 무시한다 —
        예외도 경고도 없이 글자색만 상속으로 돌아간다. 눈으로는 못 찾는다.
        """
        reference = sorted(PRESETS[DEFAULT_PRESET])
        for name, colors in PRESETS.items():
            missing = set(reference) - set(colors)
            extra = set(colors) - set(reference)
            self.assertEqual(
                (sorted(missing), sorted(extra)), ([], []),
                f"'{name}' 프리셋의 키가 '{DEFAULT_PRESET}' 과 다르다 "
                f"(빠짐={sorted(missing)}, 추가={sorted(extra)})")

    def test_every_preset_declares_mode_and_label(self):
        for name, colors in PRESETS.items():
            self.assertIn(colors.get("mode"), ("dark", "light"), f"'{name}' 의 mode 가 이상하다")
            self.assertTrue(colors.get("label"), f"'{name}' 에 설정 화면용 라벨이 없다")

    def test_editable_keys_exist_in_every_preset(self):
        """사용자가 바꿀 수 있다고 해 놓고 프리셋에 없으면 resolve 가 KeyError 를 낸다."""
        for name, colors in PRESETS.items():
            for key in EDITABLE_KEYS:
                self.assertIn(key, colors, f"'{name}' 에 편집 가능 키 '{key}' 가 없다")


class ContrastTests(unittest.TestCase):
    """모든 프리셋이 읽히는가. 숫자로 못박아 프리셋 수정 때 바로 걸리게 한다."""

    def test_body_text_is_readable_on_every_background(self):
        for name in PRESETS:
            colors = resolve(name)
            for key in ("text-primary", "text-secondary"):
                ratio, bg = _worst(colors[key], ALL_BACKGROUNDS, colors)
                self.assertGreaterEqual(
                    ratio, MIN_BODY,
                    f"[{name}] --{key} 가 --{bg} 위에서 {ratio:.2f}:1 — 본문은 {MIN_BODY}:1 이상")

    def test_muted_label_is_readable(self):
        """`text-muted` 도 본문과 같은 4.5:1 로 잡는다.

        디자인 메모에는 '라벨 3:1' 로 적혀 있었지만, 실제로 이 토큰이 그리는 것은
        `.qp-label`('대기열') 처럼 **작은 본문 글자**다. 3:1 로 두었더니 버튼 면
        위에서 4.16:1 이 되어 13개 탭 전부에서 걸렸다. 크기로 예외를 주려면
        글자 크기를 아는 자리에서 해야 하는데, 토큰은 그걸 모른다.
        """
        for name in PRESETS:
            colors = resolve(name)
            ratio, bg = _worst(colors["text-muted"], ALL_BACKGROUNDS, colors)
            self.assertGreaterEqual(
                ratio, MIN_LABEL,
                f"[{name}] --text-muted 가 --{bg} 위에서 {ratio:.2f}:1 — 라벨은 {MIN_LABEL}:1 이상")

    def test_visible_edge_is_actually_visible(self):
        """`--edge` 는 '보여야 하는 경계'(포커스링·활성 테두리) 토큰이다.

        `--rule`/`--border` 는 반대로 **일부러 흐린** 구분선이라 여기 넣지 않는다 —
        섞으면 장식용 선을 밝히려다 화면이 격자로 뒤덮인다.
        """
        for name in PRESETS:
            colors = resolve(name)
            ratio, bg = _worst(colors["edge"], SURFACES, colors)
            self.assertGreaterEqual(
                ratio, MIN_EDGE,
                f"[{name}] --edge 가 --{bg} 위에서 {ratio:.2f}:1 — 경계는 {MIN_EDGE}:1 이상")

    def test_state_text_colors_are_readable(self):
        """상태 **글자**는 `-fg` 다. 채움색을 글자로 쓰면 미달한다(#D14141 은 4.33:1)."""
        for name in PRESETS:
            colors = resolve(name)
            for role in STATE_ROLES:
                key = f"state-{role}-fg"
                ratio, bg = _worst(colors[key], SURFACES, colors)
                self.assertGreaterEqual(
                    ratio, MIN_STATE,
                    f"[{name}] --{key} 가 --{bg} 위에서 {ratio:.2f}:1 — "
                    f"상태 글자는 {MIN_STATE}:1 이상")

    def test_white_text_is_readable_on_state_fills(self):
        """`state-x` 는 배지 *배경* 이다. 흰 글자를 얹는 전제로 잡은 값이라 그걸 검사한다."""
        for name in PRESETS:
            colors = resolve(name)
            for role in STATE_ROLES:
                key = f"state-{role}"
                ratio = contrast_ratio("#FFFFFF", colors[key])
                self.assertGreaterEqual(
                    ratio, MIN_STATE,
                    f"[{name}] 흰 글자가 --{key} 배지 위에서 {ratio:.2f}:1 — {MIN_STATE}:1 이상")

    def test_tag_colors_are_readable(self):
        """라이트는 다크를 뒤집은 게 아니다 — 명도를 색상마다 따로 풀어야 여기를 통과한다."""
        for name in PRESETS:
            colors = resolve(name)
            for key in TAG_TEXT_KEYS:
                ratio, bg = _worst(colors[key], SURFACES, colors)
                self.assertGreaterEqual(
                    ratio, MIN_TAG,
                    f"[{name}] --{key} 가 --{bg} 위에서 {ratio:.2f}:1 — 태그는 {MIN_TAG}:1 이상")


class TagHueSeparationTests(unittest.TestCase):
    """태그 색은 '분류를 구분하는 신호'다. 붙어 있으면 신호가 아니다."""

    def test_tag_hues_are_far_enough_apart(self):
        hues = sorted(TAG_HUES.items(), key=lambda kv: kv[1])
        for (name_a, hue_a), (name_b, hue_b) in zip(hues, hues[1:] + hues[:1]):
            gap = _hue_gap(hue_a, hue_b)
            self.assertGreaterEqual(
                gap, MIN_TAG_HUE_GAP,
                f"태그 '{name_a}'({hue_a}°) 와 '{name_b}'({hue_b}°) 가 {gap:.0f}° — "
                f"{MIN_TAG_HUE_GAP}° 이상 떨어져야 칩 색으로 분류가 구분된다")

    def test_tag_hues_stay_away_from_the_accent(self):
        """강조색과 겹치면 그 분류의 칩이 전부 '선택됨' 표시처럼 보인다."""
        for name, preset in PRESETS.items():
            accent_hue = _hue(preset["accent"])
            for tag, hue in TAG_HUES.items():
                gap = _hue_gap(accent_hue, hue)
                self.assertGreaterEqual(
                    gap, MIN_ACCENT_HUE_GAP,
                    f"[{name}] 태그 '{tag}'({hue}°) 가 강조색({accent_hue:.0f}°) 과 "
                    f"{gap:.0f}° — {MIN_ACCENT_HUE_GAP}° 이상 필요")


class DerivedAccentTests(unittest.TestCase):
    """사용자는 색상환의 아무 색이나 고를 수 있다 — 그 전부에서 버튼이 읽혀야 한다."""

    def test_primary_button_text_is_readable_for_any_accent(self):
        """`accent-fill` 위의 `on-accent` 가 항상 4.5:1 인가.

        중간 밝기 색(#D14747 류)은 흰 글자도 검은 글자도 4.4 대라 어느 쪽을 골라도
        모자란다. `readable_fill` 이 면을 미는 게 그래서인데, 미는 폭(50 스텝)이
        모자란 색상이 하나라도 있으면 그 색을 고른 사용자만 버튼을 못 읽는다.
        """
        worst = (99.0, "")
        for hue in range(0, 360, 5):
            for sat in (0.0, 0.3, 0.6, 1.0):
                for light in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9):
                    r, g, b = colorsys.hls_to_rgb(hue / 360, light, sat)
                    accent = "#%02X%02X%02X" % tuple(round(c * 255) for c in (r, g, b))
                    for mode in ("dark", "light"):
                        derived = derive_accent(accent, mode)
                        ratio = contrast_ratio(derived["on-accent"], derived["accent-fill"])
                        if ratio < worst[0]:
                            worst = (ratio, f"{accent}/{mode} → fill={derived['accent-fill']} "
                                            f"on={derived['on-accent']}")
        self.assertGreaterEqual(
            worst[0], 4.5,
            f"주 버튼 글자가 안 읽히는 강조색이 있다: {worst[1]} = {worst[0]:.2f}:1")

    def test_primary_button_stays_readable_on_hover(self):
        """호버한 주 버튼도 4.5:1 인가.

        `accent-fill` 만 검사하면 절반만 보는 것이다. 호버 면을 테마 밝기대로만
        밀던 시절엔 흰 글자를 얹는 면(중간 밝기 강조색)이 호버에서 2.9:1 까지
        떨어졌다 — 누르려고 마우스를 올린 순간 글자가 사라진다.
        """
        worst = (99.0, "")
        for hue in range(0, 360, 5):
            for sat in (0.0, 0.3, 0.6, 1.0):
                for light in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9):
                    r, g, b = colorsys.hls_to_rgb(hue / 360, light, sat)
                    accent = "#%02X%02X%02X" % tuple(round(c * 255) for c in (r, g, b))
                    for mode in ("dark", "light"):
                        derived = derive_accent(accent, mode)
                        ratio = contrast_ratio(
                            derived["on-accent"], derived["accent-fill-hover"])
                        if ratio < worst[0]:
                            worst = (ratio, f"{accent}/{mode} → "
                                            f"hover={derived['accent-fill-hover']} "
                                            f"on={derived['on-accent']}")
        self.assertGreaterEqual(
            worst[0], 4.5,
            f"호버에서 주 버튼 글자가 안 읽히는 강조색이 있다: {worst[1]} = {worst[0]:.2f}:1")

    def test_hover_variants_exist_and_differ(self):
        """호버가 원색과 같으면 버튼이 죽은 것처럼 보인다(마우스에 반응이 없다)."""
        for name, preset in PRESETS.items():
            derived = derive_accent(preset["accent"], preset["mode"])
            self.assertNotEqual(
                derived["accent-hover"], derived["accent"],
                f"[{name}] accent-hover 가 accent 와 같다")
            self.assertNotEqual(
                derived["accent-fill-hover"], derived["accent-fill"],
                f"[{name}] accent-fill-hover 가 accent-fill 과 같다")


class TokenAdoptionTests(unittest.TestCase):
    """토큰을 만들어도 Vue 가 hex 를 그대로 쓰면 테마를 바꿔도 그 자리만 안 바뀐다."""

    @staticmethod
    def _count() -> tuple[int, dict[str, int], int]:
        total, per_file, scanned = 0, {}, 0
        for path in sorted(SRC.rglob("*.vue")):
            scanned += 1
            text = path.read_text(encoding="utf-8")
            found = sum(len(_HEX.findall(block)) for block in _STYLE_BLOCK.findall(text))
            if found:
                per_file[path.relative_to(ROOT).as_posix()] = found
                total += found
        return total, per_file, scanned

    def test_scanner_actually_sees_the_frontend(self):
        # 안전장치 — 경로가 틀리면 0곳으로 '통과'한다
        _total, _per_file, scanned = self._count()
        self.assertGreater(scanned, 30, "Vue 파일을 거의 못 읽었다 — 경로/글롭이 깨졌다")

    def test_hardcoded_hex_stays_under_the_cap(self):
        total, per_file, _scanned = self._count()
        worst = sorted(per_file.items(), key=lambda kv: -kv[1])[:5]
        self.assertLessEqual(
            total, MAX_HARDCODED_HEX,
            f"<style> 안 하드코딩 hex 가 {total}곳 (상한 {MAX_HARDCODED_HEX}). "
            f"많은 순: {worst} — var(--토큰) 으로 바꿔라. "
            "상한은 올리는 게 아니라 내리는 값이다.")


if __name__ == "__main__":
    unittest.main()

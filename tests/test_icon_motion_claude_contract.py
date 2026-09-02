"""Claude 아이콘 모션 프리셋의 정적 계약.

이 프리셋의 원리는 하나다 — **틀은 멈춰 있고 장치만 움직인다.** 눌림(press) 하나만
글리프 전체에 걸리고, 나머지는 전부 `.icon-part-N` 안에서 일어난다.
그 원리는 CSS 를 조금만 고쳐도 조용히 무너지므로(테두리가 통째로 돌아도 화면은
'그럴듯하게' 보인다) 여기서 못 박는다.

`iconMotion.css`(gpt 프리셋)는 건드리지 않는다. 두 프리셋은 루트 속성값으로
갈라져 서로의 선택자가 만나지 않는다.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "frontend" / "src" / "styles" / "iconMotionClaude.css"
CSS = CSS_PATH.read_text(encoding="utf-8")
MOTION_TS = (ROOT / "frontend" / "src" / "icons" / "motion.ts").read_text(encoding="utf-8")
ICONS_TS = (ROOT / "frontend" / "src" / "icons" / "index.ts").read_text(encoding="utf-8")


class ProfileIsolationTests(unittest.TestCase):
    def test_only_the_claude_profile_is_targeted(self):
        """다른 프리셋의 선택자가 섞이면 '없음' 을 골라도 움직인다."""
        self.assertIn(":root[data-icon-animation='claude']", CSS)
        self.assertIsNone(
            re.search(r"data-icon-animation=['\"](?:none|gpt)['\"]", CSS),
            "claude 파일이 다른 프리셋을 건드린다",
        )

    def test_the_gpt_stylesheet_stays_untouched_by_this_preset(self):
        """그쪽 파일에 claude *선택자* 가 생기면 두 프리셋이 겹쳐 켜진다.

        머리말 주석에 'claude' 라는 낱말이 나오는 것은 상관없다 — 규칙만 본다.
        """
        gpt_css = (ROOT / "frontend" / "src" / "styles" / "iconMotion.css").read_text(
            encoding="utf-8"
        )
        self.assertIsNone(re.search(r"data-icon-animation=['\"]claude['\"]", gpt_css))


class MotionPrincipleTests(unittest.TestCase):
    """틀은 멈춘다 — 이 프리셋을 다른 것과 가르는 규칙."""

    #: 글리프 전체(`.icon`)에 걸리는 변형 변수. 눌림만 허용한다.
    _GLYPH_VAR = re.compile(r"--ic-glyph:\s*([^;]+);")

    def test_only_press_transforms_the_whole_glyph(self):
        values = {m.group(1).strip() for m in self._GLYPH_VAR.finditer(CSS)}
        self.assertEqual(
            values,
            {"var(--ic-press)"},
            "글리프 전체 변형은 눌림 하나뿐이어야 한다. 호버·선택은 조각만 움직인다.",
        )

    def test_hover_and_selected_never_rotate_or_scale_the_frame(self):
        """`--ic-open` / `--ic-hold` / `--ic-focus` 는 조각 변수다.

        누군가 이 값을 `.icon` 규칙에 직접 붙이면 아이콘 전체가 돌아간다 —
        15px 스트로크가 흐려지고, 70개가 전부 같은 꿈틀거림이 된다.
        """
        for line in CSS.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("--ic-open", "--ic-hold", "--ic-focus")):
                continue
            self.assertNotIn(
                "--ic-glyph", stripped, f"조각 변수가 글리프에 걸렸다: {stripped}"
            )

    def test_press_wins_over_hover_and_selected(self):
        """상태 규칙 넷은 특정성이 같다 — 순서가 승자를 정한다.

        누름이 호버보다 **앞**에 있으면 마우스로 누르는 동안 호버가 이겨서
        '장치가 쉼 자리로 돌아가 착지한다' 가 한 번도 일어나지 않는다.
        실제로 그렇게 났던 버그라 순서를 못 박는다.
        """
        def first(needle: str) -> int:
            index = CSS.find(needle)
            self.assertNotEqual(index, -1, f"{needle} 규칙이 없다")
            return index

        selected = first("[aria-pressed='true'],")
        focus = first("):focus-visible .icon[data-icon-motion] .icon-part {")
        hover = first("):hover .icon[data-icon-motion] .icon-part {")
        press = first("):active .icon[data-icon-motion] {")
        self.assertLess(selected, focus, "선택은 포커스보다 앞")
        self.assertLess(focus, hover, "포커스는 호버보다 앞")
        self.assertLess(hover, press, "누름은 맨 뒤여야 호버를 이긴다")

    def test_multi_part_rules_do_not_share_one_transform_origin(self):
        """`transform-box: fill-box` 는 조각마다 제 경계상자를 쓴다.

        조각 여러 개를 한 규칙에 묶고 `transform-origin` 을 주면 축이 서로 갈려
        조각들이 분해된다. 휴지통 뚜껑이 그렇게 어긋났었다.
        """
        for chunk in CSS.split("}"):
            if "transform-origin" not in chunk or "view-box" in chunk:
                continue
            parts = re.findall(r"\.icon-part-(\d+)", chunk)
            self.assertLessEqual(
                len(set(parts)), 1,
                f"조각 여러 개가 origin 을 나눠 쓴다 — 축이 갈린다: {chunk.strip()[:90]}",
            )

    def test_translations_are_large_enough_to_see(self):
        """0.3 유닛 아래는 15px 로 그려지면 0.2 픽셀이라 보이지 않는다.

        안 보이는 변형은 뜻은 없고 리페인트 비용만 남는다.
        """
        tiny = [
            value for value in re.findall(r"translate[XY]?\(([-\d.]+)px", CSS)
            if 0 < abs(float(value)) < 0.3
        ]
        self.assertEqual(tiny, [], f"눈에 안 보이는 이동: {tiny}")

    def test_press_scale_is_a_single_shared_value(self):
        """눌림은 '버튼을 눌렀다' 는 촉감이라 아이콘마다 다르면 안 된다."""
        presses = re.findall(r"--ic-press:\s*([^;]+);", CSS)
        self.assertEqual(len(set(presses)), 1, f"눌림 값이 갈렸다: {set(presses)}")


class SafetyGuardTests(unittest.TestCase):
    def test_pointer_and_reduced_motion_guards_are_present(self):
        self.assertIn("@media (hover: hover) and (pointer: fine)", CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)
        self.assertRegex(CSS, r"animation:\s*none !important")
        self.assertRegex(CSS, r"transform:\s*none !important")
        self.assertRegex(CSS, r"transition:\s*opacity 100ms linear !important")

    def test_nothing_touches_layout_or_hit_area(self):
        """크기·여백·위치를 건드리면 클릭 영역이 바뀌고 이웃이 흔들린다."""
        layout = re.compile(
            r"^\s*(?:display|position|inset|top|right|bottom|left|width|height|"
            r"margin|padding|gap|overflow|font-size)\s*:",
            re.MULTILINE,
        )
        found = layout.findall(CSS)
        self.assertEqual(found, [], f"레이아웃 속성이 들어왔다: {found}")

    def test_infinite_animation_only_where_something_is_actually_running(self):
        loops = re.findall(r"\binfinite\b", CSS)
        self.assertEqual(len(loops), 4, "무한 반복이 늘었다 — 지속 상태에만 허용한다")
        for anchor in (
            ":where([aria-busy='true'], .is-loading, .loading, .busy.on)",
            ".ai-loading",
            ":where(.running-badge, .queue-pin.running)",
            ".q-row.active",
        ):
            self.assertIn(anchor, CSS, f"무한 반복의 근거 상태가 없다: {anchor}")

    def test_durations_stay_inside_the_agreed_ranges(self):
        """호버 140~220ms · 눌림 80~160ms · 상태 전환 180~320ms."""
        def ms(name: str) -> list[int]:
            return [int(v) for v in re.findall(rf"--{name}:\s*(\d+)ms", CSS)]

        for value in ms("ic-hover-ms"):
            self.assertTrue(140 <= value <= 220, f"호버 {value}ms")
        for value in ms("ic-press-ms"):
            self.assertTrue(80 <= value <= 160, f"눌림 {value}ms")
        for value in ms("ic-hold-ms"):
            self.assertTrue(180 <= value <= 320, f"상태 전환 {value}ms")


class PartContractTests(unittest.TestCase):
    """CSS 가 기대는 조각 번호가 실제 아이콘에 있는지.

    path 순서가 바뀌거나 개수가 줄면 **예외 없이** 엉뚱한 조각이 움직인다.
    `ICON_PART_MINIMUMS` 가 그 계약이고, 여기서는 CSS 와 대조한다.
    """

    _RULE = re.compile(
        r"\.icon\[data-icon-name='([a-z-]+)'\][^{]*?\{", re.S
    )

    def _minimums(self) -> dict[str, int]:
        block = MOTION_TS.split("ICON_PART_MINIMUMS", 1)[1].split("})", 1)[0]
        out: dict[str, int] = {}
        for name, value in re.findall(r"'?([a-z-]+)'?:\s*(\d+)", block):
            out[name] = int(value)
        return out

    def test_every_referenced_part_index_is_pinned(self):
        minimums = self._minimums()
        missing: list[str] = []
        # 규칙 하나(선택자 + 본문)마다 아이콘 이름과 조각 번호를 함께 읽는다.
        for chunk in re.split(r"\}\s*", CSS):
            names = re.findall(r"\.icon(?:\[data-icon-name='([a-z-]+)'\])", chunk)
            parts = [int(n) for n in re.findall(r"\.icon-part-(\d+)", chunk)]
            if not names or not parts:
                continue
            needed = max(parts)
            # 조각 1 은 아이콘이 존재하면 반드시 있다(빈 아이콘은 motion.test.ts 가 잡는다).
            # 계약이 지켜야 할 것은 '두 번째 이후 조각이 사라지지 않는가' 다.
            if needed < 2:
                continue
            for name in set(names):
                if minimums.get(name, 0) < needed:
                    missing.append(f"{name} 는 조각 {needed} 를 쓰는데 계약은 {minimums.get(name, 0)}")
        self.assertEqual(missing, [], "; ".join(missing))

    def test_pinned_minimums_match_the_real_icon_paths(self):
        """계약이 실제 path 개수를 넘어서면 그 규칙은 영영 안 걸린다."""
        for name, minimum in self._minimums().items():
            key = f"'{name}'" if "-" in name else name
            match = re.search(rf"\n  {re.escape(key)}: \[(.*?)\],\n", ICONS_TS, re.S)
            self.assertIsNotNone(match, f"{name} 아이콘을 찾지 못했다")
            count = len(re.findall(r"'", match.group(1))) // 2
            self.assertGreaterEqual(count, minimum, f"{name}: path {count} < 계약 {minimum}")


if __name__ == "__main__":
    unittest.main()

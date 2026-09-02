"""Claude 아이콘 모션 프리셋의 정적 계약.

이 프리셋의 원리는 하나다 — **틀은 멈춰 있고 장치만 움직인다.** 눌림(press) 하나만
글리프 전체에 걸리고, 나머지는 전부 `.icon-part-N` 안에서 일어난다.
그 원리는 CSS 를 조금만 고쳐도 조용히 무너지므로(테두리가 통째로 돌아도 화면은
'그럴듯하게' 보인다) 여기서 못 박는다.

두 가지를 덧붙인다.
- **전부 움직인다.** 예전엔 '명사는 가만히 둔다' 였는데 화면에서 "아무것도 안
  움직인다" 로 읽혔다. 규칙이 없는 아이콘은 실수다 — 일부러 세워 두려면
  `DELIBERATELY_STILL` 에 이름을 적어 결정을 남긴다.
- **호버 중 반복**이 있다. 내려받기·새로고침·종처럼 한 프레임으로 뜻이 안 서는
  것은 손을 올린 동안 되풀이한다. 반복은 `:hover` 안이나 '돌고 있는 상태' 안에만
  산다 — 쉼 상태에서 돌면 화면이 초조해진다.

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
        """화면에서 1px 아래로 움직이면 안티앨리어싱에 묻혀 사라진다.

        예전엔 이 검사가 `translateY(-.9px)` 같은 **날값**만 봤는데, 그건 화면
        픽셀이 아니라 viewBox 단위다. 앱 아이콘은 17px 로 그려지므로 실제 크기는
        값 × 17/24. 그래서 0.9 는 화면에서 0.64px 였고, 하한(0.3)은 통과하는데
        아무도 못 보는 상태가 됐다 — 사용자가 "움직이는지도 모르겠다" 고 한 그것이다.

        이제는 **진폭 배수를 곱한 실효 크기**를 화면 픽셀로 환산해 본다.
        `calc()` 를 못 읽고 지나가면 검사가 통째로 헛돌므로, 하나도 못 읽으면 실패한다.
        """
        amp = _amp("--ic-amp-move")
        scale = amp * ICON_PX / VIEWBOX
        seen = 0
        # 호버(open)는 움직임만으로 뜻을 전한다 — 1px 아래면 없는 것과 같다.
        # 선택(hold)·포커스(focus)는 버튼의 면과 포커스 링이 같이 말해 주므로
        # 더 옅어도 되지만, 그래도 0.7px 아래면 리페인트 비용만 남는다.
        for prop, floor in (("open", 1.0), ("hold", 0.7), ("focus", 0.7)):
            values = []
            for decl in re.findall(rf"--ic-{prop}:\s*([^;]+);", CSS):
                values += re.findall(r"translate[XY]?\(\s*calc\(\s*(-?[\d.]+)px\s*\*", decl)
            seen += len(values)
            faint = sorted({v for v in values if 0 < abs(float(v)) * scale < floor}, key=float)
            self.assertEqual(
                faint, [],
                f"--ic-{prop} 이 화면에서 {floor}px 도 안 움직인다 "
                f"(진폭 {amp}, {ICON_PX}px 렌더 기준): {faint}",
            )
        self.assertTrue(
            seen, "이동 값을 하나도 읽지 못했다 — 표기가 바뀌었는데 검사가 헛돌고 있다",
        )

    def test_amplitude_is_tunable_from_one_place(self):
        """세기를 바꾸려고 60개 규칙을 고치게 되면 아무도 안 고친다.

        각 규칙은 비율만 갖고, 실제 크기는 루트의 세 숫자가 정한다.
        """
        for name in ("--ic-amp-move", "--ic-amp-turn", "--ic-amp-size"):
            self.assertGreater(_amp(name), 0, f"{name} 을 읽지 못했다")
        # 날것 그대로 남은 값이 있으면 그 아이콘만 진폭 조절에서 빠진다.
        raw = re.findall(r"--ic-(?:open|hold|focus):\s*[^;]*?(?<![\w(])(?:translate[XY]?|rotate)\(\s*-?[\d.]+(?:px|deg)", CSS)
        self.assertEqual(raw, [], f"진폭 변수를 안 거치는 값이 남아 있다: {raw}")

    def test_press_scale_is_a_single_shared_value(self):
        """눌림은 '버튼을 눌렀다' 는 촉감이라 아이콘마다 다르면 안 된다."""
        presses = re.findall(r"--ic-press:\s*([^;]+);", CSS)
        self.assertEqual(len(set(presses)), 1, f"눌림 값이 갈렸다: {set(presses)}")


#: 앱이 아이콘을 그리는 크기와 SVG viewBox 크기. 변형값은 viewBox 단위라
#: 화면 크기 = 값 x ICON_PX / VIEWBOX 다.
ICON_PX = 17
VIEWBOX = 24


def _amp(name: str) -> float:
    """루트에 선언된 진폭 배수."""
    m = re.search(rf"{re.escape(name)}:\s*([\d.]+)\s*;", CSS)
    return float(m.group(1)) if m else 0.0


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

    #: 무한 반복이 서도 되는 곳 — '지금 돌고 있다' 를 말하는 상태들.
    RUNNING_ANCHORS = (
        ":where([aria-busy='true'], .is-loading, .loading, .busy.on)",
        ".ai-loading",
        ":where(.running-badge, .queue-pin.running)",
        ".q-row.active",
    )

    def test_infinite_loops_only_run_while_something_is_going_on(self):
        """무한 반복은 두 곳에만 산다 — 돌고 있는 상태, 그리고 호버.

        호버 반복은 손을 떼면 멈추니 '계속되는 일' 의 예고다. 그 밖(쉼 상태)에서
        돌면 화면이 초조해지고 GPU 가 논다.
        """
        stray = []
        seen = 0
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
            if "infinite" not in body:
                continue
            seen += 1
            if ":hover" in selector or any(a in selector for a in self.RUNNING_ANCHORS):
                continue
            stray.append(" ".join(selector.split())[-90:])
        self.assertTrue(seen, "무한 반복을 하나도 읽지 못했다 — 검사가 헛돌고 있다")
        self.assertEqual(stray, [], f"쉼 상태에서 도는 무한 반복: {stray}")
        for anchor in self.RUNNING_ANCHORS:
            self.assertIn(anchor, CSS, f"무한 반복의 근거 상태가 없다: {anchor}")

    def test_hover_loops_are_guarded_by_pointer_capability(self):
        """터치 화면에는 호버가 없다 — 반복이 눌림에 묻어 두 번 움직인다.

        호버 반복 규칙은 전부 `(hover: hover) and (pointer: fine)` 안에 있어야 한다.
        """
        outside = []
        depth = 0
        in_hover_media = False
        for line in CSS.splitlines():
            if line.startswith("@media (hover: hover)"):
                in_hover_media = True
            if in_hover_media:
                depth += line.count("{") - line.count("}")
                if depth <= 0:
                    in_hover_media = False
                continue
            if ":hover" in line and "infinite" in line:
                outside.append(line.strip()[:90])
        self.assertEqual(outside, [], f"포인터 가드 밖의 호버 반복: {outside}")

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


#: 보고 나서 '이건 세워 두는 게 낫다' 고 결정한 아이콘. 비어 있는 게 기본이다 —
#: 여기 적히지 않았는데 규칙이 없으면 실수다.
DELIBERATELY_STILL: frozenset[str] = frozenset()


class CoverageTests(unittest.TestCase):
    """전부 움직인다 — 명사도. 규칙이 빠진 아이콘은 조용히 멈춰 있다."""

    def _icon_names(self) -> list[str]:
        block = ICONS_TS.split("export const ICONS", 1)[1].split(chr(10) + "}" + chr(10), 1)[0]
        names = re.findall(r"^\s{2}'?([a-z-]+)'?:\s*\[", block, re.M)
        names.append("star")  # ICONS.star 는 블록 밖에서 붙는다
        return sorted(set(names))

    def test_every_icon_has_a_mechanism(self):
        names = self._icon_names()
        self.assertGreaterEqual(len(names), 80, "아이콘 목록을 읽지 못했다")
        silent = [
            n for n in names
            if f"data-icon-name='{n}'" not in CSS and n not in DELIBERATELY_STILL
        ]
        self.assertEqual(
            silent, [],
            "규칙이 없는 아이콘 — 움직여야 한다. 일부러 세워 두려면 DELIBERATELY_STILL 에 적는다: "
            + ", ".join(silent),
        )

    def test_deliberately_still_names_are_real(self):
        names = set(self._icon_names())
        ghosts = sorted(DELIBERATELY_STILL - names)
        self.assertEqual(ghosts, [], f"없는 아이콘이 목록에 있다: {ghosts}")


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

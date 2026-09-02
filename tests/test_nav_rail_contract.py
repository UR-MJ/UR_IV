# -*- coding: utf-8 -*-
"""세로 탭 레일 회귀 테스트 — 레일이 가리키는 곳이 실제로 존재하는지.

레일의 '서랍'은 하위 항목을 누르면 왼쪽 패널의 그 섹션으로 스크롤한다. 대상은
`document.getElementById(id)` 로 찾는데, id 가 없으면 **예외가 안 난다** —
눌러도 화면이 가만히 있을 뿐이다. 아이콘도 같다: `icons/index.ts` 에 없는 이름은
빈 `<svg>` 로 렌더돼 버튼이 통째로 비어 보인다. 둘 다 이 저장소의 단골 실패
방식('조용히 안 맞는 것')이라 정적으로 잡는다.

(`test_editor_tools_contract.py` · `test_bridge_contract.py` 와 같은 방식 — Qt 비의존.)
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

SECTIONS_TS = SRC / "utils" / "navSections.ts"
RAIL = SRC / "components" / "NavRail.vue"
APP = SRC / "App.vue"
PROMPT_PANEL = SRC / "components" / "PromptPanel.vue"
ROUTER = SRC / "router.js"
ICONS = SRC / "icons" / "index.ts"

#: 레일이 라우트가 아니라 PyQt 화면으로 보내는 탭. 라우터에는 없다.
NATIVE_TABS = ("web", "backend")

_SECTION = re.compile(
    r"\{\s*id:\s*'(?P<id>[a-z0-9-]+)'\s*,"
    r"\s*label:\s*'(?P<label>[^']+)'\s*,"
    r"\s*panel:\s*'(?P<panel>left|extend)'"
    r"(?:\s*,\s*badge:\s*'(?P<badge>[a-z-]+)')?\s*\}"
)


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _sections() -> list[dict]:
    return [m.groupdict() for m in _SECTION.finditer(_read(SECTIONS_TS))]


def _declared_routes() -> list[str]:
    """`NAV_SECTIONS` 항목의 route 이름."""
    text = _read(SECTIONS_TS)
    body = text.split("export const NAV_SECTIONS", 1)[1].split("= [", 1)[1].split("\n]", 1)[0]
    return re.findall(r"route:\s*'([a-z0-9]+)'", body)


def _router_names() -> list[str]:
    return re.findall(r"name:\s*'([a-z0-9]+)'", _read(ROUTER))


def _rail_group_names() -> list[str]:
    """레일 묶음(GROUPS)에 적힌 탭 이름 전부, 선언 순서대로."""
    text = _read(RAIL)
    body = text.split("const GROUPS", 1)[1].split("= [", 1)[1].split("\n]", 1)[0]
    names: list[str] = []
    for chunk in re.findall(r"names:\s*\[([^\]]*)\]", body):
        names.extend(re.findall(r"'([a-z0-9]+)'", chunk))
    return names


class NavSectionRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sections = _sections()
        cls.app = _read(APP)
        cls.panel = _read(PROMPT_PANEL)

    def test_registry_is_readable(self):
        self.assertGreaterEqual(
            len(self.sections), 4,
            "navSections.ts 에서 섹션을 하나도 읽지 못했다 — 선언 형태가 바뀌었는지 확인",
        )

    def test_every_section_id_exists_exactly_once_in_the_markup(self):
        """id 가 없으면 하위 항목을 눌러도 아무 일이 없다. 둘이면 엉뚱한 데로 간다."""
        markup = self.app + "\n" + self.panel
        for section in self.sections:
            hits = markup.count(f'id="{section["id"]}"')
            self.assertEqual(
                hits, 1,
                f"'{section['id']}' ({section['label']}) 가 마크업에 {hits}번 있다 — "
                "1번이어야 한다. 없으면 스크롤이 조용히 실패하고, "
                "둘이면 getElementById 가 앞의 것을 집는다.",
            )

    def test_left_sections_live_in_the_left_panel(self):
        for section in self.sections:
            if section["panel"] != "left":
                continue
            self.assertIn(
                f'id="{section["id"]}"', self.panel,
                f"'{section['id']}' 를 panel:'left' 로 적었는데 PromptPanel 에 없다",
            )

    def test_extend_sections_live_in_the_advanced_overlay(self):
        """'고급 설정' 은 v-if 라 닫히면 DOM 에 없다 — 그래서 panel 구분이 필요하다."""
        overlay = self.app.split('class="extend-overlay"', 1)
        self.assertEqual(len(overlay), 2, "App.vue 에서 고급 설정 오버레이를 찾지 못했다")
        body = overlay[1].split("</aside>", 1)[0]
        for section in self.sections:
            if section["panel"] != "extend":
                continue
            self.assertIn(
                f'id="{section["id"]}"', body,
                f"'{section['id']}' 를 panel:'extend' 로 적었는데 오버레이 안에 없다 — "
                "레일이 오버레이를 열어도 대상이 거기 없으면 스크롤이 죽는다",
            )

    def test_declared_routes_are_real_routes(self):
        known = set(_router_names())
        for name in _declared_routes():
            self.assertIn(name, known, f"'{name}' 은 router.js 에 없는 탭이다")

    def test_app_opens_the_overlay_before_scrolling(self):
        """오버레이를 안 열고 스크롤하면 요소가 없어 조용히 아무 일도 안 일어난다."""
        handler = re.search(r"async function goToNavSection\(.*?\n\}", self.app, re.S)
        self.assertIsNotNone(handler, "App.vue 에 goToNavSection 이 없다")
        body = handler.group(0)
        self.assertIn("showExtendPanel.value = true", body, "오버레이를 열지 않는다")
        self.assertIn("nextTick", body, "열자마자 스크롤하면 아직 DOM 에 없다")
        self.assertIn("scrollIntoView", body)
        self.assertIn("HTMLDetailsElement", body, "접힌 <details> 를 펴지 않는다")


class NavRailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rail = _read(RAIL)
        cls.app = _read(APP)
        cls.icons = _read(ICONS)

    def test_the_horizontal_tab_bar_is_gone(self):
        """가로 바는 '네비 3안' 시안이었고 본안이 아니다. 남아 있으면 둘이 공존한다."""
        self.assertFalse(
            (SRC / "components" / "TabBar.vue").exists(),
            "components/TabBar.vue 가 아직 있다",
        )
        for path in SRC.rglob("*.vue"):
            self.assertNotIn(
                "TabBar.vue", _read(path), f"{path.name} 이 아직 TabBar 를 import 한다",
            )
        self.assertNotIn("app-header", self.app, "60px 헤더가 남아 있다 — 무대 세로를 그만큼 잃는다")

    def test_rail_is_wired_in_app(self):
        self.assertIn("<NavRail", self.app, "App.vue 가 레일을 쓰지 않는다")
        # 선언한 emit 이 부모에 안 걸리면 눌러도 아무 일이 없다
        # (test_component_emit_contract.py 와 같은 이유).
        self.assertRegex(self.app, r"<NavRail[^>]*@tab-changed=")
        self.assertRegex(self.app, r"<NavRail[^>]*@go-section=")
        self.assertRegex(
            self.app,
            r"\.app-container\s*\{[^}]*flex-direction:\s*row",
            "레일과 작업 공간이 나란히 서려면 app-container 가 가로 배치여야 한다",
        )

    def test_every_router_tab_is_placed_in_a_group(self):
        """묶음에서 빠진 탭은 화면에서 그냥 사라진다 — 예외도 경고도 없다."""
        placed = _rail_group_names()
        for name in _router_names():
            self.assertIn(name, placed, f"'{name}' 탭이 레일 묶음 어디에도 없다")
        for name in NATIVE_TABS:
            self.assertIn(name, placed, f"네이티브 탭 '{name}' 이 레일에 없다")

    def test_every_tab_icon_exists_in_the_registry(self):
        """없는 아이콘 이름은 빈 <svg> 로 렌더된다 — 접힌 레일이 통째로 빈칸이 된다."""
        body = self.rail.split("const ICON_BY_TAB", 1)[1].split("= {", 1)[1].split("\n}", 1)[0]
        pairs = re.findall(r"([a-z0-9]+):\s*'([a-z-]+)'", body)
        self.assertGreaterEqual(len(pairs), 15, "아이콘 표를 읽지 못했다")
        for tab, icon in pairs:
            key = f"'{icon}':" if "-" in icon else f"{icon}:"
            self.assertIn(key, self.icons, f"'{tab}' 의 아이콘 '{icon}' 이 icons/index.ts 에 없다")

    def test_rail_reads_sections_from_the_registry(self):
        """DOM 을 훑어 추측하면 패널을 손볼 때마다 목록이 조용히 달라진다."""
        self.assertIn("sectionsFor", self.rail, "레일이 navSections 레지스트리를 안 쓴다")
        self.assertIn("currentTab === tab.name", self.rail, "활성 탭만 펼치는 조건이 없다")

    def test_collapsed_rail_keeps_names_reachable(self):
        """52px 로 접히면 이름이 사라진다 — 이름표가 없으면 아이콘만 남아 못 읽는다."""
        self.assertRegex(self.rail, r"\.nav-rail\s*\{[^}]*width:\s*196px")
        self.assertRegex(self.rail, r"\.nav-rail\.collapsed\s*\{[^}]*width:\s*52px")
        # 레일은 세로 스크롤을 하므로 툴팁을 안에 두면 잘린다 — EditorToolbar 와 같은 이유.
        self.assertIn("<Teleport to=\"body\">", self.rail)
        self.assertIn("navRailCollapsed", self.rail, "접힌 상태가 저장되지 않는다")

    def test_token_badge_rule_matches_the_prompt_panel(self):
        """레일 숫자와 카드 숫자가 다르면 어느 쪽을 믿어야 할지 알 수 없다.

        `approxTokens` 는 아직 두 곳에 있다(PromptPanel 쪽이 로컬 함수라 못 가져온다).
        규칙이 갈라지는 순간을 여기서 잡는다.
        """
        rule = "total + Math.max(0, chunks.length - 1)"
        self.assertIn(rule, self.rail)
        self.assertIn(rule, _read(PROMPT_PANEL))

    def test_rail_colors_come_from_tokens(self):
        """하드코딩 hex 는 라이트 모드에서 깨진다 (tests/test_theme_contract.py 참조)."""
        styles = re.findall(r"<style\b[^>]*>(.*?)</style>", self.rail, re.S)
        self.assertTrue(styles, "NavRail 에 <style> 이 없다")
        hexes = re.findall(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b", "".join(styles))
        self.assertEqual(hexes, [], f"레일 CSS 에 하드코딩 색이 있다: {hexes}")
        # 활성 행은 두 모드 모두에서 '한 단 올라온 면'이어야 한다 — rgba(255,255,255,.08)
        # 은 라이트에서 안 보인다.
        self.assertRegex(self.rail, r"\.nav\.on\s*\{[^}]*background:\s*var\(--bg-button\)")
        self.assertRegex(self.rail, r"\.sub\.open\s*\{[^}]*background:\s*var\(--accent-dim\)")


if __name__ == "__main__":
    unittest.main()

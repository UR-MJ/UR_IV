"""세로 툴바 도구 레지스트리 회귀 테스트.

`frontend/src/utils/editorTools.ts` 의 도구 id 는 `EditorCanvas` 가 문자열로 분기하는
값과 정확히 같아야 한다. 어긋나면 예외 없이 **아무 일도 일어나지 않는다** —
도구를 눌렀는데 커서만 바뀌고 캔버스는 반응이 없다. 이 프로젝트의 단골 실패 방식이라
정적으로 잡는다.
"""

from __future__ import annotations

import pathlib
import re
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"
REGISTRY = SRC / "utils" / "editorTools.ts"
CANVAS = SRC / "components" / "editor" / "EditorCanvas.vue"
DRAW_TOOLS = SRC / "utils" / "drawTools.ts"
EDITOR_VIEW = SRC / "views" / "EditorView.vue"

_TOOL = re.compile(
    r"\{\s*id:\s*'(?P<id>[a-z_]+)'.*?"
    r"label:\s*'(?P<label>[^']+)'.*?"
    r"icon:\s*'(?P<icon>[a-z-]+)'.*?"
    r"shortcut:\s*'(?P<key>[A-Z])'.*?"
    r"kind:\s*'(?P<kind>[a-z]+)'",
    re.S,
)


def _tools() -> list[dict]:
    """배열 리터럴 본문만 잘라 파싱한다.

    선언이 `EDITOR_TOOLS: EditorTool[] = [` 라서 첫 `]` 로 자르면 타입의 대괄호에
    걸려 본문이 빈 문자열이 된다 — 줄 맨 앞의 `]` 를 끝으로 본다.
    """
    text = REGISTRY.read_text(encoding="utf-8")
    after = text.split("export const EDITOR_TOOLS", 1)[1]
    body = after.split("= [", 1)[1].split("\n]", 1)[0]
    return [m.groupdict() for m in _TOOL.finditer(body)]


class ToolRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = _tools()
        cls.canvas = CANVAS.read_text(encoding="utf-8")
        cls.draw = DRAW_TOOLS.read_text(encoding="utf-8")
        cls.icons = (SRC / "icons" / "index.ts").read_text(encoding="utf-8")

    def test_registry_is_not_empty(self):
        self.assertGreaterEqual(len(self.tools), 15, "도구 레지스트리를 읽지 못했다")

    def test_every_tool_id_is_understood_by_the_canvas(self):
        """마스크 도구는 EditorCanvas 가 직접 분기하고, 그리기 도구는 DRAW_TOOLS 에 있다."""
        for tool in self.tools:
            tool_id = tool["id"]
            if tool["kind"] == "draw":
                self.assertIn(
                    f"'{tool_id}'", self.draw,
                    f"'{tool_id}' 가 utils/drawTools.ts 의 DRAW_TOOLS 에 없다 — "
                    "isDrawTool 이 false 라 포인터가 마스크 처리로 새어 나간다.",
                )
            else:
                self.assertRegex(
                    self.canvas,
                    r"props\.tool\s*===\s*'" + re.escape(tool_id) + r"'",
                    f"EditorCanvas 가 '{tool_id}' 를 분기하지 않는다 — 골라도 아무 일이 없다.",
                )

    def test_shortcuts_are_unique(self):
        keys = [t["key"] for t in self.tools]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        self.assertEqual(dupes, [], f"단축키가 겹친다: {dupes}")

    def test_every_icon_exists_in_the_registry(self):
        """없는 아이콘 이름은 빈 <svg> 로 렌더된다 — 버튼이 통째로 비어 보인다."""
        for tool in self.tools:
            name = tool["icon"]
            key = f"'{name}':" if "-" in name else f"{name}:"
            self.assertIn(key, self.icons, f"아이콘 '{name}' 이 icons/index.ts 에 없다")

    def test_toolbar_is_wired_in_the_editor(self):
        text = EDITOR_VIEW.read_text(encoding="utf-8")
        self.assertIn("<EditorToolbar", text, "EditorView 가 툴바를 쓰지 않는다")
        self.assertRegex(
            text, r"<EditorToolbar[^>]*:model-value=", "툴바에 현재 도구가 전달되지 않는다"
        )
        self.assertRegex(
            text, r"<EditorToolbar[^>]*@select=", "툴바의 선택이 아무데도 연결되지 않았다"
        )

    def test_draw_tool_selection_syncs_canvas_and_panel(self):
        """캔버스가 보는 값과 패널 하이라이트를 함께 바꿔야 둘이 같은 도구를 가리킨다."""
        text = EDITOR_VIEW.read_text(encoding="utf-8")
        select = re.search(r"function selectTool\(.*?\n\}", text, re.S)
        self.assertIsNotNone(select, "selectTool 을 찾지 못했다")
        body = select.group(0)
        self.assertIn("currentTool.value = id", body)
        self.assertIn("drawParams.value", body, "그리기 도구가 캔버스 파라미터에 반영되지 않는다")
        self.assertIn("setTool", body, "패널 하이라이트가 툴바를 따라가지 않는다")


if __name__ == "__main__":
    unittest.main()

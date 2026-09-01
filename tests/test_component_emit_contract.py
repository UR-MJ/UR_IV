"""컴포넌트 emit 배선 회귀 테스트.

PyQt → Vue 이전 과정에서 패널이 선언한 emit 을 부모가 바인딩하지 않아
'보이는데 눌러도 아무 일이 없는' 컨트롤이 다수 생겼다(에디터 탭 표면적의 30%).
tests/test_bridge_contract.py 는 requestAction/onBackendEvent **이름**만 검사하므로
이 계층은 사각지대였다. 여기서 그 구멍을 막는다.

규칙: 컴포넌트가 defineEmits 로 선언한 이벤트는, 그 컴포넌트를 쓰는 부모 템플릿에서
@이벤트 로 바인딩되어야 한다. 아직 구현이 안 된 것은 PENDING 에 사유와 함께
명시적으로 적는다 — 조용히 빠지는 것과 알고 미루는 것을 구분하기 위해서다.
"""

from __future__ import annotations

import pathlib
import re
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"

# 아직 바인딩하지 않은 emit — 반드시 사유를 남길 것.
# 구현되면 여기서 지운다. 여기 없는 미바인딩이 생기면 테스트가 실패한다.
PENDING: dict[tuple[str, str], str] = {
    ("EditorCanvas", "mask-changed"): "선언만 있고 emit 하는 곳이 없는 죽은 선언 — 정리 대상",
    ("MosaicPanel", "effect-changed"): "같은 페이로드가 effect-apply 에 포함돼 전달됨 (중복)",
}


def _kebab(name: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name).lower()


def _open_tags(text: str, component: str) -> list[str]:
    """<Component ...> 여는 태그의 속성 본문을 반환한다.

    바인딩 값 안의 화살표 함수(``@flip="op => doOp(op)"``)에 '>' 가 들어 있어
    단순 정규식은 태그를 중간에서 잘라먹는다. 따옴표 상태를 추적해야 한다.
    """
    bodies: list[str] = []
    pattern = re.compile(r"<" + re.escape(component) + r"(?=[\s/>])")
    index = 0
    while True:
        match = pattern.search(text, index)
        if not match:
            return bodies
        cursor, quote = match.end(), None
        while cursor < len(text):
            char = text[cursor]
            if quote:
                if char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == ">":
                break
            cursor += 1
        bodies.append(text[match.end():cursor])
        index = cursor + 1


def _declared_emits(text: str) -> set[str]:
    block = re.search(r"defineEmits<\{(.*?)\}>\(\)", text, re.S)
    if not block:
        return set()
    names = re.findall(r"^\s*'?([A-Za-z][\w-]*)'?\s*:", block.group(1), re.M)
    return {_kebab(n) for n in names}


class ComponentEmitContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {p: p.read_text(encoding="utf-8") for p in SRC.rglob("*.vue")}

    def _unbound(self) -> dict[tuple[str, str], list[str]]:
        declared = {}
        for path, text in self.sources.items():
            emits = _declared_emits(text)
            if emits:
                declared[path.stem] = (path, emits)

        unbound: dict[tuple[str, str], list[str]] = {}
        for component, (own_path, emits) in declared.items():
            bound: set[str] = set()
            users: list[str] = []
            for path, text in self.sources.items():
                if path == own_path:
                    continue
                for body in _open_tags(text, component):
                    users.append(path.name)
                    bound.update(_kebab(e) for e in re.findall(r"@([A-Za-z][\w-]*)", body))
                    bound.update(_kebab(e) for e in re.findall(r"v-on:([A-Za-z][\w-]*)", body))
            if not users:
                continue  # 아직 아무도 쓰지 않는 컴포넌트는 대상 밖
            for event in sorted(emits - bound):
                unbound[(component, event)] = sorted(set(users))
        return unbound

    def test_declared_emits_are_bound_by_parents(self):
        unbound = self._unbound()
        surprises = {k: v for k, v in unbound.items() if k not in PENDING}
        self.assertEqual(
            surprises,
            {},
            "부모가 바인딩하지 않는 emit 이 새로 생겼다. 배선하거나, 미룰 사유를 PENDING 에 적어라.",
        )

    def test_pending_list_has_no_stale_entries(self):
        """구현이 끝났는데 PENDING 에 남아 있으면 알려준다 — 목록이 낡지 않게."""
        unbound = self._unbound()
        stale = sorted(k for k in PENDING if k not in unbound)
        self.assertEqual(
            stale,
            [],
            "이미 배선된 항목이 PENDING 에 남아 있다. 목록에서 지워라.",
        )

    def test_draw_panel_tool_payload_is_not_assigned_raw(self):
        """DrawPanel 은 객체를 emit 한다. 그걸 currentTool 에 그대로 넣으면
        EditorCanvas 의 문자열 비교가 전부 어긋나 그리기 탭은 물론 선택 도구까지 죽는다.
        (실제로 있었던 버그 — EditorView.vue 의 `currentTool = $event`)
        """
        editor = SRC / "views" / "EditorView.vue"
        text = editor.read_text(encoding="utf-8")
        for body in _open_tags(text, "DrawPanel"):
            self.assertNotRegex(
                body,
                r'@tool-changed\s*=\s*"currentTool\s*=\s*\$event"',
                "DrawPanel 의 tool-changed 페이로드는 객체다 — 핸들러에서 .tool 을 꺼내 쓸 것.",
            )

    def test_histogram_receives_live_image_source(self):
        """히스토그램·커브는 부모가 내려주는 값으로 산다.

        배선이 끊겨도 예외가 나지 않는다 — 그냥 빈 상자가 된다. 이 프로젝트에서
        제일 자주 났던 실패 방식이라(보이는데 아무 일도 안 함) 정적으로 잡는다.
        `active` 는 숨은 탭에서 계산을 멈추는 스위치라 같이 확인한다.
        """
        editor = (SRC / "views" / "EditorView.vue").read_text(encoding="utf-8")
        panel_tags = _open_tags(editor, "AdvancedColorPanel")
        self.assertTrue(panel_tags, "EditorView 가 AdvancedColorPanel 을 쓰지 않는다")
        for body in panel_tags:
            self.assertRegex(
                body, r":src\s*=", "AdvancedColorPanel 에 :src 가 없으면 히스토그램은 빈 상자다."
            )
            self.assertRegex(
                body, r":active\s*=", "AdvancedColorPanel 에 :active 가 없으면 숨은 탭에서도 계산한다."
            )

        panel = (SRC / "components" / "editor" / "AdvancedColorPanel.vue").read_text(
            encoding="utf-8"
        )
        expected = {
            # 히스토그램은 계산하지 않는다 — 패널이 useImageHistogram 결과를 나눠 준다
            "HistogramChart": (":hists", ":has-data", ":black-point", ":white-point"),
            # 커브 편집기는 같은 분포를 배경으로 깔고, 편집 결과를 change 로 돌려준다
            "CurvesEditor": (":curves", ":hists", ":has-data"),
        }
        for component, attrs in expected.items():
            tags = _open_tags(panel, component)
            self.assertTrue(tags, f"AdvancedColorPanel 이 {component} 를 쓰지 않는다")
            for body in tags:
                for attr in attrs:
                    self.assertIn(attr, body, f"{component} 에 {attr} 가 전달되지 않는다.")

    def test_draw_layer_is_wired_to_the_canvas(self):
        """그리기 파라미터가 캔버스까지 내려가야 도구 10개가 산다.

        빠져도 예외는 없다 — 기본값(검은 펜 3px)으로 조용히 그려져서, 색·크기·
        투명도 슬라이더가 전부 무반응인 것처럼 보인다.
        """
        editor = (SRC / "views" / "EditorView.vue").read_text(encoding="utf-8")
        canvas_tags = _open_tags(editor, "EditorCanvas")
        self.assertTrue(canvas_tags, "EditorView 가 EditorCanvas 를 쓰지 않는다")
        for body in canvas_tags:
            for attr in (":draw-params", ":layer-opacity"):
                self.assertIn(attr, body, f"EditorCanvas 에 {attr} 가 전달되지 않는다.")

    def test_draw_layer_is_cleared_when_the_image_changes(self):
        """회전·자르기·병합 뒤에도 레이어가 남으면 안 맞는 그림이 얹힌 채로 보인다."""
        editor = (SRC / "views" / "EditorView.vue").read_text(encoding="utf-8")
        self.assertRegex(
            editor,
            r"watch\(imagePath,[^\n]*clearDrawLayer",
            "확정 이미지가 바뀔 때 드로잉 레이어를 비우지 않는다.",
        )

    def test_curve_payload_reaches_the_backend(self):
        """커브는 adv_color 페이로드에 실려야 백엔드가 적용한다.

        패널이 curves 를 담아도 EditorView 의 중립 판정이 커브를 안 보면,
        슬라이더가 전부 기본값일 때 커브만 만진 프리뷰가 통째로 걷힌다.
        """
        panel = (SRC / "components" / "editor" / "AdvancedColorPanel.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("curves: curves.value", panel, "adv_color 페이로드에 curves 가 없다.")

        editor = (SRC / "views" / "EditorView.vue").read_text(encoding="utf-8")
        preview = re.search(r"function previewAdvAdj\(.*?\n\}", editor, re.S)
        self.assertIsNotNone(preview, "previewAdvAdj 를 찾지 못했다")
        self.assertIn(
            "isIdentity(adj.curves)",
            preview.group(0),
            "중립 판정이 커브를 보지 않는다 — 커브만 만지면 프리뷰가 안 나간다.",
        )


if __name__ == "__main__":
    unittest.main()

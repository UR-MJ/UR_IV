"""화면 문구 표기 규칙 회귀 테스트.

**대문자 영문은 '이름'에만, 한글은 '일'에.**

전각 대문자 영문은 드물어야 신호가 된다. 전부 대문자로 쓰면 아무것도 강조되지 않고,
읽는 속도만 느려지며 '옛날 UI' 인상을 만든다. 그래서 남기는 자리를 좁게 못 박는다:

  ① 화면 이름 — `h1`/`h2` 자리, 화면당 하나 (`TAG EXPLORER`, `MASK EDITOR` …)
  ② 주 실행 버튼 — 화면에서 '그걸 하는' 버튼 하나 (`GENERATE IMAGE`)
  ③ 약어·규격 — 번역하면 오히려 못 알아보는 것 (`CFG`, `VAE`, `T2I`, `SAM3`)

제품명은 **원래 표기**로 쓴다. `ADETAILER` 가 아니라 `ADetailer` 다 — 전부 대문자로
미는 스타일이 제품명의 실제 철자까지 뭉갰었다.

이 규칙은 CSS 로도 깨질 수 있다: `text-transform: uppercase` 가 남아 있으면 마크업을
한국어로 고쳐도 화면은 그대로거나, `ADetailer` 가 다시 `ADETAILER` 로 보인다.
실제로 갤러리의 폴더 경로가 이 규칙에 걸려 **파일 경로가 대문자로 표시되고 있었다**.
"""

from __future__ import annotations

import pathlib
import re
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"

VUE = sorted(SRC.rglob("*.vue"))
CSS = sorted(SRC.rglob("*.css"))

#: 전각 대문자로 남겨도 되는 것 — 여기 없는 대문자 문자열은 실패시킨다.
ALLOWED_CAPS = {
    # ① 화면 이름
    "AI STUDIO PRO", "CREATOR STUDIO", "MASK EDITOR", "TAG EXPLORER", "EVENT GENERATOR",
    # ② 주 실행 버튼
    "GENERATE IMAGE", "GENERATE T2V", "GENERATE I2V", "GENERATE V2V",
    # ③ 약어 · 규격 · 코드
    # VRAM 은 하단 계기 스트립(StatusStrip)의 칸 이름. '비디오 메모리'로 풀면
    # 오히려 못 알아본다 — CFG·VAE 와 같은 ③ 약어다.
    "CFG", "VAE", "T2I", "I2I", "T2V", "I2V", "V2V", "NSFW", "SAM3", "API URL", "VRAM",
    "GEN", "SENS", "QUES", "EXPL", "AND", "OR",
    "DCW / RDC / DAVE / CNS",
}

#: 원래 철자가 전각 대문자가 아닌 제품명 — 대문자로 쓰면 틀린 표기다.
PRODUCT_SPELLING = {
    "ADETAILER": "ADetailer",
    "CONTROLNET": "ControlNet",
    "COMFYUI": "ComfyUI",
    "HIRES.FIX": "Hires.fix",
    "MINIMAX": "MiniMax",
}

_ROOT_TEMPLATE = re.compile(r"<template>(.*?)\n</template>", re.S)
_CAPS_TEXT = re.compile(r">\s*([A-Z][A-Z0-9 &./()+_-]{2,}?)\s*<")


def _template(path: pathlib.Path) -> str:
    m = _ROOT_TEMPLATE.search(path.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


class CapsUsageTests(unittest.TestCase):
    def test_all_caps_text_is_limited_to_names_and_terms(self):
        found: dict[str, set[str]] = {}
        for path in VUE:
            for raw in _CAPS_TEXT.findall(_template(path)):
                word = raw.strip()
                if len(word) < 3 or word.isdigit() or word in ALLOWED_CAPS:
                    continue
                found.setdefault(word, set()).add(path.stem)
        self.assertEqual(
            found, {},
            "전각 대문자 영문은 화면 이름 · 주 실행 버튼 · 약어에만 쓴다. "
            f"규칙 밖: { {k: sorted(v) for k, v in found.items()} }",
        )

    def test_product_names_keep_their_real_spelling(self):
        for path in VUE:
            body = _template(path)
            for wrong, right in PRODUCT_SPELLING.items():
                self.assertNotRegex(
                    body, r"(?<![A-Z])" + re.escape(wrong) + r"(?![A-Z])",
                    f"{path.name}: '{wrong}' 은 원래 '{right}' 로 쓴다",
                )


class TypographyTests(unittest.TestCase):
    def test_no_css_uppercasing(self):
        """CSS 가 대문자로 밀면 마크업을 고쳐도 화면은 안 바뀐다.

        폴더 경로에 걸려 있어 **실제 파일 경로가 대문자로 표시**되던 자리가 있었다.
        """
        offenders = [
            p.relative_to(SRC).as_posix()
            for p in VUE + CSS
            if re.search(r"text-transform:\s*uppercase", p.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [], f"text-transform: uppercase 가 남아 있다: {offenders}")

    def test_font_weight_uses_the_tokens(self):
        """굵기는 400/500/600 세 단계뿐이다.

        11px 한글에 800~900 은 획이 붙어 뭉갠다 — '구식' 의 무거움이 여기서 나왔다.
        위계는 굵기가 아니라 크기와 색이 진다.
        """
        offenders: dict[str, list[str]] = {}
        for path in VUE + CSS:
            hits = re.findall(r"font-weight:\s*(\d{3}|bold)\b", path.read_text(encoding="utf-8"))
            if hits:
                offenders[path.relative_to(SRC).as_posix()] = sorted(set(hits))
        self.assertEqual(
            offenders, {},
            f"font-weight 는 var(--fw-normal|medium|bold) 를 쓴다. 숫자로 박힌 곳: {offenders}",
        )

    def test_letter_spacing_only_on_caps_names(self):
        """자간은 대문자 영문에만.

        한글은 글자 자체에 여백이 있어 자간을 벌리면 흐트러진다. 대문자 영문은 반대로
        글자 사이가 좁아 보여 트래킹이 필요하다 — 그래서 화면 이름에만 남긴다.
        """
        offenders: dict[str, list[str]] = {}
        for path in VUE + CSS:
            hits = re.findall(r"letter-spacing:\s*([0-9.]+px)", path.read_text(encoding="utf-8"))
            if hits:
                offenders[path.relative_to(SRC).as_posix()] = sorted(set(hits))
        self.assertEqual(
            offenders, {},
            f"자간은 px 대신 대문자 이름 자리에만 em 으로 준다. px 로 박힌 곳: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()

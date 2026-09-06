"""Static safety contract for the global semantic icon motion stylesheet."""

from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICON_MOTION_CSS = (
    PROJECT_ROOT / "frontend" / "src" / "styles" / "iconMotion.css"
).read_text(encoding="utf-8")


def _semantic_hover_profiles() -> dict[str, str]:
    profiles: dict[str, str] = {}
    for kind, body in re.findall(
        r"data-icon-motion='([a-z-]+)'\]\s*\{(.*?)\}",
        ICON_MOTION_CSS,
        re.DOTALL,
    ):
        match = re.search(r"--icon-hover-transform:\s*([^;]+)", body)
        if match:
            profiles[kind] = match.group(1).strip()
    return profiles


def _gesture_is_perceptible(transform: str, *, min_translation: float = 1.25) -> bool:
    translations = [
        abs(float(value))
        for value in re.findall(r"(?<![a-z])(-?\d*\.?\d+)px", transform)
    ]
    rotations = [
        abs(float(value))
        for value in re.findall(r"rotate\((-?\d*\.?\d+)deg\)", transform)
    ]
    scales = [
        abs(float(value) - 1.0)
        for value in re.findall(r"scale(?:X|Y)?\((\d*\.?\d+)\)", transform)
    ]
    return bool(
        (translations and max(translations) >= min_translation)
        or (rotations and max(rotations) >= 5.0)
        or (scales and max(scales) >= 0.06)
    )


class IconMotionContractTests(unittest.TestCase):
    def test_only_the_implemented_gpt_profile_activates_motion(self):
        self.assertIn(":root[data-icon-animation='gpt']", ICON_MOTION_CSS)
        self.assertIsNone(
            re.search(r"data-icon-animation=['\"](?:none|claude)['\"]", ICON_MOTION_CSS)
        )

    def test_common_rule_does_not_override_semantic_profiles_by_specificity(self):
        first_selector = next(
            line.strip()
            for line in ICON_MOTION_CSS.splitlines()
            if line.startswith(":root[data-icon-animation='gpt']")
        )
        self.assertEqual(
            first_selector,
            ":root[data-icon-animation='gpt'] .icon[data-icon-motion] {",
        )

    def test_pointer_and_reduced_motion_guards_are_present(self):
        self.assertIn("@media (hover: hover) and (pointer: fine)", ICON_MOTION_CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", ICON_MOTION_CSS)
        self.assertRegex(ICON_MOTION_CSS, r"animation:\s*none !important")
        self.assertRegex(ICON_MOTION_CSS, r"transform:\s*none !important")
        self.assertRegex(
            ICON_MOTION_CSS, r"transition:\s*opacity 100ms linear !important"
        )

    def test_all_existing_clickable_icon_hosts_receive_motion(self):
        """Icon을 직접 품은 비버튼 클릭 호스트도 공통 상태 연결에서 빠지지 않는다."""
        for class_name in (
            "half-moon",
            "cpm-item",
            "q-row",
            "file-item",
            "folder-info",
            "gallery-card",
            "exif-close",
            "exif-preview",
            "drop-empty",
            "compare-container",
            "image-area",
        ):
            self.assertIn(f".{class_name}", ICON_MOTION_CSS)

    def test_interaction_motion_stays_inside_release_quality_limits(self):
        interaction_css = ICON_MOTION_CSS.split("@keyframes", 1)[0]
        rotations = [
            abs(float(value))
            for value in re.findall(r"rotate\((-?\d+(?:\.\d+)?)deg\)", interaction_css)
        ]
        scales = [
            float(value)
            for value in re.findall(r"scale(?:X|Y)?\((\d*\.\d+|\d+)\)", interaction_css)
        ]
        hover_durations = [
            int(value)
            for value in re.findall(r"--icon-hover-duration:\s*(\d+)ms", ICON_MOTION_CSS)
        ]
        press_durations = [
            int(value)
            for value in re.findall(r"--icon-press-duration:\s*(\d+)ms", ICON_MOTION_CSS)
        ]

        self.assertTrue(rotations)
        self.assertLessEqual(max(rotations), 18)
        self.assertTrue(scales)
        self.assertGreaterEqual(min(scales), 0.90)
        self.assertLessEqual(max(scales), 1.12)
        self.assertLessEqual(max(hover_durations), 190)
        self.assertLessEqual(max(press_durations), 100)

    def test_every_semantic_profile_has_a_perceptible_hover_gesture(self):
        """Enabled motion must be visible before the shared press feedback.

        When a semantic profile has no hover gesture, the only remaining
        transform is the common press scale.  A screen full of those icons
        therefore feels both motionless and mechanically identical.
        """

        profiles = _semantic_hover_profiles()
        active = {kind: value for kind, value in profiles.items() if kind != "quiet"}
        missing = sorted(kind for kind, value in active.items() if value == "none")
        faint = sorted(
            kind
            for kind, value in active.items()
            if value != "none" and not _gesture_is_perceptible(value)
        )
        self.assertEqual(missing, [], f"hover 동작이 없는 의미군: {missing}")
        self.assertEqual(faint, [], f"눈에 잘 안 보이는 의미군: {faint}")

    def test_semantic_profiles_do_not_collapse_into_one_motion(self):
        profiles = _semantic_hover_profiles()
        active = {
            kind: value
            for kind, value in profiles.items()
            if kind != "quiet" and value != "none"
        }
        for left, right in (
            ("travel-up", "travel-down"),
            ("travel-left", "travel-right"),
            ("cycle-cw", "cycle-ccw"),
            ("inspect", "configure"),
            ("play", "pause"),
            ("store", "delete"),
            ("signal", "compute"),
        ):
            self.assertNotEqual(active[left], active[right], f"{left}/{right} 동작이 같습니다")

        operators = {
            operator
            for transform in active.values()
            for operator in ("translate", "translateX", "translateY", "rotate", "scale")
            if f"{operator}(" in transform
        }
        self.assertEqual(
            operators,
            {"translate", "translateX", "translateY", "rotate", "scale"},
        )
        repeated = {
            transform
            for transform in set(active.values())
            if list(active.values()).count(transform) > 3
        }
        self.assertEqual(repeated, set(), f"너무 많은 의미군이 같은 동작을 공유합니다: {repeated}")

    def test_internal_part_gestures_are_not_subpixel_only(self):
        gestures = re.findall(
            r"--icon-part-hover-transform:\s*([^;]+)", ICON_MOTION_CSS
        )
        faint = [
            value.strip()
            for value in gestures
            if not _gesture_is_perceptible(value, min_translation=1.6)
        ]
        self.assertEqual(faint, [], f"눈에 잘 안 보이는 SVG 파츠 동작: {faint}")

    def test_active_and_focus_do_not_leave_persistent_icon_transforms(self):
        self.assertNotIn("--icon-selected-transform", ICON_MOTION_CSS)
        self.assertNotIn("--icon-focus-transform", ICON_MOTION_CSS)
        self.assertNotRegex(ICON_MOTION_CSS, r"animation:[^;]*\bboth\b")

        hover_position = ICON_MOTION_CSS.index("@media (hover: hover) and (pointer: fine)")
        press_position = ICON_MOTION_CSS.index("):active .icon[data-icon-motion]")
        self.assertLess(hover_position, press_position)

    def test_refined_semantic_overrides_avoid_misaligned_whole_icon_motion(self):
        quiet_whole_icons = re.search(
            r"\.icon:is\((.*?)\)\s*\{\s*--icon-hover-transform:\s*none;",
            ICON_MOTION_CSS,
            re.DOTALL,
        )
        self.assertIsNotNone(quiet_whole_icons)
        for icon_name in ("wand", "sliders", "target", "move"):
            self.assertIn(f"[data-icon-name='{icon_name}']", quiet_whole_icons.group(1))

        suppressed_names = set(re.findall(r"data-icon-name='([a-z-]+)'", quiet_whole_icons.group(1)))
        part_driven_names: set[str] = set()
        for chunk in ICON_MOTION_CSS.split("}"):
            if "--icon-part-hover-transform" not in chunk:
                continue
            part_driven_names.update(re.findall(r"data-icon-name='([a-z-]+)'", chunk))
        self.assertEqual(
            suppressed_names - part_driven_names,
            set(),
            "whole-icon hover를 끈 아이콘에는 보이는 part 동작이 있어야 합니다",
        )

        self.assertNotRegex(
            ICON_MOTION_CSS,
            r"data-icon-name='save'[^\{]*\.icon-part-3\s*\{",
        )

    def test_motion_styles_do_not_mutate_layout_or_hit_area_properties(self):
        layout_declaration = re.compile(
            r"^\s*(?:display|position|inset|top|right|bottom|left|width|height|"
            r"margin|padding|gap|overflow)\s*:",
            re.MULTILINE,
        )
        self.assertIsNone(layout_declaration.search(ICON_MOTION_CSS))

    def test_infinite_motion_is_limited_to_pointer_hover_or_live_states(self):
        # User opted into repeating hover gestures; none/reduced-motion retain
        # their no-motion contract, and idle controls must never animate.
        self.assertEqual(len(re.findall(r"\binfinite\b", ICON_MOTION_CSS)), 5)
        self.assertIn('animation: icon-hover-repeat 1000ms', ICON_MOTION_CSS)
        self.assertIn('animation: icon-part-hover-repeat 1000ms', ICON_MOTION_CSS)
        hover = ICON_MOTION_CSS.index('@media (hover: hover) and (pointer: fine)')
        self.assertGreater(ICON_MOTION_CSS.index('animation: icon-hover-repeat'), hover)
        self.assertIn(
            ":where([aria-busy='true'], .is-loading, .busy.on)",
            ICON_MOTION_CSS,
        )
        self.assertNotIn(".ai-loading .icon[data-icon-motion='compute']", ICON_MOTION_CSS)
        self.assertNotIn(".running-badge", ICON_MOTION_CSS)
        self.assertIn(".queue-pin.running .icon[data-icon-motion='play']", ICON_MOTION_CSS)
        self.assertIn(".q-row.active .icon[data-icon-motion='wait']", ICON_MOTION_CSS)


if __name__ == "__main__":
    unittest.main()

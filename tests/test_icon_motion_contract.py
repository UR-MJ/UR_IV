"""Static safety contract for the global semantic icon motion stylesheet."""

from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICON_MOTION_CSS = (
    PROJECT_ROOT / "frontend" / "src" / "styles" / "iconMotion.css"
).read_text(encoding="utf-8")


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
        self.assertLessEqual(max(rotations), 14)
        self.assertTrue(scales)
        self.assertGreaterEqual(min(scales), 0.94)
        self.assertLessEqual(max(scales), 1.04)
        self.assertLessEqual(max(hover_durations), 190)
        self.assertLessEqual(max(press_durations), 100)

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

    def test_infinite_motion_is_limited_to_running_or_loading_states(self):
        self.assertEqual(len(re.findall(r"\binfinite\b", ICON_MOTION_CSS)), 3)
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

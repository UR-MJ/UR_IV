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

    def test_motion_styles_do_not_mutate_layout_or_hit_area_properties(self):
        layout_declaration = re.compile(
            r"^\s*(?:display|position|inset|top|right|bottom|left|width|height|"
            r"margin|padding|gap|overflow)\s*:",
            re.MULTILINE,
        )
        self.assertIsNone(layout_declaration.search(ICON_MOTION_CSS))

    def test_infinite_motion_is_limited_to_running_or_loading_states(self):
        self.assertEqual(len(re.findall(r"\binfinite\b", ICON_MOTION_CSS)), 4)
        self.assertIn(
            ":where([aria-busy='true'], .is-loading, .loading, .busy.on)",
            ICON_MOTION_CSS,
        )
        self.assertIn(".ai-loading .icon[data-icon-motion='compute']", ICON_MOTION_CSS)
        self.assertIn(":where(.running-badge, .queue-pin.running)", ICON_MOTION_CSS)
        self.assertIn(".q-row.active .icon[data-icon-motion='wait']", ICON_MOTION_CSS)


if __name__ == "__main__":
    unittest.main()

"""Frontend contrast and tooltip accessibility regression tests."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLE = (ROOT / "frontend" / "src" / "style.css").read_text(encoding="utf-8")
APP = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
ANIMA_PANEL = (ROOT / "frontend" / "src" / "components" / "AnimaGuidancePanel.vue").read_text(encoding="utf-8")


def _css_hex_variable(name: str) -> str:
    match = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{6}})", STYLE)
    assert match, f"missing CSS variable: {name}"
    return match.group(1)


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    high, low = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class FrontendContrastTests(unittest.TestCase):
    def test_muted_text_remains_readable_on_cards(self) -> None:
        ratio = _contrast(_css_hex_variable("--text-muted"), _css_hex_variable("--bg-card"))
        self.assertGreaterEqual(ratio, 4.5, f"muted text contrast is only {ratio:.2f}:1")

    def test_disabled_buttons_keep_a_visible_opacity_floor(self) -> None:
        match = re.search(r"button:disabled\s*\{[^}]*opacity\s*:\s*([0-9.]+)\s*!important", STYLE, re.DOTALL)
        self.assertIsNotNone(match, "global disabled-button visibility floor is missing")
        self.assertGreaterEqual(float(match.group(1)), 0.6)

    def test_app_installs_theme_aware_tooltips(self) -> None:
        self.assertIn("import AppTooltip from './components/AppTooltip.vue'", APP)
        self.assertIn("<AppTooltip />", APP)
        tooltip = ROOT / "frontend" / "src" / "components" / "AppTooltip.vue"
        self.assertTrue(tooltip.is_file())
        source = tooltip.read_text(encoding="utf-8")
        self.assertIn("removeAttribute('title')", source)
        self.assertIn("role=\"tooltip\"", source)

    def test_anima_dropdown_uses_compact_panel_font_size(self) -> None:
        self.assertRegex(
            ANIMA_PANEL,
            r":deep\(\.csel-display\)\s*\{[^}]*font-size\s*:\s*11px",
        )
        self.assertRegex(
            ANIMA_PANEL,
            r"\.ext-note\s*\{[^}]*font-size\s*:\s*10px",
        )

    def test_anima_panel_exposes_forge_import_action(self) -> None:
        self.assertIn("requestAction('import_anima_from_forge')", ANIMA_PANEL)

    def test_anima_panel_exposes_current_forge_smc_controls(self) -> None:
        self.assertIn("b('guid_smc_master_enabled')", ANIMA_PANEL)
        self.assertIn('v-model="w._guid_smc_preset"', ANIMA_PANEL)
        self.assertIn("'Cosmos / Wan'", ANIMA_PANEL)
        self.assertIn("w._guid_smc_preset === 'Custom'", ANIMA_PANEL)

    def test_anima_panel_exposes_current_forge_rdc_controls(self) -> None:
        for widget_id in (
            '_guid_rdc_enabled', '_guid_rdc_tau',
            '_guid_rdc_alpha_ll', '_guid_rdc_alpha_hh',
        ):
            self.assertIn(widget_id, ANIMA_PANEL)


if __name__ == "__main__":
    unittest.main()

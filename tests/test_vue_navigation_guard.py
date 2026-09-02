from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QUrl

from ui.generator_ui_setup import (
    UISetupMixin,
    _VueNavigationDecision,
    _VueNavigationPolicy,
)


class VueNavigationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.frontend_root = self.root / "frontend_dist"
        self.frontend_root.mkdir()
        self.index = self.frontend_root / "index.html"
        self.index.write_text("<!doctype html>", encoding="utf-8")
        self.policy = _VueNavigationPolicy(self.index)

    def test_allows_only_exact_index_as_main_document(self) -> None:
        index_url = QUrl.fromLocalFile(str(self.index))
        index_url.setQuery("theme=dark")
        index_url.setFragment("settings")

        self.assertIs(
            self.policy.decide(index_url, is_main_frame=True),
            _VueNavigationDecision.ALLOW,
        )

        nested_html = self.frontend_root / "assets" / "other.html"
        nested_html.parent.mkdir()
        nested_html.write_text("untrusted document", encoding="utf-8")
        self.assertIs(
            self.policy.decide(
                QUrl.fromLocalFile(str(nested_html)), is_main_frame=True
            ),
            _VueNavigationDecision.BLOCK,
        )

    def test_blocks_subframes_even_when_the_file_is_inside_frontend_dist(self) -> None:
        self.assertIs(
            self.policy.decide(
                QUrl.fromLocalFile(str(self.index)), is_main_frame=False
            ),
            _VueNavigationDecision.BLOCK,
        )

    def test_blocks_sibling_prefix_and_parent_traversal_paths(self) -> None:
        prefix_collision = self.root / "frontend_dist_backup" / "index.html"
        prefix_collision.parent.mkdir()
        prefix_collision.write_text("outside", encoding="utf-8")
        parent_file = self.frontend_root / ".." / "secret.html"
        parent_file.resolve().write_text("outside", encoding="utf-8")

        for candidate in (prefix_collision, parent_file):
            with self.subTest(candidate=candidate):
                self.assertIs(
                    self.policy.decide(
                        QUrl.fromLocalFile(str(candidate)), is_main_frame=True
                    ),
                    _VueNavigationDecision.BLOCK,
                )

    def test_routes_safe_external_schemes_outside_the_webengine_page(self) -> None:
        for raw_url in (
            "https://github.com/UR-al/UR_IV/releases",
            "http://example.com/release-notes",
            "mailto:maintainer@example.com",
        ):
            with self.subTest(raw_url=raw_url):
                self.assertIs(
                    self.policy.decide(QUrl(raw_url), is_main_frame=True),
                    _VueNavigationDecision.OPEN_EXTERNALLY,
                )

    def test_blocks_unsafe_or_malformed_external_urls(self) -> None:
        for raw_url in (
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "qrc:///qtwebchannel/qwebchannel.js",
            "https:///missing-host",
        ):
            with self.subTest(raw_url=raw_url):
                self.assertIs(
                    self.policy.decide(QUrl(raw_url), is_main_frame=True),
                    _VueNavigationDecision.BLOCK,
                )


class VueNavigationIntegrationContractTests(unittest.TestCase):
    def test_main_page_routes_external_urls_and_disables_subframe_injection(self) -> None:
        source = inspect.getsource(UISetupMixin._setup_ui)

        self.assertIn("def acceptNavigationRequest", source)
        self.assertIn("QDesktopServices.openUrl(url)", source)
        self.assertIn("qwc.setRunsOnSubFrames(False)", source)
        self.assertIn("return _ExternalNavigationPage", source)


if __name__ == "__main__":
    unittest.main()

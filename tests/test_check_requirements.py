from __future__ import annotations

import unittest
from unittest.mock import patch

from importlib.metadata import PackageNotFoundError

from core.check_requirements import _requirement_satisfied


class CheckRequirementsTests(unittest.TestCase):
    def test_installed_version_must_satisfy_the_requirement(self):
        with patch("core.check_requirements.version", return_value="2.31.0"):
            self.assertFalse(_requirement_satisfied("requests", "requests>=2.32.0"))
        with patch("core.check_requirements.version", return_value="2.32.3"):
            self.assertTrue(_requirement_satisfied("requests", "requests>=2.32.0"))

    def test_missing_distribution_is_not_satisfied(self):
        with patch("core.check_requirements.version", side_effect=PackageNotFoundError):
            self.assertFalse(_requirement_satisfied("missing", "missing>=1.0"))

    def test_false_environment_marker_does_not_trigger_install(self):
        with patch("core.check_requirements.version", side_effect=AssertionError("must not inspect")):
            self.assertTrue(_requirement_satisfied("demo", "demo>=9; python_version<'2'"))


if __name__ == "__main__":
    unittest.main()

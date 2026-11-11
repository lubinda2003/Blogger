"""Regression tests for primary-source checks on Google product claims."""

import unittest

from src.quality_checks import has_official_google_source


class TestGooglePrimarySourceRequirements(unittest.TestCase):
    def test_official_google_developer_and_help_domains_are_accepted(self):
        self.assertTrue(has_official_google_source(["https://ai.google.dev/gemini-api/docs/pricing"], pricing=True))
        self.assertTrue(has_official_google_source(["https://support.google.com/docs/answer/14356410"]))

    def test_third_party_sources_are_not_treated_as_official(self):
        self.assertFalse(has_official_google_source([
            "https://www.nocode.mba/articles/google-ai-studio-pricing",
            "https://finance.yahoo.com/news/example",
            "https://www.youtube.com/watch?v=example",
        ], pricing=True))

    def test_lookalike_domain_is_not_accepted(self):
        self.assertFalse(has_official_google_source(["https://ai.google.dev.example.com/pricing"], pricing=True))
        self.assertFalse(has_official_google_source(["https://google.com.evil.example/pricing"]))


if __name__ == "__main__":
    unittest.main()

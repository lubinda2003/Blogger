"""Tests for deterministic first-party documentation discovery ordering."""

import unittest

from src.research import ResearchCollector


class TestOfficialSourcePriority(unittest.TestCase):
    def test_editorially_supplied_vendor_domain_is_prioritized(self):
        target = "https://www.notion.so/"
        self.assertLess(
            ResearchCollector._source_priority("https://www.notion.so/help", "Notion Help", target),
            ResearchCollector._source_priority("https://example.com/notion-guide", "Notion guide", target),
        )

    def test_documentation_subdomains_and_paths_are_prioritized(self):
        self.assertEqual(
            ResearchCollector._source_priority("https://support.google.com/gemini", "Gemini Help"),
            1,
        )
        self.assertEqual(
            ResearchCollector._source_priority("https://example.com/docs/api", "API reference"),
            1,
        )

    def test_official_documentation_title_is_a_secondary_signal(self):
        self.assertEqual(
            ResearchCollector._source_priority(
                "https://example.com/article", "Official documentation for product features"
            ),
            2,
        )

    def test_general_commentary_is_not_mislabeled_as_official(self):
        self.assertEqual(
            ResearchCollector._source_priority(
                "https://example.com/blog", "My thoughts on productivity tools"
            ),
            3,
        )

    def test_target_domain_matching_does_not_match_lookalike_domains(self):
        target = "https://notion.so/"
        self.assertNotEqual(
            ResearchCollector._source_priority("https://notion.so.evil.example/post", "Notion", target),
            0,
        )


if __name__ == "__main__":
    unittest.main()

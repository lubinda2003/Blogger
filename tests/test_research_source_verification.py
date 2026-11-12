"""Regression tests for source-domain policy and Tavily fallback verification."""

import unittest
from unittest.mock import patch

from src.research import ResearchCollector


class TestResearchSourceVerification(unittest.TestCase):
    def test_allowlist_handles_www_and_domains_starting_with_w(self):
        collector = ResearchCollector(domain_allowlist=["wikipedia.org"])

        self.assertTrue(collector._is_domain_allowed("https://www.wikipedia.org/wiki/AI"))
        self.assertTrue(collector._is_domain_allowed("https://en.wikipedia.org/wiki/AI"))
        self.assertFalse(collector._is_domain_allowed("https://notwikipedia.org/wiki/AI"))

    @patch("src.research.topic_relevance_claim", return_value="enterprise API billing limits")
    @patch.object(
        ResearchCollector,
        "verify_and_fetch_source",
        return_value=(False, 403, "", "", "https://example.com/guide", "Access denied"),
    )
    @patch.object(
        ResearchCollector,
        "_search_tavily",
        return_value=[
            {
                "title": "Notion workspace collaboration guide",
                "url": "https://example.com/guide",
                "raw_content": (
                    "Notion workspace collaboration guide explains how teams share projects, "
                    "assign tasks, and manage team updates across a shared workspace."
                ),
            }
        ],
    )
    def test_topic_mention_does_not_replace_an_unsupported_required_claim(
        self, _search, _fetch, _claim
    ):
        collector = ResearchCollector(tavily_api_key="test-key")
        brief = collector.conduct_research(
            topic_id="notion-workspace",
            topic_title="Notion workspace collaboration guide",
            category="Software and Productivity",
            target_url="",
            zambia_context=False,
        )

        self.assertEqual(len(brief.sources), 1)
        self.assertFalse(brief.sources[0].verified)
        self.assertIn("enterprise API billing limits", brief.sources[0].unverified_claims)

    @patch.object(
        ResearchCollector,
        "verify_and_fetch_source",
        return_value=(False, 403, "", "", "https://example.com/guide", "Access denied"),
    )
    @patch.object(
        ResearchCollector,
        "_search_tavily",
        return_value=[
            {
                "title": "Notion workspace collaboration guide",
                "url": "https://example.com/guide",
                "raw_content": (
                    "Notion workspace collaboration guide explains how teams share projects, "
                    "assign tasks, and manage team updates across a shared workspace."
                ),
            }
        ],
    )
    def test_tavily_fallback_preserves_actual_direct_fetch_http_status(self, _search, _fetch):
        collector = ResearchCollector(tavily_api_key="test-key")
        brief = collector.conduct_research(
            topic_id="notion-workspace",
            topic_title="Notion workspace collaboration guide",
            category="Software and Productivity",
            target_url="",
            zambia_context=False,
        )

        self.assertTrue(brief.sources[0].verified)
        self.assertEqual(brief.sources[0].http_status, 403)
        self.assertTrue(brief.sources[0].content_extraction_success)


if __name__ == "__main__":
    unittest.main()

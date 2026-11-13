import unittest

from src.research import ResearchCollector


class ResearchSourceReliabilityTests(unittest.TestCase):
    def test_default_low_evidence_domains_remain_blocked_with_empty_config(self):
        collector = ResearchCollector(tavily_api_key="test-key", domain_blocklist=[])

        self.assertFalse(collector._is_domain_allowed("https://www.facebook.com/example"))
        self.assertFalse(collector._is_domain_allowed("https://youtube.com/watch?v=123"))
        self.assertFalse(collector._is_domain_allowed("https://reddit.com/r/example"))
        self.assertTrue(collector._is_domain_allowed("https://docs.example.com/guide"))

    def test_custom_blocklist_extends_default_exclusions(self):
        collector = ResearchCollector(
            tavily_api_key="test-key",
            domain_blocklist=["low-quality.example"],
        )

        self.assertFalse(collector._is_domain_allowed("https://low-quality.example/post"))
        self.assertFalse(collector._is_domain_allowed("https://www.instagram.com/example"))
        self.assertTrue(collector._is_domain_allowed("https://support.example.com/article"))

    def test_research_queries_cover_distinct_intents_for_same_topic(self):
        queries = ResearchCollector._build_research_queries(
            "15 AI Tips and Workflows I Wish I Knew Sooner"
        )

        self.assertEqual(len(queries), 3)
        self.assertIn('"15 AI Tips and Workflows I Wish I Knew Sooner"', queries[0])
        self.assertIn("practical guide examples workflow", queries[1])
        self.assertIn("tutorial implementation use cases", queries[2])

    def test_empty_topic_does_not_create_search_queries(self):
        self.assertEqual(ResearchCollector._build_research_queries("  "), [])


if __name__ == "__main__":
    unittest.main()

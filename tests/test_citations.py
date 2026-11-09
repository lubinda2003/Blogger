"""Regression tests for the first live-run failure: the model cited the topic's unverified target URL."""

import unittest
from unittest.mock import patch

from src.article_writer import ArticleWriter
from src.research import ResearchBrief, ResearchCollector, SourceCitation, mentions_brand, topic_brand


def _source(url, verified=True):
    return SourceCitation(
        title=url, url=url, retrieval_date="November 2026", verified=verified, http_status=200,
        content_extraction_success=True, evidence_excerpt="e", cleaned_text="text" if verified else None,
        verified_claims=["c"] if verified else [],
    )


def _brief(*sources):
    brief = ResearchBrief(topic_id="t", topic_title="Notion dashboard", target_url="https://www.notion.com")
    brief.sources = list(sources)
    return brief


BODY = (
    '<p>Start with <a href="https://docs.example.com/guide">the guide</a> and the '
    '<a href="https://www.notion.com/">official site</a>.</p><p>Then <a href="https://other.example.org/x">read more</a>.</p>'
)
DRAFT = {
    "html_content": BODY,
    "sources_used": [
        {"title": "Guide", "url": "https://docs.example.com/guide"},
        {"title": "Notion", "url": "https://www.notion.com"},
        {"title": "Other", "url": "https://other.example.org/x"},
    ],
}


class TestDropUnverifiedSources(unittest.TestCase):
    def setUp(self):
        self.writer = ArticleWriter(api_key="k")
        self.brief = _brief(_source("https://docs.example.com/guide"), _source("https://other.example.org/x"),
                            _source("https://www.notion.com", verified=False))

    def test_unverified_citation_is_removed_from_the_list_and_unlinked_in_the_body(self):
        out = self.writer._drop_unverified_sources(DRAFT, self.brief)
        self.assertEqual([s["url"] for s in out["sources_used"]], ["https://docs.example.com/guide", "https://other.example.org/x"])
        self.assertNotIn("notion.com", out["html_content"])
        self.assertIn("official site", out["html_content"])  # the words stay, only the link goes

    def test_verified_links_are_untouched(self):
        out = self.writer._drop_unverified_sources(DRAFT, self.brief)
        self.assertIn('href="https://docs.example.com/guide"', out["html_content"])
        self.assertIn('href="https://other.example.org/x"', out["html_content"])

    def test_trailing_slash_and_scheme_differences_still_count_as_verified(self):
        brief = _brief(_source("https://docs.example.com/guide/"), _source("http://other.example.org/x"))
        out = self.writer._drop_unverified_sources(DRAFT, brief)
        self.assertEqual(len(out["sources_used"]), 2)

    def test_nothing_changes_when_everything_is_verified(self):
        brief = _brief(_source("https://docs.example.com/guide"), _source("https://www.notion.com"), _source("https://other.example.org/x"))
        self.assertIs(self.writer._drop_unverified_sources(DRAFT, brief), DRAFT)

    def test_no_verified_sources_leaves_the_decision_to_the_quality_gate(self):
        self.assertIs(self.writer._drop_unverified_sources(DRAFT, _brief(_source("https://x.example", verified=False))), DRAFT)

    def test_the_input_draft_is_not_mutated(self):
        before = list(DRAFT["sources_used"])
        self.writer._drop_unverified_sources(DRAFT, self.brief)
        self.assertEqual(DRAFT["sources_used"], before)


class TestCitationRuleInBrief(unittest.TestCase):
    def test_brief_tells_the_model_to_cite_only_verified_urls(self):
        text = _brief(_source("https://docs.example.com/guide")).format_for_prompt()
        self.assertIn("CITATION RULE", text)
        self.assertIn("Target URL", text)


class TestTopicBrand(unittest.TestCase):
    def test_brand_comes_from_the_target_domain_when_the_title_names_it(self):
        self.assertEqual(topic_brand("How to Build a Clean Project Management Dashboard in Notion", "https://www.notion.com"), "notion")
        self.assertEqual(topic_brand("Google Docs voice typing guide", "https://docs.google.com/x"), "google")

    def test_no_brand_when_the_title_does_not_name_the_tool(self):
        self.assertIsNone(topic_brand("7 Best Free AI Research Tools for Students", "https://consensus.app"))

    def test_no_brand_for_missing_url_or_very_short_names(self):
        self.assertIsNone(topic_brand("Anything", ""))
        self.assertIsNone(topic_brand("Try X for work", "https://x.com"))

    def test_page_must_name_the_tool_at_least_twice(self):
        self.assertTrue(mentions_brand("notion", "Notion is great. Notion pages are flexible."))
        self.assertFalse(mentions_brand("notion", "A profile of Taskade that mentions Notion once."))
        self.assertTrue(mentions_brand(None, "anything at all"))


class TestRelevanceGate(unittest.TestCase):
    TITLE = "Build a Clean Project Management Dashboard in Notion"
    GOOD = TITLE + ". Notion lets you build a project management dashboard. Notion databases power the dashboard."
    COMPETITOR = TITLE + " Taskade is a project management dashboard company profile with many features."

    def _research(self):
        pages = {"https://blog.example.com/notion": self.GOOD, "https://profiles.example.com/taskade": self.COMPETITOR}
        results = [
            {"title": "Notion dashboard guide", "url": "https://blog.example.com/notion", "content": self.GOOD},
            {"title": "Taskade profile", "url": "https://profiles.example.com/taskade", "content": self.COMPETITOR},
        ]

        def fake_fetch(self_, url):
            self_.last_fetched_content = pages.get(url, "")
            return (bool(pages.get(url)), 200, "t", "e", url, None if pages.get(url) else "nope")

        collector = ResearchCollector()
        with patch.object(ResearchCollector, "_search_tavily", return_value=results), \
             patch.object(ResearchCollector, "verify_and_fetch_source", fake_fetch):
            return collector.conduct_research("t", self.TITLE, "Productivity", "https://www.notion.com", zambia_context=False)

    def test_a_page_about_a_competitor_is_not_accepted_as_a_source_for_a_notion_topic(self):
        brief = self._research()
        by_url = {s.url: s for s in brief.sources}
        self.assertTrue(by_url["https://blog.example.com/notion"].verified)
        self.assertFalse(by_url["https://profiles.example.com/taskade"].verified)
        self.assertIn("notion", by_url["https://profiles.example.com/taskade"].failure_reason.lower())


if __name__ == "__main__":
    unittest.main()

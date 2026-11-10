"""Regression tests for the problems found in the live runs of 8-10 November 2026."""

import unittest

from src.article_writer import ArticleDraft, ArticleWriter
from src.config import load_config
from src.quality_checks import QualityGate
from src.research import DEFAULT_DOMAIN_BLOCKLIST, ResearchCollector

URL_WITH_AMP = "https://amp.example.com/select/best?a=1&hostDomain=www.example.com"


def _draft(html, sources):
    return ArticleDraft(
        topic_id="t", title="Practical Guide to Freelance Invoicing",
        meta_description="A clear, step-by-step walkthrough detailing invoicing workflows for freelancers.",
        labels=["Freelancing"], html_content=html, summary="s", sources_used=sources, primary_intent="Tutorial",
        word_count=900, last_checked_date="November 2026", is_dry_run_fixture=False,
        affiliate_disclosure_required=False, screenshot_needed=False,
    )


class TestLinkedSourcesWithAmpersands(unittest.TestCase):
    """The Sources section writes & as &amp;, so a URL containing & was reported as 'not linked in the body'."""

    def _failures(self, html):
        gate = QualityGate(min_word_count=0, min_sources=1, max_reading_grade=0, is_live_mode=False)
        report = gate.run_all_checks(
            _draft(html, [{"title": "T", "url": URL_WITH_AMP}]), verified_source_urls=[URL_WITH_AMP], check_duplicate=False
        )
        return [f for f in report.failures if "not linked" in f]

    def test_url_with_an_ampersand_counts_as_linked_when_the_href_is_escaped(self):
        self.assertEqual(self._failures('<p>x</p><a href="https://amp.example.com/select/best?a=1&amp;hostDomain=www.example.com">T</a>'), [])

    def test_a_missing_link_is_still_reported(self):
        self.assertEqual(len(self._failures("<p>no links here</p>")), 1)


class TestDropUnverifiedWithAmpersands(unittest.TestCase):
    def test_an_escaped_href_to_an_unverified_source_is_unwrapped(self):
        class Source:
            def __init__(self, url):
                self.url = url

        class Brief:
            def verified_sources(self):
                return [Source("https://good.example.com/page")]

        parsed = {
            "sources_used": [{"url": "https://good.example.com/page"}, {"url": URL_WITH_AMP}],
            "html_content": '<a href="https://good.example.com/page">good</a> <a href="https://amp.example.com/select/best?a=1&amp;hostDomain=www.example.com">bad</a>',
        }
        out = ArticleWriter(api_key="k")._drop_unverified_sources(parsed, Brief())
        self.assertEqual([s["url"] for s in out["sources_used"]], ["https://good.example.com/page"])
        self.assertIn("bad", out["html_content"])
        self.assertNotIn("amp.example.com", out["html_content"])


class TestDefaultBlocklist(unittest.TestCase):
    def test_video_social_and_company_profile_sites_are_blocked_by_default(self):
        rc = ResearchCollector()
        for url in ("https://www.youtube.com/watch?v=abc", "https://youtu.be/abc", "https://www.cbinsights.com/company/taskade",
                    "https://www.reddit.com/r/freelance/", "https://old.reddit.com/r/x", "https://x.com/someone"):
            self.assertFalse(rc._is_domain_allowed(url), url)

    def test_normal_sites_are_not_blocked(self):
        rc = ResearchCollector()
        for url in ("https://www.notion.com/help", "https://zapier.com/blog/best-free-invoice-software/", "https://waveapps.com/", "https://wired.com/a"):
            self.assertTrue(rc._is_domain_allowed(url), url)

    def test_an_explicit_list_replaces_the_default_and_an_empty_list_disables_blocking(self):
        self.assertTrue(ResearchCollector(domain_blocklist=[])._is_domain_allowed("https://www.youtube.com/watch?v=abc"))
        custom = ResearchCollector(domain_blocklist=["www.waveapps.com"])
        self.assertFalse(custom._is_domain_allowed("https://waveapps.com/pricing"))  # was mangled by lstrip("www.")
        self.assertTrue(custom._is_domain_allowed("https://www.youtube.com/watch?v=abc"))

    def test_the_default_list_is_not_empty(self):
        self.assertIn("youtube.com", DEFAULT_DOMAIN_BLOCKLIST)


class TestGroqModel(unittest.TestCase):
    def test_default_is_a_current_model_not_the_retired_llama(self):
        self.assertEqual(load_config().groq_model, "openai/gpt-oss-120b")
        self.assertEqual(ArticleWriter(api_key="k", groq_api_key="g").groq_model, "openai/gpt-oss-120b")


if __name__ == "__main__":
    unittest.main()

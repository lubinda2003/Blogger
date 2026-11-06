"""Unit tests for research collector, live source verification, and evidence mapping."""

import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from src.research import ResearchCollector, ResearchBrief, SourceCitation


class TestResearchAndSources(unittest.TestCase):
    """Test suite for live research collection and claim-to-source mapping."""

    def setUp(self):
        self.collector = ResearchCollector(request_timeout=5)

    def test_unreachable_source_is_not_marked_verified(self):
        """An unreachable URL (e.g. 404 or connection failure) must NOT be marked verified."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://example.com/notfound",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=MagicMock(read=lambda: b"Not found"),
            )

            ok, status, title, excerpt, final_url, err = self.collector.verify_and_fetch_source("https://example.com/notfound")
            self.assertFalse(ok)
            self.assertEqual(status, 404)
            self.assertIn("HTTP request failed with code 404", err)

    def test_head_failure_falls_back_to_get_when_applicable(self):
        """When HEAD returns 405 Method Not Allowed, GET should be attempted."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            def side_effect(req, timeout=None):
                if req.get_method() == "HEAD":
                    raise urllib.error.HTTPError(
                        url="https://example.com/test",
                        code=405,
                        msg="Method Not Allowed",
                        hdrs={},
                        fp=MagicMock(read=lambda: b""),
                    )
                else:
                    # GET returns valid HTML
                    resp = MagicMock()
                    resp.status = 200
                    resp.url = "https://example.com/test"
                    resp.__enter__.return_value = resp
                    resp.read.return_value = b"<html><head><title>Official Documentation Page</title></head><body><p>This is substantive factual documentation that is long enough to pass extraction checks.</p></body></html>"
                    return resp

            mock_urlopen.side_effect = side_effect

            ok, status, title, excerpt, final_url, err = self.collector.verify_and_fetch_source("https://example.com/test")
            self.assertTrue(ok)
            self.assertEqual(status, 200)
            self.assertEqual(title, "Official Documentation Page")
            self.assertIn("substantive factual documentation", excerpt)

    def test_insufficient_verified_sources_flags_failure(self):
        """If fewer than 2 sources can be verified, insufficient_evidence must be True."""
        brief = ResearchBrief(topic_id="test", topic_title="Test Topic", target_url="https://example.com")
        brief.sources = [
            SourceCitation(title="Failed Source 1", url="https://example.com/1", retrieval_date="Today", verified=False),
            SourceCitation(title="Verified Source 2", url="https://example.com/2", retrieval_date="Today", verified=True),
        ]
        self.assertEqual(len(brief.verified_sources()), 1)

    def test_prompt_format_includes_claim_to_source_mapping(self):
        """The rendered prompt text must include the verified source URLs and claim mappings."""
        brief = ResearchBrief(topic_id="test", topic_title="Test", target_url="https://example.com")
        brief.key_facts = ["Fact 1: Gemini accepts structured schemas."]
        brief.sources = [
            SourceCitation(
                title="Google Docs",
                url="https://ai.google.dev",
                retrieval_date="October 2026",
                verified=True,
                verified_claims=["Structured output schema", "Free tier bounds"],
                evidence_excerpt="Gemini models accept response schema.",
            )
        ]

        prompt_str = brief.format_for_prompt()
        self.assertIn("https://ai.google.dev", prompt_str)
        self.assertIn("Structured output schema", prompt_str)
        self.assertIn("Gemini models accept response schema", prompt_str)


    def test_http_200_with_irrelevant_content_does_not_verify_claims(self):
        """A website returning HTTP 200 with unrelated content must NOT mark claims as verified."""
        with patch.object(self.collector, "verify_and_fetch_source") as mock_fetch:
            # Returns HTTP 200, but content is an unrelated cake baking blog
            mock_fetch.return_value = (
                True,
                200,
                "Delicious Chocolate Cake Recipes",
                "How to bake double chocolate brownies from scratch in 30 minutes.",
                "https://example.com/blog",
                None,
            )
            self.collector.last_fetched_content = "Preheat oven to 350 degrees. Mix cocoa powder and butter."

            brief = self.collector.conduct_research(
                topic_id="notion-guide",
                topic_title="How to Use Notion for Project Management",
                category="Software and Productivity",
                target_url="https://example.com/blog",
                configured_sources=[{
                    "title": "Unrelated Cooking Blog",
                    "url": "https://example.com/blog",
                    "claims": ["Database organization, workspace templates, and permission management"],
                }],
                dry_run=False,
            )

            source = brief.sources[0]
            # Must NOT be verified because content does not support the claim!
            self.assertFalse(source.verified)
            self.assertEqual(len(source.verified_claims), 0)
            self.assertIn("Database organization, workspace templates, and permission management", source.unverified_claims)
            self.assertIn("does not support required claims", source.failure_reason)

    def test_http_200_with_supporting_content_marks_claims_verified(self):
        """A website returning HTTP 200 that substantively mentions claim keywords is marked verified."""
        with patch.object(self.collector, "verify_and_fetch_source") as mock_fetch:
            mock_fetch.return_value = (
                True,
                200,
                "Notion Help: Databases and Workspace Templates",
                "Learn how to set up relational databases and custom workspace templates with permissions.",
                "https://notion.so/help",
                None,
            )
            self.collector.last_fetched_content = (
                "Notion databases allow workspace organization, permission management, and custom templates."
            )

            brief = self.collector.conduct_research(
                topic_id="notion-guide",
                topic_title="How to Use Notion for Project Management",
                category="Software and Productivity",
                target_url="https://notion.so/help",
                configured_sources=[{
                    "title": "Notion Official Help",
                    "url": "https://notion.so/help",
                    "claims": ["Database organization, workspace templates, and permission management"],
                }],
                dry_run=False,
            )

            source = brief.sources[0]
            self.assertTrue(source.verified)
            self.assertIn("Database organization, workspace templates, and permission management", source.verified_claims)
            self.assertEqual(len(source.unverified_claims), 0)

    def test_soft_404_or_error_page_disguised_as_200_is_rejected(self):
        """Pages returning HTTP 200 with '404 Not Found' or error title must fail verification."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.status = 200
            resp.url = "https://example.com/deadlink"
            resp.__enter__.return_value = resp
            resp.read.return_value = b"<html><head><title>404 Page Not Found</title></head><body><p>The page requested is missing.</p></body></html>"
            mock_urlopen.return_value = resp

            ok, status, title, excerpt, final_url, err = self.collector.verify_and_fetch_source("https://example.com/deadlink")
            self.assertFalse(ok)
            self.assertEqual(status, 200)
            self.assertIn("missing page, error", err)

    def test_scattered_keyword_overlap_without_contextual_support_is_rejected(self):
        """Keywords scattered across disjoint headers and footers must not count as claim verification."""
        claim = "Freelancer service fee structure on Upwork contracts"
        # Content has 'contracts' in a disclaimer footer and 'fee' in pricing link, but no coherent claim support
        corpus = (
            "<html><body>"
            "<header><nav><a href='/pricing'>Fee Calculator</a></nav></header>"
            "<main><p>Welcome to our unrelated platform landing page with generic text.</p></main>"
            "<footer><p>All legal contracts are subject to local arbitration.</p></footer>"
            "</body></html>"
        )
        is_supported = self.collector.check_claim_support(claim, corpus)
        self.assertFalse(
            is_supported,
            "Loose keyword overlap unexpectedly verified a claim without contextual sentence-level support.",
        )

    def test_unsupported_claim_routes_to_unverified_and_requires_manual_review(self):
        """Claims without reliable source support must be routed to unverified_claims and marked for review."""
        with patch.object(self.collector, "verify_and_fetch_source") as mock_fetch:
            mock_fetch.return_value = (
                True,
                200,
                "Generic Overview Page",
                "A generic overview with no specific pricing or contract details.",
                "https://example.com/fees",
                None,
            )
            self.collector.last_fetched_content = "This page discusses general digital marketing trends in 2026."

            brief = self.collector.conduct_research(
                topic_id="upwork-fees",
                topic_title="Understanding Upwork Freelancer Fees",
                category="Freelancing and Remote Work",
                target_url="https://example.com/fees",
                configured_sources=[{
                    "title": "Unverified Fee Article",
                    "url": "https://example.com/fees",
                    "claims": ["Freelancer service fee structure on Upwork contracts"],
                }],
                dry_run=False,
            )

            source = brief.sources[0]
            self.assertFalse(source.verified)
            self.assertIn("Freelancer service fee structure on Upwork contracts", source.unverified_claims)
            self.assertEqual(len(source.verified_claims), 0)
            self.assertIn("does not support required claims", source.failure_reason.lower())

    def test_javascript_spa_page_fails_extraction(self):
        """A JavaScript-only SPA page returning HTTP 200 with an empty skeleton must fail content extraction."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.status = 200
            resp.url = "https://example.com/spa"
            resp.__enter__.return_value = resp
            resp.read.return_value = b"<html><head><title>App</title></head><body><div id='root'></div></body></html>"
            mock_urlopen.return_value = resp

            ok, status, title, excerpt, final_url, err = self.collector.verify_and_fetch_source("https://example.com/spa")
            self.assertFalse(ok)
            self.assertEqual(status, 200)
            self.assertIn("JavaScript-rendered SPA page", err)

    def test_redirect_and_canonical_url(self):
        """Redirects must be followed and final canonical URL captured via resp.url."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.status = 200
            resp.url = "https://canonical.example.com/page"
            resp.__enter__.return_value = resp
            resp.read.return_value = b"<html><head><title>Canonical Page</title></head><body><p>This is a long substantive paragraph with enough text to pass extraction check successfully.</p></body></html>"
            mock_urlopen.return_value = resp

            ok, status, title, excerpt, final_url, err = self.collector.verify_and_fetch_source("https://example.com/old")
            self.assertTrue(ok)
            self.assertEqual(status, 200)
            self.assertEqual(final_url, "https://canonical.example.com/page")

    def test_antibot_response_detected(self):
        """Anti-bot challenges (e.g. Cloudflare Ray ID) disguised as HTTP 200 must fail extraction."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.status = 200
            resp.url = "https://example.com/protected"
            resp.__enter__.return_value = resp
            resp.read.return_value = b"<html><head><title>Access Denied</title></head><body><p>Cloudflare Ray ID: 12345 - Please enable JavaScript and verify you are human.</p></body></html>"
            mock_urlopen.return_value = resp

            ok, status, title, excerpt, final_url, err = self.collector.verify_and_fetch_source("https://example.com/protected")
            self.assertFalse(ok)
            self.assertIn("anti-bot challenge", err)

    def test_tavily_search_success_returns_results(self):
        """Tavily search HTTP POST returning 200 must return result dictionaries."""
        collector = ResearchCollector(tavily_api_key="tvly-mock-key")
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.status = 200
            resp.__enter__.return_value = resp
            resp.read.return_value = b'{"results": [{"title": "Notion Docs", "url": "https://notion.so/help", "content": "Official Notion guide."}]}'
            mock_urlopen.return_value = resp

            results = collector._search_tavily("Notion documentation", max_results=3)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["title"], "Notion Docs")
            self.assertEqual(results[0]["url"], "https://notion.so/help")

    def test_tavily_search_401_unauthorized_falls_back_gracefully(self):
        """An invalid Tavily API key returning 401 must log a warning and return [] without raising."""
        collector = ResearchCollector(tavily_api_key="invalid-key")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://api.tavily.com/search",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=MagicMock(read=lambda: b"Unauthorized"),
            )

            results = collector._search_tavily("test query")
            self.assertEqual(results, [])

    def test_tavily_search_429_rate_limit_falls_back_gracefully(self):
        """A Tavily 429 rate limit error must log a warning and return [] gracefully."""
        collector = ResearchCollector(tavily_api_key="tvly-mock-key")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://api.tavily.com/search",
                code=429,
                msg="Rate limit exceeded",
                hdrs={},
                fp=MagicMock(read=lambda: b"Rate limit"),
            )

            results = collector._search_tavily("test query")
            self.assertEqual(results, [])

    def test_tavily_fallback_corpus_verifies_claim_when_direct_fetch_blocked(self):
        """When direct HTTP fetch is blocked by anti-bot, Tavily extracted snippet serves as fallback corpus."""
        collector = ResearchCollector(tavily_api_key="tvly-mock-key")
        with patch.object(collector, "_search_tavily") as mock_search, \
             patch.object(collector, "verify_and_fetch_source") as mock_fetch:

            mock_search.return_value = [{
                "title": "Shopify Documentation",
                "url": "https://help.shopify.com",
                "content": "Official Shopify documentation on store creation, payment gateways, and checkout management.",
                "raw_content": "Official Shopify documentation on store creation, payment gateways, and checkout management.",
            }]

            # Direct fetch fails with Cloudflare challenge
            mock_fetch.return_value = (
                False,
                403,
                "Access Denied",
                "",
                "https://help.shopify.com",
                "anti-bot challenge",
            )

            brief = collector.conduct_research(
                topic_id="shopify-setup",
                topic_title="How to Set Up a Shopify Store",
                category="Digital Business Tools",
                target_url="https://help.shopify.com",
                dry_run=False,
            )

            # Verification should succeed via Tavily extracted content!
            verified_sources = brief.verified_sources()
            self.assertTrue(len(verified_sources) >= 1)
            self.assertTrue(verified_sources[0].verified)
            self.assertTrue(verified_sources[0].content_extraction_success)

    def test_substring_routing_removed_unrelated_topics_not_assigned_notion_or_shopify(self):
        """Unrelated topics containing substrings like 'email' or 'daily' must not be routed to Notion/Shopify."""
        collector = ResearchCollector(request_timeout=5)
        with patch.object(collector, "_search_tavily") as mock_search, \
             patch.object(collector, "verify_and_fetch_source") as mock_fetch:

            mock_search.return_value = []
            mock_fetch.return_value = (True, 200, "Example Docs", "Example content", "https://example.com/daily", None)

            # Topic contains 'ai' inside 'email' and 'daily'
            brief = collector.conduct_research(
                topic_id="daily-email",
                topic_title="Setting Up Daily Email Newsletters",
                category="Digital Marketing",
                target_url="https://example.com/daily",
                dry_run=False,
            )

            # Sources must NOT include notion.so or shopify.com or ai.google.dev
            urls = [s.url for s in brief.sources]
            self.assertFalse(any("notion.so" in u for u in urls))
            self.assertFalse(any("shopify.com" in u for u in urls))
            self.assertFalse(any("ai.google.dev" in u for u in urls))

    def test_domain_allowlist_and_blocklist_filtering(self):
        """Allowed and blocked domain lists must filter candidate URLs."""
        # 1. Allowlist restricts to permitted domains only
        collector_allow = ResearchCollector(domain_allowlist=["trusted.org", "docs.google.com"])
        self.assertTrue(collector_allow._is_domain_allowed("https://trusted.org/help"))
        self.assertTrue(collector_allow._is_domain_allowed("https://sub.trusted.org/help"))
        self.assertFalse(collector_allow._is_domain_allowed("https://untrusted.com/page"))

        # 2. Blocklist rejects blacklisted domains
        collector_block = ResearchCollector(domain_blocklist=["spam.com", "sketchy-affiliate.net"])
        self.assertFalse(collector_block._is_domain_allowed("https://spam.com/promo"))
        self.assertFalse(collector_block._is_domain_allowed("https://blog.sketchy-affiliate.net/link"))
        self.assertTrue(collector_block._is_domain_allowed("https://trusted.org/help"))

    def test_tavily_fallback_does_not_verify_unsupported_snippet_over_200_chars(self):
        """A Tavily fallback snippet > 200 characters with completely unsupported claims must NOT be verified."""
        collector = ResearchCollector(tavily_api_key="tvly-mock-key")
        with patch.object(collector, "_search_tavily") as mock_search, \
             patch.object(collector, "verify_and_fetch_source") as mock_fetch:

            # Long snippet (> 200 chars), but completely unrelated content
            long_unrelated_snippet = (
                "Baking sourdough bread requires flour, filtered water, ambient yeast culture, and exact fermentation times. "
                "Ensure your Dutch oven is preheated to 450 degrees Fahrenheit. Score the dough with a sharp baker's lame before placing it in the oven."
            )
            mock_search.return_value = [{
                "title": "Baking Sourdough Guide",
                "url": "https://example.com/sourdough",
                "content": long_unrelated_snippet,
                "raw_content": long_unrelated_snippet,
            }]

            # Direct fetch fails (e.g. 403 bot check)
            mock_fetch.return_value = (False, 403, "Access Denied", "", "https://example.com/sourdough", "Forbidden")

            brief = collector.conduct_research(
                topic_id="notion-db",
                topic_title="How to Build Relational Databases in Notion",
                category="Productivity",
                target_url="https://example.com/sourdough",
                configured_sources=[{
                    "title": "Baking Sourdough Guide",
                    "url": "https://example.com/sourdough",
                    "claims": ["Relational databases in Notion workspaces", "Rollup formulas and relation properties"],
                }],
                dry_run=False,
            )

            source = brief.sources[0]
            # Must NOT be marked verified despite snippet length > 200 chars!
            self.assertFalse(source.verified)
            self.assertEqual(len(source.verified_claims), 0)

    def test_hardcoded_upwork_fact_removed_from_brief(self):
        """Brief key_facts must never contain hardcoded unretrieved facts like Upwork fee October 2026."""
        collector = ResearchCollector()
        brief = collector.conduct_research(
            topic_id="upwork-test",
            topic_title="How to Get Started on Upwork",
            category="Freelancing",
            target_url="https://support.upwork.com",
            dry_run=True,
        )

        for fact in brief.key_facts:
            self.assertNotIn("verified October 2026 via official Upwork Help Center", fact)
            self.assertNotIn("flat 10% freelancer fee", fact)

    def test_cleaned_text_and_untrusted_delimiters_in_prompt(self):
        """Research brief format_for_prompt must delimit external text as untrusted data."""
        brief = ResearchBrief(topic_id="test", topic_title="Test Topic", target_url="https://example.com")
        brief.sources = [
            SourceCitation(
                title="Example Official Docs",
                url="https://example.com/docs",
                retrieval_date="November 2026",
                verified=True,
                verified_claims=["Automated webhook delivery"],
                cleaned_text="Webhooks send real-time JSON payloads to configured HTTP endpoints upon status changes.",
            )
        ]

        prompt_text = brief.format_for_prompt()
        self.assertIn("<<<START UNTRUSTED SOURCE TEXT>>>", prompt_text)
        self.assertIn("<<<END UNTRUSTED SOURCE TEXT>>>", prompt_text)
        self.assertIn("UNTRUSTED external data", prompt_text)
        self.assertIn("Do NOT fabricate or extrapolate exact pricing", prompt_text)
        self.assertIn("Webhooks send real-time JSON payloads", prompt_text)


if __name__ == "__main__":
    unittest.main()

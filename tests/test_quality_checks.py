"""Unit tests for the hard quality gate checks, plain-English style, and safety rules."""

import unittest
from src.article_writer import ArticleDraft, ArticleWriter
from src.quality_checks import QualityGate, validate_final_blogger_html
from src.screenshot_capture import ScreenshotResult


class TestQualityChecks(unittest.TestCase):
    """Test suite for quality gate validation rules."""

    def setUp(self):
        self.gate = QualityGate(min_word_count=800, min_sources=2, is_live_mode=False)
        self.live_gate = QualityGate(min_word_count=800, min_sources=2, is_live_mode=True)

    def _create_valid_draft(self) -> ArticleDraft:
        """Helper generating a compliant draft in plain English."""
        words_block = " ".join(["Each step is short and easy to follow."] * 140)  # ~980 words of plain sentences
        html = f"""<div class="article-body">
<h2>Setting Up Your Remote Work Schedule</h2>
<p>This guide explains practical methods for independent contractors. {words_block}</p>
<h3>Step 1: Setup and Verification</h3>
<p>Follow official setup instructions carefully to ensure clean configuration.</p>
<h3>Step 2: Execution and Review</h3>
<p>Perform structured audits across all deliverables before final signoff.</p>
</div>"""

        sources = [
            {"title": "Official Google Documentation", "url": "https://ai.google.dev/docs"},
            {"title": "W3C Web Standards", "url": "https://www.w3.org/"},
        ]
        html_with_sources = ArticleWriter.append_sources_section(html, sources)

        return ArticleDraft(
            topic_id="test-topic-1",
            title="Practical Guide to Freelance Copy Editing",
            meta_description="A clear, step-by-step walkthrough detailing copy editing workflows for freelance editors.",
            labels=["AI Tools", "Freelancing", "Productivity"],
            html_content=html_with_sources,
            summary="A clear walkthrough detailing copy editing workflows.",
            sources_used=sources,
            primary_intent="Tutorial",
            word_count=850,
            last_checked_date="October 2026",
            is_dry_run_fixture=False,
            affiliate_disclosure_required=False,
            screenshot_needed=False,
        )

    def test_live_gate_does_not_require_exact_source_quotes(self):
        """Original articles must not need sentence-by-sentence copied-source quote mappings."""
        draft = self._create_valid_draft()
        report = self.live_gate.run_all_checks(
            draft,
            verified_source_urls={"https://ai.google.dev/docs", "https://www.w3.org/"},
            check_duplicate=False,
        )
        self.assertTrue(report.passed, f"Unexpected source-quote blocker: {report.failures}")

    def test_valid_draft_passes_gate(self):
        """Test that a compliant article passes all quality checks."""
        draft = self._create_valid_draft()
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, f"Expected pass, got failures: {report.failures}")
        self.assertEqual(len(report.failures), 0)

    def test_ai_cliche_is_a_warning_not_a_publication_blocker(self):
        """Generic AI phrasing should be flagged for editing without blocking a useful draft."""
        draft = self._create_valid_draft()
        draft.html_content = "<p>In today's fast-paced digital world, let us delve into the depths of freelancing.</p>" + draft.html_content
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, report.failures)
        self.assertTrue(any("Writing style advisory" in warning for warning in report.warnings))

    def test_local_screenshot_path_fails_html_check(self):
        """Test that runner-local screenshot paths leaked into HTML are rejected."""
        draft = self._create_valid_draft()
        draft.html_content += '<img src="output/screenshots/captured_123.png" alt="local screenshot" />'
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("Runner-local path" in f for f in report.failures))

    def test_dry_run_fixture_rejected_in_live_mode(self):
        """Test that dry-run test fixtures can NEVER pass live-mode gates."""
        draft = self._create_valid_draft()
        draft.is_dry_run_fixture = True
        report = self.live_gate.run_all_checks(
            draft, check_duplicate=False
        )
        self.assertFalse(report.passed)
        self.assertTrue(any("Live Guard failed: Dry-run test fixture cannot be published" in f for f in report.failures))

    def test_thin_content_below_safety_floor_fails_length_check(self):
        """Only genuinely thin articles below the 450-word safety floor are blocked."""
        draft = self._create_valid_draft()
        draft.html_content = "<h2>Short Article</h2><p>This is far too brief to be useful.</p>"
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("450-word minimum" in f for f in report.failures))

    def test_concise_complete_article_above_safety_floor_can_pass(self):
        """A 500+ word useful article may proceed with a length advisory."""
        draft = self._create_valid_draft()
        body = "<h2>Practical Steps</h2><p>" + "Useful guidance helps readers complete practical tasks. " * 90 + "</p>"
        draft.html_content = ArticleWriter.append_sources_section(
            body, draft.sources_used
        )
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, report.failures)
        self.assertTrue(any("Length advisory" in warning for warning in report.warnings))

    def test_article_without_source_links_can_pass(self):
        """An original article is not blocked when no external citations are needed."""
        draft = self._create_valid_draft()
        draft.sources_used = []
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, f"An uncited original article should pass: {report.failures}")

    def test_one_optional_source_does_not_fail_source_count_gate(self):
        """An article may include one useful source; no minimum source quota applies."""
        draft = self._create_valid_draft()
        draft.sources_used = [{"title": "Only One Source", "url": "https://example.com"}]
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, f"Optional sources should not block a draft: {report.failures}")

    def test_optional_citation_still_must_be_verified_in_live_mode(self):
        """A citation is optional, but a supplied citation must match a verified source."""
        draft = self._create_valid_draft()
        verified_urls = {"https://ai.google.dev/docs"}  # W3C was not verified
        report = self.live_gate.run_all_checks(
            draft, verified_source_urls=verified_urls,
            check_duplicate=False
        )
        self.assertFalse(report.passed)
        self.assertTrue(any("was not verified" in f for f in report.failures))

    def test_prohibited_guarantee_fails(self):
        """Test that banned earning guarantees fail immediately."""
        draft = self._create_valid_draft()
        draft.html_content += "<p>Follow this method to earn guaranteed income of $500 per day!</p>"
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("Policy check failed" in f for f in report.failures))

    def test_markdown_leak_fails_html_check(self):
        """Test that unrendered markdown headers or links fail HTML checks."""
        draft = self._create_valid_draft()
        draft.html_content += "\n### Unrendered Markdown Header\n<p>Some text</p>"
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("Markdown headers" in f for f in report.failures))

    def test_normalize_url_variations(self):
        """URL normalization must handle protocol, www prefix, case, and trailing slashes."""
        from src.quality_checks import normalize_url

        self.assertEqual(normalize_url("https://www.notion.so/help/"), "notion.so/help")
        self.assertEqual(normalize_url("http://notion.so/help"), "notion.so/help")
        self.assertEqual(normalize_url("https://ai.google.dev/"), "ai.google.dev")
        self.assertEqual(normalize_url("http://WWW.AI.GOOGLE.DEV"), "ai.google.dev")
        self.assertEqual(
            normalize_url("https://support.upwork.com/hc/en-us/articles/123/"),
            "support.upwork.com/hc/en-us/articles/123",
        )

    def test_qa_fails_if_sources_used_are_not_linked_in_body(self):
        """QA gate must fail if sources listed in sources_used are not linked with href in HTML body."""
        draft = self._create_valid_draft()
        # Remove the article-sources section so links are missing
        draft.html_content = (
            '<div class="article-body"><h2>Overview</h2>'
            '<p>' + ' '.join(["word"] * 850) + '</p></div>'
        )
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("is not linked in the article body" in f for f in report.failures))

    def test_qa_normalizes_urls_when_matching_verified_sources(self):
        """Optional citations must match verified URLs despite protocol, www, or trailing-slash differences."""
        draft = self._create_valid_draft()
        # Verified URL has https and trailing slash, draft cited source has http without trailing slash
        verified_urls = {
            "https://www.ai.google.dev/docs/",
            "http://w3.org/",
        }
        report = self.live_gate.run_all_checks(
            draft,
            verified_source_urls=verified_urls,
            check_duplicate=False,
        )
        self.assertTrue(report.passed, f"Expected pass with normalized URLs, got: {report.failures}")

    def test_append_sources_section_creates_visible_html_links(self):
        """ArticleWriter.append_sources_section must append visible HTML with valid links."""
        raw_html = "<div><h2>Title</h2><p>Article body content.</p></div>"
        sources = [
            {"title": "Notion Help", "url": "https://notion.so/help"},
            {"title": "Shopify Guide", "url": "https://help.shopify.com"},
        ]
        result = ArticleWriter.append_sources_section(raw_html, sources)
        self.assertIn('<div class="article-sources"', result)
        self.assertIn("Sources &amp; References", result)
        self.assertIn('href="https://notion.so/help"', result)
        self.assertIn('href="https://help.shopify.com"', result)
        self.assertIn('target="_blank"', result)
        self.assertIn('rel="noopener noreferrer"', result)


    def test_seo_metadata_lengths_are_advisory_not_hard_blocks(self):
        draft = self._create_valid_draft()
        draft.title = "Useful digital guide"
        draft.meta_description = "A short but valid description that explains the article topic clearly."
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, report.failures)
        self.assertTrue(any("SEO title advisory" in warning for warning in report.warnings))
        self.assertTrue(any("SEO description advisory" in warning for warning in report.warnings))
        self.assertEqual(report.metrics["seo_title_characters"], len("Useful digital guide"))
        self.assertEqual(report.metrics["seo_description_characters"], len("A short but valid description that explains the article topic clearly."))

    def test_preferred_word_count_is_warning_not_hard_block(self):
        """A useful article below the preferred target should pass with an advisory."""
        draft = self._create_valid_draft()
        gate = QualityGate(min_word_count=2000, min_sources=2, is_live_mode=False)
        report = gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, report.failures)
        self.assertTrue(any("Length advisory" in warning for warning in report.warnings))


class TestFinalBloggerHTMLValidation(unittest.TestCase):
    def _valid_html(self):
        return '''<script type="application/ld+json">{"@type":"BlogPosting","headline":"A valid article title","description":"A valid article description."}</script>
        <div class="dt-article-body"><h2 id="overview">Overview</h2>
        <p>Article content.</p><img src="https://cdn.example/image.jpg" alt="Product settings screen" />
        <a href="https://example.com/docs" target="_blank" rel="noopener noreferrer">Official docs</a>
        <h2>Sources &amp; References</h2><p>Sources listed here.</p></div>'''

    def test_valid_final_fragment_passes(self):
        self.assertEqual(validate_final_blogger_html(self._valid_html()), [])

    def test_missing_blogposting_schema_fails(self):
        bad = self._valid_html().replace(
            '<script type="application/ld+json">{"@type":"BlogPosting","headline":"A valid article title","description":"A valid article description."}</script>',
            "",
        )
        self.assertTrue(any("BlogPosting structured data is missing" in item for item in validate_final_blogger_html(bad)))

    def test_invalid_blogposting_schema_fails(self):
        bad = self._valid_html().replace(
            '{"@type":"BlogPosting","headline":"A valid article title","description":"A valid article description."}',
            '{"@type":"TechArticle"}',
        )
        self.assertTrue(any("Google-supported BlogPosting type" in item for item in validate_final_blogger_html(bad)))

    def test_sources_section_is_optional_in_final_html(self):
        failures = validate_final_blogger_html(self._valid_html().replace("Sources &amp; References", "Further reading"))
        self.assertEqual(failures, [])

    def test_local_or_non_https_image_fails(self):
        bad = self._valid_html().replace("https://cdn.example/image.jpg", "output/featured/cover.png")
        self.assertTrue(any("public HTTPS" in item for item in validate_final_blogger_html(bad)))

    def test_missing_alt_text_fails(self):
        bad = self._valid_html().replace('alt="Product settings screen"', 'alt=""')
        self.assertTrue(any("alt text" in item for item in validate_final_blogger_html(bad)))

    def test_duplicate_ids_fail(self):
        bad = self._valid_html().replace('<h2>Sources', '<h2 id="overview">Sources')
        self.assertTrue(any("duplicate element IDs" in item for item in validate_final_blogger_html(bad)))

    def test_unsafe_link_scheme_fails(self):
        bad = self._valid_html().replace('href="https://example.com/docs"', 'href="javascript:alert(1)"')
        self.assertTrue(any("unsafe or unsupported link" in item for item in validate_final_blogger_html(bad)))

    def test_new_tab_link_requires_safe_rel_attributes(self):
        bad = self._valid_html().replace('rel="noopener noreferrer"', 'rel="nofollow"')
        self.assertTrue(any("external-link protections" in item for item in validate_final_blogger_html(bad)))

    def test_empty_document_fails(self):
        self.assertTrue(validate_final_blogger_html(""))


if __name__ == "__main__":
    unittest.main()

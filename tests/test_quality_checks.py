"""Unit tests for the hard quality gate checks, plain-English style, and safety rules."""

import unittest
from src.article_writer import ArticleDraft
from src.quality_checks import QualityGate
from src.screenshot_capture import ScreenshotResult


class TestQualityChecks(unittest.TestCase):
    """Test suite for quality gate validation rules."""

    def setUp(self):
        self.gate = QualityGate(min_word_count=800, min_sources=2, is_live_mode=False)
        self.live_gate = QualityGate(min_word_count=800, min_sources=2, is_live_mode=True)

    def _create_valid_draft(self) -> ArticleDraft:
        """Helper generating a compliant draft in plain English."""
        words_block = " ".join(["practical workflow implementation detail"] * 240)  # ~960 words
        html = f"""<div class="article-body">
<h2>Setting Up Your Remote Work Schedule</h2>
<p>This guide explains practical methods for independent contractors. {words_block}</p>
<h3>Step 1: Setup and Verification</h3>
<p>Follow official setup instructions carefully to ensure clean configuration.</p>
<h3>Step 2: Execution and Review</h3>
<p>Perform structured audits across all deliverables before final signoff.</p>
</div>"""

        return ArticleDraft(
            topic_id="test-topic-1",
            title="Practical Guide to Freelance Copy Editing",
            meta_description="A clear, step-by-step walkthrough detailing copy editing workflows for freelance editors.",
            labels=["AI Tools", "Freelancing", "Productivity"],
            html_content=html,
            summary="A clear walkthrough detailing copy editing workflows.",
            sources_used=[
                {"title": "Official Google Documentation", "url": "https://ai.google.dev/docs"},
                {"title": "W3C Web Standards", "url": "https://www.w3.org/"},
            ],
            primary_intent="Tutorial",
            word_count=850,
            last_checked_date="October 2026",
            is_dry_run_fixture=False,
            affiliate_disclosure_required=False,
            screenshot_needed=False,
        )

    def test_valid_draft_passes_gate(self):
        """Test that a compliant article passes all quality checks."""
        draft = self._create_valid_draft()
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertTrue(report.passed, f"Expected pass, got failures: {report.failures}")
        self.assertEqual(len(report.failures), 0)

    def test_ai_cliche_fails_style_check(self):
        """Test that generic AI cliches fail the plain-English style gate."""
        draft = self._create_valid_draft()
        draft.html_content = "<p>In today's fast-paced digital world, let us delve into the depths of freelancing.</p>" + draft.html_content
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("Generic AI cliché detected" in f for f in report.failures))

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
        report = self.live_gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("Live Guard failed: Dry-run test fixture cannot be published" in f for f in report.failures))

    def test_thin_content_fails_length_check(self):
        """Test that articles below word count threshold fail."""
        draft = self._create_valid_draft()
        draft.html_content = "<h2>Short Article</h2><p>This is far too brief to be useful.</p>"
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("minimum threshold" in f for f in report.failures))

    def test_insufficient_sources_fails(self):
        """Test that lack of credible sources fails the gate."""
        draft = self._create_valid_draft()
        draft.sources_used = [{"title": "Only One Source", "url": "https://example.com"}]
        report = self.gate.run_all_checks(draft, check_duplicate=False)
        self.assertFalse(report.passed)
        self.assertTrue(any("Sources check failed" in f for f in report.failures))

    def test_unverified_source_in_live_mode_fails(self):
        """Test that citing an unverified source fails in live mode."""
        draft = self._create_valid_draft()
        verified_urls = {"https://ai.google.dev/docs"}  # W3C was not verified
        report = self.live_gate.run_all_checks(draft, verified_source_urls=verified_urls, check_duplicate=False)
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


if __name__ == "__main__":
    unittest.main()

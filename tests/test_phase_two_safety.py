"""Phase 2 regression tests for draft-only publishing and report diagnostics."""

import tempfile
import unittest
from pathlib import Path

from src.blogger_client import BloggerClient
from src.config import AppConfig
from src.report import PipelineReporter


class TestDraftOnlySafety(unittest.TestCase):
    def test_public_mode_is_rejected_even_with_confirmation(self):
        config = AppConfig(publish_mode="publish", confirm_live_publish=True)
        errors = config.validate_for_mode(stage="all")
        self.assertTrue(any("public Blogger publishing is disabled" in item for item in errors))

    def test_blogger_client_refuses_public_post_request(self):
        client = BloggerClient(blog_id="123")
        result = client.insert_post(
            title="Safety test",
            html_content="<p>Test</p>",
            labels=[],
            is_draft=False,
            dry_run=True,
        )
        self.assertFalse(result.success)
        self.assertTrue(result.is_draft)
        self.assertIn("Public Blogger publishing is disabled", result.error_message)

    def test_blogger_client_dry_run_remains_a_draft(self):
        client = BloggerClient(blog_id="123")
        result = client.insert_post(
            title="Draft test",
            html_content="<p>Test</p>",
            labels=[],
            is_draft=True,
            dry_run=True,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.is_draft)


class TestDiagnosticsReporting(unittest.TestCase):
    def test_accessibility_and_visual_diagnostics_are_saved_and_summarized(self):
        with tempfile.TemporaryDirectory() as tmp:
            reporter = PipelineReporter(output_dir=tmp)
            reporter.accessibility_report = {
                "available": True,
                "target": "final article HTML in isolated browser document",
                "violations": [
                    {"id": "image-alt", "impact": "critical", "help": "Images must have alternate text", "nodes": 2}
                ],
                "passes": 18,
                "incomplete": 1,
                "error": None,
            }
            reporter.visual_assets = {"featured_image": "hosted", "mermaid_diagrams": "1 hosted; 1 rendered"}
            report = reporter.finalize(success=True)
            summary = (Path(tmp) / "summary.md").read_text(encoding="utf-8")

        self.assertEqual(len(report["accessibility"]["violations"]), 1)
        self.assertEqual(report["metrics"]["visual_assets"]["featured_image"], "hosted")
        self.assertIn("Accessibility Diagnostics", summary)
        self.assertIn("image-alt", summary)
        self.assertIn("Visual Asset Outcomes", summary)
        self.assertIn("Featured image", summary)


if __name__ == "__main__":
    unittest.main()

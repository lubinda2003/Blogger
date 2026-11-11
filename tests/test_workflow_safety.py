"""Regression tests for safe defaults in the GitHub content workflow."""

from pathlib import Path
import unittest


class TestWorkflowSafety(unittest.TestCase):
    def test_content_workflow_defaults_to_dry_run_and_draft(self):
        workflow = Path(".github/workflows/content-pipeline.yml").read_text(encoding="utf-8")
        self.assertIn("DRY_RUN: 'true'", workflow)
        self.assertIn("PUBLISH_MODE: draft", workflow)
        self.assertIn("CONFIRM_LIVE_PUBLISH: false", workflow)
        self.assertIn("TOPIC_ID: ''", workflow)
        self.assertNotIn("SCHEDULED_LIVE", workflow)


if __name__ == "__main__":
    unittest.main()

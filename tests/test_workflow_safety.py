"""Regression tests for safe defaults in the GitHub content workflow."""

from pathlib import Path
import unittest


class TestWorkflowSafety(unittest.TestCase):
    def test_content_workflow_runs_real_generation_but_only_creates_drafts(self):
        workflow = Path(".github/workflows/content-pipeline.yml").read_text(encoding="utf-8")
        self.assertIn("DRY_RUN: 'false'", workflow)
        self.assertIn("PUBLISH_MODE: draft", workflow)
        self.assertIn("CONFIRM_LIVE_PUBLISH: false", workflow)
        self.assertIn("TOPIC_ID: ''", workflow)
        self.assertNotIn("SCHEDULED_LIVE", workflow)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the quality metrics retained in pipeline run reports."""

import tempfile
import unittest
from pathlib import Path

from src.report import PipelineReporter


class TestPipelineReporterQualityMetrics(unittest.TestCase):
    def test_qa_metrics_and_warnings_are_saved_and_shown_in_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            reporter = PipelineReporter(output_dir=tmp)
            reporter.qa_passed = True
            reporter.qa_metrics = {
                "word_count": 1240,
                "sources_count": 3,
                "screenshot_captured": True,
                "has_public_screenshot": False,
            }
            reporter.qa_warnings = ["Readability is close to the configured limit."]

            report = reporter.finalize(success=True)
            summary = (Path(tmp) / "summary.md").read_text(encoding="utf-8")

        self.assertEqual(report["qa"]["metrics"]["word_count"], 1240)
        self.assertEqual(report["qa"]["metrics"]["sources_count"], 3)
        self.assertIn("### 📊 Quality Check Metrics", summary)
        self.assertIn("**Word count:** 1240", summary)
        self.assertIn("**Has public screenshot:** No", summary)
        self.assertIn("### ⚠️ QA Warnings", summary)
        self.assertIn("Readability is close to the configured limit.", summary)


if __name__ == "__main__":
    unittest.main()

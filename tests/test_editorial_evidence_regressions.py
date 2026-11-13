"""Regression tests for editorial evidence matching and complete source references."""

import unittest

from src.article_writer import ArticleWriter
from src.quality_checks import claim_is_represented_in_article
from src.state_store import merge_state_snapshots


class TestEditorialEvidenceRegressions(unittest.TestCase):
    def test_paraphrased_claim_is_accepted_when_key_terms_are_preserved(self):
        self.assertTrue(claim_is_represented_in_article(
            "The platform lets freelancers create invoices and track unpaid payments.",
            "Freelancers can make invoices and monitor unpaid payments with the platform.",
        ))

    def test_unrelated_article_text_does_not_support_claim(self):
        self.assertFalse(claim_is_represented_in_article(
            "The platform lets freelancers create invoices and track unpaid payments.",
            "This software helps teams plan projects, manage calendars, and share files.",
        ))

    def test_numeric_claim_requires_same_values(self):
        self.assertFalse(claim_is_represented_in_article(
            "The plan includes 10 invoices each month for freelancers.",
            "Freelancers receive 100 invoices each month on this plan.",
        ))

    def test_negation_must_be_preserved(self):
        self.assertFalse(claim_is_represented_in_article(
            "The free plan does not include team billing.",
            "The free plan includes team billing.",
        ))

    def test_missing_sources_are_added_to_existing_empty_references_heading(self):
        body = "<h2>Overview</h2><p>Useful article text.</p><h3>Sources &amp; References</h3>"
        result = ArticleWriter.append_sources_section(body, [
            {"title": "Official Guide", "url": "https://example.com/guide"}
        ])
        self.assertIn('href="https://example.com/guide"', result)
        self.assertEqual(result.count("Sources &amp; References"), 1)

    def test_missing_sources_are_added_to_existing_references_list_without_duplicates(self):
        body = (
            '<h3>Sources &amp; References</h3><ul>'
            '<li><a href="https://example.com/one">One</a></li></ul>'
        )
        result = ArticleWriter.append_sources_section(body, [
            {"title": "One", "url": "https://example.com/one"},
            {"title": "Two", "url": "https://example.com/two"},
        ])
        self.assertEqual(result.count("https://example.com/one"), 1)
        self.assertEqual(result.count("https://example.com/two"), 1)

    def test_state_merge_preserves_both_concurrent_failure_increments(self):
        base = {"failed_attempts": {"topic-a": 2}, "processed": [], "total_runs": 0}
        local = {"failed_attempts": {"topic-a": 3}, "processed": [], "total_runs": 0}
        remote = {"failed_attempts": {"topic-a": 3}, "processed": [], "total_runs": 0}
        merged = merge_state_snapshots(base, local, remote)
        self.assertEqual(merged["failed_attempts"]["topic-a"], 4)

    def test_state_merge_keeps_successful_posts_from_both_attempts(self):
        base = {"failed_attempts": {}, "processed": [], "total_runs": 0}
        local = {"failed_attempts": {}, "processed": [
            {"topic_id": "a", "timestamp": "2026-11-13T10:00:00+00:00"}
        ]}
        remote = {"failed_attempts": {}, "processed": [
            {"topic_id": "b", "timestamp": "2026-11-13T10:01:00+00:00"}
        ]}
        merged = merge_state_snapshots(base, local, remote)
        self.assertEqual({item["topic_id"] for item in merged["processed"]}, {"a", "b"})
        self.assertEqual(merged["total_runs"], 2)


if __name__ == "__main__":
    unittest.main()

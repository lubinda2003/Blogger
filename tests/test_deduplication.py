"""Unit tests for topic deduplication and persistent state across separate workflow runs."""

import json
import tempfile
import unittest
from pathlib import Path

from src.state_store import StateStore, normalize_fingerprint


class TestDeduplication(unittest.TestCase):
    """Test suite for topic deduplication and idempotency controls."""

    def test_fingerprint_normalization_matches_reordered_words(self):
        """Reordered query variations should produce identical fingerprints."""
        fp1 = normalize_fingerprint("How to Use Google Gemini for Copy Editing")
        fp2 = normalize_fingerprint("Copy Editing with Google Gemini: A Guide")
        self.assertEqual(fp1, fp2)

    def test_fingerprint_ignores_stop_words_and_case(self):
        """Stop words and casing should not produce duplicate articles."""
        fp1 = normalize_fingerprint("upwork setup in zambia")
        fp2 = normalize_fingerprint("UPWORK SETUP FOR ZAMBIA - A Step-by-Step Tutorial")
        self.assertEqual(fp1, fp2)

    def test_state_store_records_and_detects_duplicates(self):
        """StateStore should correctly detect already processed topic IDs and fingerprints."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "test_processed.json"
            store = StateStore(str(state_file))

            # Initially not duplicate
            self.assertFalse(store.is_duplicate("topic-1", "Mastering Upwork Payments in Zambia"))

            # Record success
            store.record_success(
                topic_id="topic-1",
                topic_title="Mastering Upwork Payments in Zambia",
                post_id="blogger-12345",
                post_url="https://example.blogger.com/b/post/12345",
            )

            # Now should be detected as duplicate by ID
            self.assertTrue(store.is_duplicate("topic-1", "Mastering Upwork Payments in Zambia"))

            # And detected as duplicate by normalized title even with different ID
            self.assertTrue(store.is_duplicate("topic-2", "Guide to Upwork Payments in Zambia"))

    def test_topic_history_survives_separate_workflow_runs(self):
        """Simulate separate GitHub Actions workflow runs restoring state from disk/cache."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "processed_topics.json"

            # Workflow Run 1: Initializes state and processes topic 1
            run1_store = StateStore(str(state_file))
            run1_store.record_success(
                topic_id="ai-gemini-editing",
                topic_title="How to Use Google Gemini for Copy Editing",
                post_id="post-run1-9988",
                post_url="https://test.blogger.com/9988",
            )

            # Workflow Run 1 completes. File persists in runner cache / repository state.
            self.assertTrue(state_file.exists())

            # Workflow Run 2: Fresh process starts and loads the restored state file
            run2_store = StateStore(str(state_file))

            # Proves topic 1 is detected as already processed and skipped in Run 2
            self.assertTrue(run2_store.is_duplicate("ai-gemini-editing", "How to Use Google Gemini for Copy Editing"))
            self.assertTrue(run2_store.is_duplicate("ai-gemini-editing-2", "Copy Editing with Google Gemini"))

            # Run 2 processes topic 2
            run2_store.record_success(
                topic_id="upwork-zambia-kyc",
                topic_title="Upwork Account Setup and KYC in Zambia",
                post_id="post-run2-1122",
                post_url="https://test.blogger.com/1122",
            )

            # Verify total history contains both runs
            history = run2_store.list_history()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["topic_id"], "ai-gemini-editing")
            self.assertEqual(history[1]["topic_id"], "upwork-zambia-kyc")


if __name__ == "__main__":
    unittest.main()

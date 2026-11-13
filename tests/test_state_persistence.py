"""Unit tests for repository-based topic history persistence, deduplication, and failure handling."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import AppConfig, load_config
from src.main import run_pipeline
from src.state_store import StateStore, normalize_fingerprint


class TestStatePersistence(unittest.TestCase):
    """Test suite verifying repository-first topic persistence without Cloudflare dependencies."""

    def test_draft_only_and_dry_run_defaults_intact(self):
        """Default configuration must strictly enforce dry_run=True and publish_mode='draft'."""
        config = AppConfig()
        self.assertTrue(config.dry_run, "dry_run must default to True for safety")
        self.assertEqual(config.publish_mode, "draft", "publish_mode must default to 'draft'")

        # Check code defaults independently of workflow-level environment overrides.
        # GitHub Actions may set DRY_RUN=false for an explicitly requested live draft run.
        with patch.dict(os.environ, {}, clear=True):
            loaded = load_config()
        self.assertTrue(loaded.dry_run)
        self.assertEqual(loaded.publish_mode, "draft")

        # Safety guard: live publishing requires CONFIRM_LIVE_PUBLISH='true'
        unsafe_config = AppConfig(dry_run=False, publish_mode="publish")
        errors = unsafe_config.validate_for_mode()
        self.assertTrue(any("public Blogger publishing is disabled" in err for err in errors))

    def test_duplicate_prevention_by_id_and_fingerprint(self):
        """StateStore must prevent duplicates by topic ID and semantic title fingerprint."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "processed_topics.json"
            store = StateStore(str(state_file))

            # Initially not duplicate
            self.assertFalse(store.is_duplicate("topic-1", "Mastering Upwork Payments in Zambia"))

            # Record success
            store.record_success(
                topic_id="topic-1",
                topic_title="Mastering Upwork Payments in Zambia",
                post_id="post-1001",
                post_url="https://digitaltoolkitguide.blogspot.com/post1001",
                mode="draft",
            )

            # Duplicate by topic ID
            self.assertTrue(store.is_duplicate("topic-1", "Completely Different Title"))

            # Duplicate by normalized title (ignoring case, stop words, order)
            self.assertTrue(store.is_duplicate("topic-2", "A Complete Guide to Upwork Payments in Zambia"))
            self.assertTrue(store.is_duplicate("topic-3", "UPWORK PAYMENTS IN ZAMBIA: MASTERING GUIDE"))

            # Unrelated topic is not duplicate
            self.assertFalse(store.is_duplicate("topic-4", "Notion vs Obsidian for Students"))

    def test_topic_history_persists_in_json_between_runs(self):
        """Simulate separate GitHub Actions runs reading and updating data/processed_topics.json."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "processed_topics.json"

            # Workflow Run 1: Initializes repository state and processes topic 1
            run1_store = StateStore(str(state_file))
            run1_store.record_success(
                topic_id="ai-gemini-editing",
                topic_title="How to Use Google Gemini for Copy Editing",
                post_id="post-run1-9988",
                post_url="https://digitaltoolkitguide.blogspot.com/9988",
            )

            # Run 1 commits and pushes to repository. File exists on disk.
            self.assertTrue(state_file.exists())

            # Workflow Run 2: Next runner checks out repository and loads existing state file
            run2_store = StateStore(str(state_file))

            # Run 2 immediately detects topic 1 as duplicate
            self.assertTrue(run2_store.is_duplicate("ai-gemini-editing", "How to Use Google Gemini for Copy Editing"))

            # Run 2 processes topic 2
            run2_store.record_success(
                topic_id="notion-project-management",
                topic_title="How to Manage Projects with Notion",
                post_id="post-run2-1122",
                post_url="https://digitaltoolkitguide.blogspot.com/1122",
            )

            # Verify total history contains both runs in sequence
            history = run2_store.list_history()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["topic_id"], "ai-gemini-editing")
            self.assertEqual(history[1]["topic_id"], "notion-project-management")

    def test_failure_handling_when_persistence_file_unwritable(self):
        """StateStore must fail loudly and NEVER silently fall back to ephemeral in-memory state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "processed_topics.json"
            store = StateStore(str(state_file))

            # Simulate unwritable repository/filesystem permissions (e.g. read-only filesystem, Git permission denied)
            with patch("builtins.open", side_effect=PermissionError("Permission denied: data/processed_topics.json")):
                # verify_persistence must raise RuntimeError
                with self.assertRaises(RuntimeError) as ctx:
                    store.verify_persistence()
                self.assertIn("State persistence verification failed", str(ctx.exception))

                # record_success must also raise RuntimeError and not silently succeed
                with self.assertRaises(RuntimeError) as ctx:
                    store.record_success(topic_id="t1", topic_title="Title 1")
                self.assertIn("State store", str(ctx.exception))

    def test_pipeline_halts_if_state_persistence_unwritable(self):
        """Pipeline must fail closed (exit code 1) when repository state cannot be verified."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            unwritable_state_path = Path(tmp_dir) / "readonly_state.json"
            unwritable_state_path.write_text('{"processed": []}', encoding="utf-8")

            config = AppConfig(
                dry_run=True,
                publish_mode="draft",
                processed_json_path=str(unwritable_state_path),
            )

            # Simulate filesystem permission failure during state store verification
            with patch.object(StateStore, "verify_persistence", side_effect=RuntimeError("Filesystem is read-only")):
                exit_code = run_pipeline(config=config, stage_limit="all")
                self.assertEqual(exit_code, 1, "Pipeline must fail closed when state store is unwritable")

    def test_atomic_write_prevents_file_corruption(self):
        """Writes to processed_topics.json must use an atomic temp file swap."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "processed_topics.json"
            store = StateStore(str(state_file))

            store.record_success(
                topic_id="topic-abc",
                topic_title="Atomic Write Test",
                post_id="post-abc",
            )

            # Temp file must not be left behind
            temp_file = state_file.with_suffix(".tmp")
            self.assertFalse(temp_file.exists(), "Temporary write file must be cleanly swapped")

            # Final file must be valid parseable JSON
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertEqual(len(data["processed"]), 1)
                self.assertEqual(data["processed"][0]["topic_id"], "topic-abc")


if __name__ == "__main__":
    unittest.main()

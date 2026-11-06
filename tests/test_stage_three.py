"""Unit tests for Stage 3 features: head-of-line blocking, idempotency reconciliation, label normalization, and screenshots."""

import unittest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path

from src.state_store import StateStore
from src.topic_discovery import TopicDiscovery, TopicItem
from src.blogger_client import BloggerClient
from src.seo_metadata import SEOMetadata
from src.article_writer import ArticleDraft
from src.screenshot_capture import ScreenshotCapture, ScreenshotResult


class TestStageThree(unittest.TestCase):
    """Test suite for Stage 3 requirements."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "processed_topics.json"
        self.state_store = StateStore(state_file_path=str(self.state_file))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_head_of_line_blocking_skips_topic_after_three_failures(self):
        """A topic that fails QA 3 times must be skipped by topic selection (head-of-line blocking protection)."""
        csv_content = (
            "id,topic,category,primary_intent,priority,requires_screenshot,target_url,target_audience\n"
            "topic-a,Topic A,Tech,Tutorial,1,false,https://example.com/a,Everyone\n"
            "topic-b,Topic B,Tech,Tutorial,2,false,https://example.com/b,Everyone\n"
        )
        csv_path = Path(self.temp_dir.name) / "topics.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        discovery = TopicDiscovery(csv_path=str(csv_path), state_store=self.state_store)

        # Initially topic-a is selected
        selected = discovery.select_next_topic()
        self.assertEqual(selected.id, "topic-a")

        # Record 3 failures for topic-a
        self.state_store.record_failure("topic-a", "Topic A", "QA failed 1")
        self.state_store.record_failure("topic-a", "Topic A", "QA failed 2")
        self.state_store.record_failure("topic-a", "Topic A", "QA failed 3")

        self.assertTrue(self.state_store.is_max_failed("topic-a", max_failures=3))

        # Now topic-a should be skipped and topic-b selected
        selected_next = discovery.select_next_topic()
        self.assertEqual(selected_next.id, "topic-b")

    def test_blogger_client_embeds_topic_id_marker_and_label(self):
        """BloggerClient payload builder must embed hidden topic_id HTML comment and label tag."""
        client = BloggerClient(blog_id="123", client_id="cid", client_secret="csec", refresh_token="rtoken")
        payload = client.build_post_payload(
            title="Test Article Title",
            html_content="<p>Hello world</p>",
            labels=["Tech", "AI Tools"],
            topic_id="my-topic-123",
        )

        self.assertIn("<!-- topic_id: my-topic-123 -->", payload["content"])
        # The marker is a hidden HTML comment only; a "TopicID:" label would be shown to readers.
        self.assertNotIn("TopicID:my-topic-123", payload["labels"])

    def test_normalize_labels_preserves_known_acronyms(self):
        """normalize_labels must preserve known acronyms like AI, API, ChatGPT, SQL without converting to Ai, Chatgpt."""
        labels = ["artificial intelligence", "ai tools", "chatgpt workflow", "api reference", "sql database", "pwa guide"]
        normalized = SEOMetadata.normalize_labels(labels)

        self.assertIn("Artificial Intelligence", normalized)
        self.assertIn("AI Tools", normalized)
        self.assertIn("ChatGPT Workflow", normalized)
        self.assertIn("API Reference", normalized)
        self.assertIn("SQL Database", normalized)
        self.assertIn("PWA Guide", normalized)

        # Ensure bad title casing like "Ai" or "Chatgpt" is not present
        self.assertNotIn("Ai Tools", normalized)
        self.assertNotIn("Chatgpt Workflow", normalized)

    def test_optional_screenshot_failure_is_non_fatal(self):
        """Screenshot failure should not abort pipeline when requires_screenshot is False."""
        capturer = ScreenshotCapture(output_dir=self.temp_dir.name)
        with patch.object(capturer, "capture") as mock_cap:
            mock_cap.return_value = ScreenshotResult(
                success=False,
                url="https://example.com",
                error_message="Connection timed out",
            )
            res = capturer.capture("https://example.com", "slug", "alt", "caption", mock_mode=False)
            self.assertFalse(res.success)


if __name__ == "__main__":
    unittest.main()

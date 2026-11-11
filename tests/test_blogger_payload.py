"""Unit tests for Blogger API payload generation, token masking, and safe reconciliation."""

import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from src.blogger_client import BloggerClient
from src.seo_metadata import SEOMetadata


class TestBloggerPayload(unittest.TestCase):
    """Test suite for Blogger payload structure, token masking, and reconciliation safety."""

    def setUp(self):
        self.client = BloggerClient(
            blog_id="1234567890",
            client_id="dummy-client-id.apps.googleusercontent.com",
            client_secret="dummy-secret-xyz",
            refresh_token="dummy-refresh-token",
        )

    def test_payload_structure_matches_v3_specification(self):
        """Post payload must contain kind, title, content, and labels."""
        payload = self.client.build_post_payload(
            title="How to Use Gemini API",
            html_content="<h2>Hello World</h2><p>Article body.</p>",
            labels=["AI Tools", "Tutorial"],
        )

        self.assertEqual(payload["kind"], "blogger#post")
        self.assertEqual(payload["title"], "How to Use Gemini API")
        self.assertIn("<h2>Hello World</h2>", payload["content"])
        self.assertEqual(payload["labels"], ["AI Tools", "Tutorial"])

    def test_dry_run_returns_draft_success_without_network(self):
        """Dry-run post insertion must return successful draft result without network call."""
        res = self.client.insert_post(
            title="Dry Run Article Test",
            html_content="<p>Test content</p>",
            labels=["Testing"],
            is_draft=True,
            dry_run=True,
        )

        self.assertTrue(res.success)
        self.assertTrue(res.is_draft)
        self.assertTrue(res.post_id.startswith("dryrun-"))
        self.assertIsNotNone(res.post_url)

    def test_token_redaction(self):
        """Tokens and secrets must be properly masked in string representations."""
        secret = "1//04_abcdef123456789xyz"
        redacted = self.client._redact_token(secret)
        self.assertTrue(redacted.startswith("1//0..."))
        self.assertTrue(redacted.endswith("...9xyz"))
        self.assertNotIn("abcdef123456", redacted)

    def test_reconciliation_error_does_not_swallow_exception(self):
        """Reconciliation lookup failures must raise an exception so the pipeline fails closed."""
        self.client._access_token = "mock-token"

        with patch("urllib.request.urlopen") as mock_urlopen:
            # Simulate a 500 server error on Blogger search API
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://www.googleapis.com/blogger/v3/blogs/1234567890/posts/search",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=MagicMock(read=lambda: b"Backend error"),
            )

            # Must raise RuntimeError and NOT return None silently
            with self.assertRaises(RuntimeError) as cm:
                self.client.reconcile_existing_post("Existing Article")

            self.assertIn("Stopping safely to prevent duplicates", str(cm.exception))

    def test_missing_credentials_fails_refresh(self):
        """Missing credentials must fail cleanly with informative ValueError."""
        empty_client = BloggerClient(blog_id="123")
        with self.assertRaises(ValueError) as cm:
            empty_client.refresh_access_token()
        self.assertIn("Missing OAuth credentials", str(cm.exception))

    def test_seo_metadata_forbids_local_paths(self):
        """SEOMetadata.inject_seo_and_assets must reject runner-local paths and omit them."""
        html_input = "<p>Article text</p>"
        local_path = "output/screenshots/screen_123.png"
        injected = SEOMetadata.inject_seo_and_assets(
            html_body=html_input,
            title="Test Post",
            meta_description="A test post description.",
            public_screenshot_url=local_path,  # Passed local path
        )
        self.assertNotIn("<img", injected)
        self.assertNotIn(local_path, injected)

    def test_multiple_product_screenshots_are_distributed_across_distinct_sections(self):
        body = (
            "<h2>Understanding Brand Kit Plans</h2><p>Choose a plan for your team.</p>"
            "<p>More plan details.</p><h2>Creating Your Brand Kit</h2>"
            "<p>Open the Brand tab and add your assets.</p><p>Save your kit.</p>"
            "<h2>Applying Your Brand Kit</h2><p>Use saved colors in a design.</p>"
            "<h2>Sources &amp; References</h2><p>Official documentation.</p>"
        )
        screenshots = [
            {"url": "https://cdn.example/one.png", "source_url": "https://www.canva.com/",
             "caption": "Canva plans", "alt": "Plan settings"},
            {"url": "https://cdn.example/two.png", "source_url": "https://www.canva.com/",
             "caption": "Canva brand kit", "alt": "Brand kit editor"},
        ]
        result = SEOMetadata.inject_seo_and_assets(
            body, "Canva Brand Kit", "A practical guide.",
            public_screenshot_items=screenshots, include_schema=False,
        )
        plans = result.index("Choose a plan")
        first_image = result.index("one.png")
        create = result.index("Open the Brand tab")
        second_image = result.index("two.png")
        apply = result.index("Use saved colors")
        self.assertLess(plans, first_image)
        self.assertLess(first_image, create)
        self.assertLess(create, second_image)
        self.assertLess(second_image, apply)
        self.assertNotIn("one.png", result[result.index("Sources &amp; References"):])

    def test_default_configuration_enforces_dry_run_and_draft(self):
        """Default configuration must enforce dry_run=True and publish_mode='draft'."""
        from src.config import AppConfig
        cfg = AppConfig()
        self.assertTrue(cfg.dry_run, "Dry run must be True by default for safety.")
        self.assertEqual(cfg.publish_mode, "draft", "Draft must be the default publication mode.")

    def test_live_publish_requires_explicit_confirmation(self):
        """Publishing publicly requires CONFIRM_LIVE_PUBLISH='true' to prevent accidental live posts."""
        import os
        from src.config import AppConfig

        cfg = AppConfig(
            dry_run=False,
            publish_mode="publish",
            gemini_api_key="fake-key",
            blogger_blog_id="fake-id",
            blogger_client_id="fake-cid",
            blogger_client_secret="fake-secret",
            blogger_refresh_token="fake-rt",
        )

        with patch.dict(os.environ, {"CONFIRM_LIVE_PUBLISH": "false"}, clear=False):
            errors = cfg.validate_for_mode(stage="all")
            self.assertTrue(any("CONFIRM_LIVE_PUBLISH" in e for e in errors))

        with patch.dict(os.environ, {"CONFIRM_LIVE_PUBLISH": "true"}, clear=False):
            errors = cfg.validate_for_mode(stage="all")
            self.assertFalse(any("CONFIRM_LIVE_PUBLISH" in e for e in errors))

    def test_topic_id_reconciliation_finds_match_on_second_page(self):
        """Topic markers on older pages must prevent duplicate insertion."""
        self.client._access_token = "mock-token"
        page_one = MagicMock()
        page_one.__enter__.return_value.read.return_value = b'{"items":[{"id":"newer","title":"Newer"}],"nextPageToken":"page/2 + token"}'
        page_two = MagicMock()
        page_two.__enter__.return_value.read.return_value = (
            b'{"items":[{"id":"older","title":"Older","url":"https://example.com/older",'
            b'"status":"DRAFT","content":"<!-- topic_id: archived-topic -->"}]}'
        )

        with patch("urllib.request.urlopen", side_effect=[page_one, page_two]) as mock_urlopen:
            result = self.client.reconcile_existing_post("", topic_id="archived-topic")

        self.assertTrue(result.reconciled_existing)
        self.assertEqual(result.post_id, "older")
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertIn("pageToken=page%2F2%20%2B%20token", mock_urlopen.call_args_list[1].args[0].full_url)

    def test_topic_id_reconciliation_stops_after_final_page(self):
        """A response without nextPageToken must not cause an unnecessary request."""
        self.client._access_token = "mock-token"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"items":[]}'

        with patch("urllib.request.urlopen", return_value=response) as mock_urlopen:
            result = self.client.reconcile_existing_post("", topic_id="not-present")

        self.assertIsNone(result)
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_topic_id_reconciliation_fails_closed_on_later_page_error(self):
        """A later-page API failure must stop reconciliation rather than risk a duplicate."""
        self.client._access_token = "mock-token"
        first_page = MagicMock()
        first_page.__enter__.return_value.read.return_value = b'{"items":[],"nextPageToken":"page-2"}'
        later_error = urllib.error.HTTPError(
            url="https://www.googleapis.com/blogger/v3/blogs/1234567890/posts",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=MagicMock(read=lambda: b"Unavailable"),
        )

        with patch("urllib.request.urlopen", side_effect=[first_page, later_error]):
            with self.assertRaises(RuntimeError) as cm:
                self.client.reconcile_existing_post("", topic_id="topic")

        self.assertIn("Stopping to prevent duplicates", str(cm.exception))

    def test_topic_id_reconciliation_rejects_repeated_page_token(self):
        """Repeated pagination tokens must not create an infinite request loop."""
        self.client._access_token = "mock-token"
        first_page = MagicMock()
        first_page.__enter__.return_value.read.return_value = b'{"items":[],"nextPageToken":"same"}'
        second_page = MagicMock()
        second_page.__enter__.return_value.read.return_value = b'{"items":[],"nextPageToken":"same"}'

        with patch("urllib.request.urlopen", side_effect=[first_page, second_page]) as mock_urlopen:
            with self.assertRaises(RuntimeError) as cm:
                self.client.reconcile_existing_post("", topic_id="topic")

        self.assertIn("repeated page token", str(cm.exception))
        self.assertEqual(mock_urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()

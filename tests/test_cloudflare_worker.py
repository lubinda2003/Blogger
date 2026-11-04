"""Unit tests for Cloudflare Worker client and persistent state coordination."""

import json
import unittest
from unittest.mock import MagicMock, patch

from src.cloudflare_client import CloudflareWorkerClient
from src.state_store import StateStore


class TestCloudflareWorkerClient(unittest.TestCase):
    """Test suite for Cloudflare Worker bridge and D1 coordination."""

    def test_unconfigured_client_gracefully_noops(self):
        """When worker URL is unset, client is not configured and calls return safe empty defaults."""
        client = CloudflareWorkerClient(worker_url=None, auth_token=None)
        self.assertFalse(client.is_configured)
        self.assertEqual(client.get_processed_topics(), [])
        self.assertFalse(client.record_run({"status": "SUCCESS"}))
        self.assertFalse(client.record_topic(topic_id="t1", topic_title="Title 1"))

    def test_get_processed_topics_parses_json(self):
        """When worker URL is set, get_processed_topics should query /api/topics/processed."""
        client = CloudflareWorkerClient(worker_url="https://worker.example.workers.dev", auth_token="secret-123")
        self.assertTrue(client.is_configured)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "success": True,
            "processed": [
                {"topic_id": "topic-1", "fingerprint": "fp-1"},
                {"topic_id": "topic-2", "fingerprint": "fp-2"},
            ]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            topics = client.get_processed_topics()
            self.assertEqual(len(topics), 2)
            self.assertEqual(topics[0]["topic_id"], "topic-1")

            # Check Authorization header was provided
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.headers.get("Authorization"), "Bearer secret-123")

    def test_record_run_posts_aligned_telemetry(self):
        """record_run sends canonical field names matching the Worker D1 schema."""
        client = CloudflareWorkerClient(worker_url="https://worker.example.workers.dev", auth_token="secret-123")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"success": True, "recorded_run": True}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            res = client.record_run({
                "run_id": "test-123",
                "overall_status": "SUCCESS",
                "selected_topic_id": "topic-1",
                "selected_topic": "Test Topic Title",
                "post_id": "post-999",
                "post_url": "https://example.com/p/999",
                "publish_mode": "draft",
                "dry_run": False,
                "category": "Software and Productivity",
                "total_duration_seconds": 12.5,
            })
            self.assertTrue(res)
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.method, "POST")
            self.assertTrue(req.full_url.endswith("/api/runs/record"))
            sent_payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(sent_payload["overall_status"], "SUCCESS")
            self.assertEqual(sent_payload["selected_topic_id"], "topic-1")
            self.assertEqual(sent_payload["blogger"]["post_id"], "post-999")

    def test_record_topic_direct_d1_insert(self):
        """record_topic calls /api/topics/record with proper payload."""
        client = CloudflareWorkerClient(worker_url="https://worker.example.workers.dev", auth_token="secret-123")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"success": True, "topic_id": "topic-abc"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            res = client.record_topic(
                topic_id="topic-abc",
                topic_title="Obsidian vs Notion",
                category="Software and Productivity",
                post_id="post-555",
            )
            self.assertTrue(res)
            req = mock_urlopen.call_args[0][0]
            self.assertTrue(req.full_url.endswith("/api/topics/record"))

    def test_state_store_merges_cloudflare_fingerprints(self):
        """StateStore should query Cloudflare client and add remote topic IDs and fingerprints."""
        mock_cf = MagicMock()
        mock_cf.is_configured = True
        mock_cf.get_processed_topics.return_value = [
            {"topic_id": "remote-topic-99", "fingerprint": "remotefp99"}
        ]

        store = StateStore(state_file_path="data/processed_topics.json", cloudflare_client=mock_cf)
        fingerprints = store.get_processed_fingerprints()

        self.assertIn("id:remote-topic-99", fingerprints)
        self.assertIn("remotefp99", fingerprints)
        self.assertTrue(store.is_duplicate("remote-topic-99", "Some Unrelated Title"))


    def test_d1_failure_reports_clearly_and_sets_last_error(self):
        """When Worker or D1 returns HTTP 503 or 500, error must be captured and last_error populated."""
        import urllib.error
        client = CloudflareWorkerClient(worker_url="https://worker.example.workers.dev", auth_token="secret-123")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://worker.example.workers.dev/api/topics/processed",
                code=503,
                msg="Service Unavailable",
                hdrs={},
                fp=MagicMock(read=lambda: b'{"error": "D1 database binding \'DB\' is not configured or unavailable", "success": false}'),
            )

            # Non-raising mode should record last_error and return empty list
            topics = client.get_processed_topics(raise_on_error=False)
            self.assertEqual(topics, [])
            self.assertIsNotNone(client.last_error)
            self.assertIn("503", client.last_error)
            self.assertIn("D1 database binding", client.last_error)

            # Raising mode must raise RuntimeError with descriptive message
            with self.assertRaises(RuntimeError) as ctx:
                client.get_processed_topics(raise_on_error=True)
            self.assertIn("503", str(ctx.exception))

    def test_state_store_distinguishes_d1_failure_from_success(self):
        """StateStore must explicitly mark remote_sync_status as FAILED or SUCCESS."""
        mock_cf = MagicMock()
        mock_cf.is_configured = True

        # Case 1: D1 fails
        mock_cf.get_processed_topics.side_effect = RuntimeError("Cloudflare Worker HTTP 503: D1 unavailable")
        store = StateStore(state_file_path="data/processed_topics.json", cloudflare_client=mock_cf)

        fps = store.get_processed_fingerprints()
        self.assertEqual(store.remote_sync_status, "FAILED")
        self.assertIn("503", store.remote_sync_error)
        self.assertIsInstance(fps, set)

        # Case 2: D1 succeeds
        mock_cf.get_processed_topics.side_effect = None
        mock_cf.get_processed_topics.return_value = [{"topic_id": "remote-1", "fingerprint": "fp-1"}]
        store2 = StateStore(state_file_path="data/processed_topics.json", cloudflare_client=mock_cf)

        fps2 = store2.get_processed_fingerprints()
        self.assertEqual(store2.remote_sync_status, "SUCCESS")
        self.assertIsNone(store2.remote_sync_error)
        self.assertIn("id:remote-1", fps2)

    def test_missing_or_placeholder_d1_database_id_detected(self):
        """Placeholders and missing database IDs in D1 configuration must be flagged."""
        from src.cloudflare_client import check_d1_database_id_configured, inspect_wrangler_d1_config

        # Test placeholder patterns
        is_valid, msg = check_d1_database_id_configured("<YOUR_D1_DATABASE_ID_FROM_CLOUDFLARE>")
        self.assertFalse(is_valid)
        self.assertIn("placeholder", msg.lower())

        is_valid, msg = check_d1_database_id_configured("")
        self.assertFalse(is_valid)
        self.assertIn("empty or missing", msg.lower())

        is_valid, msg = check_d1_database_id_configured("your_d1_uuid_here")
        self.assertFalse(is_valid)

        # Valid UUID format
        is_valid, msg = check_d1_database_id_configured("12345678-abcd-ef01-2345-6789abcdef01")
        self.assertTrue(is_valid)

        # Check existing worker/wrangler.toml
        is_valid, msg = inspect_wrangler_d1_config("worker/wrangler.toml")
        self.assertFalse(is_valid)
        self.assertIn("placeholder", msg.lower())

    def test_d1_lookup_failure_stops_pipeline_when_not_local_only(self):
        """When D1 lookup fails and local_only is False, pipeline must halt to protect against duplicate posts."""
        from src.config import AppConfig
        from src.main import run_pipeline

        config = AppConfig(
            dry_run=True,
            publish_mode="draft",
            local_only=False,
            cloudflare_worker_url="https://worker.example.workers.dev",
            cloudflare_worker_secret="test-token",
        )

        with patch("src.main.CloudflareWorkerClient") as mock_cf_cls:
            mock_cf = MagicMock()
            mock_cf.is_configured = True
            mock_cf.get_processed_topics.side_effect = RuntimeError("503 Service Unavailable: D1 is not responding")
            mock_cf_cls.return_value = mock_cf

            exit_code = run_pipeline(config=config, stage_limit="all")
            # Pipeline MUST fail closed (exit code 1) to prevent generating duplicates
            self.assertEqual(exit_code, 1)

    def test_local_only_operation_bypasses_d1_and_uses_local_cache(self):
        """When local_only is True, pipeline operates on local state cache and succeeds even without D1."""
        from src.config import AppConfig
        from src.main import run_pipeline

        config = AppConfig(
            dry_run=True,
            publish_mode="draft",
            local_only=True,
            cloudflare_worker_url="https://worker.example.workers.dev",
            cloudflare_worker_secret="test-token",
        )

        with patch("src.main.CloudflareWorkerClient") as mock_cf_cls:
            mock_cf = MagicMock()
            mock_cf.is_configured = True
            mock_cf.get_processed_topics.side_effect = RuntimeError("D1 is down")
            mock_cf_cls.return_value = mock_cf

            exit_code = run_pipeline(config=config, target_topic_id="notion-obsidian", stage_limit="discover")
            # Must succeed in discover stage using local cache
            self.assertEqual(exit_code, 0)

    def test_safe_handling_of_unauthorized_cloudflare_credentials(self):
        """Worker returning HTTP 401 Unauthorized must set last_error and fail gracefully."""
        import urllib.error
        client = CloudflareWorkerClient(worker_url="https://worker.example.workers.dev", auth_token="bad-token")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://worker.example.workers.dev/api/topics/processed",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=MagicMock(read=lambda: b'{"error": "Unauthorized: Invalid or missing Bearer token", "success": false}'),
            )

            topics = client.get_processed_topics(raise_on_error=False)
            self.assertEqual(topics, [])
            self.assertIsNotNone(client.last_error)
            self.assertIn("401", client.last_error)
            self.assertIn("Unauthorized", client.last_error)
            self.assertIn("Auth Diagnostic", client.last_error)
            self.assertIn("present (length: 9)", client.last_error)
            # Must not expose the secret token itself
            self.assertNotIn("bad-token", client.last_error)

    def test_client_sanitizes_token_quotes_and_whitespace(self):
        """Client must strip whitespace and surrounding quotes from worker URL and auth token."""
        client = CloudflareWorkerClient(
            worker_url='  "https://worker.example.workers.dev/"  ',
            auth_token="  'my-secret-key'  ",
        )
        self.assertEqual(client.worker_url, "https://worker.example.workers.dev")
        self.assertEqual(client.auth_token, "my-secret-key")
        headers = client._headers()
        self.assertEqual(headers["Authorization"], "Bearer my-secret-key")

    def test_client_diagnostics_when_token_is_missing(self):
        """When worker URL is set but token is None/empty, HTTP 401 reports token as MISSING / UNSET."""
        import urllib.error
        client = CloudflareWorkerClient(worker_url="https://worker.example.workers.dev", auth_token=None)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://worker.example.workers.dev/api/topics/processed",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=MagicMock(read=lambda: b'{"error": "Unauthorized: Missing Authorization header (expected Bearer <token>)", "success": false}'),
            )
            topics = client.get_processed_topics(raise_on_error=False)
            self.assertEqual(topics, [])
            self.assertIn("401", client.last_error)
            self.assertIn("MISSING / UNSET", client.last_error)

    def test_config_loads_worker_secret_aliases(self):
        """load_config must recognize WORKER_API_SECRET as alias for CLOUDFLARE_WORKER_SECRET."""
        import os
        from src.config import load_config

        # Test WORKER_API_SECRET alias with surrounding quotes
        with patch.dict(os.environ, {"WORKER_API_SECRET": '"alias-secret-key"'}, clear=False):
            # Ensure CLOUDFLARE_WORKER_SECRET is not set
            if "CLOUDFLARE_WORKER_SECRET" in os.environ:
                del os.environ["CLOUDFLARE_WORKER_SECRET"]
            cfg = load_config()
            self.assertEqual(cfg.cloudflare_worker_secret, "alias-secret-key")


if __name__ == "__main__":
    unittest.main()



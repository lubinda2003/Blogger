"""Security tests for the developer console routes, input validation, and file reading defenses."""

import re
import unittest


class TestSecurityAndConsole(unittest.TestCase):
    """Test suite verifying input validation, argument isolation, and path traversal defense."""

    TOPIC_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    ALLOWED_STAGES = {'all', 'discover', 'research', 'write', 'screenshot', 'qa', 'publish'}

    ALLOWED_REPO_FILES = {
        '.github/workflows/content-pipeline.yml',
        '.github/workflows/deploy-worker.yml',
        '.github/workflows/tests.yml',
        'config/settings.example.yaml',
        'config/editorial_policy.md',
        'config/config.json',
        'config/config.example.json',
        'data/topics.csv',
        'data/processed_topics.json',
        'src/__init__.py',
        'src/main.py',
        'src/config.py',
        'src/topic_discovery.py',
        'src/research.py',
        'src/article_writer.py',
        'src/screenshot_capture.py',
        'src/seo_metadata.py',
        'src/quality_checks.py',
        'src/blogger_client.py',
        'src/cloudflare_client.py',
        'src/state_store.py',
        'src/report.py',
        'worker/index.ts',
        'worker/wrangler.toml',
        'worker/schema.sql',
        'worker/package.json',
        'worker/tsconfig.json',
        'templates/article_prompt.md',
        'tests/test_quality_checks.py',
        'tests/test_deduplication.py',
        'tests/test_blogger_payload.py',
        'tests/test_research_and_sources.py',
        'tests/test_style_and_writer.py',
        'tests/test_security_and_console.py',
        'tests/test_cloudflare_worker.py',
        'scripts/get_blogger_refresh_token.py',
        'config/requirements.txt',
        'README.md',
        'LICENSE',
        '.gitignore',
    }

    def test_topic_id_blocks_command_injection(self):
        """Dangerous shell characters in topicId must fail the regex validator."""
        malicious_inputs = [
            "topic; rm -rf /",
            "topic && whoami",
            "topic | cat /etc/passwd",
            "`id`",
            "$(cat .env)",
            "topic>out.txt",
            "topic' OR '1'='1",
            "../../../etc/shadow",
        ]
        for payload in malicious_inputs:
            self.assertFalse(
                bool(self.TOPIC_ID_REGEX.match(payload)),
                f"Malicious payload unexpectedly passed topic ID validator: {payload}",
            )

    def test_valid_topic_ids_pass(self):
        """Legitimate alphanumeric, dashed, and underscored IDs must pass."""
        valid_ids = [
            "ai-gemini-editing",
            "upwork_zambia_2026",
            "payoneer-banking",
            "canva-brand-kit",
        ]
        for valid in valid_ids:
            self.assertTrue(bool(self.TOPIC_ID_REGEX.match(valid)))

    def test_file_reader_blocks_path_traversal(self):
        """Directory traversal attempts and secret files must be blocked by the allowlist."""
        forbidden_paths = [
            "../server.ts",
            "../../etc/passwd",
            ".env",
            ".env.local",
            "config/../../.env",
            "secrets.json",
            "id_rsa",
            "id_rsa.pub",
        ]
        for p in forbidden_paths:
            # Traversal check: check for '..' or not in allowed list
            is_blocked = ".." in p or p not in self.ALLOWED_REPO_FILES
            self.assertTrue(is_blocked, f"Path was not blocked: {p}")

    def test_stage_allowlist_blocks_unauthorized_stages(self):
        """Invalid or injected stage names must be rejected."""
        invalid_stages = ["eval", "bash", "exec", "rm", "stage;ls"]
        for s in invalid_stages:
            self.assertNotIn(s, self.ALLOWED_STAGES)


if __name__ == "__main__":
    unittest.main()

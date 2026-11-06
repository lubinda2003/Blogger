"""Unit tests for Gemini response handling, fail-closed schema validation, and plain-English style."""

import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from src.article_writer import ArticleWriter
from src.research import ResearchBrief
from src.topic_discovery import TopicItem


class TestStyleAndWriter(unittest.TestCase):
    """Test suite for Gemini response validation and style requirements."""

    def setUp(self):
        self.writer = ArticleWriter(api_key="mock-api-key")
        self.topic = TopicItem(
            id="test-topic",
            topic="How to Use Gemini API",
            category="AI Tools",
            primary_intent="Tutorial",
            priority=1,
            requires_screenshot=False,
            target_url="https://ai.google.dev",
            target_audience="Developers",
        )
        self.brief = ResearchBrief(
            topic_id="test-topic",
            topic_title="How to Use Gemini API",
            target_url="https://ai.google.dev",
        )

    def test_malformed_gemini_json_fails_closed_in_live_mode(self):
        """In live mode, if Gemini returns invalid JSON and repair fails, it must fail closed and NOT use fallback."""
        with patch.object(self.writer, "_call_gemini_rest") as mock_call:
            mock_call.return_value = "This is not valid JSON at all!"

            with self.assertRaises(RuntimeError) as cm:
                self.writer.write_article(self.topic, self.brief, dry_run=False)

            self.assertIn("could not be parsed as JSON", str(cm.exception))

    def test_missing_required_fields_fails_schema_validation(self):
        """If Gemini returns JSON missing required fields (e.g. title or html_content), it must fail."""
        with patch.object(self.writer, "_call_gemini_rest") as mock_call:
            # Missing html_content and title
            mock_call.return_value = '{"summary": "Just a summary"}'

            with self.assertRaises(RuntimeError) as cm:
                self.writer.write_article(self.topic, self.brief, dry_run=False)

            self.assertIn("failed schema validation", str(cm.exception))

    def test_gemini_api_error_does_not_log_secret_key(self):
        """HTTP error from Gemini must redact API key from exception message."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key=AIzaSySecretKey123",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=MagicMock(read=lambda: b'{"error": {"message": "Invalid request parameters key=AIzaSySecretKey123"}}'),
            )

            with self.assertRaises(RuntimeError) as cm:
                self.writer._call_gemini_rest("Test prompt")

            err_str = str(cm.exception)
            self.assertNotIn("AIzaSySecretKey123", err_str)
            self.assertIn("[REDACTED]", err_str)

    def test_default_gemini_model_is_gemini_3_8_flash(self):
        """Default Gemini model across AppConfig and ArticleWriter must be gemini-3.8-flash."""
        from src.config import AppConfig, load_config
        config = load_config()
        self.assertEqual(config.gemini_model, "gemini-3.8-flash")
        writer = ArticleWriter(api_key="test-key")
        self.assertEqual(writer.model_name, "gemini-3.8-flash")

    def test_gemini_model_env_var_override(self):
        """Setting GEMINI_MODEL env var must override default model in load_config and ArticleWriter."""
        from src.config import load_config
        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-custom-override"}):
            config = load_config()
            self.assertEqual(config.gemini_model, "gemini-custom-override")
            writer = ArticleWriter(api_key="test-key")
            self.assertEqual(writer.model_name, "gemini-custom-override")

    def test_article_writer_uses_configured_model_in_rest_call(self):
        """ArticleWriter must construct REST endpoint URL with the exact configured model name."""
        writer = ArticleWriter(api_key="test-key", model_name="gemini-3.8-flash")
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"title\\": \\"Test\\", \\"meta_description\\": \\"Desc\\", \\"labels\\": [\\"Tag\\"], \\"html_content\\": \\"<p>Substantive article text long enough for schema validation check.</p>\\", \\"sources_used\\": []}"}]}}]}'
            mock_urlopen.return_value = resp

            writer._call_gemini_rest("Test prompt")

            args, kwargs = mock_urlopen.call_args
            req = args[0]
            self.assertIn("models/gemini-3.8-flash:generateContent", req.full_url)

    def test_groq_rest_call_success(self):
        """ArticleWriter must support Groq API REST calls with llama-3.3-70b-versatile."""
        writer = ArticleWriter(groq_api_key="gsk-mock-key", provider="groq")
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.read.return_value = b'{"choices": [{"message": {"content": "{\\"title\\": \\"Groq Article\\", \\"meta_description\\": \\"Desc\\", \\"labels\\": [\\"Tag\\"], \\"html_content\\": \\"<p>Substantive text from Groq model.</p>\\", \\"sources_used\\": []}"}}]}'
            mock_urlopen.return_value = resp

            result = writer._call_groq_rest("Test prompt")
            self.assertIn("Groq Article", result)

            args, kwargs = mock_urlopen.call_args
            req = args[0]
            self.assertEqual(req.full_url, "https://api.groq.com/openai/v1/chat/completions")
            self.assertEqual(req.headers.get("Authorization"), "Bearer gsk-mock-key")

    def test_gemini_fails_over_to_groq_when_groq_key_available(self):
        """When Gemini API call fails and GROQ_API_KEY is available, ArticleWriter automatically fails over to Groq."""
        writer = ArticleWriter(api_key="gemini-bad-key", groq_api_key="gsk-valid-key", provider="auto")
        with patch.object(writer, "_call_gemini_rest", side_effect=RuntimeError("Gemini 404 Model Not Found")), \
             patch.object(writer, "_call_groq_rest") as mock_groq:

            mock_groq.return_value = '{"title": "Failover Article"}'
            res = writer._call_llm_provider("Test prompt")
            self.assertEqual(res, '{"title": "Failover Article"}')
            mock_groq.assert_called_once_with("Test prompt", max_tokens=None)
            self.assertEqual(writer.actual_provider, "groq")
            self.assertEqual(writer.actual_model, "llama-3.3-70b-versatile")

    def test_gemini_header_auth_and_user_agent(self):
        """Gemini REST call must send x-goog-api-key header, custom User-Agent, and NO api key in URL."""
        writer = ArticleWriter(api_key="secret-api-key", model_name="gemini-3.8-flash")
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"title\\": \\"Test\\"}"}]}}]}'
            mock_urlopen.return_value = resp

            writer._call_gemini_rest("Test prompt")

            args, kwargs = mock_urlopen.call_args
            req = args[0]
            self.assertNotIn("?key=", req.full_url)
            self.assertEqual(req.headers.get("X-goog-api-key"), "secret-api-key")
            self.assertEqual(req.headers.get("User-agent"), "DigitalToolkitContentEngine/1.0")

    def test_groq_user_agent_and_max_tokens(self):
        """Groq REST call must send custom User-Agent and max_tokens (default 8192)."""
        writer = ArticleWriter(groq_api_key="gsk-test", provider="groq")
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.read.return_value = b'{"choices": [{"message": {"content": "{\\"title\\": \\"Groq Article\\"}"}}]}'
            mock_urlopen.return_value = resp

            writer._call_groq_rest("Test prompt")

            args, kwargs = mock_urlopen.call_args
            req = args[0]
            self.assertEqual(req.headers.get("User-agent"), "DigitalToolkitContentEngine/1.0")
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload.get("max_tokens"), 8192)

    def test_fallback_model_chain_tried_before_groq(self):
        """When primary Gemini model fails, fallback Gemini model is tried before Groq."""
        writer = ArticleWriter(
            api_key="gemini-key",
            model_name="gemini-3.8-flash",
            fallback_model="gemini-3.5-flash",
            groq_api_key="groq-key",
            provider="auto",
        )
        call_log = []

        def mock_gemini(prompt, model_name=None, max_tokens=None, is_token_retry=False):
            call_log.append(model_name)
            if model_name == "gemini-3.8-flash":
                raise RuntimeError("503 Service Unavailable")
            return '{"title": "From Fallback Flash"}'

        with patch.object(writer, "_call_gemini_rest", side_effect=mock_gemini), \
             patch.object(writer, "_call_groq_rest") as mock_groq:

            res = writer._call_llm_provider("Write prompt")
            self.assertEqual(res, '{"title": "From Fallback Flash"}')
            self.assertEqual(call_log, ["gemini-3.8-flash", "gemini-3.5-flash"])
            mock_groq.assert_not_called()
            self.assertEqual(writer.actual_provider, "gemini")
            self.assertEqual(writer.actual_model, "gemini-3.5-flash")

    def test_gemini_503_retried_up_to_5_times(self):
        """Gemini 503 errors must be retried up to 5 times with exponential backoff and jitter."""
        writer = ArticleWriter(api_key="gemini-key")
        attempt_count = 0

        def mock_urlopen(req, timeout=90):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=503,
                    msg="Service Unavailable",
                    hdrs={},
                    fp=MagicMock(read=lambda: b'{"error": "Backend overloaded"}'),
                )
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"title\\": \\"OK\\"}"}]}}]}'
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen), \
             patch("time.sleep") as mock_sleep:
            res = writer._call_gemini_rest("Test prompt")
            self.assertEqual(attempt_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)
            self.assertIn("OK", res)

    def test_finish_reason_max_tokens_retries_with_higher_limit(self):
        """If Gemini candidate has finishReason == 'MAX_TOKENS', it retries once with higher limit."""
        writer = ArticleWriter(api_key="gemini-key", max_tokens=4096)
        call_tokens = []

        def mock_urlopen(req, timeout=90):
            payload = json.loads(req.data.decode("utf-8"))
            toks = payload.get("generationConfig", {}).get("maxOutputTokens")
            call_tokens.append(toks)

            resp = MagicMock()
            resp.__enter__.return_value = resp
            if len(call_tokens) == 1:
                resp.read.return_value = b'{"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "truncated json"}]}}]}'
            else:
                resp.read.return_value = b'{"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "complete json"}]}}]}'
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = writer._call_gemini_rest("Test prompt")
            self.assertEqual(res, "complete json")
            self.assertEqual(call_tokens, [4096, 8192])

    def test_json_repair_prompt_contains_full_output(self):
        """JSON repair prompt must pass the full previous output without truncation."""
        writer = ArticleWriter(api_key="gemini-key")
        long_bad_output = '{"broken": "' + ("A" * 800)
        valid_repaired = json.dumps({
            "title": "Fixed Article",
            "meta_description": "A clear, practical guide with detailed steps and real instructions.",
            "labels": ["AI Tools", "Tutorial"],
            "html_content": "<p>" + ("Valid substantive article body text exceeding 200 characters. " * 5) + "</p>",
            "sources_used": [{"title": "Official Docs", "url": "https://example.com"}],
        })

        with patch.object(writer, "_call_llm_provider") as mock_llm:
            mock_llm.side_effect = [
                long_bad_output,  # Initial attempt (truncated)
                long_bad_output,  # Higher token retry (still fails)
                valid_repaired,   # Repaired via repair prompt
            ]

            draft = writer.write_article(self.topic, self.brief, dry_run=False)
            self.assertEqual(draft.title, "Fixed Article")

            repair_call_prompt = mock_llm.call_args_list[2][0][0]
            self.assertIn("A" * 800, repair_call_prompt)
            self.assertNotIn("[:400]", repair_call_prompt)

    def test_config_loads_gemini_temperature_and_max_tokens(self):
        """load_config must load temperature and max_output_tokens (default 8192) from config.json and env."""
        from src.config import load_config
        cfg = load_config()
        self.assertEqual(cfg.gemini_max_tokens, 8192)
        self.assertEqual(cfg.gemini_temperature, 0.3)
        self.assertEqual(cfg.gemini_fallback_model, "gemini-3.5-flash")

        with patch.dict("os.environ", {
            "GEMINI_TEMPERATURE": "0.7",
            "GEMINI_MAX_TOKENS": "12000",
            "GEMINI_FALLBACK_MODEL": "gemini-custom-flash",
        }):
            cfg2 = load_config()
            self.assertEqual(cfg2.gemini_temperature, 0.7)
            self.assertEqual(cfg2.gemini_max_tokens, 12000)
            self.assertEqual(cfg2.gemini_fallback_model, "gemini-custom-flash")

    def test_outbound_user_agent_on_all_clients(self):
        """BloggerClient and ResearchCollector must include DigitalToolkitContentEngine/1.0 User-Agent."""
        from src.blogger_client import BloggerClient
        from src.research import ResearchCollector
        from src.screenshot_capture import ScreenshotCapture

        blogger = BloggerClient(blog_id="test-blog", client_id="cid", client_secret="csec", refresh_token="tok")
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.read.return_value = b'{"access_token": "mock-token"}'
            mock_urlopen.return_value = resp

            blogger.refresh_access_token()
            args, _ = mock_urlopen.call_args
            self.assertEqual(args[0].headers.get("User-agent"), "DigitalToolkitContentEngine/1.0")

        researcher = ResearchCollector(tavily_api_key="tvly-mock")
        with patch("urllib.request.urlopen") as mock_urlopen:
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.status = 200
            resp.read.return_value = b'{"results": []}'
            mock_urlopen.return_value = resp

            researcher._search_tavily("test query")
            args, _ = mock_urlopen.call_args
            self.assertEqual(args[0].headers.get("User-agent"), "DigitalToolkitContentEngine/1.0")

        capturer = ScreenshotCapture()
        self.assertEqual(capturer.image_host_url, None)

    def test_dry_run_fixture_contains_no_ai_cliches(self):
        """Dry run text fixtures must comply with plain-English rules and contain no generic AI cliches."""
        fixture = self.writer._generate_dry_run_fixture(self.topic, self.brief)
        html = fixture["html_content"].lower()

        cliches = [
            "in today's fast-paced digital world",
            "unlock the power",
            "delve into",
            "embark on a journey",
            "game-changer",
            "look no further",
        ]
        for c in cliches:
            self.assertNotIn(c, html, f"Forbidden cliché found in dry run fixture: '{c}'")

    def test_article_draft_contains_slug_and_featured_image_brief(self):
        """ArticleDraft output must carry suggested_slug and structured featured_image_brief."""
        draft = self.writer.write_article(self.topic, self.brief, dry_run=True)
        self.assertTrue(draft.suggested_slug)
        self.assertNotIn(" ", draft.suggested_slug)
        self.assertIsInstance(draft.featured_image_brief, dict)
        self.assertIn("description", draft.featured_image_brief)
        self.assertIn("alt_text", draft.featured_image_brief)
        self.assertIn("aspect_ratio", draft.featured_image_brief)
        draft_dict = draft.to_dict()
        self.assertIn("suggested_slug", draft_dict)
        self.assertIn("featured_image_brief", draft_dict)
        self.assertIn("actual_provider", draft_dict)
        self.assertIn("actual_model", draft_dict)


if __name__ == "__main__":
    unittest.main()


"""Regression tests for bounded LLM provider failover."""

import json
import unittest
from unittest.mock import MagicMock, patch

from src.article_writer import ArticleWriter, GROQ_MAX_COMPLETION_TOKENS, GROQ_MAX_PROMPT_CHARS


class ArticleWriterFallbackTests(unittest.TestCase):
    def make_writer(self):
        return ArticleWriter(
            api_key="gemini-key-one",
            groq_api_key="groq-key",
            model_name="primary-model",
            fallback_model="secondary-model",
            provider="auto",
            prompt_template_path="missing-prompt.md",
            voice_guide_path="missing-voice.md",
            layout_guide_path="missing-layout.md",
        )

    def test_groq_prompt_is_bounded_and_keeps_prompt_edges(self):
        writer = self.make_writer()
        prompt = "OPENING-INSTRUCTIONS " + ("research context " * 2000) + " FINAL-JSON-SCHEMA"
        fitted = writer._fit_groq_prompt(prompt)

        self.assertLessEqual(len(fitted), GROQ_MAX_PROMPT_CHARS)
        self.assertTrue(fitted.startswith("OPENING-INSTRUCTIONS"))
        self.assertTrue(fitted.endswith("FINAL-JSON-SCHEMA"))
        self.assertIn("context shortened", fitted)

    def test_short_groq_prompt_is_unchanged(self):
        writer = self.make_writer()
        prompt = "Short complete prompt."
        self.assertEqual(writer._fit_groq_prompt(prompt), prompt)

    def test_groq_completion_budget_is_conservative(self):
        self.assertEqual(GROQ_MAX_COMPLETION_TOKENS, 8192)

    def test_groq_request_uses_expanded_completion_budget_and_gpt_oss_low_effort(self):
        writer = self.make_writer()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"choices":[{"message":{"content":"{}"}}]}'
        )

        with patch("src.article_writer.urllib.request.urlopen", return_value=response) as urlopen:
            self.assertEqual(writer._call_groq_rest("Return a JSON object."), "{}")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["max_completion_tokens"], 8192)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["reasoning_effort"], "low")

    def test_secondary_gemini_rotates_keys_before_groq(self):
        writer = self.make_writer()
        writer.gemini_api_keys = ["gemini-key-one", "gemini-key-two"]
        calls = []

        def gemini(prompt, model_name=None, max_tokens=None, max_attempts=None, api_key=None):
            calls.append((model_name, api_key))
            if model_name == "primary-model":
                raise RuntimeError("Gemini quota exhausted")
            if api_key == "gemini-key-one":
                raise RuntimeError("Gemini quota exhausted")
            return '{"ok": true}'

        with patch.object(writer, "_call_gemini_rest", side_effect=gemini), \
             patch.object(writer, "_call_groq_rest") as groq:
            result = writer._call_llm_provider("prompt")

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(
            calls,
            [
                ("primary-model", "gemini-key-one"),
                ("primary-model", "gemini-key-two"),
                ("secondary-model", "gemini-key-one"),
                ("secondary-model", "gemini-key-two"),
            ],
        )
        groq.assert_not_called()
        self.assertEqual(writer.actual_provider, "gemini")
        self.assertEqual(writer.actual_model, "secondary-model")


    def test_groq_metadata_recovery_uses_topic_and_article_without_changing_body(self):
        writer = self.make_writer()
        topic = MagicMock()
        topic.topic = "How to Build a Weekly Work Plan"
        topic.category = "Software and Productivity"
        body = "<h2>Plan your week</h2><p>Start by listing your priorities and deadlines. " + ("Review your tasks and choose realistic work blocks. " * 8) + "</p>"
        parsed = {"html_content": body, "sources_used": [{"title": "Official guide", "url": "https://example.com"}]}

        completed = writer._complete_groq_metadata(parsed, topic)

        self.assertEqual(completed["title"], topic.topic)
        self.assertEqual(completed["labels"], [topic.category])
        self.assertTrue(completed["meta_description"])
        self.assertLessEqual(len(completed["meta_description"]), 160)
        self.assertEqual(completed["html_content"], body)
        self.assertEqual(completed["sources_used"], parsed["sources_used"])

    def test_groq_metadata_recovery_preserves_valid_metadata(self):
        writer = self.make_writer()
        topic = MagicMock()
        topic.topic = "Fallback topic"
        topic.category = "Tutorials"
        parsed = {
            "title": "A supplied title",
            "meta_description": "A supplied description.",
            "labels": ["AI Tools", "Tutorial"],
            "html_content": "<p>" + ("Useful article content. " * 20) + "</p>",
            "sources_used": [{"title": "Official guide", "url": "https://example.com"}],
        }

        completed = writer._complete_groq_metadata(parsed, topic)

        self.assertEqual(completed["title"], "A supplied title")
        self.assertEqual(completed["meta_description"], "A supplied description.")
        self.assertEqual(completed["labels"], ["AI Tools", "Tutorial"])

    def test_groq_metadata_recovery_does_not_repair_missing_article_body_or_sources(self):
        writer = self.make_writer()
        topic = MagicMock()
        topic.topic = "A real topic"
        topic.category = "Tutorials"

        completed = writer._complete_groq_metadata({"html_content": "", "sources_used": []}, topic)
        errors = writer._validate_schema(completed)

        self.assertTrue(any("html_content" in error for error in errors))
        self.assertTrue(any("sources_used" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

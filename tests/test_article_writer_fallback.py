"""Regression tests for bounded LLM provider failover."""

import unittest
from unittest.mock import patch

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
        self.assertEqual(GROQ_MAX_COMPLETION_TOKENS, 2500)

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


if __name__ == "__main__":
    unittest.main()

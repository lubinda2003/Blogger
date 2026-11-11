"""Phase-one regression tests for Blogger HTML output quality."""

import unittest

from src.article_writer import ArticleWriter
from src.seo_metadata import SEOMetadata


class TestSeoAssetMarkup(unittest.TestCase):
    def test_screenshot_markup_uses_real_newlines_not_literal_backslash_n(self):
        result = SEOMetadata.inject_seo_and_assets(
            html_body="<h2>Google AI Studio</h2><p>Upload a PDF.</p>",
            title="PDF guide",
            meta_description="A practical guide to analysing PDF files with Gemini.",
            public_screenshot_items=[{
                "url": "https://cdn.example/screenshot.png",
                "source_url": "https://ai.google.dev/",
                "caption": "Google AI Studio interface",
                "alt": "Google AI Studio interface",
            }],
            include_schema=False,
        )
        self.assertNotIn(r"\\n", result)
        self.assertIn("\n", result)
        self.assertIn('<figure class="article-screenshot"', result)

    def test_article_wrapper_does_not_add_literal_backslash_n(self):
        result = SEOMetadata.inject_seo_and_assets(
            html_body="<p>Useful content.</p>",
            title="A useful guide",
            meta_description="A useful guide with practical steps and clear explanations.",
            include_schema=False,
        )
        self.assertNotIn(r"\\n", result)
        self.assertTrue(result.endswith("</div>"))


class TestSourcesSection(unittest.TestCase):
    def test_existing_sources_heading_prevents_duplicate_empty_wrapper(self):
        body = (
            "<p>Article body.</p>"
            "<h2>Sources &amp; References</h2>"
            '<ul><li><a href="https://example.com">Example</a></li></ul>'
        )
        result = ArticleWriter.append_sources_section(
            body, [{"title": "Example", "url": "https://example.com"}]
        )
        self.assertEqual(result, body)
        self.assertNotIn('class="article-sources"', result)

    def test_sources_are_appended_when_article_has_no_references(self):
        body = '<div class="article-body"><p>Article body.</p></div>'
        result = ArticleWriter.append_sources_section(
            body, [{"title": "Example", "url": "https://example.com"}]
        )
        self.assertIn("Sources &amp; References", result)
        self.assertIn("https://example.com", result)
        self.assertEqual(result.count("Sources &amp; References"), 1)


if __name__ == "__main__":
    unittest.main()

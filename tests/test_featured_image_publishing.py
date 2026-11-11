"""Tests for header image publishing, embedding and pipeline wiring."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import main as pipeline
from src.config import load_config
from src.featured_image import FeaturedImage, prepare_featured_image
from src.seo_metadata import SEOMetadata


class TestPrepare(unittest.TestCase):
    def _generator(self, ok=True):
        gen = MagicMock()
        gen.generate.return_value = (
            FeaturedImage(True, Path("output/featured/x.jpg"), "a" * 64, "alt") if ok else FeaturedImage(False, error_message="nope")
        )
        return gen

    def test_disabled_returns_none_and_does_nothing(self):
        gen = self._generator()
        self.assertIsNone(prepare_featured_image(False, False, "T", "K", "slug", generator=gen))
        gen.generate.assert_not_called()

    def test_dry_run_renders_but_never_publishes(self):
        publisher = MagicMock()
        img = prepare_featured_image(True, True, "T", "K", "slug", generator=self._generator(), publisher=publisher)
        self.assertTrue(img.success)
        self.assertIsNone(img.public_url)
        publisher.assert_not_called()

    def test_live_run_publishes_and_sets_the_public_url(self):
        publisher = MagicMock(return_value="https://cdn.jsdelivr.net/gh/o/r@main/assets/covers/x.jpg")
        img = prepare_featured_image(True, False, "T", "K", "slug", generator=self._generator(), publisher=publisher)
        publisher.assert_called_once_with(Path("output/featured/x.jpg"), "slug", "a" * 64)
        self.assertEqual(img.public_url, "https://cdn.jsdelivr.net/gh/o/r@main/assets/covers/x.jpg")

    def test_hosting_failure_is_not_fatal(self):
        publisher = MagicMock(side_effect=RuntimeError("push rejected"))
        img = prepare_featured_image(True, False, "T", "K", "slug", generator=self._generator(), publisher=publisher)
        self.assertTrue(img.success)
        self.assertIsNone(img.public_url)

    def test_generation_failure_skips_publishing(self):
        publisher = MagicMock()
        img = prepare_featured_image(True, False, "T", "K", "slug", generator=self._generator(ok=False), publisher=publisher)
        self.assertFalse(img.success)
        publisher.assert_not_called()


class TestInjection(unittest.TestCase):
    URL = "https://cdn.jsdelivr.net/gh/o/r@main/assets/covers/x.jpg"

    def _inject(self, **kw):
        return SEOMetadata.inject_seo_and_assets("<p>Body</p>", "Title", "Desc", **kw)

    def test_cover_has_dimensions_alt_and_comes_before_the_body(self):
        out = self._inject(featured_image_url=self.URL, featured_image_alt='Cover "one" <b>')
        self.assertIn('width="1200" height="630"', out)
        self.assertIn("Cover &quot;one&quot; &lt;b&gt;", out)
        self.assertLess(out.index("article-cover"), out.index("<p>Body</p>"))

    def test_cover_comes_before_the_screenshot(self):
        out = self._inject(featured_image_url=self.URL, public_screenshot_url="https://cdn.example/s.png")
        self.assertLess(out.index("article-cover"), out.index("article-screenshot"))

    def test_screenshots_are_placed_in_the_matching_product_sections(self):
        body = (
            "<p>Introduction.</p>"
            "<h2>How Obsidian Works</h2><p>Obsidian stores notes locally.</p><p>More detail.</p>"
            "<h2>How Notion Works</h2><p>Notion is a collaborative workspace.</p><p>More detail.</p>"
            "<h2>Sources &amp; References</h2><ul><li>Source</li></ul>"
        )
        items = [
            {"url": "https://cdn.example/obsidian.png", "source_url": "https://obsidian.md", "caption": "Obsidian interface", "alt": "Obsidian"},
            {"url": "https://cdn.example/notion.png", "source_url": "https://www.notion.so", "caption": "Notion interface", "alt": "Notion"},
        ]
        out = SEOMetadata.inject_seo_and_assets(body, "Title", "Desc", public_screenshot_items=items)
        self.assertLess(out.index("How Obsidian Works"), out.index("obsidian.png"))
        self.assertLess(out.index("obsidian.png"), out.index("How Notion Works"))
        self.assertLess(out.index("How Notion Works"), out.index("notion.png"))
        self.assertLess(out.index("notion.png"), out.index("Sources &amp; References"))
        self.assertEqual(out.count('class="article-screenshot"'), 2)

    def test_unmatched_screenshot_falls_back_before_sources_not_before_intro(self):
        out = self._inject(public_screenshot_items=[{
            "url": "https://cdn.example/s.png", "source_url": "https://example.org", "caption": "Example", "alt": "Example"
        }])
        self.assertLess(out.index("<p>Body</p>"), out.index("s.png"))

    def test_screenshot_markup_has_real_newlines_not_literal_backslash_n(self):
        out = self._inject(public_screenshot_url="https://cdn.example/s.png")
        self.assertNotIn(r"\n  <img", out)
        self.assertNotIn(r"\n  <figcaption", out)
        self.assertIn("\n  <img", out)

    def test_no_cover_without_a_url(self):
        self.assertNotIn("article-cover", self._inject())

    def test_unsafe_urls_are_never_embedded(self):
        for bad in ("http://cdn.example/x.jpg", "output/featured/x.jpg", "https://localhost/x.jpg", "https://127.0.0.1/x.jpg"):
            self.assertNotIn("article-cover", self._inject(featured_image_url=bad), bad)


class TestPipelineWiring(unittest.TestCase):
    def _run(self, **cfg_overrides):
        captured = {}
        original = SEOMetadata.inject_seo_and_assets

        def spy(*args, **kwargs):
            captured.update(kwargs)
            return original(*args, **kwargs)

        fake = FeaturedImage(True, Path("output/featured/x.jpg"), "a" * 64, "Cover alt", "https://cdn.example/x.jpg")
        with tempfile.TemporaryDirectory() as tmp, \
             patch("src.main.prepare_featured_image", return_value=fake) as prep, \
             patch.object(SEOMetadata, "inject_seo_and_assets", side_effect=spy):
            cfg = load_config({"dry_run": True, "output_dir": os.path.join(tmp, "out"),
                               "processed_json_path": os.path.join(tmp, "s.json"), **cfg_overrides})
            code = pipeline.run_pipeline(cfg, target_topic_id="free-ai-research-tools-students")
        return code, captured, prep

    def test_cover_url_reaches_the_published_html(self):
        code, captured, prep = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(captured["featured_image_url"], "https://cdn.example/x.jpg")
        self.assertEqual(captured["featured_image_alt"], "Cover alt")
        self.assertTrue(prep.call_args.kwargs["enabled"])
        self.assertTrue(prep.call_args.kwargs["dry_run"])

    def test_the_setting_turns_the_feature_off(self):
        _, _, prep = self._run(featured_image_enabled=False)
        self.assertFalse(prep.call_args.kwargs["enabled"])


if __name__ == "__main__":
    unittest.main()

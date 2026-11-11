"""Tests for header image rendering: HTML, generator and validation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.featured_image import (
    JPEG_MAGIC,
    FeaturedImageGenerator,
    _title_size,
    build_html,
    _topic_family,
    PALETTES,
)

FAKE_JPEG = JPEG_MAGIC + b"\x00" * 3000


def _fake_render(self, page_html, out_path):
    Path(out_path).write_bytes(FAKE_JPEG)


def _chromium_available():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


class TestBuildHtml(unittest.TestCase):
    def test_title_is_escaped_and_nothing_executable_is_added(self):
        tag = "scr" + "ipt"  # built in pieces so this file never contains a literal script tag
        page = build_html(f"<{tag}>alert(1)</{tag}> Guide & Tips", "AI <b>Tools</b>", "seed")
        self.assertNotIn(f"<{tag}", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; Guide &amp; Tips", page)
        self.assertIn("AI &lt;B&gt;TOOLS&lt;/B&gt;", page)

    def test_brand_is_present_and_there_are_no_external_assets(self):
        page = build_html("Notion Setup Guide", "Tutorial", "seed")
        self.assertIn("The Digital Toolkit", page)
        self.assertNotIn("https://", page)
        for external in ("http://", "https://", "url(", "@import"):
            self.assertNotIn(external, page)

    def test_topic_families_have_distinct_visual_palettes(self):
        self.assertEqual(_topic_family("Best AI Tools", "AI and AI Tools"), "ai")
        self.assertEqual(_topic_family("Notion productivity workspace", "Software"), "software")
        self.assertEqual(_topic_family("Freelance invoicing for business", "Business"), "business")
        self.assertEqual(_topic_family("How to set up your account", "Tutorial"), "tutorial")
        self.assertEqual(len(set(PALETTES.values())), len(PALETTES))

    def test_thumbnail_contains_topic_palette_and_no_remote_assets(self):
        ai = build_html("Best AI Tools", "AI Tools", "ai")
        business = build_html("Freelance invoicing", "Digital Business", "biz")
        self.assertIn(PALETTES["ai"][1], ai)
        self.assertIn(PALETTES["business"][1], business)
        self.assertNotEqual(ai, business)
        for page in (ai, business):
            self.assertNotIn("http://", page)
            self.assertNotIn("https://", page)
            self.assertNotIn("@import", page)

    def test_placeholder_like_text_in_the_title_is_not_substituted(self):
        page = build_html("__KICKER__ and __BRAND__", "Guide", "seed")
        self.assertIn("__KICKER__ and __BRAND__", page)
        self.assertEqual(page.count("GUIDE"), 1)

    def test_longer_titles_get_smaller_type_with_a_floor(self):
        sizes = [_title_size(n) for n in (20, 40, 55, 70, 120)]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual(sizes[-1], 46)

    def test_decoration_is_deterministic_per_slug_but_differs_between_slugs(self):
        self.assertEqual(build_html("T", "K", "a"), build_html("T", "K", "a"))
        self.assertNotEqual(build_html("T", "K", "a"), build_html("T", "K", "b"))


class TestGenerator(unittest.TestCase):
    def test_success_returns_hash_and_accurate_alt_text(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(FeaturedImageGenerator, "_render_png", _fake_render):
            img = FeaturedImageGenerator(tmp).generate("Notion Setup Guide", "Tutorial", "notion-setup")
        self.assertTrue(img.success)
        self.assertEqual(img.file_path.suffix, ".jpg")
        self.assertEqual(len(img.sha256), 64)
        self.assertEqual(img.alt_text, "Editorial cover graphic for: Notion Setup Guide")

    def test_invalid_image_data_is_rejected(self):
        def bad(self, page_html, out_path):
            Path(out_path).write_bytes(b"not an image" * 500)

        with tempfile.TemporaryDirectory() as tmp, patch.object(FeaturedImageGenerator, "_render_png", bad):
            img = FeaturedImageGenerator(tmp).generate("T", "K", "slug")
        self.assertFalse(img.success)
        self.assertIn("valid JPEG", img.error_message)

    def test_render_error_is_swallowed_not_raised(self):
        def boom(self, page_html, out_path):
            raise RuntimeError("browser crashed")

        with tempfile.TemporaryDirectory() as tmp, patch.object(FeaturedImageGenerator, "_render_png", boom):
            img = FeaturedImageGenerator(tmp).generate("T", "K", "slug")
        self.assertFalse(img.success)
        self.assertIn("browser crashed", img.error_message)

    def test_slug_cannot_escape_the_output_folder(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(FeaturedImageGenerator, "_render_png", _fake_render):
            img = FeaturedImageGenerator(tmp).generate("T", "K", "../../etc/Pass wd")
            self.assertTrue(str(img.file_path.resolve()).startswith(str(Path(tmp).resolve())))
        self.assertEqual(img.file_path.name, "etc-pass-wd.jpg")

    @unittest.skipUnless(_chromium_available(), "Chromium is not installed here")
    def test_real_render_produces_a_reasonably_small_jpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = FeaturedImageGenerator(tmp).generate("How to Set Up Notion for Project Management", "Tutorial", "real")
            data = img.file_path.read_bytes()
        self.assertTrue(img.success, img.error_message)
        self.assertTrue(data.startswith(JPEG_MAGIC))
        self.assertTrue(20_000 < len(data) < 250_000, len(data))


if __name__ == "__main__":
    unittest.main()

"""Regression tests for optional article visual tooling."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.visual_tools import (
    audit_html_accessibility,
    generate_supporting_visuals,
    inject_visual_figures,
    optimize_image,
    render_mermaid_blocks,
)


class TestVisualHelpers(unittest.TestCase):
    def test_mermaid_blocks_are_ignored_when_not_present(self):
        body = "<p>Plain article body.</p>"
        rendered, items = render_mermaid_blocks(body, "output")
        self.assertEqual(rendered, body)
        self.assertEqual(items, [])

    def test_mermaid_detection_requires_mermaid_class(self):
        body = '<pre class="language-python">print("hello")</pre>'
        rendered, items = render_mermaid_blocks(body, "output")
        self.assertEqual(rendered, body)
        self.assertEqual(items, [])

    def test_supporting_visual_generation_is_disabled_by_default(self):
        with patch.dict(os.environ, {"IMAGE_GENERATION_ENABLED": "false"}, clear=False):
            self.assertEqual(generate_supporting_visuals([{"prompt": "A scene"}], "output"), [])

    def test_supporting_visual_generation_is_capped_at_two(self):
        with patch.dict(os.environ, {"IMAGE_GENERATION_ENABLED": "true"}, clear=False), \
             patch("src.visual_tools.generate_gemini_image") as generate:
            generate.side_effect = lambda prompt, path, **kw: Path(path)
            with patch("src.visual_tools.Path.mkdir"):
                items = generate_supporting_visuals(
                    [{"prompt": "one", "alt_text": "one", "caption": "", "section_heading": "One"},
                     {"prompt": "two", "alt_text": "two", "caption": "", "section_heading": "Two"},
                     {"prompt": "three", "alt_text": "three", "caption": "", "section_heading": "Three"}],
                    "output",
                )
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(len(items), 2)

    def test_custom_visual_is_inserted_after_its_section_paragraph(self):
        body = "<h2>Battery Saving</h2><p>First explanation.</p><p>More detail.</p><h2>Next</h2>"
        items = [{"url": "https://cdn.example/photo.webp", "alt": "Laptop workspace",
                  "caption": "A focused workspace", "section_heading": "Battery Saving"}]
        out = inject_visual_figures(body, items)
        self.assertLess(out.index("First explanation"), out.index("photo.webp"))
        self.assertLess(out.index("photo.webp"), out.index("More detail"))

    def test_non_https_visual_is_not_injected(self):
        body = "<p>Article</p>"
        out = inject_visual_figures(body, [{"url": "http://cdn.example/photo.jpg", "alt": "Photo"}])
        self.assertEqual(out, body)

    def test_optimizer_keeps_original_when_sharp_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "image.jpg"
            source.write_bytes(b"image")
            with patch("src.visual_tools.SHARP_SCRIPT", Path(tmp) / "missing.mjs"):
                self.assertEqual(optimize_image(source), source)

    def test_accessibility_audit_reports_missing_tool_without_crashing(self):
        with patch("src.visual_tools.AXE_JS", Path("/missing/axe.min.js")):
            result = audit_html_accessibility("<p>Article</p>")
        self.assertFalse(result["available"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()

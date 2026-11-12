"""Regression tests for optional article visual tooling."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.visual_tools import (
    AXE_JS, MERMAID_JS, audit_html_accessibility,
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

    @unittest.skipUnless(MERMAID_JS.is_file(), "Mermaid package is not installed")
    def test_mermaid_renders_to_svg_in_playwright(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "diagram.svg"
            render_mermaid_blocks(
                '<pre class="mermaid">flowchart TD; A[Start] --> B[Finish]</pre>',
                tmp,
            )
            from src.visual_tools import render_mermaid_svg
            render_mermaid_svg("flowchart TD; A[Start] --> B[Finish]", output)
            self.assertIn("<svg", output.read_text(encoding="utf-8"))

    def test_supporting_visuals_render_local_svg_without_image_api(self):
        plan = [{"prompt": "A simple workflow showing input, processing and output",
                 "alt_text": "Three stages of an automated workflow",
                 "caption": "A simple view of the process",
                 "section_heading": "How the workflow works"}]
        with tempfile.TemporaryDirectory() as tmp, \
             patch("src.visual_tools.generate_gemini_image") as generate:
            def publish(path, slug, digest):
                self.assertTrue(path.read_text(encoding="utf-8").startswith("<svg"))
                self.assertEqual(path.suffix, ".svg")
                self.assertEqual(len(digest), 64)
                return "https://cdn.example/" + slug + ".svg"

            items = generate_supporting_visuals(plan, tmp, publisher=publish)
            generate.assert_not_called()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["kind"], "illustration")
            self.assertEqual(items[0]["url"], "https://cdn.example/supporting-1.svg")

    def test_supporting_visual_generation_is_capped_at_two(self):
        plans = [
            {"prompt": f"Concept {i}", "alt_text": f"Concept {i}",
             "caption": "", "section_heading": f"Section {i}"}
            for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            items = generate_supporting_visuals(
                plans, tmp,
                publisher=lambda path, slug, digest: "https://cdn.example/" + slug + ".svg",
            )
            self.assertEqual(len(items), 2)

    def test_supporting_visuals_skip_incomplete_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            items = generate_supporting_visuals(
                [{"prompt": "Concept only", "alt_text": "", "section_heading": "Section"}],
                tmp,
                publisher=lambda path, slug, digest: "https://cdn.example/" + slug + ".svg",
            )
            self.assertEqual(items, [])

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

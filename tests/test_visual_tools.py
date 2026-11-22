"""Regression tests for optional article visual tooling."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.visual_tools import (
    AXE_JS, MERMAID_JS, ARTICLE_FRAGMENT_EXCLUDED_AXE_RULES, audit_html_accessibility,
    generate_supporting_visuals,
    inject_visual_figures,
    optimize_image,
    render_mermaid_blocks,
    _validate_mermaid_svg,
)


class TestVisualHelpers(unittest.TestCase):
    def test_mermaid_svg_validation_accepts_valid_viewbox(self):
        self.assertTrue(_validate_mermaid_svg(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400"><text>Step</text></svg>'
        ))

    def test_mermaid_svg_validation_rejects_missing_or_invalid_dimensions(self):
        self.assertFalse(_validate_mermaid_svg('<svg xmlns="http://www.w3.org/2000/svg"></svg>'))
        self.assertFalse(_validate_mermaid_svg(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 400"></svg>'
        ))
        self.assertFalse(_validate_mermaid_svg('<svg'))

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

    def test_mermaid_render_failure_replaces_source_with_accessible_note(self):
        body = '<pre class="mermaid">flowchart TD; A[Start] --> B[Finish]</pre>'
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.visual_tools.render_mermaid_svg", side_effect=RuntimeError("renderer unavailable")
        ):
            rendered, items = render_mermaid_blocks(
                body, tmp, publisher=lambda *args: "https://cdn.example/x.svg"
            )
        self.assertNotIn("flowchart TD", rendered)
        self.assertIn("diagram-note", rendered)
        self.assertEqual(items[0]["status"], "omitted")

    def test_mermaid_without_public_host_is_not_left_as_raw_source(self):
        body = '<pre class="mermaid">flowchart TD; A[Start] --> B[Finish]</pre>'
        def fake_render(source, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>',
                encoding="utf-8",
            )
            return output_path
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.visual_tools.render_mermaid_svg", side_effect=fake_render
        ):
            rendered, items = render_mermaid_blocks(body, tmp)
        self.assertNotIn("flowchart TD", rendered)
        self.assertIn("diagram-note", rendered)
        self.assertEqual(items[0]["status"], "rendered_unhosted")

    def test_mermaid_block_over_limit_is_removed_from_reader_facing_html(self):
        body = (
            '<pre class="mermaid">flowchart TD; A[First] --> B[Second]</pre>'
            '<pre class="mermaid">flowchart TD; C[Third] --> D[Fourth]</pre>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            rendered, items = render_mermaid_blocks(body, tmp, max_items=0)
        self.assertNotIn("flowchart TD", rendered)
        self.assertEqual(rendered.count("diagram-note"), 2)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["status"] == "omitted" for item in items))

    def test_mermaid_with_successful_public_host_is_replaced_by_image(self):
        body = '<pre class="mermaid">flowchart TD; A[Start] --> B[Finish]</pre>'
        def fake_render(source, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>',
                encoding="utf-8",
            )
            return output_path
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.visual_tools.render_mermaid_svg", side_effect=fake_render
        ):
            rendered, items = render_mermaid_blocks(
                body, tmp, publisher=lambda *args: "https://cdn.example/diagram.svg"
            )
        self.assertNotIn("flowchart TD", rendered)
        self.assertIn("https://cdn.example/diagram.svg", rendered)
        self.assertEqual(items[0]["status"], "hosted")

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

    def test_missing_or_none_visual_url_is_skipped(self):
        body = "<p>Article</p>"
        for item in (
            {"url": None, "alt": "No hosted image"},
            {"alt": "Missing URL"},
            {"url": 123, "alt": "Invalid URL type"},
            None,
        ):
            with self.subTest(item=item):
                self.assertEqual(inject_visual_figures(body, [item]), body)

    def test_supporting_visuals_without_public_url_are_kept_unembedded(self):
        plan = [{"prompt": "A workflow", "alt_text": "Workflow", "caption": "",
                 "section_heading": "How it works"}]
        with tempfile.TemporaryDirectory() as tmp:
            for publisher_result in (None, 123, "http://cdn.example/image.svg"):
                items = generate_supporting_visuals(
                    plan, tmp, publisher=lambda path, slug, digest: publisher_result
                )
                self.assertEqual(len(items), 1)
                self.assertIsNone(items[0]["url"])


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
        self.assertIn("document-title", result["excluded_rules"])
        self.assertIn("html-has-lang", result["excluded_rules"])
        self.assertIn("page-has-heading-one", ARTICLE_FRAGMENT_EXCLUDED_AXE_RULES)


if __name__ == "__main__":
    unittest.main()

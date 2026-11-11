"""Tests for article layout: styled components, table of contents and HTML sanitising."""

import os
import re
import tempfile
import unittest
from pathlib import Path

from src import main as pipeline
from src.article_writer import ArticleWriter
from src.config import load_config
from src.layout import add_table_of_contents, apply_layout, deduplicate_reference_sections, sanitize_html
from src.research import ResearchCollector
from src.state_store import StateStore
from src.topic_discovery import TopicDiscovery

S = "scr" + "ipt"  # built in pieces so this file never contains a literal script tag
H2 = "<h2>One</h2><p>a</p><h2>Two</h2><p>b</p><h2>Three</h2><p>c</p><h2>Four</h2><p>d</p>"


class TestCallouts(unittest.TestCase):
    def test_each_component_gets_a_label_role_and_inline_style(self):
        out = apply_layout(
            '<div class="quick-answer"><p>Short answer.</p></div>'
            '<div class="tip"><p>A tip.</p></div><div class="warning"><p>Careful.</p></div>'
        )
        for label in ("Quick answer", "Tip", "Heads up"):
            self.assertIn(f">{label}</p>", out)
        self.assertEqual(out.count('role="note"'), 3)
        self.assertEqual(out.count("border-left:4px solid"), 3)
        self.assertIn("rgba(", out)  # translucent, so it works on light and dark themes

    def test_unknown_classes_are_left_alone(self):
        body = '<div class="mystery"><p>x</p></div>'
        self.assertEqual(apply_layout(body), body)

    def test_content_inside_the_callout_is_kept(self):
        self.assertIn("Use the free plan first.", apply_layout('<div class="tip"><p>Use the free plan first.</p></div>'))


class TestStepsAndTables(unittest.TestCase):
    def test_steps_list_items_are_spaced(self):
        out = apply_layout('<ol class="steps"><li>One</li><li>Two</li></ol>')
        self.assertEqual(out.count('<li style="margin-bottom:10px;">'), 2)

    def test_plain_ordered_lists_are_untouched(self):
        body = "<ol><li>One</li></ol>"
        self.assertEqual(apply_layout(body), body)

    def test_compare_table_is_wrapped_for_mobile_and_styled(self):
        out = apply_layout('<table class="compare"><thead><tr><th>A</th></tr></thead><tbody><tr><td>x</td></tr></tbody></table>')
        self.assertIn("overflow-x:auto", out)
        self.assertIn('<th style="', out)
        self.assertIn('<td style="', out)

    def test_markdown_pipe_table_is_converted_and_styled(self):
        body = "| Tool | Best for |\n| --- | :---: |\n| Alpha | Research |\n| Beta | Writing |"
        out = apply_layout(body)
        self.assertIn('<table class="compare">', out)
        self.assertIn("<th>Tool</th>", out)
        self.assertIn("<td>Research</td>", out)
        self.assertIn("overflow-x:auto", out)
        self.assertNotIn("| --- |", out)
    def test_other_tables_are_untouched(self):
        body = "<table><tr><td>x</td></tr></table>"
        self.assertEqual(apply_layout(body), body)


class TestTableOfContents(unittest.TestCase):
    def test_four_headings_get_ids_and_a_contents_list_before_the_first_one(self):
        out = add_table_of_contents(H2)
        self.assertIn('aria-label="Table of contents"', out)
        self.assertLess(out.index("Table of contents"), out.index("<h2"))
        for slug in ("one", "two", "three", "four"):
            self.assertIn(f'<a href="#{slug}">', out)
            self.assertIn(f'<h2 id="{slug}"', out)

    def test_fewer_than_four_headings_get_no_contents_list(self):
        self.assertEqual(add_table_of_contents("<h2>A</h2><h2>B</h2><h2>C</h2>"), "<h2>A</h2><h2>B</h2><h2>C</h2>")

    def test_duplicate_headings_get_unique_ids(self):
        out = add_table_of_contents("<h2>Tips</h2><h2>Tips</h2><h2>Tips</h2><h2>Other</h2>")
        ids = re.findall(r'<h2 id="([^"]+)"', out)
        self.assertEqual(len(ids), len(set(ids)))

    def test_heading_text_is_escaped_in_the_list(self):
        out = add_table_of_contents("<h2>Tom &amp; Jerry</h2>" + H2)
        self.assertIn("Tom &amp; Jerry</a>", out)

    def test_applying_twice_changes_nothing(self):
        once = apply_layout(H2)
        self.assertEqual(apply_layout(once), once)


class TestReferenceSections(unittest.TestCase):

    def test_duplicate_reference_sections_are_removed(self):
        body = (
            "<h2>Guide</h2><p>Useful article text.</p>"
            "<h2>Sources &amp; References</h2><ul><li>Source A</li></ul>"
            "<h2>References &amp; Resources</h2><ul><li>Source B</li></ul>"
        )
        out = apply_layout(body)
        self.assertEqual(len(re.findall(r"<h2[^>]*>[^<]*(?:Sources|References)", out)), 1)
        self.assertIn("Source A", out)
        self.assertNotIn("Source B", out)


class TestSanitize(unittest.TestCase):
    def test_scripts_embeds_and_handlers_are_removed(self):
        dirty = (
            f"<p>ok</p><{S}>alert(1)</{S}><{S} src='x.js'>"
            '<iframe src="https://evil.example"></iframe><img src="a.jpg" onerror="alert(2)">'
            '<a href="javascript:alert(3)">x</a><form action="/x"><input></form>'
        )
        clean = sanitize_html(dirty)
        for bad in (f"<{S}", "<iframe", "onerror", "javascript:", "<form"):
            self.assertNotIn(bad, clean)
        self.assertIn("<p>ok</p>", clean)

    def test_normal_markup_survives(self):
        body = '<p>See <a href="https://example.com/doc">the docs</a>.</p><pre style="padding:8px;"><code>x = 1</code></pre><img src="https://cdn.example/a.jpg" alt="a">'
        self.assertEqual(sanitize_html(body), body)


class TestWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_layout_guide_is_in_the_prompt_and_missing_file_is_harmless(self):
        topic = TopicDiscovery("data/topics.csv", StateStore(os.path.join(self.tmp.name, "s.json"))).select_next_topic()
        brief = ResearchCollector().conduct_research(topic.id, topic.topic, topic.category, topic.target_url, zambia_context=False, dry_run=True)
        prompt = ArticleWriter(api_key="k")._render_prompt(topic, brief)
        self.assertIn("Layout Components", prompt)
        self.assertIn('class="quick-answer"', prompt)
        self.assertNotIn("Layout Components", ArticleWriter(api_key="k", layout_guide_path="nope.md")._render_prompt(topic, brief))

    def test_dry_run_saves_the_finished_styled_post_for_review(self):
        cfg = load_config({"dry_run": True, "output_dir": os.path.join(self.tmp.name, "out"),
                           "processed_json_path": os.path.join(self.tmp.name, "s.json")})
        self.assertEqual(pipeline.run_pipeline(cfg, target_topic_id="free-ai-research-tools-students"), 0)
        final = Path(cfg.output_dir, "final.html").read_text(encoding="utf-8")
        draft = Path(cfg.output_dir, "draft.html").read_text(encoding="utf-8")
        self.assertIn('role="note"', final)  # components are styled in the published version
        self.assertNotIn('role="note"', draft)  # ...and the raw draft keeps the plain components
        self.assertIn('aria-label="Table of contents"', final)
        self.assertIn("overflow-x:auto", final)
        self.assertNotIn(f"<{S}>alert", final)


if __name__ == "__main__":
    unittest.main()

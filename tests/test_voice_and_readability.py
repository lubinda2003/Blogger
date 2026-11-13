"""Tests for the consistent voice, plain-English measurement and honesty guards."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.article_writer import ArticleDraft, ArticleWriter
from src.quality_checks import QualityGate
from src.readability import analyze, prose_text
from src.research import ResearchCollector
from src.seo_metadata import SEOMetadata
from src.state_store import StateStore
from src.topic_discovery import TopicDiscovery

PLAIN = "<p>Open the app and click New page. Name the page after your project. Add a table to track tasks. " * 1 + "</p>"
DENSE = (
    "<p>Utilizing comprehensive project management functionality, organizations can systematically orchestrate "
    "interdisciplinary collaboration across distributed environments while simultaneously maintaining "
    "synchronization of deliverables and stakeholder expectations throughout implementation phases.</p>"
)


def _draft(html, **kw):
    base = dict(
        topic_id="t", title="Practical Guide to Freelance Copy Editing",
        meta_description="A clear, step-by-step walkthrough detailing copy editing workflows for freelance editors.",
        labels=["AI Tools", "Freelancing"], html_content=html, summary="s", sources_used=[],
        primary_intent="Tutorial", word_count=900, last_checked_date="October 2026", is_dry_run_fixture=False,
        affiliate_disclosure_required=False, screenshot_needed=False,
    )
    base.update(kw)
    return ArticleDraft(**base)


class TestReadability(unittest.TestCase):
    def test_plain_text_scores_easy_and_dense_text_scores_hard(self):
        self.assertLess(analyze(PLAIN).fk_grade, 6)
        hard = analyze(DENSE)
        self.assertGreater(hard.fk_grade, 20)
        self.assertTrue(hard.is_hard(11.0))

    def test_code_tables_headings_and_sources_are_ignored(self):
        html = (
            "<h2>Utilizing comprehensive interdisciplinary orchestration</h2><p>Click the button.</p>"
            "<pre>def utilize_comprehensive_functionality(): pass</pre><table><tr><td>x</td></tr></table>"
            '<div class="article-sources"><ul><li>Some long source title here</li></ul></div>'
        )
        self.assertEqual(prose_text(html), "Click the button. .".replace(" .", "").strip() + ".")  # only the paragraph remains
        self.assertEqual(analyze(html).words, 3)

    def test_list_items_without_full_stops_count_as_sentences(self):
        self.assertEqual(analyze("<ul><li>Pick a template</li><li>Invite one teammate</li></ul>").sentences, 2)


class TestQualityGateVoice(unittest.TestCase):
    def setUp(self):
        self.gate = QualityGate(min_word_count=0, min_sources=0, is_live_mode=False)

    def _run(self, html):
        return self.gate.run_all_checks(_draft(html), check_duplicate=False)

    def test_hard_to_read_article_is_rejected(self):
        report = self._run(DENSE * 8)
        self.assertTrue(any("Readability check failed" in f for f in report.failures), report.failures)

    def test_plain_article_has_no_readability_failure(self):
        report = self._run("<p>Open the app and click New page. Name it after your project. Add a table to track tasks.</p>" * 20)
        self.assertFalse(any("Readability" in f for f in report.failures), report.failures)

    def test_short_text_is_not_judged_on_readability(self):
        self.assertFalse(any("Readability" in f for f in self._run(DENSE).failures))

    def test_invented_first_hand_testing_is_rejected(self):
        for claim in ("We tested all seven tools for a week.", "I personally prefer this one.",
                      "In my experience, the free plan is enough.", "Our own testing showed fast results.",
                      "After I tried it, I used it daily."):
            report = self._run(f"<p>{claim}</p>")
            self.assertTrue(any("Honesty check failed" in f for f in report.failures), claim)

    def test_attributed_statements_are_allowed(self):
        report = self._run("<p>According to the official docs, you can use the free plan. We recommend starting small.</p>")
        self.assertFalse(any("Honesty check" in f for f in report.failures), report.failures)

    def test_new_hype_phrases_are_rejected(self):
        report = self._run("<p>This ultimate guide will supercharge your workflow.</p>")
        self.assertTrue(any("cliché" in f for f in report.failures))


class TestWriterVoiceAndSimplify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.topic = TopicDiscovery("data/topics.csv", StateStore(os.path.join(self.tmp.name, "s.json"))).select_next_topic()
        self.brief = ResearchCollector().conduct_research(
            self.topic.id, self.topic.topic, self.topic.category, self.topic.target_url, zambia_context=False, dry_run=True)
        self.writer = ArticleWriter(api_key="k", min_word_count=0)
        base = self.writer._generate_dry_run_fixture(self.topic, self.brief)
        link = '<a href="https://example.com/doc">doc</a>'
        self.hard = dict(base, html_content=(DENSE + f"<p>See {link}.</p>") * 10)
        self.easy = dict(base, html_content=(PLAIN + f"<p>See {link}.</p>") * 10)

    def _call(self, parsed, responses):
        with patch.object(self.writer, "_call_llm_provider", side_effect=responses) as call:
            out = self.writer._simplify_if_hard(parsed)
        return out, call

    def test_voice_guide_is_added_to_the_prompt(self):
        prompt = self.writer._render_prompt(self.topic, self.brief)
        self.assertIn("Voice Guide: The Digital Toolkit", prompt)
        self.assertIn("Never say you or we tested", prompt)

    def test_missing_voice_guide_is_harmless(self):
        w = ArticleWriter(api_key="k", voice_guide_path="does/not/exist.md")
        self.assertNotIn("Voice Guide", w._render_prompt(self.topic, self.brief))

    def test_easy_draft_is_left_alone(self):
        out, call = self._call(self.easy, [])
        self.assertIs(out, self.easy)
        call.assert_not_called()

    def test_hard_draft_is_rewritten_once(self):
        out, call = self._call(self.hard, [json.dumps(self.easy)])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(out["html_content"], self.easy["html_content"])

    def test_rewrite_that_drops_a_link_is_rejected(self):
        no_link = dict(self.easy, html_content=PLAIN * 10)
        out, _ = self._call(self.hard, [json.dumps(no_link)])
        self.assertIs(out, self.hard)

    def test_rewrite_that_is_not_easier_is_rejected(self):
        out, _ = self._call(self.hard, [json.dumps(self.hard)])
        self.assertIs(out, self.hard)

    def test_failed_rewrite_keeps_original(self):
        out, _ = self._call(self.hard, [RuntimeError("boom")])
        self.assertIs(out, self.hard)

    def test_rewrite_below_minimum_length_is_rejected(self):
        self.writer.min_word_count = 150
        tiny = dict(self.easy, html_content="<p>Click here.</p><p>See <a href=\"https://example.com/doc\">doc</a>.</p>")
        out, _ = self._call(self.hard, [json.dumps(tiny)])
        self.assertIs(out, self.hard)


class TestHonestAuthor(unittest.TestCase):
    def test_default_author_is_the_publication_not_an_invented_person(self):
        data = json.loads(SEOMetadata.generate_schema_jsonld("T", "D").split("\n", 1)[1].rsplit("\n</script>", 1)[0])
        self.assertEqual(data["author"], {
            "@type": "Organization",
            "name": "The Digital Toolkit",
            "url": "https://digitaltoolkitguide.blogspot.com/p/about-digital-toolkit.html",
        })

    def test_a_real_configured_author_is_used_as_a_person(self):
        data = json.loads(SEOMetadata.generate_schema_jsonld("T", "D", author_name="Jane Doe").split("\n", 1)[1].rsplit("\n</script>", 1)[0])
        self.assertEqual(data["author"], {"@type": "Person", "name": "Jane Doe"})


if __name__ == "__main__":
    unittest.main()

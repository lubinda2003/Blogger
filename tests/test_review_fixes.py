"""Regression tests for bugs found in the November 2026 code review."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src import main as pipeline
from src.article_writer import ArticleWriter
from src.blogger_client import BloggerClient
from src.config import load_config
from src.research import ResearchCollector
from src.screenshot_capture import ScreenshotResult
from src.seo_metadata import SEOMetadata


def _cfg(tmp, dry_run=True):
    return load_config({
        "dry_run": dry_run,
        "output_dir": os.path.join(tmp, "out"),
        "processed_json_path": os.path.join(tmp, "state.json"),
    })


class TestDraftBackup(unittest.TestCase):
    def test_draft_json_and_html_are_saved(self):
        """main.py used json without importing it, so draft.json was empty and draft.html never written."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp)
            self.assertEqual(pipeline.run_pipeline(cfg, target_topic_id="free-ai-research-tools-students"), 0)
            with open(os.path.join(cfg.output_dir, "draft.json"), encoding="utf-8") as f:
                self.assertIn("title", json.load(f))
            self.assertGreater(os.path.getsize(os.path.join(cfg.output_dir, "draft.html")), 100)


class TestOptionalScreenshot(unittest.TestCase):
    def test_optional_screenshot_failure_does_not_crash_or_fail_qa(self):
        orig = ArticleWriter.write_article

        def needs_shot(self, topic, brief, dry_run=False):
            d = orig(self, topic, brief, dry_run)
            d.screenshot_needed = True
            return d

        failed = ScreenshotResult(url="https://consensus.app", success=False, error_message="timeout")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(ArticleWriter, "write_article", needs_shot), \
             patch("src.main.ScreenshotCapture") as capturer:
            capturer.return_value.capture.return_value = failed
            # topic does not set requires_screenshot -> failure must be non-fatal
            code = pipeline.run_pipeline(_cfg(tmp), target_topic_id="free-ai-research-tools-students")
        self.assertEqual(code, 0)


class TestFailureRecording(unittest.TestCase):
    def test_insufficient_research_counts_as_failure_in_live_mode_only(self):
        from src.research import ResearchBrief

        def weak(*a, **k):
            return ResearchBrief(topic_id="t", topic_title="t", target_url="", insufficient_evidence=True, notes="only 0 verified")

        for live in (True, False):
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.object(ResearchCollector, "conduct_research", weak), \
                 patch("src.main.BloggerClient") as bc:
                bc.return_value.reconcile_existing_post.return_value = None
                cfg = _cfg(tmp, dry_run=not live)
                cfg.blogger_blog_id = cfg.blogger_client_id = "1"
                cfg.blogger_client_secret = cfg.blogger_refresh_token = cfg.gemini_api_key = "x"
                code = pipeline.run_pipeline(cfg, target_topic_id="free-ai-research-tools-students")
                self.assertEqual(code, 1)
                with open(cfg.processed_json_path, encoding="utf-8") as f:
                    attempts = json.load(f).get("failed_attempts", {})
                self.assertEqual(attempts.get("free-ai-research-tools-students", 0), 1 if live else 0)


class TestBloggerReconcile(unittest.TestCase):
    def test_payload_has_hidden_marker_but_no_public_label(self):
        c = BloggerClient(blog_id="1", client_id="a", client_secret="b", refresh_token="c")
        payload = c.build_post_payload("T", "<p>x</p>", ["Tech"], topic_id="foo")
        self.assertIn("<!-- topic_id: foo -->", payload["content"])
        self.assertEqual(payload["labels"], ["Tech"])

    def test_marker_match_is_exact_and_lists_drafts(self):
        c = BloggerClient(blog_id="1", client_id="a", client_secret="b", refresh_token="c")
        c._access_token = "tok"
        body = json.dumps({"items": [{"id": "9", "url": "u", "title": "Other", "status": "DRAFT",
                                      "content": "<p>x</p><!-- topic_id: foo-bar -->"}]}).encode()
        seen = {}

        def fake_urlopen(req, timeout=0):
            seen["url"] = req.full_url
            resp = MagicMock()
            resp.read.return_value = body
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            self.assertIsNone(c.reconcile_existing_post("", topic_id="foo"))  # 'foo' must not match 'foo-bar'
            self.assertIsNotNone(c.reconcile_existing_post("", topic_id="foo-bar"))
        for status in ("status=draft", "status=live"):
            self.assertIn(status, seen["url"])


class TestResearchExtraction(unittest.TestCase):
    PAGE = (
        "<html><head><title>Notion Help</title></head><body>"
        "<noscript>Please enable JavaScript to use this site.</noscript>"
        "<header><div>" + "".join(f"<a>Menu item {i}</a>" for i in range(60)) + "</div></header>"
        "<main><h1>Real article</h1><p>" + "Useful sentence about databases and templates. " * 30 + "</p></main>"
        "</body></html>"
    )

    def _fetch(self):
        rc = ResearchCollector()
        resp = MagicMock()
        resp.status = 200
        resp.url = "https://example.com/help"
        resp.read.return_value = self.PAGE.encode()
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            return rc, rc.verify_and_fetch_source("https://example.com/help")

    def test_noscript_notice_does_not_reject_valid_page(self):
        _, result = self._fetch()
        self.assertTrue(result[0], result[-1])

    def test_cleaned_text_skips_menu_chrome(self):
        rc, _ = self._fetch()
        text = rc._clean_corpus_text(self.PAGE)
        self.assertNotIn("Menu item", text)
        self.assertIn("Useful sentence", text)

    def test_real_error_page_still_rejected(self):
        rc = ResearchCollector()
        page = "<html><head><title>404 Not Found</title></head><body><h1>Page not found</h1>" + "x " * 100 + "</body></html>"
        resp = MagicMock()
        resp.status = 200
        resp.url = "https://example.com/x"
        resp.read.return_value = page.encode()
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            self.assertFalse(rc.verify_and_fetch_source("https://example.com/x")[0])


class TestLabelsAndModels(unittest.TestCase):
    def test_mixed_case_labels_preserved(self):
        out = SEOMetadata.normalize_labels(["NotebookLM", "iPhone", "ai tools", "google docs"])
        self.assertEqual(out, ["NotebookLM", "iPhone", "AI Tools", "Google Docs"])

    def test_default_fallback_model_is_not_retired_1_5(self):
        self.assertNotIn("1.5", load_config().gemini_fallback_model)
        self.assertNotIn("1.5", ArticleWriter(api_key="k").fallback_model)


class TestLengthRequirementAndFailover(unittest.TestCase):
    """A live run produced 538 words and failed the 800-word gate because the prompt never mentioned a minimum."""

    def setUp(self):
        from src.state_store import StateStore
        from src.topic_discovery import TopicDiscovery

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.topic = TopicDiscovery("data/topics.csv", StateStore(os.path.join(self.tmp.name, "s.json"))).select_next_topic()
        self.brief = ResearchCollector().conduct_research(
            self.topic.id, self.topic.topic, self.topic.category, self.topic.target_url, zambia_context=False, dry_run=True
        )
        self.writer = ArticleWriter(api_key="k", min_word_count=800)
        fixture = self.writer._generate_dry_run_fixture(self.topic, self.brief)
        self.long = fixture
        self.short = dict(fixture, html_content="<h2>Intro</h2><p>" + "word " * 100 + "</p>")

    def _write(self, responses):
        with patch.object(self.writer, "_call_llm_provider", side_effect=responses) as call:
            draft = self.writer.write_article(self.topic, self.brief, dry_run=False)
        return draft, call

    def test_prompt_states_the_minimum_length(self):
        prompt = self.writer._render_prompt(self.topic, self.brief)
        self.assertIn("at least 800 words", prompt)
        self.assertIn("about 1100", prompt)

    def test_prompt_has_no_length_section_when_disabled(self):
        w = ArticleWriter(api_key="k", min_word_count=0)
        self.assertNotIn("Length Requirement", w._render_prompt(self.topic, self.brief))

    def test_short_draft_is_expanded_once(self):
        draft, call = self._write([json.dumps(self.short), json.dumps(self.long)])
        self.assertEqual(call.call_count, 2)
        self.assertGreaterEqual(draft.word_count, 800)
        current = self.writer._count_words(self.short["html_content"])
        self.assertIn(f"only {current} words", call.call_args_list[1].args[0])  # expansion prompt names the current length

    def test_long_enough_draft_is_not_expanded(self):
        draft, call = self._write([json.dumps(self.long)])
        self.assertEqual(call.call_count, 1)

    def test_failed_expansion_keeps_original_draft(self):
        draft, call = self._write([json.dumps(self.short), RuntimeError("boom")])
        self.assertEqual(call.call_count, 2)
        self.assertLess(draft.word_count, 800)  # unchanged; the quality gate will reject it as before

    def test_expansion_that_is_not_longer_keeps_original(self):
        tiny = dict(self.short, html_content="<p>tiny</p>")
        draft, call = self._write([json.dumps(self.short), json.dumps(tiny)])
        self.assertLess(draft.word_count, 800)
        self.assertIn("word", draft.html_content)

    def test_primary_model_gets_three_attempts_fallback_gets_default(self):
        seen = []

        def fake(prompt, model_name=None, max_tokens=None, is_token_retry=False, max_attempts=None):
            seen.append((model_name, max_attempts))
            if model_name == self.writer.model_name:
                raise RuntimeError("503")
            return "{}"

        with patch.object(self.writer, "_call_gemini_rest", side_effect=fake):
            self.writer._call_llm_provider("p")
        self.assertEqual(seen[0][1], 3)
        self.assertIsNone(seen[1][1])

    def test_main_passes_min_word_count_to_writer(self):
        with tempfile.TemporaryDirectory() as tmp, patch("src.main.ArticleWriter", wraps=ArticleWriter) as aw:
            cfg = _cfg(tmp)
            cfg.min_word_count = 950
            pipeline.run_pipeline(cfg, target_topic_id="free-ai-research-tools-students")
        self.assertEqual(aw.call_args.kwargs["min_word_count"], 950)


class TestRepoImageHosting(unittest.TestCase):
    """Blogger cannot upload images, so screenshots are committed to the repo and served through jsDelivr."""

    def _png(self, tmp):
        from pathlib import Path
        p = Path(tmp) / "shot.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 6000)
        return p

    def _capture(self, tmp):
        from src.screenshot_capture import ScreenshotCapture
        return ScreenshotCapture(output_dir=os.path.join(tmp, "out"), repo_assets_dir=os.path.join(tmp, "assets/screenshots"))

    ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "lubinda2003/Blogger", "GITHUB_REF_NAME": "main"}

    def test_returns_cdn_url_only_after_successful_push(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append([c for c in cmd if not c.startswith(("user.", "-c"))])
            out = MagicMock()
            out.stdout = " A assets/x.png" if "status" in cmd else ""
            return out

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, self.ENV), patch("subprocess.run", fake_run):
            url = self._capture(tmp).publish_to_repo_assets(self._png(tmp), "notion-project-management-setup", "a" * 64)
        self.assertTrue(url.startswith("https://cdn.jsdelivr.net/gh/lubinda2003/Blogger@main/"))
        self.assertIn("notion-project-management-setup-aaaaaaaaaa.png", url)
        verbs = [c[1] for c in calls]
        self.assertEqual(verbs, ["add", "status", "commit", "pull", "push"])

    def test_push_failure_means_no_image_not_a_broken_link(self):
        import subprocess as sp

        def boom(cmd, **kw):
            if "push" in cmd:
                raise sp.CalledProcessError(1, cmd, stderr="rejected")
            out = MagicMock()
            out.stdout = " A x"
            return out

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, self.ENV), patch("subprocess.run", boom):
            self.assertIsNone(self._capture(tmp).publish_to_repo_assets(self._png(tmp), "slug", "b" * 64))

    def test_disabled_outside_github_actions(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"GITHUB_ACTIONS": "", "GITHUB_REPOSITORY": "a/b"}), \
             patch("subprocess.run") as run:
            self.assertIsNone(self._capture(tmp).publish_to_repo_assets(self._png(tmp), "slug", "c" * 64))
            run.assert_not_called()

    def test_already_committed_image_skips_commit(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            out = MagicMock()
            out.stdout = ""  # git status clean: identical image already in repo
            return out

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, self.ENV), patch("subprocess.run", fake_run):
            url = self._capture(tmp).publish_to_repo_assets(self._png(tmp), "slug", "d" * 64)
        self.assertIsNotNone(url)
        self.assertFalse(any("commit" in c or "push" in c for c in calls))

    def test_slug_is_sanitised(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, self.ENV), patch("subprocess.run") as run:
            run.return_value.stdout = ""
            url = self._capture(tmp).publish_to_repo_assets(self._png(tmp), "../../etc/Pass wd", "e" * 64)
        self.assertNotIn("..", url)
        self.assertIn("etc-pass-wd-eeeeeeeeee.png", url)


if __name__ == "__main__":
    unittest.main()

"""Main CLI orchestrator for the Blogger Content Automation Engine."""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from src.article_writer import ArticleWriter
from src.blogger_client import BloggerClient
from src.config import AppConfig, load_config
from src.quality_checks import QualityGate
from src.report import PipelineReporter
from src.research import ResearchCollector
from src.screenshot_capture import ScreenshotCapture
from src.seo_metadata import SEOMetadata
from src.state_store import StateStore
from src.topic_discovery import TopicDiscovery

# Configure logging with structured clean formatting
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def _record_failure(state_store: StateStore, config: AppConfig, topic, message: str) -> None:
    """Count a permanent failure against a topic (never in dry-run, so test runs don't mutate state)."""
    if config.dry_run:
        return
    try:
        state_store.record_failure(topic.id, topic.topic, message)
    except Exception as e:  # never mask the original failure
        logger.warning(f"Could not record failure for topic '{topic.id}': {e}")


def run_pipeline(
    config: AppConfig,
    target_topic_id: Optional[str] = None,
    stage_limit: str = "all",
) -> int:
    """Execute the full editorial pipeline stages safely with fail-closed gates.

    Returns process exit code: 0 for success, 1 for critical failure.
    """
    reporter = PipelineReporter(output_dir=config.output_dir)
    reporter.dry_run = config.dry_run
    reporter.mode = config.publish_mode

    logger.info("=" * 65)
    logger.info("Starting Blogger Content Automation Pipeline")
    logger.info(f"Execution Mode: {'DRY RUN (Test Fixtures)' if config.dry_run else 'LIVE PRODUCTION'}")
    logger.info(f"Publish Target: {config.publish_mode.upper()} (Draft default enforced)")
    logger.info("=" * 65)

    # -------------------------------------------------------------
    # Stage 1: Validation
    # -------------------------------------------------------------
    t0 = time.time()
    validation_errors = config.validate_for_mode(stage=stage_limit)
    if validation_errors:
        for err in validation_errors:
            logger.error(f"Configuration error: {err}")
        reporter.add_stage(
            stage_name="Validation",
            status="FAILED",
            duration_seconds=time.time() - t0,
            details=f"Configuration validation failed: {validation_errors[0]}",
        )
        reporter.finalize(success=False, next_action="Review environment variables and credentials in GitHub Secrets.")
        return 1

    reporter.add_stage(
        stage_name="Validation",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details="Environment and configuration validated successfully.",
    )

    # -------------------------------------------------------------
    # Stage 2: Topic Selection & State Store Consultation
    # -------------------------------------------------------------
    t0 = time.time()
    state_store = StateStore(config.processed_json_path)

    # Fail closed if repository state store cannot be persisted or verified
    try:
        state_store.verify_persistence()
    except Exception as e:
        fail_msg = f"[STATE PERSISTENCE HALT] Repository state file ({config.processed_json_path}) is not accessible or writable: {e}"
        logger.error(fail_msg)
        reporter.add_stage(
            stage_name="Topic Selection",
            status="FAILED",
            duration_seconds=time.time() - t0,
            details=fail_msg,
        )
        reporter.finalize(
            success=False,
            next_action="Verify repository write permissions and data/processed_topics.json file integrity.",
        )
        return 1

    discovery = TopicDiscovery(csv_path=config.topics_csv_path, state_store=state_store)
    topic = discovery.select_next_topic(requested_id=target_topic_id)

    if not topic:
        logger.info("No eligible unprocessed topics found in queue. Safe no-op.")
        reporter.add_stage(
            stage_name="Topic Selection",
            status="SUCCESS",
            duration_seconds=time.time() - t0,
            details="Topic queue exhausted or all topics already processed. Pipeline completed safely.",
        )
        reporter.finalize(success=True, next_action="Add new topic entries to data/topics.csv.")
        return 0

    reporter.selected_topic_id = topic.id
    reporter.selected_topic = topic.topic

    topic_details = f"Selected topic '{topic.topic}' (Priority {topic.priority}) [Repository state active]"

    reporter.add_stage(
        stage_name="Topic Selection",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details=topic_details,
    )

    if stage_limit == "discover":
        reporter.finalize(success=True, next_action="Stage limit reached: discover.")
        return 0

    # -------------------------------------------------------------
    # Pre-Generation Idempotency Check on Blogger
    # -------------------------------------------------------------
    blogger = BloggerClient(
        blog_id=config.blogger_blog_id,
        client_id=config.blogger_client_id,
        client_secret=config.blogger_client_secret,
        refresh_token=config.blogger_refresh_token,
    )

    if not config.dry_run:
        try:
            existing_post = blogger.reconcile_existing_post(topic.topic, topic_id=topic.id)
            if existing_post:
                logger.warning(f"Blogger post already exists for '{topic.topic}' (ID: {existing_post.post_id}).")
                state_store.record_success(
                    topic_id=topic.id,
                    topic_title=topic.topic,
                    post_id=existing_post.post_id,
                    post_url=existing_post.post_url,
                    mode="draft" if existing_post.is_draft else "publish",
                )
                reporter.post_id = existing_post.post_id
                reporter.post_url = existing_post.post_url
                reporter.add_stage(
                    stage_name="Pre-check Reconciliation",
                    status="SUCCESS",
                    duration_seconds=0.0,
                    details=f"Reconciled existing Blogger post {existing_post.post_id}. Skipped duplicate generation.",
                )
                reporter.finalize(success=True, next_action="Post already exists. No new post created.")
                return 0
        except Exception as e:
            logger.error(f"Pre-check reconciliation failed: {e}. Failing closed to prevent duplicates.")
            reporter.add_stage(
                stage_name="Pre-check Reconciliation",
                status="FAILED",
                duration_seconds=0.0,
                details=f"Reconciliation error: {e}",
            )
            reporter.finalize(success=False, next_action="Fix Blogger API credentials or check blog connectivity.")
            return 1

    # -------------------------------------------------------------
    # Stage 3: Live Research & Fact Verification
    # -------------------------------------------------------------
    t0 = time.time()
    researcher = ResearchCollector(
        tavily_api_key=config.tavily_api_key,
        domain_allowlist=config.research_domain_allowlist,
        domain_blocklist=config.research_domain_blocklist,
    )
    brief = researcher.conduct_research(
        topic_id=topic.id,
        topic_title=topic.topic,
        category=topic.category,
        target_url=topic.target_url,
        zambia_context=config.zambia_context_enabled,
        dry_run=config.dry_run,
    )

    reporter.research_sources = [s.to_dict() for s in brief.sources]
    reporter.source_count = len(brief.verified_sources())
    if brief.insufficient_evidence:
        details_msg = brief.notes or "Fewer than 2 verified sources found. Factual evidence insufficient."
        logger.error(f"Research stage failed closed: {details_msg}")
        _record_failure(state_store, config, topic, details_msg)
        reporter.add_stage(
            stage_name="Research",
            status="FAILED",
            duration_seconds=time.time() - t0,
            details=details_msg,
        )
        reporter.finalize(success=False, next_action="Provide reachable, authoritative source URLs for this topic.")
        return 1

    stage_label = "[DRY-RUN FIXTURES]" if config.dry_run else "[LIVE HTTP VERIFICATION]"
    reporter.add_stage(
        stage_name="Research",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details=f"{stage_label} Verified {reporter.source_count} sources.",
    )

    if stage_limit == "research":
        reporter.finalize(success=True, next_action="Stage limit reached: research.")
        return 0

    # -------------------------------------------------------------
    # Stage 4: Article Generation (Gemini API)
    # -------------------------------------------------------------
    t0 = time.time()
    writer = ArticleWriter(
        api_key=config.gemini_api_key,
        model_name=config.gemini_model,
        fallback_model=config.gemini_fallback_model,
        temperature=config.gemini_temperature,
        max_tokens=config.gemini_max_tokens,
        prompt_template_path=config.template_prompt_path,
        provider=config.llm_provider,
        groq_api_key=config.groq_api_key,
        groq_model=config.groq_model,
        min_word_count=config.min_word_count,
    )

    try:
        draft = writer.write_article(topic, brief, dry_run=config.dry_run)
    except Exception as e:
        logger.error(f"Article generation failed closed: {e}")
        reporter.add_stage(
            stage_name="Article Generation",
            status="FAILED",
            duration_seconds=time.time() - t0,
            details=f"LLM generation failure: {e}",
        )
        reporter.finalize(success=False, next_action="Check Gemini API key quota, model availability, and network.")
        return 1

    gen_mode = (
        "Dry-run text fixture"
        if draft.is_dry_run_fixture
        else f"Live {draft.actual_provider} ({draft.actual_model})"
    )
    reporter.add_stage(
        stage_name="Article Generation",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details=f"Generated draft '{draft.title}' ({draft.word_count} words, {gen_mode}).",
    )

    if stage_limit == "write":
        reporter.finalize(success=True, next_action="Stage limit reached: write.")
        return 0

    # Save draft.json and draft.html to output/ on every run, including rejected drafts
    try:
        os.makedirs(config.output_dir, exist_ok=True)
        with open(os.path.join(config.output_dir, "draft.json"), "w", encoding="utf-8") as f:
            json.dump(draft.to_dict(), f, indent=2, ensure_ascii=False)
        with open(os.path.join(config.output_dir, "draft.html"), "w", encoding="utf-8") as f:
            f.write(draft.html_content)
    except Exception as e:
        logger.warning(f"Failed to save draft backup files to output/: {e}")

    # -------------------------------------------------------------
    # Stage 5: Screenshot Capture (Playwright)
    # -------------------------------------------------------------
    t0 = time.time()
    screenshot_res = None
    if draft.screenshot_needed:
        capturer = ScreenshotCapture(
            output_dir=os.path.join(config.output_dir, "screenshots"),
            viewport_width=config.screenshot_viewport_width,
            viewport_height=config.screenshot_viewport_height,
            timeout_ms=config.screenshot_timeout_ms,
        )
        screenshot_res = capturer.capture(
            url=topic.target_url,
            slug=topic.id,
            alt_text=draft.screenshot_alt_text or draft.title,
            caption=draft.screenshot_caption or f"Screenshot for {topic.topic}",
            mock_mode=config.dry_run,
        )

        reporter.screenshot_captured = bool(screenshot_res and screenshot_res.success)
        if not screenshot_res.success:
            if topic.requires_screenshot:
                logger.error(f"Required screenshot capture failed closed: {screenshot_res.error_message}")
                _record_failure(state_store, config, topic, screenshot_res.error_message)
                reporter.add_stage(
                    stage_name="Screenshot Capture",
                    status="FAILED",
                    duration_seconds=time.time() - t0,
                    details=screenshot_res.error_message,
                )
                reporter.finalize(success=False, next_action="Verify target URL is accessible without auth walls.")
                return 1
            else:
                warn_msg = screenshot_res.error_message
                logger.warning(f"Optional screenshot capture failed: {warn_msg}. Continuing without image.")
                screenshot_res = None
                draft.screenshot_needed = False  # nothing to validate; QA must not demand it
                reporter.add_stage(
                    stage_name="Screenshot Capture",
                    status="SKIPPED",
                    duration_seconds=time.time() - t0,
                    details=f"Optional screenshot failed ({warn_msg}); published without image.",
                )

        if screenshot_res is not None:
            img_hosted_msg = (
                f"Hosted: {screenshot_res.public_url}"
                if screenshot_res.public_url
                else "Saved locally; omitted from HTML to prevent broken links"
            )
            reporter.add_stage(
                stage_name="Screenshot Capture",
                status="SUCCESS",
                duration_seconds=time.time() - t0,
                details=f"Captured image ({screenshot_res.file_size_bytes} bytes). {img_hosted_msg}",
            )
    else:
        reporter.add_stage(
            stage_name="Screenshot Capture",
            status="SKIPPED",
            duration_seconds=0.0,
            details="Topic does not require software interface screenshots.",
        )

    if stage_limit == "screenshot":
        reporter.finalize(success=True, next_action="Stage limit reached: screenshot.")
        return 0

    # -------------------------------------------------------------
    # Stage 6: Hard Quality Gate (QA)
    # -------------------------------------------------------------
    t0 = time.time()
    gate = QualityGate(
        min_word_count=config.min_word_count,
        min_sources=config.min_credible_sources,
        state_store=state_store,
        is_live_mode=not config.dry_run,
    )

    verified_urls = {s.url for s in brief.verified_sources()}

    qa_report = gate.run_all_checks(
        draft=draft,
        screenshot_result=screenshot_res,
        verified_source_urls=verified_urls if not config.dry_run else None,
        check_duplicate=not config.dry_run,
    )

    reporter.qa_passed = qa_report.passed
    reporter.qa_failures = qa_report.failures
    reporter.qa_warnings = qa_report.warnings

    if not qa_report.passed:
        logger.error(f"Quality gate rejected article: {qa_report.failures}")
        _record_failure(state_store, config, topic, qa_report.failures[0])
        reporter.add_stage(
            stage_name="Quality Gate",
            status="FAILED",
            duration_seconds=time.time() - t0,
            details=f"Rejected on hard check: {qa_report.failures[0]}",
        )
        reporter.finalize(
            success=False,
            next_action=f"Remediate QA failure: {qa_report.failures[0]} before publishing.",
        )
        return 1

    reporter.add_stage(
        stage_name="Quality Gate",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details=f"Passed all {len(qa_report.metrics)} quality criteria (Plain English & Safety verified).",
    )

    if stage_limit == "qa":
        reporter.finalize(success=True, next_action="Stage limit reached: qa.")
        return 0

    # -------------------------------------------------------------
    # Stage 7: Blogger Draft Creation / Publishing
    # -------------------------------------------------------------
    t0 = time.time()

    # Prepare final HTML - NEVER passes local paths
    public_img = screenshot_res.public_url if (screenshot_res and screenshot_res.success) else None
    final_html = SEOMetadata.inject_seo_and_assets(
        html_body=draft.html_content,
        title=draft.title,
        meta_description=draft.meta_description,
        public_screenshot_url=public_img,
        screenshot_caption=screenshot_res.caption if public_img else None,
        screenshot_alt=screenshot_res.alt_text if public_img else None,
    )

    normalized_labels = SEOMetadata.normalize_labels(draft.labels)
    is_draft = config.publish_mode != "publish"

    post_res = blogger.insert_post(
        title=draft.title,
        html_content=final_html,
        labels=normalized_labels,
        is_draft=is_draft,
        dry_run=config.dry_run,
        topic_id=topic.id,
    )

    if not post_res.success:
        logger.error(f"Blogger post creation failed: {post_res.error_message}")
        _record_failure(state_store, config, topic, post_res.error_message)
        reporter.add_stage(
            stage_name="Blogger Publication",
            status="FAILED",
            duration_seconds=time.time() - t0,
            details=post_res.error_message,
        )
        reporter.finalize(success=False, next_action="Review Blogger API credentials and OAuth permissions.")
        return 1

    if not config.dry_run:
        if not post_res.post_id or str(post_res.post_id).startswith("dryrun-") or not post_res.post_url or "example.blogger.com" in post_res.post_url:
            err_details = f"Live Blogger API response returned simulated or invalid post ID/URL (ID: {post_res.post_id}, URL: {post_res.post_url})"
            logger.error(err_details)
            reporter.add_stage(
                stage_name="Blogger Publication",
                status="FAILED",
                duration_seconds=time.time() - t0,
                details=err_details,
            )
            reporter.finalize(success=False, next_action="Verify Blogger API credentials and live network connectivity.")
            return 1

    reporter.post_id = post_res.post_id
    reporter.post_url = post_res.post_url

    post_mode_str = "Draft" if is_draft else "Public"
    reporter.add_stage(
        stage_name="Blogger Publication",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details=f"Created Blogger {post_mode_str} post (ID: {post_res.post_id})",
    )

    # -------------------------------------------------------------
    # Stage 8: State Persistence & State Update
    # -------------------------------------------------------------
    t0 = time.time()

    if config.dry_run:
        state_details = "Dry-run mode: state mutations skipped."
    else:
        try:
            state_store.record_success(
                topic_id=topic.id,
                topic_title=draft.title,
                post_id=post_res.post_id if post_res else None,
                post_url=post_res.post_url if post_res else None,
                mode=config.publish_mode,
                meta={"labels": normalized_labels, "word_count": draft.word_count},
            )
            state_details = f"Topic '{topic.id}' recorded in {config.processed_json_path} for repository persistence."
        except Exception as e:
            fail_msg = f"Failed to persist topic '{topic.id}' in repository state file: {e}"
            logger.error(fail_msg)
            reporter.add_stage(
                stage_name="State Persistence",
                status="FAILED",
                duration_seconds=time.time() - t0,
                details=fail_msg,
            )
            reporter.finalize(
                success=False,
                next_action="Check repository file write permissions for data/processed_topics.json.",
            )
            return 1

    reporter.add_stage(
        stage_name="State Persistence",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details=state_details,
    )

    # Finalize reports
    next_step = (
        "Inspect generated Blogger draft in Blogger Dashboard before approving for live publication."
        if is_draft
        else "Post is live on Blogger."
    )
    reporter.finalize(success=True, next_action=next_step)
    logger.info("Pipeline completed successfully!")
    return 0


def main() -> None:
    """CLI Entry point with flag parsing."""
    parser = argparse.ArgumentParser(
        description="Blogger Content Automation Engine - Scheduled GitHub Actions Pipeline",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Execute pipeline in dry-run mode without modifying Blogger state",
    )
    parser.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Execute pipeline in live mode (requires valid API credentials)",
    )
    parser.set_defaults(dry_run=None)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Execute pipeline using repository state (retained for backward compatibility)",
    )
    parser.add_argument(
        "--publish-mode",
        choices=["draft", "publish"],
        default=None,
        help="Publish mode: 'draft' (default) or 'publish'",
    )
    parser.add_argument(
        "--topic-id",
        type=str,
        default=None,
        help="Execute pipeline for a specific topic ID from data/topics.csv",
    )
    parser.add_argument(
        "--stage",
        choices=["all", "discover", "research", "write", "screenshot", "qa", "publish"],
        default="all",
        help="Execute up to a specific pipeline stage",
    )

    args = parser.parse_args()

    overrides = {}
    if args.dry_run is not None:
        overrides["dry_run"] = args.dry_run

    if args.local_only:
        overrides["local_only"] = True

    if args.publish_mode:
        overrides["publish_mode"] = args.publish_mode

    config = load_config(overrides=overrides)
    exit_code = run_pipeline(config=config, target_topic_id=args.topic_id, stage_limit=args.stage)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

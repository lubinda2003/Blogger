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
from src.featured_image import prepare_featured_image
from src.layout import apply_layout
from src.quality_checks import QualityGate
from src.report import PipelineReporter
from src.research import ResearchCollector
from src.screenshot_capture import ScreenshotCapture
from src.seo_metadata import SEOMetadata
from src.state_store import StateStore
from src.topic_discovery import TopicDiscovery
from src.autonomous_topic_discovery import AutonomousTopicDiscoverer
from src.topic_opportunity import TopicOpportunityScorer
from src.visual_tools import (
    audit_html_accessibility, capture_article_previews, generate_supporting_visuals,
    inject_visual_figures, render_mermaid_blocks,
)

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


def _build_screenshot_targets(topic, brief, needed: bool) -> list:
    """Return trusted screenshot URLs, with verified same-product pages as fallbacks.

    The topic's configured targets stay first. If a site blocks browser capture on its
    homepage, verified research pages on that same domain can still provide genuine UI
    screenshots. Unrelated third-party sources are never used as screenshot targets.
    """
    from urllib.parse import urlparse

    if not needed and not topic.screenshot_targets:
        return []

    targets = list(topic.screenshot_targets or [])
    if not targets and topic.target_url:
        targets.append(topic.target_url)

    target_host = (urlparse(topic.target_url).hostname or "").lower()
    if target_host.startswith("www."):
        target_host = target_host[4:]

    if target_host and brief:
        for source in brief.verified_sources():
            candidate = source.url
            parsed = urlparse(candidate)
            host = (parsed.hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            if parsed.scheme not in ("http", "https") or not host:
                continue
            if host == target_host or host.endswith("." + target_host):
                targets.append(candidate)

    # Preserve editorial order while removing duplicate URLs.
    return list(dict.fromkeys(url for url in targets if url))


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
    if target_topic_id:
        # Explicit operator-selected topics remain available from the optional CSV.
        topic = discovery.select_next_topic(requested_id=target_topic_id)
        opportunity_note = "Manual topic selection from the optional editorial ideas file."
    else:
        # Normal operation is autonomous: Tavily supplies fresh candidates across all four
        # publication pillars. The CSV is not required to keep the pipeline running.
        discoverer = AutonomousTopicDiscoverer(api_key=config.tavily_api_key)
        candidates = discoverer.discover(state_store)
        if candidates:
            topic = sorted(candidates, key=lambda item: (item.priority, item.id))[0]
            opportunity_note = discoverer.last_note
            logger.info("Autonomous discovery selected '%s' from %s candidates.", topic.topic, len(candidates))
        else:
            topic = None
            opportunity_note = discoverer.last_note
            logger.error(opportunity_note)

    if not topic:
        logger.error("Topic discovery produced no eligible article topic.")
        reporter.add_stage(
            stage_name="Topic Discovery",
            status="FAILED",
            duration_seconds=time.time() - t0,
            details=opportunity_note,
        )
        reporter.finalize(
            success=False,
            next_action="Check TAVILY_API_KEY and Tavily availability, then run discovery again. You do not need to add topics to data/topics.csv.",
        )
        return 1

    reporter.add_stage(
        stage_name="Topic Discovery",
        status="SUCCESS",
        duration_seconds=time.time() - t0,
        details=f"Selected '{topic.topic}' from live search opportunities. {opportunity_note}",
    )

    reporter.selected_topic_id = topic.id
    reporter.selected_topic = topic.topic

    topic_details = f"Selected topic '{topic.topic}' (Priority {topic.priority}) [Repository state active]. {opportunity_note}"

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
        max_reading_grade=config.max_reading_grade,
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
    # Topic-owned URLs are trusted editorial targets; the model cannot invent capture destinations.
    t0 = time.time()
    screenshot_results = []
    needs_screenshot = draft.screenshot_needed or topic.requires_screenshot or bool(topic.screenshot_targets)
    capture_targets = _build_screenshot_targets(topic, brief, needs_screenshot)
    if capture_targets:
        capturer = ScreenshotCapture(
            output_dir=os.path.join(config.output_dir, "screenshots"),
            viewport_width=config.screenshot_viewport_width,
            viewport_height=config.screenshot_viewport_height,
            timeout_ms=config.screenshot_timeout_ms,
        )
        for index, target_url in enumerate(capture_targets, start=1):
            from urllib.parse import urlparse
            host = urlparse(target_url).hostname or "product website"
            result = capturer.capture(
                url=target_url,
                slug=f"{topic.id}-{index}",
                alt_text=f"{host} interface screenshot",
                caption=f"Official {host} website interface",
                mock_mode=config.dry_run,
            )
            screenshot_results.append(result)
            if not result.success:
                logger.warning(f"Screenshot capture failed for {target_url}: {result.error_message}")

        screenshot_res = next((item for item in screenshot_results if item.success), None)
        if topic.requires_screenshot and screenshot_res is None:
            failures = "; ".join(
                f"{item.url}: {item.error_message or 'capture failed'}"
                for item in screenshot_results
            )
            failure_detail = f"All {len(screenshot_results)} trusted screenshot target(s) failed. {failures}"
            image_generation_enabled = os.getenv("IMAGE_GENERATION_ENABLED", "false").strip().lower() in ("true", "1", "yes", "on")
            if image_generation_enabled:
                logger.warning(
                    "%s Continuing because custom visual generation is enabled; "
                    "the article will rely on generated explanatory visuals instead of blocked screenshots.",
                    failure_detail,
                )
                reporter.add_stage(
                    stage_name="Screenshot Capture",
                    status="WARNING",
                    duration_seconds=time.time() - t0,
                    details=f"{failure_detail} Custom visuals will be used as the fallback.",
                )
            else:
                _record_failure(state_store, config, topic, failure_detail)
                reporter.add_stage(
                    stage_name="Screenshot Capture",
                    status="FAILED",
                    duration_seconds=time.time() - t0,
                    details=failure_detail,
                )
                reporter.finalize(
                    success=False,
                    next_action="Enable custom visual generation or add an accessible official screenshot target.",
                )
                return 1
        reporter.screenshot_captured = bool(screenshot_res)
        successes = sum(1 for item in screenshot_results if item.success)
        if successes:
            reporter.add_stage(
                stage_name="Screenshot Capture",
                status="SUCCESS",
                duration_seconds=time.time() - t0,
                details=f"Captured {successes} of {len(screenshot_results)} configured genuine website screenshot(s).",
            )
        else:
            # An optional screenshot is an enhancement, not a hard QA requirement.
            # Clear the draft flag when the capture failed; required topics already fail closed above.
            if not topic.requires_screenshot:
                draft.screenshot_needed = False
            reporter.add_stage(
                stage_name="Screenshot Capture",
                status="SKIPPED",
                duration_seconds=time.time() - t0,
                details="No usable screenshot was captured; no local or mock image will be embedded.",
            )
    else:
        screenshot_res = None
        reporter.add_stage(
            stage_name="Screenshot Capture",
            status="SKIPPED",
            duration_seconds=0.0,
            details="Neither the editorial topic nor the article requires an interface screenshot.",
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
        max_reading_grade=config.max_reading_grade,
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

    # Render authored Mermaid diagrams with the existing Playwright browser. In live mode,
    # host the SVGs in the repository; dry-runs keep source blocks for safe preview.
    article_body = draft.html_content
    diagram_assets = []
    try:
        diagram_publisher = None
        if not config.dry_run:
            diagram_host = ScreenshotCapture(
                output_dir=os.path.join(config.output_dir, "visuals"),
                repo_assets_dir="assets/visuals",
            )
            diagram_publisher = diagram_host.publish_to_repo_assets
        successful_screenshots = sum(1 for item in screenshot_results if item.success and not item.is_mock)
        article_body, diagram_assets = render_mermaid_blocks(
            article_body, config.output_dir, publisher=diagram_publisher,
            max_items=max(0, 3 - successful_screenshots),
        )
        if diagram_assets:
            reporter.add_stage(
                stage_name="Article Diagrams",
                status="SUCCESS" if all(item.get("path") for item in diagram_assets) else "WARNING",
                duration_seconds=0,
                details=f"Rendered {len(diagram_assets)} explanatory diagram(s); public embedding is limited to live runs.",
            )
    except Exception as exc:
        logger.warning("Article diagram rendering skipped without blocking the article: %s", exc)

    # Header image: generated per article and hosted from the repo in live runs. Never fatal.
    t_img = time.time()
    featured = prepare_featured_image(
        enabled=config.featured_image_enabled,
        dry_run=config.dry_run,
        title=draft.title,
        kicker=topic.category,
        slug=topic.id,
        output_dir=config.output_dir,
        brief=draft.featured_image_brief,
    )
    if featured is not None:
        if featured.public_url:
            img_status, img_details = "SUCCESS", f"Generated and hosted: {featured.public_url}"
        elif featured.success:
            img_status, img_details = "SUCCESS", "Generated (saved under output/featured) but not embedded: dry-run or hosting unavailable."
        else:
            img_status, img_details = "SKIPPED", f"Not generated: {featured.error_message}"
        reporter.add_stage(
            stage_name="Featured Image",
            status=img_status,
            duration_seconds=time.time() - t_img,
            details=img_details,
        )

    # -------------------------------------------------------------
    # Stage 7: Blogger Draft Creation / Publishing
    # -------------------------------------------------------------
    t0 = time.time()

    # Prepare final HTML - NEVER passes local paths
    public_screenshot_items = [
        {"url": item.public_url, "source_url": item.url, "caption": item.caption, "alt": item.alt_text}
        for item in screenshot_results
        if item.success and item.public_url and not item.is_mock
    ][:3]
    visual_publisher = None
    if not config.dry_run:
        visual_host = ScreenshotCapture(
            output_dir=os.path.join(config.output_dir, "visuals"),
            repo_assets_dir="assets/visuals",
        )
        visual_publisher = visual_host.publish_to_repo_assets
    supporting_visuals = generate_supporting_visuals(
        draft.visual_plan,
        config.output_dir,
        publisher=visual_publisher,
        max_items=max(0, 3 - len(public_screenshot_items) - len(diagram_assets)),
    )
    article_body = inject_visual_figures(article_body, supporting_visuals)
    final_html = SEOMetadata.inject_seo_and_assets(
        html_body=apply_layout(article_body),
        title=draft.title,
        meta_description=draft.meta_description,
        public_screenshot_items=public_screenshot_items,
        featured_image_url=featured.public_url if featured else None,
        featured_image_alt=featured.alt_text if featured else None,
    )

    # Accessibility and responsive previews are diagnostic: findings are recorded, never
    # allowed to silently discard a valid article or block Blogger draft creation.
    try:
        accessibility = audit_html_accessibility(
            final_html, os.path.join(config.output_dir, "accessibility-report.json")
        )
        if accessibility.get("available"):
            logger.info(
                "Article accessibility scan: %s violation(s), %s passed rule(s).",
                len(accessibility.get("violations", [])), accessibility.get("passes", 0),
            )
    except Exception as exc:
        logger.warning("Accessibility audit skipped without blocking publication: %s", exc)
    try:
        previews = capture_article_previews(final_html, config.output_dir)
        logger.info("Saved responsive article previews: %s", ", ".join(previews))
    except Exception as exc:
        logger.warning("Responsive article previews could not be captured: %s", exc)

    try:  # the finished post exactly as it will be published, for review in the run artifact
        os.makedirs(config.output_dir, exist_ok=True)
        with open(os.path.join(config.output_dir, "final.html"), "w", encoding="utf-8") as f:
            f.write(final_html)
    except Exception as e:
        logger.warning(f"Failed to save final.html: {e}")

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

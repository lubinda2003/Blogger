"""Hard quality gate engine enforcing editorial, structural, safety, and plain-English standards."""

import html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from src.article_writer import ArticleDraft
from src.screenshot_capture import ScreenshotResult
from src.state_store import StateStore


@dataclass
class QAReport:
    """Consolidated results of the Quality Assurance hard gate checks."""
    passed: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failures": self.failures,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


class QualityGate:
    """Enforces strict pre-publication gates. Fails closed on any hard check violation."""

    BANNED_PROMISES = [
        r"\bget\s+rich\s+quick\b",
        r"\bguaranteed\s+(?:income|wealth|profit|cash|\$\d+)\b",
        r"\bmake\s+\$\d+\s+(?:per\s+day|daily|today|in\s+your\s+sleep)\b",
        r"\bpassive\s+income\s+secret\b",
        r"\b100%\s+risk\s+free\s+money\b",
        r"\bovernight\s+millionaire\b",
        r"\bsecret\s+hack\s+to\s+wealth\b",
        r"\btransform\s+your\s+life\s+overnight\b",
    ]

    GENERIC_AI_CLICHES = [
        r"\bin\s+today'?s\s+fast[\s-]paced\s+digital\s+world\b",
        r"\bin\s+the\s+ever[\s-]evolving\s+landscape\b",
        r"\bunlock\s+the\s+power\s+of\b",
        r"\brevolutionize\s+the\s+way\s+you\b",
        r"\bdelve\s+into\s+the\s+(?:intricacies|depths|world)\b",
        r"\bembark\s+on\s+a\s+journey\b",
        r"\bgame[\s-]changer\b",
        r"\bgroundbreaking\s+strategies\b",
        r"\blook\s+no\s+further\b",
        r"\bwhether\s+you'?re\s+a\s+beginner\s+or\s+an\s+expert\b",
    ]

    ALLOWED_AFFILIATE_DOMAINS = {
        "upwork.com",
        "payoneer.com",
        "fnbzambia.co.zm",
        "stanbicbank.co.zm",
    }

    def __init__(
        self,
        min_word_count: int = 800,
        min_sources: int = 2,
        state_store: Optional[StateStore] = None,
        is_live_mode: bool = False,
    ):
        self.min_word_count = min_word_count
        self.min_sources = min_sources
        self.state_store = state_store or StateStore()
        self.is_live_mode = is_live_mode

    def run_all_checks(
        self,
        draft: ArticleDraft,
        screenshot_result: Optional[ScreenshotResult] = None,
        verified_source_urls: Optional[Set[str]] = None,
        check_duplicate: bool = True,
    ) -> QAReport:
        """Run all hard checks. If any check fails, publication is blocked."""
        failures: List[str] = []
        warnings: List[str] = []

        html_str = draft.html_content or ""
        clean_text = re.sub(r"<[^>]+>", " ", html_str)
        text_lower = clean_text.lower()

        # 0. Mock & Test Fixture Guard for Live Mode
        if self.is_live_mode:
            if draft.is_dry_run_fixture:
                failures.append("Live Guard failed: Dry-run test fixture cannot be published in live mode.")
            if screenshot_result and screenshot_result.is_mock:
                failures.append("Live Guard failed: Mock screenshot cannot be published in live mode.")

        # 1. Plain-English Style and Generic AI Cliché Check
        for pattern in self.GENERIC_AI_CLICHES:
            match = re.search(pattern, text_lower)
            if match:
                failures.append(
                    f"Writing Style failed: Generic AI cliché detected: '{match.group(0)}'. "
                    "Rewrite in plain, direct, natural English."
                )

        # 2. Banned Financial Promises & Fake Guarantees
        for pattern in self.BANNED_PROMISES:
            match = re.search(pattern, text_lower)
            if match:
                failures.append(
                    f"Policy check failed: Prohibited financial/guarantee claim detected matching '{match.group(0)}'."
                )

        # 3. Local Runner Paths Leakage Check (CRITICAL)
        # HTML must NEVER contain runner-local paths or debug file paths
        local_path_patterns = [
            r"output/screenshots/[^\s\"'>]+",
            r"/app/applet/[^\s\"'>]+",
            r"file://[^\s\"'>]+",
            r"localhost:\d+",
            r"127\.0\.0\.1",
        ]
        for pat in local_path_patterns:
            leaks = re.findall(pat, html_str, re.IGNORECASE)
            if leaks:
                failures.append(
                    f"Security/HTML check failed: Runner-local path or debug URL leaked into HTML content: '{leaks[0]}'."
                )

        # 4. Metadata and Title checks
        if not draft.title or len(draft.title.strip()) < 10:
            failures.append("Metadata check failed: Title is missing or shorter than 10 characters.")
        elif len(draft.title.strip()) > 95:
            warnings.append(f"Title is long ({len(draft.title)} chars). Recommended length is 40-70 chars.")

        if not draft.meta_description or len(draft.meta_description.strip()) < 50:
            failures.append("Metadata check failed: Meta description is missing or shorter than 50 characters.")
        elif len(draft.meta_description.strip()) > 200:
            warnings.append(f"Meta description is long ({len(draft.meta_description)} chars). Optimal length is 120-160 chars.")

        # 5. Content Length & Substantive Value
        words = re.findall(r"\b\w+\b", clean_text)
        word_count = len(words)
        if word_count < self.min_word_count:
            failures.append(
                f"Originality/Length check failed: Article contains {word_count} words, which is below the minimum "
                f"threshold of {self.min_word_count} words for a substantive educational guide."
            )

        # 6. HTML Validity & Markdown Leaks (ignore code blocks where # is valid syntax)
        clean_for_md_check = re.sub(r"<pre[^>]*>.*?</pre>", "", html_str, flags=re.DOTALL | re.IGNORECASE)
        clean_for_md_check = re.sub(r"<code[^>]*>.*?</code>", "", clean_for_md_check, flags=re.DOTALL | re.IGNORECASE)

        if re.search(r"(?:^|\n)#{1,4}\s+[^\n]+", clean_for_md_check):
            failures.append("HTML check failed: Raw Markdown headers ('###') detected inside HTML body.")

        if re.search(r"\[.+?\]\(https?://[^\)]+\)", clean_for_md_check):
            failures.append("HTML check failed: Raw Markdown links ('[text](url)') detected inside HTML body.")

        # Check tag balance
        for tag in ("h2", "h3", "p", "ul", "ol", "div"):
            open_count = len(re.findall(rf"<{tag}(?:\s+[^>]*)?>", html_str, re.IGNORECASE))
            close_count = len(re.findall(rf"</{tag}>", html_str, re.IGNORECASE))
            if open_count != close_count:
                failures.append(
                    f"HTML check failed: Tag <{tag}> is unbalanced (opened {open_count} times, closed {close_count} times)."
                )

        # 7. Real Sourced Evidence & Citations Verification
        if not draft.sources_used or len(draft.sources_used) < self.min_sources:
            failures.append(
                f"Sources check failed: Article cites {len(draft.sources_used or [])} sources, "
                f"failing the requirement of at least {self.min_sources} verified credible sources."
            )
        else:
            for s in draft.sources_used:
                url = s.get("url", "")
                if not url.startswith("http://") and not url.startswith("https://"):
                    failures.append(f"Sources check failed: Source URL '{url}' is malformed.")
                elif verified_source_urls is not None and url not in verified_source_urls:
                    # In live mode or when verified URLs list is supplied
                    failures.append(
                        f"Sources check failed: Cited source '{url}' was not verified during the research phase."
                    )

        # 8. Affiliate Disclosure
        found_links = re.findall(r'href=["\'](https?://[^"\']+)["\']', html_str, re.IGNORECASE)
        has_affiliate_link = any(any(dom in l for dom in self.ALLOWED_AFFILIATE_DOMAINS) for l in found_links)

        if has_affiliate_link:
            disclosure_pattern = r"(?:affiliate\s+disclosure|commission|we\s+may\s+earn)"
            if not re.search(disclosure_pattern, text_lower):
                failures.append(
                    "Disclosure check failed: Article contains commercial/affiliate links but lacks an explicit "
                    "affiliate disclosure callout."
                )

        # 9. Screenshot Checks for Visual Tutorials
        if draft.screenshot_needed:
            if not screenshot_result:
                failures.append("Screenshot check failed: Topic requires a screenshot, but no capture was provided.")
            elif not screenshot_result.success:
                failures.append(
                    f"Screenshot check failed: Required screenshot could not be captured ({screenshot_result.error_message})."
                )
            elif not screenshot_result.alt_text or len(screenshot_result.alt_text.strip()) < 5:
                failures.append("Screenshot check failed: Captured screenshot is missing descriptive alt text.")

        # 10. Duplicate Content Guard (Checks Normalized Content Fingerprint)
        if check_duplicate:
            if self.state_store.is_duplicate(draft.topic_id, draft.title):
                failures.append(
                    f"Duplicate guard failed: Topic '{draft.topic_id}' / '{draft.title}' has already been processed."
                )

        passed = len(failures) == 0
        return QAReport(
            passed=passed,
            failures=failures,
            warnings=warnings,
            metrics={
                "word_count": word_count,
                "sources_count": len(draft.sources_used or []),
                "labels_count": len(draft.labels or []),
                "screenshot_captured": bool(screenshot_result and screenshot_result.success),
                "has_public_screenshot": bool(screenshot_result and screenshot_result.public_url),
            },
        )

"""Hard quality gate engine enforcing editorial, structural, safety, and plain-English standards."""

import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from src.article_writer import ArticleDraft
from src.readability import analyze as analyze_readability
from src.screenshot_capture import ScreenshotResult
from src.state_store import StateStore
from src.research import ResearchCollector


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




GOOGLE_OFFICIAL_PRODUCT_DOMAINS = (
    "ai.google.dev",
    "cloud.google.com",
    "support.google.com",
    "workspace.google.com",
    "developers.googleblog.com",
    "blog.google",
)
GOOGLE_OFFICIAL_PRICING_DOMAINS = ("ai.google.dev", "cloud.google.com")


CLAIM_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for", "from",
    "has", "have", "how", "in", "into", "is", "it", "its", "of", "on", "or", "that",
    "the", "their", "this", "to", "use", "used", "using", "was", "were", "what", "when",
    "which", "with", "you", "your", "let", "lets", "allow", "allows",
}
CLAIM_NEGATIONS = {"no", "not", "never", "cannot", "can't", "doesn't", "don't", "without", "neither", "nor"}


def _claim_token_key(token: str) -> str:
    """Normalize common inflections and safe editorial paraphrases for claim matching."""
    token = token.casefold()
    aliases = {
        "revealed": "show", "showed": "show",
        "delivers": "give", "delivered": "give", "gives": "give",
        "citations": "source", "citation": "source", "links": "source", "link": "source",
        "supported": "source", "supporting": "source", "sources": "source",
        "discussions": "call", "discussion": "call", "meetings": "call", "meeting": "call",
        "flexible": "flexibility", "evaluating": "test", "evaluate": "test",
        "committing": "spend", "subscription": "plan", "subscriptions": "plan",
        "desire": "choose", "driven": "choose", "earn": "income",
    }
    if token in aliases:
        return aliases[token]
    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("ing") and len(token) > 5:
        token = token[:-3]
    elif token.endswith("ed") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("s") and len(token) > 3:
        token = token[:-1]
    return aliases.get(token, token)


def _normalized_claim_tokens(value: str) -> Set[str]:
    return {
        _claim_token_key(token)
        for token in re.findall(r"[a-z0-9]+", (value or "").casefold())
        if token not in CLAIM_STOP_WORDS and token not in {"largely", "looking", "inline"}
    }


def _evidence_text_for_matching(value: str) -> str:
    """Remove lightweight Markdown decoration while preserving linked evidence text."""
    text = html.unescape(str(value or ""))
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`~]{1,3}", "", text)
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text.casefold().strip()


def _claim_number_contexts(claim: str) -> List[tuple]:
    """Return each numeric marker and nearby claim terms that identify what it measures."""
    tokens = list(re.finditer(r"[a-z0-9]+", (claim or "").casefold()))
    contexts = []
    for index, match in enumerate(tokens):
        if not re.fullmatch(r"\d+(?:[.,]\d+)?%?", match.group()):
            continue
        nearby = [
            _claim_token_key(item.group())
            for item in tokens[max(0, index - 1):index] + tokens[index + 1:index + 3]
            if item.group() not in CLAIM_STOP_WORDS and not re.fullmatch(r"\d+(?:[.,]\d+)?%?", item.group())
        ]
        contexts.append((match.group().rstrip("%"), set(nearby)))
    return contexts


def claim_is_represented_in_article(claim: str, article_text: str) -> bool:
    """Match paraphrased claims in a local passage while keeping numbers and negation grounded."""
    claim_tokens = _normalized_claim_tokens(claim)
    if len(claim_tokens) < 3:
        return False

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", (article_text or "").casefold())
        if sentence.strip()
    ]
    if not sentences:
        return False

    negation_pattern = r"\b(?:no|not|never|cannot|can't|doesn't|don't|without|neither|nor)\b"
    claim_has_negation = bool(re.search(negation_pattern, claim.casefold()))
    number_contexts = _claim_number_contexts(claim)
    claim_numbers = {number for number, _ in number_contexts}

    # A claim can span a short paragraph (for example, a statistic explained over
    # two sentences). Do not compare against the whole article.
    for index in range(len(sentences)):
        for width in (1, 2, 3, 4):
            passage = sentences[index:index + width]
            window = " ".join(passage)
            window_tokens = _normalized_claim_tokens(window)
            coverage = len(claim_tokens & window_tokens) / len(claim_tokens)
            if coverage < 0.65:
                continue

            # Every number must occur in the passage and be anchored to at least one
            # nearby subject/context term from the claim in the same sentence.
            if number_contexts:
                valid_numbers = set()
                for sentence in passage:
                    sentence_numbers = {
                        number.rstrip("%")
                        for number in re.findall(r"\b\d+(?:[.,]\d+)?%?\b", sentence)
                    }
                    if not sentence_numbers:
                        continue
                    sentence_tokens = _normalized_claim_tokens(sentence)
                    for number, anchors in number_contexts:
                        if number in sentence_numbers and (not anchors or anchors & sentence_tokens):
                            valid_numbers.add(number)
                if not claim_numbers.issubset(valid_numbers):
                    continue

            if claim_has_negation != bool(re.search(negation_pattern, window)):
                continue
            return True
    return False


def has_official_google_source(source_urls, pricing: bool = False) -> bool:
    """Return True only when a citation URL belongs to an official Google product source."""
    allowed = GOOGLE_OFFICIAL_PRICING_DOMAINS if pricing else GOOGLE_OFFICIAL_PRODUCT_DOMAINS
    for url in source_urls or []:
        try:
            host = (urlparse(url).hostname or "").lower()
        except (TypeError, ValueError):
            continue
        if any(host == domain or host.endswith("." + domain) for domain in allowed):
            return True
    return False


def normalize_url(url: str) -> str:
    """Normalize a URL by stripping http(s)://, leading www., and trailing slashes for comparison."""
    if not url:
        return ""
    u = url.strip()
    u = re.sub(r"^https?://", "", u, flags=re.IGNORECASE)
    u = re.sub(r"^www\.", "", u, flags=re.IGNORECASE)
    parts = u.split("/", 1)
    domain = parts[0].lower()
    path = "/" + parts[1] if len(parts) > 1 else ""
    return f"{domain}{path}".rstrip("/")


class _FinalHTMLInspector(HTMLParser):
    """Collect structural and security signals from the completed Blogger HTML fragment."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = set()
        self.ids = set()
        self.duplicate_ids = set()
        self.images_without_alt = 0
        self.bad_images = []
        self.bad_links = []
        self.unsafe_attributes = []
        self.parse_errors = []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        values = {key.lower(): value for key, value in attrs if key}
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.duplicate_ids.add(element_id)
            self.ids.add(element_id)
        for key in values:
            if key.startswith("on"):
                self.unsafe_attributes.append(f"{tag}[{key}]")
        if tag.lower() == "img":
            if not values.get("alt", "").strip():
                self.images_without_alt += 1
            src = values.get("src", "")
            if not src.startswith("https://"):
                self.bad_images.append(src or "(missing src)")
        if tag.lower() == "a":
            href = values.get("href", "").strip().lower()
            if href and not (href.startswith(("https://", "http://", "#", "mailto:"))):
                self.bad_links.append(values.get("href", ""))
            if values.get("target", "").lower() == "_blank":
                rel = set(values.get("rel", "").lower().split())
                if not {"noopener", "noreferrer"}.issubset(rel):
                    self.unsafe_attributes.append("a[target=_blank without noopener noreferrer]")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def error(self, message):
        self.parse_errors.append(message)


def validate_final_blogger_html(document: str) -> List[str]:
    """Validate the fully transformed Blogger fragment immediately before API submission."""
    failures: List[str] = []
    if not isinstance(document, str) or not document.strip():
        return ["Final HTML validation failed: document is empty."]
    inspector = _FinalHTMLInspector()
    try:
        inspector.feed(document)
        inspector.close()
    except Exception as exc:
        return [f"Final HTML validation failed: parser could not read document ({exc})."]
    schema_blocks = re.findall(
        r"""<script\b[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script\s*>""",
        document, flags=re.I | re.S,
    )
    if not schema_blocks:
        failures.append("Final HTML validation failed: BlogPosting structured data is missing.")
    else:
        try:
            schema = json.loads(schema_blocks[0])
            if schema.get("@type") != "BlogPosting":
                failures.append("Final HTML validation failed: structured data must use the Google-supported BlogPosting type.")
            if not str(schema.get("headline", "")).strip():
                failures.append("Final HTML validation failed: BlogPosting headline is missing.")
            if not str(schema.get("description", "")).strip():
                failures.append("Final HTML validation failed: BlogPosting description is missing.")
        except (TypeError, ValueError):
            failures.append("Final HTML validation failed: BlogPosting JSON-LD is not valid JSON.")
    if "dt-article-body" not in document:
        failures.append("Final HTML validation failed: styled article body wrapper is missing.")
    if "h2" not in inspector.tags:
        failures.append("Final HTML validation failed: article has no section headings (h2).")
    if "Sources &amp; References" not in document and "Sources & References" not in document:
        failures.append("Final HTML validation failed: visible Sources & References section is missing.")
    if inspector.duplicate_ids:
        failures.append("Final HTML validation failed: duplicate element IDs: " + ", ".join(sorted(inspector.duplicate_ids)) + ".")
    if inspector.images_without_alt:
        failures.append(f"Final HTML validation failed: {inspector.images_without_alt} image(s) have no descriptive alt text.")
    if inspector.bad_images:
        failures.append("Final HTML validation failed: image sources must be public HTTPS URLs (" + ", ".join(inspector.bad_images[:3]) + ").")
    if inspector.bad_links:
        failures.append("Final HTML validation failed: unsafe or unsupported link URL(s) detected.")
    if inspector.unsafe_attributes:
        failures.append("Final HTML validation failed: unsafe attributes or external-link protections missing (" + ", ".join(inspector.unsafe_attributes[:3]) + ").")
    return failures


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
        r"\bsupercharge\b",
        r"\bto\s+the\s+next\s+level\b",
        r"\bultimate\s+guide\b",
        r"\brevolutionary\b",
        r"\bit(?:'s|\s+is)\s+important\s+to\s+note\b",
    ]

    # The pipeline cannot verify personal experience, so any first-hand claim is invented by definition.
    FABRICATED_EXPERIENCE = [
        r"\b(?:i|we)\s+(?:have\s+|'ve\s+|personally\s+)?(?:tested|tried|used|spent)\b",
        r"\bin\s+my\s+(?:own\s+)?(?:experience|testing)\b",
        r"\bour\s+(?:own\s+)?(?:testing|tests|hands[\s-]on)\b",
        r"\bi\s+personally\b",
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
        max_reading_grade: float = 11.0,
    ):
        self.max_reading_grade = max_reading_grade
        self.min_word_count = min_word_count
        self.min_sources = min_sources
        self.state_store = state_store or StateStore()
        self.is_live_mode = is_live_mode

    def run_all_checks(
        self,
        draft: ArticleDraft,
        screenshot_result: Optional[ScreenshotResult] = None,
        verified_source_urls: Optional[Set[str]] = None,
        verified_source_evidence: Optional[List[Dict[str, Any]]] = None,
        check_duplicate: bool = True,
    ) -> QAReport:
        """Run all hard checks. If any check fails, publication is blocked."""
        failures: List[str] = []
        warnings: List[str] = []

        html_str = draft.html_content or ""
        clean_text = re.sub(r"<[^>]+>", " ", html_str)
        text_lower = clean_text.lower()

        # 0. Claim-level evidence verification. URL reachability alone is not proof.
        if self.is_live_mode:
            evidence_by_url = {
                normalize_url(item.get("url", "")): item
                for item in (verified_source_evidence or [])
                if item.get("verified") and item.get("url")
            }
            if not draft.claim_evidence:
                failures.append(
                    "Evidence check failed: live article has no claim_evidence mappings. "
                    "Every material factual claim must map to retrieved source text."
                )
            else:
                normalized_article_text = re.sub(r"\s+", " ", html.unescape(clean_text)).strip().casefold()
                for index, item in enumerate(draft.claim_evidence, start=1):
                    claim = re.sub(r"\s+", " ", str(item.get("claim", ""))).strip()
                    source_url = str(item.get("source_url", "")).strip()
                    quote = re.sub(r"\s+", " ", str(item.get("evidence_quote", ""))).strip()
                    if not claim or not source_url or not quote:
                        failures.append(f"Evidence check failed: claim mapping #{index} is incomplete.")
                        continue
                    if not claim_is_represented_in_article(claim, normalized_article_text):
                        failures.append(
                            f"Evidence check failed: mapped claim #{index} is not sufficiently represented in the article "
                            "(key terms, numeric values, and negation must be preserved)."
                        )
                        continue
                    normalized_url = normalize_url(source_url)
                    source = evidence_by_url.get(normalized_url)
                    if not source:
                        failures.append(f"Evidence check failed: claim #{index} points to a source that was not verified.")
                        continue
                    source_text = _evidence_text_for_matching(
                        source.get("cleaned_text") or source.get("evidence_excerpt") or ""
                    )
                    normalized_quote = _evidence_text_for_matching(quote)
                    if normalized_quote not in source_text:
                        failures.append(f"Evidence check failed: evidence quote for claim #{index} is not present in retrieved source text.")
                        continue
                    if not ResearchCollector._supports_numeric_markers(claim, quote):
                        failures.append(f"Evidence check failed: numeric values in claim #{index} are not supported by its evidence quote.")

        # 0b. Mock & Test Fixture Guard for Live Mode
        if self.is_live_mode:
            if draft.is_dry_run_fixture:
                failures.append("Live Guard failed: Dry-run test fixture cannot be published in live mode.")
            if screenshot_result and screenshot_result.is_mock:
                failures.append("Live Guard failed: Mock screenshot cannot be published in live mode.")

        # 1a. SEO metadata guidance. These are advisory, not ranking guarantees or hard gates.
        title_length = len((draft.title or "").strip())
        description_length = len((draft.meta_description or "").strip())
        if title_length < 30 or title_length > 65:
            warnings.append(
                f"SEO title advisory: title is {title_length} characters; aim for a concise, descriptive title around 30–65 characters."
            )
        if description_length < 120 or description_length > 155:
            warnings.append(
                f"SEO description advisory: description is {description_length} characters; the editorial target is 120–155 characters."
            )
        if not (draft.meta_description or "").strip():
            warnings.append("SEO description advisory: no meta description was generated; the opening paragraph should clearly summarise the answer.")

        # 1. Plain-English Style and Generic AI Cliché Check
        for pattern in self.GENERIC_AI_CLICHES:
            match = re.search(pattern, text_lower)
            if match:
                failures.append(
                    f"Writing Style failed: Generic AI cliché detected: '{match.group(0)}'. "
                    "Rewrite in plain, direct, natural English."
                )

        # 1b. Honesty: no invented first-hand experience (Google treats this as deceptive)
        for pattern in self.FABRICATED_EXPERIENCE:
            match = re.search(pattern, text_lower)
            if match:
                failures.append(
                    f"Honesty check failed: article claims first-hand experience ('{match.group(0)}'). "
                    "Personal testing cannot be verified; attribute facts to the sources instead."
                )
                break

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
        # The configured target is editorial guidance, not an arbitrary publish blocker.
        # Keep a lower safety floor so genuinely thin articles still fail.
        hard_minimum = min(self.min_word_count, 600)
        if word_count < hard_minimum:
            failures.append(
                f"Originality/Length check failed: Article contains {word_count} words, below the "
                f"{hard_minimum}-word minimum for a useful guide."
            )
        elif word_count < self.min_word_count:
            warnings.append(
                f"Length advisory: article contains {word_count} words; the preferred target is "
                f"{self.min_word_count}. It may still proceed if all critical checks pass."
            )

        # 5b. Plain English: measured, not assumed
        if self.max_reading_grade:
            read = analyze_readability(html_str)
            if read.words >= 200:
                hard_reading_limit = max(self.max_reading_grade + 2.5, 13.5)
                if read.is_hard(hard_reading_limit):
                    failures.append(
                        f"Readability check failed: reading grade {read.fk_grade} (hard limit {hard_reading_limit}), "
                        f"average sentence {read.avg_sentence_words} words. Rewrite in shorter sentences and plainer words."
                    )
                elif read.fk_grade > self.max_reading_grade or read.long_sentence_pct > 15:
                    warnings.append(
                        f"Readability advisory: grade {read.fk_grade}, {read.long_sentence_pct}% of sentences over 25 words. "
                        "Consider simplifying before publication."
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
            normalized_verified = (
                {normalize_url(u) for u in verified_source_urls}
                if verified_source_urls is not None
                else None
            )
            found_hrefs = re.findall(r'href=["\'](https?://[^"\']+)["\']', html_str, re.IGNORECASE)
            normalized_body_links = {normalize_url(html.unescape(l)) for l in found_hrefs}  # hrefs hold &amp;, URLs hold &

            for s in draft.sources_used:
                url = s.get("url", "")
                if not url.startswith("http://") and not url.startswith("https://"):
                    failures.append(f"Sources check failed: Source URL '{url}' is malformed.")
                else:
                    norm_url = normalize_url(url)
                    if normalized_verified is not None and norm_url not in normalized_verified:
                        # In live mode or when verified URLs list is supplied
                        failures.append(
                            f"Sources check failed: Cited source '{url}' was not verified during the research phase."
                        )
                    if norm_url not in normalized_body_links:
                        failures.append(
                            f"Sources check failed: Cited source '{url}' is not linked in the article body."
                        )

        # 7b. Google product and API claims need primary-source evidence.
        source_urls = [s.get("url", "") for s in (draft.sources_used or [])]
        mentions_google_product = bool(re.search(r"\b(?:google|gemini)\b", text_lower))
        has_exact_pricing = bool(
            re.search(r"\$\s?\d|\bper\s+(?:1m|million)\s+tokens\b|\bapi\s+rates\b", text_lower)
        )
        has_model_identifier = bool(re.search(r"\bgemini\s+\d+(?:\.\d+)?\s+flash\b", text_lower))
        if mentions_google_product and has_exact_pricing and not has_official_google_source(source_urls, pricing=True):
            failures.append(
                "Evidence check failed: Google/Gemini pricing claims require an official Google AI pricing or Cloud pricing source."
            )
        elif mentions_google_product and has_model_identifier and not has_official_google_source(source_urls, pricing=False):
            failures.append(
                "Evidence check failed: Specific Gemini model availability claims require an official Google product or developer source."
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
                "seo_title_characters": len((draft.title or "").strip()),
                "seo_description_characters": len((draft.meta_description or "").strip()),
                "screenshot_captured": bool(screenshot_result and screenshot_result.success),
                "has_public_screenshot": bool(screenshot_result and screenshot_result.public_url),
            },
        )

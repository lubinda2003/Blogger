"""Autonomous editorial topic discovery from live Tavily search results.

The static CSV remains an optional fallback/manual source, not the normal topic supply.
"""
import json
import logging
import re
import urllib.error
import urllib.request
from typing import List, Optional
from urllib.parse import urlparse

from src.topic_discovery import TopicItem
from src.state_store import normalize_fingerprint

logger = logging.getLogger(__name__)


EDITORIAL_SEARCHES = (
    ("Productivity", "personal productivity digital organization time management workflows focus task planning", "How-to"),
    ("Student Success", "study skills digital note taking online research exam preparation academic productivity", "Guide"),
    ("Freelancing", "freelance skills client communication proposals portfolios project delivery remote work", "How-to"),
    ("Digital Skills", "practical digital skills computer basics internet safety email spreadsheets cloud files online collaboration", "Tutorial"),
)

_BLOCKED_DOMAINS = (
    "youtube.com", "youtu.be", "reddit.com", "quora.com", "pinterest.com",
    "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com",
)


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return value[:72].strip("-")


def _intent(title: str, content: str) -> str:
    text = f"{title} {content}".lower()
    if any(term in text for term in (" vs ", " versus ", " compared", "comparison", "alternative")):
        return "Comparison"
    if any(term in text for term in ("how to", "step-by-step", "step by step", "tutorial", "setup", "guide")):
        return "Tutorial"
    if any(term in text for term in ("best ", "top ", "alternatives", "tools for")):
        return "Listicle"
    return "How-to"


class AutonomousTopicDiscoverer:
    """Find fresh article candidates by searching Tavily across the publication's four practical digital-skills categories."""

    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: Optional[str], timeout: int = 18, max_per_category: int = 5):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.max_per_category = max(1, min(max_per_category, 8))
        self.last_candidates: List[TopicItem] = []
        self.last_search_count = 0
        self.last_note = ""

    def _search(self, query: str) -> list:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": 8,
        }
        request = urllib.request.Request(
            self.ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "DigitalToolkitContentEngine/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    return []
                return json.loads(response.read().decode("utf-8")).get("results", [])
        except urllib.error.HTTPError as exc:
            logger.warning("Autonomous Tavily discovery failed with HTTP %s.", exc.code)
        except Exception as exc:
            logger.warning("Autonomous Tavily discovery request failed: %s", exc)
        return []

    @staticmethod
    def _allowed_url(url: str) -> bool:
        try:
            parsed = urlparse(url or "")
            host = (parsed.hostname or "").lower().removeprefix("www.")
            if parsed.scheme not in ("http", "https") or not host:
                return False
            return not any(host == domain or host.endswith("." + domain) for domain in _BLOCKED_DOMAINS)
        except Exception:
            return False

    def discover(self, state_store) -> List[TopicItem]:
        """Search each editorial pillar and return the strongest unseen, usable candidates."""
        self.last_candidates = []
        self.last_search_count = 0
        if not self.api_key:
            self.last_note = "TAVILY_API_KEY is missing; autonomous discovery cannot run."
            return []

        seen_ids = set()
        seen_fingerprints = set()
        candidates = []
        for category, query, default_intent in EDITORIAL_SEARCHES:
            results = self._search(query)
            self.last_search_count += 1
            category_items = []
            for result in results:
                title = re.sub(r"\s+", " ", str(result.get("title") or "")).strip()
                url = str(result.get("url") or "").strip()
                content = str(result.get("content") or result.get("snippet") or "").strip()
                if len(title) < 24 or len(title) > 150 or not self._allowed_url(url):
                    continue
                # Avoid social/forum pages and generic navigation pages; require a useful topical signal.
                if len(content) < 40:
                    continue
                topic_id = _slug(title)
                fingerprint = normalize_fingerprint(title)
                if (
                    not topic_id
                    or not fingerprint
                    or topic_id in seen_ids
                    or fingerprint in seen_fingerprints
                    or state_store.is_duplicate(topic_id, title)
                ):
                    continue
                if state_store.is_max_failed(topic_id, max_failures=3):
                    continue
                try:
                    relevance = float(result.get("score", 0.0) or 0.0)
                except (TypeError, ValueError):
                    relevance = 0.0
                # Tavily's relevance score is a search-result signal, not keyword volume.
                item = TopicItem(
                    id=topic_id,
                    topic=title,
                    category=category,
                    primary_intent=_intent(title, content) or default_intent,
                    priority=max(1, min(5, 5 - int(relevance * 4))),
                    requires_screenshot=False,
                    target_url="",
                    target_audience="International students, freelancers and everyday internet users",
                    screenshot_targets=[],
                )
                category_items.append((relevance, item))
                seen_ids.add(topic_id)
                seen_fingerprints.add(fingerprint)
            category_items.sort(key=lambda pair: pair[0], reverse=True)
            candidates.extend(item for _, item in category_items[:self.max_per_category])

        self.last_candidates = candidates
        if candidates:
            self.last_note = (
                f"Tavily searched {self.last_search_count} editorial areas and found "
                f"{len(candidates)} unseen topic candidates. Ranking uses Tavily result relevance, "
                "not verified search volume."
            )
        else:
            self.last_note = (
                f"Tavily searched {self.last_search_count} editorial areas but found no eligible new candidates. "
                "No article was generated."
            )
        return candidates

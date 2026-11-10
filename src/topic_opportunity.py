"""Search-result opportunity screening for queued editorial topics.

This is a lightweight SERP review, not a keyword-volume or keyword-difficulty tool.
It uses the existing Tavily key and makes no claim about monthly search volume.
"""
import json
import logging
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_STOP = {
    "the", "and", "for", "with", "from", "how", "what", "why", "when", "where",
    "best", "free", "guide", "using", "use", "tool", "tools", "without", "your",
    "into", "that", "this", "2026", "2025", "online", "top",
}


def _tokens(value: str) -> set:
    return {
        word.lower() for word in re.findall(r"[a-z0-9]{3,}", value or "", re.I)
        if word.lower() not in _STOP
    }


@dataclass
class TopicOpportunity:
    topic_id: str
    score: int
    result_count: int
    unique_domains: int
    assessment: str
    signals: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "score": self.score,
            "result_count": self.result_count,
            "unique_domains": self.unique_domains,
            "assessment": self.assessment,
            "signals": self.signals,
            "metric_note": "SERP screening estimate only; no search-volume or keyword-difficulty data.",
        }


class TopicOpportunityScorer:
    """Compare queued topics using search-result relevance and visible SERP patterns."""

    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: Optional[str], timeout: int = 15, max_candidates: int = 5):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.max_candidates = max(1, min(max_candidates, 10))
        self.last_results: List[TopicOpportunity] = []

    @staticmethod
    def _query(topic: Any) -> str:
        intent = (getattr(topic, "primary_intent", "") or "").lower()
        if "comparison" in intent:
            suffix = "comparison alternatives who is it best for"
        elif "tutorial" in intent or "how-to" in intent:
            suffix = "step by step tutorial setup"
        elif "listicle" in intent:
            suffix = "best options features free plans"
        else:
            suffix = "guide use cases features"
        return f"{topic.topic} {suffix}"

    def _search(self, query: str) -> List[Dict[str, Any]]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
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
            logger.warning("Topic opportunity search failed with HTTP %s.", exc.code)
        except Exception as exc:
            logger.warning("Topic opportunity search failed: %s", exc)
        return []

    def evaluate_one(self, topic: Any) -> Optional[TopicOpportunity]:
        if not self.api_key:
            return None
        results = self._search(self._query(topic))
        if not results:
            return None

        topic_tokens = _tokens(topic.topic)
        if not topic_tokens:
            return None

        result_tokens = []
        domains = []
        exact_title_matches = 0
        for result in results:
            title = str(result.get("title") or "")
            content = str(result.get("content") or result.get("snippet") or "")
            combined = _tokens(title + " " + content)
            result_tokens.append(combined)
            url = str(result.get("url") or "")
            host = (urlparse(url).hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            if host:
                domains.append(host)
            title_tokens = _tokens(title)
            if len(topic_tokens) >= 3 and len(topic_tokens & title_tokens) / len(topic_tokens) >= 0.75:
                exact_title_matches += 1

        matches = [len(topic_tokens & tokens) / len(topic_tokens) for tokens in result_tokens]
        relevance = sum(matches) / len(matches) if matches else 0.0
        unique_domains = len(set(domains))
        # Heuristic indicators only: broad similarity suggests a crowded exact-angle SERP;
        # domain diversity indicates a range of competing pages, not their authority.
        score = round(45 * relevance + 25 * min(1.0, unique_domains / 6) + 15 * min(1.0, len(results) / 8))
        score -= min(15, exact_title_matches * 3)
        score = max(0, min(100, score))

        signals = [
            f"{len(results)} search results reviewed",
            f"{unique_domains} distinct domains represented",
            f"{exact_title_matches} titles closely match the proposed angle",
        ]
        if relevance >= 0.55 and exact_title_matches <= 2:
            assessment = "Promising relevance with limited exact-angle matches in this result sample"
        elif exact_title_matches >= 4:
            assessment = "Potentially crowded exact-angle results; consider a narrower practical angle"
        elif relevance < 0.3:
            assessment = "Weak result alignment; revise the topic or search phrasing"
        else:
            assessment = "Mixed signals; editorial judgement is still required"

        return TopicOpportunity(
            topic_id=topic.id, score=score, result_count=len(results),
            unique_domains=unique_domains, assessment=assessment, signals=signals,
        )

    def rank(self, topics: List[Any]) -> List[Any]:
        """Return scored topics first; preserve original priority order when scoring is unavailable."""
        if not self.api_key or not topics:
            logger.info("Topic opportunity screening skipped; no Tavily key or candidates.")
            self.last_results = []
            return topics

        scored = []
        unscored = []
        for topic in topics[: self.max_candidates]:
            result = self.evaluate_one(topic)
            if result is None:
                unscored.append(topic)
            else:
                scored.append((result.score, -topic.priority, topic, result))
        self.last_results = [item[3] for item in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)]
        scored_topics = [item[2] for item in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)]
        remaining = topics[self.max_candidates:] + unscored
        seen = {item.id for item in scored_topics}
        return scored_topics + [item for item in remaining if item.id not in seen]

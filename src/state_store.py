"""State storage, topic fingerprinting, deduplication, and persistent execution history."""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def normalize_fingerprint(text: str) -> str:
    """Compute a normalized fingerprint from a topic title or keyword phrase.

    Strips punctuation, stop words, and whitespace to prevent near-duplicate posts.
    """
    if not text:
        return ""

    text = text.lower().strip()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\s]", " ", text)

    stop_words = {
        "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
        "by", "how", "what", "why", "step", "guide", "tutorial", "walkthrough", "best",
        "top", "tips", "tricks", "2024", "2025", "2026", "easy", "simple", "beginners",
        "use", "using", "mastering", "complete", "ultimate", "practical", "overview"
    }

    words = [w for w in text.split() if len(w) > 1 and w not in stop_words]
    words.sort()

    normalized_str = " ".join(words)
    return hashlib.sha256(normalized_str.encode("utf-8")).hexdigest()[:16]


class StateStore:
    """Manages processed topic persistence, deduplication checks, and run history."""

    def __init__(
        self,
        state_file_path: str = "data/processed_topics.json",
        cloudflare_client: Optional[Any] = None,
    ):
        self.state_file_path = Path(state_file_path)
        self.cloudflare_client = cloudflare_client
        self.remote_sync_status: str = "NOT_CONFIGURED"
        self.remote_sync_error: Optional[str] = None
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create state file with initial schema if missing."""
        if not self.state_file_path.exists():
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
            initial_data = {
                "version": "1.0",
                "processed": [],
                "last_updated": None,
                "total_runs": 0,
            }
            self._write_raw(initial_data)

    def _read_raw(self) -> Dict[str, Any]:
        """Read state json safely."""
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"processed": [], "last_updated": None}
                return data
        except Exception as e:
            logger.warning(f"Could not read state file {self.state_file_path} ({e}); starting fresh.")
            return {"processed": [], "last_updated": None}

    def _write_raw(self, data: Dict[str, Any]) -> None:
        """Write state json atomically using temporary file swap."""
        temp_path = self.state_file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.state_file_path)

    def get_processed_fingerprints(self) -> Set[str]:
        """Get the set of all processed fingerprints and topic IDs from local cache and Cloudflare D1."""
        data = self._read_raw()
        fingerprints = set()
        for item in data.get("processed", []):
            if "fingerprint" in item and item["fingerprint"]:
                fingerprints.add(item["fingerprint"])
            if "topic_id" in item and item["topic_id"]:
                fingerprints.add(f"id:{item['topic_id']}")

        # Merge remote state from Cloudflare D1 if configured
        if self.cloudflare_client and getattr(self.cloudflare_client, "is_configured", False):
            try:
                remote_topics = self.cloudflare_client.get_processed_topics(raise_on_error=True)
                self.remote_sync_status = "SUCCESS"
                self.remote_sync_error = None
                if remote_topics:
                    for rt in remote_topics:
                        if rt.get("fingerprint"):
                            fingerprints.add(rt["fingerprint"])
                        if rt.get("topic_id"):
                            fingerprints.add(f"id:{rt['topic_id']}")
            except Exception as e:
                self.remote_sync_status = "FAILED"
                self.remote_sync_error = str(e)
                logger.error(
                    f"[D1 SYNC FAILED] Could not fetch remote topics from Cloudflare Worker: {e}. "
                    "Falling back to local state only."
                )
        else:
            self.remote_sync_status = "NOT_CONFIGURED"
            self.remote_sync_error = None

        return fingerprints

    def is_duplicate(self, topic_id: str, topic_title: str) -> bool:
        """Check if topic ID or normalized title matches an already processed article."""
        fp = normalize_fingerprint(topic_title)
        processed = self.get_processed_fingerprints()

        if f"id:{topic_id}" in processed:
            return True
        if fp in processed:
            return True
        return False

    def record_success(
        self,
        topic_id: str,
        topic_title: str,
        post_id: Optional[str] = None,
        post_url: Optional[str] = None,
        mode: str = "draft",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a completed publication run in persistent state."""
        data = self._read_raw()
        fp = normalize_fingerprint(topic_title)

        record = {
            "topic_id": topic_id,
            "topic_title": topic_title,
            "fingerprint": fp,
            "post_id": post_id,
            "post_url": post_url,
            "mode": mode,
            "status": "COMPLETED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": meta or {},
        }

        # Keep latest record per topic_id
        data["processed"] = [item for item in data.get("processed", []) if item.get("topic_id") != topic_id]
        data["processed"].append(record)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["total_runs"] = len(data["processed"])

        self._write_raw(data)
        logger.info(f"Recorded completed topic '{topic_id}' in persistent state ({self.state_file_path}).")
        return record

    def list_history(self) -> List[Dict[str, Any]]:
        """Return the list of all processed records."""
        data = self._read_raw()
        return data.get("processed", [])

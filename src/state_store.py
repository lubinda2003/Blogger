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
    """Manages processed topic persistence, deduplication checks, and run history via repository state."""

    def __init__(self, state_file_path: str = "data/processed_topics.json"):
        self.state_file_path = Path(state_file_path)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create state file with initial schema if missing."""
        if not self.state_file_path.exists():
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
            initial_data = {
                "version": "1.0",
                "processed": [],
                "failed_attempts": {},
                "last_updated": None,
                "total_runs": 0,
            }
            self._write_raw(initial_data)

    def verify_persistence(self) -> None:
        """Verify that state storage file is readable and writable.

        Fails loudly if the filesystem/repository state cannot be persisted,
        preventing silent fallback to ephemeral in-memory state.
        """
        try:
            data = self._read_raw()
            if not isinstance(data, dict):
                raise ValueError(f"State file {self.state_file_path} does not contain a valid JSON object.")
            # Test write capability atomically
            self._write_raw(data)
        except Exception as e:
            logger.error(f"State persistence verification failed for {self.state_file_path}: {e}")
            raise RuntimeError(
                f"State persistence verification failed for {self.state_file_path}: {e}. "
                "Pipeline will not proceed without reliable state persistence."
            ) from e

    def _read_raw(self) -> Dict[str, Any]:
        """Read state json safely."""
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError(f"State file {self.state_file_path} root is not a dictionary")
                return data
        except Exception as e:
            logger.error(f"Failed to read state file {self.state_file_path}: {e}")
            raise RuntimeError(f"State store read failure for {self.state_file_path}: {e}") from e

    def _write_raw(self, data: Dict[str, Any]) -> None:
        """Write state json atomically using temporary file swap."""
        try:
            temp_path = self.state_file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self.state_file_path)
        except Exception as e:
            logger.error(f"Failed to write state file {self.state_file_path}: {e}")
            raise RuntimeError(f"State store write failure for {self.state_file_path}: {e}") from e

    def get_processed_fingerprints(self) -> Set[str]:
        """Get the set of all processed fingerprints and topic IDs from repository state."""
        data = self._read_raw()
        fingerprints = set()
        for item in data.get("processed", []):
            if "fingerprint" in item and item["fingerprint"]:
                fingerprints.add(item["fingerprint"])
            if "topic_id" in item and item["topic_id"]:
                fingerprints.add(f"id:{item['topic_id']}")
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
        """Record a completed publication run in persistent state.

        Writes atomically to repository state file. Raises RuntimeError on failure to prevent silent fallback.
        """
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

    def get_failed_attempts(self, topic_id: str) -> int:
        """Get the number of failed processing attempts for a topic."""
        data = self._read_raw()
        return data.get("failed_attempts", {}).get(topic_id, 0)

    def is_max_failed(self, topic_id: str, max_failures: int = 3) -> bool:
        """Check if topic has reached or exceeded max allowed failures (head-of-line blocking protection)."""
        return self.get_failed_attempts(topic_id) >= max_failures

    def record_failure(self, topic_id: str, topic_title: str, error_msg: str) -> int:
        """Record a processing failure for a topic and increment failure count."""
        data = self._read_raw()
        if "failed_attempts" not in data:
            data["failed_attempts"] = {}
        current = data["failed_attempts"].get(topic_id, 0) + 1
        data["failed_attempts"][topic_id] = current
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._write_raw(data)
        logger.warning(f"Recorded failure for topic '{topic_id}' (Attempt {current}/3): {error_msg}")
        return current


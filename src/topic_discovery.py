"""Topic intake, prioritization, queue discovery, and selection logic."""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.state_store import StateStore

logger = logging.getLogger(__name__)


@dataclass
class TopicItem:
    """Represents a topic candidate from the editorial queue."""
    id: str
    topic: str
    category: str
    primary_intent: str
    priority: int
    requires_screenshot: bool
    target_url: str
    target_audience: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "category": self.category,
            "primary_intent": self.primary_intent,
            "priority": self.priority,
            "requires_screenshot": self.requires_screenshot,
            "target_url": self.target_url,
            "target_audience": self.target_audience,
        }


class TopicDiscovery:
    """Discovers and selects eligible topics from data/topics.csv without web scraping search engines."""

    def __init__(self, csv_path: str = "data/topics.csv", state_store: Optional[StateStore] = None):
        self.csv_path = Path(csv_path)
        self.state_store = state_store or StateStore()

    def load_queue(self) -> List[TopicItem]:
        """Load and parse candidate topics from CSV."""
        if not self.csv_path.exists():
            logger.warning(f"Topics queue file {self.csv_path} does not exist.")
            return []

        items: List[TopicItem] = []
        with open(self.csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    priority = int(row.get("priority", "3").strip() or 3)
                except ValueError:
                    priority = 3

                req_screenshot = row.get("requires_screenshot", "false").strip().lower() in ("true", "1", "yes")

                item = TopicItem(
                    id=row.get("id", "").strip(),
                    topic=row.get("topic", "").strip(),
                    category=row.get("category", "General").strip(),
                    primary_intent=row.get("primary_intent", "Tutorial").strip(),
                    priority=priority,
                    requires_screenshot=req_screenshot,
                    target_url=row.get("target_url", "").strip(),
                    target_audience=row.get("target_audience", "Digital Workers").strip(),
                )
                if item.id and item.topic:
                    items.append(item)

        # Sort by priority ascending (1 is highest priority)
        items.sort(key=lambda x: x.priority)
        return items

    def select_next_topic(self, requested_id: Optional[str] = None) -> Optional[TopicItem]:
        """Select the highest-priority eligible topic that has not yet been processed."""
        candidates = self.load_queue()

        if requested_id:
            for item in candidates:
                if item.id == requested_id:
                    logger.info(f"Targeted topic selected by ID: {item.id} ('{item.topic}')")
                    return item
            logger.warning(f"Requested topic ID '{requested_id}' not found in queue.")
            return None

        for item in candidates:
            if self.state_store.is_duplicate(item.id, item.topic):
                logger.debug(f"Skipping already processed topic: {item.id} ('{item.topic}')")
                continue
            if self.state_store.is_max_failed(item.id, max_failures=3):
                logger.warning(f"Skipping topic '{item.id}' ('{item.topic}') due to max failure limit (>=3 attempts).")
                continue
            logger.info(f"Selected next eligible topic: {item.id} ('{item.topic}') [Priority {item.priority}]")
            return item

        logger.info("No eligible unprocessed topics found in queue.")
        return None

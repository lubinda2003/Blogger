"""Regression tests for The Digital Toolkit's approved editorial taxonomy."""

import csv
import json
import unittest
from pathlib import Path

from src.autonomous_topic_discovery import EDITORIAL_SEARCHES


ROOT = Path(__file__).resolve().parents[1]


class TestEditorialTaxonomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = json.loads(
            (ROOT / "config" / "editorial_taxonomy.json").read_text(encoding="utf-8")
        )
        cls.categories = [item["name"] for item in cls.taxonomy["categories"]]

    def test_exactly_eight_approved_categories_are_defined(self):
        self.assertEqual(len(self.categories), 8)
        self.assertEqual(
            self.categories,
            [
                "AI and AI Tools",
                "Office Software and Everyday Productivity",
                "Spreadsheets, Data and Reporting",
                "Graphic Design, Video and Content Creation",
                "Freelancing and Remote Work",
                "Digital Business, Marketing and E-commerce",
                "Digital Learning, Research and Study Skills",
                "Digital Foundations, Online Safety and Troubleshooting",
            ],
        )

    def test_each_category_has_topic_clusters_and_accuracy_guidance(self):
        guidance = self.taxonomy["category_accuracy_rules"]
        self.assertEqual(set(guidance), set(self.categories))
        for category in self.taxonomy["categories"]:
            self.assertGreaterEqual(len(category["clusters"]), 5, category["name"])
            self.assertTrue(guidance[category["name"]], category["name"])

    def test_topic_queue_uses_only_approved_categories_and_covers_all_eight(self):
        with (ROOT / "data" / "topics.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(rows)
        queue_categories = {row["category"] for row in rows}
        self.assertEqual(queue_categories, set(self.categories))
        topic_ids = [row["id"] for row in rows]
        self.assertEqual(len(topic_ids), len(set(topic_ids)), "Topic IDs must be unique.")

    def test_autonomous_discovery_searches_all_eight_categories(self):
        discovered_categories = [item[0] for item in EDITORIAL_SEARCHES]
        self.assertEqual(discovered_categories, self.categories)
        self.assertEqual(len(discovered_categories), 8)

    def test_content_type_library_covers_practical_and_explanatory_formats(self):
        content_types = {item["name"] for item in self.taxonomy["content_types"]}
        self.assertIn("Step-by-step tutorial", content_types)
        self.assertIn("Practical project", content_types)
        self.assertIn("Formula or calculation tutorial", content_types)
        self.assertIn("Troubleshooting guide", content_types)
        self.assertIn("Comparison", content_types)


if __name__ == "__main__":
    unittest.main()

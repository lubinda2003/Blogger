import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.autonomous_topic_discovery import AutonomousTopicDiscoverer


class FakeState:
    def __init__(self, duplicates=None, failed=None):
        self.duplicates = set(duplicates or [])
        self.failed = set(failed or [])

    def is_duplicate(self, topic_id, title):
        return topic_id in self.duplicates

    def is_max_failed(self, topic_id, max_failures=3):
        return topic_id in self.failed


class AutonomousTopicDiscoveryTests(unittest.TestCase):
    def test_missing_tavily_key_returns_clear_empty_result(self):
        discoverer = AutonomousTopicDiscoverer(None)
        self.assertEqual(discoverer.discover(FakeState()), [])
        self.assertIn("TAVILY_API_KEY", discoverer.last_note)

    @patch.object(AutonomousTopicDiscoverer, "_search")
    def test_discovers_candidates_across_four_editorial_pillars(self, search):
        search.return_value = [{
            "title": "How to automate client onboarding for freelance businesses",
            "content": "A practical guide explaining onboarding forms, client communication, project setup and repeatable workflows.",
            "url": "https://example.com/onboarding",
            "score": 0.92,
        }]
        discoverer = AutonomousTopicDiscoverer("test-key")
        found = discoverer.discover(FakeState())
        self.assertEqual(search.call_count, 4)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].category, "Artificial Intelligence and AI Tools")
        self.assertEqual(found[0].primary_intent, "Tutorial")
        self.assertFalse(found[0].requires_screenshot)
        self.assertEqual(found[0].target_url, "")

    @patch.object(AutonomousTopicDiscoverer, "_search")
    def test_filters_processed_and_social_results(self, search):
        search.return_value = [
            {
                "title": "How to build a better productivity workflow for remote teams",
                "content": "A detailed explanation of task planning, team communication and workflow management.",
                "url": "https://reddit.com/example",
                "score": 0.99,
            },
            {
                "title": "How to build a better productivity workflow for remote teams",
                "content": "A detailed explanation of task planning, team communication and workflow management.",
                "url": "https://example.com/workflow",
                "score": 0.95,
            },
        ]
        title_id = "how-to-build-a-better-productivity-workflow-for-remote-teams"
        found = AutonomousTopicDiscoverer("test-key").discover(FakeState(duplicates={title_id}))
        self.assertEqual(found, [])

    @patch.object(AutonomousTopicDiscoverer, "_search")
    def test_normalized_duplicate_titles_are_kept_only_once_across_categories(self, search):
        first = {
            "title": "How to Build a Better Productivity Workflow for Remote Teams",
            "content": "A detailed guide to planning tasks, communication and team workflows.",
            "url": "https://example.com/first",
            "score": 0.91,
        }
        duplicate = {
            "title": "A Better Productivity Workflow for Remote Teams: Build It",
            "content": "A detailed guide to planning tasks, communication and team workflows.",
            "url": "https://another.example/second",
            "score": 0.95,
        }
        search.side_effect = [[first], [duplicate], [], []]

        found = AutonomousTopicDiscoverer("test-key").discover(FakeState())

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].topic, first["title"])
        self.assertEqual(found[0].category, "Artificial Intelligence and AI Tools")

    @patch.object(AutonomousTopicDiscoverer, "_search", return_value=[])
    def test_empty_search_is_not_reported_as_successful_discovery(self, _search):
        discoverer = AutonomousTopicDiscoverer("test-key")
        self.assertEqual(discoverer.discover(FakeState()), [])
        self.assertIn("no eligible new candidates", discoverer.last_note.lower())


if __name__ == "__main__":
    unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.topic_opportunity import TopicOpportunityScorer


def topic(topic_id, title, intent="Tutorial", priority=3):
    return SimpleNamespace(id=topic_id, topic=title, primary_intent=intent, priority=priority)


class TopicOpportunityTests(unittest.TestCase):
    def test_missing_key_preserves_editorial_order(self):
        scorer = TopicOpportunityScorer(api_key=None)
        candidates = [topic("b", "Notion project setup"), topic("a", "Free AI research tools", priority=1)]
        self.assertEqual(scorer.rank(candidates), candidates)
        self.assertEqual(scorer.last_results, [])

    @patch.object(TopicOpportunityScorer, "_search")
    def test_search_results_produce_transparent_estimate(self, search):
        search.return_value = [
            {"title": "Notion project management dashboard tutorial", "content": "Build a project workflow in Notion.", "url": "https://example.com/a"},
            {"title": "How to organise projects in Notion", "content": "A practical Notion workspace setup.", "url": "https://another.example/b"},
            {"title": "Notion templates for freelancers", "content": "Project planning and task management.", "url": "https://third.example/c"},
        ]
        scorer = TopicOpportunityScorer(api_key="test-key")
        result = scorer.evaluate_one(topic("notion", "How to Build a Clean Project Management Dashboard in Notion"))
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)
        self.assertEqual(result.result_count, 3)
        self.assertIn("no search-volume", result.to_dict()["metric_note"])

    @patch.object(TopicOpportunityScorer, "_search")
    def test_rank_prefers_scored_candidate_over_static_queue_order(self, search):
        def fake_search(query):
            if "Notion" in query:
                return [{"title": "Notion dashboard project management", "content": "Notion dashboard workflow", "url": "https://one.example"}]
            return [
                {"title": "Completely unrelated recipe", "content": "Cooking dinner", "url": "https://food.example"},
                {"title": "Another unrelated page", "content": "Travel guide", "url": "https://travel.example"},
            ]
        search.side_effect = fake_search
        scorer = TopicOpportunityScorer(api_key="test-key", max_candidates=2)
        candidates = [
            topic("weak", "How to use an obscure task tracker"),
            topic("strong", "Notion project management dashboard tutorial", priority=4),
        ]
        ranked = scorer.rank(candidates)
        self.assertEqual(ranked[0].id, "strong")

    @patch.object(TopicOpportunityScorer, "_search", return_value=[])
    def test_unavailable_search_falls_back_to_queue_order(self, _search):
        scorer = TopicOpportunityScorer(api_key="test-key")
        candidates = [topic("first", "Topic one", priority=1), topic("second", "Topic two", priority=2)]
        self.assertEqual(scorer.rank(candidates), candidates)
        self.assertEqual(scorer.last_results, [])


if __name__ == "__main__":
    unittest.main()

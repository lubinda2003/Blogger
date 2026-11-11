"""Regression tests for trusted screenshot target fallback selection."""

import unittest
from types import SimpleNamespace

from src.main import _build_screenshot_targets


class TestScreenshotTargetFallbacks(unittest.TestCase):
    def test_verified_pages_on_product_domain_follow_primary_target(self):
        topic = SimpleNamespace(
            target_url="https://www.canva.com",
            screenshot_targets=[],
        )
        brief = SimpleNamespace(
            verified_sources=lambda: [
                SimpleNamespace(url="https://www.canva.com/learn/how-to-build-a-brand-kit"),
                SimpleNamespace(url="https://help.canva.com/brand-kit"),
                SimpleNamespace(url="https://www.youtube.com/watch?v=example"),
                SimpleNamespace(url="https://example.com/canva-guide"),
            ]
        )

        targets = _build_screenshot_targets(topic, brief, needed=True)

        self.assertEqual(
            targets,
            [
                "https://www.canva.com",
                "https://www.canva.com/learn/how-to-build-a-brand-kit",
                "https://help.canva.com/brand-kit",
            ],
        )

    def test_explicit_editorial_targets_keep_order_and_are_deduplicated(self):
        topic = SimpleNamespace(
            target_url="https://www.notion.com",
            screenshot_targets=[
                "https://www.notion.com",
                "https://www.notion.com",
            ],
        )
        brief = SimpleNamespace(
            verified_sources=lambda: [
                SimpleNamespace(url="https://www.notion.com/help/guides"),
                SimpleNamespace(url="https://www.youtube.com/watch?v=example"),
            ]
        )

        targets = _build_screenshot_targets(topic, brief, needed=True)

        self.assertEqual(
            targets,
            [
                "https://www.notion.com",
                "https://www.notion.com/help/guides",
            ],
        )

    def test_no_screenshot_requirement_returns_no_targets(self):
        topic = SimpleNamespace(
            target_url="https://www.canva.com",
            screenshot_targets=[],
        )
        brief = SimpleNamespace(verified_sources=lambda: [])

        self.assertEqual(_build_screenshot_targets(topic, brief, needed=False), [])


if __name__ == "__main__":
    unittest.main()

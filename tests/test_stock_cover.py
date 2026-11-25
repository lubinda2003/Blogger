"""Tests for photo-led featured cover composition."""
import tempfile
import unittest
from pathlib import Path

from src.featured_image import _build_photo_cover_html


class TestPhotoCoverHtml(unittest.TestCase):
    def test_stock_photo_is_embedded_locally_with_headline_and_brand(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "background.jpg"
            photo.write_bytes(b"\\xff\\xd8\\xff" + b"photo-bytes")
            page = _build_photo_cover_html(
                "How to Build a Clear Freelance Portfolio",
                "Freelancing",
                "portfolio-cover",
                {"cover_title": "Build a Strong Portfolio"},
                photo,
            )
        self.assertIn("data:image/jpeg;base64,", page)
        self.assertIn("Build a Strong Portfolio", page)
        self.assertIn("The Digital Toolkit", page)
        self.assertIn("background-size:cover", page)
        self.assertNotIn("https://", page)

    def test_cover_title_is_html_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "background.jpg"
            photo.write_bytes(b"\\xff\\xd8\\xff" + b"photo-bytes")
            page = _build_photo_cover_html("<script>alert(1)</script>", "Guide", "x", {}, photo)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()

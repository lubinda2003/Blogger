"""Tests for photo-led featured cover composition."""
import tempfile
import unittest
from pathlib import Path

from src.featured_image import _build_photo_cover_html, _clean_cover_title


class TestPhotoCoverHtml(unittest.TestCase):
    def test_stock_photo_is_embedded_locally_with_headline_and_brand(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "background.jpg"
            photo.write_bytes(b"\xff\xd8\xff" + b"photo-bytes")
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
        self.assertIn("object-fit:cover", page)
        self.assertNotIn("https://", page)

    def test_cover_title_is_html_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "background.jpg"
            photo.write_bytes(b"\xff\xd8\xff" + b"photo-bytes")
            page = _build_photo_cover_html("<script>alert(1)</script>", "Guide", "x", {}, photo)
        self.assertNotIn('<div class="title"><script>', page)
        self.assertIn("&lt;script&gt;", page)

    def test_long_seo_title_is_reduced_to_reader_facing_cover_title(self):
        self.assertEqual(
            _clean_cover_title("07 Online Safety and Cybersecurity Basics | PDF | Password | Computer Security"),
            "Online Safety and Cybersecurity Basics",
        )

    def test_explicit_editorial_cover_title_takes_precedence(self):
        self.assertEqual(
            _clean_cover_title("Long SEO title | keyword", {"cover_title": "Protect Your Online Accounts"}),
            "Protect Your Online Accounts",
        )

    def test_photo_cover_uses_dynamic_negative_space_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "background.jpg"
            photo.write_bytes(b"\\xff\\xd8\\xff" + b"photo-bytes")
            page = _build_photo_cover_html(
                "Online Safety and Cybersecurity Basics | PDF | Password",
                "Digital Foundations",
                "security-cover",
                {},
                photo,
            )
        self.assertIn("getImageData", page)
        self.assertIn("candidates.sort", page)
        self.assertIn("Online Safety and Cybersecurity Basics", page)
        self.assertNotIn("PDF | Password", page)
        self.assertIn("The Digital Toolkit", page)


if __name__ == "__main__":
    unittest.main()

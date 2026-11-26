"""Tests for Pixabay stock media retrieval, caching and safe article placement."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.stock_media import (
    PixabayClient, build_search_query, inject_stock_photos, select_article_photos,
)


class TestPixabayClient(unittest.TestCase):
    def test_search_query_is_concise_and_removes_stopwords(self):
        self.assertEqual(
            build_search_query("How to Build a Clear Freelance Portfolio", "Create Three High Quality Sample Projects"),
            "three high quality sample clear freelance portfolio",
        )

    def test_photo_selection_prefers_large_landscape_and_avoids_duplicates(self):
        hits = [
            {"id": 1, "imageWidth": 640, "imageHeight": 480, "largeImageURL": "https://x/1.jpg", "downloads": 1000},
            {"id": 2, "imageWidth": 1600, "imageHeight": 900, "largeImageURL": "https://x/2.jpg", "downloads": 20},
            {"id": 3, "imageWidth": 1920, "imageHeight": 1080, "largeImageURL": "https://x/3.jpg", "downloads": 200},
        ]
        self.assertEqual(PixabayClient.choose_photo(hits)["id"], 3)
        self.assertEqual(PixabayClient.choose_photo(hits, {3})["id"], 2)
        self.assertIsNone(PixabayClient.choose_photo(hits, {1, 2, 3}))

    def test_relevance_filter_rejects_unrelated_stock_photos(self):
        hits = [
            {"id": 10, "imageWidth": 1600, "imageHeight": 900,
             "largeImageURL": "https://x/flowers.jpg", "tags": "flowers garden spring",
             "downloads": 10000},
            {"id": 11, "imageWidth": 1600, "imageHeight": 900,
             "largeImageURL": "https://x/portfolio.jpg", "tags": "freelance portfolio website",
             "downloads": 10},
        ]
        chosen = PixabayClient.choose_photo(hits, required_terms={"portfolio", "freelance"})
        self.assertEqual(chosen["id"], 11)
        self.assertIsNone(PixabayClient.choose_photo(hits[:1], required_terms={"portfolio"}))

    def test_single_generic_tag_is_not_enough_to_select_a_photo(self):
        hit = {"id": 12, "imageWidth": 1600, "imageHeight": 900,
               "largeImageURL": "https://x/digital.jpg",
               "tags": "digital workspace", "downloads": 5000}
        self.assertIsNone(PixabayClient.choose_photo([hit], required_terms={"digital", "products"}))

    def test_search_results_are_cached_for_24_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = PixabayClient(api_key="test-key", cache_dir=tmp)
            payload = {"hits": [{"id": 9}]}
            with patch("src.stock_media.urllib.request.urlopen") as urlopen:
                response = urlopen.return_value.__enter__.return_value
                response.read.return_value = json.dumps(payload).encode()
                first = client.search_photos("freelance workspace")
                second = client.search_photos("freelance workspace")
            self.assertEqual(first, second)
            self.assertEqual(urlopen.call_count, 1)

    def test_missing_api_key_disables_stock_media_without_failure(self):
        client = PixabayClient(api_key="")
        self.assertFalse(client.available)
        self.assertEqual(client.search_photos("laptop workspace"), [])

    def test_download_accepts_valid_jpeg_when_cdn_uses_generic_content_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = PixabayClient(api_key="test")
            jpeg = b"\xff\xd8\xff" + b"valid-image-bytes"
            with patch("src.stock_media.urllib.request.urlopen") as urlopen:
                response = urlopen.return_value.__enter__.return_value
                response.read.return_value = jpeg
                response.headers.get.return_value = "application/octet-stream"
                path = client.download_photo(
                    {"largeImageURL": "https://example.test/photo"}, Path(tmp) / "photo"
                )
            self.assertEqual(path.suffix, ".jpg")
            self.assertEqual(path.read_bytes(), jpeg)

    def test_download_rejects_non_image_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = PixabayClient(api_key="test")
            with patch("src.stock_media.urllib.request.urlopen") as urlopen:
                response = urlopen.return_value.__enter__.return_value
                response.read.return_value = b"<html>not an image</html>"
                response.headers.get.return_value = "text/html"
                with self.assertRaisesRegex(ValueError, "not a supported"):
                    client.download_photo({"largeImageURL": "https://example.test/photo"}, Path(tmp) / "photo")


class TestStockPhotoPlacement(unittest.TestCase):
    def test_photo_is_inserted_after_first_paragraph_of_matching_heading(self):
        article = "<h2>Build a Portfolio</h2><p>Start with your strongest work.</p><p>Explain each project.</p><h2>Find Clients</h2>"
        photo = {
            "url": "https://cdn.example/portfolio.jpg",
            "section_heading": "Build a Portfolio",
            "alt_text": "A portfolio displayed on a laptop",
            "caption": 'Photo by Creator on <a href="https://pixabay.com/photo/1">Pixabay</a>',
        }
        output = inject_stock_photos(article, [photo])
        self.assertLess(output.index("Start with your strongest work"), output.index("portfolio.jpg"))
        self.assertLess(output.index("portfolio.jpg"), output.index("Explain each project"))
        self.assertNotIn("Photo by Creator", output)

    def test_untrusted_or_incomplete_photo_is_not_inserted(self):
        article = "<h2>Introduction</h2><p>Text.</p>"
        for item in (
            {"url": "http://cdn.example/photo.jpg", "section_heading": "Introduction", "alt_text": "Photo"},
            {"url": "https://cdn.example/photo.jpg", "section_heading": "", "alt_text": "Photo"},
        ):
            self.assertEqual(inject_stock_photos(article, [item]), article)

    def test_article_photo_selection_uses_distinct_heading_queries(self):
        class FakeClient:
            available = True
            def __init__(self):
                self.queries = []
                self.n = 0
            def search_photos(self, query):
                self.queries.append(query)
                self.n += 1
                return [{"id": self.n, "imageWidth": 1600, "imageHeight": 900,
                         "largeImageURL": f"https://images.example/{self.n}.jpg",
                         "pageURL": f"https://pixabay.com/photos/{self.n}/",
                         "tags": query, "user": "Photographer", "downloads": 100}]
            def choose_photo(self, hits, used_ids=None, required_terms=None):
                return PixabayClient.choose_photo(hits, used_ids, required_terms)
            def download_photo(self, hit, output_path):
                path = Path(output_path).with_suffix(".jpg")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fake")
                return path
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient()
            items = select_article_photos(
                "Freelance Portfolio Guide",
                "<h2>Build Sample Projects</h2><p>Text</p><h2>Choose a Platform</h2><p>Text</p><h2>Find Clients</h2><p>Text</p>",
                tmp, max_items=2, client=client,
            )
        # Only the concrete "Sample Projects" section qualifies; generic
        # "Choose a Platform" and "Find Clients" headings are not visual evidence.
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["section_heading"], "Build Sample Projects")
        self.assertEqual(len(client.queries), 1)


if __name__ == "__main__":
    unittest.main()

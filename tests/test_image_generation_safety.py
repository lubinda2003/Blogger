"""Safety tests ensuring paid image generation is never enabled by default."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.visual_tools import generate_gemini_image


class TestGeminiImageGenerationSafety(unittest.TestCase):
    def test_free_default_blocks_image_api_even_if_article_key_is_passed(self):
        env = {
            "IMAGE_PROVIDER": "local",
            "GEMINI_IMAGE_GENERATION_ENABLED": "false",
            "ALLOW_PAID_IMAGE_GENERATION": "false",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("urllib.request.urlopen") as urlopen, \
             tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "Gemini image generation is disabled"):
                generate_gemini_image(
                    "A simple editorial illustration",
                    Path(tmp) / "cover.png",
                    api_key="article-writing-key",
                )
            urlopen.assert_not_called()

    def test_paid_generation_requires_dedicated_image_key(self):
        env = {
            "IMAGE_PROVIDER": "gemini",
            "GEMINI_IMAGE_GENERATION_ENABLED": "true",
            "ALLOW_PAID_IMAGE_GENERATION": "true",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("urllib.request.urlopen") as urlopen, \
             tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"GEMINI_IMAGE_API_KEY": ""}):
                with self.assertRaisesRegex(RuntimeError, "GEMINI_IMAGE_API_KEY"):
                    generate_gemini_image(
                        "A simple editorial illustration",
                        Path(tmp) / "cover.png",
                        api_key=None,
                    )
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()

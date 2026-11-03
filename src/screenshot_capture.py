"""Browser automation with Playwright for genuine screenshot capture and safe image hosting."""

import hashlib
import json
import logging
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ScreenshotResult:
    """Represents the outcome of a screenshot capture task."""
    success: bool
    url: str
    local_path: Optional[str] = None
    public_url: Optional[str] = None  # Valid HTTPS URL only. Never a local runner path!
    alt_text: str = ""
    caption: str = ""
    sha256_hash: Optional[str] = None
    timestamp: Optional[str] = None
    error_message: Optional[str] = None
    file_size_bytes: int = 0
    dimensions: Optional[Tuple[int, int]] = None
    is_mock: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "url": self.url,
            "local_path": self.local_path,
            "public_url": self.public_url,
            "alt_text": self.alt_text,
            "caption": self.caption,
            "sha256_hash": self.sha256_hash,
            "timestamp": self.timestamp,
            "error_message": self.error_message,
            "file_size_bytes": self.file_size_bytes,
            "dimensions": self.dimensions,
            "is_mock": self.is_mock,
        }


class ScreenshotCapture:
    """Captures real screenshots using Playwright Chromium with strict safety constraints."""

    MIN_FILE_SIZE = 5120  # Minimum 5KB for a valid non-blank screenshot

    def __init__(
        self,
        output_dir: str = "output/screenshots",
        viewport_width: int = 1280,
        viewport_height: int = 800,
        timeout_ms: int = 30000,
        max_retries: int = 2,
        image_host_url: Optional[str] = None,
    ):
        self.output_dir = Path(output_dir)
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.image_host_url = image_host_url or os.getenv("SCREENSHOT_HOST_URL")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _compute_file_hash(self, path: Path) -> str:
        """Compute SHA-256 hash of an image file."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _validate_image_file(self, path: Path) -> Tuple[bool, Optional[Tuple[int, int]], str]:
        """Validate that file exists, has valid PNG magic bytes, sensible size, and parse dimensions."""
        if not path.exists():
            return False, None, "File does not exist."

        size = path.stat().st_size
        if size < self.MIN_FILE_SIZE:
            return False, None, f"Image file suspiciously small ({size} bytes, min {self.MIN_FILE_SIZE} bytes)."

        with open(path, "rb") as f:
            header = f.read(24)

        # Check PNG magic bytes: \x89PNG\r\n\x1a\n
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            width, height = struct.unpack(">II", header[16:24])
            if width < 300 or height < 200:
                return False, (width, height), f"Image dimensions too small: {width}x{height}."
            return True, (width, height), "Valid PNG"

        # Check JPEG magic bytes: \xff\xd8\xff
        if header.startswith(b"\xff\xd8\xff"):
            return True, (self.viewport_width, self.viewport_height), "Valid JPEG"

        return False, None, "Invalid image format (not a valid PNG or JPEG)."

    def upload_to_public_host(self, local_path: Path) -> Optional[str]:
        """Upload screenshot to configured public HTTPS host.

        If no image host is configured, returns None so HTML never embeds a broken runner-local path.
        """
        if not self.image_host_url:
            logger.info("No SCREENSHOT_HOST_URL configured; omitting image from published HTML.")
            return None

        # Verify host scheme
        if not self.image_host_url.startswith("https://"):
            logger.warning(f"Configured image host '{self.image_host_url}' is not HTTPS. Skipping upload.")
            return None

        try:
            with open(local_path, "rb") as f:
                img_data = f.read()

            req = urllib.request.Request(
                self.image_host_url,
                data=img_data,
                headers={
                    "Content-Type": "image/png",
                    "User-Agent": "BloggerContentEngine/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    res_body = json.loads(resp.read().decode("utf-8"))
                    public_url = res_body.get("url") or res_body.get("secure_url")
                    if public_url and public_url.startswith("https://"):
                        return public_url
        except Exception as e:
            logger.warning(f"Image host upload failed ({e}); falling back to omitting image.")

        return None

    def capture(
        self,
        url: str,
        slug: str,
        alt_text: str,
        caption: str,
        mock_mode: bool = False,
    ) -> ScreenshotResult:
        """Capture screenshot from a live URL with Playwright Chromium.

        In mock_mode, creates a valid PNG test fixture clearly labelled as mock data.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return ScreenshotResult(
                success=False,
                url=url or "",
                alt_text=alt_text,
                caption=caption,
                timestamp=now_iso,
                error_message="Invalid URL. Screenshots require a valid http or https protocol.",
            )

        target_filename = f"{slug}_{int(time.time())}.png"
        file_path = self.output_dir / target_filename

        if mock_mode:
            logger.info(f"Mock mode active: generating test fixture screenshot at {file_path}")
            # Generate a valid PNG fixture >= 5KB for test suite
            header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 1280, 800) + b"\x08\x02\x00\x00\x00"
            crc = struct.pack(">I", 0x12345678)
            # Pad IDAT to ensure >= 5KB
            padding_data = b"IDAT" + (b"\x78\x9c\x01\x00\x00\xff\xff" * 800)
            chunk_len = struct.pack(">I", len(padding_data) - 4)
            footer = b"\x00\x00\x00\x00IEND\xaeB`\x82"
            mock_png = header + crc + chunk_len + padding_data + footer
            file_path.write_bytes(mock_png)

            return ScreenshotResult(
                success=True,
                url=url,
                local_path=str(file_path),
                public_url=None,  # No public URL in mock mode
                alt_text=alt_text,
                caption=caption,
                sha256_hash=self._compute_file_hash(file_path),
                timestamp=now_iso,
                file_size_bytes=len(mock_png),
                dimensions=(1280, 800),
                is_mock=True,
            )

        # Attempt live Playwright capture
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            return ScreenshotResult(
                success=False,
                url=url,
                alt_text=alt_text,
                caption=caption,
                timestamp=now_iso,
                error_message="Playwright library not installed. Cannot capture screenshot.",
            )

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Capturing live screenshot of '{url}' (attempt {attempt}/{self.max_retries})...")
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={"width": self.viewport_width, "height": self.viewport_height},
                        device_scale_factor=1.0,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    )
                    page = context.new_page()
                    page.set_default_timeout(self.timeout_ms)

                    response = page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)

                    if response and response.status >= 400:
                        browser.close()
                        return ScreenshotResult(
                            success=False,
                            url=url,
                            alt_text=alt_text,
                            caption=caption,
                            timestamp=now_iso,
                            error_message=f"HTTP status error: {response.status} returned by page.",
                        )

                    # Check for blank / blocked page
                    body_text = page.inner_text("body")
                    if len(body_text.strip()) < 50:
                        browser.close()
                        return ScreenshotResult(
                            success=False,
                            url=url,
                            alt_text=alt_text,
                            caption=caption,
                            timestamp=now_iso,
                            error_message="Captured page appeared blank or access-blocked.",
                        )

                    page.screenshot(path=str(file_path), full_page=False)
                    browser.close()

                    # Validate the captured file
                    valid, dims, validation_err = self._validate_image_file(file_path)
                    if not valid:
                        return ScreenshotResult(
                            success=False,
                            url=url,
                            local_path=str(file_path),
                            alt_text=alt_text,
                            caption=caption,
                            timestamp=now_iso,
                            error_message=f"Image validation failed: {validation_err}",
                        )

                    file_hash = self._compute_file_hash(file_path)
                    public_url = self.upload_to_public_host(file_path)

                    return ScreenshotResult(
                        success=True,
                        url=url,
                        local_path=str(file_path),
                        public_url=public_url,
                        alt_text=alt_text,
                        caption=caption,
                        sha256_hash=file_hash,
                        timestamp=now_iso,
                        file_size_bytes=file_path.stat().st_size,
                        dimensions=dims,
                        is_mock=False,
                    )
            except Exception as e:
                last_error = e
                logger.warning(f"Screenshot attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(2.0)

        return ScreenshotResult(
            success=False,
            url=url,
            alt_text=alt_text,
            caption=caption,
            timestamp=now_iso,
            error_message=f"Playwright capture failed: {last_error}",
        )

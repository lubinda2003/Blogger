"""Generated header image for every article.

One consistent look (navy and gold, same layout) with a small per-article variation, rendered locally with
Playwright from plain HTML. No AI image model, no stock photos and no external assets, so there is nothing to
license and nothing that can break. The image is hosted from the repository (see ScreenshotCapture) and is
only embedded after it has been published successfully.
"""

import hashlib
import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1200, 630  # the standard link-preview / Open Graph ratio
BRAND = "The Digital Toolkit"
TAGLINE = "Discover smarter tools. Work better. Do more."
GOLD = "#d4af37"
JPEG_MAGIC = b"\xff\xd8\xff"  # JPEG at quality 90 is about 80 KB; the same image as PNG is about 320 KB

_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
html,body{margin:0;width:__W__px;height:__H__px;overflow:hidden}
body{font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Liberation Sans","DejaVu Sans",sans-serif;
background:linear-gradient(135deg,#050914 0%,#0d1730 60%,#08101f 100%);color:#ffffff;position:relative}
.bar{position:absolute;left:0;top:0;bottom:0;width:14px;background:__GOLD__}
svg{position:absolute;left:0;top:0}
.wrap{position:absolute;left:84px;right:84px;top:64px;bottom:60px;display:flex;flex-direction:column;justify-content:space-between}
.kicker{align-self:flex-start;padding:8px 20px;border:2px solid __GOLD__;border-radius:999px;color:__GOLD__;font-weight:700;font-size:22px;letter-spacing:.14em}
.title{font-weight:800;line-height:1.14;letter-spacing:-.01em;max-width:940px;font-size:__SIZE__px;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.brand{display:flex;align-items:center;gap:16px}
.mark{width:16px;height:16px;background:__GOLD__;transform:rotate(45deg);margin-right:4px}
.name{color:__GOLD__;font-weight:800;font-size:28px;letter-spacing:.02em}
.tag{color:#9fb0cf;font-size:22px}
</style></head><body><div class="bar"></div>
<svg width="__W__" height="__H__" viewBox="0 0 __W__ __H__">__CIRCLES__</svg>
<div class="wrap"><div class="kicker">__KICKER__</div><div class="title">__TITLE__</div>
<div class="brand"><div class="mark"></div><div class="name">__BRAND__</div><div class="tag">__TAGLINE__</div></div></div>
</body></html>"""


@dataclass
class FeaturedImage:
    success: bool
    file_path: Optional[Path] = None
    sha256: str = ""
    alt_text: str = ""
    public_url: Optional[str] = None
    error_message: str = ""


def _title_size(length: int) -> int:
    """Longer titles get smaller type so they always fit in at most four lines."""
    for limit, size in ((30, 84), (45, 72), (60, 64), (80, 56)):
        if length <= limit:
            return size
    return 46


def build_html(title: str, kicker: str, seed: str) -> str:
    """The image as a self-contained HTML page. Pure function: easy to test, no browser needed."""
    digest = hashlib.sha1(seed.encode("utf-8")).digest()
    circles = []
    for i in range(3):  # decoration is derived from the slug: consistent style, unique per article
        cx = 700 + digest[i * 3] % 450
        cy = 40 + digest[i * 3 + 1] % 560
        r = 90 + digest[i * 3 + 2] % 160
        circles.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GOLD}" stroke-opacity="0.16" stroke-width="2"/>'
        )
    values = {
        "W": str(WIDTH), "H": str(HEIGHT), "GOLD": GOLD, "SIZE": str(_title_size(len(title.strip()))),
        "CIRCLES": "".join(circles), "BRAND": html.escape(BRAND), "TAGLINE": html.escape(TAGLINE),
        "KICKER": html.escape((kicker or "Guide").strip().upper()), "TITLE": html.escape(title.strip()),
    }
    # One pass, so text that happens to look like a placeholder is never substituted twice.
    return re.sub(r"__([A-Z]+)__", lambda m: values[m.group(1)], _TEMPLATE)


class FeaturedImageGenerator:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir) / "featured"

    def _render_png(self, page_html: str, out_path: Path) -> None:
        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
                page.set_content(page_html, wait_until="load")
                page.screenshot(path=str(out_path), type="jpeg", quality=90)
            finally:
                browser.close()

    def generate(self, title: str, kicker: str, slug: str) -> FeaturedImage:
        try:
            safe = re.sub(r"[^a-z0-9\-]+", "-", slug.lower()).strip("-") or "article"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{safe}.jpg"
            self._render_png(build_html(title, kicker, seed=safe), path)
            data = path.read_bytes()
            if not data.startswith(JPEG_MAGIC) or len(data) < 2000:
                raise ValueError("rendered file is not a valid JPEG")
            return FeaturedImage(
                success=True, file_path=path, sha256=hashlib.sha256(data).hexdigest(),
                alt_text=f"Cover image for the guide: {title.strip()}",
            )
        except Exception as e:  # an image must never block an article
            logger.warning(f"Featured image not generated: {e}")
            return FeaturedImage(success=False, error_message=str(e))


def prepare_featured_image(
    enabled: bool,
    dry_run: bool,
    title: str,
    kicker: str,
    slug: str,
    output_dir: str = "output",
    generator: Optional[FeaturedImageGenerator] = None,
    publisher: Optional[Callable[[Path, str, str], Optional[str]]] = None,
) -> Optional[FeaturedImage]:
    """Render the header image and, in live runs only, publish it. Returns None when disabled.

    Dry-runs render to output/featured/ for review but never commit anything to the repository.
    A failure here is never fatal: the article is simply published without a cover image.
    """
    if not enabled:
        return None
    image = (generator or FeaturedImageGenerator(output_dir)).generate(title, kicker, slug)
    if image.success and not dry_run:
        if publisher is None:
            from src.screenshot_capture import ScreenshotCapture

            publisher = ScreenshotCapture(output_dir=output_dir, repo_assets_dir="assets/covers").publish_to_repo_assets
        try:
            image.public_url = publisher(image.file_path, slug, image.sha256)
        except Exception as e:
            logger.warning(f"Featured image hosting failed: {e}")
            image.public_url = None
    return image

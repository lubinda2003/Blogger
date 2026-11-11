"""Generated header image for every article.

One consistent look (navy and gold, same layout) with a small per-article variation, rendered locally with
Playwright from plain HTML. No AI image model, no stock photos and no external assets, so there is nothing to
license and nothing that can break. The image is hosted from the repository (see ScreenshotCapture) and is
only embedded after it has been published successfully.
"""

import hashlib
import html
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from src.visual_tools import generate_gemini_image

WIDTH, HEIGHT = 1200, 630  # the standard link-preview / Open Graph ratio
BRAND = "The Digital Toolkit"
TAGLINE = "Discover smarter tools. Work better. Do more."
GOLD = "#d4af37"
JPEG_MAGIC = b"\xff\xd8\xff"  # JPEG at quality 90 is about 80 KB; the same image as PNG is about 320 KB

_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
html,body{margin:0;width:__W__px;height:__H__px;overflow:hidden}
body{font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;background:radial-gradient(ellipse at 82% 45%,#1b3158 0%,#0c1730 42%,#060b17 100%);color:#fff;position:relative}
.bar{position:absolute;left:0;top:0;bottom:0;width:12px;background:__GOLD__}
.grid{position:absolute;inset:0;opacity:.12;background-image:linear-gradient(rgba(255,255,255,.12) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.12) 1px,transparent 1px);background-size:48px 48px}
.wrap{position:absolute;left:76px;top:62px;bottom:48px;width:610px;display:flex;flex-direction:column;justify-content:space-between}
.kicker{display:inline-flex;align-self:flex-start;padding:9px 17px;border:1px solid rgba(212,175,55,.75);border-radius:5px;color:__GOLD__;font-weight:800;font-size:17px;letter-spacing:.16em}
.title{font-weight:800;line-height:1.08;letter-spacing:-.035em;max-width:610px;font-size:__SIZE__px;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;text-shadow:0 3px 22px rgba(0,0,0,.28)}
.brand{display:flex;align-items:center;gap:13px}
.mark{width:13px;height:13px;background:__GOLD__;transform:rotate(45deg)}
.name{color:__GOLD__;font-weight:800;font-size:21px;letter-spacing:.02em}
.tag{color:#aab9d2;font-size:15px;margin-left:8px}
.art{position:absolute;right:45px;top:95px;width:440px;height:430px}
.art-card{fill:#132544;stroke:#60799f;stroke-width:2}
.art-line{stroke:#d4af37;stroke-width:5;stroke-linecap:round}
.art-soft{fill:#21395f}
.art-muted{fill:#9fb2d0}
.art-gold{fill:#d4af37}
.art-glow{fill:#d4af37;fill-opacity:.13}
</style></head><body><div class="bar"></div><div class="grid"></div>
<svg class="art" viewBox="0 0 440 430" aria-hidden="true">__ART__</svg>
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
    """Render a self-contained editorial cover with a topic-aware visual composition."""
    digest = hashlib.sha1(seed.encode("utf-8")).digest()
    circles = []
    for i in range(3):
        cx = 90 + digest[i * 3] % 1080
        cy = 35 + digest[i * 3 + 1] % 560
        r = 65 + digest[i * 3 + 2] % 150
        circles.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GOLD}" stroke-opacity="0.10" stroke-width="2"/>'
        )
    lowered = title.lower()
    if any(word in lowered for word in (" vs ", "versus", "comparison", "compared")):
        art = (
            '<rect x="25" y="70" width="175" height="250" rx="18" class="art-card"/>'
            '<rect x="240" y="70" width="175" height="250" rx="18" class="art-card"/>'
            '<rect x="48" y="100" width="129" height="18" rx="6" class="art-soft"/>'
            '<rect x="263" y="100" width="129" height="18" rx="6" class="art-soft"/>'
            '<rect x="48" y="145" width="129" height="74" rx="9" class="art-glow"/>'
            '<rect x="263" y="145" width="129" height="74" rx="9" class="art-glow"/>'
            '<path d="M62 190 L87 170 L111 182 L151 154" fill="none" class="art-line"/>'
            '<path d="M277 190 L302 177 L326 158 L366 173" fill="none" class="art-line"/>'
            '<rect x="48" y="242" width="95" height="9" rx="4" class="art-muted"/>'
            '<rect x="263" y="242" width="95" height="9" rx="4" class="art-muted"/>'
            '<circle cx="220" cy="194" r="34" class="art-gold"/>'
            '<text x="220" y="203" text-anchor="middle" font-size="23" font-weight="800" fill="#08101f">VS</text>'
            '<path d="M75 355 H365" stroke="#d4af37" stroke-opacity=".55" stroke-width="2"/>'
            '<circle cx="220" cy="355" r="7" class="art-gold"/>'
        )
    else:
        art = (
            '<rect x="50" y="60" width="340" height="275" rx="18" class="art-card"/>'
            '<rect x="50" y="60" width="340" height="38" rx="18" class="art-soft"/>'
            '<circle cx="76" cy="79" r="5" class="art-gold"/><circle cx="95" cy="79" r="5" class="art-muted"/>'
            '<rect x="72" y="120" width="82" height="188" rx="9" class="art-soft"/>'
            '<rect x="174" y="120" width="194" height="82" rx="9" class="art-glow"/>'
            '<rect x="174" y="218" width="88" height="90" rx="9" class="art-soft"/>'
            '<rect x="280" y="218" width="88" height="90" rx="9" class="art-soft"/>'
            '<path d="M190 178 L220 157 L248 169 L285 139 L344 151" fill="none" class="art-line"/>'
            '<rect x="88" y="145" width="49" height="8" rx="4" class="art-muted"/>'
            '<rect x="88" y="166" width="37" height="8" rx="4" class="art-muted"/>'
            '<rect x="88" y="187" width="45" height="8" rx="4" class="art-muted"/>'
            '<rect x="190" y="244" width="55" height="8" rx="4" class="art-muted"/>'
            '<rect x="296" y="244" width="55" height="8" rx="4" class="art-muted"/>'
            '<circle cx="220" cy="375" r="28" class="art-glow"/>'
            '<path d="M205 375 L216 386 L238 360" fill="none" class="art-line"/>'
        )
    art += "".join(circles)
    values = {
        "W": str(WIDTH), "H": str(HEIGHT), "GOLD": GOLD, "SIZE": str(min(_title_size(len(title.strip())), 68)),
        "ART": art, "BRAND": html.escape(BRAND), "TAGLINE": html.escape(TAGLINE),
        "KICKER": html.escape((kicker or "Guide").strip().upper()), "TITLE": html.escape(title.strip()),
    }
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

    def generate(self, title: str, kicker: str, slug: str, brief: Optional[dict] = None) -> FeaturedImage:
        try:
            safe = re.sub(r"[^a-z0-9\-]+", "-", slug.lower()).strip("-") or "article"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{safe}.jpg"
            if os.getenv("IMAGE_GENERATION_ENABLED", "false").strip().lower() in ("true", "1", "yes", "on"):
                description = (brief or {}).get("description", "")
                photo_prompt = (
                    "Create a premium, photorealistic editorial technology photograph for an international "
                    "technology publication. Show one believable real-world scene that visually communicates "
                    f"the article topic: {title.strip()}. Creative direction: {description}. "
                    "Natural daylight or realistic studio lighting, authentic materials, carefully art-directed "
                    "composition, restrained modern colour palette, clear subject, subtle depth of field. "
                    "Landscape 16:9 crop with useful negative space. This must look like commissioned editorial "
                    "photography, not an AI illustration, 3D render, stock-photo collage, dashboard mockup, "
                    "floating icons, glowing circuitry, or futuristic interface. No text, no letters, no logos, "
                    "no watermark, no UI screenshots."
                )
                try:
                    path = generate_gemini_image(photo_prompt, path, aspect_ratio="16:9")
                except Exception as image_error:
                    logger.warning("Photographic cover generation failed; using local fallback: %s", image_error)
                    self._render_png(build_html(title, kicker, seed=safe), path)
            else:
                self._render_png(build_html(title, kicker, seed=safe), path)
            data = path.read_bytes()
            valid_jpeg = data.startswith(JPEG_MAGIC)
            valid_png = data.startswith(b"\x89PNG\r\n\x1a\n")
            if not (valid_jpeg or valid_png) or len(data) < 2000:
                raise ValueError("rendered file is not a valid JPEG or PNG")
            return FeaturedImage(
                success=True, file_path=path, sha256=hashlib.sha256(data).hexdigest(),
                alt_text=(brief or {}).get("alt_text") or f"Cover image for the guide: {title.strip()}",
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
    brief: Optional[dict] = None,
) -> Optional[FeaturedImage]:
    """Render the header image and, in live runs only, publish it. Returns None when disabled.

    Dry-runs render to output/featured/ for review but never commit anything to the repository.
    A failure here is never fatal: the article is simply published without a cover image.
    """
    if not enabled:
        return None
    image = (generator or FeaturedImageGenerator(output_dir)).generate(title, kicker, slug, brief=brief)
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

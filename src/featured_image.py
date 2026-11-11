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

WIDTH, HEIGHT = 1200, 675
BRAND = "The Digital Toolkit"
TAGLINE = "Discover smarter tools. Work better. Do more."
JPEG_MAGIC = b"\\xff\\xd8\\xff"

# Topic families deliberately use different art direction; no fixed brand palette.
PALETTES = {
    "ai": ("#101b36", "#6ee7f9", "#f59e0b", "#dbeafe"),
    "software": ("#14251f", "#a7f3d0", "#fbbf24", "#ecfdf5"),
    "business": ("#251638", "#c4b5fd", "#fb7185", "#f5f3ff"),
    "tutorial": ("#202b38", "#fcd34d", "#38bdf8", "#f8fafc"),
    "default": ("#172033", "#93c5fd", "#f0abfc", "#f8fafc"),
}

def _topic_family(title: str, kicker: str = "") -> str:
    text = f"{title} {kicker}".lower()
    if any(w in text for w in ("ai ", "artificial intelligence", "machine learning", "chatgpt", "claude", "gemini", "llm")):
        return "ai"
    if any(w in text for w in ("business", "freelance", "invoice", "marketing", "monetiz", "startup", "revenue")):
        return "business"
    if any(w in text for w in ("tutorial", "how to", "step-by-step", "setup", "guide", "fix", "troubleshoot")):
        return "tutorial"
    if any(w in text for w in ("software", "notion", "productivity", "workspace", "project management", "app", "tool")):
        return "software"
    return "default"


def _title_size(length: int) -> int:
    for limit, size in ((30, 82), (45, 70), (60, 62), (80, 54)):
        if length <= limit:
            return size
    return 44


def build_html(title: str, kicker: str, seed: str) -> str:
    """Build a self-contained, topic-aware editorial cover using local HTML and SVG only."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    family = _topic_family(title, kicker)
    bg, accent, pop, ink = PALETTES[family]
    # Distinct compositions per topic family, with seeded variation within each family.
    if family == "ai":
        art = (
            '<circle cx="910" cy="320" r="205" fill="none" stroke="__ACCENT__" stroke-width="2" opacity=".25"/>'
            '<circle cx="910" cy="320" r="145" fill="__ACCENT__" opacity=".08"/>'
            '<path d="M760 320h300M910 170v300M804 214l212 212M1016 214L804 426" stroke="__ACCENT__" stroke-width="3" opacity=".45"/>'
            '<rect x="830" y="240" width="160" height="160" rx="34" fill="__BG2__" stroke="__ACCENT__" stroke-width="3"/>'
            '<path d="M875 290h70M875 320h70M875 350h42" stroke="__POP__" stroke-width="9" stroke-linecap="round"/>'
        )
    elif family == "software":
        art = (
            '<rect x="720" y="125" width="390" height="400" rx="28" fill="__BG2__" stroke="__ACCENT__" stroke-width="2"/>'
            '<rect x="750" y="158" width="330" height="48" rx="12" fill="__ACCENT__" opacity=".18"/>'
            '<rect x="750" y="232" width="100" height="250" rx="15" fill="__ACCENT__" opacity=".13"/>'
            '<rect x="872" y="232" width="208" height="112" rx="15" fill="__POP__" opacity=".2"/>'
            '<rect x="872" y="365" width="96" height="117" rx="15" fill="__ACCENT__" opacity=".2"/>'
            '<rect x="984" y="365" width="96" height="117" rx="15" fill="__POP__" opacity=".15"/>'
            '<path d="M775 290h50M775 325h38M895 310l35-24 35 15 65-49" fill="none" stroke="__POP__" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    elif family == "business":
        art = (
            '<path d="M735 475L835 365l88 50 150-190" fill="none" stroke="__ACCENT__" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M1010 225h65v65" fill="none" stroke="__POP__" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>'
            '<rect x="735" y="490" width="360" height="5" rx="2" fill="__ACCENT__" opacity=".4"/>'
            '<circle cx="835" cy="365" r="17" fill="__POP__"/><circle cx="923" cy="415" r="17" fill="__POP__"/>'
            '<circle cx="1073" cy="225" r="17" fill="__POP__"/>'
            '<rect x="755" y="145" width="290" height="55" rx="16" fill="__BG2__" stroke="__ACCENT__" stroke-opacity=".6"/>'
            '<path d="M785 172h105M925 172h85" stroke="__ACCENT__" stroke-width="8" stroke-linecap="round"/>'
        )
    else:
        art = (
            '<rect x="755" y="145" width="330" height="355" rx="28" fill="__BG2__" stroke="__ACCENT__" stroke-width="2"/>'
            '<rect x="790" y="180" width="260" height="48" rx="12" fill="__ACCENT__" opacity=".18"/>'
            '<circle cx="820" cy="204" r="7" fill="__POP__"/><circle cx="844" cy="204" r="7" fill="__ACCENT__"/>'
            '<path d="M810 280l55 55 110-112" fill="none" stroke="__POP__" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M810 395h220M810 430h165" stroke="__ACCENT__" stroke-width="10" stroke-linecap="round" opacity=".55"/>'
        )
    # Small deterministic decorative dots make repeat runs stable but not identical across articles.
    dots = "".join(
        f'<circle cx="{760 + digest[i] % 350}" cy="{100 + digest[i+1] % 470}" r="{5 + digest[i+2] % 10}" fill="__POP__" opacity=".5"/>'
        for i in (0, 3, 6, 9, 12, 15)
    )
    title_html = html.escape(title.strip())
    kicker_html = html.escape((kicker or "Guide").strip().upper())
    template = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:1200px;height:675px;overflow:hidden}
body{font-family:Inter,-apple-system,"Segoe UI",Arial,sans-serif;background:radial-gradient(ellipse at 78% 48%,__BG2__ 0%,__BG__ 68%);color:__INK__;position:relative}
.texture{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:44px 44px;mask-image:linear-gradient(90deg,black,transparent)}
.orb{position:absolute;width:540px;height:540px;right:30px;top:65px;border-radius:50%;background:__ACCENT__;opacity:.045;filter:blur(2px)}
.copy{position:absolute;left:78px;top:75px;bottom:58px;width:625px;display:flex;flex-direction:column;justify-content:space-between}
.kicker{font-size:17px;letter-spacing:.16em;font-weight:800;color:__ACCENT__;text-transform:uppercase}
.rule{width:76px;height:6px;border-radius:9px;background:__POP__;margin-top:18px}
.title{font-size:__SIZE__px;line-height:1.08;letter-spacing:-.045em;font-weight:820;max-width:630px;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;text-wrap:balance}
.brand{display:flex;align-items:center;gap:11px;color:__INK__;font-size:17px;font-weight:700;opacity:.82}
.mark{width:10px;height:10px;border-radius:3px;background:__ACCENT__;transform:rotate(45deg)}
.art{position:absolute;inset:0;width:1200px;height:675px}
</style></head><body><div class="texture"></div><div class="orb"></div>
<svg class="art" viewBox="0 0 1200 675" aria-hidden="true">__ART____DOTS__</svg>
<div class="copy"><div><div class="kicker">__KICKER__</div><div class="rule"></div></div><div class="title">__TITLE__</div>
<div class="brand"><span class="mark"></span><span>__BRAND__</span></div></div></body></html>"""
    values = {
        "__BG__": bg, "__BG2__": bg, "__ACCENT__": accent, "__POP__": pop, "__INK__": ink,
        "__SIZE__": str(min(_title_size(len(title.strip())), 68)), "__ART__": art, "__DOTS__": dots,
        "__KICKER__": kicker_html, "__TITLE__": title_html, "__BRAND__": BRAND,
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return template


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
                page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
                page.set_content(page_html, wait_until="load")
                page.screenshot(path=str(out_path), type="jpeg", quality=91, animations="disabled")
            finally:
                browser.close()

    def generate(self, title: str, kicker: str, slug: str, brief: Optional[dict] = None) -> FeaturedImage:
        try:
            safe = re.sub(r"[^a-z0-9\\-]+", "-", slug.lower()).strip("-") or "article"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{safe}.jpg"
            # Fully offline: local HTML/CSS/SVG rendering only. No image API or remote assets.
            self._render_png(build_html(title, kicker, seed=safe), path)
            data = path.read_bytes()
            if not data.startswith(JPEG_MAGIC) or len(data) < 2000:
                raise ValueError("rendered file is not a valid JPEG")
            return FeaturedImage(
                success=True, file_path=path, sha256=hashlib.sha256(data).hexdigest(),
                alt_text=(brief or {}).get("alt_text") or f"Editorial cover graphic for: {title.strip()}",
            )
        except Exception as e:
            logger.warning("Featured image not generated: %s", e)
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

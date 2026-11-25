"""Offline topic-aware editorial cover images rendered with local HTML, CSS, SVG and Playwright."""

import base64
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
JPEG_MAGIC = b"\xff\xd8\xff"

# Topic families deliberately use different art direction; no fixed brand palette.
PALETTES = {
    "ai": ("#11152b", "#7dd3fc", "#fbbf24", "#f8fafc"),
    "software": ("#102b3f", "#67e8f9", "#fb923c", "#ecfeff"),
    "business": ("#251b16", "#fbbf24", "#fb7185", "#fff7ed"),
    "design": ("#2a1642", "#f0abfc", "#a3e635", "#fdf4ff"),
    "spreadsheets": ("#102d27", "#86efac", "#facc15", "#f0fdf4"),
    "productivity": ("#14251f", "#a7f3d0", "#fbbf24", "#ecfdf5"),
    "student": ("#101b36", "#6ee7f9", "#f59e0b", "#dbeafe"),
    "freelancing": ("#251638", "#c4b5fd", "#fb7185", "#f5f3ff"),
    "digital_skills": ("#202b38", "#fcd34d", "#38bdf8", "#f8fafc"),
    "default": ("#172033", "#93c5fd", "#f0abfc", "#f8fafc"),
}

def _topic_family(title: str, kicker: str = "") -> str:
    text = f"{title} {kicker}".lower()
    if any(w in text for w in ("artificial intelligence", " ai ", "ai assistant", "chatgpt", "gemini", "claude", "copilot")):
        return "ai"
    if any(w in text for w in ("spreadsheet", "excel", "google sheets", "formula", "data reporting")):
        return "spreadsheets"
    if any(w in text for w in ("graphic design", "canva", "video editing", "content creation", "brand kit")):
        return "design"
    if any(w in text for w in ("digital business", "e-commerce", "ecommerce", "marketing", "payment processing", "online store")):
        return "business"
    if any(w in text for w in ("software", "notion", "obsidian", "browser extension", "app comparison")):
        return "software"
    if any(w in text for w in ("student", "study", "exam", "academic", "research", "learning", "notes")):
        return "student"
    if any(w in text for w in ("freelanc", "client", "proposal", "portfolio", "invoice", "independent worker")):
        return "freelancing"
    if any(w in text for w in ("productivity", "work plan", "time management", "focus", "task planning", "workflow", "organize")):
        return "productivity"
    if any(w in text for w in ("digital skills", "spreadsheet", "online safety", "email", "computer basics", "cloud files", "internet skills")):
        return "digital_skills"
    return "default"


def _title_size(length: int) -> int:
    for limit, size in ((30, 82), (45, 70), (60, 62), (80, 54)):
        if length <= limit:
            return size
    return 46


def _visual_concept(title: str, family: str) -> str:
    """Choose a concrete subject motif from the article title, not just its category."""
    text = title.lower()
    if any(word in text for word in ("account", "password", "security", "safe", "phishing", "privacy", "passkey")):
        return "security"
    if any(word in text for word in ("portfolio", "proposal", "freelance", "client", "invoice")):
        return "freelance"
    if any(word in text for word in ("spreadsheet", "formula", "excel", "sheets", "dashboard", "report")):
        return "spreadsheet"
    if any(word in text for word in ("assistant", "chatgpt", "gemini", "claude", "copilot", "artificial intelligence", " ai ")):
        return "ai"
    return family


def _artwork(concept: str, accent: str, pop: str, ink: str, pale: str) -> str:
    """Purpose-drawn SVG scenes; each concept has a different silhouette and visual story."""
    scenes = {
        "ai": '<rect x="700" y="130" width="410" height="390" rx="34" fill="#101d35" stroke="#6ccdf5" stroke-width="3"/><rect x="735" y="165" width="340" height="52" rx="16" fill="#233d5b"/><circle cx="765" cy="191" r="8" fill="#f7c85b"/><circle cx="792" cy="191" r="8" fill="#76e0cf"/><rect x="755" y="260" width="110" height="120" rx="24" fill="#173f56" stroke="#6ccdf5" stroke-width="3"/><circle cx="810" cy="302" r="23" fill="#6ccdf5"/><circle cx="802" cy="299" r="4" fill="#102033"/><circle cx="818" cy="299" r="4" fill="#102033"/><path d="M795 320q15 13 30 0" fill="none" stroke="#102033" stroke-width="4" stroke-linecap="round"/><rect x="900" y="255" width="165" height="55" rx="14" fill="#293b61"/><path d="M925 282h112" stroke="#b8d8f5" stroke-width="8" stroke-linecap="round"/><rect x="900" y="335" width="165" height="55" rx="14" fill="#224c4d"/><path d="M925 362h82" stroke="#9de7cb" stroke-width="8" stroke-linecap="round"/><path d="M810 410v42m0 0h145" stroke="#6ccdf5" stroke-width="5" stroke-linecap="round"/><circle cx="970" cy="452" r="18" fill="#f7c85b"/>',
        "security": '<rect x="680" y="170" width="470" height="300" rx="28" fill="#102b48" stroke="#4aa9e8" stroke-width="4"/><rect x="710" y="200" width="410" height="230" rx="12" fill="#153d61"/><path d="M845 170v-48q0-90 75-90t75 90v48" transform="translate(0 130)" fill="none" stroke="#7bd8ff" stroke-width="28" stroke-linecap="round"/><rect x="850" y="245" width="145" height="150" rx="24" fill="#2c8cc7"/><path d="M922 280v38m-22 18q22 26 44 0" stroke="#fff" stroke-width="12" stroke-linecap="round" fill="none"/><circle cx="922" cy="340" r="12" fill="#fff"/><path d="M720 480h390" stroke="#4aa9e8" stroke-width="12" stroke-linecap="round"/><circle cx="760" cy="520" r="12" fill="#f4c95d"/><path d="M1040 110l42 18v48q0 48-42 72-42-24-42-72v-48z" fill="#123f59" stroke="#79e0d0" stroke-width="6"/><path d="M1020 168l15 15 29-34" fill="none" stroke="#79e0d0" stroke-width="8" stroke-linecap="round"/>',
        "freelance": '<rect x="690" y="145" width="440" height="345" rx="24" fill="#14243d" stroke="#c6a6ff" stroke-width="3"/><rect x="715" y="175" width="390" height="46" rx="12" fill="#3b3158"/><circle cx="742" cy="198" r="7" fill="#ffb77a"/><circle cx="765" cy="198" r="7" fill="#c6a6ff"/><rect x="730" y="250" width="155" height="185" rx="14" fill="#31506b"/><rect x="905" y="250" width="185" height="78" rx="14" fill="#594273"/><rect x="905" y="345" width="185" height="90" rx="14" fill="#24545b"/><path d="M750 390l40-65 45 45 28-35" fill="none" stroke="#f6c56c" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/><path d="M930 286h130m-130 20h82M930 380h120m-120 20h88" stroke="#f1eaff" stroke-width="7" stroke-linecap="round"/><path d="M820 520h180" stroke="#c6a6ff" stroke-width="12" stroke-linecap="round"/>',
        "spreadsheet": '<rect x="675" y="120" width="470" height="420" rx="24" fill="#f4fbf7" stroke="#62c69a" stroke-width="5"/><rect x="675" y="120" width="470" height="64" rx="22" fill="#16734f"/><path d="M675 184h470M770 184v356M865 184v356M960 184v356M1055 184v356M675 270h470M675 356h470M675 442h470" stroke="#b9d9c9" stroke-width="3"/><rect x="772" y="272" width="91" height="82" fill="#b8ebd0"/><rect x="867" y="358" width="91" height="82" fill="#8edbb4"/><path d="M715 490l70-65 70 24 90-105 75-35" fill="none" stroke="#14885d" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/><path d="M1000 306h32v32" fill="none" stroke="#14885d" stroke-width="10" stroke-linecap="round"/>',
        "design": '<rect x="700" y="145" width="410" height="360" rx="26" fill="#251b3e" stroke="#d6a5f5" stroke-width="3"/><circle cx="830" cy="280" r="85" fill="#f5a9ca"/><circle cx="830" cy="280" r="42" fill="#ffc96b"/><path d="M830 195a85 85 0 0 1 85 85h-85z" fill="#71d7c1"/><rect x="945" y="225" width="115" height="24" rx="12" fill="#9b83e8"/><rect x="945" y="270" width="90" height="24" rx="12" fill="#f5a9ca"/><rect x="945" y="315" width="105" height="24" rx="12" fill="#71d7c1"/><path d="M750 420h300" stroke="#f8eaff" stroke-width="8" stroke-linecap="round"/>',
        "business": '<path d="M700 270l210-120 210 120v240H700z" fill="#273a50" stroke="#f6c56c" stroke-width="4"/><path d="M670 275h480" stroke="#f6c56c" stroke-width="18" stroke-linecap="round"/><rect x="750" y="330" width="110" height="180" rx="10" fill="#356a68"/><rect x="900" y="330" width="150" height="95" rx="10" fill="#8d6bb8"/><path d="M920 380h110M920 400h80" stroke="#fff" stroke-width="7" stroke-linecap="round"/><path d="M930 245l80-60 80 30" fill="none" stroke="#8be0c2" stroke-width="10" stroke-linecap="round"/>',
        "student": '<path d="M680 230q120-70 240 0v270q-120-70-240 0z" fill="#234568" stroke="#85d6f0" stroke-width="4"/><path d="M920 230q120-70 240 0v270q-120-70-240 0z" fill="#31577a" stroke="#85d6f0" stroke-width="4"/><path d="M920 230v270" stroke="#f6c56c" stroke-width="5"/><path d="M720 290h145m-145 42h145m-145 42h110m130-84h145m-145 42h145m-145 42h110" stroke="#dceeff" stroke-width="8" stroke-linecap="round"/>',
        "software": '<rect x="680" y="135" width="470" height="370" rx="25" fill="#152e49" stroke="#79d6e6" stroke-width="4"/><rect x="680" y="135" width="470" height="58" rx="22" fill="#244d68"/><circle cx="720" cy="164" r="8" fill="#f6c56c"/><circle cx="747" cy="164" r="8" fill="#85d6c4"/><rect x="720" y="225" width="125" height="235" rx="12" fill="#315a70"/><rect x="870" y="225" width="245" height="95" rx="12" fill="#3b456f"/><rect x="870" y="340" width="112" height="120" rx="12" fill="#286b65"/><rect x="995" y="340" width="120" height="120" rx="12" fill="#775a92"/>',
        "productivity": '<rect x="710" y="135" width="410" height="390" rx="24" fill="#183a3c" stroke="#91dfc3" stroke-width="4"/><rect x="710" y="135" width="410" height="70" rx="20" fill="#285c53"/><path d="M765 115v55m300-55v55" stroke="#f6c56c" stroke-width="12" stroke-linecap="round"/><path d="M755 270h300m-300 75h300m-300 75h300" stroke="#8bcab7" stroke-width="4"/><rect x="755" y="235" width="28" height="28" rx="6" fill="#f6c56c"/><path d="M761 249l7 7 13-17" stroke="#183a3c" stroke-width="4" fill="none"/><rect x="755" y="310" width="28" height="28" rx="6" fill="#f6c56c"/><path d="M761 324l7 7 13-17" stroke="#183a3c" stroke-width="4" fill="none"/>',
        "default": '<circle cx="900" cy="330" r="190" fill="#24496a" stroke="#85d6f0" stroke-width="4"/><circle cx="900" cy="330" r="120" fill="none" stroke="#f6c56c" stroke-width="8"/><path d="M770 330h260M900 200v260" stroke="#85d6f0" stroke-width="5"/><circle cx="900" cy="330" r="35" fill="#f6c56c"/>',
    }
    return scenes.get(concept, scenes["default"])


def build_html(title: str, kicker: str, seed: str, brief: Optional[dict] = None) -> str:
    """Build an article-aware cover with varied compositions and subject-specific artwork."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    family = _topic_family(title, kicker)
    concept = _visual_concept(title, family)
    bg, accent, pop, ink = PALETTES[family]
    scene = _artwork(concept, accent, pop, ink, "#f8fafc")
    # Four composition families. The title can move, shrink or disappear when the visual carries the story.
    layout = digest[0] % 4
    title_text = (brief or {}).get("cover_title") or title.strip()
    show_title = (brief or {}).get("show_title")
    if show_title is None:
        show_title = len(title_text) < 76 and layout != 2
    title_html = html.escape(str(title_text))
    kicker_html = html.escape((kicker or "Guide").strip().upper())
    if layout == 0:
        copy_css = "left:64px;top:64px;bottom:52px;width:520px;justify-content:space-between;text-align:left"
        title_css = "font-size:clamp(48px,5.4vw,70px);max-width:520px"
        scene_transform = "translate(0 0)"
        panel = '<rect x="0" y="0" width="590" height="675" fill="#081321" opacity=".82"/>'
    elif layout == 1:
        copy_css = "left:70px;right:70px;top:48px;bottom:42px;width:auto;justify-content:space-between;text-align:left"
        title_css = "font-size:58px;max-width:690px"
        scene_transform = "translate(0 0) scale(.86) translate(100 55)"
        panel = '<rect x="0" y="0" width="1200" height="675" fill="#071522" opacity=".20"/>'
    elif layout == 2:
        copy_css = "left:70px;right:70px;top:485px;bottom:34px;width:auto;justify-content:flex-end;text-align:left"
        title_css = "font-size:48px;max-width:1050px"
        scene_transform = "translate(0 -30) scale(1.04)"
        panel = '<rect x="0" y="445" width="1200" height="230" fill="#071522" opacity=".88"/>'
    else:
        copy_css = "left:70px;top:58px;bottom:50px;width:410px;justify-content:space-between;text-align:left"
        title_css = "font-size:56px;max-width:410px"
        scene_transform = "translate(80 0) scale(.92)"
        panel = '<path d="M0 0h560v675H0z" fill="#071522" opacity=".86"/>'
    if not show_title:
        title_block = ""
        title_visibility = "display:none"
    else:
        title_block = f'<div class="title">{title_html}</div>'
        title_visibility = ""
    dots = "".join(
        f'<circle cx="{110 + digest[i] % 980}" cy="{80 + digest[i+1] % 500}" r="{3 + digest[i+2] % 8}" fill="{pop}" opacity=".55"/>'
        for i in (0, 3, 6, 9, 12, 15)
    )
    template = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:1200px;height:675px;overflow:hidden}
body{font-family:Inter,-apple-system,"Segoe UI",Arial,sans-serif;background:__BG__;color:#f8fafc;position:relative}
.art{position:absolute;inset:0;width:1200px;height:675px}
.copy{position:absolute;__COPY__}
.kicker{font-size:15px;letter-spacing:.16em;font-weight:800;color:__ACCENT__;text-transform:uppercase;text-shadow:0 2px 12px #000}
.title{font-weight:850;line-height:1.02;letter-spacing:-.045em;text-shadow:0 3px 18px rgba(0,0,0,.55);__TITLE__}
.rule{width:76px;height:6px;border-radius:9px;background:__POP__;margin-top:16px}
.brand{display:flex;align-items:center;gap:10px;color:#fff;font-size:15px;font-weight:750;letter-spacing:.01em;text-shadow:0 2px 10px #000}
.mark{width:13px;height:13px;border:3px solid __ACCENT__;border-radius:4px;transform:rotate(45deg)}
</style></head><body>
<svg class="art" viewBox="0 0 1200 675" aria-hidden="true">__SCENE__</svg>
<div class="copy"><div><div class="kicker">__KICKER__</div><div class="rule"></div></div>__TITLE_BLOCK__
<div class="brand"><span class="mark"></span><span>The Digital Toolkit</span></div></div></body></html>"""
    values = {
        "__BG__": bg, "__ACCENT__": accent, "__POP__": pop, "__COPY__": copy_css,
        "__TITLE__": title_css,
        "__SCENE__": panel + f'<g transform="{scene_transform}">{scene}</g>' + dots,
        "__KICKER__": kicker_html, "__TITLE_BLOCK__": title_block,
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
    source_credit: str = ""


def _build_photo_cover_html(title: str, kicker: str, seed: str, brief: Optional[dict], photo_path: Path) -> str:
    """Compose a real stock photograph with flexible, readable editorial typography."""
    data = photo_path.read_bytes()
    suffix = photo_path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    if not mime:
        raise ValueError("Unsupported stock cover photo format.")
    photo_uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    title_text = str((brief or {}).get("cover_title") or title.strip())
    title_text = re.sub(r"\\s+", " ", title_text).strip()
    kicker_text = html.escape((kicker or "Guide").strip().upper())
    title_html = html.escape(title_text)
    layout = digest[0] % 3
    if layout == 0:
        copy_css = "left:64px;bottom:58px;max-width:760px"
        gradient = "linear-gradient(90deg,rgba(7,16,28,.88) 0%,rgba(7,16,28,.48) 62%,rgba(7,16,28,0) 100%)"
        title_size = "66px"
    elif layout == 1:
        copy_css = "left:64px;top:58px;max-width:720px"
        gradient = "linear-gradient(180deg,rgba(7,16,28,.78) 0%,rgba(7,16,28,.28) 58%,rgba(7,16,28,0) 100%)"
        title_size = "62px"
    else:
        copy_css = "left:64px;right:64px;bottom:48px;max-width:920px"
        gradient = "linear-gradient(0deg,rgba(7,16,28,.91) 0%,rgba(7,16,28,.40) 55%,rgba(7,16,28,0) 100%)"
        title_size = "58px"
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:1200px;height:675px;overflow:hidden}}
body{{font-family:Inter,-apple-system,"Segoe UI",Arial,sans-serif;color:#fff;background:#101820}}
.photo{{position:absolute;inset:0;background-image:{gradient},url("{photo_uri}");background-size:cover;background-position:center}}
.copy{{position:absolute;{copy_css};display:flex;flex-direction:column;gap:18px}}
.kicker{{font-size:15px;letter-spacing:.16em;font-weight:800;text-transform:uppercase;color:#fff;text-shadow:0 2px 12px #000}}
.title{{font-size:{title_size};font-weight:850;line-height:1.02;letter-spacing:-.04em;text-shadow:0 3px 18px rgba(0,0,0,.55);max-width:100%}}
.brand{{position:absolute;right:42px;bottom:32px;font-size:14px;font-weight:750;letter-spacing:.02em;color:#fff;text-shadow:0 2px 10px #000}}
</style></head><body><div class="photo"></div><div class="copy"><div class="kicker">{kicker_text}</div><div class="title">{title_html}</div></div><div class="brand">The Digital Toolkit</div></body></html>'''


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

    def generate(self, title: str, kicker: str, slug: str, brief: Optional[dict] = None, photo_path: Optional[Path] = None, source_credit: str = "") -> FeaturedImage:
        try:
            safe = re.sub(r"[^a-z0-9\\-]+", "-", slug.lower()).strip("-") or "article"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{safe}.jpg"
            # A downloaded stock photograph is composed locally; SVG remains the safe fallback.
            page_html = (_build_photo_cover_html(title, kicker, safe, brief, Path(photo_path))
                         if photo_path and Path(photo_path).is_file()
                         else build_html(title, kicker, seed=safe, brief=brief))
            self._render_png(page_html, path)
            data = path.read_bytes()
            if not data.startswith(JPEG_MAGIC) or len(data) < 2000:
                raise ValueError("rendered file is not a valid JPEG")
            return FeaturedImage(
                success=True, file_path=path, sha256=hashlib.sha256(data).hexdigest(),
                alt_text=(brief or {}).get("alt_text") or (f"Cover photograph illustrating: {title.strip()}" if photo_path and Path(photo_path).is_file() else f"Editorial cover graphic for: {title.strip()}"),
                source_credit=source_credit,
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
    photo_path: Optional[Path] = None,
    source_credit: str = "",
) -> Optional[FeaturedImage]:
    """Render the header image and, in live runs only, publish it. Returns None when disabled.

    Dry-runs render to output/featured/ for review but never commit anything to the repository.
    A failure here is never fatal: the article is simply published without a cover image.
    """
    if not enabled:
        return None
    image = (generator or FeaturedImageGenerator(output_dir)).generate(
        title, kicker, slug, brief=brief, photo_path=photo_path, source_credit=source_credit
    )
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

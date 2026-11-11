"""Visual utilities for Mermaid diagrams, image optimisation, and article QA.

The Python pipeline keeps Playwright as its only browser automation layer. Mermaid and
axe-core are loaded from locally installed npm packages; Sharp handles image conversion.
"""
import base64
import hashlib
import html
import json
import logging
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

MERMAID_JS = Path("tools/visuals/node_modules/mermaid/dist/mermaid.min.js")
AXE_JS = Path("tools/visuals/node_modules/axe-core/axe.min.js")
SHARP_SCRIPT = Path("scripts/optimize-image.mjs")


def generate_gemini_image(
    prompt: str,
    output_path: Path,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> Path:
    """Generate a single image through the Gemini API using the existing API key."""
    import os

    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured for image generation.")
    model_name = model or os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "responseFormat": {"image": {"aspectRatio": aspect_ratio, "imageSize": "1K"}},
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"Gemini image API returned HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini image generation request failed: {exc}") from exc

    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline or not inline.get("data"):
                continue
            mime = (inline.get("mimeType") or inline.get("mime_type") or "image/png").lower()
            extension = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
            target = Path(output_path).with_suffix(extension)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(inline["data"]))
            data = target.read_bytes()
            valid = data.startswith(b"\\xff\\xd8\\xff") if extension == ".jpg" else data.startswith(b"\\x89PNG\\r\\n\\x1a\\n")
            if not valid or len(data) < 5000:
                target.unlink(missing_ok=True)
                raise RuntimeError("Gemini returned invalid or unexpectedly small image data.")
            return target
    raise RuntimeError("Gemini returned no image data.")

def optimize_image(path: Path, output_format: str = "webp") -> Path:
    """Convert raster images to compact WebP with Sharp; safely retain the original on failure."""
    path = Path(path)
    if not path.is_file() or path.suffix.lower() in {".svg", ".webp"}:
        return path
    if not SHARP_SCRIPT.is_file():
        logger.info("Sharp optimiser is unavailable; keeping original image.")
        return path
    target = path.with_suffix(f".{output_format}")
    try:
        subprocess.run(
            ["node", str(SHARP_SCRIPT), str(path), str(target)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        if target.is_file() and target.stat().st_size > 0:
            if target.stat().st_size < path.stat().st_size:
                return target
            target.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Sharp optimisation failed; keeping original image: %s", exc)
        target.unlink(missing_ok=True)
    return path


def render_mermaid_svg(source: str, output_path: Path) -> Path:
    """Render one Mermaid diagram to a self-contained SVG using the existing Playwright Chromium."""
    if not MERMAID_JS.is_file():
        raise RuntimeError("Mermaid is not installed. Run npm install in tools/visuals.")
    from playwright.sync_api import sync_playwright  # type: ignore

    safe_source = html.escape(source.strip())
    page_html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<style>body{margin:0;padding:24px;background:#fff;font-family:Arial,sans-serif}'
        '.mermaid{display:flex;justify-content:center}</style></head>'
        f'<body><pre class="mermaid">{safe_source}</pre></body></html>'
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 900}, device_scale_factor=1)
            page.set_content(page_html, wait_until="load")
            page.add_script_tag(path=str(MERMAID_JS.resolve()))
            page.evaluate("""async () => {
                window.mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral' });
                await window.mermaid.run({ querySelector: '.mermaid' });
            }""")
            page.wait_for_selector(".mermaid svg", timeout=15000)
            svg = page.locator(".mermaid svg").evaluate("(node) => node.outerHTML")
            if not svg or "<svg" not in svg:
                raise RuntimeError("Mermaid did not return an SVG diagram.")
            output_path.write_text(svg, encoding="utf-8")
        finally:
            browser.close()
    return output_path


def render_mermaid_blocks(
    article_html: str,
    output_dir: str,
    publisher: Optional[Callable[[Path, str, str], Optional[str]]] = None,
) -> tuple[str, list[dict]]:
    """Render useful Mermaid blocks and replace them only when a public asset URL is available."""
    pattern = re.compile(
        r'<pre\\b[^>]*class=["\'][^"\']*\\bmermaid\\b[^"\']*["\'][^>]*>(.*?)</pre\\s*>',
        re.I | re.S,
    )
    items: list[dict] = []
    updated = article_html
    for index, match in enumerate(list(pattern.finditer(article_html)), start=1):
        source = html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
        if not source or len(source) > 12000:
            continue
        try:
            svg_path = Path(output_dir) / "visuals" / f"diagram-{index}.svg"
            render_mermaid_svg(source, svg_path)
            digest = hashlib.sha256(svg_path.read_bytes()).hexdigest()
            public_url = publisher(svg_path, f"diagram-{index}", digest) if publisher else None
            if public_url and public_url.startswith("https://"):
                figure = (
                    '<figure class="article-visual article-diagram" style="margin:26px auto;max-width:900px;">'
                    f'<img src="{html.escape(public_url)}" alt="Explanatory diagram for this section" '
                    'loading="lazy" style="display:block;width:100%;height:auto;margin:auto;" />'
                    '</figure>'
                )
                updated = updated.replace(match.group(0), figure, 1)
                items.append({"path": str(svg_path), "url": public_url, "kind": "diagram"})
            else:
                items.append({"path": str(svg_path), "url": None, "kind": "diagram"})
        except Exception as exc:
            logger.warning("Could not render Mermaid diagram %s: %s", index, exc)
    return updated, items


def audit_html_accessibility(article_html: str, output_path: Optional[str] = None) -> dict:
    """Run axe-core against article markup. Findings are reported, not used as a false-positive hard gate."""
    if not AXE_JS.is_file():
        return {"available": False, "violations": [], "error": "axe-core is not installed"}
    from playwright.sync_api import sync_playwright  # type: ignore

    result = {"available": True, "violations": [], "passes": 0, "incomplete": 0}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.set_content(article_html, wait_until="domcontentloaded")
            page.add_script_tag(path=str(AXE_JS.resolve()))
            report = page.evaluate("async () => await axe.run(document)")
            result["violations"] = [
                {
                    "id": item.get("id"),
                    "impact": item.get("impact"),
                    "description": item.get("description"),
                    "help": item.get("help"),
                    "nodes": len(item.get("nodes", [])),
                }
                for item in report.get("violations", [])
            ]
            result["passes"] = len(report.get("passes", []))
            result["incomplete"] = len(report.get("incomplete", []))
        finally:
            browser.close()
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def capture_article_previews(article_html: str, output_dir: str) -> list[str]:
    """Save mobile and desktop article previews for visual review in the run report."""
    from playwright.sync_api import sync_playwright  # type: ignore

    out = Path(output_dir) / "visual-previews"
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for name, width, height in (("mobile", 390, 844), ("desktop", 1280, 900)):
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.set_content(article_html, wait_until="domcontentloaded")
                page.screenshot(path=str(out / f"article-{name}.png"), full_page=True)
                saved.append(str(out / f"article-{name}.png"))
                page.close()
        finally:
            browser.close()
    return saved

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
import xml.etree.ElementTree as ET
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
    model: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> Path:
    """Generate an image only after explicit paid-image opt-in.

    The article-writing Gemini keys are deliberately not reused. Image generation
    requires a dedicated GEMINI_IMAGE_API_KEY and three independent opt-ins so a
    free-tier pipeline can never incur an image-generation charge by accident.
    """
    import os

    provider = os.getenv("IMAGE_PROVIDER", "local").strip().lower()
    enabled = os.getenv("GEMINI_IMAGE_GENERATION_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
    allow_paid = os.getenv("ALLOW_PAID_IMAGE_GENERATION", "false").strip().lower() in ("1", "true", "yes", "on")
    if provider != "gemini" or not enabled or not allow_paid:
        raise RuntimeError(
            "Gemini image generation is disabled. It requires IMAGE_PROVIDER=gemini, "
            "GEMINI_IMAGE_GENERATION_ENABLED=true, and ALLOW_PAID_IMAGE_GENERATION=true."
        )

    key = os.getenv("GEMINI_IMAGE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_IMAGE_API_KEY is not configured; article-writing Gemini keys are not used for images.")
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
            valid = data.startswith(b"\xff\xd8\xff") if extension == ".jpg" else data.startswith(b"\x89PNG\r\n\x1a\n")
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


def _validate_mermaid_svg(svg: str) -> bool:
    """Reject malformed or dimensionless Mermaid output before it reaches an article."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return False
    if root.tag.split("}")[-1].lower() != "svg":
        return False
    view_box = root.attrib.get("viewBox", "").replace(",", " ").split()
    if len(view_box) != 4:
        return False
    try:
        _, _, width, height = (float(value) for value in view_box)
    except (TypeError, ValueError):
        return False
    return width > 0 and height > 0


def render_mermaid_svg(source: str, output_path: Path) -> Path:
    """Render one Mermaid diagram to a self-contained SVG using the existing Playwright Chromium."""
    if not MERMAID_JS.is_file():
        raise RuntimeError("Mermaid is not installed. Run npm install in tools/visuals.")
    from playwright.sync_api import sync_playwright  # type: ignore

    safe_source = html.escape(source.strip())
    page_html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<style>'
        ':root{color-scheme:light}'
        'html,body{margin:0;min-height:100%;background:#fff}'
        'body{padding:36px;box-sizing:border-box;font-family:Inter,Arial,sans-serif}'
        '.mermaid{display:flex;justify-content:center;align-items:center;width:100%;}'
        '.mermaid svg{max-width:100%;height:auto;overflow:visible;}'
        '.mermaid .node rect,.mermaid .node polygon,.mermaid .node circle{stroke-width:1.7px;}'
        '.mermaid .edgePath .path{stroke-width:1.8px;}'
        '.mermaid .edgeLabel{background:#fff;}'
        '</style></head>'
        f'<body><pre class="mermaid">{safe_source}</pre></body></html>'
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": 1600, "height": 1200},
                device_scale_factor=2,
                color_scheme="light",
            )
            page.set_content(page_html, wait_until="load")
            page.add_script_tag(path=str(MERMAID_JS.resolve()))
            page.evaluate("""async () => {
                window.mermaid.initialize({
                    startOnLoad: false,
                    securityLevel: 'strict',
                    theme: 'base',
                    themeVariables: {
                        fontFamily: 'Inter, Arial, sans-serif',
                        fontSize: '16px',
                        background: '#ffffff',
                        primaryColor: '#e8f5f2',
                        primaryTextColor: '#142b35',
                        primaryBorderColor: '#167d78',
                        lineColor: '#52717a',
                        secondaryColor: '#edf3fb',
                        secondaryTextColor: '#142b35',
                        secondaryBorderColor: '#54759a',
                        tertiaryColor: '#fff7e8',
                        tertiaryTextColor: '#42351e',
                        tertiaryBorderColor: '#c58a2b',
                        mainBkg: '#e8f5f2',
                        nodeBorder: '#167d78',
                        clusterBkg: '#f5f8fa',
                        clusterBorder: '#cbd5e1',
                        edgeLabelBackground: '#ffffff'
                    },
                    flowchart: {
                        curve: 'basis',
                        nodeSpacing: 56,
                        rankSpacing: 68,
                        padding: 18,
                        htmlLabels: true
                    }
                });
                await document.fonts.ready;
                await window.mermaid.run({ querySelector: '.mermaid' });
            }""")
            page.wait_for_selector(".mermaid svg", timeout=15000)
            page.wait_for_function("""() => {
                const svg = document.querySelector('.mermaid svg');
                if (!svg) return false;
                const box = svg.getBBox();
                return box.width > 0 && box.height > 0;
            }""", timeout=10000)
            svg = page.locator(".mermaid svg").evaluate("""(node) => {
                node.setAttribute('role', 'img');
                node.setAttribute('aria-label', 'The Digital Toolkit explanatory diagram');
                node.setAttribute('preserveAspectRatio', 'xMidYMid meet');
                node.style.maxWidth = '100%';
                node.style.height = 'auto';
                node.style.display = 'block';
                node.style.margin = '0 auto';
                return node.outerHTML;
            }""")
            if not svg or not _validate_mermaid_svg(svg):
                raise RuntimeError("Mermaid returned an invalid or dimensionless SVG diagram.")
            output_path.write_text(svg, encoding="utf-8")
        finally:
            browser.close()
    return output_path


def render_mermaid_blocks(
    article_html: str,
    output_dir: str,
    publisher: Optional[Callable[[Path, str, str], Optional[str]]] = None,
    max_items: int = 2,
) -> tuple[str, list[dict]]:
    """Render useful Mermaid blocks and replace them only when a public asset URL is available."""
    pattern = re.compile(
        r'<pre\b[^>]*class=["\'][^"\']*\bmermaid\b[^"\']*["\'][^>]*>(.*?)</pre\s*>',
        re.I | re.S,
    )
    items: list[dict] = []
    updated = article_html
    for index, match in enumerate(list(pattern.finditer(article_html))[:max(0, max_items)], start=1):
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
    scan_target = "final article HTML in an isolated browser document; live Blogger theme and surrounding page are not included"
    if not AXE_JS.is_file():
        result = {
            "available": False, "target": scan_target, "violations": [],
            "passes": 0, "incomplete": 0, "error": "axe-core is not installed",
        }
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    from playwright.sync_api import sync_playwright  # type: ignore

    result = {
        "available": True, "target": scan_target, "violations": [],
        "passes": 0, "incomplete": 0, "error": None,
    }
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


def _render_editorial_svg(plan: dict, output_path: Path, index: int) -> Path:
    """Create a clean, topic-aware editorial illustration using local SVG only.

    This deliberately creates conceptual artwork, not a simulated product interface
    or a screenshot. It has no network, API, font, or external-asset dependency.
    """
    heading = re.sub(r"\s+", " ", str(plan.get("section_heading", "A closer look"))).strip()
    prompt = re.sub(r"\s+", " ", str(plan.get("prompt", ""))).strip()
    concept = (heading + " " + prompt).lower()
    palettes = (
        ("#14251f", "#a7f3d0", "#fbbf24", "#ecfdf5"),
        ("#101b36", "#6ee7f9", "#f59e0b", "#dbeafe"),
        ("#251638", "#c4b5fd", "#fb7185", "#f5f3ff"),
    )
    bg, accent, pop, ink = palettes[(index - 1) % len(palettes)]
    if any(word in concept for word in ("step", "process", "workflow", "sequence", "automate")):
        motif = (
            '<g fill="none" stroke="' + accent + '" stroke-width="8" stroke-linecap="round">'
            '<path d="M245 350H955"/><path d="M875 285l80 65-80 65"/></g>'
            '<g fill="' + bg + '" stroke="' + accent + '" stroke-width="5">'
            '<rect x="150" y="260" width="210" height="180" rx="28"/>'
            '<rect x="495" y="260" width="210" height="180" rx="28"/>'
            '<rect x="840" y="260" width="210" height="180" rx="28"/></g>'
            '<g fill="' + pop + '"><circle cx="255" cy="315" r="22"/><circle cx="600" cy="315" r="22"/><circle cx="945" cy="315" r="22"/></g>'
            '<g fill="' + ink + '" font-family="Arial,sans-serif" font-size="25" font-weight="700" text-anchor="middle">'
            '<text x="255" y="380">INPUT</text><text x="600" y="380">WORK</text><text x="945" y="380">RESULT</text></g>'
        )
    elif any(word in concept for word in ("compare", "versus", "difference", "choose", "option")):
        motif = (
            '<g><circle cx="390" cy="345" r="145" fill="' + accent + '" opacity=".18" stroke="' + accent + '" stroke-width="5"/>'
            '<circle cx="810" cy="345" r="145" fill="' + pop + '" opacity=".18" stroke="' + pop + '" stroke-width="5"/>'
            '<path d="M600 205v280" stroke="' + ink + '" stroke-width="3" stroke-dasharray="10 14" opacity=".45"/>'
            '<path d="M325 345h130M390 280v130M745 345h130" stroke="' + accent + '" stroke-width="13" stroke-linecap="round"/>'
            '<path d="M810 280v130" stroke="' + pop + '" stroke-width="13" stroke-linecap="round"/></g>'
        )
    else:
        motif = (
            '<circle cx="600" cy="345" r="175" fill="' + accent + '" opacity=".10"/>'
            '<circle cx="600" cy="345" r="125" fill="none" stroke="' + accent + '" stroke-width="5"/>'
            '<circle cx="600" cy="345" r="78" fill="' + pop + '" opacity=".25"/>'
            '<path d="M600 220v250M475 345h250M512 257l176 176M688 257L512 433" stroke="' + accent + '" stroke-width="4" opacity=".7"/>'
            '<circle cx="600" cy="345" r="25" fill="' + pop + '"/>'
        )
    safe_heading = html.escape(heading[:90])
    svg = "".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" role="img" aria-label="',
        html.escape(heading or "Editorial illustration"), '">',
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '<stop offset="0" stop-color="', bg, '"/><stop offset="1" stop-color="#0b1220"/></linearGradient></defs>',
        '<rect width="1200" height="675" rx="28" fill="url(#bg)"/>',
        '<path d="M0 520Q300 450 600 545T1200 500V675H0Z" fill="', accent, '" opacity=".06"/>',
        '<text x="78" y="82" fill="', accent, '" font-family="Arial,sans-serif" font-size="20" font-weight="700" letter-spacing="5">THE DIGITAL TOOLKIT  /  FIELD GUIDE</text>',
        motif,
        '<text x="78" y="585" fill="', ink, '" font-family="Arial,sans-serif" font-size="35" font-weight="700">', safe_heading, '</text>',
        '<text x="78" y="625" fill="', accent, '" font-family="Arial,sans-serif" font-size="16" letter-spacing="2">EXPLANATORY ILLUSTRATION</text></svg>',
    ])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return output_path


def generate_supporting_visuals(
    visual_plan: list[dict],
    output_dir: str,
    publisher: Optional[Callable[[Path, str, str], Optional[str]]] = None,
    max_items: int = 2,
) -> list[dict]:
    """Generate useful supporting illustrations locally and return safely hosted assets.

    No image-generation API is called. A visual is included only when the article
    explicitly supplies a meaningful visual plan and a public HTTPS asset URL is
    available from the repository publisher.
    """
    items = []
    plans = (visual_plan or [])[:max(0, min(2, max_items))]
    for index, plan in enumerate(plans, start=1):
        if not isinstance(plan, dict):
            continue
        heading = str(plan.get("section_heading", "")).strip()
        alt_text = str(plan.get("alt_text", "")).strip()
        prompt = str(plan.get("prompt", "")).strip()
        if not heading or not alt_text or not prompt:
            continue
        try:
            path = _render_editorial_svg(
                plan, Path(output_dir) / "visuals" / f"supporting-{index}.svg", index
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            public_url = publisher(path, f"supporting-{index}", digest) if publisher else None
            items.append({
                "path": str(path),
                "url": public_url if public_url and public_url.startswith("https://") else None,
                "alt": alt_text[:240],
                "caption": str(plan.get("caption", ""))[:300],
                "section_heading": heading[:180],
                "kind": "illustration",
            })
        except Exception as exc:
            logger.warning("Supporting illustration %s could not be generated: %s", index, exc)
    return items

def inject_visual_figures(article_html: str, visual_items: list[dict]) -> str:
    """Insert hosted custom visuals after the first explanatory paragraph of their target section."""
    updated = article_html
    for item in visual_items or []:
        url = item.get("url", "")
        if not url.startswith("https://") or any(token in url.lower() for token in ("localhost", "127.0.0.1")):
            continue
        alt = html.escape(str(item.get("alt", "Editorial article visual")))
        caption = html.escape(str(item.get("caption", "")))
        figure = (
            '<figure class="article-visual" style="margin:26px auto;max-width:900px;text-align:center;">'
            f'<img src="{html.escape(url)}" alt="{alt}" loading="lazy" '
            'style="display:block;width:100%;height:auto;margin:0 auto;border-radius:8px;" />'
            f'<figcaption style="font-size:13px;line-height:1.5;color:#64748b;margin-top:9px;">{caption}</figcaption>'
            '</figure>'
        )
        heading_text = re.sub(r"\s+", " ", html.unescape(str(item.get("section_heading", "")))).strip().lower()
        headings = list(re.finditer(r"<h([23])\b[^>]*>(.*?)</h\1\s*>", updated, re.I | re.S))
        target = None
        for index, heading in enumerate(headings):
            label = re.sub(r"<[^>]+>", " ", html.unescape(heading.group(2)))
            label = re.sub(r"\s+", " ", label).strip().lower()
            if heading_text and (heading_text == label or heading_text in label or label in heading_text):
                section_end = headings[index + 1].start() if index + 1 < len(headings) else len(updated)
                paragraph = re.search(r"</p\s*>", updated[heading.end():section_end], re.I)
                target = heading.end() + paragraph.end() if paragraph else heading.end()
                break
        if target is None:
            refs = re.search(r"<h[23]\b[^>]*>[^<]*(?:sources?|references?)\b.*?</h[23]\s*>", updated, re.I | re.S)
            target = refs.start() if refs else len(updated)
        updated = updated[:target] + "\n" + figure + updated[target:]
    return updated


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
                page = browser.new_page(
                    viewport={"width": width, "height": height},
                    device_scale_factor=2,
                    color_scheme="light",
                )
                page.set_content(article_html, wait_until="domcontentloaded")
                page.evaluate("""async () => {
                    await document.fonts.ready;
                    await Promise.all(Array.from(document.images).map((img) => {
                        if (img.complete) return Promise.resolve();
                        return new Promise((resolve) => {
                            img.addEventListener('load', resolve, { once: true });
                            img.addEventListener('error', resolve, { once: true });
                        });
                    }));
                }""")
                if MERMAID_JS.is_file() and page.locator(".mermaid").count():
                    page.add_script_tag(path=str(MERMAID_JS.resolve()))
                    page.evaluate("""async () => {
                        window.mermaid.initialize({
                            startOnLoad: false,
                            securityLevel: 'strict',
                            theme: 'base',
                            themeVariables: {
                                fontFamily: 'Inter, Arial, sans-serif',
                                fontSize: '16px',
                                background: '#ffffff',
                                primaryColor: '#e8f5f2',
                                primaryTextColor: '#142b35',
                                primaryBorderColor: '#167d78',
                                lineColor: '#52717a',
                                secondaryColor: '#edf3fb',
                                secondaryBorderColor: '#54759a',
                                tertiaryColor: '#fff7e8',
                                tertiaryBorderColor: '#c58a2b',
                                edgeLabelBackground: '#ffffff'
                            },
                            flowchart: { curve: 'basis', nodeSpacing: 56, rankSpacing: 68, padding: 18 }
                        });
                        await window.mermaid.run({ querySelector: '.mermaid' });
                    }""")
                page.screenshot(
                    path=str(out / f"article-{name}.png"),
                    full_page=True,
                    animations="disabled",
                )
                saved.append(str(out / f"article-{name}.png"))
                page.close()
        finally:
            browser.close()
    return saved

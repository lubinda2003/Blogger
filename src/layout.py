"""Turns the writer's simple semantic components into styled HTML that works in any Blogger theme.

The writer only emits plain components (quick-answer, tip, warning, steps, compare table). This module adds the
styling as inline attributes, so it does not depend on the theme, needs no <style> block and no scripts, and uses
translucent colours so it reads well on both light and dark themes. It also removes anything unsafe from the
model's HTML and builds a table of contents for longer articles.
"""

import html
import re

GOLD = "#d4af37"
_BORDER = "rgba(128,128,128,.35)"
_LABEL = "font-weight:700;font-size:.78em;letter-spacing:.08em;text-transform:uppercase;margin:0 0 6px 0;"
_BOX = "padding:14px 18px;margin:20px 0;border-radius:6px;border-left:4px solid {color};background:{bg};"

# class name -> (label, accent colour, translucent background)
CALLOUTS = {
    "quick-answer": ("Quick answer", GOLD, "rgba(212,175,55,.12)"),
    "tip": ("Tip", "#2e9e6b", "rgba(46,158,107,.12)"),
    "warning": ("Heads up", "#d9822b", "rgba(217,130,43,.13)"),
}

_DANGEROUS_BLOCKS = re.compile(r"<(script|style|iframe|object|embed|form|noscript)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_DANGEROUS_TAGS = re.compile(r"<(script|style|iframe|object|embed|form|link|meta|base)\b[^>]*/?>", re.I)
_EVENT_ATTRS = re.compile(r"""\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_JS_URLS = re.compile(r"""(href|src)\s*=\s*(["'])\s*javascript:[^"']*\2""", re.I)


def sanitize_html(body: str) -> str:
    """Remove scripts, embeds, event handlers and javascript: links from model-written HTML."""
    out = _DANGEROUS_BLOCKS.sub("", body or "")
    out = _DANGEROUS_TAGS.sub("", out)
    out = _EVENT_ATTRS.sub("", out)
    return _JS_URLS.sub(lambda m: f"{m.group(1)}={m.group(2)}#{m.group(2)}", out)



_REFERENCE_HEADING = re.compile(r"<h([23])\b[^>]*>(.*?)</h\1\s*>", re.I | re.S)
_REFERENCE_WORDS = re.compile(r"\b(?:sources?|references?|resources?)\b", re.I)


def deduplicate_reference_sections(body: str) -> str:
    """Keep only the first final source/reference section; remove repeated variants."""
    headings = list(_REFERENCE_HEADING.finditer(body or ""))
    reference_headings = []
    for match in headings:
        label = re.sub(r"<[^>]+>", " ", html.unescape(match.group(2)))
        if _REFERENCE_WORDS.search(label) and len(label.split()) <= 5:
            reference_headings.append(match)

    if len(reference_headings) < 2:
        return body

    # Preserve the first section. Later duplicate reference sections are removed
    # through the next heading, or to the end when they are the final section.
    removals = []
    for match in reference_headings[1:]:
        next_heading = next((h for h in headings if h.start() > match.start()), None)
        end = next_heading.start() if next_heading else len(body)
        removals.append((match.start(), end))

    for start, end in reversed(removals):
        body = body[:start] + body[end:]
    return body


def _slug(text: str) -> str:
    plain = re.sub(r"<[^>]+>", "", html.unescape(text)).lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "section"


def add_table_of_contents(body: str, min_headings: int = 4) -> str:
    """Give every plain <h2> an id and add an 'In this guide' list before the first one (4+ headings only)."""
    if 'aria-label="Table of contents"' in body:
        return body
    matches = list(re.finditer(r"<h2>(.*?)</h2>", body, flags=re.S))
    if len(matches) < min_headings:
        return body
    used, entries, replacements = set(), [], []
    for m in matches:
        base = _slug(m.group(1))
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        label = html.escape(re.sub(r"<[^>]+>", "", html.unescape(m.group(1))).strip())
        entries.append(f'<li><a href="#{slug}">{label}</a></li>')
        replacements.append((m.start(), m.end(), f'<h2 id="{slug}" style="scroll-margin-top:80px;">{m.group(1)}</h2>'))
    for start, end, new in reversed(replacements):  # back to front so earlier offsets stay valid
        body = body[:start] + new + body[end:]
    toc = (
        f'<nav aria-label="Table of contents" style="margin:20px 0;padding:14px 18px;border:1px solid {_BORDER};'
        f'border-radius:6px;">\n<p style="{_LABEL}">In this guide</p>\n'
        f'<ul style="margin:0;padding-left:1.3em;">\n' + "\n".join(entries) + "\n</ul>\n</nav>\n"
    )
    first_h2 = body.index("<h2")
    return body[:first_h2] + toc + body[first_h2:]


def _style_callouts(body: str) -> str:
    for name, (label, color, bg) in CALLOUTS.items():
        body = body.replace(
            f'<div class="{name}">',
            f'<div class="{name}" role="note" style="{_BOX.format(color=color, bg=bg)}">\n'
            f'<p style="{_LABEL}">{label}</p>',
        )
    return body


def _style_steps(body: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        inner = re.sub(r"<li>", '<li style="margin-bottom:10px;">', m.group(1))
        return f'<ol class="steps" style="padding-left:1.5em;margin:16px 0;">{inner}</ol>'

    return re.sub(r'<ol class="steps">(.*?)</ol>', repl, body, flags=re.S)


def _style_compare_tables(body: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        inner = m.group(1)
        inner = re.sub(
            r"<th>", f'<th style="text-align:left;padding:10px 12px;border:1px solid {_BORDER};background:rgba(212,175,55,.18);">', inner
        )
        inner = re.sub(r"<td>", f'<td style="padding:10px 12px;border:1px solid {_BORDER};vertical-align:top;">', inner)
        return (
            '<div style="overflow-x:auto;margin:22px 0;">\n'
            f'<table class="compare" style="border-collapse:collapse;width:100%;min-width:480px;">{inner}</table>\n</div>'
        )

    return re.sub(r'<table class="compare">(.*?)</table>', repl, body, flags=re.S)


def convert_markdown_tables(body: str) -> str:
    """Convert Markdown pipe tables in generated article HTML into Blogger-safe comparison tables."""
    lines = (body or "").splitlines()
    output = []
    i = 0
    while i < len(lines):
        header = lines[i].strip()
        if i + 1 < len(lines):
            separator = lines[i + 1].strip()
            cells = [cell.strip() for cell in header.strip("|").split("|")]
            separators = [cell.strip() for cell in separator.strip("|").split("|")]
            is_table = (len(cells) >= 2 and len(cells) == len(separators) and
                        all(re.fullmatch(r":?-{3,}:?", cell) for cell in separators))
            if is_table:
                rows = []
                i += 2
                while i < len(lines) and "|" in lines[i]:
                    row = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                    if len(row) != len(cells):
                        break
                    rows.append(row)
                    i += 1
                def render_cell(value: str, tag: str) -> str:
                    return f"<{tag}>{html.escape(value, quote=False)}</{tag}>"
                head = "<thead><tr>" + "".join(render_cell(value, "th") for value in cells) + "</tr></thead>"
                body_rows = "".join("<tr>" + "".join(render_cell(value, "td") for value in row) + "</tr>" for row in rows)
                output.append(f'<table class="compare">{head}<tbody>{body_rows}</tbody></table>')
                continue
        output.append(lines[i])
        i += 1
    return "\n".join(output)

def apply_layout(body: str) -> str:
    """Sanitize, add the table of contents, then style the components. Safe to apply twice."""
    body = convert_markdown_tables(body)
    body = sanitize_html(body)
    body = deduplicate_reference_sections(body)
    body = add_table_of_contents(body)
    body = _style_callouts(body)
    body = _style_steps(body)
    return _style_compare_tables(body)

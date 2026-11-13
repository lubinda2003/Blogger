"""SEO metadata validation, label normalization, and Schema.org structured data generation."""

import html
import json
import re
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional


class SEOMetadata:
    """Manages SEO tags, meta descriptions, labels, and structured schema."""

    KNOWN_ACRONYMS = {"ai", "api", "ui", "ux", "seo", "pdf", "nrc", "zmw", "usd", "kyc", "html", "css", "js", "sql", "pwa", "llm", "id", "faq", "url"}

    @staticmethod
    def normalize_labels(labels: List[str]) -> List[str]:
        """Clean and normalize Blogger labels (tags).

        Preserves known acronyms and formats title-cased labels.
        """
        cleaned = []
        seen = set()
        for label in labels:
            if not label:
                continue
            norm = re.sub(r"[#@!$%^&*()+=<>]", "", label).strip()
            if len(norm) >= 2:
                words = norm.split()
                processed_words = []
                for w in words:
                    if w.lower() in SEOMetadata.KNOWN_ACRONYMS:
                        processed_words.append(w.upper())
                    elif w.lower() == "chatgpt":
                        processed_words.append("ChatGPT")
                    elif w.lower() == "upwork":
                        processed_words.append("Upwork")
                    elif w.lower() == "shopify":
                        processed_words.append("Shopify")
                    elif w.lower() == "notion":
                        processed_words.append("Notion")
                    elif w.lower() == "obsidian":
                        processed_words.append("Obsidian")
                    elif w.lower() == "canva":
                        processed_words.append("Canva")
                    elif w.lower() == "gumroad":
                        processed_words.append("Gumroad")
                    elif w.lower() == "payoneer":
                        processed_words.append("Payoneer")
                    elif any(c.isupper() for c in w[1:]):
                        processed_words.append(w)  # already mixed-case (NotebookLM, iPhone): keep as written
                    else:
                        processed_words.append(w.capitalize())
                norm_formatted = " ".join(processed_words)
                if norm_formatted.lower() not in seen:
                    seen.add(norm_formatted.lower())
                    cleaned.append(norm_formatted)
        return cleaned[:6]

    @staticmethod
    def generate_schema_jsonld(
        title: str,
        description: str,
        url: Optional[str] = None,
        date_published: Optional[str] = None,
        author_name: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> str:
        """Generate valid Schema.org Article JSON-LD for rich snippets."""
        schema_dict: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": title,
            "description": description,
            # A real person only if one is configured; never an invented "team" persona.
            "author": (
                {"@type": "Person", "name": author_name}
                if author_name
                else {
                    "@type": "Organization",
                    "name": "The Digital Toolkit",
                    "url": "https://digitaltoolkitguide.blogspot.com/p/about-digital-toolkit.html",
                }
            ),
            "publisher": {
                "@type": "Organization",
                "name": "The Digital Toolkit",
                "url": "https://digitaltoolkitguide.blogspot.com/",
            },
            "inLanguage": "en",
        }
        if image_url:
            schema_dict["image"] = image_url
        if url:
            schema_dict["mainEntityOfPage"] = url
        if date_published:
            schema_dict["datePublished"] = date_published

        json_str = json.dumps(schema_dict, indent=2, ensure_ascii=False)
        return f'<script type="application/ld+json">\n{json_str}\n</script>'

    @staticmethod
    def _place_screenshot_in_section(body: str, image_url: str, figure: str, source_url: Optional[str] = None, used_sections: Optional[set] = None) -> str:
        """Place screenshots beside distinct relevant sections, not in one product gallery."""
        from urllib.parse import unquote
        used_sections = used_sections if used_sections is not None else set()
        parsed = urlparse(source_url or image_url)
        path_terms = set(re.findall(r"[a-z]{3,}", unquote(parsed.path).lower()))
        path_terms -= {"www", "help", "docs", "app", "com", "html", "page", "pages"}
        headings = list(re.finditer(r"<h([23])\b[^>]*>(.*?)</h\1\s*>", body, re.I | re.S))
        candidates = []
        for index, heading in enumerate(headings):
            label = re.sub(r"<[^>]+>", " ", html.unescape(heading.group(2)))
            label = re.sub(r"\s+", " ", label).strip()
            key = label.casefold()
            if not key or key in used_sections or re.search(r"\b(faq|frequently asked|sources|references|conclusion)\b", key):
                continue
            end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
            section = re.sub(r"<[^>]+>", " ", html.unescape(body[heading.end():end])).lower()
            words = set(re.findall(r"[a-z]{3,}", (label + " " + section[:1200]).lower()))
            candidates.append((len(path_terms & words), heading, key, end))
        if candidates:
            score = max(item[0] for item in candidates)
            _, heading, key, end = next(item for item in candidates if item[0] == score)
            paragraph = re.search(r"</p\s*>", body[heading.end():end], re.I)
            target = heading.end() + paragraph.end() if paragraph else heading.end()
            used_sections.add(key)
            return body[:target] + "\n" + figure + body[target:]
        refs = re.search(r"<h[23]\b.*?\b(?:sources?|references?)\b.*?</h[23]\s*>", body, re.I | re.S)
        target = refs.start() if refs else len(body)
        return body[:target] + "\n" + figure + body[target:]

    @staticmethod
    def inject_seo_and_assets(
        html_body: str,
        title: str,
        meta_description: str,
        public_screenshot_url: Optional[str] = None,
        screenshot_caption: Optional[str] = None,
        screenshot_alt: Optional[str] = None,
        include_schema: bool = True,
        featured_image_url: Optional[str] = None,
        featured_image_alt: Optional[str] = None,
        public_screenshot_items: Optional[List[Dict[str, str]]] = None,
        schema_url: Optional[str] = None,
        date_published: Optional[str] = None,
    ) -> str:
        """Inject structured data and optional public screenshot image markup into article HTML.

        SECURITY & INTEGRITY RULE: Never inject local runner paths (e.g. output/..., /app/...).
        Only inject images when a verified public HTTPS URL is provided.
        """
        blocks: List[str] = []

        # Only expose a verified public HTTPS cover URL in either HTML or structured data.
        public_featured_image_url = (
            featured_image_url
            if featured_image_url and featured_image_url.startswith("https://") and not any(
                sub in featured_image_url for sub in ("localhost", "127.0.0.1", "output/")
            )
            else None
        )

        if include_schema:
            schema = SEOMetadata.generate_schema_jsonld(
                title=title,
                description=meta_description,
                url=schema_url if schema_url and schema_url.startswith(("https://", "http://")) else None,
                date_published=date_published,
                image_url=public_featured_image_url,
            )
            blocks.append(schema)

        # Cover image: same strict public-HTTPS rule as screenshots. Explicit width/height avoid layout shift.
        if public_featured_image_url:
            blocks.append(
                f'<figure class="article-cover" style="margin:0 0 24px 0;">\n'
                f'  <img src="{html.escape(public_featured_image_url)}" alt="{html.escape(featured_image_alt or title)}" '
                f'width="1200" height="630" loading="eager" style="width:100%; max-width:100%; height:auto; border-radius:8px;" />\n'
                f'</figure>'
            )

        # Place each verified screenshot in the article section it illustrates.
        screenshot_items = public_screenshot_items or (
            [{"url": public_screenshot_url, "caption": screenshot_caption or "", "alt": screenshot_alt or title}]
            if public_screenshot_url else []
        )
        body_with_screenshots = html_body
        seen_urls = set()
        used_screenshot_sections = set()
        for item in screenshot_items:
            image_url = item.get("url", "")
            if not image_url.startswith("https://") or any(
                sub in image_url for sub in ("localhost", "127.0.0.1", "output/")
            ) or image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            clean_alt = html.escape(item.get("alt", title))
            clean_caption = html.escape(item.get("caption", ""))
            figure = (
                '<figure class="article-screenshot" style="margin:24px auto 28px;max-width:900px;text-align:center;">\n'
                f'  <img src="{html.escape(image_url)}" alt="{clean_alt}" loading="lazy" '
                'style="display:block;width:100%;max-width:100%;height:auto;margin:0 auto;border-radius:8px;border:1px solid #e2e8f0;" />\n'
                f'  <figcaption style="font-size:13px;line-height:1.5;color:#64748b;margin-top:9px;">{clean_caption}</figcaption>\n'
                '</figure>'
            )
            body_with_screenshots = SEOMetadata._place_screenshot_in_section(
                body_with_screenshots, image_url, figure, item.get("source_url"), used_screenshot_sections
            )
        body_with_screenshots = (
            '<div class="dt-article-body" style="font-family:Arial,Helvetica,sans-serif;'
            'font-size:16px;line-height:1.75;color:#202124;max-width:860px;margin:0 auto;">\n'
            + body_with_screenshots + '\n</div>'
        )
        body_with_screenshots = re.sub(
            r'<h2(?![^>]*\bstyle=)([^>]*)>',
            r'<h2\1 style="font-family:Arial,Helvetica,sans-serif;font-size:25px;line-height:1.3;font-weight:700;margin:34px 0 12px;color:inherit;">',
            body_with_screenshots, flags=re.I
        )
        body_with_screenshots = re.sub(
            r'<h3(?![^>]*\bstyle=)([^>]*)>',
            r'<h3\1 style="font-family:Arial,Helvetica,sans-serif;font-size:19px;line-height:1.4;font-weight:700;margin:24px 0 9px;color:inherit;">',
            body_with_screenshots, flags=re.I
        )
        blocks.append(body_with_screenshots)
        return "\n\n".join(blocks)

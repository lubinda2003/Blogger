"""SEO metadata validation, label normalization, and Schema.org structured data generation."""

import html
import json
import re
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
    ) -> str:
        """Generate valid Schema.org Article JSON-LD for rich snippets."""
        schema_dict: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": title,
            "description": description,
            # A real person only if one is configured; never an invented "team" persona.
            "author": (
                {"@type": "Person", "name": author_name}
                if author_name
                else {"@type": "Organization", "name": "The Digital Toolkit"}
            ),
            "publisher": {
                "@type": "Organization",
                "name": "The Digital Toolkit",
            },
            "inLanguage": "en-US",
        }
        if url:
            schema_dict["mainEntityOfPage"] = url
        if date_published:
            schema_dict["datePublished"] = date_published

        json_str = json.dumps(schema_dict, indent=2, ensure_ascii=False)
        return f'<script type="application/ld+json">\n{json_str}\n</script>'

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
    ) -> str:
        """Inject structured data and optional public screenshot image markup into article HTML.

        SECURITY & INTEGRITY RULE: Never inject local runner paths (e.g. output/..., /app/...).
        Only inject images when a verified public HTTPS URL is provided.
        """
        blocks: List[str] = []

        if include_schema:
            schema = SEOMetadata.generate_schema_jsonld(title=title, description=meta_description)
            blocks.append(schema)

        # Cover image: same strict public-HTTPS rule as screenshots. Explicit width/height avoid layout shift.
        if featured_image_url and featured_image_url.startswith("https://") and not any(
            sub in featured_image_url for sub in ("localhost", "127.0.0.1", "output/")
        ):
            blocks.append(
                f'<figure class="article-cover" style="margin:0 0 24px 0;">\n'
                f'  <img src="{html.escape(featured_image_url)}" alt="{html.escape(featured_image_alt or title)}" '
                f'width="1200" height="630" loading="eager" style="width:100%; max-width:100%; height:auto; border-radius:8px;" />\n'
                f'</figure>'
            )

        # Multiple verified screenshots support product comparisons; retain legacy single-image compatibility.
        screenshot_items = public_screenshot_items or (
            [{"url": public_screenshot_url, "caption": screenshot_caption or "", "alt": screenshot_alt or title}]
            if public_screenshot_url else []
        )
        for item in screenshot_items:
            image_url = item.get("url", "")
            if not image_url.startswith("https://") or any(
                sub in image_url for sub in ("localhost", "127.0.0.1", "output/")
            ):
                continue
            clean_alt = html.escape(item.get("alt", title))
            clean_caption = html.escape(item.get("caption", ""))
            blocks.append(
                f'<figure class="article-screenshot" style="margin:24px 0; text-align:center;">\\n'
                f'  <img src="{html.escape(image_url)}" alt="{clean_alt}" loading="lazy" style="max-width:100%; height:auto; border-radius:6px; border:1px solid #e2e8f0;" />\\n'
                f'  <figcaption style="font-size:13px; color:#64748b; margin-top:8px;">{clean_caption}</figcaption>\\n'
                f'</figure>'
            )

        blocks.append(html_body)
        return "\n\n".join(blocks)

"""SEO metadata validation, label normalization, and Schema.org structured data generation."""

import html
import json
import re
from typing import Any, Dict, List, Optional


class SEOMetadata:
    """Manages SEO tags, meta descriptions, labels, and structured schema."""

    @staticmethod
    def normalize_labels(labels: List[str]) -> List[str]:
        """Clean and normalize Blogger labels (tags).

        Enforces title-cased labels, strips invalid characters, deduplicates, and limits to 6 tags.
        """
        cleaned = []
        seen = set()
        for label in labels:
            if not label:
                continue
            norm = re.sub(r"[#@!$%^&*()+=<>]", "", label).strip()
            if len(norm) >= 2:
                norm_title = norm.title()
                if norm_title.lower() not in seen:
                    seen.add(norm_title.lower())
                    cleaned.append(norm_title)
        return cleaned[:6]

    @staticmethod
    def generate_schema_jsonld(
        title: str,
        description: str,
        url: Optional[str] = None,
        date_published: Optional[str] = None,
        author_name: str = "Editorial Team",
    ) -> str:
        """Generate valid Schema.org Article JSON-LD for rich snippets."""
        schema_dict: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": title,
            "description": description,
            "author": {
                "@type": "Person",
                "name": author_name,
            },
            "publisher": {
                "@type": "Organization",
                "name": "Blogger Content Automation Engine",
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
    ) -> str:
        """Inject structured data and optional public screenshot image markup into article HTML.

        SECURITY & INTEGRITY RULE: Never inject local runner paths (e.g. output/..., /app/...).
        Only inject images when a verified public HTTPS URL is provided.
        """
        blocks: List[str] = []

        if include_schema:
            schema = SEOMetadata.generate_schema_jsonld(title=title, description=meta_description)
            blocks.append(schema)

        # STRICT CHECK: Only embed image if it is a valid public HTTPS URL
        if public_screenshot_url and public_screenshot_url.startswith("https://"):
            # Double check it is not a runner-local path pretending to be https
            if not any(sub in public_screenshot_url for sub in ("localhost", "127.0.0.1", "output/")):
                clean_alt = html.escape(screenshot_alt or title)
                clean_caption = html.escape(screenshot_caption or "")
                img_block = (
                    f'<figure class="article-screenshot" style="margin:24px 0; text-align:center;">\n'
                    f'  <img src="{html.escape(public_screenshot_url)}" alt="{clean_alt}" style="max-width:100%; height:auto; border-radius:6px; border:1px solid #e2e8f0;" />\n'
                    f'  <figcaption style="font-size:13px; color:#64748b; margin-top:8px;">{clean_caption}</figcaption>\n'
                    f'</figure>'
                )
                blocks.append(img_block)

        blocks.append(html_body)
        return "\n\n".join(blocks)

"""Pixabay stock-photo retrieval with 24-hour response caching and local asset hosting.

Only a small number of targeted searches are made per article. Pixabay results are
downloaded before permanent use; API result URLs are never embedded in published posts.
"""
import hashlib
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
PIXABAY_API = "https://pixabay.com/api/"
CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
IMAGE_GENERIC_TERMS = {
    "best", "build", "choose", "create", "creating", "digital", "easy", "guide",
    "help", "how", "idea", "ideas", "make", "making", "online", "platform",
    "phase", "product", "products", "sell", "selling",
    "step", "steps", "tool", "tools", "use", "using", "way", "ways", "work",
}

STOPWORDS = {
    "about", "after", "also", "and", "are", "before", "best", "build", "choosing",
    "create", "creating", "easy", "everyday", "first", "from", "guide", "help",
    "how", "into", "make", "more", "online", "simple", "step", "steps", "that",
    "the", "their", "this", "through", "tips", "using", "what", "when", "with",
    "your", "you", "why", "ways", "work",
}


def _words(value: str, limit: int = 7) -> list[str]:
    words = re.findall(r"[a-z0-9]{3,}", (value or "").lower())
    return list(dict.fromkeys(w for w in words if w not in STOPWORDS))[:limit]


def _specific_terms(value: str) -> set[str]:
    """Keep concrete subject words; broad editorial terms are not image evidence."""
    return set(_words(value, 12)) - IMAGE_GENERIC_TERMS


def build_search_query(title: str, section_heading: str = "") -> str:
    """Build a short, subject-led stock-photo query."""
    terms = _words(section_heading, 4) + _words(title, 4)
    return " ".join(dict.fromkeys(terms))[:100].strip()


class PixabayClient:
    def __init__(self, api_key: Optional[str] = None, cache_dir: str = "output/.cache/pixabay"):
        self.api_key = (api_key if api_key is not None else os.getenv("PIXABAY_API_KEY", "")).strip()
        self.cache_dir = Path(cache_dir)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _cache_path(self, query: str) -> Path:
        digest = hashlib.sha256(query.lower().encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def search_photos(self, query: str, per_page: int = 30) -> list[dict]:
        """Search only landscape photos; honor Pixabay's 24-hour API response cache rule."""
        if not self.api_key or not query.strip():
            return []
        query = query.strip()[:100]
        cache_path = self._cache_path(query)
        try:
            if cache_path.is_file() and time.time() - cache_path.stat().st_mtime < CACHE_TTL_SECONDS:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                return cached.get("hits", []) if isinstance(cached, dict) else []
        except Exception as exc:
            logger.warning("Pixabay cache could not be read: %s", exc)

        params = urllib.parse.urlencode({
            "key": self.api_key, "q": query, "image_type": "photo",
            "orientation": "horizontal", "safesearch": "true",
            "per_page": max(3, min(int(per_page), 50)), "lang": "en",
        })
        request = urllib.request.Request(
            PIXABAY_API + "?" + params,
            headers={"User-Agent": "TheDigitalToolkit/1.0 (editorial media retrieval)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
                raise ValueError("Pixabay returned an unexpected response.")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            return payload["hits"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Pixabay photo search returned HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise RuntimeError(f"Pixabay photo search failed: {exc}") from exc

    @staticmethod
    def choose_photo(
        hits: list[dict],
        used_ids: Optional[set[int]] = None,
        required_terms: Optional[set[str]] = None,
    ) -> Optional[dict]:
        """Choose a large landscape photo only when its Pixabay tags match the subject."""
        used_ids = used_ids or set()
        candidates = []
        for hit in hits:
            try:
                photo_id = int(hit.get("id", 0))
                width, height = int(hit.get("imageWidth", 0)), int(hit.get("imageHeight", 0))
                url = hit.get("largeImageURL") or hit.get("webformatURL")
                if photo_id in used_ids or not url or width < 1000 or height < 500:
                    continue
                ratio = width / max(height, 1)
                if not 1.25 <= ratio <= 2.4:
                    continue
                relevance = 0
                if required_terms:
                    searchable = " ".join((str(hit.get("tags") or ""), str(hit.get("pageURL") or ""))).lower()
                    searchable_terms = set(re.findall(r"[a-z0-9]+", searchable))
                    relevance = len(required_terms.intersection(searchable_terms))
                    # A single broad tag is not enough to justify embedding a photo.
                    # Require at least two distinct subject matches to reduce false positives.
                    if relevance < 2:
                        continue
                hit["_editorial_relevance"] = relevance
                candidates.append(hit)
            except (TypeError, ValueError):
                continue
        if not candidates:
            return None
        return max(candidates, key=lambda item: (
            int(item.get("_editorial_relevance", 0) or 0),
            int(item.get("downloads", 0) or 0),
            int(item.get("likes", 0) or 0),
            int(item.get("imageWidth", 0) or 0),
        ))

    def download_photo(self, hit: dict, output_path: Path) -> Path:
        """Download and validate a Pixabay image; never publish the provider's temporary URL."""
        url = hit.get("largeImageURL") or hit.get("webformatURL")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("Pixabay did not provide a secure image URL.")
        request = urllib.request.Request(url, headers={"User-Agent": "TheDigitalToolkit/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
            content_type = (response.headers.get("Content-Type") or "").lower()
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Selected stock photo exceeds the 12 MB download limit.")
        # Some image CDNs label valid image bytes as application/octet-stream.
        # Trust the file signature, not the response header; still reject HTML/error pages.
        valid = None
        if data.startswith(b"\xff\xd8\xff"):
            valid = ".jpg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            valid = ".png"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            valid = ".webp"
        if not valid:
            raise ValueError(
                "Pixabay download was not a supported, valid JPEG, PNG or WebP image "
                f"(response content type: {content_type or 'missing'})."
            )
        target = Path(output_path).with_suffix(valid)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target


def choose_cover_photo(title: str, brief: Optional[dict], output_dir: str = "output", client: Optional[PixabayClient] = None) -> Optional[dict]:
    """Fetch one cover photo. Fail softly when the API is not configured or returns no fit."""
    client = client or PixabayClient(cache_dir=str(Path(output_dir) / ".cache" / "pixabay"))
    if not client.available:
        return None
    description = (brief or {}).get("description", "")
    query = build_search_query(title, description)
    if not query:
        query = title[:100]
    try:
        required_terms = _specific_terms(title)
        # If the title contains no concrete visual subject, prefer the custom editorial
        # illustration fallback over an unrelated stock photograph.
        if len(required_terms) < 2:
            return None
        hit = client.choose_photo(client.search_photos(query), required_terms=required_terms)
        if not hit:
            return None
        path = client.download_photo(hit, Path(output_dir) / "stock" / f"cover-{hashlib.sha256(title.encode()).hexdigest()[:12]}")
        return {
            "path": path, "source_url": hit.get("pageURL", ""),
            "photographer": hit.get("user", "Pixabay contributor"),
            "photo_id": hit.get("id"), "query": query,
        }
    except Exception as exc:
        logger.warning("Stock cover photo unavailable; local cover fallback will be used: %s", exc)
        return None


def select_article_photos(
    title: str,
    article_html: str,
    output_dir: str = "output",
    max_items: int = 2,
    client: Optional[PixabayClient] = None,
) -> list[dict]:
    """Find up to two distinct, section-relevant photos for in-article placement."""
    client = client or PixabayClient(cache_dir=str(Path(output_dir) / ".cache" / "pixabay"))
    if not client.available or max_items <= 0:
        return []
    headings = re.findall(r"<h[23]\b[^>]*>(.*?)</h[23]>", article_html or "", re.I | re.S)
    candidates = []
    for raw in headings:
        heading = re.sub(r"<[^>]+>", " ", raw)
        heading = html.unescape(re.sub(r"\s+", " ", heading)).strip()
        if not heading or re.search(r"faq|frequently asked|conclusion|sources|references|next steps", heading, re.I):
            continue
        # Generic headings ("Introduction", "Choose a Platform", "Next Steps")
        # do not provide enough visual context for a reliable stock-photo match.
        if len(_specific_terms(heading)) < 2:
            continue
        candidates.append(heading)
    # Choose headings spread through the article rather than adjacent sections.
    if len(candidates) > max_items:
        if max_items == 1:
            indexes = [len(candidates) // 2]
        else:
            indexes = [round(i * (len(candidates) - 1) / (max_items - 1)) for i in range(max_items)]
        candidates = [candidates[i] for i in indexes]
    used_ids: set[int] = set()
    selected = []
    for index, heading in enumerate(candidates[:max_items], start=1):
        query = build_search_query(title, heading)
        if not query:
            continue
        try:
            required_terms = _specific_terms(heading)
            if len(required_terms) < 2:
                continue
            hit = client.choose_photo(
                client.search_photos(query), used_ids, required_terms=required_terms
            )
            if not hit:
                continue
            photo_id = int(hit.get("id", 0))
            path = client.download_photo(
                hit, Path(output_dir) / "stock" / f"section-{index}-{photo_id}"
            )
            used_ids.add(photo_id)
            photographer = str(hit.get("user") or "Pixabay contributor")
            page_url = str(hit.get("pageURL") or "https://pixabay.com/")
            selected.append({
                "path": path, "section_heading": heading,
                "alt_text": f"Photograph illustrating {heading}",
                "caption": f'Photo by {html.escape(photographer)} on <a href="{html.escape(page_url, quote=True)}" rel="nofollow noopener">Pixabay</a>',
                "source_url": page_url, "photographer": photographer,
                "photo_id": photo_id, "query": query,
            })
        except Exception as exc:
            logger.warning("Stock photo for section '%s' was skipped: %s", heading, exc)
    return selected


def inject_stock_photos(article_html: str, photo_items: list[dict]) -> str:
    """Insert hosted photos after the first explanatory paragraph under their matching heading."""
    updated = article_html or ""
    for item in photo_items or []:
        url = item.get("url")
        heading = str(item.get("section_heading") or "").strip()
        alt = html.escape(str(item.get("alt_text") or ""))
        if not isinstance(url, str) or not url.startswith("https://") or not heading:
            continue
        pattern = re.compile(
            r"(<h[23]\b[^>]*>)(.*?)(</h[23]>)(.*?)(?=<h[23]\b|$)",
            re.I | re.S,
        )
        inserted = False
        for match in pattern.finditer(updated):
            plain_heading = html.unescape(re.sub(r"<[^>]+>", " ", match.group(2)))
            if re.sub(r"\s+", " ", plain_heading).strip().casefold() != heading.casefold():
                continue
            section = match.group(4)
            paragraph = re.search(r"</p\s*>", section, re.I)
            if not paragraph:
                break
            figure = (
                '<figure class="dt-stock-photo" style="margin:24px 0;text-align:center">'
                f'<img src="{html.escape(url, quote=True)}" alt="{alt}" loading="lazy" '
                'style="display:block;width:100%;height:auto;max-width:100%;border-radius:8px"/>'
                '</figure>'
            )
            insert_at = match.start(4) + paragraph.end()
            updated = updated[:insert_at] + figure + updated[insert_at:]
            inserted = True
            break
        if not inserted:
            logger.info("No exact article heading found for stock photo placement: %s", heading)
    return updated

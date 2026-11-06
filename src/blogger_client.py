"""Blogger API v3 client with OAuth2 refresh token exchange and safe draft creation."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USER_AGENT = "DigitalToolkitContentEngine/1.0"


@dataclass
class BloggerPostResult:
    """Represents the response from a Blogger API operation."""
    success: bool
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    title: Optional[str] = None
    is_draft: bool = True
    error_message: Optional[str] = None
    reconciled_existing: bool = False
    raw_payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "title": self.title,
            "is_draft": self.is_draft,
            "error_message": self.error_message,
            "reconciled_existing": self.reconciled_existing,
        }


class BloggerClient:
    """Interacts with Google Blogger API v3 using OAuth2 refresh tokens."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    BASE_URL = "https://www.googleapis.com/blogger/v3"

    def __init__(
        self,
        blog_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        timeout: int = 30,
    ):
        self.blog_id = blog_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.timeout = timeout
        self._access_token: Optional[str] = None

    def _redact_token(self, token: Optional[str]) -> str:
        """Mask token for secure logs."""
        if not token:
            return "[EMPTY]"
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}...{token[-4:]}"

    def refresh_access_token(self) -> str:
        """Exchange the refresh token for a short-lived OAuth2 access token."""
        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise ValueError(
                "Missing OAuth credentials. BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, "
                "and BLOGGER_REFRESH_TOKEN are required."
            )

        logger.info(f"Refreshing OAuth2 access token for client ID {self._redact_token(self.client_id)}...")

        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")

        req = urllib.request.Request(
            self.TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                access_token = body.get("access_token")
                if not access_token:
                    raise RuntimeError("OAuth token endpoint response did not contain 'access_token'.")
                self._access_token = access_token
                logger.info("Successfully refreshed short-lived Blogger access token.")
                return access_token
        except urllib.error.HTTPError as e:
            # Mask sensitive request details
            logger.error(f"OAuth token refresh failed with HTTP {e.code}")
            raise RuntimeError(f"OAuth token refresh failed (HTTP {e.code}). Verify refresh token in GitHub Secrets.") from e
        except Exception as e:
            logger.error("OAuth token exchange network failure.")
            raise RuntimeError(f"OAuth token network failure: {e}") from e

    def build_post_payload(self, title: str, html_content: str, labels: List[str], topic_id: Optional[str] = None) -> Dict[str, Any]:
        """Construct the official Blogger API v3 post resource with hidden topic_id marker and label."""
        final_html = html_content
        final_labels = list(labels or ["AI Tools", "Digital Skills"])

        if topic_id:
            marker = f"<!-- topic_id: {topic_id} -->"
            if marker not in final_html:
                final_html = final_html.rstrip() + f"\n\n{marker}"
            # NOTE: no public "TopicID:" label. Blogger shows labels to readers once published;
            # the hidden HTML comment above is the reconciliation marker.

        return {
            "kind": "blogger#post",
            "title": title,
            "content": final_html,
            "labels": final_labels,
        }

    def reconcile_existing_post(self, title: str, topic_id: Optional[str] = None) -> Optional[BloggerPostResult]:
        """Query Blogger API for an existing post by title or hidden topic_id marker/label to prevent duplicate insertion.

        FAIL-CLOSED SAFETY: If the lookup fails due to network, auth, or API error, do NOT swallow
        the error! Raise it so the pipeline stops safely rather than risking duplicate insertion.
        """
        if not self.blog_id:
            raise ValueError("BLOGGER_BLOG_ID is required for post reconciliation.")

        if not self._access_token:
            self.refresh_access_token()

        # 1. Search by title query
        if title:
            try:
                encoded_query = urllib.parse.quote(title)
                url = f"{self.BASE_URL}/blogs/{self.blog_id}/posts/search?q={encoded_query}"
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "User-Agent": USER_AGENT,
                    },
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("items", [])
                    for item in items:
                        if item.get("title", "").strip().lower() == title.strip().lower():
                            logger.info(f"Reconciliation matched existing post ID {item.get('id')} by title: '{title}'")
                            return BloggerPostResult(
                                success=True,
                                post_id=item.get("id"),
                                post_url=item.get("url"),
                                title=item.get("title"),
                                is_draft=item.get("status") == "DRAFT",
                                reconciled_existing=True,
                            )
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise RuntimeError(f"Blogger blog ID '{self.blog_id}' not found (HTTP 404). Check BLOGGER_BLOG_ID.") from e
                raise RuntimeError(f"Blogger search/reconciliation failed (HTTP {e.code}). Stopping safely to prevent duplicates.") from e
            except Exception as e:
                raise RuntimeError(f"Blogger reconciliation check failed ({e}). Stopping to prevent duplicates.") from e

        # 2. List recent posts and check topic_id marker or label
        if topic_id:
            try:
                list_url = f"{self.BASE_URL}/blogs/{self.blog_id}/posts?fetchBodies=true&maxResults=50&status=draft&status=live&status=scheduled"
                req = urllib.request.Request(
                    list_url,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "User-Agent": USER_AGENT,
                    },
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("items", [])
                    marker = f"topic_id: {topic_id} -->"  # exact: "foo" must not match "foo-bar"
                    label_tag = f"TopicID:{topic_id}"
                    for item in items:
                        content = item.get("content", "")
                        item_labels = item.get("labels", [])
                        if marker in content or label_tag in item_labels:
                            logger.info(f"Reconciliation matched existing post ID {item.get('id')} by topic_id marker/label '{topic_id}'")
                            return BloggerPostResult(
                                success=True,
                                post_id=item.get("id"),
                                post_url=item.get("url"),
                                title=item.get("title"),
                                is_draft=item.get("status") == "DRAFT",
                                reconciled_existing=True,
                            )
            except Exception as e:
                raise RuntimeError(f"Blogger post list reconciliation failed ({e}). Stopping to prevent duplicates.") from e

        return None

    def insert_post(
        self,
        title: str,
        html_content: str,
        labels: List[str],
        is_draft: bool = True,
        dry_run: bool = False,
        topic_id: Optional[str] = None,
    ) -> BloggerPostResult:
        """Create a post on the Blogger blog. Default isDraft=True."""
        payload = self.build_post_payload(title=title, html_content=html_content, labels=labels, topic_id=topic_id)

        if dry_run:
            logger.info(f"[DRY RUN] Simulating Blogger draft insertion for: '{title}' (Labels: {payload['labels']})")
            dummy_id = "dryrun-" + str(abs(hash(title)))[:10]
            dummy_url = f"https://example.blogger.com/b/preview/{dummy_id}"
            return BloggerPostResult(
                success=True,
                post_id=dummy_id,
                post_url=dummy_url,
                title=title,
                is_draft=is_draft,
                raw_payload=payload,
            )

        if not self.blog_id:
            return BloggerPostResult(
                success=False,
                error_message="BLOGGER_BLOG_ID is not configured.",
                raw_payload=payload,
            )

        # Check reconciliation first to prevent duplicates on workflow retry.
        existing = self.reconcile_existing_post(title, topic_id=topic_id)
        if existing:
            logger.warning(f"Post with title '{title}' or topic_id '{topic_id}' already exists on Blogger (ID: {existing.post_id}). Skipping insertion.")
            return existing

        # Ensure active access token
        if not self._access_token:
            self.refresh_access_token()

        draft_param = "true" if is_draft else "false"
        url = f"{self.BASE_URL}/blogs/{self.blog_id}/posts?isDraft={draft_param}"

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._access_token}",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        try:
            logger.info(f"Submitting post to Blogger API (Blog ID: {self.blog_id}, isDraft={draft_param})...")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                post_id = resp_data.get("id")
                post_url = resp_data.get("url")
                logger.info(f"Blogger post successfully created! ID: {post_id}, URL: {post_url}")
                return BloggerPostResult(
                    success=True,
                    post_id=post_id,
                    post_url=post_url,
                    title=resp_data.get("title", title),
                    is_draft=is_draft,
                    raw_payload=resp_data,
                )
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            safe_err = f"Blogger API HTTP {e.code}: {err_msg[:250]}"
            logger.error(safe_err)
            return BloggerPostResult(
                success=False,
                error_message=safe_err,
                raw_payload=payload,
            )
        except Exception as e:
            logger.error(f"Blogger API network failure: {e}")
            return BloggerPostResult(
                success=False,
                error_message=f"Blogger network error: {e}",
                raw_payload=payload,
            )

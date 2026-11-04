"""Cloudflare Worker bridge for persistent D1 storage and topic/run coordination."""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def check_d1_database_id_configured(database_id: Optional[str]) -> Tuple[bool, str]:
    """Check if a Cloudflare D1 database ID is configured with a real UUID rather than a placeholder.

    Returns (is_valid, message).
    """
    if not database_id or not database_id.strip():
        return False, "D1 database_id is empty or missing."
    val = database_id.strip().strip('"').strip("'")
    if val.startswith("<") and val.endswith(">"):
        return False, f"D1 database_id is still a placeholder: '{val}'"
    if "placeholder" in val.lower() or "your_d1" in val.lower():
        return False, f"D1 database_id appears to be a placeholder: '{val}'"
    # Basic UUID pattern check (36 chars: 8-4-4-4-12 hex)
    uuid_pattern = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    if uuid_pattern.match(val):
        return True, "Valid D1 UUID configured."
    return True, f"Configured D1 ID: '{val}'"


def inspect_wrangler_d1_config(wrangler_path: str = "worker/wrangler.toml") -> Tuple[bool, str]:
    """Inspect worker/wrangler.toml to verify whether D1 binding has a valid ID or a placeholder."""
    path = Path(wrangler_path)
    if not path.exists():
        return False, f"Wrangler file not found at {wrangler_path}"
    try:
        content = path.read_text(encoding="utf-8")
        match = re.search(r'database_id\s*=\s*["\']([^"\']+)["\']', content)
        if not match:
            return False, "No database_id found in wrangler.toml under [[d1_databases]]."
        raw_id = match.group(1).strip()
        return check_d1_database_id_configured(raw_id)
    except Exception as e:
        return False, f"Failed to inspect wrangler.toml: {e}"


def sanitize_response_body(body: str, max_length: int = 300) -> str:
    """Sanitize and summarize an HTTP response body, redacting secrets and parsing HTML titles."""
    if not body or not body.strip():
        return "(empty response body)"

    # Redact sensitive credentials, authorization bearer tokens, cookies, or secrets
    sanitized = re.sub(
        r"(Bearer\s+)[A-Za-z0-9_\-\.~+/=]+", r"\1[REDACTED]", body, flags=re.IGNORECASE
    )
    sanitized = re.sub(
        r"(client_secret|api_key|token|secret|password|authorization)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.~+/=]+",
        r"\1: [REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )

    # If HTML error page from Cloudflare Edge / WAF
    lower = sanitized.lower()
    if "<html" in lower or "<!doctype" in lower:
        title_match = re.search(r"<title>(.*?)</title>", sanitized, re.IGNORECASE | re.DOTALL)
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", sanitized, re.IGNORECASE | re.DOTALL)
        title = " ".join(title_match.group(1).split()) if title_match else "No Title"
        h1 = " ".join(h1_match.group(1).split()) if h1_match else None

        signatures = []
        if "1020" in sanitized:
            signatures.append("Cloudflare Error 1020 (Access Denied / WAF Rule)")
        if "1010" in sanitized:
            signatures.append("Cloudflare Error 1010 (Browser Integrity Check / Python-urllib blocked)")
        if "1015" in sanitized:
            signatures.append("Cloudflare Error 1015 (Rate Limited)")
        if "just a moment" in lower or "cf-mitigated" in lower or "challenge-platform" in lower:
            signatures.append("Cloudflare Interactive Challenge / Bot Fight Mode")
        if "cloudflare access" in lower or "cdn-cgi/access" in lower:
            signatures.append("Cloudflare Access / Zero Trust application login required")

        summary = f"HTML page received. Title: '{title}'"
        if h1:
            summary += f", Heading: '{h1}'"
        if signatures:
            summary += f". Detected signature: {'; '.join(signatures)}"
        return summary

    single_line = " ".join(sanitized.split())
    if len(single_line) > max_length:
        return single_line[:max_length] + "..."
    return single_line


def format_http_error_report(
    req: urllib.request.Request,
    e: urllib.error.HTTPError,
    auth_token: Optional[str] = None,
    prefix_message: str = "",
) -> str:
    """Produce a safe, non-sensitive diagnostic error report distinguishing Worker from Cloudflare Edge."""
    headers = e.headers or {}
    cf_ray = headers.get("cf-ray") or headers.get("CF-RAY")
    server = headers.get("server") or headers.get("Server") or "Unknown"
    worker_marker = headers.get("x-worker-served-by") or headers.get("X-Worker-Served-By")
    endpoint = req.full_url
    method = req.get_method()
    code = e.code

    err_body = e.read().decode("utf-8", errors="ignore")
    body_summary = sanitize_response_body(err_body)
    token_status = f"present (length: {len(auth_token)})" if auth_token else "MISSING / UNSET"

    base_msg = f"{prefix_message}: {body_summary}" if prefix_message else f"HTTP {code}: {body_summary}"

    diagnostic_lines = [
        base_msg,
        f"[HTTP {code} SAFE Auth Diagnostic Report]",
        f"  - Request: {method} {endpoint}",
        f"  - Client Bearer Token: {token_status}",
    ]

    if worker_marker:
        diagnostic_lines.append(f"  - Response Origin: Worker Application (X-Worker-Served-By: '{worker_marker}')")
    else:
        diagnostic_lines.append(f"  - Response Origin: Cloudflare Edge / Security Layer (Server: '{server}', CF-Ray: '{cf_ray or 'N/A'}')")
        diagnostic_lines.append(f"  - Rejection Note: 'X-Worker-Served-By' header is absent. Request was intercepted by Cloudflare Edge BEFORE reaching worker/index.ts.")

    if code == 403:
        if not worker_marker:
            diagnostic_lines.append(
                "  - Likely Causes:\n"
                "    1. Cloudflare Browser Integrity Check (BIC) or Bot Fight Mode blocking requests from GitHub Actions / Python.\n"
                "    2. Cloudflare WAF Custom Rule / Security Level blocking traffic to this endpoint.\n"
                "    3. Cloudflare Access (Zero Trust) application configured on the domain requiring Service Tokens (CF-Access-Client-Id / CF-Access-Client-Secret).\n"
                f"    -> Look up CF-Ray '{cf_ray or 'N/A'}' in Cloudflare Dashboard under Security > Events for the exact trigger."
            )
        else:
            diagnostic_lines.append("  - Root Cause: Worker application returned HTTP 403.")
    elif code == 401:
        if worker_marker:
            diagnostic_lines.append(
                "  - Likely Cause: Worker Bearer authentication failed. Ensure CLOUDFLARE_WORKER_SECRET in GitHub Secrets matches WORKER_API_SECRET in Cloudflare Worker Variables."
            )
        else:
            diagnostic_lines.append(
                f"  - Likely Cause: Cloudflare Edge authentication failed (CF-Ray: {cf_ray or 'N/A'})."
            )

    return "\n".join(diagnostic_lines)


class CloudflareWorkerClient:
    """Client for communicating with The Digital Toolkit supporting Cloudflare Worker."""

    def __init__(
        self,
        worker_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        cf_access_client_id: Optional[str] = None,
        cf_access_client_secret: Optional[str] = None,
        timeout: int = 15,
    ):
        self.worker_url = (worker_url or "").strip().strip('"').strip("'").rstrip("/")
        self.auth_token = auth_token.strip().strip('"').strip("'") if auth_token else None
        self.cf_access_client_id = (
            cf_access_client_id.strip().strip('"').strip("'") if cf_access_client_id else None
        )
        self.cf_access_client_secret = (
            cf_access_client_secret.strip().strip('"').strip("'") if cf_access_client_secret else None
        )
        self.timeout = timeout
        self.last_error: Optional[str] = None

        if self.worker_url and not self.auth_token:
            logger.warning(
                "[AUTH CONFIG WARNING] CLOUDFLARE_WORKER_URL is configured, but auth token is unset or empty. "
                "Requests will be sent without an Authorization Bearer header and will receive HTTP 401 from the Worker. "
                "Configure CLOUDFLARE_WORKER_SECRET in GitHub Secrets to match WORKER_API_SECRET on the Worker."
            )

    @property
    def is_configured(self) -> bool:
        return bool(self.worker_url)

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DigitalToolkitContentEngine/1.0 (+https://digitaltoolkitguide.blogspot.com/; GitHubActions/1.0)",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.cf_access_client_id and self.cf_access_client_secret:
            headers["CF-Access-Client-Id"] = self.cf_access_client_id
            headers["CF-Access-Client-Secret"] = self.cf_access_client_secret
        return headers

    def get_processed_topics(self, raise_on_error: bool = False) -> List[Dict[str, Any]]:
        """Fetch processed topics from Cloudflare D1 via Worker.

        Returns list of processed topic records. Fails loudly on API/database errors.
        """
        self.last_error = None
        if not self.is_configured:
            return []

        url = f"{self.worker_url}/api/topics/processed"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("success", False) and "error" in data:
                    err_msg = f"Cloudflare Worker error ({resp.status}): {data.get('error')}"
                    self.last_error = err_msg
                    logger.error(err_msg)
                    if raise_on_error:
                        raise RuntimeError(err_msg)
                    return []
                return data.get("processed", [])
        except urllib.error.HTTPError as e:
            err_msg = format_http_error_report(
                req=req,
                e=e,
                auth_token=self.auth_token,
                prefix_message=f"Cloudflare Worker returned HTTP {e.code} for processed topics",
            )
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise RuntimeError(err_msg) from e
            return []
        except Exception as e:
            err_msg = f"Cloudflare Worker connection failed: {e}"
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise RuntimeError(err_msg) from e
            return []

    def record_topic(
        self,
        topic_id: str,
        topic_title: str,
        fingerprint: Optional[str] = None,
        category: str = "General",
        post_id: Optional[str] = None,
        post_url: Optional[str] = None,
        publish_mode: str = "draft",
        raise_on_error: bool = False,
    ) -> bool:
        """Persist a single completed topic directly into Cloudflare D1."""
        self.last_error = None
        if not self.is_configured:
            self.last_error = "Cloudflare client not configured (WORKER_URL is empty)"
            return False

        url = f"{self.worker_url}/api/topics/record"
        payload = {
            "topic_id": topic_id,
            "topic_title": topic_title,
            "fingerprint": fingerprint or f"id:{topic_id}",
            "category": category,
            "post_id": post_id,
            "post_url": post_url,
            "publish_mode": publish_mode,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if resp.status in (200, 201) and data.get("success", False):
                    logger.info(f"Successfully recorded topic '{topic_id}' in Cloudflare D1.")
                    return True
                err_msg = data.get("error", f"Cloudflare Worker returned HTTP {resp.status}")
                self.last_error = err_msg
                logger.error(f"Failed to record topic in D1: {err_msg}")
                if raise_on_error:
                    raise RuntimeError(f"Failed to record topic in D1: {err_msg}")
                return False
        except urllib.error.HTTPError as e:
            err_msg = format_http_error_report(
                req=req,
                e=e,
                auth_token=self.auth_token,
                prefix_message=f"Failed to record topic in D1 (HTTP {e.code})",
            )
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise RuntimeError(err_msg) from e
            return False
        except Exception as e:
            err_msg = f"Failed to record topic in D1: {e}"
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise RuntimeError(err_msg) from e
            return False

    def record_run(self, run_report: Dict[str, Any], raise_on_error: bool = False) -> bool:
        """Send run telemetry to Cloudflare Worker for persistent D1 recording.

        Aligns field names with Worker schema and fails clearly when request fails.
        """
        self.last_error = None
        if not self.is_configured:
            self.last_error = "Cloudflare client not configured (WORKER_URL is empty)"
            return False

        url = f"{self.worker_url}/api/runs/record"

        # Canonical field mapping matching worker/index.ts schema
        payload = {
            "run_id": run_report.get("run_id"),
            "overall_status": run_report.get("overall_status") or run_report.get("status", "UNKNOWN"),
            "selected_topic": run_report.get("selected_topic") or run_report.get("topic_title"),
            "selected_topic_id": run_report.get("selected_topic_id") or run_report.get("topic_id"),
            "total_duration_seconds": run_report.get("total_duration_seconds") or run_report.get("duration_seconds", 0),
            "dry_run": run_report.get("dry_run", False),
            "publish_mode": run_report.get("publish_mode") or ("draft" if run_report.get("is_draft", True) else "publish"),
            "category": run_report.get("category", "Artificial Intelligence and AI Tools"),
            "fingerprint": run_report.get("fingerprint"),
            "post_id": run_report.get("post_id"),
            "post_url": run_report.get("post_url"),
            "blogger": {
                "post_id": run_report.get("post_id"),
                "post_url": run_report.get("post_url"),
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if resp.status in (200, 201) and data.get("success", False):
                    logger.info("Successfully recorded execution telemetry with Cloudflare Worker & D1.")
                    return True
                err_msg = data.get("error", "Unknown worker recording failure")
                self.last_error = err_msg
                logger.error(f"Cloudflare Worker record_run returned unsuccessful: {err_msg}")
                if raise_on_error:
                    raise RuntimeError(f"Cloudflare Worker record_run failed: {err_msg}")
                return False
        except urllib.error.HTTPError as e:
            err_msg = format_http_error_report(
                req=req,
                e=e,
                auth_token=self.auth_token,
                prefix_message=f"Cloudflare Worker record_run failed (HTTP {e.code})",
            )
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise RuntimeError(err_msg) from e
            return False
        except Exception as e:
            err_msg = f"Cloudflare Worker record_run failed: {e}"
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise RuntimeError(err_msg) from e
            return False


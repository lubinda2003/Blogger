"""Configuration management with environment parsing, secret masking, and validation."""

import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AppConfig:
    """Runtime configuration for the content pipeline."""

    # Execution controls
    dry_run: bool = True
    publish_mode: str = "draft"  # "draft" or "publish"
    max_articles_per_run: int = 1
    local_only: bool = False  # Bypasses Cloudflare D1 deduplication requirement for local-only runs

    # File paths
    topics_csv_path: str = "data/topics.csv"
    processed_json_path: str = "data/processed_topics.json"
    output_dir: str = "output"
    settings_path: str = "config/settings.example.yaml"
    template_prompt_path: str = "templates/article_prompt.md"

    # API credentials (never logged or committed)
    gemini_api_key: Optional[str] = field(default=None, repr=False)
    blogger_blog_id: Optional[str] = None
    blogger_client_id: Optional[str] = field(default=None, repr=False)
    blogger_client_secret: Optional[str] = field(default=None, repr=False)
    blogger_refresh_token: Optional[str] = field(default=None, repr=False)

    # Gemini model parameters
    gemini_model: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.3
    gemini_max_tokens: int = 4096

    # Quality Gate thresholds
    min_word_count: int = 800
    max_word_count: int = 2500
    min_credible_sources: int = 2
    zambia_context_enabled: bool = False  # International audience default

    # Cloudflare Worker backend
    cloudflare_worker_url: Optional[str] = None
    cloudflare_worker_secret: Optional[str] = field(default=None, repr=False)

    # Playwright browser parameters
    screenshot_viewport_width: int = 1280
    screenshot_viewport_height: int = 800
    screenshot_timeout_ms: int = 30000

    def validate_for_mode(self, stage: str = "all") -> List[str]:
        """Validate configuration requirements without throwing raw exceptions.

        Returns a list of validation error descriptions.
        """
        errors: List[str] = []

        if self.publish_mode not in ("draft", "publish"):
            errors.append(f"Invalid PUBLISH_MODE: '{self.publish_mode}'. Must be 'draft' or 'publish'.")

        # In non-dry-run mode when writing with Gemini
        if not self.dry_run and stage in ("all", "write"):
            if not self.gemini_api_key or self.gemini_api_key.strip() == "":
                errors.append(
                    "GEMINI_API_KEY is required for live generation. "
                    "Configure GEMINI_API_KEY in environment variables or GitHub Secrets."
                )

        # In non-dry-run mode when publishing or creating draft on Blogger
        if not self.dry_run and stage in ("all", "publish"):
            if not self.blogger_blog_id:
                errors.append("BLOGGER_BLOG_ID is required for Blogger operations.")
            if not self.blogger_client_id:
                errors.append("BLOGGER_CLIENT_ID is required for Blogger OAuth operations.")
            if not self.blogger_client_secret:
                errors.append("BLOGGER_CLIENT_SECRET is required for Blogger OAuth operations.")
            if not self.blogger_refresh_token:
                errors.append("BLOGGER_REFRESH_TOKEN is required for Blogger OAuth operations.")

        # Safety check: Prevent accidental public posting without explicit affirmation
        if self.publish_mode == "publish" and os.getenv("CONFIRM_LIVE_PUBLISH") != "true":
            errors.append(
                "Safety guard: PUBLISH_MODE='publish' requires CONFIRM_LIVE_PUBLISH='true'. "
                "Defaulting to 'draft' is enforced to avoid accidental unreviewed posts."
            )

        return errors

    def safe_dict(self) -> Dict[str, Any]:
        """Return a dictionary of settings with secrets redacted for safe logging."""
        def mask(val: Optional[str]) -> str:
            if not val:
                return "Not Configured"
            if len(val) <= 6:
                return "***"
            return f"{val[:3]}...{val[-3:]}"

        return {
            "dry_run": self.dry_run,
            "publish_mode": self.publish_mode,
            "local_only": self.local_only,
            "max_articles_per_run": self.max_articles_per_run,
            "gemini_model": self.gemini_model,
            "gemini_api_key": mask(self.gemini_api_key),
            "blogger_blog_id": self.blogger_blog_id or "Not Configured",
            "blogger_client_id": mask(self.blogger_client_id),
            "blogger_client_secret": mask(self.blogger_client_secret),
            "blogger_refresh_token": mask(self.blogger_refresh_token),
            "topics_csv_path": self.topics_csv_path,
            "min_word_count": self.min_word_count,
            "min_credible_sources": self.min_credible_sources,
        }


def _str_to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


def load_config(overrides: Optional[Dict[str, Any]] = None) -> AppConfig:
    """Load configuration with priority: overrides > environment variables > config/config.json > code defaults."""
    # Read optional config/config.json base settings
    json_cfg: Dict[str, Any] = {}
    json_path = Path("config/config.json")
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    json_cfg = loaded
        except Exception:
            pass

    pipeline_cfg = json_cfg.get("pipeline", {})
    blogger_cfg = json_cfg.get("blogger", {})
    worker_cfg = json_cfg.get("cloudflare_worker", {})
    gemini_cfg = json_cfg.get("gemini", {})
    editorial_cfg = json_cfg.get("editorial", {})

    dry_run_env = os.getenv("DRY_RUN")
    if dry_run_env is not None:
        dry_run = _str_to_bool(dry_run_env, default=True)
    else:
        dry_run = pipeline_cfg.get("dry_run", True)

    publish_mode_env = os.getenv("PUBLISH_MODE")
    publish_mode = (publish_mode_env or pipeline_cfg.get("publish_mode", "draft")).strip().lower()

    max_articles_raw = os.getenv("MAX_ARTICLES_PER_RUN", str(pipeline_cfg.get("max_articles_per_run", 1)))
    try:
        max_articles = max(1, min(int(max_articles_raw), 5))
    except ValueError:
        max_articles = 1

    min_words = editorial_cfg.get("min_word_count", 800)
    max_words = editorial_cfg.get("max_word_count", 2500)
    min_sources = editorial_cfg.get("min_credible_sources", 2)

    zambia_env = os.getenv("ZAMBIA_CONTEXT_ENABLED")
    if zambia_env is not None:
        zambia_enabled = _str_to_bool(zambia_env, default=False)
    else:
        zambia_enabled = bool(pipeline_cfg.get("zambia_context_enabled", False))

    local_only_env = os.getenv("LOCAL_ONLY") or os.getenv("ALLOW_LOCAL_FALLBACK")
    if local_only_env is not None:
        local_only = _str_to_bool(local_only_env, default=False)
    else:
        local_only = bool(pipeline_cfg.get("local_only", False))

    config = AppConfig(
        dry_run=dry_run,
        publish_mode=publish_mode,
        max_articles_per_run=max_articles,
        local_only=local_only,
        topics_csv_path=os.getenv("TOPICS_CSV_PATH", "data/topics.csv"),
        processed_json_path=os.getenv("PROCESSED_JSON_PATH", "data/processed_topics.json"),
        output_dir=os.getenv("OUTPUT_DIR", "output"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        blogger_blog_id=os.getenv("BLOGGER_BLOG_ID") or blogger_cfg.get("blog_id") or None,
        blogger_client_id=os.getenv("BLOGGER_CLIENT_ID"),
        blogger_client_secret=os.getenv("BLOGGER_CLIENT_SECRET"),
        blogger_refresh_token=os.getenv("BLOGGER_REFRESH_TOKEN"),
        gemini_model=os.getenv("GEMINI_MODEL") or gemini_cfg.get("model", "gemini-2.5-flash"),
        zambia_context_enabled=zambia_enabled,
        cloudflare_worker_url=os.getenv("CLOUDFLARE_WORKER_URL") or worker_cfg.get("worker_url") or None,
        cloudflare_worker_secret=os.getenv("CLOUDFLARE_WORKER_SECRET") or worker_cfg.get("auth_token") or None,
        min_word_count=min_words,
        max_word_count=max_words,
        min_credible_sources=min_sources,
    )

    if overrides:
        for k, v in overrides.items():
            if hasattr(config, k) and v is not None:
                setattr(config, k, v)

    # Ensure output directory exists
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    Path(config.output_dir, "screenshots").mkdir(parents=True, exist_ok=True)

    return config


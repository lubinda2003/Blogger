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
    confirm_live_publish: bool = False
    max_articles_per_run: int = 1


    # File paths
    topics_csv_path: str = "data/topics.csv"
    processed_json_path: str = "data/processed_topics.json"
    output_dir: str = "output"
    settings_path: str = "config/settings.example.yaml"
    template_prompt_path: str = "templates/article_prompt.md"

    # API credentials (never logged or committed)
    # API credentials (never logged or committed)
    gemini_api_key: Optional[str] = field(default=None, repr=False)
    groq_api_key: Optional[str] = field(default=None, repr=False)
    tavily_api_key: Optional[str] = field(default=None, repr=False)
    blogger_blog_id: Optional[str] = None
    blogger_client_id: Optional[str] = field(default=None, repr=False)
    blogger_client_secret: Optional[str] = field(default=None, repr=False)
    blogger_refresh_token: Optional[str] = field(default=None, repr=False)

    # LLM provider parameters
    llm_provider: str = "auto"  # "auto", "gemini", or "groq"
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_temperature: float = 0.3
    gemini_max_tokens: int = 8192

    # Quality Gate thresholds
    min_word_count: int = 800
    max_word_count: int = 2500
    min_credible_sources: int = 2
    zambia_context_enabled: bool = False  # International audience default

    # Local-first repository state
    local_only: bool = True  # Native mode: persistent state stored in data/processed_topics.json in Git repository

    # Research domain filtering
    research_domain_allowlist: List[str] = field(default_factory=list)
    research_domain_blocklist: List[str] = field(default_factory=list)

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

        # In non-dry-run mode when writing with LLM
        if not self.dry_run and stage in ("all", "write"):
            has_gemini = bool(self.gemini_api_key and self.gemini_api_key.strip())
            has_groq = bool(self.groq_api_key and self.groq_api_key.strip())
            if not has_gemini and not has_groq:
                errors.append(
                    "At least one valid LLM API key (GEMINI_API_KEY or GROQ_API_KEY) is required for live generation. "
                    "Configure GEMINI_API_KEY or GROQ_API_KEY in environment variables or GitHub Secrets."
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
        is_confirmed = self.confirm_live_publish or _str_to_bool(os.getenv("CONFIRM_LIVE_PUBLISH"), default=False)
        if self.publish_mode == "publish" and not is_confirmed:
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
            "llm_provider": self.llm_provider,
            "local_only": self.local_only,
            "max_articles_per_run": self.max_articles_per_run,
            "gemini_model": self.gemini_model,
            "gemini_fallback_model": self.gemini_fallback_model,
            "gemini_temperature": self.gemini_temperature,
            "gemini_max_tokens": self.gemini_max_tokens,
            "groq_model": self.groq_model,
            "gemini_api_key": mask(self.gemini_api_key),
            "groq_api_key": mask(self.groq_api_key),
            "tavily_api_key": mask(self.tavily_api_key),
            "blogger_blog_id": self.blogger_blog_id or "Not Configured",
            "blogger_client_id": mask(self.blogger_client_id),
            "blogger_client_secret": mask(self.blogger_client_secret),
            "blogger_refresh_token": mask(self.blogger_refresh_token),
            "topics_csv_path": self.topics_csv_path,
            "min_word_count": self.min_word_count,
            "min_credible_sources": self.min_credible_sources,
            "research_domain_allowlist": self.research_domain_allowlist,
            "research_domain_blocklist": self.research_domain_blocklist,
        }


def _str_to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


def _parse_domain_list(env_val: Optional[str], fallback: List[str]) -> List[str]:
    if not env_val:
        return fallback or []
    val = env_val.strip()
    if val.startswith("[") and val.endswith("]"):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(d).strip().lower() for d in parsed if str(d).strip()]
        except Exception:
            pass
    return [d.strip().lower() for d in val.split(",") if d.strip()]


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
    gemini_cfg = json_cfg.get("gemini", {})
    editorial_cfg = json_cfg.get("editorial", {})
    research_cfg = json_cfg.get("research", {})

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

    gemini_temp_env = os.getenv("GEMINI_TEMPERATURE")
    if gemini_temp_env is not None:
        try:
            gemini_temp = float(gemini_temp_env)
        except ValueError:
            gemini_temp = float(gemini_cfg.get("temperature", 0.3))
    else:
        gemini_temp = float(gemini_cfg.get("temperature", 0.3))

    gemini_tokens_env = os.getenv("GEMINI_MAX_TOKENS")
    if gemini_tokens_env is not None:
        try:
            gemini_tokens = int(gemini_tokens_env)
        except ValueError:
            gemini_tokens = int(gemini_cfg.get("max_output_tokens", 8192))
    else:
        gemini_tokens = int(gemini_cfg.get("max_output_tokens", 8192))

    domain_allowlist = _parse_domain_list(
        os.getenv("RESEARCH_DOMAIN_ALLOWLIST"),
        research_cfg.get("domain_allowlist", []),
    )
    domain_blocklist = _parse_domain_list(
        os.getenv("RESEARCH_DOMAIN_BLOCKLIST"),
        research_cfg.get("domain_blocklist", []),
    )

    confirm_live_publish = _str_to_bool(os.getenv("CONFIRM_LIVE_PUBLISH"), default=False)

    config = AppConfig(
        dry_run=dry_run,
        publish_mode=publish_mode,
        confirm_live_publish=confirm_live_publish,
        max_articles_per_run=max_articles,
        local_only=True,
        topics_csv_path=os.getenv("TOPICS_CSV_PATH", "data/topics.csv"),
        processed_json_path=os.getenv("PROCESSED_JSON_PATH", "data/processed_topics.json"),
        output_dir=os.getenv("OUTPUT_DIR", "output"),
        llm_provider=os.getenv("LLM_PROVIDER", "auto").strip().lower(),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        blogger_blog_id=os.getenv("BLOGGER_BLOG_ID") or blogger_cfg.get("blog_id") or None,
        blogger_client_id=os.getenv("BLOGGER_CLIENT_ID"),
        blogger_client_secret=os.getenv("BLOGGER_CLIENT_SECRET"),
        blogger_refresh_token=os.getenv("BLOGGER_REFRESH_TOKEN"),
        gemini_model=os.getenv("GEMINI_MODEL") or gemini_cfg.get("model", "gemini-3.8-flash"),
        gemini_fallback_model=os.getenv("GEMINI_FALLBACK_MODEL") or gemini_cfg.get("fallback_model", "gemini-3.5-flash"),
        groq_model=os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
        gemini_temperature=gemini_temp,
        gemini_max_tokens=gemini_tokens,
        zambia_context_enabled=zambia_enabled,
        min_word_count=min_words,
        max_word_count=max_words,
        min_credible_sources=min_sources,
        research_domain_allowlist=domain_allowlist,
        research_domain_blocklist=domain_blocklist,
    )

    if overrides:
        for k, v in overrides.items():
            if hasattr(config, k) and v is not None:
                setattr(config, k, v)

    # Ensure output directory exists
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    Path(config.output_dir, "screenshots").mkdir(parents=True, exist_ok=True)

    return config


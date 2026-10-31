"""Application configuration loaded from YAML + optional local overrides."""

from __future__ import annotations

import ipaddress
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


def default_data_dir() -> Path:
    # 1. Environment variable override
    env_dir = os.getenv("MYMONEE_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()

    # 2. Linux Docker container mount check
    if Path("/data").is_dir():
        return Path("/data")

    # 3. macOS Application Support vs Linux XDG default
    if sys.platform == "darwin":
        # Check existing MyMonee or legacy ExpenseTracker
        primary = Path.home() / "Library" / "Application Support" / "MyMonee"
        legacy = Path.home() / "Library" / "Application Support" / "ExpenseTracker"
        if not primary.exists() and legacy.exists():
            return legacy
        return primary
    return Path.home() / ".local" / "share" / "mymonee"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_local_env() -> None:
    """Load `.env` from the repo root and the data directory, never overriding real env vars.

    Every entry point (server, CLI, MCP, scripts) imports this module, so secrets such as
    OPENROUTER_API_KEY are available everywhere — previously only the FastAPI app loaded them.
    """
    for candidate in (repo_root() / ".env", default_data_dir() / ".env"):
        try:
            load_dotenv(candidate, override=False)
        except OSError:
            continue


_load_local_env()


def bundled_config_path() -> Path:
    """Resolve default.yaml from repo or installed package."""
    repo_config = repo_root() / "config" / "default.yaml"
    if repo_config.exists():
        return repo_config
    bundled = Path(__file__).resolve().parent / "bundled_config" / "default.yaml"
    return bundled


def providers_dir() -> Path:
    path = repo_root() / "config" / "providers"
    if path.exists():
        return path
    return Path(__file__).resolve().parent / "bundled_config" / "providers"


class AppConfig(BaseModel):
    name: str = "my-monee"
    host: str = "127.0.0.1"
    port: int = 8477
    data_dir: Path | None = None
    # Public origin this app is served from when it sits behind a reverse proxy or
    # tunnel (e.g. "https://my-monee.example.com"). Required for browser-based
    # OAuth from any host other than the machine running the server: Google must
    # redirect back to an origin the visitor's browser can actually reach.
    public_url: str | None = None

    @field_validator("public_url")
    @classmethod
    def _normalize_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = value.strip().rstrip("/")
        if not url:
            return None
        if not url.startswith(("http://", "https://")):
            raise ValueError(
                "app.public_url must be an absolute http(s) origin, "
                "e.g. https://my-monee.example.com"
            )
        return url


class DatabaseConfig(BaseModel):
    filename: str = "mymonee.db"
    echo: bool = False


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: Path | None = None


class SchedulerConfig(BaseModel):
    enabled: bool = False
    interval_minutes: int = 15


class GmailConfig(BaseModel):
    enabled: bool = True
    credentials_file: Path | None = None
    scopes: list[str] = Field(
        default_factory=lambda: ["https://www.googleapis.com/auth/gmail.readonly"]
    )
    sync_after_date: str | None = "2026/01/01"  # Gmail after:YYYY/MM/DD
    initial_lookback_days: int = 90
    max_messages_per_sync: int = 2000


class AIConfig(BaseModel):
    """Online (external) AI for classification suggestions. Opt-in, and never leaves the Mac
    without `privacy.allow_external_ai`."""

    enabled: bool = False
    # "openrouter" sends every online call through OpenRouter — chat models via
    # /chat/completions and Jev (typesafe/*) via /systemone. "gemini" keeps the direct
    # Google SDK path for existing installs.
    provider: str = "openrouter"
    # Jev (TypeSafe System One) answers /systemone with a typed choice plus probabilities:
    # ~0.5s and $0.00009 per classification, versus ~3.6s and $0.0035 for a reasoning chat
    # model. A chat model is kept as the fallback path when Jev is unavailable.
    model: str = "typesafe/jev-1.13"
    # Chat fallback used only when Jev fails: DeepSeek measured 2.0s / $0.0001 per
    # classification against Gemini's 3.6s / $0.0035.
    fallback_models: list[str] = Field(default_factory=lambda: ["deepseek/deepseek-v4.1-flash"])
    base_url: str = "https://openrouter.ai/api/v1"
    # Suppress reasoning tokens on the chat path (Jev ignores it). Endpoints that mandate
    # reasoning, such as Gemini flash, reject it with 400 and the provider drops it and retries.
    disable_reasoning: bool = True
    timeout_seconds: float = 60.0
    # Transient-failure retries per request (429 / 5xx / transport). OpenAI-compatible
    # providers can take tens of seconds, so keep the ceiling modest.
    max_attempts: int = 3
    backoff_seconds: float = 0.5


class PrivacyConfig(BaseModel):
    allow_external_ai: bool = False
    store_raw_email_bodies: bool = False
    mask_identifiers: bool = True


class ClassificationConfig(BaseModel):
    auto_threshold: float = 0.85
    review_threshold: float = 0.55


class DashboardConfig(BaseModel):
    default_currency: str = "INR"
    month_start_day: int = 1


class BankingConfig(BaseModel):
    upi_handles: list[str] = Field(
        default_factory=lambda: [
            "okaxis",
            "okicici",
            "oksbi",
            "okhdfcbank",
            "ybl",
            "ibl",
            "axl",
            "paytm",
            "apl",
            "sbi",
            "hdfcbank",
            "icici",
            "axisbank",
            "upi",
            "pnb",
            "kotak",
            "barodampay",
        ]
    )


class EmbeddingsConfig(BaseModel):
    """Local embedding service integration (embedding-g2) for semantic search over the ledger.

    Disabled by default, like other opt-in inference features. This integration only talks to a
    service on the loopback interface; no transaction data leaves the machine.
    """

    enabled: bool = False
    base_url: str = "http://127.0.0.1:8001"
    # embedding-g2 queues inference internally (30s budget) before answering, so allow more.
    timeout_seconds: float = 35.0
    # At or below embedding-g2's max_batch_size (50).
    batch_size: int = 50
    # Transient-failure retries per HTTP request (503 SERVER_BUSY / MODEL_NOT_READY / transport).
    request_max_attempts: int = 5
    # Durable job attempts before a job is marked failed (each attempt may issue requests).
    max_attempts: int = 5
    backoff_seconds: float = 0.5
    # A job left "running" for longer than this (a crashed run) may be reclaimed.
    stale_job_seconds: int = 300


def _is_loopback_host(host: str) -> bool:
    """True when `host` only resolves on the machine serving the app."""
    if not host:
        return True
    candidate = host.strip().strip("[]").lower()
    if candidate == "localhost" or candidate.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    gmail: GmailConfig = Field(default_factory=GmailConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    banking: BankingConfig = Field(default_factory=BankingConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)

    def resolved_data_dir(self) -> Path:
        path = self.app.data_dir or default_data_dir()
        path.mkdir(parents=True, exist_ok=True)
        (path / "db").mkdir(exist_ok=True)
        (path / "statements").mkdir(exist_ok=True)
        (path / "evidence").mkdir(exist_ok=True)
        (path / "attachments").mkdir(exist_ok=True)
        (path / "backups").mkdir(exist_ok=True)
        (path / "exports").mkdir(exist_ok=True)
        (path / "tmp").mkdir(exist_ok=True)
        (path / "logs").mkdir(exist_ok=True)
        return path

    def database_path(self) -> Path:
        env_override = os.getenv("MYMONEE_DB_PATH") or os.getenv("EXPENSE_TRACKER_DB_PATH")
        if env_override:
            return Path(env_override).expanduser()

        data_dir = self.resolved_data_dir()
        configured = data_dir / self.database.filename
        legacy = data_dir / "expense_tracker.db"
        legacy_nested = data_dir / "db" / "expense_tracker.db"

        # If legacy database with data exists and configured is smaller/empty, use legacy
        if legacy.exists() and (
            not configured.exists() or legacy.stat().st_size > configured.stat().st_size
        ):
            return legacy
        if legacy_nested.exists() and (
            not configured.exists() or legacy_nested.stat().st_size > configured.stat().st_size
        ):
            return legacy_nested

        if configured.exists():
            return configured
        nested_path = data_dir / "db" / self.database.filename
        if nested_path.exists():
            return nested_path
        if legacy.exists():
            return legacy
        return configured

    def log_path(self) -> Path:
        if self.logging.file:
            return Path(self.logging.file)
        return self.resolved_data_dir() / "logs" / "mymonee.log"

    def gmail_credentials_path(self) -> Path:
        if self.gmail.credentials_file:
            return Path(self.gmail.credentials_file).expanduser()
        return self.resolved_data_dir() / "gmail_credentials.json"

    def oauth_redirect_uri(self, *, request_host: str | None = None) -> str:
        """Redirect URI Google must send the browser back to.

        Loopback stays the default: a Desktop OAuth client only accepts loopback
        URIs, and local-only setups must not depend on a tunnel being up. But when
        the app is reached through a non-loopback host (proxy, tunnel, phone),
        ``127.0.0.1`` resolves on the *visitor's* machine — so the request has to
        come back to the configured public origin instead.
        """
        if request_host and not _is_loopback_host(request_host):
            public = self._public_oauth_callback()
            if public:
                return public

        # Google's OAuth client only accepts loopback redirect URIs, so this
        # must stay 127.0.0.1 even if app.host is bound wider (e.g. 0.0.0.0).
        return self._loopback_oauth_callback()

    def oauth_redirect_uris(self) -> list[str]:
        """Every redirect URI that has to be registered on the Google client.

        Google matches redirect URIs literally, so the loopback URI and the
        public URI — when one is configured — must both be listed.
        """
        uris = [self._loopback_oauth_callback()]
        public = self._public_oauth_callback()
        if public:
            uris.append(public)
        return uris

    def _loopback_oauth_callback(self) -> str:
        host = self.app.host if self.app.host not in ("0.0.0.0", "::") else "127.0.0.1"
        return f"http://{host}:{self.app.port}/oauth/callback"

    def _public_oauth_callback(self) -> str | None:
        if not self.app.public_url:
            return None
        return f"{self.app.public_url}/oauth/callback"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")  # noqa: TRY004
    return data


def load_settings(local_override: Path | None = None) -> Settings:
    raw = _load_yaml(bundled_config_path())
    data_dir = default_data_dir()
    local_path = local_override or (data_dir / "config.local.yaml")
    raw = _deep_merge(raw, _load_yaml(local_path))

    if "app" in raw and isinstance(raw["app"], dict) and raw["app"].get("data_dir"):
        raw["app"]["data_dir"] = Path(raw["app"]["data_dir"]).expanduser()
    if "logging" in raw and isinstance(raw["logging"], dict) and raw["logging"].get("file"):
        raw["logging"]["file"] = Path(raw["logging"]["file"]).expanduser()
    if "gmail" in raw and isinstance(raw["gmail"], dict) and raw["gmail"].get("credentials_file"):
        raw["gmail"]["credentials_file"] = Path(raw["gmail"]["credentials_file"]).expanduser()

    return Settings.model_validate(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()

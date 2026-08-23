"""Application configuration loaded from YAML + optional local overrides."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


import os
import sys

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
    enabled: bool = False
    provider: str = "gemini"
    model: str = "gemini-3.7-flash"
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
        ]
    )


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
            "okaxis", "okicici", "oksbi", "okhdfcbank", 
            "ybl", "ibl", "axl", "paytm", "apl",
            "sbi", "hdfcbank", "icici", "axisbank", 
            "upi", "pnb", "kotak", "barodampay"
        ]
    )

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
        # Check standard flat or db/ nested path
        flat_path = self.resolved_data_dir() / self.database.filename
        if flat_path.exists():
            return flat_path
        nested_path = self.resolved_data_dir() / "db" / self.database.filename
        if nested_path.exists():
            return nested_path
        # Legacy fallback if mymonee.db exists
        legacy_flat = self.resolved_data_dir() / "mymonee.db"
        if legacy_flat.exists():
            return legacy_flat
        legacy_nested = self.resolved_data_dir() / "db" / "mymonee.db"
        if legacy_nested.exists():
            return legacy_nested
        return flat_path

    def log_path(self) -> Path:
        if self.logging.file:
            return Path(self.logging.file)
        return self.resolved_data_dir() / "logs" / "mymonee.log"

    def gmail_credentials_path(self) -> Path:
        if self.gmail.credentials_file:
            return Path(self.gmail.credentials_file).expanduser()
        return self.resolved_data_dir() / "gmail_credentials.json"

    def oauth_redirect_uri(self) -> str:
        # Google's OAuth client only accepts loopback redirect URIs, so this
        # must stay 127.0.0.1 even if app.host is bound wider (e.g. 0.0.0.0).
        host = self.app.host if self.app.host not in ("0.0.0.0", "::") else "127.0.0.1"
        return f"http://{host}:{self.app.port}/oauth/callback"


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
        raise ValueError(f"Config root must be a mapping: {path}")
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

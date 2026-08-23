"""Central logging setup — never log secrets or full card numbers."""

from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mymonee.config import Settings

_SENSITIVE_KEYS = (
    "token",
    "refresh_token",
    "access_token",
    "password",
    "client_secret",
    "client_id",
    "api_key",
    "authorization",
    "secret",
    "keychain",
)

# Regex to match potential 13-19 digit card numbers (allowing spaces or dashes)
_CARD_NUMBER_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# Regex to match Bearer / OAuth tokens and Google API keys
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE)
_API_KEY_RE = re.compile(r"\b(AIza[0-9A-Za-z-_]{30,45})\b")


def _mask_sensitive_text(text: str) -> str:
    """Mask credentials, card numbers, and sensitive parameters in text."""
    # Redact Google API keys
    text = _API_KEY_RE.sub("[REDACTED_API_KEY]", text)
    # Redact Bearer tokens
    text = _BEARER_RE.sub(r"\1[REDACTED_TOKEN]", text)

    # Redact credit card numbers (preserve last 4 digits)
    def _mask_card(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19:
            return f"****-****-****-{digits[-4:]}"
        return raw

    text = _CARD_NUMBER_RE.sub(_mask_card, text)
    return text


class RedactingFilter(logging.Filter):
    """Filters and redacts sensitive keys, credentials, and full PANs."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            # Fails closed on formatting/args mismatch errors: do not emit unredacted record
            record.msg = "[redacted log record formatting error]"
            record.args = ()
            return True

        lower = message.lower()
        if any(key in lower for key in _SENSITIVE_KEYS):
            sanitized = _mask_sensitive_text(message)
            for key in _SENSITIVE_KEYS:
                # Separator may be `[:=]` with no surrounding space (as in
                # "client_secret=GOCSPX-abc123" or URL query strings) or bare
                # whitespace (as in prose like "password abc123") — either
                # must trigger redaction of the value that follows.
                pattern = re.compile(
                    rf"({key}\s*(?:[:=]\s*|\s+))([^\s,;]+)", re.IGNORECASE
                )
                sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
            record.msg = sanitized
            record.args = ()
        else:
            masked = _mask_sensitive_text(message)
            if masked != message:
                record.msg = masked
                record.args = ()

        return True


def setup_logging(settings: Settings | None = None) -> None:
    """Configure structured logging for CLI, background jobs, and web server."""
    env_level = os.getenv("LOG_LEVEL") or os.getenv("EXPENSE_TRACKER_LOG_LEVEL")
    if env_level:
        level_str = env_level.upper()
    elif settings and getattr(settings, "logging", None) and getattr(settings.logging, "level", None):
        level_str = settings.logging.level.upper()
    else:
        level_str = "INFO"

    level = getattr(logging, level_str, logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redactor = RedactingFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(redactor)
    console.setLevel(level)
    root.addHandler(console)

    if settings is not None and hasattr(settings, "log_path"):
        try:
            log_path: Path = settings.log_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=5_000_000,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(redactor)
            file_handler.setLevel(level)
            root.addHandler(file_handler)
        except OSError:
            pass

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


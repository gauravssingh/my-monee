"""Gmail OAuth using loopback redirect + macOS Keychain via keyring."""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from expense_tracker.config import Settings

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "ExpenseTracker"
KEYRING_ACCOUNT = "gmail-oauth"
STATE_ACCOUNT = "gmail-oauth-state"


class GmailAuthError(RuntimeError):
    pass


@dataclass
class AuthStart:
    authorization_url: str
    state: str


def _token_to_dict(creds: Credentials) -> dict[str, Any]:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def _dict_to_credentials(data: dict[str, Any], scopes: list[str]) -> Credentials:
    expiry = None
    if data.get("expiry"):
        expiry = datetime.fromisoformat(data["expiry"])
        if expiry.tzinfo is not None:
            expiry = expiry.astimezone(UTC).replace(tzinfo=None)
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or scopes,
        expiry=expiry,
    )


def save_credentials(creds: Credentials, settings: Settings | None = None) -> None:
    payload = json.dumps(_token_to_dict(creds))
    saved_keyring = False
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, payload)
        saved_keyring = True
        logger.info("Stored Gmail OAuth credentials in macOS Keychain")
    except Exception as e:
        logger.info("Keyring unavailable (%s), storing token in data directory", e)

    # In Linux/Docker or fallback, store to data_dir/gmail_token.json
    try:
        from expense_tracker.config import get_settings
        s = settings or get_settings()
        token_path = s.resolved_data_dir() / "gmail_token.json"
        token_path.write_text(payload, encoding="utf-8")
        # Secure file permissions (read/write only for owner)
        try:
            token_path.chmod(0o600)
        except Exception:
            pass
    except Exception as e:
        logger.warning("Could not persist token file fallback: %s", e)


def load_credentials(settings: Settings) -> Credentials | None:
    raw = None
    try:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except Exception:
        pass

    if not raw:
        token_path = settings.resolved_data_dir() / "gmail_token.json"
        if token_path.exists():
            try:
                raw = token_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Could not read gmail_token.json: %s", e)

    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid Gmail token payload; clearing")
        clear_credentials(settings)
        return None
    return _dict_to_credentials(data, settings.gmail.scopes)


def clear_credentials(settings: Settings | None = None) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except Exception:
        pass
    try:
        keyring.delete_password(KEYRING_SERVICE, STATE_ACCOUNT)
    except Exception:
        pass

    try:
        from expense_tracker.config import get_settings
        s = settings or get_settings()
        token_path = s.resolved_data_dir() / "gmail_token.json"
        token_path.unlink(missing_ok=True)
    except Exception:
        pass


def is_connected(settings: Settings) -> bool:
    # Google access tokens expire in about an hour. A stored refresh token means the
    # connection is still valid, so refresh it before reporting the integration as
    # disconnected or allowing a caller to block sync.
    creds = get_valid_credentials(settings, refresh=True)
    return creds is not None and bool(creds.refresh_token or creds.token)


def get_valid_credentials(settings: Settings, *, refresh: bool = True) -> Credentials | None:
    creds = load_credentials(settings)
    if creds is None:
        return None
    if creds.valid:
        return creds
    if refresh and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
            return creds
        except Exception:
            logger.exception("Failed to refresh Gmail OAuth token")
            return None
    return creds if creds.valid else None


def _require_credentials_file(settings: Settings) -> None:
    path = settings.gmail_credentials_path()
    if not path.exists():
        raise GmailAuthError(
            f"Google OAuth client secrets not found at {path}. "
            "Create a Desktop OAuth client in Google Cloud Console, download the JSON, "
            "and save it there (or set gmail.credentials_file)."
        )


def _save_oauth_pending(*, state: str, code_verifier: str | None, redirect_uri: str) -> None:
    payload = {
        "state": state,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    keyring.set_password(KEYRING_SERVICE, STATE_ACCOUNT, json.dumps(payload))


def _load_oauth_pending() -> dict[str, Any] | None:
    raw = keyring.get_password(KEYRING_SERVICE, STATE_ACCOUNT)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("state"):
            return data
    except json.JSONDecodeError:
        # Legacy: plain state string
        return {"state": raw, "code_verifier": None, "redirect_uri": None}
    return {"state": raw, "code_verifier": None, "redirect_uri": None}


def _clear_oauth_pending() -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, STATE_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass


def start_oauth(settings: Settings) -> AuthStart:
    _require_credentials_file(settings)
    redirect_uri = settings.oauth_redirect_uri()
    flow = Flow.from_client_secrets_file(
        str(settings.gmail_credentials_path()),
        scopes=settings.gmail.scopes,
        redirect_uri=redirect_uri,
    )
    state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    # PKCE verifier is generated during authorization_url(); must survive into callback.
    _save_oauth_pending(
        state=state,
        code_verifier=getattr(flow, "code_verifier", None),
        redirect_uri=redirect_uri,
    )
    return AuthStart(authorization_url=auth_url, state=state)


def complete_oauth(settings: Settings, *, code: str, state: str | None) -> Credentials:
    pending = _load_oauth_pending()
    expected_state = pending.get("state") if pending else None
    if expected_state and state and state != expected_state:
        raise GmailAuthError("OAuth state mismatch — start Connect Gmail again")
    _require_credentials_file(settings)
    redirect_uri = (pending or {}).get("redirect_uri") or settings.oauth_redirect_uri()
    flow = Flow.from_client_secrets_file(
        str(settings.gmail_credentials_path()),
        scopes=settings.gmail.scopes,
        redirect_uri=redirect_uri,
        state=state or expected_state,
    )
    code_verifier = (pending or {}).get("code_verifier")
    if code_verifier:
        flow.code_verifier = code_verifier
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        logger.exception("Gmail OAuth token exchange failed")
        raise GmailAuthError(
            f"Token exchange failed ({exc}). Click Connect Gmail again — "
            "authorization codes are single-use and expire quickly."
        ) from exc
    creds = flow.credentials
    if not creds.refresh_token:
        # May happen on re-consent without prompt=consent; keep existing refresh if present
        existing = load_credentials(settings)
        if existing and existing.refresh_token:
            merged = _token_to_dict(creds)
            merged["refresh_token"] = existing.refresh_token
            creds = _dict_to_credentials(merged, settings.gmail.scopes)
    save_credentials(creds)
    _clear_oauth_pending()
    return creds

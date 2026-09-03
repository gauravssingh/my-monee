"""Local-first Authentication & Master Passcode service for MyMonee."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from mymonee.db.models import AppSetting, utcnow

ITERATIONS = 100_000
TOKEN_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days
_AUTH_CACHE_TTL_SECONDS = 60.0

_cached_auth_configured: bool | None = None
_cached_secret_key: str | None = None
_cache_timestamp: float = 0.0


def invalidate_auth_cache() -> None:
    """Clear in-memory auth cache so subsequent checks reload from database."""
    global _cached_auth_configured, _cached_secret_key, _cache_timestamp
    _cached_auth_configured = None
    _cached_secret_key = None
    _cache_timestamp = 0.0


def _get_setting(session: Session, key: str) -> Any | None:
    row = session.get(AppSetting, key)
    return row.value_json if row else None


def _set_setting(session: Session, key: str, value: Any) -> None:
    row = session.get(AppSetting, key)
    if row:
        row.value_json = value
        row.updated_at = utcnow()
    else:
        row = AppSetting(key=key, value_json=value)
        session.add(row)
    session.flush()


def _get_or_create_secret(session: Session) -> str:
    secret = _get_setting(session, "auth_secret_key")
    if not secret:
        secret = secrets.token_hex(32)
        _set_setting(session, "auth_secret_key", secret)
    return secret


def is_auth_configured(session: Session | None = None) -> bool:
    """Check if a master PIN has been configured. Uses in-memory cache if fresh."""
    global _cached_auth_configured, _cached_secret_key, _cache_timestamp
    now = time.time()
    if _cached_auth_configured is not None and (now - _cache_timestamp) < _AUTH_CACHE_TTL_SECONDS:
        return _cached_auth_configured

    if session is None:
        from mymonee.db.session import get_session_factory
        with get_session_factory()() as db_session:
            return is_auth_configured(db_session)

    pin_hash = _get_setting(session, "auth_pin_hash")
    is_conf = bool(pin_hash)
    _cached_auth_configured = is_conf
    if is_conf and _cached_secret_key is None:
        _cached_secret_key = _get_or_create_secret(session)
    _cache_timestamp = now
    return is_conf


def set_master_pin(session: Session, pin: str) -> str:
    pin = str(pin).strip()
    if len(pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 characters")

    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, ITERATIONS)

    _set_setting(session, "auth_pin_hash", derived.hex())
    _set_setting(session, "auth_salt", salt.hex())

    secret = _get_or_create_secret(session)

    global _cached_auth_configured, _cached_secret_key, _cache_timestamp
    _cached_auth_configured = True
    _cached_secret_key = secret
    _cache_timestamp = time.time()

    return create_session_token(secret)


def change_master_pin(session: Session, old_pin: str, new_pin: str) -> str:
    stored_hash = _get_setting(session, "auth_pin_hash")
    stored_salt = _get_setting(session, "auth_salt")

    if not stored_hash or not stored_salt:
        return set_master_pin(session, new_pin)

    salt_bytes = bytes.fromhex(stored_salt)
    derived = hashlib.pbkdf2_hmac("sha256", str(old_pin).strip().encode("utf-8"), salt_bytes, ITERATIONS)
    if not hmac.compare_digest(derived.hex(), stored_hash):
        raise HTTPException(status_code=401, detail="Incorrect existing PIN")

    return set_master_pin(session, new_pin)


def verify_master_pin(session: Session, pin: str) -> str:
    stored_hash = _get_setting(session, "auth_pin_hash")
    stored_salt = _get_setting(session, "auth_salt")

    if not stored_hash or not stored_salt:
        raise HTTPException(status_code=400, detail="Master PIN is not configured yet")

    salt_bytes = bytes.fromhex(stored_salt)
    derived = hashlib.pbkdf2_hmac("sha256", str(pin).strip().encode("utf-8"), salt_bytes, ITERATIONS)

    if not hmac.compare_digest(derived.hex(), stored_hash):
        raise HTTPException(status_code=401, detail="Invalid PIN")

    secret = _get_or_create_secret(session)
    return create_session_token(secret)


def create_session_token(secret_key: str) -> str:
    ts = int(time.time())
    payload = f"session:{ts}"
    sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_session_token(session: Session | None = None, token: str | None = None) -> bool:
    if not token or ":" not in token:
        return False

    try:
        parts = token.split(":")
        if len(parts) != 3 or parts[0] != "session":
            return False

        ts = int(parts[1])
        now = int(time.time())
        if now - ts > TOKEN_MAX_AGE_SECONDS or ts > now + 300:
            return False

        global _cached_secret_key, _cache_timestamp
        secret = _cached_secret_key
        if secret is None:
            if session is None:
                from mymonee.db.session import get_session_factory
                with get_session_factory()() as db_session:
                    secret = _get_or_create_secret(db_session)
            else:
                secret = _get_or_create_secret(session)
            _cached_secret_key = secret
            _cache_timestamp = now

        payload = f"session:{ts}"
        expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(parts[2], expected_sig)
    except Exception:
        return False

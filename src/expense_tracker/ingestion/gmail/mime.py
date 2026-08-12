"""MIME helpers for Gmail message payloads."""

from __future__ import annotations

import base64
import re
from email.utils import parsedate_to_datetime
from typing import Any


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _walk_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parts = payload.get("parts") or []
    if not parts:
        return [payload]
    collected: list[dict[str, Any]] = []
    for part in parts:
        if part.get("parts"):
            collected.extend(_walk_parts(part))
        else:
            collected.append(part)
    return collected


def extract_bodies(payload: dict[str, Any]) -> tuple[str, str | None]:
    text_chunks: list[str] = []
    html_chunks: list[str] = []
    for part in _walk_parts(payload):
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if not data:
            continue
        try:
            decoded = _b64url_decode(data).decode("utf-8", errors="replace")
        except Exception:
            continue
        if mime == "text/plain":
            text_chunks.append(decoded)
        elif mime == "text/html":
            html_chunks.append(decoded)
        elif mime.startswith("text/") and not text_chunks:
            text_chunks.append(decoded)

    text = "\n".join(text_chunks).strip()
    html = "\n".join(html_chunks).strip() or None
    if not text and html:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
    return text, html


def header_map(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers") or []
    result: dict[str, str] = {}
    for item in headers:
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            result[name.lower()] = value
    return result


def parse_internal_date(ms: str | int | None):
    if ms is None:
        return None
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_header_date(value: str | None):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            from datetime import timezone

            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

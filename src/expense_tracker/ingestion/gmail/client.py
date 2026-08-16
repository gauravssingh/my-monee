"""Thin Gmail API client."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from googleapiclient.discovery import build

from expense_tracker.config import Settings
from expense_tracker.ingestion.gmail import mime as mime_utils
from expense_tracker.ingestion.gmail.oauth import get_valid_credentials

logger = logging.getLogger(__name__)


EXCLUDED_RECIPIENT_PATTERNS: list[str] = [
    r"\bgauravsingh86@gmail\.com\b",
]


def is_excluded_recipient_headers(headers: dict[str, str] | None) -> bool:
    """Check if email headers explicitly indicate an excluded recipient (e.g. gauravsingh86@gmail.com without dots)."""
    if not headers:
        return False
    for key, val in headers.items():
        if key.lower() in (
            "to",
            "delivered-to",
            "x-original-to",
            "x-forwarded-to",
            "cc",
            "bcc",
            "envelope-to",
            "recipient",
        ):
            if val and any(re.search(p, str(val), re.IGNORECASE) for p in EXCLUDED_RECIPIENT_PATTERNS):
                return True
    return False


@dataclass
class GmailMessage:
    id: str
    thread_id: str | None
    sender: str | None
    subject: str | None
    snippet: str | None
    received_at: datetime | None
    label_ids: list[str]
    headers: dict[str, str]
    body_text: str
    body_html: str | None
    history_id: str | None = None
    internal_date_ms: int | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)

    def is_excluded_recipient(self) -> bool:
        """Return True if this email was addressed to an excluded recipient."""
        return is_excluded_recipient_headers(self.headers)


class MessageSource(Protocol):
    def list_message_ids(self, query: str, *, max_results: int) -> list[str]: ...

    def get_message(self, message_id: str) -> GmailMessage: ...

    def get_profile_history_id(self) -> str | None: ...

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes: ...


class GmailApiSource:
    def __init__(self, settings: Settings) -> None:
        creds = get_valid_credentials(settings, refresh=True)
        if creds is None:
            raise RuntimeError("Gmail is not connected")
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def list_message_ids(self, query: str, *, max_results: int) -> list[str]:
        ids: list[str] = []
        request = (
            self._service.users()
            .messages()
            .list(userId="me", q=query, maxResults=min(max_results, 500))
        )
        while request is not None and len(ids) < max_results:
            response = request.execute()
            for item in response.get("messages") or []:
                ids.append(item["id"])
                if len(ids) >= max_results:
                    break
            request = (
                self._service.users()
                .messages()
                .list_next(previous_request=request, previous_response=response)
            )
        return ids

    def get_message(self, message_id: str) -> GmailMessage:
        raw = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = raw.get("payload") or {}
        headers = mime_utils.header_map(payload)
        body_text, body_html = mime_utils.extract_bodies(payload)
        attachments = mime_utils.extract_attachments(payload)
        internal = raw.get("internalDate")
        received = mime_utils.parse_internal_date(internal) or mime_utils.parse_header_date(
            headers.get("date")
        )
        return GmailMessage(
            id=raw["id"],
            thread_id=raw.get("threadId"),
            sender=headers.get("from"),
            subject=headers.get("subject"),
            snippet=raw.get("snippet"),
            received_at=received,
            label_ids=list(raw.get("labelIds") or []),
            headers=headers,
            body_text=body_text,
            body_html=body_html,
            history_id=str(raw["historyId"]) if raw.get("historyId") is not None else None,
            internal_date_ms=int(internal) if internal is not None else None,
            attachments=attachments,
        )

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        raw = (
            self._service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        data = raw.get("data") or ""
        return mime_utils._b64url_decode(data)

    def get_profile_history_id(self) -> str | None:
        profile = self._service.users().getProfile(userId="me").execute()
        hid = profile.get("historyId")
        return str(hid) if hid is not None else None


class FixtureMessageSource:
    """In-memory source for tests and demo ingestion."""

    def __init__(
        self,
        messages: list[GmailMessage],
        attachments: dict[tuple[str, str], bytes] | None = None,
    ) -> None:
        self._by_id = {m.id: m for m in messages}
        self._attachments = attachments or {}

    def list_message_ids(self, query: str, *, max_results: int) -> list[str]:  # noqa: ARG002
        return list(self._by_id.keys())[:max_results]

    def get_message(self, message_id: str) -> GmailMessage:
        return self._by_id[message_id]

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        key = (message_id, attachment_id)
        if key in self._attachments:
            return self._attachments[key]
        # Check if attachment inline data is in message
        msg = self._by_id.get(message_id)
        if msg:
            for att in msg.attachments:
                if att.get("attachmentId") == attachment_id and att.get("data"):
                    return att["data"]
        raise KeyError(f"Attachment {attachment_id} not found for message {message_id}")

    def get_profile_history_id(self) -> str | None:
        return None


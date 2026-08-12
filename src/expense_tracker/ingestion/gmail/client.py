"""Thin Gmail API client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from googleapiclient.discovery import build

from expense_tracker.config import Settings
from expense_tracker.ingestion.gmail import mime as mime_utils
from expense_tracker.ingestion.gmail.oauth import get_valid_credentials

logger = logging.getLogger(__name__)


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


class MessageSource(Protocol):
    def list_message_ids(self, query: str, *, max_results: int) -> list[str]: ...

    def get_message(self, message_id: str) -> GmailMessage: ...

    def get_profile_history_id(self) -> str | None: ...


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
        )

    def get_profile_history_id(self) -> str | None:
        profile = self._service.users().getProfile(userId="me").execute()
        hid = profile.get("historyId")
        return str(hid) if hid is not None else None


class FixtureMessageSource:
    """In-memory source for tests and demo ingestion."""

    def __init__(self, messages: list[GmailMessage]) -> None:
        self._by_id = {m.id: m for m in messages}

    def list_message_ids(self, query: str, *, max_results: int) -> list[str]:  # noqa: ARG002
        return list(self._by_id.keys())[:max_results]

    def get_message(self, message_id: str) -> GmailMessage:
        return self._by_id[message_id]

    def get_profile_history_id(self) -> str | None:
        return None

"""Parser plugin protocol — implemented in Phase 2+."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass
class EmailContext:
    message_id: str
    thread_id: str | None
    sender: str | None
    subject: str | None
    received_at: datetime | None
    body_text: str
    body_html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)


@dataclass
class ParsedTransaction:
    amount: Decimal
    currency: str
    direction: str
    transaction_date: datetime
    transaction_type: str = "other"
    merchant_raw: str | None = None
    payment_method: str | None = None
    account: str | None = None
    card: str | None = None
    upi_id: str | None = None
    reference_number: str | None = None
    bank_reference: str | None = None
    description: str | None = None
    location: str | None = None
    posted_date: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ParserPlugin(Protocol):
    name: str
    priority: int

    def can_parse(self, email: EmailContext) -> float:
        """Return confidence 0–1 that this plugin should parse the email."""
        ...

    def parse(self, email: EmailContext) -> list[ParsedTransaction]:
        ...

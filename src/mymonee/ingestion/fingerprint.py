"""Idempotent transaction fingerprints."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal


def transaction_fingerprint(
    *,
    source_email_id: str,
    amount: Decimal,
    direction: str,
    transaction_date: datetime,
    merchant_raw: str | None,
    reference_number: str | None,
) -> str:
    date_key = transaction_date.date().isoformat()
    amount_key = f"{amount:.4f}"
    merchant_key = (merchant_raw or "").strip().upper()
    ref_key = (reference_number or "").strip().upper()
    material = "|".join(
        [
            source_email_id,
            amount_key,
            direction.lower(),
            date_key,
            merchant_key,
            ref_key,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

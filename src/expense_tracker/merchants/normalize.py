"""Merchant normalization stubs — Phase 4."""

from __future__ import annotations

import re


def normalize_merchant(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().upper()
    cleaned = re.sub(r"^(RAZ\*|PYU\*|PAYTM\*|GPAY\*)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.title() if cleaned else None

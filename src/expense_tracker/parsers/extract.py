"""Shared parsing helpers for amounts, dates, direction, references."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from dateutil import parser as date_parser

AMOUNT_PATTERNS = [
    re.compile(
        r"(?:INR|Rs\.?|₹)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?|\.[0-9]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*(?:INR|Rs\.?|₹)",
        re.IGNORECASE,
    ),
]

DEBIT_HINTS = re.compile(
    r"\b(debited|spent|paid|purchase|withdrawn|withdrawal|sent|amount debited)\b",
    re.IGNORECASE,
)
# Intentionally no bare "credit"/"debit" — those match "credit card" / "debit card".
CREDIT_HINTS = re.compile(
    r"\b(credited|received|refund(?:ed)?|reversed|reversal|cashback|amount credited)\b",
    re.IGNORECASE,
)
REFUND_HINTS = re.compile(r"\b(refund|reversed|reversal|chargeback)\b", re.IGNORECASE)
EMI_HINTS = re.compile(r"\b(emi|equated monthly)\b", re.IGNORECASE)
CARD_SPEND_HINTS = re.compile(
    r"(?:credit|debit)\s+cards?|using your .{0,80}card|card ending|"
    r"your payment on|transaction was successful",
    re.IGNORECASE,
)

REF_PATTERNS = [
    re.compile(
        r"\b((?:NEFT|IMPS|RTGS|ACH(?:-DR|-CR)?|UPI(?:LITE)?|UPI/P2A)/[A-Za-z0-9/.\-]{2,80})",
        re.I,
    ),
    re.compile(r"\b(?:UPI\s*(?:Ref|Ref No|Reference)[:\s#-]*|UPI[:\s#-]+)([A-Za-z0-9]+)", re.I),
    re.compile(r"\b(?:Txn(?:n)?(?:\s*ID|\s*Ref)?|Ref(?:erence)?(?:\s*No)?)[:\s#-]*([A-Za-z0-9-]+)", re.I),
    re.compile(r"\b(?:RRN|Stan)[:\s#-]*([A-Za-z0-9]+)", re.I),
]

MERCHANT_PATTERNS = [
    # Labeled field first (Scapia / fintech templates)
    re.compile(r"\bMerchant\s*[:\n\r]+\s*([^\n\r&#]{2,80})", re.I),
    re.compile(r"\bMerchant\s+([A-Z0-9][^\n\r&#]{1,80})", re.I),
    re.compile(r"(?:paid to|towards)\s+([A-Z0-9][A-Z0-9 &.*'-]{2,60})", re.I),
    re.compile(r"\bat\s+([A-Z][A-Z0-9 &.*'-]{2,60})", re.I),
    re.compile(r"\b(?:Info|INFO)[:\s]+([A-Z0-9][A-Z0-9 &.*'-]{2,60})", re.I),
]

MERCHANT_JUNK = re.compile(
    r"support on the scapia|head to support|not you\?|call\s*1800|customer\s*care|"
    r"for help|contact us|unsubscribe",
    re.I,
)

CARD_PATTERN = re.compile(r"\b(?:card|xx|ending|x{2,})[^\d]*(\d{4})\b", re.I)
UPI_ID_PATTERN = re.compile(r"\b([a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,})\b")
ACCOUNT_PATTERN = re.compile(r"\b(?:a/c|account|acct)[^\d]*([Xx*\d]{4,}\d{2,4})\b", re.I)


def parse_amount(text: str) -> Decimal | None:
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(1).replace(",", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        if value > 0:
            return value
    return None


def parse_all_amounts(text: str) -> list[Decimal]:
    found: list[Decimal] = []
    seen: set[str] = set()
    for pattern in AMOUNT_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1).replace(",", "")
            if raw in seen:
                continue
            seen.add(raw)
            try:
                value = Decimal(raw)
            except InvalidOperation:
                continue
            if value > 0:
                found.append(value)
    return found


def infer_direction(text: str) -> str:
    """Infer cashflow direction.

    Card-type phrases like ``credit card`` must not count as money-in credits.
    Card purchase / payment-success alerts are spending (debit) unless refund language.
    """
    if REFUND_HINTS.search(text) and not DEBIT_HINTS.search(text):
        return "credit"
    if CARD_SPEND_HINTS.search(text) and not re.search(r"\bcredited\b", text, re.I):
        return "debit"
    if CREDIT_HINTS.search(text) and not DEBIT_HINTS.search(text):
        return "credit"
    if DEBIT_HINTS.search(text):
        return "debit"
    if CREDIT_HINTS.search(text):
        return "credit"
    return "debit"


def infer_transaction_type(text: str, direction: str) -> str:
    if REFUND_HINTS.search(text):
        return "refund"
    if EMI_HINTS.search(text):
        return "emi_interest" if re.search(r"interest", text, re.I) else "emi"
    if re.search(r"\btransfer\b", text, re.I):
        return "transfer"
    if re.search(r"\bwithdraw", text, re.I):
        return "cash_withdrawal"
    if re.search(r"\b(fee|charge)\b", text, re.I):
        return "fee"
    if re.search(r"\b(gst|tax)\b", text, re.I):
        return "tax"
    if direction == "credit":
        return "other"
    return "purchase"


def extract_reference(text: str) -> str | None:
    for pattern in REF_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def extract_merchant(text: str) -> str | None:
    for pattern in MERCHANT_PATTERNS:
        for match in pattern.finditer(text):
            merchant = re.sub(r"\s+", " ", match.group(1)).strip(" .-:,")
            merchant = re.sub(r"\s+(Amount|Not you|Support|Card|Ending).*$", "", merchant, flags=re.I)
            if len(merchant) < 3:
                continue
            if MERCHANT_JUNK.search(merchant):
                continue
            # Reject clock fragments from "at 01:37 PM"
            if re.fullmatch(r"\d{1,2}", merchant):
                continue
            return merchant[:120]
    return None


def extract_card(text: str) -> str | None:
    match = CARD_PATTERN.search(text)
    return match.group(1) if match else None


def extract_upi_id(text: str) -> str | None:
    match = UPI_ID_PATTERN.search(text)
    return match.group(1) if match else None


def extract_account(text: str) -> str | None:
    match = ACCOUNT_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1)
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 4:
        return f"****{digits[-4:]}"
    return value


def parse_date_near_amount(text: str, fallback: datetime | None) -> datetime | None:
    """Extract a transaction date from email text.

    Important: never parse ISO ``YYYY-MM-DD`` with ``dayfirst=True`` — dateutil
    treats ``2026-05-10`` as 5 Oct 2026 in that mode.
    """

    def _attach_tz(dt: datetime) -> datetime:
        if dt.tzinfo is None and fallback and fallback.tzinfo:
            return dt.replace(tzinfo=fallback.tzinfo)
        return dt

    # 1) ISO dates / datetimes first (authoritative in many Indian fintech emails)
    iso_match = re.search(
        r"\b(\d{4}-\d{2}-\d{2})(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b",
        text,
    )
    if iso_match:
        try:
            raw = iso_match.group(0).replace(" ", "T", 1)
            # date-only
            if len(iso_match.group(0)) == 10:
                dt = datetime.fromisoformat(iso_match.group(1))
            else:
                dt = datetime.fromisoformat(raw)
            return _attach_tz(dt)
        except ValueError:
            pass

    # 2) Day + month name (unambiguous): 10 May 2026 / 10-May-2026
    named = re.search(
        r"\b(\d{1,2}[-/ ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
        r"[-/ ]\d{2,4})\b",
        text,
        re.IGNORECASE,
    )
    if named:
        try:
            dt = date_parser.parse(named.group(1), dayfirst=True)
            return _attach_tz(dt)
        except (ValueError, OverflowError, TypeError):
            pass

    # 3) Numeric D/M/Y — prefer Indian day-first; if ambiguous, pick closest to email date
    numeric = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", text)
    if numeric:
        token = numeric.group(0)
        try:
            dayfirst = date_parser.parse(token, dayfirst=True)
            monthfirst = date_parser.parse(token, dayfirst=False)
            dayfirst = _attach_tz(dayfirst)
            monthfirst = _attach_tz(monthfirst)
            if dayfirst.date() == monthfirst.date():
                return dayfirst
            if fallback is not None:
                if dayfirst.date() == fallback.date():
                    return dayfirst
                if monthfirst.date() == fallback.date():
                    return monthfirst
                # choose nearer interpretation
                d1 = abs((dayfirst.date() - fallback.date()).days)
                d2 = abs((monthfirst.date() - fallback.date()).days)
                return dayfirst if d1 <= d2 else monthfirst
            return dayfirst  # India default
        except (ValueError, OverflowError, TypeError):
            pass

    return fallback


def dates_look_day_month_swapped(parsed: datetime, reference: datetime) -> bool:
    """True when parsed is reference with day/month swapped (classic dayfirst ISO bug)."""
    p, r = parsed.date(), reference.date()
    return (
        p.year == r.year
        and p.day == r.month
        and p.month == r.day
        and r.day <= 12
        and r.month <= 12
        and p != r
    )


def html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        return soup.get_text("\n", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def combined_text(subject: str | None, body_text: str, body_html: str | None) -> str:
    parts: list[str] = []
    if subject:
        parts.append(subject)
    if body_text:
        parts.append(body_text)
    elif body_html:
        parts.append(html_to_text(body_html))
    return "\n".join(parts)


def first_nonempty(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None

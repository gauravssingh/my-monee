"""Statement discovery heuristics and candidate email identification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dateutil.relativedelta import relativedelta

from expense_tracker.ingestion.gmail.client import GmailMessage, is_excluded_recipient_headers


def _safe_date(year: int, month: int, day: int) -> datetime | None:
    """Build a UTC datetime, or None for a calendar-invalid year/month/day.

    Regex-captured date fragments from freeform email text (e.g. a US-style
    MM/DD misread as DD/MM, or a non-leap Feb 29) can describe a date that
    doesn't exist — that must fail this one candidate, not the whole email.
    """
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class DiscoveredStatementCandidate:
    source_email_id: str
    source_attachment_id: str
    issuer: str
    card_last4: str | None
    statement_date: datetime | None
    statement_period_start: datetime | None
    statement_period_end: datetime | None
    payment_due_date: datetime | None = None
    total_amount_due: float | None = None
    original_filename: str = ""
    statement_type: str = "CREDIT_CARD"
    attachment_data: bytes | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)


# Issuer definitions with sender regexes, subject patterns, and last4 regexes
# Issuer definitions with sender regexes and subject patterns
ISSUER_PATTERNS = [
    {
        "issuer": "SCAPIA",
        "senders": [r"@scapia\.cards", r"scapiacards@federalbank\.co\.in", r"scapia"],
        "subjects": [r"scapia.*statement", r"statement.*scapia", r"scapia\s+federal", r"\bscapia\b"],
    },
    {
        "issuer": "HDFC",
        "senders": [r"@hdfcbank\.(net|com)", r"hdfcbank"],
        "subjects": [r"hdfc.*statement", r"hdfc.*card.*statement", r"\bhdfc\b"],
    },
    {
        "issuer": "ICICI",
        "senders": [r"@icicibank\.(com|co\.in)", r"estatements\.icicibank\.com", r"icicibank"],
        "subjects": [r"icici.*statement", r"statement.*icici", r"\bicici\b"],
    },
    {
        "issuer": "AXIS",
        "senders": [
            r"@axisbank\.com",
            r"statements@axis\.bank\.in",
            r"axis\.bank\.in",
            r"axisbank",
            r"statements@axis",
        ],
        "subjects": [
            r"axis\s*bank\s*statement",
            r"axis.*statement",
            r"axis.*card.*e-?statement",
            r"money\s*quotient",
            r"\baxis\b",
        ],
    },
    {
        "issuer": "SBI",
        "senders": [r"@sbicard\.com", r"@sbi\.co\.in", r"sbicard"],
        "subjects": [r"sbi\s*card\s*statement", r"sbicard.*statement", r"\bsbi\b"],
    },
    {
        "issuer": "FEDERAL",
        "senders": [r"@federalbank\.co\.in", r"federalbank"],
        "subjects": [r"federal.*card.*statement", r"federal.*statement"],
    },
    {
        "issuer": "AMEX",
        "senders": [r"@americanexpress\.com", r"@.*\.aexp\.com", r"americanexpress"],
        "subjects": [r"american\s*express.*statement", r"amex.*statement"],
    },
]

GENERIC_STATEMENT_SUBJECTS = [
    r"credit\s*card\s*statement",
    r"card\s*e-?statement",
    r"statement\s*for\s*your\s*credit\s*card",
    r"monthly\s*statement\s*for\s*card",
    r"e-?statement\s*for\s*account",
    r"bank\s*statement",
]

CARD_LAST4_PATTERNS = [
    r"(?:ending|ends\s*in|ending\s*with|card\s*no\.?|card\s*ending\s*in|account\s*no\.?|a/c\s*no\.?|account\s*number|acct\s*no\.?|for\s*x+|\*+|xx+)\s*[:\-]?\s*(\d{4})",
    r"[xX\*]{2,12}(\d{4})",
    r"\bcard\s+(\d{4})\b",
    r"\ba/c\s+(\d{4})\b",
]

MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def detect_issuer(sender: str, subject: str, body: str = "") -> str:
    combined = f"{sender} {subject} {body}".lower()
    # Check Scapia specifically first since it is co-branded on federalbank.co.in
    if "scapia" in combined:
        return "SCAPIA"
    for item in ISSUER_PATTERNS:
        if any(re.search(p, sender, re.IGNORECASE) for p in item["senders"]):
            return item["issuer"]
        if any(re.search(p, subject, re.IGNORECASE) for p in item["subjects"]):
            return item["issuer"]
    # Fallback keyword checks
    if "hdfc" in combined:
        return "HDFC"
    if "icici" in combined:
        return "ICICI"
    if "axis" in combined:
        return "AXIS"
    if "sbicard" in combined or "sbi card" in combined:
        return "SBI"
    if "federal" in combined:
        return "FEDERAL"
    if "amex" in combined or "american express" in combined:
        return "AMEX"
    return "UNKNOWN"


def detect_statement_type(sender: str, subject: str, body: str = "") -> str:
    """Classify whether the statement is for a Credit Card or Bank Account.

    Direct Axis Sender Rule:
    - cc.statements@axis.bank.in (or axisbank.com) -> CREDIT_CARD
    - statements@axis.bank.in (or axisbank.com) -> BANK_ACCOUNT
    """
    sender_lower = (sender or "").lower()
    subject_lower = (subject or "").lower()

    # 1. Direct Axis Sender Classification
    if "cc.statements@" in sender_lower:
        return "CREDIT_CARD"
    if "statements@axis.bank.in" in sender_lower or "statements@axisbank.com" in sender_lower:
        return "BANK_ACCOUNT"

    # 2. General Credit Card senders/subjects
    if "credit" in sender_lower or re.search(
        r"credit\s*card|scapia|sbicard|card\s*statement|rewards\s*credit\s*card",
        subject_lower,
    ):
        return "CREDIT_CARD"

    # 3. General Bank Account subjects/senders
    if re.search(
        r"money\s*quotient|bank\s*statement|account\s*statement|savings\s*account|current\s*account|casa|for\s*x{3,}\d{4}",
        subject_lower,
    ):
        return "BANK_ACCOUNT"

    # 4. Content fallback
    body_lower = (body or "").lower()
    if re.search(r"money\s*quotient|savings\s*account|current\s*account|account\s*statement", body_lower):
        return "BANK_ACCOUNT"
    if "credit card" in body_lower or "scapia card" in body_lower or "sbicard" in body_lower:
        return "CREDIT_CARD"

    return "CREDIT_CARD"


def extract_card_last4(text: str) -> str | None:
    for pattern in CARD_LAST4_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            digits = match.group(1)
            if len(digits) == 4 and digits.isdigit():
                # Prevent extracting statement year (e.g. 2024..2030) as card last 4 digits
                if 2000 <= int(digits) <= 2099:
                    prefix_match = re.search(
                        r"(?:ending|ends\s*in|ending\s*with|card\s*no\.?|card\s*#?|account\s*no\.?|for\s*x+|[xX\*]{2,})\s*[:\-]?\s*"
                        + digits,
                        text,
                        re.IGNORECASE,
                    )
                    if not prefix_match:
                        continue
                return digits
    return None


def parse_date_str(date_str: str) -> datetime | None:
    """Parse various Indian banking date formats into timezone-aware UTC datetime."""
    s = date_str.strip()
    months_re = "|".join(MONTH_NAMES.keys())
    # DD Mon YYYY / DD-Mon-YYYY / DD Month YYYY
    m = re.match(rf"(\d{{1,2}})(?:st|nd|rd|th)?[\s\-_]+({months_re})[\s\-_]+(20\d{{2}})", s, re.IGNORECASE)
    if m:
        d, mon, y = m.groups()
        mon_num = MONTH_NAMES.get(mon.lower()[:3]) or MONTH_NAMES.get(mon.lower())
        if mon_num:
            return _safe_date(int(y), mon_num, int(d))
    # Mon DD, YYYY / Month DD, YYYY
    m = re.match(rf"({months_re})[\s\-_]+(\d{{1,2}}),?[\s\-_]+(20\d{{2}})", s, re.IGNORECASE)
    if m:
        mon, d, y = m.groups()
        mon_num = MONTH_NAMES.get(mon.lower()[:3]) or MONTH_NAMES.get(mon.lower())
        if mon_num:
            return _safe_date(int(y), mon_num, int(d))
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})", s)
    if m:
        d, mon, y = m.groups()
        return _safe_date(int(y), int(mon), int(d))
    # YYYY-MM-DD
    m = re.match(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mon, d = m.groups()
        return _safe_date(int(y), int(mon), int(d))
    return None


def extract_statement_dates(
    subject: str, snippet: str = "", received_at: datetime | None = None
) -> tuple[datetime | None, datetime | None, datetime | None]:
    """Extract (statement_date, period_start, period_end) from email subject or filename."""
    text = subject.lower()
    months_re = "|".join(MONTH_NAMES.keys())

    # 1. Check for Month DD, YYYY to Month DD, YYYY (e.g. September 01, 2025 to September 30, 2025)
    named_range = re.search(
        rf"\b({months_re})\s+(\d{{1,2}}),?\s+(20\d{{2}})\s*(?:to|–|-)\s*({months_re})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
        text,
    )
    if named_range:
        m1_str, d1_str, y1_str, m2_str, d2_str, y2_str = named_range.groups()
        start = _safe_date(int(y1_str), MONTH_NAMES[m1_str], int(d1_str))
        end = _safe_date(int(y2_str), MONTH_NAMES[m2_str], int(d2_str))
        if start and end:
            return end, start, end

    # 2. Check for DD Mon YYYY to DD Mon YYYY (e.g. 21 Jun 2026 - 20 Jul 2026)
    dd_mon_range = re.search(
        rf"(\d{{1,2}})\s+({months_re})\s+(20\d{{2}})\s*(?:to|–|-)\s*(\d{{1,2}})\s+({months_re})\s+(20\d{{2}})",
        text,
    )
    if dd_mon_range:
        d1_str, m1_str, y1_str, d2_str, m2_str, y2_str = dd_mon_range.groups()
        start = _safe_date(int(y1_str), MONTH_NAMES[m1_str], int(d1_str))
        end = _safe_date(int(y2_str), MONTH_NAMES[m2_str], int(d2_str))
        if start and end:
            return end, start, end

    # 3. Check for explicit Month Name + Year in subject, e.g. "for July 2026", "July 2026", "Statement for July 2026"
    month_pattern = r"(?:for\s+)?\b(" + months_re + r")[\s\-_,]+(20\d{2})\b"
    m = re.search(month_pattern, text)
    if m:
        month_str, year_str = m.groups()
        month = MONTH_NAMES[month_str]
        year = int(year_str)
        period_start = datetime(year, month, 1, tzinfo=timezone.utc)
        period_end = period_start + relativedelta(months=1, days=-1)
        statement_date = period_end
        return statement_date, period_start, period_end

    # 4. Check for explicit date ranges: DD/MM/YYYY to DD/MM/YYYY
    range_pattern = r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\s*(?:to|–|-)\s*(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})"
    m = re.search(range_pattern, text)
    if m:
        d1, m1, y1, d2, m2, y2 = m.groups()
        start = _safe_date(int(y1), int(m1), int(d1))
        end = _safe_date(int(y2), int(m2), int(d2))
        if start and end:
            return end, start, end

    return None, None, None


def extract_statement_metadata(
    subject: str,
    snippet: str = "",
    body: str = "",
    received_at: datetime | None = None,
) -> dict[str, Any]:
    """Extract statement_period, statement_date, payment_due_date, and total_amount_due from email content."""
    combined_body = f"{snippet} {body[:2500]}".strip()
    months_re = "|".join(MONTH_NAMES.keys())

    period_start: datetime | None = None
    period_end: datetime | None = None
    statement_date: datetime | None = None
    due_date: datetime | None = None
    total_amount_due: float | None = None

    # 1. Look for explicit statement period (e.g. Scapia "statement for 21 Jun 2026 - 20 Jul 2026")
    range_match = re.search(
        rf"(?:statement\s*(?:for|period)|billing\s*period|period)?\s*[:\-]?\s*(\d{{1,2}}(?:st|nd|rd|th)?[\s\-_]+(?:{months_re})[\s\-_]+20\d{{2}}|\d{{1,2}}[-/.](?:{months_re}|\d{{1,2}})[-/.]20\d{{2}})\s*(?:to|–|-)\s*(\d{{1,2}}(?:st|nd|rd|th)?[\s\-_]+(?:{months_re})[\s\-_]+20\d{{2}}|\d{{1,2}}[-/.](?:{months_re}|\d{{1,2}})[-/.]20\d{{2}})",
        combined_body,
        re.IGNORECASE,
    )
    if range_match:
        p_start_str, p_end_str = range_match.groups()
        period_start = parse_date_str(p_start_str)
        period_end = parse_date_str(p_end_str)
        if period_end:
            statement_date = period_end

    # Fallback to subject-based extraction if not in body
    if not period_start or not period_end:
        s_date, s_start, s_end = extract_statement_dates(subject, snippet, received_at)
        if s_start and s_end:
            period_start = s_start
            period_end = s_end
            statement_date = s_date or s_end

    # 2. Look for explicit Statement Date in body/snippet
    stmt_date_match = re.search(
        rf"(?:statement\s*date|bill\s*date|generated\s*on)\s*[:\-]?\s*(\d{{1,2}}(?:st|nd|rd|th)?[\s\-_]+(?:{months_re})[\s\-_]+20\d{{2}}|\d{{1,2}}[-/.](?:{months_re}|\d{{1,2}})[-/.]20\d{{2}})",
        combined_body,
        re.IGNORECASE,
    )
    if stmt_date_match:
        parsed_sd = parse_date_str(stmt_date_match.group(1))
        if parsed_sd:
            statement_date = parsed_sd

    # 3. Look for Payment Due Date in body/snippet
    due_date_match = re.search(
        rf"(?:payment\s*due\s*date|due\s*date|pay\s*by|due\s*on)\s*[:\-]?\s*(\d{{1,2}}(?:st|nd|rd|th)?[\s\-_]+(?:{months_re})[\s\-_]+20\d{{2}}|\d{{1,2}}[-/.](?:{months_re}|\d{{1,2}})[-/.]20\d{{2}})",
        combined_body,
        re.IGNORECASE,
    )
    if due_date_match:
        due_date = parse_date_str(due_date_match.group(1))

    # 4. Look for Total Amount Due in body/snippet
    amount_match = re.search(
        r"(?:total\s*amount\s*due|total\s*due|amount\s*due|amt\s*due)\s*[:\-]?\s*(?:(?:inr|rs\.?|₹)\s*)?([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{2})?|[0-9]+(?:\.[0-9]{2})?)",
        combined_body,
        re.IGNORECASE,
    )
    if amount_match:
        try:
            amt_str = amount_match.group(1).replace(",", "")
            total_amount_due = float(amt_str)
        except Exception:
            total_amount_due = None

    return {
        "statement_period_start": period_start,
        "statement_period_end": period_end,
        "statement_date": statement_date,
        "payment_due_date": due_date,
        "total_amount_due": total_amount_due,
    }


EXCLUDED_STATEMENT_PATTERNS = [
    r"home\s*loan",
    r"personal\s*loan",
    r"car\s*loan",
    r"auto\s*loan",
    r"loan\s*account",
    r"emi\s*letter",
    r"provisional[-_\s]*statement",
    r"provisional",
    r"interest\s*certificate",
    r"tax\s*certificate",
    r"it_prov",
    r"no\s*dues\s*certificate",
    r"mitc",
    r"kfs",
    r"key\s*fact",
    r"most\s*important\s*terms",
    r"welcome\s*kit",
    r"card\s*member\s*agreement",
    r"demat",
    r"mutual\s*fund",
    r"fixed\s*deposit",
    r"recurring\s*deposit",
    r"lichousing",
    r"instaforex",
]


def is_statement_candidate(message: GmailMessage) -> bool:
    sender = message.sender or ""
    subject = message.subject or ""

    # Universal filtering: Exclude emails sent to invalid/unwanted recipients (e.g. gauravsingh86@gmail.com without dots)
    if hasattr(message, "is_excluded_recipient") and callable(message.is_excluded_recipient):
        if message.is_excluded_recipient():
            return False
    elif is_excluded_recipient_headers(getattr(message, "headers", None)):
        return False

    # Exclude loan statements, tax/interest certificates, and provisional statements
    if any(re.search(p, subject, re.IGNORECASE) for p in EXCLUDED_STATEMENT_PATTERNS):
        return False
    if any(re.search(p, sender, re.IGNORECASE) for p in EXCLUDED_STATEMENT_PATTERNS):
        return False

    # Check subject against generic statement subjects
    if any(re.search(p, subject, re.IGNORECASE) for p in GENERIC_STATEMENT_SUBJECTS):
        return True

    # Check issuer-specific subject patterns
    for item in ISSUER_PATTERNS:
        if any(re.search(p, sender, re.IGNORECASE) for p in item["senders"]):
            if any(re.search(p, subject, re.IGNORECASE) for p in item["subjects"]):
                return True
            # If sender is statement sender and subject contains statement or e-statement
            if re.search(r"statement|e-?bill", subject, re.IGNORECASE):
                return True

    # Check body / snippet
    if ("credit card" in subject.lower() or "card" in subject.lower() or "bank" in subject.lower()) and "statement" in subject.lower():
        return True

    return False


def discover_statement_candidates(
    messages: list[GmailMessage],
) -> list[DiscoveredStatementCandidate]:
    """Scan messages and extract statement candidates with attachment metadata."""
    candidates: list[DiscoveredStatementCandidate] = []

    for msg in messages:
        if not is_statement_candidate(msg):
            continue

        attachments = msg.attachments or []
        pdf_attachments = [
            att for att in attachments
            if (att.get("filename", "").lower().endswith(".pdf") or att.get("mimeType") == "application/pdf")
        ]

        if not pdf_attachments:
            # Check if there's any attachment ID or file
            continue

        issuer = detect_issuer(msg.sender or "", msg.subject or "", msg.body_text or "")
        stmt_type = detect_statement_type(msg.sender or "", msg.subject or "", msg.body_text or "")
        card_last4 = extract_card_last4(f"{msg.subject or ''} {msg.snippet or ''} {msg.body_text[:1000] if msg.body_text else ''}")
        
        meta = extract_statement_metadata(
            msg.subject or "", msg.snippet or "", msg.body_text or "", msg.received_at
        )

        for att in pdf_attachments:
            att_id = att.get("attachmentId") or f"inline_{att.get('filename')}"
            filename = att.get("filename") or f"{issuer.lower()}_statement.pdf"
            
            # Exclude provisional interest certificates or loan statement attachments
            if any(re.search(p, filename, re.IGNORECASE) for p in EXCLUDED_STATEMENT_PATTERNS):
                continue

            # Filename might also contain card last 4
            if not card_last4:
                card_last4 = extract_card_last4(filename)

            candidates.append(
                DiscoveredStatementCandidate(
                    source_email_id=msg.id,
                    source_attachment_id=att_id,
                    issuer=issuer,
                    card_last4=card_last4,
                    statement_date=meta["statement_date"],
                    statement_period_start=meta["statement_period_start"],
                    statement_period_end=meta["statement_period_end"],
                    payment_due_date=meta["payment_due_date"],
                    total_amount_due=meta["total_amount_due"],
                    original_filename=filename,
                    statement_type=stmt_type,
                    attachment_data=att.get("data"),
                    extra_metadata={
                        "sender": msg.sender,
                        "subject": msg.subject,
                        "received_at": msg.received_at.isoformat() if msg.received_at else None,
                        "payment_due_date": meta["payment_due_date"].isoformat() if meta["payment_due_date"] else None,
                        "total_amount_due": meta["total_amount_due"],
                    },
                )
            )

    return candidates

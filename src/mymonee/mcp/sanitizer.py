"""Centralized privacy sanitizer and fail-closed privacy validator.

Operating principle:
Database -> Domain Calculation -> Agent DTO -> Privacy Validator -> MCP Response
If any prohibited pattern or canary is detected on the response path, the validator
fails closed by raising an AgentServiceError(ErrorCode.INTERNAL).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel

from mymonee.mcp.errors import AgentServiceError, ErrorCode, generate_correlation_id

logger = logging.getLogger(__name__)

# Test canaries
CANARY_PATTERNS = [
    "SECRET_API_KEY_TEST",
    "OAUTH_TOKEN_TEST",
    "REFRESH_TOKEN_TEST",
    "FULL_ACCOUNT_TEST",
    "test@example.com",
    "CANARY_LEAK_TEST",
    "CANARY_PASSWORD_TEST",
    "GMAIL_ID_TEST_",
]

# Sensitive runtime patterns
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
JWT_REGEX = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
BEARER_REGEX = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE)
FILE_PATH_REGEX = re.compile(r"(?:/Users/|/home/|/private/|/var/|[a-zA-Z]:\\)[^\s,;\"]+", re.IGNORECASE)
DB_NAME_REGEX = re.compile(r"\b\w+\.(?:sqlite|db|sqlite3|wal|shm)\b", re.IGNORECASE)
TRACEBACK_REGEX = re.compile(r"Traceback \(most recent call last\):")
UPI_VPA_REGEX = re.compile(r"\b[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}\b")
BANK_REF_REGEX = re.compile(r"\b(?:UTR|Ref|Txn|IMPS|NEFT|RTGS)[:\s]*[A-Za-z0-9]{12,25}\b", re.IGNORECASE)


def mask_account(account: str | None) -> str | None:
    """Mask account string, revealing at most the last 4 alphanumeric characters."""
    if not account:
        return None
    cleaned = account.strip()
    digits = re.findall(r"[A-Za-z0-9]", cleaned)
    if not digits:
        return "••••"
    last4 = "".join(digits[-4:])
    return f"•••• {last4}"


def mask_card(card: str | None) -> str | None:
    """Mask card string, revealing at most the last 4 digits."""
    if not card:
        return None
    cleaned = re.sub(r"\D", "", card)
    if not cleaned:
        return "••••"
    last4 = cleaned[-4:]
    return f"•••• {last4}"


def sanitize_merchant(raw: str | None, normalized: str | None) -> str:
    """Derive clean, sanitized merchant name."""
    if normalized and normalized.strip():
        name = normalized.strip()
    elif raw and raw.strip():
        # Strip trailing location codes like "BLR", "MUMBAI", "NEW DELHI" if excessive
        name = re.sub(r"\s+(?:BANGALORE|BLR|MUMBAI|DELHI|GURGAON|NOIDA)\s*$", "", raw.strip(), flags=re.IGNORECASE)
    else:
        name = "Unknown Merchant"
    # Never exceed 80 chars
    return name[:80]


def sanitize_description(desc: str | None) -> str | None:
    """Strip banking reference codes, UPI VPAs, and email addresses from descriptions."""
    if not desc:
        return None
    cleaned = desc.strip()
    # Remove UTR / banking reference sequences
    cleaned = BANK_REF_REGEX.sub("[REF]", cleaned)
    # Remove UPI handles
    cleaned = UPI_VPA_REGEX.sub("[UPI]", cleaned)
    # Remove emails
    cleaned = EMAIL_REGEX.sub("[EMAIL]", cleaned)
    return cleaned[:200]


def _is_luhn_valid(number_str: str) -> bool:
    """Verify if a 13-19 digit string satisfies the Luhn check (credit/debit card)."""
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for idx, d in enumerate(reverse_digits):
        if idx % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def _check_string_for_leaks(value: str, field_path: str, cid: str) -> None:
    """Inspect a single string value for prohibited patterns and canaries."""
    # 1. Canary checks
    for canary in CANARY_PATTERNS:
        if canary in value:
            logger.error("Privacy canary detected: cid=%s, canary=%s, field=%s", cid, canary, field_path)
            raise AgentServiceError(ErrorCode.INTERNAL, "Unable to complete requested operation.", cid=cid)

    # 2. Pattern checks
    if EMAIL_REGEX.search(value):
        logger.error("Email pattern detected in DTO: cid=%s, field=%s", cid, field_path)
        raise AgentServiceError(ErrorCode.INTERNAL, "Unable to complete requested operation.", cid=cid)

    if JWT_REGEX.search(value) or BEARER_REGEX.search(value):
        logger.error("Auth token pattern detected in DTO: cid=%s, field=%s", cid, field_path)
        raise AgentServiceError(ErrorCode.INTERNAL, "Unable to complete requested operation.", cid=cid)

    if FILE_PATH_REGEX.search(value) or DB_NAME_REGEX.search(value):
        logger.error("Filesystem/DB path pattern detected in DTO: cid=%s, field=%s", cid, field_path)
        raise AgentServiceError(ErrorCode.INTERNAL, "Unable to complete requested operation.", cid=cid)

    if TRACEBACK_REGEX.search(value):
        logger.error("Stack trace pattern detected in DTO: cid=%s, field=%s", cid, field_path)
        raise AgentServiceError(ErrorCode.INTERNAL, "Unable to complete requested operation.", cid=cid)

    # 3. Card number check (13 to 19 digits)
    potential_cards = re.findall(r"\b(?:\d[ -]*?){13,19}\b", value)
    for p in potential_cards:
        clean_num = re.sub(r"\D", "", p)
        if _is_luhn_valid(clean_num):
            logger.error("Luhn-valid card number detected in DTO: cid=%s, field=%s", cid, field_path)
            raise AgentServiceError(ErrorCode.INTERNAL, "Unable to complete requested operation.", cid=cid)


def validate_agent_dto(dto: Any, cid: str | None = None, field_prefix: str = "root") -> None:
    """Recursively validate that no PII, tokens, paths, or canaries exist in an Agent DTO.

    FAILS CLOSED: If any leak is detected, raises AgentServiceError(ErrorCode.INTERNAL).
    """
    cid = cid or generate_correlation_id()
    if isinstance(dto, str):
        _check_string_for_leaks(dto, field_prefix, cid)
    elif isinstance(dto, BaseModel):
        for field_name, val in dto.__dict__.items():
            validate_agent_dto(val, cid=cid, field_prefix=f"{field_prefix}.{field_name}")
    elif isinstance(dto, dict):
        for k, val in dto.items():
            validate_agent_dto(val, cid=cid, field_prefix=f"{field_prefix}.{k}")
    elif isinstance(dto, (list, tuple, set)):
        for idx, item in enumerate(dto):
            validate_agent_dto(item, cid=cid, field_prefix=f"{field_prefix}[{idx}]")

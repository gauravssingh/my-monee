"""Input validation and parameter bounding for MCP tools.

Enforces:
- Strict parameter bounds (limits, history months, text lengths)
- Pydantic models with ConfigDict(extra="forbid")
- Safe date boundaries (rejecting 0001-01-01 or 9999-12-31)
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict

from mymonee.mcp.errors import AgentServiceError, ErrorCode
from mymonee.mcp.limits import Limits

MONTH_REGEX = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MIN_ALLOWED_YEAR = 2000
MAX_ALLOWED_YEAR = 2100


class BaseInputModel(BaseModel):
    """Base input model forbidding unrecognized extra parameters."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def validate_month_arg(month: str | None) -> str:
    """Validate and normalize month parameter ('current', 'last', 'YYYY-MM', or month names)."""
    if not month or month.strip().lower() == "current":
        return "current"
    val = month.strip().lower()
    if val == "last":
        return "last"

    # Match named month + year e.g. 'july 2026'
    m_name_year = re.match(r"^([a-z]+)\s+(\d{4})$", val)
    if m_name_year and m_name_year.group(1) in MONTH_NAMES:
        m_num = MONTH_NAMES[m_name_year.group(1)]
        y_num = int(m_name_year.group(2))
        return f"{y_num:04d}-{m_num:02d}"

    # Match single month name e.g. 'july' -> defaults to current year
    if val in MONTH_NAMES:
        from datetime import UTC, datetime

        curr_year = datetime.now(UTC).year
        return f"{curr_year:04d}-{MONTH_NAMES[val]:02d}"

    if not MONTH_REGEX.match(val):
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT,
            f"Invalid month format '{month}'. Expected 'current', 'last', 'YYYY-MM', or month name.",
        )
    year = int(val[:4])
    if year < MIN_ALLOWED_YEAR or year > MAX_ALLOWED_YEAR:
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT,
            f"Year {year} is out of allowable range ({MIN_ALLOWED_YEAR}–{MAX_ALLOWED_YEAR}).",
        )
    return val


def validate_range_arg(range_str: str | None) -> str:
    """Validate time range string ('1m', '3m', '6m', '12m', 'ytd')."""
    if not range_str:
        return "1m"
    clean = range_str.strip().lower()
    if clean not in {"1m", "3m", "6m", "12m", "ytd"}:
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT,
            f"Invalid range '{range_str}'. Supported ranges: '1m', '3m', '6m', '12m', 'ytd'.",
        )
    return clean


def validate_limit_arg(
    limit: int | None, default: int = Limits.DEFAULT_RESULTS, max_limit: int = Limits.MAX_RESULTS
) -> int:
    """Clamp limit to safe bounds [1, max_limit]."""
    if limit is None:
        return default
    if limit <= 0:
        raise AgentServiceError(ErrorCode.INVALID_ARGUMENT, "Limit must be a positive integer.")
    return min(int(limit), max_limit)


def validate_months_arg(
    months: int | None,
    default: int = Limits.DEFAULT_HISTORY_MONTHS,
    max_months: int = Limits.MAX_HISTORY_MONTHS,
) -> int:
    """Clamp historical months lookback to safe bounds [1, max_months]."""
    if months is None:
        return default
    if months <= 0:
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT, "Months parameter must be a positive integer."
        )
    return min(int(months), max_months)


def validate_date_arg(date_str: str | None, param_name: str = "date") -> date | None:
    """Validate and parse ISO date string YYYY-MM-DD within allowable calendar range."""
    if not date_str or not date_str.strip():
        return None
    val = date_str.strip()
    if not DATE_REGEX.match(val):
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT,
            f"Invalid {param_name} format '{date_str}'. Expected 'YYYY-MM-DD'.",
        )
    try:
        parsed = date.fromisoformat(val)
    except ValueError as err:
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT, f"Invalid calendar date '{date_str}': {err}"
        ) from err

    if parsed.year < MIN_ALLOWED_YEAR or parsed.year > MAX_ALLOWED_YEAR:
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT,
            f"{param_name} year {parsed.year} out of range ({MIN_ALLOWED_YEAR}–{MAX_ALLOWED_YEAR}).",
        )
    return parsed


def validate_query_text(query: str | None) -> str | None:
    """Validate and sanitize free-text query string."""
    if not query or not query.strip():
        return None
    clean = query.strip()
    if len(clean) > Limits.MAX_QUERY_LENGTH:
        raise AgentServiceError(
            ErrorCode.LIMIT_EXCEEDED,
            f"Query text exceeds maximum length of {Limits.MAX_QUERY_LENGTH} characters.",
        )
    return clean


def validate_direction_arg(direction: str | None) -> str:
    """Validate direction filter ('debit', 'credit', 'all')."""
    if not direction:
        return "debit"
    clean = direction.strip().lower()
    if clean not in {"debit", "credit", "all"}:
        raise AgentServiceError(
            ErrorCode.INVALID_ARGUMENT,
            f"Invalid direction '{direction}'. Supported: 'debit', 'credit', 'all'.",
        )
    return clean


def validate_amount_arg(amount: float | None, param_name: str = "amount") -> float | None:
    """Validate numeric amount bounds."""
    if amount is None:
        return None
    if amount < 0:
        raise AgentServiceError(ErrorCode.INVALID_ARGUMENT, f"{param_name} cannot be negative.")
    if amount > 1_000_000_000:
        raise AgentServiceError(ErrorCode.LIMIT_EXCEEDED, f"{param_name} exceeds allowable bounds.")
    return float(amount)

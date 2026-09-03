"""Central resource limits and guardrails for agent queries."""

from __future__ import annotations


class Limits:
    """Application-level resource bounds protecting against agent runaway loops."""

    MAX_RESULTS: int = 50
    DEFAULT_RESULTS: int = 10

    MAX_MERCHANT_RECENT: int = 25
    DEFAULT_MERCHANT_RECENT: int = 5

    MAX_HISTORY_MONTHS: int = 24
    DEFAULT_HISTORY_MONTHS: int = 6

    MAX_QUERY_LENGTH: int = 500

    MAX_RECURRING_ITEMS: int = 100
    MAX_CATEGORIES: int = 100

    MAX_RESPONSE_BYTES: int = 256 * 1024  # 256 KB hard response limit

    DB_TIMEOUT_SECONDS: float = 2.0  # 2-second target timeout for SQLite execution

    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_BURST: int = 20

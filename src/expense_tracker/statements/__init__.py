"""Statements package: Credit card statement vault, password strategy engine, and discovery."""

from expense_tracker.statements.discovery import (
    DiscoveredStatementCandidate,
    discover_statement_candidates,
    is_statement_candidate,
)
from expense_tracker.statements.password_engine import (
    AccountProfile,
    generate_candidate_passwords,
    get_statement_adapter,
)
from expense_tracker.statements.service import (
    discover_statements_from_source,
    ingest_candidate,
    unlock_statement_manually,
    upsert_password_profile,
)
from expense_tracker.statements.vault import (
    compute_sha256,
    resolve_statement_paths,
    save_original_statement,
    save_unlocked_statement,
    unlock_pdf,
    validate_pdf,
)

__all__ = [
    "AccountProfile",
    "DiscoveredStatementCandidate",
    "compute_sha256",
    "discover_statement_candidates",
    "discover_statements_from_source",
    "generate_candidate_passwords",
    "get_statement_adapter",
    "ingest_candidate",
    "is_statement_candidate",
    "resolve_statement_paths",
    "save_original_statement",
    "save_unlocked_statement",
    "unlock_pdf",
    "unlock_statement_manually",
    "upsert_password_profile",
    "validate_pdf",
]

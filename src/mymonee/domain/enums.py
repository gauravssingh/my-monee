"""Domain enums for the canonical transaction model."""

from __future__ import annotations

from enum import StrEnum


class Direction(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionType(StrEnum):
    PURCHASE = "purchase"
    REFUND = "refund"
    REVERSAL = "reversal"
    TRANSFER = "transfer"
    INCOME = "income"
    EMI = "emi"
    EMI_INTEREST = "emi_interest"
    FEE = "fee"
    TAX = "tax"
    CASH_WITHDRAWAL = "cash_withdrawal"
    OTHER = "other"
    NOT_A_TRANSACTION = "not_a_transaction"
    REIMBURSED = "reimbursed"


class ClassificationSource(StrEnum):
    RULE = "rule"
    HISTORICAL = "historical"
    AI = "ai"
    USER = "user"
    UNKNOWN = "unknown"


class EmailParseStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    SKIPPED = "skipped"
    ERROR = "error"


class LinkKind(StrEnum):
    REFUND = "refund"
    REVERSAL = "reversal"
    PARTIAL_REFUND = "partial_refund"
    DUPLICATE = "duplicate"
    EMI_COMPONENT = "emi_component"
    TRANSFER = "transfer"
    CC_PAYMENT = "cc_payment"
    REIMBURSEMENT = "reimbursement"


class IngestionRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DataIssueType(StrEnum):
    WRONG_AMOUNT = "wrong_amount"
    WRONG_DATE = "wrong_date"
    WRONG_MERCHANT = "wrong_merchant"
    WRONG_DIRECTION = "wrong_direction"
    NOT_A_TRANSACTION = "not_a_transaction"
    DUPLICATE = "duplicate"
    OTHER = "other"


class DataIssueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"

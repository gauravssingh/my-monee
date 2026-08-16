"""Base classes and canonical dataclasses for statement parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from expense_tracker.statements.extractor import PDFDocumentStructure


@dataclass
class ParsedStatementAccount:
    account_type: str  # "CREDIT_CARD", "BANK_ACCOUNT"
    institution: str
    account_identifier: str | None = None
    masked_identifier: str | None = None
    card_network: str | None = None  # "VISA", "RUPAY", "MASTERCARD"
    account_name: str | None = None
    currency: str = "INR"
    opening_balance: float | None = None
    closing_balance: float | None = None
    credit_limit: float | None = None
    available_limit: float | None = None
    cash_withdrawal_limit: float | None = None
    attribution_confidence: str = "EXACT"  # "EXACT", "INFERRED", "UNKNOWN"


@dataclass
class ParsedStatementSummary:
    previous_balance: float | None = None
    payments: float | None = None
    refunds: float | None = None
    purchases: float | None = None
    cash_withdrawals: float | None = None
    fees: float | None = None
    interest: float | None = None
    other_charges: float | None = None
    total_due: float | None = None
    minimum_due: float | None = None
    statement_date: datetime | None = None
    due_date: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    currency: str = "INR"
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedStatementSection:
    section_type: str  # "SUMMARY", "TRANSACTIONS", "PAYMENTS", "FEES", "EMI", "REWARDS"
    page_start: int
    page_end: int
    source_text: str | None = None


@dataclass
class ParsedStatementTransaction:
    transaction_date: datetime
    description: str
    amount: float  # always positive magnitude
    transaction_type: str = "PURCHASE"  # "PURCHASE", "REFUND", "PAYMENT", "FEE", "INTEREST", "TRANSFER", "OTHER"
    debit_amount: float | None = None
    credit_amount: float | None = None
    transaction_time: str | None = None
    value_date: datetime | None = None
    reference_number: str | None = None
    running_balance: float | None = None
    currency: str = "INR"
    source_page: int = 1
    source_row: int | None = None
    raw_text: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)
    # Attribution to a specific card in a multi-card statement:
    # If the document does not establish attribution (like Scapia), this remains UNKNOWN / None.
    attribution_status: str = "UNKNOWN"  # "EXACT", "UNKNOWN", "INFERRED"
    statement_account_index: int | None = None  # Index into result.accounts if attributed


@dataclass
class ParsedStatementResult:
    parser_name: str
    parser_version: str
    institution: str
    statement_type: str  # "CREDIT_CARD", "BANK_ACCOUNT"
    extraction_strategy: str = "pdf_table"  # "pdf_table", "coordinate_rows", "text_blocks", "hybrid"
    accounts: list[ParsedStatementAccount] = field(default_factory=list)
    summary: ParsedStatementSummary | None = None
    sections: list[ParsedStatementSection] = field(default_factory=list)
    transactions: list[ParsedStatementTransaction] = field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseStatementParser(ABC):
    """Protocol / base class for deterministic PDF statement parsers."""

    name: str = "base"
    version: str = "1.0.0"
    institution: str = "UNKNOWN"
    statement_type: str = "CREDIT_CARD"
    extraction_strategy: str = "pdf_table"  # Default primary extraction strategy

    @abstractmethod
    def can_parse(self, doc_struct: PDFDocumentStructure) -> float:
        """Return confidence score 0.0 - 1.0 indicating if this parser handles the PDF."""
        pass

    @abstractmethod
    def parse(self, doc_struct: PDFDocumentStructure) -> ParsedStatementResult:
        """Parse structured text and tables into canonical statement model."""
        pass


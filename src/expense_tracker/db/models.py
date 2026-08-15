"""SQLAlchemy models — canonical schema with JSON extensibility."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    expense_type: Mapped[str] = mapped_column(String(32), default="discretionary")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subcategories: Mapped[list[Subcategory]] = relationship(back_populates="category")


class Subcategory(Base):
    __tablename__ = "subcategories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    category: Mapped[Category] = relationship(back_populates="subcategories")

    __table_args__ = (UniqueConstraint("category_id", "slug", name="uq_subcategory_slug"),)


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_name: Mapped[str | None] = mapped_column(String(255))
    normalized_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category_hint: Mapped[str | None] = mapped_column(String(100))
    merchant_type: Mapped[str | None] = mapped_column(String(32))
    default_category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    default_subcategory_id: Mapped[str | None] = mapped_column(ForeignKey("subcategories.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    aliases: Mapped[list[MerchantAlias]] = relationship(back_populates="merchant")


class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    alias_raw: Mapped[str] = mapped_column(String(512), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="learned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="aliases")

    __table_args__ = (UniqueConstraint("alias_normalized", name="uq_merchant_alias_norm"),)


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # Gmail message id
    thread_id: Mapped[str | None] = mapped_column(String(128))
    sender: Mapped[str | None] = mapped_column(String(512))
    subject: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    label_ids_json: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text)
    provider_hint: Mapped[str | None] = mapped_column(String(100))
    headers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text_path: Mapped[str | None] = mapped_column(Text)  # opt-in raw storage
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    financial_event_id: Mapped[str | None] = mapped_column(ForeignKey("financial_events.id"))
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    source_email_id: Mapped[str | None] = mapped_column(ForeignKey("emails.id"))
    source_thread_id: Mapped[str | None] = mapped_column(String(128))
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)

    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    posted_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), default="other")

    merchant_raw: Mapped[str | None] = mapped_column(String(512))
    merchant_normalized: Mapped[str | None] = mapped_column(String(512))
    merchant_entity_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id"))
    merchant_category: Mapped[str | None] = mapped_column(String(100))

    payment_method: Mapped[str | None] = mapped_column(String(100))
    account: Mapped[str | None] = mapped_column(String(100))
    card: Mapped[str | None] = mapped_column(String(32))
    upi_id: Mapped[str | None] = mapped_column(String(255))
    reference_number: Mapped[str | None] = mapped_column(String(128))
    bank_reference: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))

    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    subcategory_id: Mapped[str | None] = mapped_column(ForeignKey("subcategories.id"))
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classification_source: Mapped[str] = mapped_column(String(32), default="unknown")
    classification_signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    parent_transaction_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id"))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False)
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    excludes_from_spending: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    raw_email_reference: Mapped[str | None] = mapped_column(Text)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    category: Mapped[Category | None] = relationship(foreign_keys=[category_id])
    subcategory: Mapped[Subcategory | None] = relationship(foreign_keys=[subcategory_id])

    __table_args__ = (
        Index(
            "ix_tx_source_email_ref",
            "source",
            "source_email_id",
            "reference_number",
        ),
        Index("ix_tx_date", "transaction_date"),
        Index("ix_tx_needs_review", "needs_review"),
        UniqueConstraint(
            "source",
            "fingerprint",
            name="uq_tx_source_fingerprint",
        ),
    )


class TransactionLink(Base):
    __tablename__ = "transaction_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    from_transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    to_transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "from_transaction_id",
            "to_transaction_id",
            "kind",
            name="uq_tx_link",
        ),
    )


class ClassificationRule(Base):
    __tablename__ = "classification_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[int] = mapped_column(default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # match fields — any set fields participate in matching
    merchant_normalized: Mapped[str | None] = mapped_column(String(512))
    merchant_entity_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id"))
    upi_id: Mapped[str | None] = mapped_column(String(255))
    match_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), nullable=False)
    subcategory_id: Mapped[str | None] = mapped_column(ForeignKey("subcategories.id"))
    source: Mapped[str] = mapped_column(String(32), default="user")  # user | learned | system
    hit_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ClassificationCorrection(Base):
    """Audit trail of every user-driven category correction.

    Captures the label *before* it was overwritten so mispredictions can be
    replayed as supervised training pairs (previous vs. corrected label)
    instead of being lost when the transaction row is updated in place.
    """

    __tablename__ = "classification_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)

    previous_category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    previous_subcategory_id: Mapped[str | None] = mapped_column(ForeignKey("subcategories.id"))
    previous_classification_source: Mapped[str | None] = mapped_column(String(32))
    previous_classification_confidence: Mapped[float | None] = mapped_column(Float)
    previous_classification_signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    new_category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    new_subcategory_id: Mapped[str | None] = mapped_column(ForeignKey("subcategories.id"))

    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_correction_transaction", "transaction_id"),)


class DataIssueFlag(Base):
    """User-reported data-extraction problem on a transaction.

    Purely additive: flagging never mutates the transaction. `source` and
    `merchant_normalized` are denormalized at flag time so flags can be
    grouped by likely root cause (parser/provider, merchant) and triaged in
    bulk instead of being fixed one email at a time.
    """

    __tablename__ = "data_issue_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)

    issue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(64))
    reported_value: Mapped[str | None] = mapped_column(Text)
    suggested_value: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")

    source: Mapped[str | None] = mapped_column(String(100))
    merchant_normalized: Mapped[str | None] = mapped_column(String(512))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_note: Mapped[str | None] = mapped_column(Text)

    transaction: Mapped[Transaction] = relationship()

    __table_args__ = (
        Index("ix_data_issue_status", "status"),
        Index("ix_data_issue_type", "issue_type"),
        Index("ix_data_issue_source", "source"),
    )


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running")
    emails_discovered: Mapped[int] = mapped_column(default=0)
    emails_processed: Mapped[int] = mapped_column(default=0)
    transactions_extracted: Mapped[int] = mapped_column(default=0)
    transactions_rejected: Mapped[int] = mapped_column(default=0)
    transactions_duplicated: Mapped[int] = mapped_column(default=0)
    transactions_classified: Mapped[int] = mapped_column(default=0)
    transactions_needing_review: Mapped[int] = mapped_column(default=0)
    parsing_errors: Mapped[int] = mapped_column(default=0)
    auth_errors: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    level: Mapped[str] = mapped_column(String(16), default="info")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    email_id: Mapped[str | None] = mapped_column(String(128))
    transaction_id: Mapped[str | None] = mapped_column(String(36))
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )




class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_type: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(2))
    logo_reference: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"))
    account_type: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    account_number_masked: Mapped[str | None] = mapped_column(String(64))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    upi_identifier_masked: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    is_asset: Mapped[bool] = mapped_column(Boolean, default=True)
    is_liability: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_limit: Mapped[float | None] = mapped_column(Numeric(18, 4))
    opening_balance: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    opening_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_balance: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FinancialEvent(Base):
    __tablename__ = "financial_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="manual")
    source_reference: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Posting(Base):
    __tablename__ = "postings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("financial_events.id"), nullable=False)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False) # debit/credit
    posting_type: Mapped[str] = mapped_column(String(32), nullable=False) # expense, liability_decrease, asset_decrease, etc
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)


class IncomeSource(Base):
    __tablename__ = "income_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    expected_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    frequency: Mapped[str] = mapped_column(String(32)) # monthly, weekly, etc
    next_expected_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id"))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))

    expected_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    amount_variance: Mapped[float | None] = mapped_column(Float)

    frequency: Mapped[str] = mapped_column(String(32))
    interval_days: Mapped[int | None] = mapped_column(default=30)
    expected_day: Mapped[int | None] = mapped_column(Integer)
    date_tolerance_days: Mapped[int | None] = mapped_column(Integer, default=4)

    next_expected_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="detected") # detected, active, paused, cancelled, ignored

    matching_rules_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TransactionRecurringLink(Base):
    __tablename__ = "transaction_recurring_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    recurring_transaction_id: Mapped[str] = mapped_column(ForeignKey("recurring_transactions.id"), nullable=False)
    match_type: Mapped[str] = mapped_column(String(32), default="auto")  # auto, manual
    confidence: Mapped[float | None] = mapped_column(Float)
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "recurring_transaction_id",
            name="uq_tx_recurring_link",
        ),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recurring_transaction_id: Mapped[str] = mapped_column(ForeignKey("recurring_transactions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    annual_cost: Mapped[float | None] = mapped_column(Numeric(18, 4))
    
    last_paid_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_paid_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    next_expected_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    
    status: Mapped[str] = mapped_column(String(32), default="detected") # detected, active, paused, cancelled, ignored
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recurring_transaction_id: Mapped[str] = mapped_column(ForeignKey("recurring_transactions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    bill_type: Mapped[str] = mapped_column(String(32), default="OTHER") # UTILITY, SUBSCRIPTION, INSURANCE, RENT, LOAN, CREDIT_CARD, OTHER
    autopay: Mapped[bool] = mapped_column(Boolean, default=False)
    
    minimum_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    average_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    median_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    max_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    amount_stddev: Mapped[float | None] = mapped_column(Numeric(18, 4))
    
    last_paid_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_paid_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    next_expected_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    
    status: Mapped[str] = mapped_column(String(32), default="detected") # detected, active, paused, cancelled, ignored
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    period: Mapped[str] = mapped_column(String(32), default="monthly")
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    rollover: Mapped[bool] = mapped_column(Boolean, default=False)
    current_spent: Mapped[float] = mapped_column(Numeric(18, 4), default=0)


@event.listens_for(Transaction, "before_update")
def _touch_transaction_updated_at(mapper, connection, target: Transaction) -> None:  # noqa: ARG001
    target.updated_at = utcnow()

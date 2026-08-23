from mymonee.db.models import Base

new_models = """

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
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id"))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    expected_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    frequency: Mapped[str] = mapped_column(String(32))
    interval_days: Mapped[int | None] = mapped_column(default=30)
    next_expected_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amount_variance: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="active")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    billing_frequency: Mapped[str] = mapped_column(String(32))
    next_billing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    annual_cost: Mapped[float | None] = mapped_column(Numeric(18, 4))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    status: Mapped[str] = mapped_column(String(32), default="active")
    first_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id"))
    expected_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    minimum_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frequency: Mapped[str] = mapped_column(String(32))
    autopay: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    period: Mapped[str] = mapped_column(String(32), default="monthly")
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    rollover: Mapped[bool] = mapped_column(Boolean, default=False)
    current_spent: Mapped[float] = mapped_column(Numeric(18, 4), default=0)

"""

import sys

def main():
    target_file = "/Users/gauravsingh/projects/expense-tracker/src/mymonee/db/models.py"
    with open(target_file, "r") as f:
        content = f.read()

    # insert the new models right before the `@event.listens_for(Transaction, "before_update")`
    idx = content.find('@event.listens_for(Transaction, "before_update")')
    if idx == -1:
        print("Could not find the insertion point.")
        sys.exit(1)
        
    new_content = content[:idx] + new_models + "\n" + content[idx:]
    with open(target_file, "w") as f:
        f.write(new_content)
        
    print("New models appended successfully.")

if __name__ == "__main__":
    main()

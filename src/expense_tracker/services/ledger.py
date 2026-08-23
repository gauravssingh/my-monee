"""Canonical Ledger domain service — double-entry invariant verification and account balance projections."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from expense_tracker.db.models import Account, FinancialEvent, Posting, Transaction


@dataclass(frozen=True)
class AccountBalanceProjection:
    account_id: str
    name: str
    account_type: str
    is_asset: bool
    is_liability: bool
    normal_balance: str  # "debit" for assets, "credit" for liabilities
    opening_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    current_balance: Decimal


@dataclass(frozen=True)
class LedgerSummary:
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    accounts: list[AccountBalanceProjection]


def derive_account_balance(
    *,
    is_asset: bool,
    is_liability: bool,
    opening_balance: Decimal,
    total_debits: Decimal,
    total_credits: Decimal,
) -> Decimal:
    """Derive account balance from normal balance semantics.
    
    - Assets: Debit normal -> Opening + (Debits - Credits)
    - Liabilities: Credit normal -> Opening + (Credits - Debits)
    """
    if is_liability:
        # Normal credit balance (e.g. credit card debt outstanding)
        # Note: in banking alerts, user spending on card is a debit alert, which increases card liability.
        return opening_balance + (total_debits - total_credits)
    else:
        # Normal debit balance (assets: bank, cash, wallet)
        # In banking alerts, income is credit (+), spending is debit (-)
        return opening_balance + (total_credits - total_debits)


def calculate_ledger_balances(session: Session) -> LedgerSummary:
    """Calculate canonical balance projections from ledger postings."""
    accounts = session.scalars(select(Account).order_by(Account.name)).all()

    # Aggregate postings by account_id and direction
    postings_query = session.execute(
        select(
            Posting.account_id,
            Posting.direction,
            func.coalesce(func.sum(Posting.amount), 0),
        )
        .where(Posting.account_id.isnot(None))
        .group_by(Posting.account_id, Posting.direction)
    ).all()

    totals: dict[str, dict[str, Decimal]] = {}
    for acc_id, direction, amt in postings_query:
        if acc_id not in totals:
            totals[acc_id] = {"debit": Decimal(0), "credit": Decimal(0)}
        dir_key = str(direction).lower()
        totals[acc_id][dir_key] = Decimal(str(amt))

    projections: list[AccountBalanceProjection] = []
    total_assets = Decimal(0)
    total_liabilities = Decimal(0)

    for acc in accounts:
        acc_totals = totals.get(acc.id, {"debit": Decimal(0), "credit": Decimal(0)})
        debits = acc_totals["debit"]
        credits = acc_totals["credit"]
        opening = Decimal(str(acc.opening_balance or 0))

        normal = "credit" if acc.is_liability else "debit"
        current_bal = derive_account_balance(
            is_asset=acc.is_asset,
            is_liability=acc.is_liability,
            opening_balance=opening,
            total_debits=debits,
            total_credits=credits,
        )

        proj = AccountBalanceProjection(
            account_id=acc.id,
            name=acc.name,
            account_type=acc.account_type,
            is_asset=acc.is_asset,
            is_liability=acc.is_liability,
            normal_balance=normal,
            opening_balance=opening,
            total_debits=debits,
            total_credits=credits,
            current_balance=current_bal,
        )
        projections.append(proj)

        if acc.is_asset:
            total_assets += current_bal
        elif acc.is_liability:
            total_liabilities += current_bal

    net_worth = total_assets - total_liabilities

    return LedgerSummary(
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=net_worth,
        accounts=projections,
    )


def verify_event_double_entry(session: Session, event_id: str) -> tuple[bool, Decimal, Decimal]:
    """Verify that a specific FinancialEvent has balanced postings (sum debits == sum credits)."""
    postings = session.scalars(select(Posting).where(Posting.event_id == event_id)).all()
    if not postings:
        return True, Decimal(0), Decimal(0)

    sum_debits = sum((Decimal(str(p.amount)) for p in postings if p.direction == "debit"), Decimal(0))
    sum_credits = sum((Decimal(str(p.amount)) for p in postings if p.direction == "credit"), Decimal(0))

    is_balanced = sum_debits == sum_credits
    return is_balanced, sum_debits, sum_credits

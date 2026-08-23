"""Financial onboarding and initial configuration wizard service."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from expense_tracker.db.models import (
    Account,
    AppSetting,
    Category,
    IncomeSource,
    RecurringTransaction,
    Transaction,
    utcnow,
)
from expense_tracker.services.reconciliation import run_full_reconciliation

logger = logging.getLogger(__name__)


def get_onboarding_status(session: Session) -> dict[str, Any]:
    """Check whether onboarding has been completed and return profile summary."""
    setting = session.get(AppSetting, "onboarding_completed")
    completed = bool(setting.value_json) if setting else False

    account_count = session.scalar(select(func.count()).select_from(Account)) or 0
    tx_count = session.scalar(select(func.count()).select_from(Transaction)) or 0
    recurring_count = session.scalar(select(func.count()).select_from(RecurringTransaction)) or 0
    income_count = session.scalar(select(func.count()).select_from(IncomeSource)) or 0

    return {
        "completed": completed,
        "accounts_configured": account_count,
        "transactions_ingested": tx_count,
        "recurring_configured": recurring_count,
        "income_sources_configured": income_count,
    }


def discover_onboarding_entities(session: Session) -> dict[str, Any]:
    """Scan existing database and transactions to discover candidate accounts,
    income streams, and recurring obligations for the onboarding wizard."""
    # 1. Accounts discovery
    accounts = session.scalars(select(Account).order_by(Account.name.asc())).all()
    account_items = []
    for acc in accounts:
        account_items.append({
            "id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type,
            "card_last4": acc.card_last4,
            "account_number_masked": acc.account_number_masked,
            "is_asset": acc.is_asset,
            "is_liability": acc.is_liability,
        })

    # 2. Income stream discovery
    # Look for credit transactions >= 10,000 or salary descriptions
    income_candidates = session.scalars(
        select(Transaction)
        .where(
            Transaction.direction == "credit",
            Transaction.excludes_from_spending == True,
            Transaction.amount >= 5000,
        )
        .order_by(Transaction.transaction_date.desc())
    ).all()

    discovered_income: list[dict[str, Any]] = []
    seen_income_sources = set()
    for tx in income_candidates:
        merchant = tx.merchant_normalized or tx.merchant_raw or tx.description or "Primary Salary"
        if merchant in seen_income_sources:
            continue
        seen_income_sources.add(merchant)
        discovered_income.append({
            "name": merchant,
            "amount": float(tx.amount),
            "currency": tx.currency,
            "account": tx.account,
            "last_date": tx.transaction_date.strftime("%Y-%m-%d") if tx.transaction_date else None,
            "expected_day": tx.transaction_date.day if tx.transaction_date else 1,
        })

    # 3. Recurring subscriptions & bills discovery
    recurring_rows = session.scalars(select(RecurringTransaction)).all()
    discovered_recurring: list[dict[str, Any]] = []
    for r in recurring_rows:
        discovered_recurring.append({
            "id": r.id,
            "name": r.name,
            "expected_amount": float(r.expected_amount) if r.expected_amount else 0.0,
            "frequency": r.frequency or "monthly",
            "expected_day": r.expected_day or 1,
            "status": r.status or "active",
        })

    # If no recurring configured yet, discover common subscriptions from transactions
    if not discovered_recurring:
        candidate_subs = session.scalars(
            select(Transaction)
            .where(
                Transaction.direction == "debit",
                Transaction.merchant_normalized.is_not(None),
            )
            .group_by(Transaction.merchant_normalized)
            .having(func.count(Transaction.id) >= 2)
        ).all()
        for tx in candidate_subs[:6]:
            discovered_recurring.append({
                "id": None,
                "name": tx.merchant_normalized,
                "expected_amount": float(tx.amount),
                "frequency": "monthly",
                "expected_day": tx.transaction_date.day if tx.transaction_date else 1,
                "status": "detected",
            })

    return {
        "accounts": account_items,
        "income_sources": discovered_income[:4],
        "recurring": discovered_recurring,
    }


def complete_onboarding(
    session: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply configurations from the onboarding wizard and mark setup as complete."""
    # 1. Income setup
    salary_cfg = payload.get("primary_salary")
    if salary_cfg and salary_cfg.get("name"):
        existing_income = session.scalars(
            select(IncomeSource).where(IncomeSource.name == salary_cfg["name"])
        ).first()
        if not existing_income:
            income_cat = session.scalar(select(Category).where(Category.slug == "income"))
            existing_income = IncomeSource(
                name=salary_cfg["name"],
                category_id=income_cat.id if income_cat else None,
                expected_amount=float(salary_cfg.get("expected_amount") or 0.0),
                frequency=salary_cfg.get("frequency", "monthly"),
                confidence=1.0,
            )
            session.add(existing_income)

    # 2. Recurring confirmations
    recurring_list = payload.get("recurring_items", [])
    for rec in recurring_list:
        if not rec.get("name"):
            continue
        existing_rec = session.scalars(
            select(RecurringTransaction).where(RecurringTransaction.name == rec["name"])
        ).first()
        if not existing_rec:
            session.add(RecurringTransaction(
                name=rec["name"],
                expected_amount=float(rec.get("expected_amount") or 0.0),
                frequency=rec.get("frequency", "monthly"),
                expected_day=int(rec.get("expected_day") or 1),
                status="active",
                confidence=1.0,
            ))

    # 3. Mark Onboarding completed in AppSettings
    setting = session.get(AppSetting, "onboarding_completed")
    if not setting:
        setting = AppSetting(key="onboarding_completed", value_json=True)
        session.add(setting)
    else:
        setting.value_json = True
        setting.updated_at = utcnow()

    # 4. Run baseline ledger reconciliation
    reconciliation_summary = run_full_reconciliation(session)

    session.commit()
    logger.info("Financial onboarding completed successfully.")
    return {
        "success": True,
        "completed": True,
        "reconciliation": reconciliation_summary,
    }


def reset_onboarding(session: Session) -> dict[str, Any]:
    """Reset onboarding flag to allow re-running the configuration wizard."""
    setting = session.get(AppSetting, "onboarding_completed")
    if setting:
        setting.value_json = False
        setting.updated_at = utcnow()
        session.commit()
    return {"success": True, "completed": False}

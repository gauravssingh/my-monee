"""Financial onboarding and initial configuration wizard service."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mymonee.config import Settings
from mymonee.db.models import (
    Account,
    AppSetting,
    Category,
    Email,
    IncomeSource,
    RecurringTransaction,
    Transaction,
    utcnow,
)
from mymonee.ingestion.gmail.oauth import is_connected
from mymonee.services.auth import is_auth_configured, set_master_pin
from mymonee.services.reconciliation import run_full_reconciliation

logger = logging.getLogger(__name__)

KNOWN_INSTITUTION_PATTERNS = [
    {"name": "Axis Bank", "type": "BANK", "domain": "axisbank.com", "icon": "🏦", "keywords": ["axis", "axisbank"]},
    {"name": "HDFC Bank", "type": "BANK", "domain": "hdfcbank.net", "icon": "🏦", "keywords": ["hdfc", "hdfcbank"]},
    {"name": "ICICI Bank", "type": "BANK", "domain": "icicibank.com", "icon": "🏦", "keywords": ["icici", "icicibank"]},
    {"name": "State Bank of India", "type": "BANK", "domain": "sbi.co.in", "icon": "🏦", "keywords": ["sbi", "state bank"]},
    {"name": "Kotak Mahindra Bank", "type": "BANK", "domain": "kotak.com", "icon": "🏦", "keywords": ["kotak"]},
    {"name": "Scapia Federal", "type": "CREDIT_CARD", "domain": "scapia.cards", "icon": "💳", "keywords": ["scapia"]},
    {"name": "HDFC Credit Card", "type": "CREDIT_CARD", "domain": "hdfcbank.net", "icon": "💳", "keywords": ["hdfc credit card", "infinia", "regalia", "millennia"]},
    {"name": "PhonePe", "type": "WALLET", "domain": "phonepe.com", "icon": "📱", "keywords": ["phonepe", "ybl", "ibl"]},
    {"name": "Google Pay", "type": "WALLET", "domain": "google.com", "icon": "📱", "keywords": ["google pay", "okaxis", "okhdfcbank", "okicici"]},
    {"name": "Amazon Pay", "type": "WALLET", "domain": "amazon.in", "icon": "🛒", "keywords": ["amazon pay", "apl"]},
]


def get_onboarding_state(session: Session, settings: Settings) -> dict[str, Any]:
    """Return complete state for the 6-step onboarding wizard."""
    setting = session.get(AppSetting, "onboarding_completed")
    completed = bool(setting.value_json) if setting else False

    progress_setting = session.get(AppSetting, "onboarding_progress")
    progress = progress_setting.value_json if progress_setting else {}

    auth_ready = is_auth_configured(session)
    gmail_conn = is_connected(settings)

    currency_setting = session.get(AppSetting, "default_currency")
    currency = currency_setting.value_json if currency_setting else settings.dashboard.default_currency

    locale_setting = session.get(AppSetting, "locale")
    locale = locale_setting.value_json if locale_setting else "en-IN"

    discovered = discover_onboarding_entities(session)

    account_count = session.scalar(select(func.count()).select_from(Account)) or 0
    tx_count = session.scalar(select(func.count()).select_from(Transaction)) or 0
    review_count = session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.needs_review == True)
    ) or 0

    return {
        "completed": completed,
        "current_step": progress.get("step", 1 if not auth_ready else (2 if not completed else 6)),
        "auth_configured": auth_ready,
        "gmail_connected": gmail_conn,
        "currency": currency,
        "locale": locale,
        "progress": progress,
        "discovered": discovered,
        "metrics": {
            "accounts_configured": account_count,
            "transactions_ingested": tx_count,
            "needs_review_count": review_count,
        },
    }


def get_onboarding_status(session: Session) -> dict[str, Any]:
    """Compatibility check whether onboarding has been completed."""
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


def fast_discovery_scan(session: Session) -> dict[str, Any]:
    """Scan raw evidence and email headers to detect institutions and accounts."""
    # 1. Inspect recent emails
    email_rows = session.scalars(
        select(Email).order_by(Email.received_at.desc()).limit(150)
    ).all()

    found_institutions = []
    seen_inst_names = set()

    for em in email_rows:
        sender_lower = (em.sender or "").lower()
        subj_lower = (em.subject or "").lower()

        for inst in KNOWN_INSTITUTION_PATTERNS:
            if inst["name"] in seen_inst_names:
                continue
            if inst["domain"] in sender_lower or any(kw in subj_lower for kw in inst["keywords"]):
                seen_inst_names.add(inst["name"])
                found_institutions.append({
                    "name": inst["name"],
                    "type": inst["type"],
                    "icon": inst["icon"],
                    "status": "detected",
                    "sample_subject": em.subject[:60] if em.subject else None,
                })

    # If no institutions discovered from emails, provide standard starter suggestions
    if not found_institutions:
        found_institutions = [
            {"name": "Primary Bank Account", "type": "BANK", "icon": "🏦", "status": "suggested"},
            {"name": "Primary Credit Card", "type": "CREDIT_CARD", "icon": "💳", "status": "suggested"},
            {"name": "UPI / Mobile Wallet", "type": "WALLET", "icon": "📱", "status": "suggested"},
        ]

    return {
        "institutions": found_institutions,
        "emails_scanned": len(email_rows),
    }


def discover_onboarding_entities(session: Session) -> dict[str, Any]:
    """Scan existing database and transactions to discover candidate accounts,
    income streams, and recurring obligations for the onboarding wizard."""
    # 1. Accounts discovery
    accounts = session.scalars(select(Account).order_by(Account.name.asc())).all()
    account_items = []
    for acc in accounts:
        payment_acc_id = (acc.metadata_json or {}).get("payment_account_id")
        account_items.append({
            "id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type,
            "card_last4": acc.card_last4,
            "account_number_masked": acc.account_number_masked,
            "is_asset": acc.is_asset,
            "is_liability": acc.is_liability,
            "opening_balance": float(acc.opening_balance or 0),
            "payment_account_id": payment_acc_id,
        })

    # 2. Income stream discovery
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


def save_onboarding_step(
    session: Session,
    step: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Save progress for a specific onboarding step."""
    progress_setting = session.get(AppSetting, "onboarding_progress")
    progress = progress_setting.value_json if progress_setting else {}
    progress[f"step_{step}"] = payload
    progress["step"] = max(progress.get("step", 1), step + 1)

    if not progress_setting:
        session.add(AppSetting(key="onboarding_progress", value_json=progress))
    else:
        progress_setting.value_json = progress
        progress_setting.updated_at = utcnow()

    # Step-specific actions
    token = None
    if step == 1 and "password" in payload:
        token = set_master_pin(session, payload["password"])

    elif step == 2:
        if "currency" in payload:
            c_set = session.get(AppSetting, "default_currency")
            if not c_set:
                session.add(AppSetting(key="default_currency", value_json=payload["currency"]))
            else:
                c_set.value_json = payload["currency"]
                c_set.updated_at = utcnow()

        if "locale" in payload:
            l_set = session.get(AppSetting, "locale")
            if not l_set:
                session.add(AppSetting(key="locale", value_json=payload["locale"]))
            else:
                l_set.value_json = payload["locale"]
                l_set.updated_at = utcnow()

    elif step == 5 and "accounts" in payload:
        # Upsert accounts and relationships
        for acc_data in payload.get("accounts", []):
            acc_id = acc_data.get("id")
            account = session.get(Account, acc_id) if acc_id else None
            if not account:
                account = Account(
                    name=acc_data.get("name", "Account"),
                    account_type=acc_data.get("account_type", "bank"),
                    currency=acc_data.get("currency", "INR"),
                    is_asset=acc_data.get("is_asset", True),
                    is_liability=acc_data.get("is_liability", False),
                    opening_balance=float(acc_data.get("opening_balance") or 0),
                    metadata_json={
                        "payment_account_id": acc_data.get("payment_account_id"),
                        "auto_identify_bill_payments": acc_data.get("auto_identify_bill_payments", True),
                    },
                )
                session.add(account)
            else:
                account.name = acc_data.get("name", account.name)
                account.account_type = acc_data.get("account_type", account.account_type)
                account.is_asset = acc_data.get("is_asset", account.is_asset)
                account.is_liability = acc_data.get("is_liability", account.is_liability)
                account.opening_balance = float(acc_data.get("opening_balance") or account.opening_balance)
                meta = account.metadata_json or {}
                if "payment_account_id" in acc_data:
                    meta["payment_account_id"] = acc_data["payment_account_id"]
                if "auto_identify_bill_payments" in acc_data:
                    meta["auto_identify_bill_payments"] = acc_data["auto_identify_bill_payments"]
                account.metadata_json = meta
                account.updated_at = utcnow()

    session.commit()
    return {"success": True, "step": step, "next_step": progress["step"], "token": token}


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

    # 5. Gather summary calibration counts
    account_count = session.scalar(select(func.count()).select_from(Account)) or 0
    tx_count = session.scalar(select(func.count()).select_from(Transaction)) or 0
    recurring_count = session.scalar(select(func.count()).select_from(RecurringTransaction)) or 0
    review_count = session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.needs_review == True)
    ) or 0

    session.commit()
    logger.info("Financial onboarding completed successfully.")
    return {
        "success": True,
        "completed": True,
        "reconciliation": reconciliation_summary,
        "calibration": {
            "accounts_configured": account_count,
            "transactions_ingested": tx_count,
            "recurring_configured": recurring_count,
            "needs_review_count": review_count,
        },
    }


def reset_onboarding(session: Session) -> dict[str, Any]:
    """Reset onboarding flag to allow re-running the configuration wizard."""
    setting = session.get(AppSetting, "onboarding_completed")
    if setting:
        setting.value_json = False
        setting.updated_at = utcnow()

    prog_setting = session.get(AppSetting, "onboarding_progress")
    if prog_setting:
        prog_setting.value_json = {"step": 1}
        prog_setting.updated_at = utcnow()

    session.commit()
    return {"success": True, "completed": False}


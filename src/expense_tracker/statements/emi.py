"""EMI detection, grouping, and ledger import logic for credit card statements."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from expense_tracker.classification.enrichment import resolve_category_ids
from expense_tracker.db.models import (
    CreditCardStatement,
    StatementTransaction,
    Transaction,
    new_id,
)

logger = logging.getLogger(__name__)

# Regex for Axis / standard Indian credit card EMI narrations:
# e.g., "EMI PRINCIPAL - 7/9, REF# 68265776 MEDICAL"
# e.g., "EMI INTEREST - 7/9, REF# 68265776 MEDICAL"
# e.g., "EMI PRINCIPAL - 1/3 REF# 123456"
EMI_REGEX = re.compile(
    r"EMI\s+(PRINCIPAL|INTEREST)\s*-\s*(\d+)/(\d+)(?:,?\s*REF#?\s*([A-Za-z0-9]+))?(?:\s+(.*))?",
    re.IGNORECASE,
)


def parse_emi_details(description: str) -> dict[str, Any] | None:
    """Extract installment index, total tenure, ref number, and merchant tag from EMI text."""
    if not description:
        return None
    match = EMI_REGEX.search(description)
    if not match:
        return None

    emi_type = match.group(1).upper()
    installment = int(match.group(2))
    tenure = int(match.group(3))
    ref_id = match.group(4) or ""
    merchant = (match.group(5) or "").strip()

    return {
        "type": emi_type,
        "installment": installment,
        "tenure": tenure,
        "ref_id": ref_id,
        "merchant": merchant,
    }


def categorize_statement_line_item(
    description: str, amount: float, credit_amount: float | None = None
) -> tuple[str, str | None, str, str]:
    """Return (category_slug, subcategory_slug, direction, merchant_normalized)."""
    desc_upper = description.upper().strip()
    direction = "inflow" if credit_amount and credit_amount > 0 else "outflow"

    # 1. EMI Interest
    if "EMI INTEREST" in desc_upper:
        emi_info = parse_emi_details(description)
        merchant_name = f"EMI Interest ({emi_info['merchant']})" if emi_info and emi_info["merchant"] else "EMI Interest"
        return "fees-interest", "emi-interest", direction, merchant_name

    # 2. GST on EMI / Bank Charges
    if desc_upper == "GST" or desc_upper.startswith("GST ") or "GST ON" in desc_upper:
        return "fees-interest", "gst", direction, "GST on Bank Charges"

    # 3. EMI Principal
    if "EMI PRINCIPAL" in desc_upper:
        emi_info = parse_emi_details(description)
        merchant_tag = emi_info["merchant"] if emi_info else ""
        if "MEDICAL" in merchant_tag or "HEALTH" in merchant_tag or "HOSPITAL" in merchant_tag:
            return "healthcare", "clinic", direction, f"Medical EMI ({emi_info['installment']}/{emi_info['tenure']})"
        return "fees-interest", "bank-fee", direction, f"EMI Principal ({emi_info['installment']}/{emi_info['tenure']})" if emi_info else "EMI Principal"

    # 4. Bank charges & fees
    if "ANNUAL FEE" in desc_upper or "RENEWAL FEE" in desc_upper or "LATE FEE" in desc_upper:
        return "fees-interest", "bank-fee", direction, "Bank Annual Fee"

    # 5. Generic fallback
    return "other", "uncategorized", direction, description.strip()


def import_statement_transaction_to_ledger(
    session: Session,
    statement: CreditCardStatement,
    stmt_tx: StatementTransaction,
) -> Transaction:
    """Create a verified ledger transaction from a statement line item and mark as matched."""
    cat_slug, sub_slug, direction, merchant_norm = categorize_statement_line_item(
        stmt_tx.description, float(stmt_tx.amount), float(stmt_tx.credit_amount or 0)
    )
    cat_id, sub_id = resolve_category_ids(session, category_slug=cat_slug, subcategory_slug=sub_slug)

    tx = Transaction(
        id=new_id(),
        source="statement",
        transaction_date=stmt_tx.transaction_date,
        amount=float(stmt_tx.amount),
        currency=stmt_tx.currency or "INR",
        direction=direction,
        transaction_type="debit" if direction == "outflow" else "credit",
        merchant_raw=stmt_tx.description,
        merchant_normalized=merchant_norm,
        account=statement.account.name if statement.account else statement.issuer,
        card=statement.card_last4 or (statement.account.card_last4 if statement.account else None),
        reference_number=stmt_tx.reference_number,
        description=stmt_tx.description,
        category_id=cat_id,
        subcategory_id=sub_id,
        classification_confidence=1.0,
        classification_source="statement_import",
        user_verified=True,
    )
    session.add(tx)
    session.flush()

    # Link statement transaction
    stmt_tx.matched_transaction_id = tx.id
    stmt_tx.match_status = "MATCHED"
    stmt_tx.match_confidence = 1.0
    stmt_tx.match_reason = f"Imported to ledger as {merchant_norm}"

    session.commit()
    return tx


def group_emi_transactions(
    statement_transactions: list[StatementTransaction],
) -> list[dict[str, Any]]:
    """Group related EMI Principal, Interest, and GST entries into logical EMI bundles."""
    emi_bundles: dict[str, dict[str, Any]] = {}

    for tx in statement_transactions:
        emi_info = parse_emi_details(tx.description)
        if emi_info:
            date_key = tx.transaction_date.strftime("%Y-%m-%d")
            ref_key = emi_info["ref_id"] or date_key
            group_key = f"{date_key}_{ref_key}"

            if group_key not in emi_bundles:
                emi_bundles[group_key] = {
                    "date": date_key,
                    "ref_id": emi_info["ref_id"],
                    "merchant": emi_info["merchant"],
                    "installment": emi_info["installment"],
                    "tenure": emi_info["tenure"],
                    "principal_tx": None,
                    "interest_tx": None,
                    "gst_tx": None,
                    "total_amount": 0.0,
                    "transaction_ids": [],
                }

            bundle = emi_bundles[group_key]
            if emi_info["type"] == "PRINCIPAL":
                bundle["principal_tx"] = tx
            elif emi_info["type"] == "INTEREST":
                bundle["interest_tx"] = tx

            bundle["total_amount"] += float(tx.amount)
            bundle["transaction_ids"].append(tx.id)

    # Now associate GST line items on the same date
    for tx in statement_transactions:
        desc_upper = tx.description.upper().strip()
        if desc_upper == "GST" or desc_upper.startswith("GST "):
            date_key = tx.transaction_date.strftime("%Y-%m-%d")
            # Find matching EMI bundle on this date
            for key, bundle in emi_bundles.items():
                if bundle["date"] == date_key and bundle["gst_tx"] is None:
                    # Check if GST is ~18% of interest
                    interest_amt = float(bundle["interest_tx"].amount) if bundle["interest_tx"] else 0.0
                    gst_amt = float(tx.amount)
                    if interest_amt > 0 and abs(gst_amt - (interest_amt * 0.18)) < 1.0:
                        bundle["gst_tx"] = tx
                        bundle["total_amount"] += gst_amt
                        bundle["transaction_ids"].append(tx.id)
                        break

    return list(emi_bundles.values())

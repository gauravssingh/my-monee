"""Statement transaction reconciliation and matching engine."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mymonee.db.models import CreditCardStatement, StatementTransaction, Transaction
from mymonee.merchants.normalize import normalize_merchant

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    status: str  # "MATCHED", "POSSIBLE_MATCH", "UNMATCHED", "LIABILITY_PAYMENT"
    matched_transaction_id: str | None = None
    score: float = 0.0
    reason: str = ""


def compute_similarity(str1: str, str2: str) -> float:
    """Token overlap similarity between two strings."""
    if not str1 or not str2:
        return 0.0
    tokens1 = set(re.findall(r"\w+", str1.lower()))
    tokens2 = set(re.findall(r"\w+", str2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


UPI_RRN_PATTERN = re.compile(r"(?:UPI[/-](?:[A-Za-z0-9]+[/-])?)?(\d{12})\b")


def extract_upi_rrn(text: str | None) -> str | None:
    """Extract 12-digit UPI RRN (Retrieval Reference Number) from text narration or reference string."""
    if not text:
        return None
    m = UPI_RRN_PATTERN.search(text)
    if m:
        return m.group(1)
    return None


def match_statement_transaction(
    stmt_tx: StatementTransaction,
    candidate_ledger_txs: list[Transaction],
) -> MatchResult:
    """Evaluate candidate ledger transactions using composite scoring."""
    tx_desc = stmt_tx.description.lower()
    tx_amt = float(stmt_tx.amount)

    # 0. Deterministic UPI 12-digit RRN Exact Matching (Strongest Core Correlation)
    stmt_rrn = extract_upi_rrn(stmt_tx.description) or (
        stmt_tx.reference_number if stmt_tx.reference_number and len(stmt_tx.reference_number) == 12 and stmt_tx.reference_number.isdigit() else None
    )
    if stmt_rrn:
        for l_tx in candidate_ledger_txs:
            l_text = f"{l_tx.reference_number or ''} {l_tx.bank_reference or ''} {l_tx.description or ''} {l_tx.merchant_raw or ''} {l_tx.upi_id or ''}"
            l_rrn = extract_upi_rrn(l_text)
            if l_rrn == stmt_rrn:
                # If amounts match closely (within 1 rupee)
                if abs(float(l_tx.amount) - tx_amt) < 1.00:
                    return MatchResult(
                        status="MATCHED",
                        matched_transaction_id=l_tx.id,
                        score=1.0,
                        reason=f"Exact UPI RRN match: {stmt_rrn}",
                    )

    # 1. Detect Credit Card Bill Payments (Liability Payment)
    if "scapia" in tx_desc or "creditcard payment" in tx_desc or "credit card payment" in tx_desc:
        for l_tx in candidate_ledger_txs:
            if abs(float(l_tx.amount) - tx_amt) < 0.50 and abs((l_tx.transaction_date - stmt_tx.transaction_date).days) <= 4:
                return MatchResult(
                    status="LIABILITY_PAYMENT",
                    matched_transaction_id=l_tx.id,
                    score=0.95,
                    reason=f"Matched credit card settlement / bill payment against {l_tx.merchant_raw or l_tx.source}",
                )

    best_match: Transaction | None = None
    best_score = 0.0
    best_reason = ""

    stmt_norm = (normalize_merchant(stmt_tx.description) or stmt_tx.description).lower()


    for l_tx in candidate_ledger_txs:
        score = 0.0
        reasons = []

        # A. Amount score (40%)
        l_amt = float(l_tx.amount)
        if abs(l_amt - tx_amt) < 0.05:
            score += 0.40
            reasons.append("Exact amount")
        elif abs(l_amt - tx_amt) < 2.00:
            score += 0.30
            reasons.append("Near amount")
        else:
            # If amount doesn't match closely, skip
            continue

        # B. Date proximity score (25%)
        day_diff = abs((l_tx.transaction_date.date() - stmt_tx.transaction_date.date()).days)
        if day_diff == 0:
            score += 0.25
            reasons.append("Same date")
        elif day_diff <= 1:
            score += 0.20
            reasons.append("±1 day")
        elif day_diff <= 3:
            score += 0.10
            reasons.append("±3 days")

        # C. Merchant / Description similarity (20%)
        l_norm = (l_tx.merchant_normalized or l_tx.merchant_raw or "").lower()
        sim = compute_similarity(stmt_norm, l_norm)
        if sim > 0.6:
            score += 0.20
            reasons.append(f"Merchant match ({stmt_norm})")
        elif sim > 0.2:
            score += 0.10
            reasons.append("Partial merchant match")

        # D. Reference overlap (15%)
        if stmt_tx.reference_number and l_tx.reference_number:
            if stmt_tx.reference_number.strip().lower() == l_tx.reference_number.strip().lower():
                score += 0.15
                reasons.append("Reference match")

        if score > best_score:
            best_score = score
            best_match = l_tx
            best_reason = ", ".join(reasons)

    if best_match and best_score >= 0.70:
        return MatchResult(
            status="MATCHED",
            matched_transaction_id=best_match.id,
            score=best_score,
            reason=best_reason,
        )
    elif best_match and best_score >= 0.50:
        return MatchResult(
            status="POSSIBLE_MATCH",
            matched_transaction_id=best_match.id,
            score=best_score,
            reason=best_reason,
        )

    return MatchResult(status="UNMATCHED", score=0.0, reason="No matching ledger alert found")


def reconcile_statement_in_db(
    session: Session, statement_id: str
) -> dict[str, Any]:
    """Run reconciliation for all transactions belonging to a statement."""
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        return {"error": "Statement not found"}

    stmt_txs = session.scalars(
        select(StatementTransaction).where(StatementTransaction.statement_id == statement_id)
    ).all()

    if not stmt_txs:
        return {"matched": 0, "possible_matches": 0, "unmatched": 0, "liability_payments": 0}

    # Fetch candidate ledger transactions around statement period
    p_start = statement.statement_period_start or (stmt_txs[0].transaction_date - timedelta(days=35))
    p_end = statement.statement_period_end or (stmt_txs[-1].transaction_date + timedelta(days=5))

    ledger_txs = session.scalars(
        select(Transaction).where(
            Transaction.transaction_date >= p_start - timedelta(days=5),
            Transaction.transaction_date <= p_end + timedelta(days=5),
        )
    ).all()

    matched_cnt = 0
    possible_cnt = 0
    unmatched_cnt = 0
    liability_cnt = 0

    for st in stmt_txs:
        # 1. Preserve manual user confirmations and imported ledger entries
        is_user_confirmed = (
            st.match_confidence == 1.0
            or (st.match_reason and ("Manually confirmed" in st.match_reason or "Imported to ledger" in st.match_reason))
        )
        is_user_rejected = st.match_reason and ("non-match by user" in st.match_reason or "Rejected match by user" in st.match_reason)

        if is_user_confirmed and st.match_status == "MATCHED":
            matched_cnt += 1
            continue
        if is_user_rejected and st.match_status == "UNMATCHED":
            unmatched_cnt += 1
            continue

        res = match_statement_transaction(st, ledger_txs)
        st.match_status = res.status
        st.matched_transaction_id = res.matched_transaction_id
        st.match_confidence = res.score
        st.match_reason = res.reason

        if res.status == "MATCHED":
            matched_cnt += 1
        elif res.status == "POSSIBLE_MATCH":
            possible_cnt += 1
        elif res.status == "LIABILITY_PAYMENT":
            liability_cnt += 1
        else:
            unmatched_cnt += 1


    session.commit()

    return {
        "statement_id": statement_id,
        "total_transactions": len(stmt_txs),
        "matched": matched_cnt,
        "possible_matches": possible_cnt,
        "unmatched": unmatched_cnt,
        "liability_payments": liability_cnt,
    }


def scan_gmail_for_upi_rrn(
    session: Session,
    statement_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    """Search Gmail for an email matching the 12-digit UPI RRN and ingest/match it."""
    from mymonee.config import get_settings
    from mymonee.ingestion.discovery import load_discovery_rules
    from mymonee.ingestion.gmail.client import GmailApiSource
    from mymonee.ingestion.pipeline import (
        PipelineResult,
        _persist_parsed,
        _to_email_context,
        _upsert_email,
        bootstrap_parsers,
        registry,
    )

    stmt_tx = session.get(StatementTransaction, transaction_id)
    if not stmt_tx or stmt_tx.statement_id != statement_id:
        return {"success": False, "message": "Statement transaction not found"}

    rrn = extract_upi_rrn(stmt_tx.description) or (
        stmt_tx.reference_number if stmt_tx.reference_number and len(stmt_tx.reference_number) == 12 and stmt_tx.reference_number.isdigit() else None
    )
    if not rrn:
        return {"success": False, "message": "No 12-digit UPI RRN found in this transaction narration"}

    settings = get_settings()
    try:
        gmail = GmailApiSource(settings)
    except Exception as e:
        return {"success": False, "message": f"Gmail client connection unavailable: {e}"}

    # Query Gmail for the exact UPI RRN
    msg_ids = gmail.list_message_ids(query=f'"{rrn}"', max_results=5)
    if not msg_ids:
        msg_ids = gmail.list_message_ids(query=rrn, max_results=5)

    if not msg_ids:
        return {"success": True, "found": False, "rrn": rrn, "message": f"No Gmail notification emails found containing UPI reference {rrn}"}

    bootstrap_parsers()
    _ = load_discovery_rules()
    result = PipelineResult(run_id="scan_upi_rrn", status="running")

    created_tx: Transaction | None = None
    for mid in msg_ids:
        try:
            msg = gmail.get_message(mid)
            if msg.is_excluded_recipient():
                continue
            _upsert_email(session, msg)
            session.flush()

            ctx = _to_email_context(msg)
            parsed_items, provider_hint = registry.parse_with_provider(ctx)

            for parsed in parsed_items:
                _persist_parsed(
                    session,
                    message=msg,
                    parsed=parsed,
                    provider_hint=provider_hint,
                    result=result,
                    force_update=True,
                )
                tx_row = session.scalar(
                    select(Transaction).where(Transaction.source_email_id == msg.id).order_by(Transaction.created_at.desc())
                )
                if tx_row:
                    created_tx = tx_row
                    break
            if created_tx:
                break
        except Exception as msg_err:
            logger.warning("Failed processing Gmail message %s during UPI scan: %s", mid, msg_err)

    if created_tx:
        stmt_tx.matched_transaction_id = created_tx.id
        stmt_tx.match_status = "MATCHED"
        stmt_tx.match_confidence = 1.0
        stmt_tx.match_reason = f"Discovered & ingested from Gmail via UPI RRN {rrn}"
        session.commit()
        return {
            "success": True,
            "found": True,
            "rrn": rrn,
            "matched_transaction_id": created_tx.id,
            "message": f"Found email in Gmail with UPI reference {rrn} and successfully ingested into ledger!",
        }

    session.commit()
    return {"success": True, "found": False, "rrn": rrn, "message": f"Email found for {rrn}, but parser could not extract a transaction"}


"""Gmail → discover → parse → persist pipeline (idempotent)."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mymonee.config import Settings
from mymonee.classification.enrichment import apply_parsed_enrichment
from mymonee.db.models import (
    Account,
    Email,
    FinancialEvent,
    IngestionEvent,
    IngestionRun,
    Institution,
    Merchant,
    MerchantAlias,
    Posting,
    SyncState,
    Transaction,
    utcnow,
)
from mymonee.domain.enums import EmailParseStatus, IngestionRunStatus
from mymonee.ingestion.discovery import DiscoveryRules, load_discovery_rules
from mymonee.ingestion.fingerprint import transaction_fingerprint
from mymonee.ingestion.gmail.client import GmailApiSource, GmailMessage, MessageSource
from mymonee.merchants.normalize import normalize_merchant
from mymonee.parsers.base import EmailContext, ParsedTransaction
from mymonee.parsers.bootstrap import bootstrap_parsers
from mymonee.parsers.registry import registry

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    run_id: str
    status: str
    emails_discovered: int = 0
    emails_processed: int = 0
    emails_skipped: int = 0
    transactions_extracted: int = 0
    transactions_duplicated: int = 0
    transactions_rejected: int = 0
    parsing_errors: int = 0
    auth_errors: int = 0
    error_summary: str | None = None


def _set_sync(session: Session, key: str, value: str, extra: dict[str, Any] | None = None) -> None:
    row = session.get(SyncState, key)
    if row is None:
        row = SyncState(key=key, value=value, extra_json=extra or {})
        session.add(row)
    else:
        row.value = value
        row.extra_json = extra or row.extra_json or {}
        row.updated_at = utcnow()


def _get_sync(session: Session, key: str) -> SyncState | None:
    return session.get(SyncState, key)


def _log_event(
    session: Session,
    run_id: str,
    *,
    event_type: str,
    message: str,
    level: str = "info",
    email_id: str | None = None,
    transaction_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    session.add(
        IngestionEvent(
            run_id=run_id,
            level=level,
            event_type=event_type,
            message=message,
            email_id=email_id,
            transaction_id=transaction_id,
            extra_json=extra or {},
        )
    )


def _to_email_context(message: GmailMessage) -> EmailContext:
    return EmailContext(
        message_id=message.id,
        thread_id=message.thread_id,
        sender=message.sender,
        subject=message.subject,
        received_at=message.received_at,
        body_text=message.body_text,
        body_html=message.body_html,
        headers=message.headers,
        labels=message.label_ids,
    )


def _upsert_email(
    session: Session,
    message: GmailMessage,
    *,
    provider_hint: str | None,
    parse_status: str,
    parse_error: str | None = None,
) -> Email:
    existing = session.get(Email, message.id)
    if existing is None:
        existing = Email(id=message.id)
        session.add(existing)
    existing.thread_id = message.thread_id
    existing.sender = message.sender
    existing.subject = message.subject
    existing.snippet = message.snippet
    existing.received_at = message.received_at
    existing.label_ids_json = message.label_ids
    existing.headers_json = {
        k: v
        for k, v in message.headers.items()
        if k in {"from", "to", "subject", "date", "message-id"}
    }
    existing.body_text = message.body_text
    existing.body_html = message.body_html
    existing.provider_hint = provider_hint
    existing.parse_status = parse_status
    existing.parse_error = parse_error
    existing.updated_at = utcnow()
    existing.extra_json = {
        **(existing.extra_json or {}),
        "internal_date_ms": message.internal_date_ms,
        "history_id": message.history_id,
    }
    return existing


def _resolve_merchant_entity_id(session: Session, raw: str | None, norm: str | None) -> str | None:
    if not raw and not norm:
        return None
    raw_val = raw or norm or "Unknown Merchant"
    norm_val = norm or raw_val.lower().replace(" ", "_").strip() or "unknown_merchant"

    # 1. Check if an alias matches raw
    if raw:
        alias = session.scalar(select(MerchantAlias).where(MerchantAlias.alias_raw == raw).limit(1))
        if alias:
            return alias.merchant_id

    # 2. Check if Merchant exists by normalized_key
    merchant = session.scalar(select(Merchant).where(Merchant.normalized_key == norm_val).limit(1))
    if merchant:
        return merchant.id

    # 3. Create new Merchant entity
    display_name = raw_val.upper() if len(raw_val) < 4 else raw_val.title()
    merchant = Merchant(
        display_name=display_name,
        normalized_key=norm_val,
        canonical_name=None,
    )
    session.add(merchant)
    session.flush()

    if raw:
        try:
            alias = MerchantAlias(
                merchant_id=merchant.id,
                alias_raw=raw,
                alias_normalized=norm_val,
                source="ingestion",
            )
            session.add(alias)
            session.flush()
        except Exception:
            pass

    return merchant.id


def _apply_parsed_fields(
    tx: Transaction,
    parsed: ParsedTransaction,
    *,
    source: str,
    session: Session | None = None,
) -> None:
    desc = f"{parsed.description or ''} {parsed.merchant_raw or ''}".lower()
    is_refund = parsed.transaction_type == "refund" or (
        parsed.direction == "credit" and "refund" in desc
    )
    extra = dict(parsed.extra or {})
    tx.source = source
    tx.transaction_date = parsed.transaction_date
    tx.posted_date = parsed.posted_date
    tx.amount = parsed.amount
    tx.currency = parsed.currency or "INR"
    tx.direction = parsed.direction
    tx.transaction_type = parsed.transaction_type
    tx.merchant_raw = parsed.merchant_raw
    tx.merchant_normalized = normalize_merchant(parsed.merchant_raw)
    is_transfer_tx = bool(extra.get("is_transfer", parsed.transaction_type == "transfer" or extra.get("category_slug") == "transfers"))
    if session is not None and not is_transfer_tx and parsed.transaction_type != "transfer":
        tx.merchant_entity_id = _resolve_merchant_entity_id(
            session, tx.merchant_raw, tx.merchant_normalized
        )
    else:
        tx.merchant_entity_id = None
    tx.payment_method = parsed.payment_method
    tx.account = parsed.account
    tx.card = parsed.card
    tx.upi_id = parsed.upi_id
    tx.reference_number = parsed.reference_number
    tx.bank_reference = parsed.bank_reference
    tx.description = parsed.description
    tx.location = parsed.location
    tx.classification_source = str(extra.get("classification_source") or "unknown")
    tx.classification_confidence = float(extra.get("classification_confidence") or 0.0)
    tx.classification_signals = (
        extra.get("classification_signals")
        if isinstance(extra.get("classification_signals"), dict)
        else {}
    )
    tx.needs_review = bool(extra.get("needs_review", True))
    tx.is_refund = bool(extra.get("is_refund", is_refund))
    tx.is_transfer = bool(extra.get("is_transfer", parsed.transaction_type == "transfer"))
    tx.excludes_from_spending = bool(
        extra.get(
            "excludes_from_spending",
            parsed.transaction_type in {"transfer", "income"},
        )
    )
    tx.extra_json = {**(tx.extra_json or {}), **extra}
    tx.updated_at = utcnow()


def _get_or_create_account(session: Session, parsed: ParsedTransaction) -> Account:
    """Resolve an existing Account by card_last4, account_number_masked, UPI identifier, or name,
    creating one only as a fallback."""
    all_accounts = session.query(Account).all()

    # 1. Match by card last 4 digits (e.g. 4951, 1221, 0863)
    if parsed.card:
        card_clean = parsed.card.strip()
        # Prefer credit card accounts first when matching card numbers
        for acc in sorted(all_accounts, key=lambda a: (a.account_type != "CREDIT_CARD", a.name)):
            if acc.card_last4 and acc.card_last4.strip() == card_clean:
                return acc
            if acc.account_number_masked:
                masked_digits = "".join(re.findall(r"\d+", acc.account_number_masked))
                if masked_digits and masked_digits.endswith(card_clean):
                    return acc

    # 2. Match by account number or masked account (e.g. ****1022, 801022, 1022)
    if parsed.account:
        raw_digits = "".join(re.findall(r"\d+", parsed.account))
        acc_clean = parsed.account.replace("*", "").replace("X", "").strip()
        last4 = raw_digits[-4:] if len(raw_digits) >= 4 else acc_clean
        if last4:
            # When matching an account number without card, prefer BANK accounts over CREDIT_CARD
            for acc in sorted(all_accounts, key=lambda a: (a.account_type != "BANK", a.name)):
                if acc.account_number_masked:
                    masked_digits = "".join(re.findall(r"\d+", acc.account_number_masked))
                    if masked_digits and masked_digits.endswith(last4):
                        return acc
                if acc.card_last4 and acc.card_last4.strip() == last4:
                    return acc

    # 3. Match by UPI ID
    if parsed.upi_id:
        upi_clean = parsed.upi_id.lower().strip()
        for acc in all_accounts:
            if acc.upi_identifier_masked and acc.upi_identifier_masked.lower() in upi_clean:
                return acc

    # 4. Fallback matching by name
    if parsed.account:
        name = f"{parsed.account} Account"
        acc_type = "BANK"
        is_liability = False
    elif parsed.card:
        name = f"Credit Card {parsed.card}"
        acc_type = "CREDIT_CARD"
        is_liability = True
    elif parsed.upi_id:
        name = f"UPI {parsed.upi_id.split('@')[-1] if '@' in parsed.upi_id else parsed.upi_id}"
        acc_type = "BANK"
        is_liability = False
    elif parsed.payment_method:
        name = f"{parsed.payment_method} Account"
        acc_type = "BANK"
        is_liability = False
    else:
        name = "Default Cash Account"
        acc_type = "CASH"
        is_liability = False

    for acc in all_accounts:
        if acc.name.strip().lower() == name.strip().lower():
            return acc

    # 5. Create new account with populated identifier fields
    inst = session.query(Institution).filter_by(name="Unknown Institution").first()
    if not inst:
        inst = Institution(name="Unknown Institution", institution_type="BANK")
        session.add(inst)
        session.flush()

    acc = Account(
        name=name,
        institution_id=inst.id,
        account_type=acc_type,
        is_asset=not is_liability,
        is_liability=is_liability,
        card_last4=parsed.card if parsed.card else None,
        account_number_masked=parsed.account if parsed.account else None,
        upi_identifier_masked=parsed.upi_id if parsed.upi_id else None,
    )
    session.add(acc)
    session.flush()
    return acc


def _persist_parsed(
    session: Session,
    *,
    message: GmailMessage,
    parsed: ParsedTransaction,
    provider_hint: str | None,
    result: PipelineResult,
    force_update: bool = False,
) -> None:
    fingerprint = transaction_fingerprint(
        source_email_id=message.id,
        amount=parsed.amount,
        direction=parsed.direction,
        transaction_date=parsed.transaction_date,
        merchant_raw=parsed.merchant_raw,
        reference_number=parsed.reference_number,
    )
    source = f"gmail:{provider_hint}" if provider_hint else "gmail:unknown"
    existing = session.scalar(
        select(Transaction).where(Transaction.fingerprint == fingerprint)
    )
    if existing is None and parsed.reference_number:
        existing = session.scalar(
            select(Transaction).where(
                Transaction.source_email_id == message.id,
                Transaction.reference_number == parsed.reference_number,
            )
        )
    if existing is None and force_update:
        # Merchant/ref changes can alter fingerprint; still update the email's prior row.
        existing = session.scalar(
            select(Transaction).where(Transaction.source_email_id == message.id)
        )
    if existing is not None:
        result.transactions_duplicated += 1
        if force_update:
            existing.fingerprint = fingerprint
            existing.source_thread_id = message.thread_id
            existing.raw_email_reference = message.id
            _apply_parsed_fields(existing, parsed, source=source, session=session)
            apply_parsed_enrichment(session, existing, parsed)
        else:
            existing.updated_at = utcnow()
        return

    tx = Transaction(
        source=source,
        source_email_id=message.id,
        source_thread_id=message.thread_id,
        fingerprint=fingerprint,
        raw_email_reference=message.id,
    )
    _apply_parsed_fields(tx, parsed, source=source, session=session)
    
    # Ledger integration
    acc = _get_or_create_account(session, parsed)
    if acc:
        if acc.card_last4:
            tx.account = f"{acc.name} (XX{acc.card_last4})"
        elif acc.account_number_masked:
            num = acc.account_number_masked
            num_str = f"XX{num}" if not num.startswith("XX") else num
            tx.account = f"{acc.name} ({num_str})"
        else:
            tx.account = acc.name
    
    event = FinancialEvent(
        event_type="purchase" if parsed.direction == "debit" else "deposit",
        event_date=parsed.transaction_date,
        source=source,
        description=parsed.description or parsed.merchant_raw or "Ingestion",
    )
    session.add(event)
    session.flush()
    tx.financial_event_id = event.id
    
    session.add(Posting(
        event_id=event.id,
        account_id=acc.id,
        amount=parsed.amount,
        direction=parsed.direction,
        posting_type="asset_decrease" if parsed.direction == "debit" else "asset_increase"
    ))
    
    session.add(tx)
    session.flush()
    
    # After apply_parsed_enrichment, the tx.category_id will be set if matched.
    # We should add the category posting.
    apply_parsed_enrichment(session, tx, parsed)
    
    if tx.category_id:
        session.add(Posting(
            event_id=event.id,
            category_id=tx.category_id,
            amount=parsed.amount,
            direction="credit" if parsed.direction == "debit" else "debit",
            posting_type="expense" if parsed.direction == "debit" else "income"
        ))

    result.transactions_extracted += 1


def _build_query(
    settings: Settings,
    session: Session,
    rules: DiscoveryRules,
    *,
    after_date: str | None = None,
    ignore_watermark: bool = False,
) -> str:
    if after_date:
        return rules.build_gmail_query(after_date=after_date)

    if not ignore_watermark:
        watermark = _get_sync(session, "gmail.last_internal_date_ms")
        if watermark and watermark.value and watermark.value.isdigit():
            dt = datetime.fromtimestamp(int(watermark.value) / 1000, tz=timezone.utc) - timedelta(
                days=1
            )
            return rules.build_gmail_query(after_date=dt.strftime("%Y/%m/%d"))

    if settings.gmail.sync_after_date:
        return rules.build_gmail_query(after_date=settings.gmail.sync_after_date)

    return rules.build_gmail_query(newer_than_days=settings.gmail.initial_lookback_days)


def run_ingestion_pipeline(
    session: Session,
    settings: Settings,
    *,
    source: MessageSource | None = None,
    max_messages: int | None = None,
    force_reparse: bool = False,
    after_date: str | None = None,
    ignore_watermark: bool = False,
) -> PipelineResult:
    bootstrap_parsers()
    rules = load_discovery_rules()
    run = IngestionRun(status=IngestionRunStatus.RUNNING)
    session.add(run)
    session.flush()

    result = PipelineResult(run_id=run.id, status=IngestionRunStatus.RUNNING)
    max_messages = max_messages or settings.gmail.max_messages_per_sync

    logger.info(
        "Starting ingestion pipeline (max_messages=%s, after_date=%s, ignore_watermark=%s, force_reparse=%s)",
        max_messages,
        after_date,
        ignore_watermark,
        force_reparse,
    )

    try:
        if source is None:
            source = GmailApiSource(settings)
    except Exception as exc:
        logger.error("Gmail client initialization failed: %s", exc)
        result.auth_errors = 1
        result.status = IngestionRunStatus.FAILED
        result.error_summary = str(exc)
        run.status = result.status
        run.auth_errors = 1
        run.error_summary = result.error_summary
        run.finished_at = utcnow()
        _log_event(session, run.id, event_type="auth_error", message=str(exc), level="error")
        session.flush()
        return result

    query = _build_query(
        settings,
        session,
        rules,
        after_date=after_date,
        ignore_watermark=ignore_watermark,
    )
    logger.info("Gmail discovery query: '%s'", query)
    _log_event(session, run.id, event_type="query", message=f"Gmail query: {query}")

    try:
        message_ids = source.list_message_ids(query, max_results=max_messages)
    except Exception as exc:
        logger.error("Failed to query Gmail messages: %s", exc)
        result.status = IngestionRunStatus.FAILED
        result.error_summary = f"list failed: {exc}"
        run.status = result.status
        run.error_summary = result.error_summary
        run.finished_at = utcnow()
        _log_event(session, run.id, event_type="list_error", message=str(exc), level="error")
        session.flush()
        return result

    result.emails_discovered = len(message_ids)
    logger.info("Discovered %d candidate message(s) matching query", len(message_ids))
    newest_internal: int | None = None

    for message_id in message_ids:
        try:
            existing = session.get(Email, message_id)
            if (
                existing
                and existing.parse_status in {EmailParseStatus.PARSED, EmailParseStatus.SKIPPED}
                and not force_reparse
            ):
                result.emails_skipped += 1
                if existing.parse_status == EmailParseStatus.PARSED:
                    tx_count = session.scalar(
                        select(func.count()).select_from(Transaction).where(Transaction.source_email_id == existing.id)
                    ) or 1
                    result.transactions_duplicated += tx_count
                logger.debug("Skipped already processed message %s", message_id)
                continue

            message = source.get_message(message_id)
            if message.internal_date_ms is not None:
                newest_internal = max(newest_internal or 0, message.internal_date_ms)

            is_financial, reason = rules.is_financial_candidate(message)
            provider, provider_score = rules.detect_provider(message)

            if not is_financial:
                _upsert_email(
                    session,
                    message,
                    provider_hint=provider,
                    parse_status=EmailParseStatus.SKIPPED,
                    parse_error=reason,
                )
                result.emails_processed += 1
                result.emails_skipped += 1
                logger.debug("Message %s skipped: not a financial candidate (%s)", message_id, reason)
                continue

            ctx = _to_email_context(message)
            plugin, score = registry.choose(ctx)
            if plugin is None:
                _upsert_email(
                    session,
                    message,
                    provider_hint=provider,
                    parse_status=EmailParseStatus.SKIPPED,
                    parse_error="no_parser",
                )
                result.emails_processed += 1
                result.transactions_rejected += 1
                logger.warning("No parser matched message %s (provider: %s, score: %.2f)", message_id, provider, provider_score)
                _log_event(
                    session,
                    run.id,
                    event_type="no_parser",
                    message=f"No parser for message {message_id}",
                    email_id=message_id,
                    level="warning",
                    extra={"provider": provider, "provider_score": provider_score},
                )
                continue

            try:
                parsed_list = plugin.parse(ctx)
            except Exception as exc:
                result.parsing_errors += 1
                _upsert_email(
                    session,
                    message,
                    provider_hint=provider,
                    parse_status=EmailParseStatus.ERROR,
                    parse_error=str(exc),
                )
                result.emails_processed += 1
                logger.warning("Parse error on message %s via %s: %s", message_id, plugin.name, exc)
                _log_event(
                    session,
                    run.id,
                    event_type="parse_error",
                    message=str(exc),
                    email_id=message_id,
                    level="error",
                )
                continue

            if not parsed_list:
                _upsert_email(
                    session,
                    message,
                    provider_hint=provider,
                    parse_status=EmailParseStatus.SKIPPED,
                    parse_error="parser_empty",
                )
                result.emails_processed += 1
                result.transactions_rejected += 1
                logger.debug("Parser %s returned 0 transactions for message %s", plugin.name, message_id)
                continue

            _upsert_email(
                session,
                message,
                provider_hint=provider,
                parse_status=EmailParseStatus.PARSED,
            )
            for parsed in parsed_list:
                _persist_parsed(
                    session,
                    message=message,
                    parsed=parsed,
                    provider_hint=provider,
                    result=result,
                    force_update=force_reparse,
                )
            result.emails_processed += 1
            logger.debug("Parsed message %s into %d tx via %s (score=%.2f)", message_id, len(parsed_list), plugin.name, score)
            _log_event(
                session,
                run.id,
                event_type="parsed",
                message=f"Parsed {len(parsed_list)} tx via {plugin.name} (score={score:.2f})",
                email_id=message_id,
                extra={"parser": plugin.name, "provider": provider},
            )
        except Exception as exc:
            result.parsing_errors += 1
            _log_event(
                session,
                run.id,
                event_type="message_error",
                message=str(exc),
                email_id=message_id,
                level="error",
            )
            logger.exception("Failed processing message %s", message_id)
            continue

    # Update sync watermark
    if newest_internal is not None:
        _set_sync(session, "gmail.last_internal_date_ms", str(newest_internal))
    _set_sync(session, "gmail.last_sync_at", utcnow().isoformat())
    try:
        history_id = source.get_profile_history_id()
        if history_id:
            _set_sync(session, "gmail.history_id", history_id)
    except Exception:
        logger.debug("Could not fetch Gmail historyId", exc_info=True)

    if result.parsing_errors and result.transactions_extracted:
        result.status = IngestionRunStatus.PARTIAL
    elif result.auth_errors or (result.parsing_errors and not result.emails_processed):
        result.status = IngestionRunStatus.FAILED
    else:
        result.status = IngestionRunStatus.SUCCESS

    run.status = result.status
    run.finished_at = utcnow()
    run.emails_discovered = result.emails_discovered
    run.emails_processed = result.emails_processed
    run.transactions_extracted = result.transactions_extracted
    run.transactions_rejected = result.transactions_rejected
    run.transactions_duplicated = result.transactions_duplicated
    run.parsing_errors = result.parsing_errors
    run.auth_errors = result.auth_errors
    run.error_summary = result.error_summary
    run.extra_json = {"query": query, "emails_skipped": result.emails_skipped}
    session.flush()

    logger.info(
        "Ingestion pipeline completed [%s]: discovered=%d processed=%d extracted=%d skipped=%d duplicated=%d parse_errors=%d auth_errors=%d",
        result.status,
        result.emails_discovered,
        result.emails_processed,
        result.transactions_extracted,
        result.emails_skipped,
        result.transactions_duplicated,
        result.parsing_errors,
        result.auth_errors,
    )
    return result


def run_ingestion_result_dict(result: PipelineResult) -> dict[str, Any]:
    return asdict(result)

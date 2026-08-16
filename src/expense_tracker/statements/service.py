"""Statement Vault Service: Ingestion pipeline, password unlocking, file storage, and audit logging."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.config import get_settings
from expense_tracker.db.models import (
    Account,
    CreditCardStatement,
    PasswordProfile,
    StatementAccount,
    StatementProcessingEvent,
    StatementSection,
    StatementSummary,
    StatementTransaction,
    new_id,
    utcnow,
)
from expense_tracker.ingestion.gmail.client import GmailMessage, MessageSource
from expense_tracker.statements.discovery import (
    DiscoveredStatementCandidate,
    discover_statement_candidates,
)
from expense_tracker.statements.parsers.registry import get_statement_parser_registry
from expense_tracker.statements.password_engine import (
    AccountProfile,
    generate_candidate_passwords,
)
from expense_tracker.statements.reconciliation import reconcile_statement_in_db
from expense_tracker.statements.validator import StatementValidator
from expense_tracker.statements.vault import (
    compute_sha256,
    save_original_statement,
    save_unlocked_statement,
    unlock_pdf,
    validate_pdf,
)

logger = logging.getLogger(__name__)


def _record_event(
    session: Session,
    statement_id: str,
    stage: str,
    status: str,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> StatementProcessingEvent:
    event = StatementProcessingEvent(
        id=new_id(),
        statement_id=statement_id,
        stage=stage,
        status=status,
        message=message,
        metadata_json=metadata or {},
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(event)
    session.flush()
    return event


def find_matching_account(
    session: Session,
    issuer: str,
    identifier_last4: str | None,
    statement_type: str = "CREDIT_CARD",
) -> Account | None:
    """Find matching account by card_last4, account_number_masked, or issuer name."""
    all_accounts = session.scalars(select(Account)).all()

    # 1. Exact card_last4 or account_number_masked match
    if identifier_last4:
        for acc in all_accounts:
            if acc.card_last4 == identifier_last4:
                return acc
            if acc.account_number_masked and identifier_last4 in acc.account_number_masked:
                return acc

    # 2. Issuer + Statement Type match in account name
    if issuer and issuer != "UNKNOWN":
        type_filtered = [
            a for a in all_accounts
            if (statement_type == "BANK_ACCOUNT" and a.account_type == "BANK")
            or (statement_type == "CREDIT_CARD" and a.account_type == "CREDIT_CARD")
        ]
        matching = [a for a in type_filtered if issuer.lower() in a.name.lower()]
        if matching:
            return matching[0]

        # Fallback to any account with matching issuer name
        general_matching = [a for a in all_accounts if issuer.lower() in a.name.lower()]
        if general_matching:
            return general_matching[0]

    return None


def get_profile_for_account(
    session: Session, account_id: str | None, issuer: str = "", card_last4: str = ""
) -> tuple[PasswordProfile | None, AccountProfile]:
    """Load or construct account profile for password candidate generation."""
    profile_row: PasswordProfile | None = None
    if account_id:
        profile_row = session.scalars(
            select(PasswordProfile).where(PasswordProfile.account_id == account_id)
        ).first()

    account = session.get(Account, account_id) if account_id else None
    card_l4 = card_last4 or (account.card_last4 if account else "") or ""
    iss = issuer or (profile_row.issuer if profile_row else "") or ""

    if profile_row and profile_row.configuration:
        acc_prof = AccountProfile.from_dict(
            profile_row.configuration, card_last4=card_l4, issuer=iss
        )
    else:
        acc_prof = AccountProfile(card_last4=card_l4, issuer=iss)

    return profile_row, acc_prof


def enrich_statement_metadata(session: Session, statement: CreditCardStatement) -> None:
    """Enrich statement dates, period, card number, and amounts from unlocked PDF via PyMuPDF."""
    if not statement.unlocked_file_path or not Path(statement.unlocked_file_path).exists():
        return

    try:
        import re
        from datetime import datetime, timezone
        import pymupdf

        doc = pymupdf.open(statement.unlocked_file_path)
        if len(doc) == 0:
            return
        text = doc[0].get_text("text")

        # 1. Statement Period
        period_m = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
        if period_m:
            p_start = datetime.strptime(period_m.group(1), "%d/%m/%Y").replace(tzinfo=timezone.utc)
            p_end = datetime.strptime(period_m.group(2), "%d/%m/%Y").replace(tzinfo=timezone.utc)
            statement.statement_period_start = p_start
            statement.statement_period_end = p_end
            if not statement.statement_date or statement.statement_date != p_end:
                statement.statement_date = p_end
        else:
            period_m2 = re.search(
                r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*(?:to|-)\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
                text,
            )
            if period_m2:
                try:
                    p_start = datetime.strptime(period_m2.group(1), "%d %b %Y").replace(
                        tzinfo=timezone.utc
                    )
                    p_end = datetime.strptime(period_m2.group(2), "%d %b %Y").replace(
                        tzinfo=timezone.utc
                    )
                    statement.statement_period_start = p_start
                    statement.statement_period_end = p_end
                    if not statement.statement_date:
                        statement.statement_date = p_end
                except Exception:
                    pass

        # 2. Card last 4 & Account Linking
        card_m = re.search(
            r"(?:Card No|Card Number|Account No|A/c No)[\s\:\.]*(\d{4,6}[\*X]+(\d{4}))",
            text,
            re.IGNORECASE,
        )
        if card_m:
            l4 = card_m.group(2)
            statement.card_last4 = l4
            matching_acc = session.scalars(select(Account).where(Account.card_last4 == l4)).first()
            if matching_acc:
                statement.account_id = matching_acc.id
                statement.statement_type = "CREDIT_CARD"

        # 3. Total amount due
        due_m = re.search(
            r"Total (?:Payment|Amount) Due\s*\n*([0-9,]+\.\d{2})\s*(?:Dr|Cr)?",
            text,
            re.IGNORECASE,
        )
        if due_m:
            try:
                statement.total_amount_due = float(due_m.group(1).replace(",", ""))
            except Exception:
                pass
    except Exception as exc:
        logger.debug(f"Metadata enrichment skipped for statement {statement.id}: {exc}")


def process_statement_bytes(
    session: Session,
    statement: CreditCardStatement,
    content: bytes,
    data_dir: Path,
) -> CreditCardStatement:
    """Core pipeline: inspect, store original, unlock if encrypted, validate, and store unlocked."""
    statement_id = statement.id
    account_id = statement.account_id

    # 1. Validate PDF structure
    is_valid, is_encrypted, page_count, err = validate_pdf(content)
    if not is_valid:
        statement.status = "INVALID_PDF"
        statement.error_code = "INVALID_PDF"
        statement.error_message = err or "File is not a valid PDF"
        _record_event(
            session, statement_id, "PDF_INSPECTION", "FAILED", message=statement.error_message
        )
        session.commit()
        return statement

    statement.is_encrypted = is_encrypted
    _record_event(
        session,
        statement_id,
        "PDF_INSPECTION",
        "SUCCESS",
        message=f"Valid PDF (encrypted={is_encrypted}, pages={page_count})",
        metadata={"is_encrypted": is_encrypted, "page_count": page_count},
    )

    # 2. Save original PDF immutably
    orig_path, orig_sha = save_original_statement(
        data_dir, account_id, statement_id, content, statement.statement_date
    )
    statement.original_file_path = str(orig_path)
    statement.original_sha256 = orig_sha
    statement.downloaded_at = utcnow()

    # 3. If unencrypted, copy straight to unlocked
    if not is_encrypted:
        unlocked_path, unl_sha = save_unlocked_statement(
            data_dir, account_id, statement_id, content, statement.statement_date
        )
        statement.unlocked_file_path = str(unlocked_path)
        statement.unlocked_sha256 = unl_sha
        statement.status = "READY_FOR_EXTRACTION"
        statement.unlocked_at = utcnow()

        _record_event(
            session,
            statement_id,
            "UNLOCK",
            "SKIPPED",
            message="PDF is not encrypted; stored original as unlocked",
        )
        _record_event(
            session,
            statement_id,
            "VALIDATION",
            "SUCCESS",
            message="Unlocked PDF validated and ready for transaction extraction",
        )
        session.commit()
        extract_and_validate_statement(session, statement)
        return statement

    # 4. If encrypted, attempt unlocking via password profile strategies
    statement.status = "UNLOCKING"
    prof_row, profile = get_profile_for_account(
        session, account_id, issuer=statement.issuer, card_last4=statement.card_last4 or ""
    )
    preferred_strategy = prof_row.strategy if prof_row else None

    candidates = generate_candidate_passwords(
        profile, issuer=statement.issuer, preferred_strategy=preferred_strategy
    )

    if not candidates:
        statement.status = "PASSWORD_REQUIRED"
        statement.error_code = "PASSWORD_REQUIRED"
        statement.error_message = (
            "Password profile not configured or no password candidates generated"
        )
        _record_event(
            session,
            statement_id,
            "PASSWORD",
            "FAILED",
            message=statement.error_message,
        )
        session.commit()
        return statement

    attempted_strategies: list[str] = []
    unlock_success = False
    unlocked_bytes: bytes | None = None
    matched_strategy: str | None = None

    _record_event(
        session,
        statement_id,
        "PASSWORD",
        "SUCCESS",
        message=f"Generated {len(candidates)} password candidate(s)",
        metadata={"candidate_count": len(candidates), "strategies": list({s for _, s in candidates})},
    )

    for pwd, strat_id in candidates:
        if strat_id not in attempted_strategies:
            attempted_strategies.append(strat_id)
        ok, res_bytes, _ = unlock_pdf(content, pwd)
        if ok and res_bytes:
            unlock_success = True
            unlocked_bytes = res_bytes
            matched_strategy = strat_id
            break

    if unlock_success and unlocked_bytes:
        unl_path, unl_sha = save_unlocked_statement(
            data_dir, account_id, statement_id, unlocked_bytes, statement.statement_date
        )
        statement.unlocked_file_path = str(unl_path)
        statement.unlocked_sha256 = unl_sha
        statement.password_strategy_id = matched_strategy
        statement.status = "READY_FOR_EXTRACTION"
        statement.unlocked_at = utcnow()
        statement.error_code = None
        statement.error_message = None

        enrich_statement_metadata(session, statement)

        _record_event(
            session,
            statement_id,
            "UNLOCK",
            "SUCCESS",
            message=f"PDF successfully unlocked using strategy '{matched_strategy}'",
            metadata={"strategy": matched_strategy, "attempted_strategies": attempted_strategies},
        )
        _record_event(
            session,
            statement_id,
            "VALIDATION",
            "SUCCESS",
            message="Unlocked PDF re-opened and validated successfully",
        )
        session.commit()
        extract_and_validate_statement(session, statement)
    else:
        statement.status = "PASSWORD_FAILED"
        statement.error_code = "PASSWORD_FAILED"
        statement.error_message = f"Could not unlock statement. Strategies attempted: {', '.join(attempted_strategies)}"

        _record_event(
            session,
            statement_id,
            "UNLOCK",
            "FAILED",
            message=statement.error_message,
            metadata={"attempted_strategies": attempted_strategies},
        )

    session.commit()
    return statement


def ingest_candidate(
    session: Session,
    candidate: DiscoveredStatementCandidate,
    source: MessageSource | None = None,
    attachment_bytes: bytes | None = None,
) -> CreditCardStatement:
    """Ingest a single discovered candidate statement with idempotency checks."""
    settings = get_settings()
    data_dir = settings.resolved_data_dir()

    # 1. Idempotency Check A: (source_email_id, source_attachment_id)
    if candidate.source_email_id and candidate.source_attachment_id:
        existing = session.scalars(
            select(CreditCardStatement).where(
                CreditCardStatement.source_email_id == candidate.source_email_id,
                CreditCardStatement.source_attachment_id == candidate.source_attachment_id,
            )
        ).first()
        if existing:
            return existing

    # 2. Get binary attachment content
    content = attachment_bytes or candidate.attachment_data
    if content is None and source and candidate.source_email_id and candidate.source_attachment_id:
        try:
            content = source.get_attachment(
                candidate.source_email_id, candidate.source_attachment_id
            )
        except Exception as exc:
            logger.error(f"Failed to download attachment {candidate.source_attachment_id}: {exc}")
            content = None

    if not content:
        # Create failed download record
        stmt_id = new_id()
        statement = CreditCardStatement(
            id=stmt_id,
            source_email_id=candidate.source_email_id,
            source_attachment_id=candidate.source_attachment_id,
            issuer=candidate.issuer,
            card_last4=candidate.card_last4,
            statement_period_start=candidate.statement_period_start,
            statement_period_end=candidate.statement_period_end,
            statement_date=candidate.statement_date,
            original_filename=candidate.original_filename,
            status="DOWNLOAD_FAILED",
            error_code="DOWNLOAD_FAILED",
            error_message="Could not download PDF attachment from Gmail",
        )
        session.add(statement)
        session.commit()
        _record_event(
            session, stmt_id, "DOWNLOAD", "FAILED", message=statement.error_message
        )
        return statement

    # 3. Idempotency Check B: SHA-256 hash deduplication
    sha256_hash = compute_sha256(content)
    existing_by_hash = session.scalars(
        select(CreditCardStatement).where(
            CreditCardStatement.original_sha256 == sha256_hash
        )
    ).first()
    if existing_by_hash:
        return existing_by_hash

    # 4. Create new statement entity
    stmt_type = getattr(candidate, "statement_type", "CREDIT_CARD") or "CREDIT_CARD"
    matched_account = find_matching_account(
        session, candidate.issuer, candidate.card_last4, stmt_type
    )
    if matched_account and matched_account.account_type == "BANK":
        stmt_type = "BANK_ACCOUNT"
    elif matched_account and matched_account.account_type == "CREDIT_CARD":
        stmt_type = "CREDIT_CARD"

    received_dt = None
    if candidate.extra_metadata and "received_at" in candidate.extra_metadata:
        rec_raw = candidate.extra_metadata["received_at"]
        if isinstance(rec_raw, str):
            try:
                received_dt = datetime.fromisoformat(rec_raw)
            except Exception:
                received_dt = None
        elif isinstance(rec_raw, datetime):
            received_dt = rec_raw

    stmt_id = new_id()
    statement = CreditCardStatement(
        id=stmt_id,
        account_id=matched_account.id if matched_account else None,
        source_email_id=candidate.source_email_id,
        source_attachment_id=candidate.source_attachment_id,
        issuer=candidate.issuer,
        statement_type=stmt_type,
        card_last4=candidate.card_last4 or (matched_account.card_last4 if matched_account else None),
        statement_period_start=candidate.statement_period_start,
        statement_period_end=candidate.statement_period_end,
        statement_date=candidate.statement_date,
        payment_due_date=getattr(candidate, "payment_due_date", None),
        total_amount_due=getattr(candidate, "total_amount_due", None),
        email_received_at=received_dt,
        original_filename=candidate.original_filename,
        status="DOWNLOADED",
    )
    session.add(statement)
    session.flush()

    _record_event(
        session,
        stmt_id,
        "DISCOVERY",
        "SUCCESS",
        message=f"Discovered statement email for {candidate.issuer}",
        metadata=candidate.extra_metadata,
    )
    _record_event(
        session,
        stmt_id,
        "DOWNLOAD",
        "SUCCESS",
        message=f"Downloaded {len(content)} bytes ({candidate.original_filename})",
        metadata={"filename": candidate.original_filename, "size_bytes": len(content)},
    )

    # 5. Process through vault pipeline
    return process_statement_bytes(session, statement, content, data_dir)


def unlock_statement_manually(
    session: Session,
    statement_id: str,
    password: str,
    save_to_profile: bool = False,
    strategy: str = "CUSTOM",
) -> tuple[bool, CreditCardStatement | None, str | None]:
    """Manually attempt to unlock a statement with user-provided password."""
    statement = session.get(CreditCardStatement, statement_id)
    if not statement:
        return False, None, "Statement not found"

    if not statement.original_file_path or not Path(statement.original_file_path).exists():
        return False, statement, "Original statement PDF file not found on disk"

    content = Path(statement.original_file_path).read_bytes()
    ok, unlocked_bytes, err = unlock_pdf(content, password)

    if not ok or not unlocked_bytes:
        _record_event(
            session,
            statement_id,
            "UNLOCK",
            "FAILED",
            message="Manual password unlock attempt failed",
        )
        return False, statement, err or "Incorrect password"

    settings = get_settings()
    data_dir = settings.resolved_data_dir()

    unl_path, unl_sha = save_unlocked_statement(
        data_dir, statement.account_id, statement.id, unlocked_bytes, statement.statement_date
    )
    statement.unlocked_file_path = str(unl_path)
    statement.unlocked_sha256 = unl_sha
    statement.password_strategy_id = strategy
    statement.status = "READY_FOR_EXTRACTION"
    statement.unlocked_at = utcnow()
    statement.error_code = None
    statement.error_message = None

    _record_event(
        session,
        statement_id,
        "UNLOCK",
        "SUCCESS",
        message="Statement successfully unlocked via manual password entry",
    )
    _record_event(
        session,
        statement_id,
        "VALIDATION",
        "SUCCESS",
        message="Unlocked PDF re-opened and validated successfully",
    )

    # Save to profile if requested and account linked
    if save_to_profile and statement.account_id:
        upsert_password_profile(
            session,
            account_id=statement.account_id,
            issuer=statement.issuer,
            strategy="CUSTOM",
            configuration={"custom_password": password},
        )

    session.commit()
    extract_and_validate_statement(session, statement)
    return True, statement, None


def extract_and_validate_statement(
    session: Session, statement: CreditCardStatement
) -> CreditCardStatement:
    """Run deterministic extraction, validation arithmetic, and alert reconciliation on unlocked statement PDF."""
    if not statement.unlocked_file_path or not Path(statement.unlocked_file_path).exists():
        statement.status = "EXTRACTION_FAILED"
        statement.error_code = "FILE_NOT_FOUND"
        statement.error_message = "Unlocked statement PDF file missing from disk"
        session.commit()
        return statement

    statement.status = "EXTRACTING"
    _record_event(
        session,
        statement.id,
        "EXTRACTION",
        "PENDING",
        message="Starting deterministic statement extraction",
    )
    session.commit()

    try:
        registry = get_statement_parser_registry()
        parsed_res = registry.detect_and_parse(
            statement.unlocked_file_path, expected_issuer=statement.issuer
        )

        statement.parser_name = parsed_res.parser_name
        statement.parser_version = parsed_res.parser_version
        statement.statement_type = parsed_res.statement_type

        # Clear any prior parsed statement children if re-extracting
        for acc in list(statement.statement_accounts):
            session.delete(acc)
        if statement.summary:
            session.delete(statement.summary)
        for sec in list(statement.sections):
            session.delete(sec)
        for tx in list(statement.transactions):
            session.delete(tx)
        session.flush()

        # 1. Persist Statement Accounts
        created_accounts: list[StatementAccount] = []
        for p_acc in parsed_res.accounts:
            matched_local = find_matching_account(
                session, p_acc.institution, p_acc.account_identifier, p_acc.account_type
            )
            s_acc = StatementAccount(
                id=new_id(),
                statement_id=statement.id,
                linked_account_id=matched_local.id if matched_local else statement.account_id,
                account_type=p_acc.account_type,
                institution=p_acc.institution,
                account_identifier=p_acc.account_identifier,
                masked_identifier=p_acc.masked_identifier,
                card_network=p_acc.card_network,
                account_name=p_acc.account_name,
                currency=p_acc.currency,
                opening_balance=p_acc.opening_balance,
                closing_balance=p_acc.closing_balance,
                credit_limit=p_acc.credit_limit,
                available_limit=p_acc.available_limit,
                cash_withdrawal_limit=p_acc.cash_withdrawal_limit,
                attribution_confidence=p_acc.attribution_confidence,
            )
            session.add(s_acc)
            created_accounts.append(s_acc)
        session.flush()

        # 2. Persist Statement Summary
        if parsed_res.summary:
            p_sum = parsed_res.summary
            s_sum = StatementSummary(
                id=new_id(),
                statement_id=statement.id,
                previous_balance=p_sum.previous_balance,
                payments=p_sum.payments,
                refunds=p_sum.refunds,
                purchases=p_sum.purchases,
                cash_withdrawals=p_sum.cash_withdrawals,
                fees=p_sum.fees,
                interest=p_sum.interest,
                other_charges=p_sum.other_charges,
                total_due=p_sum.total_due,
                minimum_due=p_sum.minimum_due,
                statement_date=p_sum.statement_date or statement.statement_date,
                due_date=p_sum.due_date or statement.payment_due_date,
                currency=p_sum.currency,
                extra_json=p_sum.extra_data,
            )
            session.add(s_sum)
            if p_sum.total_due is not None:
                statement.total_amount_due = p_sum.total_due
            if p_sum.minimum_due is not None:
                statement.payment_due_date = p_sum.due_date
            if p_sum.statement_date:
                statement.statement_date = p_sum.statement_date
            if p_sum.period_start:
                statement.statement_period_start = p_sum.period_start
            if p_sum.period_end:
                statement.statement_period_end = p_sum.period_end

        # 3. Persist Statement Sections
        for p_sec in parsed_res.sections:
            s_sec = StatementSection(
                id=new_id(),
                statement_id=statement.id,
                section_type=p_sec.section_type,
                page_start=p_sec.page_start,
                page_end=p_sec.page_end,
                source_text=p_sec.source_text,
            )
            session.add(s_sec)

        # 4. Persist Statement Transactions
        for p_tx in parsed_res.transactions:
            acc_id = None
            if p_tx.statement_account_index is not None and p_tx.statement_account_index < len(created_accounts):
                acc_id = created_accounts[p_tx.statement_account_index].id

            s_tx = StatementTransaction(
                id=new_id(),
                statement_id=statement.id,
                statement_account_id=acc_id,
                transaction_date=p_tx.transaction_date,
                transaction_time=p_tx.transaction_time,
                value_date=p_tx.value_date,
                description=p_tx.description,
                reference_number=p_tx.reference_number,
                transaction_type=p_tx.transaction_type,
                amount=p_tx.amount,
                debit_amount=p_tx.debit_amount,
                credit_amount=p_tx.credit_amount,
                currency=p_tx.currency,
                running_balance=p_tx.running_balance,
                source_page=p_tx.source_page,
                source_row=p_tx.source_row,
                raw_text=p_tx.raw_text,
                source_metadata=p_tx.source_metadata,
                attribution_status=p_tx.attribution_status,
                match_status="UNMATCHED",
            )
            session.add(s_tx)
        session.flush()

        _record_event(
            session,
            statement.id,
            "EXTRACTION",
            "SUCCESS",
            message=f"Extracted {len(parsed_res.transactions)} transactions across {len(created_accounts)} account(s)",
            metadata={"transaction_count": len(parsed_res.transactions), "parser": parsed_res.parser_name},
        )

        # 5. Run Statement Arithmetic Validation
        validator = StatementValidator()
        val_report = validator.validate(parsed_res)
        statement.validation_status = val_report.status
        statement.validation_details_json = val_report.details

        _record_event(
            session,
            statement.id,
            "VALIDATION_ARITHMETIC",
            "SUCCESS" if val_report.status == "VALIDATED" else "WARNING",
            message="; ".join(val_report.messages + val_report.warnings) or "Validation complete",
            metadata=val_report.details,
        )

        # 6. Run Reconciliation against Ledger Alerts
        reconcile_res = reconcile_statement_in_db(session, statement.id)
        _record_event(
            session,
            statement.id,
            "RECONCILIATION",
            "SUCCESS",
            message=f"Reconciliation: {reconcile_res['matched']} matched, {reconcile_res['possible_matches']} possible, {reconcile_res['liability_payments']} liability payments",
            metadata=reconcile_res,
        )

        statement.status = "VALIDATED" if val_report.status == "VALIDATED" else "REVIEW_REQUIRED"
        session.commit()
        return statement

    except Exception as exc:
        logger.error(f"Failed statement extraction for {statement.id}: {exc}", exc_info=True)
        statement.status = "EXTRACTION_FAILED"
        statement.error_code = "EXTRACTION_FAILED"
        statement.error_message = str(exc)
        _record_event(
            session,
            statement.id,
            "EXTRACTION",
            "FAILED",
            message=f"Extraction failed: {exc}",
        )
        session.commit()
        return statement


def upsert_password_profile(
    session: Session,
    account_id: str,
    issuer: str,
    strategy: str,
    configuration: dict[str, Any],
) -> PasswordProfile:
    """Create or update a password profile for an account."""
    profile = session.scalars(
        select(PasswordProfile).where(PasswordProfile.account_id == account_id)
    ).first()

    if profile:
        profile.issuer = issuer
        profile.strategy = strategy
        profile.configuration = configuration
        profile.updated_at = utcnow()
    else:
        profile = PasswordProfile(
            id=new_id(),
            account_id=account_id,
            issuer=issuer,
            strategy=strategy,
            configuration=configuration,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(profile)

    session.commit()
    return profile


def reprocess_locked_statements_for_account(
    session: Session, account_id: str
) -> int:
    """Attempt to unlock all PASSWORD_REQUIRED / PASSWORD_FAILED statements for an account with updated profile."""
    from expense_tracker.config import get_settings
    from pathlib import Path

    settings = get_settings()
    data_dir = settings.resolved_data_dir()
    locked_stmts = session.scalars(
        select(CreditCardStatement).where(
            CreditCardStatement.account_id == account_id,
            CreditCardStatement.status.in_(["PASSWORD_REQUIRED", "PASSWORD_FAILED"]),
        )
    ).all()
    unlocked_count = 0
    for stmt in locked_stmts:
        if stmt.original_file_path and Path(stmt.original_file_path).exists():
            content = Path(stmt.original_file_path).read_bytes()
            res = process_statement_bytes(session, stmt, content, data_dir)
            if res.status in ["READY_FOR_EXTRACTION", "UNLOCKED"]:
                unlocked_count += 1
    return unlocked_count


def discover_statements_from_source(
    session: Session,
    source: MessageSource,
    max_messages: int = 150,
) -> list[CreditCardStatement]:
    """Query message source for candidate statement emails and ingest them."""
    queries = [
        '(has:attachment OR filename:pdf) (from:axis.bank.in OR from:axisbank.com OR from:axis OR subject:"Money Quotient" OR subject:"Axis Bank Statement" OR subject:"Axis Bank")',
        '(has:attachment OR filename:pdf) (subject:statement OR subject:e-statement OR subject:"credit card")',
        '(has:attachment OR filename:pdf) (from:federalbank.co.in OR from:icicibank.com OR from:hdfcbank.net OR from:sbicard.com)',
    ]
    seen_ids: set[str] = set()
    message_ids: list[str] = []
    for q in queries:
        ids = source.list_message_ids(q, max_results=max_messages)
        for mid in ids:
            if mid not in seen_ids:
                seen_ids.add(mid)
                message_ids.append(mid)

    results: list[CreditCardStatement] = []

    for msg_id in message_ids:
        try:
            msg = source.get_message(msg_id)
            candidates = discover_statement_candidates([msg])
            for candidate in candidates:
                stmt = ingest_candidate(session, candidate, source=source)
                results.append(stmt)
        except Exception as exc:
            logger.warning(f"Error processing message {msg_id} for statements: {exc}")

    return results

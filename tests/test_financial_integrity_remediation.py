"""Regression tests for Phase 1 Financial & Data Integrity Invariants.

Covers:
1. Ingestion savepoint isolation: message 1 succeeds, message 2 fails, message 3 succeeds.
   Message 1 and 3 remain committed; outer IngestionRun remains valid.
2. Unclassified transaction classification creates the missing category posting.
3. Reclassifying an existing transaction updates the posting in-place without duplicate postings.
4. Bulk classification synchronizes double-entry postings across all updated transactions.
5. Reconciliation creates TransactionLinks strictly using LinkKind enum values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from mymonee.app import create_app
from mymonee.config import Settings
from mymonee.db.models import (
    Account,
    Category,
    FinancialEvent,
    IngestionRun,
    Posting,
    Transaction,
    new_id,
)
from mymonee.db.session import get_session_factory
from mymonee.domain.enums import IngestionRunStatus, LinkKind
from mymonee.ingestion.gmail.client import GmailMessage, MessageSource
from mymonee.ingestion.pipeline import run_ingestion_pipeline
from mymonee.services.ledger import verify_event_double_entry
from mymonee.services.reconciliation import pair_cross_account_transfers, pair_refunds
from mymonee.services.transactions import (
    classify_transaction,
    classify_transactions_bulk,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app={"data_dir": tmp_path, "name": "test-mymonee"},
        database={"filename": "test.db", "echo": False},
        privacy={"allow_external_ai": False},
    )


class MockFlakyMessageSource(MessageSource):
    """Source where message-2 raises an error during get_message or parsing."""

    def __init__(self, message_ids: list[str]) -> None:
        self._message_ids = message_ids

    def list_message_ids(self, query: str, max_results: int = 500) -> list[str]:  # noqa: ARG002
        return list(self._message_ids)

    def get_message(self, message_id: str) -> GmailMessage:
        if message_id == "msg-2-fails":
            raise RuntimeError("Corrupted MIME payload or network drop on message-2")

        return GmailMessage(
            id=message_id,
            thread_id=f"thread-{message_id}",
            sender="alerts@axis.bank.in",
            subject=f"Transaction alert for Axis Bank A/c {message_id}",
            snippet=f"Your A/c was debited with INR 500.00 for {message_id}",
            received_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
            internal_date_ms=1787220000000,
            headers={
                "from": "alerts@axis.bank.in",
                "subject": f"Transaction alert for Axis Bank A/c {message_id}",
            },
            label_ids=["INBOX"],
            body_text=f"Your A/c no. XX1022 is debited with INR 500.00 on 20-08-2026 at MERCHANT_{message_id}. Ref: REF_{message_id}",
            body_html=None,
        )

    def get_profile_history_id(self) -> str | None:
        return "12345"

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:  # noqa: ARG002
        return b""


def test_ingestion_partial_failure_isolation(tmp_path: Path) -> None:
    """Invariant 1: A failure on message 2 must roll back only message 2's savepoint.

    Message 1 and Message 3 must be saved, and the IngestionRun must remain valid.
    """
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    source = MockFlakyMessageSource(["msg-1-ok", "msg-2-fails", "msg-3-ok"])

    with session_factory() as session:
        result = run_ingestion_pipeline(
            session=session,
            settings=settings,
            source=source,
            ignore_watermark=True,
        )
        session.commit()

        assert result.status == IngestionRunStatus.PARTIAL
        assert result.parsing_errors == 1
        assert result.transactions_extracted == 2
        assert result.emails_processed == 2

        # Verify message 1 was committed
        tx1 = session.scalar(select(Transaction).where(Transaction.source_email_id == "msg-1-ok"))
        assert tx1 is not None
        assert float(tx1.amount) == 500.00

        # Verify message 3 was committed
        tx3 = session.scalar(select(Transaction).where(Transaction.source_email_id == "msg-3-ok"))
        assert tx3 is not None
        assert float(tx3.amount) == 500.00

        # Verify message 2 has NO transaction
        tx2 = session.scalar(select(Transaction).where(Transaction.source_email_id == "msg-2-fails"))
        assert tx2 is None

        # Verify outer IngestionRun record was NOT rolled back
        run_record = session.get(IngestionRun, result.run_id)
        assert run_record is not None
        assert run_record.status == IngestionRunStatus.PARTIAL
        assert run_record.parsing_errors == 1
        assert run_record.transactions_extracted == 2


def test_unclassified_transaction_classification_creates_posting(tmp_path: Path) -> None:
    """Invariant 2A: Classifying an unclassified transaction creates the missing category posting."""
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        # Create an account
        acc = Account(
            id=new_id(),
            name="Savings Account",
            account_type="BANK",
            is_asset=True,
            is_liability=False,
        )
        session.add(acc)

        # Create financial event with only the account posting (simulating unclassified ingestion)
        event = FinancialEvent(
            id=new_id(),
            event_type="purchase",
            event_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
            source="test",
            description="Supermarket debit",
        )
        session.add(event)

        session.add(
            Posting(
                id=new_id(),
                event_id=event.id,
                account_id=acc.id,
                amount=Decimal("1250.00"),
                direction="debit",
                posting_type="asset_decrease",
            )
        )

        tx = Transaction(
            id=new_id(),
            financial_event_id=event.id,
            source="test",
            transaction_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
            amount=Decimal("1250.00"),
            currency="INR",
            direction="debit",
            transaction_type="purchase",
            merchant_raw="SUPERMARKET",
            merchant_normalized="Supermarket",
            category_id=None,
            subcategory_id=None,
            needs_review=True,
        )
        session.add(tx)
        session.commit()

        # Before classification: only 1 posting exists; double-entry balance check fails
        balanced, debits, credits = verify_event_double_entry(session, event.id)
        assert balanced is False
        assert debits == Decimal("1250.00")
        assert credits == Decimal("0")

        # Fetch seeded Food category
        food = session.scalar(select(Category).where(Category.slug == "food"))
        assert food is not None

        # Classify transaction
        classify_transaction(session, tx.id, category_id=food.id, create_rule=False)
        session.commit()

        # After classification: exactly 2 postings exist and double-entry holds
        postings = session.scalars(select(Posting).where(Posting.event_id == event.id)).all()
        assert len(postings) == 2

        cat_postings = [p for p in postings if p.category_id == food.id]
        assert len(cat_postings) == 1
        assert float(cat_postings[0].amount) == 1250.00
        assert cat_postings[0].direction == "credit"
        assert cat_postings[0].posting_type == "expense"

        balanced, debits, credits = verify_event_double_entry(session, event.id)
        assert balanced is True
        assert debits == Decimal("1250.00")
        assert credits == Decimal("1250.00")


def test_reclassification_updates_existing_posting_in_place(tmp_path: Path) -> None:
    """Invariant 2B: Reclassifying Shopping -> Food updates the category posting in-place."""
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        acc = Account(id=new_id(), name="Bank", account_type="BANK", is_asset=True, is_liability=False)
        shopping = session.scalar(select(Category).where(Category.slug == "shopping"))
        food = session.scalar(select(Category).where(Category.slug == "food"))
        assert shopping is not None
        assert food is not None

        session.add(acc)
        session.flush()

        event = FinancialEvent(
            id=new_id(),
            event_type="purchase",
            event_date=datetime(2026, 8, 12, tzinfo=timezone.utc),
            source="test",
        )
        session.add(event)

        session.add(
            Posting(
                id=new_id(),
                event_id=event.id,
                account_id=acc.id,
                amount=Decimal("800.00"),
                direction="debit",
                posting_type="asset_decrease",
            )
        )

        # Initial posting under Shopping
        session.add(
            Posting(
                id=new_id(),
                event_id=event.id,
                category_id=shopping.id,
                amount=Decimal("800.00"),
                direction="credit",
                posting_type="expense",
            )
        )

        tx = Transaction(
            id=new_id(),
            financial_event_id=event.id,
            source="test",
            transaction_date=datetime(2026, 8, 12, tzinfo=timezone.utc),
            amount=Decimal("800.00"),
            currency="INR",
            direction="debit",
            transaction_type="purchase",
            category_id=shopping.id,
            needs_review=False,
        )
        session.add(tx)
        session.commit()

        # Reclassify from Shopping to Food
        classify_transaction(session, tx.id, category_id=food.id, create_rule=False)
        session.commit()

        postings = session.scalars(select(Posting).where(Posting.event_id == event.id)).all()
        # Must still be exactly 2 postings (no duplicate/stale posting!)
        assert len(postings) == 2

        cat_posting = [p for p in postings if p.category_id is not None][0]
        assert cat_posting.category_id == food.id
        assert float(cat_posting.amount) == 800.00

        balanced, debits, credits = verify_event_double_entry(session, event.id)
        assert balanced is True
        assert debits == Decimal("800.00")
        assert credits == Decimal("800.00")


def test_bulk_classification_syncs_postings(tmp_path: Path) -> None:
    """Invariant 2C: Bulk classification synchronizes postings for all updated rows."""
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        acc = Account(id=new_id(), name="Bank", account_type="BANK", is_asset=True, is_liability=False)
        travel = session.scalar(select(Category).where(Category.slug == "travel"))
        assert travel is not None
        session.add(acc)
        session.flush()

        tx_ids = []
        event_ids = []
        for i in range(3):
            event = FinancialEvent(
                id=new_id(),
                event_type="purchase",
                event_date=datetime(2026, 8, 15, tzinfo=timezone.utc),
                source="test",
            )
            session.add(event)
            session.add(
                Posting(
                    id=new_id(),
                    event_id=event.id,
                    account_id=acc.id,
                    amount=Decimal(str((i + 1) * 200)),
                    direction="debit",
                    posting_type="asset_decrease",
                )
            )
            tx = Transaction(
                id=new_id(),
                financial_event_id=event.id,
                source="test",
                transaction_date=datetime(2026, 8, 15, tzinfo=timezone.utc),
                amount=Decimal(str((i + 1) * 200)),
                currency="INR",
                direction="debit",
                category_id=None,
                needs_review=True,
            )
            session.add(tx)
            tx_ids.append(tx.id)
            event_ids.append(event.id)

        session.commit()

        # Bulk classify
        classify_transactions_bulk(session, transaction_ids=tx_ids, category_id=travel.id, create_rule=False)
        session.commit()

        # All events must now have balanced double-entry postings
        for eid in event_ids:
            balanced, debits, credits = verify_event_double_entry(session, eid)
            assert balanced is True
            assert debits == credits
            assert debits > 0


def test_reconciliation_uses_canonical_enums(tmp_path: Path) -> None:
    """Invariant 3: TransactionLink.kind uses canonical LinkKind enum values."""
    settings = _settings(tmp_path)
    _ = create_app(settings)
    session_factory = get_session_factory()

    with session_factory() as session:
        # 1. Test refund pairing
        orig = Transaction(
            id=new_id(),
            source="test",
            amount=Decimal("1500.00"),
            currency="INR",
            direction="debit",
            merchant_raw="AMAZON RETAIL",
            merchant_normalized="Amazon",
            transaction_date=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            needs_review=False,
        )
        ref = Transaction(
            id=new_id(),
            source="test",
            amount=Decimal("1500.00"),
            currency="INR",
            direction="credit",
            merchant_raw="AMAZON REFUND",
            merchant_normalized="Amazon",
            description="Refund from Amazon",
            transaction_date=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
            needs_review=True,
        )
        session.add_all([orig, ref])
        session.commit()

        links = pair_refunds(session)
        session.commit()

        assert len(links) == 1
        assert links[0].kind == LinkKind.REFUND.value
        assert links[0].kind == "refund"

        # 2. Test transfer pairing
        bank_debit = Transaction(
            id=new_id(),
            source="test",
            amount=Decimal("10000.00"),
            currency="INR",
            direction="debit",
            description="Credit card payment to Scapia",
            transaction_date=datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc),
            needs_review=True,
        )
        cc_credit = Transaction(
            id=new_id(),
            source="test",
            amount=Decimal("10000.00"),
            currency="INR",
            direction="credit",
            description="Payment received for Scapia card",
            transaction_date=datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc),
            needs_review=True,
        )
        session.add_all([bank_debit, cc_credit])
        session.commit()

        transfer_links = pair_cross_account_transfers(session)
        session.commit()

        assert len(transfer_links) == 1
        assert transfer_links[0].kind == LinkKind.TRANSFER.value
        assert transfer_links[0].kind == "transfer"

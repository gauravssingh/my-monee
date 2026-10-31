"""Embedding service: durable indexing jobs, vector persistence, and semantic search.

Design notes
------------
- `embedding_jobs` is a durable queue. A job survives process restarts, so an embedding service
  that is down delays indexing instead of losing work.
- Jobs are claimed with a single conditional ``UPDATE ... WHERE id IN (SELECT ... LIMIT)`` so two
  concurrent processors can never claim the same job; a per-batch heartbeat keeps actively
  progressing jobs out of the stale-recovery window.
- Jobs are processed in batches (embedding-g2 accepts up to 50 documents per request) and each
  successful batch is committed, so progress is durable and a crash costs at most one batch.
- The ledger is never mutated: this module only writes to `transaction_embeddings` and
  `embedding_jobs`. A failure here cannot corrupt a transaction.
- Every stored vector is pinned to the full compatibility key (model id, revision, preprocessing
  version, dimensions, normalization). Search only compares vectors that match the live key and
  whose content hash still matches the transaction, because vectors from a different key — or from
  stale content — are not comparable (see docs/EMBEDDINGS.md).
"""

from __future__ import annotations

import heapq
import logging
import time
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, joinedload

from mymonee.config import Settings, get_settings
from mymonee.db.models import (
    Category,
    DataIssueFlag,
    EmbeddingJob,
    Subcategory,
    Transaction,
    TransactionEmbedding,
    new_id,
)
from mymonee.domain.enums import DataIssueStatus, EmbeddingJobStatus, TransactionType
from mymonee.services.embeddings.base import (
    EmbeddingContractError,
    EmbeddingRequestRejected,
    EmbeddingsDisabled,
    EmbeddingServiceUnavailable,
    ServiceContract,
)
from mymonee.services.embeddings.client import EmbeddingClient
from mymonee.services.embeddings.text import transaction_content_hash, transaction_embedding_text
from mymonee.services.embeddings.vectors import cosine_similarity, pack_vector, unpack_vector
from mymonee.services.transactions import serialize_transaction

logger = logging.getLogger(__name__)

SOURCE_TYPE_TRANSACTION = "transaction"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def require_embeddings_enabled(settings: Settings) -> None:
    """Hard gate: embedding work never runs unless explicitly enabled in config."""
    if not settings.embeddings.enabled:
        raise EmbeddingsDisabled(
            "Embeddings are disabled by default. Set embeddings.enabled=true in "
            "config.local.yaml (and ensure embedding-g2 is running) to index the ledger."
        )


def build_client(settings: Settings | None = None) -> EmbeddingClient:
    """Build a client for the configured embedding service (requires embeddings.enabled)."""
    resolved = settings or get_settings()
    require_embeddings_enabled(resolved)
    return EmbeddingClient.from_settings(resolved)


def indexable_transaction_filters() -> list[Any]:
    """Row predicates matching the ledger view used by `list_transactions`.

    Semantic search should return the same transactions the ledger shows: real transactions
    (not `not_a_transaction`) without an open data-issue flag.
    """
    return [
        Transaction.transaction_type != TransactionType.NOT_A_TRANSACTION.value,
        ~exists(
            select(DataIssueFlag.id).where(
                DataIssueFlag.transaction_id == Transaction.id,
                DataIssueFlag.status == DataIssueStatus.OPEN,
            )
        ),
    ]


def compatibility_filters(contract: ServiceContract) -> list[Any]:
    """Row predicates selecting vectors comparable with the live service.

    This is the complete compatibility key (docs §6): a vector is only comparable with a query
    vector when the model, revision, preprocessing version, dimensions and normalization all
    match. Reused by search, status coverage, and job freshness so the rule lives in one place.
    """
    return [
        TransactionEmbedding.model_id == contract.model_id,
        TransactionEmbedding.model_revision == contract.model_revision,
        TransactionEmbedding.preprocessing_version == contract.preprocessing_version,
        TransactionEmbedding.dimensions == contract.dimensions,
        TransactionEmbedding.normalization == contract.normalization,
    ]


def _matches_contract(embedding: TransactionEmbedding, contract: ServiceContract | None) -> bool:
    """True when a stored vector is comparable with the live service (or the live key is unknown)."""
    return contract is None or embedding.compatibility_key == contract.compatibility_key


def _is_not_a_transaction(transaction: Transaction) -> bool:
    return str(transaction.transaction_type or "") == TransactionType.NOT_A_TRANSACTION.value


def _open_flag_tx_ids(session: Session, tx_ids: Iterable[str] | None = None) -> set[str]:
    ids = list(tx_ids) if tx_ids is not None else None
    if ids is not None and not ids:
        return set()
    stmt = select(DataIssueFlag.transaction_id).where(
        DataIssueFlag.status == DataIssueStatus.OPEN.value
    )
    if ids is not None:
        stmt = stmt.where(DataIssueFlag.transaction_id.in_(ids))
    return set(session.scalars(stmt))


def _resolve_names(session: Session, transaction: Transaction) -> tuple[str | None, str | None]:
    """Resolve category/subcategory names from the current foreign keys.

    A transaction whose `category_id` just changed may still hold a stale relationship object
    until the flush completes, so prefer an explicit lookup by id.
    """
    category_name: str | None = None
    if transaction.category_id:
        category = session.get(Category, transaction.category_id)
        if category is not None:
            category_name = category.name
        elif transaction.category is not None:
            category_name = transaction.category.name
    subcategory_name: str | None = None
    if transaction.subcategory_id:
        subcategory = session.get(Subcategory, transaction.subcategory_id)
        if subcategory is not None:
            subcategory_name = subcategory.name
        elif transaction.subcategory is not None:
            subcategory_name = transaction.subcategory.name
    return category_name, subcategory_name


def _rearm_job(job: EmbeddingJob, now: datetime) -> None:
    """Reset a job so it will be claimed again (content changed, stale, or forced)."""
    job.status = EmbeddingJobStatus.PENDING.value
    job.attempts = 0
    job.last_error = None
    job.next_attempt_at = None
    job.completed_at = None
    job.updated_at = now


def _ensure_job(session: Session, transaction_id: str, now: datetime) -> bool:
    """Insert a pending job for the transaction unless one already exists.

    Uses an ``INSERT ... ON CONFLICT DO NOTHING`` against the queue's unique
    (source_type, source_id, chunk_index) key, so two workers — or a worker and the lifecycle
    hook — can never create duplicate jobs for the same chunk. Returns True when a row was
    inserted by this call.
    """
    table = EmbeddingJob.__table__
    stmt = (
        sqlite_insert(table)
        .values(
            id=new_id(),
            source_type=SOURCE_TYPE_TRANSACTION,
            source_id=transaction_id,
            chunk_index=0,
            status=EmbeddingJobStatus.PENDING.value,
            attempts=0,
            last_error=None,
            next_attempt_at=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        .on_conflict_do_nothing(index_elements=["source_type", "source_id", "chunk_index"])
    )
    return session.execute(stmt).rowcount == 1


def _remove_job(session: Session, transaction_id: str) -> str:
    """Delete any queued job for a transaction; return the outcome label."""
    result = session.execute(
        delete(EmbeddingJob.__table__).where(
            EmbeddingJob.source_type == SOURCE_TYPE_TRANSACTION,
            EmbeddingJob.source_id == transaction_id,
        )
    )
    return "removed" if result.rowcount else "ineligible"


def enqueue_transaction_embedding(
    session: Session,
    transaction: Transaction,
    *,
    force: bool = False,
    contract: ServiceContract | None = None,
    flagged_ids: set[str] | None = None,
) -> str:
    """Ensure a durable job reflects one transaction's current content and eligibility.

    Returns one of ``"enqueued"``, ``"refreshed"``, ``"skipped"``, ``"removed"``, ``"ineligible"``.
    Called by the session flush hooks, so it must stay cheap and must never touch the network.
    """
    now = _utcnow()
    if _is_not_a_transaction(transaction):
        return _remove_job(session, transaction.id)

    if flagged_ids is None:
        flagged_ids = _open_flag_tx_ids(session, [transaction.id])
    if transaction.id in flagged_ids:
        return _remove_job(session, transaction.id)

    if not force:
        category_name, subcategory_name = _resolve_names(session, transaction)
        content_hash = transaction_content_hash(
            transaction_embedding_text(
                transaction, category_name=category_name, subcategory_name=subcategory_name
            )
        )
        for existing in session.scalars(
            select(TransactionEmbedding).where(
                TransactionEmbedding.transaction_id == transaction.id,
                TransactionEmbedding.chunk_index == 0,
            )
        ):
            if existing.content_hash == content_hash and _matches_contract(existing, contract):
                return "skipped"

    job = session.scalar(
        select(EmbeddingJob).where(
            EmbeddingJob.source_type == SOURCE_TYPE_TRANSACTION,
            EmbeddingJob.source_id == transaction.id,
            EmbeddingJob.chunk_index == 0,
        )
    )
    if job is None:
        return "enqueued" if _ensure_job(session, transaction.id, now) else "skipped"
    if job.status == EmbeddingJobStatus.PENDING.value and not force:
        return "skipped"
    _rearm_job(job, now)
    return "refreshed"


def cancel_transaction_embedding(session: Session, transaction_id: str) -> bool:
    """Drop any queued job for a transaction; used when the ledger row disappears.

    The stored vector (if any) cascades with the transaction row itself, so search cannot
    surface a deleted transaction. Returns True when a job was actually removed.
    """
    return _remove_job(session, transaction_id) == "removed"


def enqueue_transaction_embeddings(
    session: Session,
    *,
    limit: int | None = None,
    force: bool = False,
    contract: ServiceContract | None = None,
) -> dict[str, int]:
    """Create or refresh durable jobs for transactions that need a current vector.

    A transaction is skipped when a stored vector already exists for the same chunk and content,
    and (when `contract` is supplied) for the same compatibility key. Pass `force=True` to
    re-index everything. Already-failed jobs are reset, so a re-run is the recovery path.

    Insertion is race-safe (``ON CONFLICT DO NOTHING`` on the queue's unique key), and a stale read
    snapshot from a competing writer is retried once against a fresh one.
    """
    for attempt in range(2):
        try:
            return _enqueue_transaction_embeddings_once(
                session, limit=limit, force=force, contract=contract
            )
        except OperationalError:  # SQLITE_BUSY / snapshot invalidation from a competing writer
            session.rollback()
            if attempt == 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def _enqueue_transaction_embeddings_once(
    session: Session,
    *,
    limit: int | None,
    force: bool,
    contract: ServiceContract | None,
) -> dict[str, int]:
    stmt = (
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.subcategory))
        .where(*indexable_transaction_filters())
        .order_by(Transaction.transaction_date.asc(), Transaction.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    transactions = list(session.scalars(stmt))

    stored: dict[tuple[str, int], list[TransactionEmbedding]] = defaultdict(list)
    for row in session.scalars(select(TransactionEmbedding)):
        stored[(row.transaction_id, row.chunk_index)].append(row)
    jobs = {
        (job.source_id, job.chunk_index): job
        for job in session.scalars(
            select(EmbeddingJob).where(EmbeddingJob.source_type == SOURCE_TYPE_TRANSACTION)
        )
    }

    summary = {"candidates": len(transactions), "enqueued": 0, "skipped": 0, "refreshed": 0}
    now = _utcnow()

    for transaction in transactions:
        text = transaction_embedding_text(transaction)
        content_hash = transaction_content_hash(text)
        is_fresh = any(
            existing.content_hash == content_hash and _matches_contract(existing, contract)
            for existing in stored.get((transaction.id, 0), [])
        )
        if is_fresh and not force:
            summary["skipped"] += 1
            continue

        job = jobs.get((transaction.id, 0))
        if job is None:
            if _ensure_job(session, transaction.id, now):
                summary["enqueued"] += 1
            else:
                # Another worker inserted the job first: it is already queued.
                summary["skipped"] += 1
        else:
            if job.status == EmbeddingJobStatus.PENDING.value and not force:
                summary["skipped"] += 1
                continue
            # Re-arm the job: content changed, the vector is stale, or a forced re-index.
            _rearm_job(job, now)
            summary["refreshed"] += 1

    session.commit()
    return summary


# ------------------------------------------------------------------ claiming


def _claimable_filters(table: Any, now: datetime, stale_before: datetime) -> list[Any]:
    return [
        table.c.source_type == SOURCE_TYPE_TRANSACTION,
        or_(
            table.c.status == EmbeddingJobStatus.PENDING.value,
            # A "running" job whose run died (crash, kill) is reclaimable after the stale window,
            # but an active run heartbeats `updated_at` every batch, so live work is never stolen.
            and_(
                table.c.status == EmbeddingJobStatus.RUNNING.value,
                table.c.updated_at <= stale_before,
            ),
        ),
        or_(table.c.next_attempt_at.is_(None), table.c.next_attempt_at <= now),
    ]


def _claim_jobs(session: Session, *, limit: int, settings: Settings) -> list[EmbeddingJob]:
    """Atomically claim due jobs for this worker.

    A single conditional ``UPDATE ... WHERE id IN (SELECT ... LIMIT) ... RETURNING id`` is used so
    SQLite's writer serialization guarantees each due job is handed to exactly one worker. If a
    competing writer invalidated our read snapshot, SQLite refuses the write; we roll back and retry
    with a fresh snapshot instead of claiming a stale row.
    """
    table = EmbeddingJob.__table__
    now = _utcnow()
    stale_before = now - timedelta(seconds=settings.embeddings.stale_job_seconds)
    candidates = (
        select(table.c.id)
        .where(*_claimable_filters(table, now, stale_before))
        .order_by(table.c.created_at.asc())
        .limit(limit)
    )
    stmt = (
        update(table)
        .where(table.c.id.in_(candidates))
        .where(*_claimable_filters(table, now, stale_before))
        .values(status=EmbeddingJobStatus.RUNNING.value, updated_at=now)
        .returning(table.c.id)
    )

    claimed_ids: list[str] = []
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            claimed_ids = list(session.execute(stmt).scalars().all())
            session.commit()
            last_error = None
            break
        except OperationalError as exc:  # SQLITE_BUSY / snapshot invalidation
            session.rollback()
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error
    if not claimed_ids:
        return []
    return list(
        session.scalars(
            select(EmbeddingJob)
            .where(EmbeddingJob.id.in_(claimed_ids))
            .order_by(EmbeddingJob.created_at.asc())
        )
    )


def _heartbeat(session: Session, jobs: list[EmbeddingJob]) -> None:
    """Refresh the lease on claimed jobs so a concurrent worker cannot reclaim active work."""
    if not jobs:
        return
    session.execute(
        update(EmbeddingJob)
        .where(EmbeddingJob.id.in_([job.id for job in jobs]))
        .values(updated_at=_utcnow())
    )
    session.commit()


# ------------------------------------------------------------------ processing


def process_embedding_jobs(
    session: Session,
    *,
    limit: int = 200,
    settings: Settings | None = None,
    client: EmbeddingClient | None = None,
    contract: ServiceContract | None = None,
) -> dict[str, int]:
    """Process due jobs: embed in batches, persist vectors, and record failures with backoff.

    Transient failures (service down, 503) defer the job with exponential backoff up to
    `embeddings.max_attempts` attempts; permanent rejections and contract violations mark the job
    failed after isolating the offending record. Every claimed job is left in a controlled state
    (`pending`, `done`, or `failed`) even when the service misbehaves. Never raises for
    service-side failures.
    """
    resolved = settings or get_settings()
    require_embeddings_enabled(resolved)

    client = client or EmbeddingClient.from_settings(resolved)
    contract = contract or client.contract()

    summary = {
        "claimed": 0,
        "embedded": 0,
        "failed": 0,
        "retried": 0,
        "dropped": 0,
        "skipped": 0,
        "batches": 0,
    }
    claimable = _claim_jobs(session, limit=limit, settings=resolved)
    if not claimable:
        return summary
    summary["claimed"] = len(claimable)

    batch_size = max(1, min(resolved.embeddings.batch_size, contract.max_batch_size))
    for start in range(0, len(claimable), batch_size):
        batch = claimable[start : start + batch_size]
        summary["batches"] += 1
        _heartbeat(session, batch)
        try:
            _process_batch(session, client, contract, batch, summary, resolved)
        except Exception as exc:
            logger.exception("embedding batch failed unexpectedly")
            session.rollback()
            _defer_jobs_by_ids(session, [job.id for job in batch], exc, resolved, summary)
    return summary


def _process_batch(
    session: Session,
    client: EmbeddingClient,
    contract: ServiceContract,
    batch: list[EmbeddingJob],
    summary: dict[str, int],
    settings: Settings,
) -> None:
    """Embed and persist one batch of claimed jobs, isolating failures to that batch."""
    source_ids = [job.source_id for job in batch]
    transactions = {
        transaction.id: transaction
        for transaction in session.scalars(
            select(Transaction)
            .options(joinedload(Transaction.category), joinedload(Transaction.subcategory))
            .where(Transaction.id.in_(source_ids))
        )
    }
    flagged = _open_flag_tx_ids(session, source_ids)

    active: list[EmbeddingJob] = []
    for job in batch:
        transaction = transactions.get(job.source_id)
        # The source row is gone (deleted) or no longer indexable (excluded, or open data issue).
        if transaction is None or _is_not_a_transaction(transaction) or job.source_id in flagged:
            session.delete(job)
            summary["dropped"] += 1
        else:
            active.append(job)
    if not active:
        session.commit()
        return

    texts = {job.id: transaction_embedding_text(transactions[job.source_id]) for job in active}
    hashes = {job.id: transaction_content_hash(texts[job.id]) for job in active}

    existing: dict[str, set[str]] = defaultdict(set)
    for row in session.scalars(
        select(TransactionEmbedding)
        .where(TransactionEmbedding.transaction_id.in_([job.source_id for job in active]))
        .where(*compatibility_filters(contract))
    ):
        existing[row.transaction_id].add(row.content_hash)

    pending: list[EmbeddingJob] = []
    for job in active:
        if hashes[job.id] in existing.get(job.source_id, set()):
            # Content is unchanged and already stored for the live key: no inference needed.
            _mark_done(session, job)
            summary["skipped"] += 1
        else:
            pending.append(job)
    if not pending:
        session.commit()
        return

    documents = [{"id": job.id, "title": None, "text": texts[job.id]} for job in pending]

    try:
        vectors = client.embed_documents(documents)
    except EmbeddingRequestRejected as exc:
        # Permanent rejection (for example a field longer than the service's character limit).
        # Fall back to one request per document so a single bad record cannot sink the batch.
        _embed_individually(session, client, contract, pending, texts, summary, settings, exc)
        return
    except EmbeddingServiceUnavailable as exc:
        logger.warning("embedding service unavailable (%s); deferring %s job(s)", exc, len(pending))
        _defer_jobs(session, pending, exc, settings, summary)
        return
    except EmbeddingContractError as exc:
        logger.warning("embedding contract violated (%s); failing %s job(s)", exc, len(pending))
        _fail_jobs(session, pending, exc, summary)
        return
    except Exception as exc:  # noqa: BLE001 - unexpected service/parse failure: retry, don't strand
        logger.warning("unexpected embedding failure (%s); deferring %s job(s)", exc, len(pending))
        _defer_jobs(session, pending, exc, settings, summary)
        return

    _persist_vectors(session, contract, pending, texts, vectors, summary)
    session.commit()


def _embed_individually(
    session: Session,
    client: EmbeddingClient,
    contract: ServiceContract,
    jobs: list[EmbeddingJob],
    texts: dict[str, str],
    summary: dict[str, int],
    settings: Settings,
    batch_error: EmbeddingRequestRejected,
) -> None:
    """Retry a rejected batch one document at a time to identify the offending record."""
    for job in jobs:
        document = [{"id": job.id, "title": None, "text": texts[job.id]}]
        try:
            vectors = client.embed_documents(document)
        except EmbeddingRequestRejected as exc:
            _fail_jobs(session, [job], exc, summary)
        except EmbeddingServiceUnavailable as exc:
            _defer_jobs(session, [job], exc, settings, summary)
        except EmbeddingContractError as exc:
            _fail_jobs(session, [job], exc, summary)
        except Exception as exc:  # noqa: BLE001
            _defer_jobs(session, [job], exc, settings, summary)
        else:
            _persist_vectors(session, contract, [job], texts, vectors, summary)
    session.commit()
    logger.warning("batch rejected (%s); processed %s job(s) individually", batch_error, len(jobs))


def _mark_done(session: Session, job: EmbeddingJob) -> None:
    now = _utcnow()
    job.status = EmbeddingJobStatus.DONE.value
    job.completed_at = now
    job.updated_at = now
    job.last_error = None


def _persist_vectors(
    session: Session,
    contract: ServiceContract,
    jobs: list[EmbeddingJob],
    texts: dict[str, str],
    vectors: list[list[float]],
    summary: dict[str, int],
) -> None:
    """Store one vector per job, pinned to the producing model revision."""
    now = _utcnow()
    for job, vector in zip(jobs, vectors, strict=True):
        existing = session.scalar(
            select(TransactionEmbedding)
            .where(TransactionEmbedding.transaction_id == job.source_id)
            .where(TransactionEmbedding.chunk_index == job.chunk_index)
            .where(TransactionEmbedding.model_revision == contract.model_revision)
        )
        content_hash = transaction_content_hash(texts[job.id])
        if existing is None:
            session.add(
                TransactionEmbedding(
                    transaction_id=job.source_id,
                    chunk_index=job.chunk_index,
                    model_id=contract.model_id,
                    model_revision=contract.model_revision,
                    preprocessing_version=contract.preprocessing_version,
                    dimensions=contract.dimensions,
                    normalization=contract.normalization,
                    content_hash=content_hash,
                    vector=pack_vector(vector),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing.model_id = contract.model_id
            existing.preprocessing_version = contract.preprocessing_version
            existing.dimensions = contract.dimensions
            existing.normalization = contract.normalization
            existing.content_hash = content_hash
            existing.vector = pack_vector(vector)
            existing.updated_at = now

        _mark_done(session, job)
        summary["embedded"] += 1


def _defer_jobs(
    session: Session,
    jobs: list[EmbeddingJob],
    error: Exception,
    settings: Settings,
    summary: dict[str, int],
) -> None:
    """Count a failed attempt; retry with exponential backoff or give up permanently."""
    now = _utcnow()
    ceiling = max(1, settings.embeddings.max_attempts)
    for job in jobs:
        job.attempts += 1
        job.last_error = str(error)[:500]
        job.updated_at = now
        if job.attempts >= ceiling:
            job.status = EmbeddingJobStatus.FAILED.value
            summary["failed"] += 1
        else:
            job.status = EmbeddingJobStatus.PENDING.value
            job.next_attempt_at = now + timedelta(
                seconds=settings.embeddings.backoff_seconds * (2 ** (job.attempts - 1))
            )
            summary["retried"] += 1
    session.commit()


def _defer_jobs_by_ids(
    session: Session,
    job_ids: list[str],
    error: Exception,
    settings: Settings,
    summary: dict[str, int],
) -> None:
    """Backstop used after a rollback: re-load the jobs and defer them by id."""
    if not job_ids:
        return
    jobs = list(session.scalars(select(EmbeddingJob).where(EmbeddingJob.id.in_(job_ids))))
    _defer_jobs(session, jobs, error, settings, summary)


def _failure_label(error: Exception) -> str:
    if isinstance(error, EmbeddingRequestRejected):
        return "rejected by embedding service"
    if isinstance(error, EmbeddingContractError):
        return "embedding contract violated"
    return "embedding failed"


def _fail_jobs(
    session: Session, jobs: list[EmbeddingJob], error: Exception, summary: dict[str, int]
) -> None:
    """Mark jobs as terminally failed: retrying cannot fix a rejected or contract-violating request."""
    now = _utcnow()
    label = _failure_label(error)
    for job in jobs:
        job.attempts += 1
        job.status = EmbeddingJobStatus.FAILED.value
        job.last_error = f"{label}: {error}"[:500]
        job.updated_at = now
        summary["failed"] += 1
    session.commit()


# ------------------------------------------------------------------ entry points


def index_transactions(
    session: Session,
    *,
    limit: int | None = None,
    force: bool = False,
    settings: Settings | None = None,
    client: EmbeddingClient | None = None,
) -> dict[str, Any]:
    """Backfill convenience: enqueue missing vectors, then process every due job."""
    resolved = settings or get_settings()
    require_embeddings_enabled(resolved)

    client = client or EmbeddingClient.from_settings(resolved)
    contract = client.contract()

    enqueued = enqueue_transaction_embeddings(session, limit=limit, force=force, contract=contract)
    processed = process_embedding_jobs(
        session,
        limit=limit if limit is not None else 10_000,
        settings=resolved,
        client=client,
        contract=contract,
    )
    return {"enqueue": enqueued, "process": processed, "contract": contract}


def search_transactions_semantic(
    session: Session,
    query: str,
    *,
    limit: int = 25,
    settings: Settings | None = None,
    client: EmbeddingClient | None = None,
    contract: ServiceContract | None = None,
) -> list[dict[str, Any]]:
    """Rank stored transaction vectors by cosine similarity to a search query.

    Only vectors whose full compatibility key matches the live service **and** whose content hash
    still matches the transaction's current text are compared. A vector that is stale (the
    transaction was edited and not yet re-indexed) or incompatible is skipped rather than returned.
    Brute-force cosine ranking is intentional at ledger scale — see docs/EMBEDDINGS.md.
    """
    text = query.strip()
    if not text:
        raise ValueError("search query must not be empty")

    resolved = settings or get_settings()
    require_embeddings_enabled(resolved)

    client = client or EmbeddingClient.from_settings(resolved)
    contract = contract or client.contract()
    query_vector = client.embed_query(text)

    rows = session.execute(
        select(TransactionEmbedding, Transaction)
        .join(Transaction, Transaction.id == TransactionEmbedding.transaction_id)
        .options(joinedload(Transaction.category), joinedload(Transaction.subcategory))
        .where(*compatibility_filters(contract))
        .where(TransactionEmbedding.chunk_index == 0)
        .where(*indexable_transaction_filters())
    ).all()

    scored: list[tuple[float, Transaction]] = []
    stale = 0
    for embedding_row, transaction in rows:
        # Guard against serving an embedding the transaction has outgrown since it was written.
        current_hash = transaction_content_hash(transaction_embedding_text(transaction))
        if current_hash != embedding_row.content_hash:
            stale += 1
            continue
        try:
            score = cosine_similarity(query_vector, unpack_vector(embedding_row.vector))
        except ValueError:
            # Dimension mismatch inside the database: skip rather than compare incompatible spaces.
            logger.warning(
                "skipping embedding %s for transaction %s: incompatible dimensions",
                embedding_row.id,
                transaction.id,
            )
            continue
        scored.append((score, transaction))

    if stale:
        logger.debug("semantic search skipped %s stale embedding(s) awaiting re-index", stale)

    top = heapq.nlargest(limit, scored, key=lambda pair: pair[0])
    return [
        {
            "transaction_id": transaction.id,
            "score": round(score, 6),
            "model_revision": contract.model_revision,
            "transaction": serialize_transaction(transaction),
        }
        for score, transaction in top
    ]


def _freshness_counts(session: Session, contract: ServiceContract | None) -> tuple[int, int]:
    """Return (indexable_transactions, stale_or_missing) against the live key.

    With `contract=None` any stored vector counts (used when the service cannot be queried), which
    still detects content drift.
    """
    stored: dict[str, set[str]] = defaultdict(set)
    embedding_stmt = select(TransactionEmbedding)
    if contract is not None:
        embedding_stmt = embedding_stmt.where(*compatibility_filters(contract))
    for row in session.scalars(embedding_stmt):
        stored[row.transaction_id].add(row.content_hash)

    indexable = session.scalars(
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.subcategory))
        .where(*indexable_transaction_filters())
    )
    total = 0
    stale = 0
    for transaction in indexable:
        total += 1
        content_hash = transaction_content_hash(transaction_embedding_text(transaction))
        if content_hash not in stored.get(transaction.id, set()):
            stale += 1
    return total, stale


def embedding_status(
    session: Session, *, settings: Settings | None = None, client: EmbeddingClient | None = None
) -> dict[str, Any]:
    """Report indexing coverage, stored vector revisions, and live service compatibility.

    `needs_reindex` is content-drift based: a transaction counts as needing re-indexing when it has
    no stored vector whose content hash matches its current text for the live compatibility key.
    Never raises for a missing service: an unreachable service is reported, not thrown, so this can
    be used as a diagnostic.
    """
    resolved = settings or get_settings()
    resolved_client = client or (
        EmbeddingClient.from_settings(resolved) if resolved.embeddings.enabled else None
    )

    job_counts = {
        status: count
        for status, count in session.execute(
            select(EmbeddingJob.status, func.count()).group_by(EmbeddingJob.status)
        ).all()
    }
    by_revision = {
        (revision or "unknown"): count
        for revision, count in session.execute(
            select(TransactionEmbedding.model_revision, func.count()).group_by(
                TransactionEmbedding.model_revision
            )
        ).all()
    }

    status: dict[str, Any] = {
        "enabled": resolved.embeddings.enabled,
        "base_url": resolved.embeddings.base_url,
        "jobs": job_counts,
        "stored_vectors": sum(by_revision.values()),
        "stored_by_revision": by_revision,
        "indexable_transactions": None,
        "stale_vectors": None,
        "current_revision_vectors": None,
        "needs_reindex": None,
        "service": None,
    }

    if not resolved.embeddings.enabled:
        status["indexable_transactions"] = (
            session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(*indexable_transaction_filters())
            )
            or 0
        )
        return status

    # Contract-free coverage first, so drift is visible even when the service is unreachable.
    total, stale = _freshness_counts(session, None)
    status["indexable_transactions"] = total
    status["stale_vectors"] = stale
    status["current_revision_vectors"] = total - stale
    status["needs_reindex"] = stale > 0

    try:
        contract = resolved_client.contract(refresh=True)
    except (EmbeddingServiceUnavailable, EmbeddingRequestRejected) as exc:
        status["service"] = {"reachable": False, "error": str(exc)}
        return status
    except EmbeddingContractError as exc:
        # Reachable but not speaking the documented contract: report, don't crash a status command.
        status["service"] = {"reachable": True, "compatible": False, "error": str(exc)}
        return status

    total, stale = _freshness_counts(session, contract)
    status["indexable_transactions"] = total
    status["stale_vectors"] = stale
    status["current_revision_vectors"] = total - stale
    status["needs_reindex"] = stale > 0
    status["service"] = {
        "reachable": True,
        "compatible": True,
        "model_id": contract.model_id,
        "model_revision": contract.model_revision,
        "preprocessing_version": contract.preprocessing_version,
        "dimensions": contract.dimensions,
        "normalization": contract.normalization,
        "max_batch_size": contract.max_batch_size,
        "service_version": contract.service_version,
        "device": contract.device,
        "precision": contract.precision,
    }
    return status

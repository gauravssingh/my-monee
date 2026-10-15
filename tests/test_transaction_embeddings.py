"""Embedding-g2 integration: durable indexing jobs, vector persistence, and semantic search.

Most tests run against an in-process fake embedding service (`FakeEmbeddingService`) that speaks
the documented embedding-g2 contract, so the real HTTP client path is exercised without needing
the model or the network. Two live tests, gated behind MYMONEE_TEST_EMBEDDINGS_LIVE=1, verify the
same code against a running embedding-g2 instance.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import urllib.error
import urllib.request
from argparse import Namespace
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text

from mymonee.app import create_app
from mymonee.config import Settings
from mymonee.db.models import (
    Category,
    DataIssueFlag,
    EmbeddingJob,
    Subcategory,
    Transaction,
    TransactionEmbedding,
)
from mymonee.db.session import get_session_factory, init_db
from mymonee.domain.enums import EmbeddingJobStatus
from mymonee.services.embeddings import (
    EmbeddingClient,
    EmbeddingContractError,
    EmbeddingRequestRejected,
    EmbeddingsDisabled,
    EmbeddingServiceUnavailable,
    cosine_similarity,
    embedding_status,
    enqueue_transaction_embeddings,
    index_transactions,
    pack_vector,
    process_embedding_jobs,
    search_transactions_semantic,
    transaction_content_hash,
    transaction_embedding_text,
    unpack_vector,
    validate_vector,
    vector_norm,
)
from mymonee.services.embeddings import client as emb_client
from mymonee.services.embeddings import service as emb_service
from mymonee.services.transactions import (
    classify_transaction,
    exclude_as_non_transaction,
    mark_reimbursed,
)

LIVE_BASE_URL = os.environ.get("EMBEDDING_G2_URL", "http://127.0.0.1:8001")


# --------------------------------------------------------------------------- fake service


class FakeEmbeddingService:
    """In-process stand-in for embedding-g2 that speaks the documented contract.

    Vectors use signed feature hashing over word tokens, so texts that share words really are
    closer in cosine space — retrieval orderings in these tests are meaningful, not canned.
    """

    OVERSIZE_MARKER = "OVERSIZE-MARKER"

    def __init__(
        self,
        *,
        model_revision: str = "rev-a",
        dimensions: int = 64,
        max_batch_size: int = 50,
        normalization: bool = True,
        normalize_response: bool = True,
        reorder_batch: bool = False,
        forced_status: int | None = None,
        forced_code: str = "FORCED_STATUS",
        retry_after: str | None = None,
        raw_body: bytes | None = None,
    ) -> None:
        self.model_revision = model_revision
        self.dimensions = dimensions
        self.max_batch_size = max_batch_size
        self.normalization = normalization
        self.normalize_response = normalize_response
        # Fault injection for error-handling tests.
        self.reorder_batch = reorder_batch
        self.forced_status = forced_status
        self.forced_code = forced_code
        self.retry_after = retry_after
        self.raw_body = raw_body
        self.requests: list[tuple[str, dict]] = []
        self.transient_failures: dict[str, int] = defaultdict(int)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle ----------------------------------------------------------

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args) -> None:
                pass

            def _send(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_raw(
                self,
                status: int,
                body: bytes,
                content_type: str = "application/json",
                extra_headers=None,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for name, value in (extra_headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def _guard(self, path: str) -> bool:
                """Return True when a scripted transient failure consumed this request."""
                if service.transient_failures[path] > 0:
                    service.transient_failures[path] -= 1
                    self._send(
                        503, {"error": {"code": "SERVER_BUSY", "message": "busy", "details": None}}
                    )
                    return True
                return False

            def do_GET(self) -> None:
                service.requests.append(("GET", {"path": self.path}))
                if self._guard(self.path):
                    return
                if self.path == "/health":
                    self._send(
                        200,
                        {
                            "status": "healthy",
                            "model_loaded": True,
                            "model_identifier": "fake/embedding-model",
                            "embedding_dimensions": service.dimensions,
                            "execution_device": "metal",
                            "model_precision": "bfloat16",
                            "service_version": "1.0.0-test",
                        },
                    )
                elif self.path == "/v1/info":
                    self._send(
                        200,
                        {
                            "model_id": "fake/embedding-model",
                            "model_revision": service.model_revision,
                            "embedding_dimensions": service.dimensions,
                            "device": "metal",
                            "precision": "bfloat16",
                            "normalization": service.normalization,
                            "supported_input_types": ["query", "document"],
                            "preprocessing_version": "v1.0.0",
                            "max_seq_length": 2048,
                            "max_batch_size": service.max_batch_size,
                            "max_input_length": 8192,
                        },
                    )
                else:
                    self._send(
                        404,
                        {"error": {"code": "HTTP_404", "message": "Not Found", "details": None}},
                    )

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length).decode("utf-8")
                body = json.loads(raw) if raw else {}
                service.requests.append(("POST", {"path": self.path, "body": body}))

                if self._guard(self.path):
                    return

                if self.path.startswith("/v1/embed"):
                    if service.forced_status is not None:
                        self._send_raw(
                            service.forced_status,
                            json.dumps(
                                {"error": {"code": service.forced_code, "message": "forced"}}
                            ).encode(),
                            extra_headers=(
                                {"Retry-After": service.retry_after}
                                if service.retry_after
                                else None
                            ),
                        )
                        return
                    if service.raw_body is not None:
                        self._send_raw(200, service.raw_body)
                        return

                texts = self._texts_for(self.path, body)
                if texts is None:
                    self._send(
                        404,
                        {"error": {"code": "HTTP_404", "message": "Not Found", "details": None}},
                    )
                    return
                if any(service.OVERSIZE_MARKER in text for text in texts):
                    self._send(
                        413,
                        {
                            "error": {
                                "code": "INPUT_TOO_LARGE",
                                "message": "Field 'document[0].text' length exceeds maximum allowed.",
                                "details": {
                                    "field": "document[0].text",
                                    "length": 9000,
                                    "max_length": 8192,
                                },
                            }
                        },
                    )
                    return
                if len(texts) > service.max_batch_size:
                    self._send(
                        413,
                        {
                            "error": {
                                "code": "BATCH_SIZE_EXCEEDED",
                                "message": f"Requested batch size ({len(texts)}) exceeds maximum allowed ({service.max_batch_size}).",
                                "details": {
                                    "requested_size": len(texts),
                                    "max_batch_size": service.max_batch_size,
                                },
                            }
                        },
                    )
                    return

                if self.path == "/v1/embed/query":
                    self._send(
                        200,
                        {
                            "embedding": service.embed(texts[0]),
                            "dimensions": service.dimensions,
                            "model_identifier": "fake/embedding-model",
                            "processing_time_ms": 1.0,
                            "truncation_info": {
                                "id": None,
                                "truncated": False,
                                "token_count": len(texts[0].split()),
                                "max_seq_length": 2048,
                            },
                        },
                    )
                else:
                    ids = [document["id"] for document in body.get("documents", [])]
                    items = [
                        {"id": document_id, "embedding": service.embed(text)}
                        for document_id, text in zip(ids, texts, strict=True)
                    ]
                    if service.reorder_batch:
                        items = list(reversed(items))
                    self._send(
                        200,
                        {
                            "embeddings": items,
                            "dimensions": service.dimensions,
                            "model_identifier": "fake/embedding-model",
                            "processing_time_ms": 1.0,
                            "truncation_info": [
                                {
                                    "id": document_id,
                                    "truncated": False,
                                    "token_count": len(text.split()),
                                    "max_seq_length": 2048,
                                }
                                for document_id, text in zip(ids, texts, strict=True)
                            ],
                        },
                    )

            @staticmethod
            def _texts_for(path: str, body: dict) -> list[str] | None:
                # Mirror the documented prompts so query/document asymmetry is preserved.
                if path == "/v1/embed/query":
                    return [f"task: search result | query: {str(body.get('query', '')).strip()}"]
                if path == "/v1/embed/documents":
                    return [
                        f"title: {document.get('title') or 'none'} | text: {document.get('text', '')}"
                        for document in body.get("documents", [])
                    ]
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    # -- helpers ------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Deterministic signed feature-hash embedding (stable across processes)."""
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            vector[0] = 1.0
            return vector
        vector = [value / norm for value in vector]
        if not self.normalize_response:
            vector = [value * 7.0 for value in vector]
        return vector

    def document_requests(self) -> list[dict]:
        return [
            body["body"]
            for method, body in self.requests
            if method == "POST" and body["path"] == "/v1/embed/documents"
        ]


# --------------------------------------------------------------------------- fixtures


def _settings(tmp_path: Path, *, base_url: str, **embeddings: object) -> Settings:
    return Settings(
        app={"data_dir": tmp_path, "name": "test-mymonee"},
        database={"filename": "test.db", "echo": False},
        privacy={"allow_external_ai": False},
        embeddings={"enabled": True, "base_url": base_url, "backoff_seconds": 0.0, **embeddings},
    )


@pytest.fixture
def service() -> Iterator[FakeEmbeddingService]:
    fake = FakeEmbeddingService()
    fake.start()
    try:
        yield fake
    finally:
        fake.stop()


@pytest.fixture
def env(tmp_path: Path, service: FakeEmbeddingService) -> Iterator[SimpleNamespace]:
    settings = _settings(tmp_path, base_url=service.url)
    init_db(settings)
    with get_session_factory(settings)() as session:
        yield SimpleNamespace(
            settings=settings,
            service=service,
            session=session,
            client=EmbeddingClient.from_settings(settings),
        )


def _category(session, name: str, slug: str) -> Category:
    existing = session.scalar(select(Category).where(Category.slug == slug))
    if existing is not None:
        return existing
    category = Category(name=name, slug=slug)
    session.add(category)
    session.flush()
    return category


def _transaction(
    session,
    *,
    merchant: str = "ACME HARDWARE",
    description: str = "Card payment to Acme Hardware",
    amount: float = 249.0,
    direction: str = "debit",
    transaction_type: str = "purchase",
    category: Category | None = None,
    subcategory: Subcategory | None = None,
    account: str | None = "HDFC Savings",
    location: str | None = None,
    transaction_date: datetime | None = None,
) -> Transaction:
    transaction = Transaction(
        source="test",
        transaction_date=transaction_date or datetime(2026, 3, 11, 9, 30, tzinfo=UTC),
        amount=amount,
        direction=direction,
        transaction_type=transaction_type,
        merchant_raw=merchant,
        merchant_normalized=merchant,
        description=description,
        account=account,
        location=location,
        category_id=category.id if category else None,
        subcategory_id=subcategory.id if subcategory else None,
    )
    session.add(transaction)
    session.flush()
    return transaction


# --------------------------------------------------------------------------- text and vectors


def test_embedding_text_includes_merchant_amount_and_category(env):
    shopping = _category(env.session, "Test Shopping", "test-shopping")
    transaction = _transaction(env.session, category=shopping)

    text = transaction_embedding_text(transaction)

    assert "debit INR 249.00" in text
    assert "merchant: ACME HARDWARE" in text
    assert "description: Card payment to Acme Hardware" in text
    assert "category: Test Shopping" in text
    assert "account: HDFC Savings" in text
    # Deterministic: the same row composes the same text, so the hash is stable.
    assert text == transaction_embedding_text(transaction)


def test_embedding_text_omits_absent_optional_fields(env):
    transaction = _transaction(
        env.session, merchant="LOCAL CAFE", description="", account=None, location=None
    )

    text = transaction_embedding_text(transaction)

    assert "description:" not in text
    assert "location:" not in text
    assert "account:" not in text
    assert "category:" not in text


def test_embedding_text_for_credit_includes_direction_and_type(env):
    transaction = _transaction(
        env.session,
        merchant="ACME HARDWARE",
        description="Refund for returned drill",
        direction="credit",
        transaction_type="refund",
        amount=249.0,
    )

    text = transaction_embedding_text(transaction)

    assert text.startswith("credit INR 249.00")
    assert "type: refund" in text


def test_content_hash_changes_when_embedded_text_changes(env):
    transaction = _transaction(env.session)
    before = transaction_content_hash(transaction_embedding_text(transaction))

    transaction.description = "Card payment to Acme Hardware (returned)"
    after = transaction_content_hash(transaction_embedding_text(transaction))

    assert before != after
    assert len(before) == 64


def test_vector_roundtrip_is_exact_float32():
    # Exactly-representable float32 values survive the round trip unchanged.
    vector = [0.5, -0.25, 0.125, 0.0625]

    blob = pack_vector(vector)

    assert len(blob) == 4 * len(vector)
    assert unpack_vector(blob) == vector


def test_vector_roundtrip_stores_float32_projection():
    # Values that are not exactly representable come back as their float32 projection,
    # which is the documented storage format (float32, not float64).
    assert unpack_vector(pack_vector([1e-8]))[0] == pytest.approx(1e-8, abs=1e-14)
    assert unpack_vector(pack_vector([0.1]))[0] != 0.1
    assert unpack_vector(pack_vector([0.1]))[0] == pytest.approx(0.1, abs=1e-8)


def test_unpack_rejects_misaligned_blob():
    with pytest.raises(ValueError, match="not a multiple"):
        unpack_vector(b"\x00\x01\x02")


def test_validate_vector_rejects_wrong_dimensions_and_scale():
    with pytest.raises(EmbeddingContractError):
        validate_vector([0.5, 0.5], expected_dimensions=4)

    with pytest.raises(EmbeddingContractError):
        validate_vector([5.0, 0.0, 0.0, 0.0], expected_dimensions=4)

    with pytest.raises(EmbeddingContractError):
        validate_vector([float("nan"), 0.0, 0.0, 0.0], expected_dimensions=4)

    unit = [0.5, 0.5, 0.5, 0.5]
    validate_vector(unit, expected_dimensions=4)  # does not raise
    assert vector_norm(unit) == pytest.approx(1.0)


def test_cosine_similarity_prefers_shared_content(service):
    coffee = service.embed("task: search result | query: coffee shop near me")
    similar = service.embed("coffee shop purchase")
    unrelated = service.embed("electricity bill payment")

    assert cosine_similarity(coffee, similar) > cosine_similarity(coffee, unrelated)


def test_cosine_similarity_rejects_incompatible_dimensions():
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


# --------------------------------------------------------------------------- client behaviour


def test_client_reads_model_contract_from_service(env):
    contract = env.client.contract()

    assert contract.model_id == "fake/embedding-model"
    assert contract.model_revision == "rev-a"
    assert contract.dimensions == 64
    assert contract.normalization is True
    assert contract.max_batch_size == 50


def test_client_rejects_service_that_disables_normalization(tmp_path):
    service = FakeEmbeddingService(normalization=False)
    service.start()
    try:
        settings = _settings(tmp_path, base_url=service.url)
        client = EmbeddingClient.from_settings(settings)
        with pytest.raises(EmbeddingContractError, match="normalization=false"):
            client.contract()
    finally:
        service.stop()


def test_client_batches_documents_and_preserves_order(tmp_path):
    service = FakeEmbeddingService(max_batch_size=3)
    service.start()
    try:
        settings = _settings(tmp_path, base_url=service.url)
        client = EmbeddingClient.from_settings(settings)
        documents = [
            {"id": f"doc-{index}", "text": f"support article number {index}"} for index in range(7)
        ]

        vectors = client.embed_documents(documents)

        assert len(vectors) == 7
        requests = service.document_requests()
        assert [len(request["documents"]) for request in requests] == [3, 3, 1]
        assert [document["id"] for request in requests for document in request["documents"]] == [
            document["id"] for document in documents
        ]
        for vector in vectors:
            validate_vector(vector, expected_dimensions=64)
    finally:
        service.stop()


def test_client_sends_only_documented_document_fields(tmp_path):
    service = FakeEmbeddingService()
    service.start()
    try:
        settings = _settings(tmp_path, base_url=service.url)
        client = EmbeddingClient.from_settings(settings)

        client.embed_documents([{"id": "doc-1", "text": "body", "internal_note": "must not leak"}])

        sent = service.document_requests()[0]["documents"][0]
        assert set(sent) == {"id", "text"}
    finally:
        service.stop()


def test_client_retries_transient_failures_then_succeeds(tmp_path):
    service = FakeEmbeddingService()
    service.start()
    try:
        service.transient_failures["/v1/embed/query"] = 2
        settings = _settings(tmp_path, base_url=service.url, request_max_attempts=4)
        client = EmbeddingClient.from_settings(settings)

        vector = client.embed_query("late delivery")

        validate_vector(vector, expected_dimensions=64)
        assert len([r for r in service.requests if r[1].get("path") == "/v1/embed/query"]) == 3
    finally:
        service.stop()


def test_client_raises_unavailable_after_exhausting_attempts(tmp_path):
    service = FakeEmbeddingService()
    service.start()
    try:
        service.transient_failures["/v1/embed/query"] = 99
        settings = _settings(tmp_path, base_url=service.url, request_max_attempts=3)
        client = EmbeddingClient.from_settings(settings)

        with pytest.raises(EmbeddingServiceUnavailable, match="SERVER_BUSY"):
            client.embed_query("late delivery")

        assert len([r for r in service.requests if r[1].get("path") == "/v1/embed/query"]) == 3
    finally:
        service.stop()


def test_client_does_not_retry_permanent_rejection(tmp_path):
    service = FakeEmbeddingService()
    service.start()
    try:
        settings = _settings(tmp_path, base_url=service.url, request_max_attempts=5)
        client = EmbeddingClient.from_settings(settings)

        with pytest.raises(EmbeddingRequestRejected) as excinfo:
            client.embed_documents([{"id": "doc-1", "text": f"{service.OVERSIZE_MARKER} body"}])

        assert excinfo.value.status == 413
        assert excinfo.value.code == "INPUT_TOO_LARGE"
        # Exactly one attempt: a 413 is permanent, so retrying would be a wasted round trip.
        assert len(service.document_requests()) == 1
    finally:
        service.stop()


def test_client_rejects_non_normalized_vector(tmp_path):
    service = FakeEmbeddingService(normalize_response=False)
    service.start()
    try:
        settings = _settings(tmp_path, base_url=service.url)
        client = EmbeddingClient.from_settings(settings)

        with pytest.raises(EmbeddingContractError, match="not unit-normalized"):
            client.embed_query("late delivery")
    finally:
        service.stop()


def test_client_reports_unreachable_service(tmp_path):
    settings = _settings(
        tmp_path, base_url="http://127.0.0.1:9", max_attempts=2, backoff_seconds=0.0
    )
    client = EmbeddingClient.from_settings(settings)

    with pytest.raises(EmbeddingServiceUnavailable, match="cannot reach embedding service"):
        client.contract()
    assert client.is_ready() is False


# --------------------------------------------------------------------------- enqueue


def test_enqueue_only_includes_indexable_transactions(env):
    included = _transaction(env.session, merchant="LOCAL CAFE")
    _transaction(env.session, merchant="IGNORED", transaction_type="not_a_transaction")
    flagged = _transaction(env.session, merchant="FLAGGED MERCHANT")
    env.session.add(
        DataIssueFlag(transaction_id=flagged.id, issue_type="wrong_amount", status="open")
    )
    env.session.commit()

    summary = enqueue_transaction_embeddings(env.session, contract=env.client.contract())

    # The lifecycle hook already queued a job for the plain purchase when it was inserted, and
    # removed the flagged row's job when the flag was opened; the explicit enqueue finds nothing
    # left to do. Only the indexable transaction may have a job.
    assert summary["candidates"] == 1
    assert summary["enqueued"] == 0
    assert summary["skipped"] == 1
    job_ids = set(env.session.scalars(select(EmbeddingJob.source_id)))
    assert job_ids == {included.id}


def test_enqueue_is_idempotent_and_refreshes_changed_content(env):
    transaction = _transaction(env.session)
    contract = env.client.contract()

    first = enqueue_transaction_embeddings(env.session, contract=contract)
    second = enqueue_transaction_embeddings(env.session, contract=contract)

    # The lifecycle hook queued the job on insert, so the explicit enqueue calls are no-ops.
    assert first["enqueued"] == 0 and first["skipped"] == 1
    assert second["enqueued"] == 0
    assert second["skipped"] == 1

    index_transactions(env.session, settings=env.settings, client=env.client)
    third = enqueue_transaction_embeddings(env.session, contract=contract)
    assert third["enqueued"] == 0 and third["refreshed"] == 0 and third["skipped"] == 1

    transaction.description = "Card payment to Acme Hardware (duplicate charge)"
    env.session.commit()

    # The lifecycle hook re-armed the job the moment the content changed; the explicit enqueue
    # now has nothing to do.
    job = env.session.scalar(select(EmbeddingJob))
    assert job.status == EmbeddingJobStatus.PENDING.value
    assert job.attempts == 0

    fourth = enqueue_transaction_embeddings(env.session, contract=contract)
    assert fourth["enqueued"] == 0 and fourth["refreshed"] == 0 and fourth["skipped"] == 1


# --------------------------------------------------------------------------- indexing


def test_index_persists_vector_with_compatibility_metadata(env):
    transaction = _transaction(env.session)

    result = index_transactions(env.session, settings=env.settings, client=env.client)

    assert result["process"]["embedded"] == 1
    stored = env.session.scalar(select(TransactionEmbedding))
    assert stored.transaction_id == transaction.id
    assert stored.model_id == "fake/embedding-model"
    assert stored.model_revision == "rev-a"
    assert stored.preprocessing_version == "v1.0.0"
    assert stored.dimensions == 64
    assert stored.content_hash == transaction_content_hash(transaction_embedding_text(transaction))
    assert len(stored.vector) == 4 * 64
    validate_vector(unpack_vector(stored.vector), expected_dimensions=64)

    job = env.session.scalar(select(EmbeddingJob))
    assert job.status == EmbeddingJobStatus.DONE.value
    assert job.completed_at is not None


def test_index_is_idempotent(env):
    _transaction(env.session)
    index_transactions(env.session, settings=env.settings, client=env.client)

    second = index_transactions(env.session, settings=env.settings, client=env.client)

    assert second["enqueue"]["enqueued"] == 0
    assert second["process"]["embedded"] == 0
    assert env.session.scalar(select(func.count()).select_from(TransactionEmbedding)) == 1


def test_ledger_rows_are_never_modified_by_indexing(env):
    transaction = _transaction(env.session)
    env.session.commit()
    before = (
        transaction.amount,
        transaction.direction,
        transaction.description,
        transaction.transaction_type,
        transaction.updated_at,
    )

    index_transactions(env.session, settings=env.settings, client=env.client)
    env.session.refresh(transaction)

    assert (
        transaction.amount,
        transaction.direction,
        transaction.description,
        transaction.transaction_type,
        transaction.updated_at,
    ) == before


def test_indexing_one_batch_issues_a_single_request(env):
    for index in range(5):
        _transaction(env.session, merchant=f"MERCHANT {index}")

    index_transactions(env.session, settings=env.settings, client=env.client)

    assert len(env.service.document_requests()) == 1
    assert len(env.service.document_requests()[0]["documents"]) == 5


def test_reindex_after_model_revision_change_creates_new_generation(env):
    _transaction(env.session)
    index_transactions(env.session, settings=env.settings, client=env.client)
    env.service.model_revision = "rev-b"

    client = EmbeddingClient.from_settings(env.settings)
    result = index_transactions(env.session, settings=env.settings, client=client)

    assert result["contract"].model_revision == "rev-b"
    # The existing (done) job is re-armed for the new revision rather than duplicated.
    assert result["enqueue"]["enqueued"] == 0
    assert result["enqueue"]["refreshed"] == 1
    assert result["process"]["embedded"] == 1
    revisions = dict(
        env.session.execute(
            select(TransactionEmbedding.model_revision, func.count()).group_by(
                TransactionEmbedding.model_revision
            )
        ).all()
    )
    assert revisions == {"rev-a": 1, "rev-b": 1}

    status = embedding_status(env.session, settings=env.settings, client=client)
    assert status["needs_reindex"] is False
    assert status["stored_by_revision"] == {"rev-a": 1, "rev-b": 1}


# --------------------------------------------------------------------------- failure handling


def test_service_outage_defers_jobs_with_backoff_and_preserves_ledger(env):
    transaction = _transaction(env.session)
    enqueue_transaction_embeddings(env.session, contract=env.client.contract())
    env.service.transient_failures["/v1/embed/documents"] = 99

    summary = process_embedding_jobs(env.session, settings=env.settings, client=env.client)

    assert summary["retried"] == 1
    assert summary["embedded"] == 0
    job = env.session.scalar(select(EmbeddingJob))
    assert job.status == EmbeddingJobStatus.PENDING.value
    assert job.attempts == 1
    assert job.next_attempt_at is not None
    assert "SERVER_BUSY" in job.last_error
    assert env.session.scalar(select(func.count()).select_from(TransactionEmbedding)) == 0
    env.session.refresh(transaction)
    assert transaction.amount == 249.0


def test_job_fails_permanently_after_attempt_ceiling(env):
    _transaction(env.session)
    enqueue_transaction_embeddings(env.session, contract=env.client.contract())
    env.service.transient_failures["/v1/embed/documents"] = 99
    settings = _settings(Path(env.settings.app.data_dir), base_url=env.service.url, max_attempts=1)

    summary = process_embedding_jobs(env.session, settings=settings, client=env.client)

    assert summary["failed"] == 1
    job = env.session.scalar(select(EmbeddingJob))
    assert job.status == EmbeddingJobStatus.FAILED.value


def test_deferred_job_is_not_reprocessed_before_backoff_expires(env):
    _transaction(env.session)
    enqueue_transaction_embeddings(env.session, contract=env.client.contract())
    env.service.transient_failures["/v1/embed/documents"] = 99
    # A real backoff window, so the deferred job is not yet due on the next pass.
    slow_backoff = _settings(
        Path(env.settings.app.data_dir), base_url=env.service.url, backoff_seconds=300.0
    )
    process_embedding_jobs(env.session, settings=slow_backoff, client=env.client)

    summary = process_embedding_jobs(env.session, settings=slow_backoff, client=env.client)

    # next_attempt_at is in the future, so nothing is due yet.
    assert summary["claimed"] == 0


def test_rejected_batch_falls_back_to_per_document_requests(env):
    good = _transaction(env.session, merchant="LOCAL CAFE", description="Coffee and pastry")
    bad = _transaction(
        env.session,
        merchant="BROKEN RECORD",
        description=f"Body {env.service.OVERSIZE_MARKER} that the service rejects",
    )

    index_transactions(env.session, settings=env.settings, client=env.client)

    stored = {row.transaction_id for row in env.session.scalars(select(TransactionEmbedding))}
    assert stored == {good.id}
    bad_job = env.session.scalar(select(EmbeddingJob).where(EmbeddingJob.source_id == bad.id))
    assert bad_job.status == EmbeddingJobStatus.FAILED.value
    assert "rejected by embedding service" in bad_job.last_error
    # The batch was attempted once, then each document individually.
    assert len(env.service.document_requests()) == 3


def test_job_is_dropped_when_source_transaction_disappears(env):
    transaction = _transaction(env.session)
    enqueue_transaction_embeddings(env.session, contract=env.client.contract())
    # Delete out-of-band (raw SQL) so the lifecycle hook is bypassed: this exercises the worker's
    # own "source vanished" handling, e.g. a row deleted by another process or a script.
    env.session.execute(text("DELETE FROM transactions WHERE id = :i"), {"i": transaction.id})
    env.session.commit()

    summary = process_embedding_jobs(env.session, settings=env.settings, client=env.client)

    assert summary["dropped"] == 1
    assert env.session.scalar(select(func.count()).select_from(EmbeddingJob)) == 0


def test_stale_running_job_is_reclaimed(env):
    _transaction(env.session)
    enqueue_transaction_embeddings(env.session, contract=env.client.contract())
    job = env.session.scalar(select(EmbeddingJob))
    job.status = EmbeddingJobStatus.RUNNING.value
    job.updated_at = datetime.now(UTC) - timedelta(seconds=9999)
    env.session.commit()

    summary = process_embedding_jobs(env.session, settings=env.settings, client=env.client)

    assert summary["claimed"] == 1
    assert summary["embedded"] == 1


def test_process_marks_jobs_running_and_reclaims_only_stale_ones(env):
    _transaction(env.session)
    enqueue_transaction_embeddings(env.session, contract=env.client.contract())
    job = env.session.scalar(select(EmbeddingJob))
    job.status = EmbeddingJobStatus.RUNNING.value
    job.updated_at = datetime.now(UTC)
    env.session.commit()

    summary = process_embedding_jobs(env.session, settings=env.settings, client=env.client)

    assert summary["claimed"] == 0


def test_embeddings_disabled_blocks_indexing_and_status_is_informational(env, tmp_path):
    disabled = _settings(tmp_path, base_url=env.service.url, enabled=False)

    with pytest.raises(EmbeddingsDisabled):
        index_transactions(env.session, settings=disabled)
    with pytest.raises(EmbeddingsDisabled):
        search_transactions_semantic(env.session, "coffee", settings=disabled)

    status = embedding_status(env.session, settings=disabled)
    assert status["enabled"] is False
    assert status["service"] is None
    assert status["jobs"] == {}


# --------------------------------------------------------------------------- search


def _seed_ledger(env) -> dict[str, Transaction]:
    shopping = _category(env.session, "Test Shopping", "test-shopping")
    utilities = _category(env.session, "Test Utilities", "test-utilities")
    records = {
        "coffee": _transaction(
            env.session,
            merchant="BLUE BOTTLE COFFEE",
            description="Cappuccino and croissant at the coffee shop",
            amount=480.0,
            category=shopping,
        ),
        "grocery": _transaction(
            env.session,
            merchant="FRESH MART GROCERY",
            description="Weekly grocery shopping for vegetables and milk",
            amount=2150.0,
            category=shopping,
        ),
        "electricity": _transaction(
            env.session,
            merchant="STATE POWER UTILITY",
            description="Monthly electricity bill payment",
            amount=1840.0,
            category=utilities,
        ),
        "salary": _transaction(
            env.session,
            merchant="NEFT SALARY CREDIT",
            description="Monthly salary credited",
            amount=125000.0,
            direction="credit",
            transaction_type="income",
        ),
    }
    env.session.commit()
    return records


def test_search_ranks_semantically_closest_transaction_first(env):
    records = _seed_ledger(env)
    index_transactions(env.session, settings=env.settings, client=env.client)

    results = search_transactions_semantic(
        env.session, "coffee shop latte", settings=env.settings, client=env.client, limit=3
    )

    assert results, "expected stored-vector search results"
    assert results[0]["transaction_id"] == records["coffee"].id
    assert results[0]["score"] > results[-1]["score"]
    assert results[0]["transaction"]["merchant_normalized"] == "BLUE BOTTLE COFFEE"


def test_search_matches_salary_query_to_income_credit(env):
    records = _seed_ledger(env)
    index_transactions(env.session, settings=env.settings, client=env.client)

    results = search_transactions_semantic(
        env.session, "salary credited this month", settings=env.settings, client=env.client, limit=1
    )

    assert results[0]["transaction_id"] == records["salary"].id


def test_search_ignores_vectors_from_other_model_revisions(env):
    _seed_ledger(env)
    index_transactions(env.session, settings=env.settings, client=env.client)
    env.service.model_revision = "rev-b"
    client = EmbeddingClient.from_settings(env.settings)
    index_transactions(env.session, settings=env.settings, client=client)

    # Remove the current-generation vectors: nothing may fall back to the rev-a generation.
    env.session.execute(
        delete(TransactionEmbedding).where(TransactionEmbedding.model_revision == "rev-b")
    )
    env.session.commit()

    results = search_transactions_semantic(
        env.session, "coffee shop latte", settings=env.settings, client=client
    )

    assert results == []


def test_search_skips_stored_vectors_with_incompatible_dimensions(env):
    records = _seed_ledger(env)
    index_transactions(env.session, settings=env.settings, client=env.client)
    # Simulate a corrupted row written by a different-dimension model under the same revision.
    poisoned = env.session.scalar(
        select(TransactionEmbedding).where(
            TransactionEmbedding.transaction_id == records["electricity"].id
        )
    )
    poisoned.vector = pack_vector([0.5, 0.5])
    env.session.commit()

    results = search_transactions_semantic(
        env.session, "electricity bill", settings=env.settings, client=env.client, limit=10
    )

    assert all(item["transaction_id"] != records["electricity"].id for item in results)
    assert results


def test_search_rejects_blank_query(env):
    with pytest.raises(ValueError, match="must not be empty"):
        search_transactions_semantic(env.session, "   ", settings=env.settings, client=env.client)


def test_search_excludes_transactions_hidden_by_data_issue_flags(env):
    records = _seed_ledger(env)
    index_transactions(env.session, settings=env.settings, client=env.client)
    env.session.add(
        DataIssueFlag(transaction_id=records["coffee"].id, issue_type="wrong_amount", status="open")
    )
    env.session.commit()

    results = search_transactions_semantic(
        env.session, "coffee shop latte", settings=env.settings, client=env.client, limit=10
    )

    assert all(item["transaction_id"] != records["coffee"].id for item in results)


def test_search_uses_one_query_request_per_call(env):
    _seed_ledger(env)
    index_transactions(env.session, settings=env.settings, client=env.client)
    env.service.requests.clear()

    search_transactions_semantic(
        env.session, "coffee", settings=env.settings, client=env.client, limit=2
    )

    paths = [body["path"] for method, body in env.service.requests if method == "POST"]
    assert paths == ["/v1/embed/query"]


# --------------------------------------------------------------------------- status and CLI


def _cli_module():
    """Import `mymonee.cli.main`, which `mymonee.cli` shadows with the re-exported `main`."""
    import importlib

    return importlib.import_module("mymonee.cli.main")


def test_status_reports_coverage_and_live_contract(env):
    records = _seed_ledger(env)

    before = embedding_status(env.session, settings=env.settings, client=env.client)
    assert before["stored_vectors"] == 0
    assert before["needs_reindex"] is True
    assert before["service"]["compatible"] is True
    assert before["service"]["model_revision"] == "rev-a"
    assert records  # ledger present

    index_transactions(env.session, settings=env.settings, client=env.client)
    after = embedding_status(env.session, settings=env.settings, client=env.client)

    assert after["stored_vectors"] == 4
    assert after["current_revision_vectors"] == 4
    assert after["needs_reindex"] is False
    assert after["jobs"] == {"done": 4}


def test_status_reports_unreachable_service_without_raising(env, tmp_path):
    unreachable = _settings(tmp_path, base_url="http://127.0.0.1:9", max_attempts=1)

    status = embedding_status(env.session, settings=unreachable)

    assert status["enabled"] is True
    assert status["service"]["reachable"] is False
    assert "cannot reach embedding service" in status["service"]["error"]


def test_cli_search_prints_ranked_results(env, monkeypatch, capsys):
    cli_main = _cli_module()

    _seed_ledger(env)
    index_transactions(env.session, settings=env.settings, client=env.client)
    monkeypatch.setattr(cli_main, "load_settings", lambda: env.settings, raising=True)

    cli_main.cmd_embeddings_search(Namespace(query="coffee shop latte", limit=4))

    output = capsys.readouterr().out
    assert "BLUE BOTTLE COFFEE" in output
    assert output.index("BLUE BOTTLE COFFEE") < output.index("FRESH MART GROCERY")


def test_cli_index_reports_counts(env, monkeypatch, capsys):
    cli_main = _cli_module()

    _seed_ledger(env)
    monkeypatch.setattr(cli_main, "load_settings", lambda: env.settings, raising=True)

    cli_main.cmd_embeddings_index(Namespace(limit=None, force=False))

    output = capsys.readouterr().out
    # The lifecycle hook already queued the jobs when the ledger was seeded, so the CLI's enqueue
    # pass has nothing to add; the process pass embeds everything.
    assert "Enqueued:   0" in output
    assert "Claimed:    4" in output
    assert "Embedded:   4" in output


def test_cli_status_prints_disabled_state(env, monkeypatch, capsys, tmp_path):
    cli_main = _cli_module()

    disabled = _settings(tmp_path, base_url=env.service.url, enabled=False)
    monkeypatch.setattr(cli_main, "load_settings", lambda: disabled, raising=True)

    cli_main.cmd_embeddings_status(Namespace())

    output = capsys.readouterr().out
    assert "Enabled         ○ No" in output
    assert "Not queried" in output


# --------------------------------------------------------------------------- live service


def _live_service_available() -> bool:
    try:
        with urllib.request.urlopen(f"{LIVE_BASE_URL}/health", timeout=3) as response:
            return json.loads(response.read()).get("model_loaded") is True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


LIVE = pytest.mark.skipif(
    os.environ.get("MYMONEE_TEST_EMBEDDINGS_LIVE") != "1",
    reason="set MYMONEE_TEST_EMBEDDINGS_LIVE=1 to run against a live embedding-g2 service",
)


@LIVE
def test_live_service_contract_matches_documented_shape(tmp_path):
    if not _live_service_available():
        pytest.skip(f"no embedding-g2 service with a loaded model at {LIVE_BASE_URL}")
    settings = _settings(tmp_path, base_url=LIVE_BASE_URL)
    client = EmbeddingClient.from_settings(settings)

    contract = client.contract()

    assert contract.dimensions == 256
    assert contract.normalization is True
    assert contract.model_revision
    vector = client.embed_query("how do I request a refund?")
    assert len(vector) == contract.dimensions
    validate_vector(vector, expected_dimensions=contract.dimensions)


@LIVE
def test_live_semantic_search_ranks_real_vectors(tmp_path):
    if not _live_service_available():
        pytest.skip(f"no embedding-g2 service with a loaded model at {LIVE_BASE_URL}")
    settings = _settings(tmp_path, base_url=LIVE_BASE_URL)
    init_db(settings)
    client = EmbeddingClient.from_settings(settings)

    with get_session_factory(settings)() as session:
        coffee = _transaction(
            session,
            merchant="BLUE BOTTLE COFFEE",
            description="Cappuccino and croissant at the coffee shop",
            amount=480.0,
        )
        _transaction(
            session,
            merchant="STATE POWER UTILITY",
            description="Monthly electricity bill payment",
            amount=1840.0,
        )
        _transaction(
            session,
            merchant="NEFT SALARY CREDIT",
            description="Monthly salary credited",
            amount=125000.0,
            direction="credit",
            transaction_type="income",
        )
        session.commit()

        index_transactions(session, settings=settings, client=client)
        results = search_transactions_semantic(
            session, "morning coffee and pastries", settings=settings, client=client, limit=3
        )

        assert results
        assert results[0]["transaction_id"] == coffee.id
        assert results[0]["score"] > 0.3


# --------------------------------------------------------------------------- remediation suites


def _search_ids(env, query: str, limit: int = 10) -> list[str]:
    return [
        item["transaction_id"]
        for item in search_transactions_semantic(
            env.session, query, settings=env.settings, client=env.client, limit=limit
        )
    ]


def _run_index(env) -> None:
    index_transactions(env.session, settings=env.settings, client=env.client)


# --- D2/D6: search freshness and compatibility ----------------------------------------------


def test_search_excludes_stale_vector_after_description_edit(env):
    transaction = _transaction(
        env.session, merchant="BLUE BOTTLE COFFEE", description="Cappuccino and croissant"
    )
    env.session.commit()
    _run_index(env)
    assert transaction.id in _search_ids(env, "cappuccino croissant")

    transaction.description = "Electricity bill payment"
    env.session.commit()
    assert transaction.id not in _search_ids(env, "cappuccino croissant")

    _run_index(env)
    assert transaction.id in _search_ids(env, "electricity bill")


def test_search_excludes_stale_vector_after_merchant_edit(env):
    transaction = _transaction(env.session, merchant="BLUE BOTTLE COFFEE")
    env.session.commit()
    _run_index(env)
    assert transaction.id in _search_ids(env, "blue bottle coffee")

    transaction.merchant_raw = "STATE POWER UTILITY"
    transaction.merchant_normalized = "STATE POWER UTILITY"
    env.session.commit()
    assert transaction.id not in _search_ids(env, "blue bottle coffee")


def test_search_excludes_stale_vector_after_category_change(env):
    coffee = _category(env.session, "Audit Coffee", "audit-coffee")
    power = _category(env.session, "Audit Power", "audit-power")
    transaction = _transaction(env.session, category=coffee)
    env.session.commit()
    _run_index(env)
    assert transaction.id in _search_ids(env, "audit coffee")

    transaction.category_id = power.id
    env.session.commit()
    assert transaction.id not in _search_ids(env, "audit coffee")


def test_search_excludes_stale_vector_after_account_edit(env):
    transaction = _transaction(env.session, account="HDFC Savings")
    env.session.commit()
    _run_index(env)
    assert transaction.id in _search_ids(env, "hdfc savings")

    transaction.account = "ICICI Credit Card"
    env.session.commit()
    assert transaction.id not in _search_ids(env, "hdfc savings")


def test_search_excludes_stale_vector_after_payment_method_edit(env):
    transaction = _transaction(env.session, account=None)
    transaction.payment_method = "UPI"
    env.session.commit()
    _run_index(env)
    assert transaction.id in _search_ids(env, "upi")

    transaction.payment_method = "Credit Card"
    env.session.commit()
    assert transaction.id not in _search_ids(env, "upi")


def test_search_keeps_returning_an_unchanged_transaction(env):
    transaction = _transaction(env.session, merchant="STABLE MERCHANT")
    env.session.commit()
    _run_index(env)

    assert transaction.id in _search_ids(env, "stable merchant")
    _run_index(env)  # a second pass must not disturb the fresh vector
    assert transaction.id in _search_ids(env, "stable merchant")


@pytest.mark.parametrize(
    "field,value",
    [("model_id", "other/model"), ("preprocessing_version", "v9.9.9"), ("normalization", False)],
)
def test_search_excludes_vectors_with_incompatible_compatibility_key(env, field, value):
    _transaction(env.session)
    env.session.commit()
    _run_index(env)

    row = env.session.scalar(select(TransactionEmbedding))
    setattr(row, field, value)
    env.session.commit()

    assert _search_ids(env, "acme hardware") == []


def test_search_excludes_deleted_transaction(env):
    transaction = _transaction(env.session)
    other = _transaction(env.session, merchant="KEEP ME")
    env.session.commit()
    _run_index(env)
    assert transaction.id in _search_ids(env, "acme hardware")

    env.session.delete(transaction)
    env.session.commit()

    assert transaction.id not in _search_ids(env, "acme hardware")
    assert other.id in _search_ids(env, "keep me")


# --- D5: needs_reindex reflects content drift ------------------------------------------------


def test_status_detects_content_drift_not_just_row_counts(env):
    transaction = _transaction(env.session)
    env.session.commit()
    _run_index(env)
    assert (
        embedding_status(env.session, settings=env.settings, client=env.client)["needs_reindex"]
        is False
    )

    transaction.description = "Edited after indexing"
    env.session.commit()

    status = embedding_status(env.session, settings=env.settings, client=env.client)
    assert status["stored_vectors"] == 1  # the row count is unchanged ...
    assert status["stale_vectors"] == 1
    assert status["needs_reindex"] is True  # ... yet the drift is reported


# --- D1: lifecycle integration ---------------------------------------------------------------


def test_lifecycle_hook_enqueues_job_on_insert(env):
    transaction = _transaction(env.session)

    jobs = list(env.session.scalars(select(EmbeddingJob)))
    assert [job.source_id for job in jobs] == [transaction.id]
    assert jobs[0].status == EmbeddingJobStatus.PENDING.value


def test_lifecycle_hook_refreshes_job_on_description_edit(env):
    transaction = _transaction(env.session)
    env.session.commit()
    _run_index(env)
    assert env.session.scalar(select(EmbeddingJob)).status == EmbeddingJobStatus.DONE.value

    transaction.description = "edited description"
    env.session.commit()

    job = env.session.scalar(select(EmbeddingJob))
    assert job.status == EmbeddingJobStatus.PENDING.value
    assert job.attempts == 0


def test_lifecycle_hook_refreshes_job_on_merchant_correction(env):
    transaction = _transaction(env.session, merchant="OLD MERCHANT")
    env.session.commit()
    _run_index(env)

    transaction.merchant_raw = "NEW MERCHANT"
    transaction.merchant_normalized = "NEW MERCHANT"
    env.session.commit()

    assert env.session.scalar(select(EmbeddingJob)).status == EmbeddingJobStatus.PENDING.value


def test_lifecycle_hook_ignores_irrelevant_edit(env):
    transaction = _transaction(env.session)
    env.session.commit()
    _run_index(env)

    transaction.needs_review = True  # not part of the embedding text
    env.session.commit()

    assert env.session.scalar(select(EmbeddingJob)).status == EmbeddingJobStatus.DONE.value


def test_lifecycle_hook_requeues_after_classification(env):
    transaction = _transaction(env.session)
    env.session.commit()
    _run_index(env)
    category = _category(env.session, "Audit Dining", "audit-dining")

    classify_transaction(env.session, transaction.id, category_id=category.id, create_rule=False)
    env.session.commit()

    assert env.session.scalar(select(EmbeddingJob)).status == EmbeddingJobStatus.PENDING.value


def test_lifecycle_hook_requeues_reimbursement(env):
    transaction = _transaction(env.session)
    env.session.commit()
    _run_index(env)

    mark_reimbursed(env.session, transaction.id)
    env.session.commit()

    # Reimbursed rows stay in the ledger view, so the text change must re-queue them.
    assert env.session.scalar(select(EmbeddingJob)).status == EmbeddingJobStatus.PENDING.value


def test_lifecycle_hook_exclusion_removes_job(env):
    transaction = _transaction(env.session)
    env.session.commit()
    assert env.session.scalar(select(EmbeddingJob)) is not None

    exclude_as_non_transaction(env.session, transaction.id)
    env.session.commit()

    assert env.session.scalar(select(func.count()).select_from(EmbeddingJob)) == 0


def test_lifecycle_hook_flag_removes_job_and_resolution_restores_search(env):
    transaction = _transaction(env.session)
    env.session.commit()
    _run_index(env)
    assert transaction.id in _search_ids(env, "acme hardware")

    flag = DataIssueFlag(transaction_id=transaction.id, issue_type="wrong_amount", status="open")
    env.session.add(flag)
    env.session.commit()
    assert env.session.scalar(select(func.count()).select_from(EmbeddingJob)) == 0
    assert transaction.id not in _search_ids(env, "acme hardware")

    flag.status = "resolved"
    env.session.commit()
    assert transaction.id in _search_ids(env, "acme hardware")


def test_lifecycle_hook_deletion_removes_job_and_vector(env):
    transaction = _transaction(env.session)
    env.session.commit()
    _run_index(env)

    env.session.delete(transaction)
    env.session.commit()

    assert env.session.scalar(select(func.count()).select_from(EmbeddingJob)) == 0
    assert env.session.scalar(select(func.count()).select_from(TransactionEmbedding)) == 0


def test_lifecycle_hooks_do_not_modify_ledger_fields(env):
    transaction = _transaction(env.session, merchant="STABLE MERCHANT")
    env.session.commit()
    guarded = (
        "amount",
        "direction",
        "currency",
        "transaction_type",
        "merchant_normalized",
        "description",
        "is_transfer",
        "excludes_from_spending",
        "user_verified",
        "needs_review",
    )
    before = {field: getattr(transaction, field) for field in guarded}

    _run_index(env)
    transaction.description = "edited via lifecycle"
    env.session.commit()
    env.session.refresh(transaction)

    after = {field: getattr(transaction, field) for field in guarded}
    after["description"] = before["description"]  # the edit itself is expected
    assert after == before


def test_lifecycle_disabled_never_enqueues(tmp_path):
    settings = _settings(tmp_path, base_url="http://127.0.0.1:9", enabled=False)
    init_db(settings)
    with get_session_factory(settings)() as session:
        _transaction(session)
        session.commit()

        assert session.scalar(select(func.count()).select_from(EmbeddingJob)) == 0


def test_lifecycle_enqueues_when_service_unavailable(tmp_path):
    settings = _settings(tmp_path, base_url="http://127.0.0.1:9")
    init_db(settings)
    with get_session_factory(settings)() as session:
        transaction = _transaction(session)
        session.commit()

        job = session.scalar(select(EmbeddingJob))
        # The ledger write succeeded and queued durable work without touching the network.
        assert job is not None
        assert job.source_id == transaction.id
        assert job.status == EmbeddingJobStatus.PENDING.value


def test_lifecycle_wires_the_api_write_path(tmp_path):
    service = FakeEmbeddingService()
    service.start()
    try:
        settings = _settings(tmp_path, base_url=service.url)
        app = create_app(settings)
        with TestClient(app) as client:
            response = client.post("/api/transactions/sample")
        assert response.status_code == 200

        with get_session_factory(settings)() as session:
            jobs = list(session.scalars(select(EmbeddingJob)))
        assert len(jobs) == 1
        assert jobs[0].status == EmbeddingJobStatus.PENDING.value
    finally:
        service.stop()


# --- D3: atomic claiming and concurrency -----------------------------------------------------


def test_concurrent_workers_claim_disjoint_jobs(env):
    for index in range(6):
        _transaction(env.session, merchant=f"CONCURRENT {index}")
    env.session.commit()

    barrier = threading.Barrier(2)
    claimed: dict[int, list[str]] = {}

    def worker(index: int) -> None:
        with get_session_factory(env.settings)() as session:
            barrier.wait(timeout=15)
            claimed[index] = [
                job.id for job in emb_service._claim_jobs(session, limit=10, settings=env.settings)
            ]

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert set(claimed[0]).isdisjoint(claimed[1])
    assert len(claimed[0]) + len(claimed[1]) == 6


def test_single_job_is_claimed_by_only_one_worker(env):
    _transaction(env.session)
    env.session.commit()

    factory = get_session_factory(env.settings)
    with factory() as first, factory() as second:
        first_claim = emb_service._claim_jobs(first, limit=1, settings=env.settings)
        second_claim = emb_service._claim_jobs(second, limit=1, settings=env.settings)

    assert len(first_claim) == 1
    assert second_claim == []


def test_concurrent_enqueue_does_not_duplicate_jobs(env):
    _transaction(env.session)
    env.session.commit()
    env.session.execute(text("DELETE FROM embedding_jobs"))
    env.session.commit()
    contract = env.client.contract()

    barrier = threading.Barrier(2)
    errors: list[str] = []

    def worker() -> None:
        with get_session_factory(env.settings)() as session:
            barrier.wait(timeout=15)
            try:
                enqueue_transaction_embeddings(session, contract=contract)
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert env.session.scalar(select(func.count()).select_from(EmbeddingJob)) == 1


def test_heartbeat_keeps_active_job_out_of_stale_reclaim(env):
    _transaction(env.session)
    env.session.commit()
    job = env.session.scalar(select(EmbeddingJob))
    job.status = EmbeddingJobStatus.RUNNING.value
    job.updated_at = datetime.now(UTC) - timedelta(seconds=9999)
    env.session.commit()
    env.session.expire_all()
    stale_value = env.session.get(EmbeddingJob, job.id).updated_at

    # The worker heartbeats each batch; a competing claimer must then leave the job alone.
    emb_service._heartbeat(env.session, [job])
    env.session.expire_all()
    refreshed = env.session.get(EmbeddingJob, job.id)
    assert refreshed.updated_at > stale_value

    assert emb_service._claim_jobs(env.session, limit=10, settings=env.settings) == []


# --- D4: error classification and recovery ---------------------------------------------------

MALFORMED_RESPONSE_BODIES = [
    b"<html>not json</html>",
    b"[1,2,3]",
    b"null",
    json.dumps({"embedding": ["x", "y"], "dimensions": 2}).encode(),
    json.dumps({"embedding": [float("nan")] * 64, "dimensions": 64}).encode(),
    json.dumps({"embedding": [0.5] * 63, "dimensions": 63}).encode(),
    json.dumps({"embedding": [0.5] * 64, "dimensions": 64}).encode(),
]


@pytest.mark.parametrize("body", MALFORMED_RESPONSE_BODIES)
def test_client_malformed_response_is_a_contract_error(tmp_path, body):
    service = FakeEmbeddingService(raw_body=body)
    service.start()
    try:
        client = EmbeddingClient.from_settings(_settings(tmp_path, base_url=service.url))
        with pytest.raises(EmbeddingContractError):
            client.embed_query("hello")
    finally:
        service.stop()


def test_client_rejects_reordered_document_batch(tmp_path):
    service = FakeEmbeddingService(reorder_batch=True)
    service.start()
    try:
        client = EmbeddingClient.from_settings(_settings(tmp_path, base_url=service.url))
        with pytest.raises(EmbeddingContractError, match="order"):
            client.embed_documents([{"id": "a", "text": "one"}, {"id": "b", "text": "two"}])
    finally:
        service.stop()


@pytest.mark.parametrize("status,code", [(413, "INPUT_TOO_LARGE"), (422, "VALIDATION_ERROR")])
def test_client_permanent_status_is_not_retried(tmp_path, status, code):
    service = FakeEmbeddingService(forced_status=status, forced_code=code)
    service.start()
    try:
        client = EmbeddingClient.from_settings(
            _settings(tmp_path, base_url=service.url, request_max_attempts=3)
        )
        with pytest.raises(EmbeddingRequestRejected) as excinfo:
            client.embed_query("hello")

        assert excinfo.value.status == status
        assert excinfo.value.code == code
        assert len([r for r in service.requests if r[1].get("path") == "/v1/embed/query"]) == 1
    finally:
        service.stop()


def test_client_auth_error_is_permanent(tmp_path):
    service = FakeEmbeddingService(forced_status=401, forced_code="UNAUTHORIZED")
    service.start()
    try:
        client = EmbeddingClient.from_settings(
            _settings(tmp_path, base_url=service.url, request_max_attempts=3)
        )
        with pytest.raises(EmbeddingRequestRejected) as excinfo:
            client.embed_query("hello")

        assert excinfo.value.status == 401
        assert len([r for r in service.requests if r[1].get("path") == "/v1/embed/query"]) == 1
    finally:
        service.stop()


def test_client_503_is_retried_then_reported(tmp_path):
    service = FakeEmbeddingService(forced_status=503, forced_code="SERVER_BUSY")
    service.start()
    try:
        client = EmbeddingClient.from_settings(
            _settings(tmp_path, base_url=service.url, request_max_attempts=3)
        )
        with pytest.raises(EmbeddingServiceUnavailable, match="SERVER_BUSY"):
            client.embed_query("hello")

        assert len([r for r in service.requests if r[1].get("path") == "/v1/embed/query"]) == 3
    finally:
        service.stop()


def test_client_honours_retry_after(tmp_path, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(emb_client.time, "sleep", lambda seconds: sleeps.append(seconds))
    service = FakeEmbeddingService(forced_status=503, forced_code="SERVER_BUSY", retry_after="7")
    service.start()
    try:
        client = EmbeddingClient.from_settings(
            _settings(tmp_path, base_url=service.url, backoff_seconds=0.0, request_max_attempts=2)
        )
        with pytest.raises(EmbeddingServiceUnavailable):
            client.embed_query("hello")

        assert sleeps == [7.0]
    finally:
        service.stop()


def test_worker_fails_contract_violation_without_stranding(tmp_path):
    service = FakeEmbeddingService(normalize_response=False)
    service.start()
    try:
        settings = _settings(tmp_path, base_url=service.url)
        init_db(settings)
        with get_session_factory(settings)() as session:
            _transaction(session)
            session.commit()

            summary = process_embedding_jobs(session, settings=settings)

            job = session.scalar(select(EmbeddingJob))
            assert summary["failed"] == 1
            assert summary["embedded"] == 0
            assert job.status == EmbeddingJobStatus.FAILED.value
            assert "contract" in job.last_error
            assert session.scalar(select(func.count()).select_from(TransactionEmbedding)) == 0
    finally:
        service.stop()


def test_worker_defers_transient_request_failure(tmp_path):
    service = FakeEmbeddingService(forced_status=503, forced_code="SERVER_BUSY")
    service.start()
    try:
        settings = _settings(
            tmp_path,
            base_url=service.url,
            request_max_attempts=1,
            max_attempts=3,
            backoff_seconds=0.0,
        )
        init_db(settings)
        with get_session_factory(settings)() as session:
            _transaction(session)
            session.commit()

            summary = process_embedding_jobs(session, settings=settings)

            job = session.scalar(select(EmbeddingJob))
            assert summary["retried"] == 1
            assert job.status == EmbeddingJobStatus.PENDING.value
            assert job.attempts == 1
            assert job.next_attempt_at is not None
            assert "SERVER_BUSY" in job.last_error
    finally:
        service.stop()


def test_worker_marks_job_failed_on_permanent_rejection(tmp_path):
    service = FakeEmbeddingService(forced_status=413, forced_code="INPUT_TOO_LARGE")
    service.start()
    try:
        settings = _settings(
            tmp_path, base_url=service.url, request_max_attempts=1, backoff_seconds=0.0
        )
        init_db(settings)
        with get_session_factory(settings)() as session:
            _transaction(session)
            session.commit()

            summary = process_embedding_jobs(session, settings=settings)

            job = session.scalar(select(EmbeddingJob))
            assert summary["failed"] == 1
            assert job.status == EmbeddingJobStatus.FAILED.value
            assert "rejected by embedding service" in job.last_error
    finally:
        service.stop()


def test_worker_keeps_job_pending_when_service_unreachable(tmp_path):
    settings = _settings(
        tmp_path, base_url="http://127.0.0.1:9", request_max_attempts=1, backoff_seconds=0.0
    )
    init_db(settings)
    with get_session_factory(settings)() as session:
        _transaction(session)
        session.commit()

        with pytest.raises(EmbeddingServiceUnavailable):
            process_embedding_jobs(session, settings=settings)

        session.rollback()
        job = session.scalar(select(EmbeddingJob))
        assert job.status == EmbeddingJobStatus.PENDING.value
        assert job.attempts == 0


def test_worker_survives_persistence_failure(env, monkeypatch):
    _transaction(env.session)
    env.session.commit()

    def boom(vector):
        raise RuntimeError("disk full")

    monkeypatch.setattr(emb_service, "pack_vector", boom)

    summary = process_embedding_jobs(env.session, settings=env.settings, client=env.client)

    job = env.session.scalar(select(EmbeddingJob))
    assert summary["retried"] == 1
    assert job.status == EmbeddingJobStatus.PENDING.value
    assert job.attempts == 1

"""Local embedding-g2 integration: durable indexing jobs and semantic transaction search."""

from __future__ import annotations

from mymonee.services.embeddings.base import (
    EmbeddingContractError,
    EmbeddingRequestRejected,
    EmbeddingsDisabled,
    EmbeddingServiceUnavailable,
    ServiceContract,
)
from mymonee.services.embeddings.client import EmbeddingClient
from mymonee.services.embeddings.service import (
    build_client,
    cancel_transaction_embedding,
    compatibility_filters,
    embedding_status,
    enqueue_transaction_embedding,
    enqueue_transaction_embeddings,
    index_transactions,
    indexable_transaction_filters,
    process_embedding_jobs,
    require_embeddings_enabled,
    search_transactions_semantic,
)
from mymonee.services.embeddings.text import transaction_content_hash, transaction_embedding_text
from mymonee.services.embeddings.vectors import (
    cosine_similarity,
    pack_vector,
    unpack_vector,
    validate_vector,
    vector_norm,
)

__all__ = [
    "EmbeddingClient",
    "EmbeddingContractError",
    "EmbeddingRequestRejected",
    "EmbeddingServiceUnavailable",
    "EmbeddingsDisabled",
    "ServiceContract",
    "build_client",
    "cancel_transaction_embedding",
    "compatibility_filters",
    "cosine_similarity",
    "embedding_status",
    "enqueue_transaction_embedding",
    "enqueue_transaction_embeddings",
    "index_transactions",
    "indexable_transaction_filters",
    "pack_vector",
    "process_embedding_jobs",
    "require_embeddings_enabled",
    "search_transactions_semantic",
    "transaction_content_hash",
    "transaction_embedding_text",
    "unpack_vector",
    "validate_vector",
    "vector_norm",
]

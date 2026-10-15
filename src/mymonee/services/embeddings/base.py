"""Exceptions and shared types for the local embedding-g2 integration.

`embedding-g2` is a loopback-only HTTP embedding service. Everything here is a client-side
concern: MyMonee never stores state in the service and never sends data off the machine.
"""

from __future__ import annotations

from dataclasses import dataclass


class EmbeddingsDisabled(Exception):
    """Raised when embedding work is requested while embeddings.enabled is False."""


class EmbeddingServiceUnavailable(Exception):
    """Raised when the embedding service is unreachable, or keeps failing transiently.

    Covers transport failures and 5xx responses (including 503 SERVER_BUSY / MODEL_NOT_READY)
    that outlive the configured retry budget.
    """


class EmbeddingRequestRejected(Exception):
    """Raised for permanent rejections (413/422/404/405) that retrying cannot fix."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class EmbeddingContractError(Exception):
    """Raised when a response violates the documented embedding contract.

    Examples: a vector whose length disagrees with the reported dimensions, a non-finite value,
    a vector that is not unit-normalized, or embedding IDs returned out of order.
    """


@dataclass(frozen=True, slots=True)
class ServiceContract:
    """The service's self-reported identity and limits, read from /health and /v1/info.

    Captured at runtime rather than hardcoded: the embedding model, revision, and dimensions are
    properties of the deployment, and MyMonee must detect a change rather than assume one.
    """

    model_id: str
    model_revision: str | None
    preprocessing_version: str | None
    dimensions: int
    normalization: bool
    max_batch_size: int
    max_seq_length: int
    max_input_length: int
    service_version: str
    device: str | None = None
    precision: str | None = None

    @property
    def compatibility_key(self) -> tuple[str, str | None, str | None, int, bool]:
        """Fields that must match before two vectors may be compared (embedding-g2 docs §6)."""
        return (
            self.model_id,
            self.model_revision,
            self.preprocessing_version,
            self.dimensions,
            self.normalization,
        )

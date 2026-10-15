"""Packing, validation, and similarity for embedding-g2 vectors.

Contract (from the embedding-g2 documentation): 256-dimensional, L2-normalized float32 values
returned as JSON arrays. Vectors are stored as little-endian packed float32 blobs — explicit byte
order keeps the blobs portable and 4x smaller than the JSON string form.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence

from mymonee.services.embeddings.base import EmbeddingContractError

FLOAT32_BYTES = 4
# embedding-g2 returns unit-norm vectors; measured deviation is ~1e-7, so 1e-4 is generous.
NORM_TOLERANCE = 1e-4


def pack_vector(vector: Sequence[float]) -> bytes:
    """Pack a vector as little-endian float32 (4 bytes per dimension)."""
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack_vector(blob: bytes) -> list[float]:
    """Unpack a little-endian float32 blob back into a list of floats."""
    if len(blob) % FLOAT32_BYTES != 0:
        raise ValueError(
            f"vector blob length {len(blob)} is not a multiple of {FLOAT32_BYTES} bytes"
        )
    return list(struct.unpack(f"<{len(blob) // FLOAT32_BYTES}f", blob))


def vector_norm(vector: Sequence[float]) -> float:
    """Euclidean (L2) norm of a vector."""
    return math.sqrt(sum(value * value for value in vector))


def validate_vector(vector: Sequence[float], *, expected_dimensions: int) -> None:
    """Validate a vector against the documented embedding contract.

    Raises EmbeddingContractError rather than storing a vector that would silently produce
    meaningless similarity scores later.
    """
    if len(vector) != expected_dimensions:
        raise EmbeddingContractError(
            f"expected {expected_dimensions} dimensions, received {len(vector)}"
        )
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingContractError("vector contains non-finite values (NaN or Infinity)")
    norm = vector_norm(vector)
    if abs(norm - 1.0) > NORM_TOLERANCE:
        raise EmbeddingContractError(f"vector is not unit-normalized (norm={norm:.6f})")


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity between two vectors.

    Raises ValueError when the lengths differ: comparing different vector spaces is a bug, not a
    low score. Vectors from embedding-g2 are already unit length, so this equals the dot product.
    """
    if len(left) != len(right):
        raise ValueError(
            f"incompatible vector dimensions: {len(left)} vs {len(right)} — "
            "vectors from different models or dimensions must never be compared"
        )
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = vector_norm(left)
    norm_right = vector_norm(right)
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)

"""HTTP client for a local embedding-g2 service.

Uses the standard library (`urllib.request`) so MyMonee gains no new runtime dependency for a
loopback HTTP call, matching the project's local-first, minimal-dependency posture.

Behaviour follows the documented embedding-g2 contract:
- `Content-Type: application/json` on every POST.
- Read timeout longer than the service's 30s inference-queue budget.
- 5xx / transport failures are retried with exponential backoff, honouring `Retry-After`.
- 400/401/403/404/405/413/422 are permanent: they are reported, never retried.
- Responses are validated (dimensions, finiteness, unit norm, batch order) before being stored.
- Every malformed or unparsable response becomes an `EmbeddingContractError`, never a raw
  `ValueError`/`TypeError`/`JSONDecodeError`, so the job worker can always classify the failure.
"""

from __future__ import annotations

import email.utils
import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from mymonee.services.embeddings.base import (
    EmbeddingContractError,
    EmbeddingRequestRejected,
    EmbeddingServiceUnavailable,
    ServiceContract,
)
from mymonee.services.embeddings.vectors import validate_vector

# Permanent request/authorization failures: retrying cannot help.
PERMANENT_STATUS = frozenset({400, 401, 403, 404, 405, 413, 422})
# Upper bound on a server-supplied Retry-After, so a misbehaving header cannot stall indexing.
MAX_RETRY_AFTER_SECONDS = 30.0


class EmbeddingClient:
    """Minimal, dependency-free client for the embedding-g2 REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 35.0,
        max_attempts: int = 5,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds
        self._contract: ServiceContract | None = None

    @classmethod
    def from_settings(cls, settings: Any) -> EmbeddingClient:
        """Build a client from MyMonee settings (does not check embeddings.enabled)."""
        config = settings.embeddings
        return cls(
            config.base_url,
            timeout_seconds=config.timeout_seconds,
            max_attempts=config.request_max_attempts,
            backoff_seconds=config.backoff_seconds,
        )

    # ------------------------------------------------------------------ discovery

    def health(self) -> dict[str, Any]:
        """GET /health — liveness plus model readiness."""
        return self._request_json("GET", "/health")

    def contract(self, *, refresh: bool = False) -> ServiceContract:
        """GET /v1/info (plus /health) and cache the service's identity and limits."""
        if self._contract is not None and not refresh:
            return self._contract

        info = self._request_json("GET", "/v1/info")
        health = self._request_json("GET", "/health")

        try:
            contract = ServiceContract(
                model_id=str(info["model_id"]),
                model_revision=info.get("model_revision"),
                preprocessing_version=info.get("preprocessing_version"),
                dimensions=int(info["embedding_dimensions"]),
                normalization=bool(info["normalization"]),
                max_batch_size=int(info["max_batch_size"]),
                max_seq_length=int(info["max_seq_length"]),
                max_input_length=int(info["max_input_length"]),
                service_version=str(health.get("service_version", "unknown")),
                device=info.get("device"),
                precision=info.get("precision"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingContractError(f"/v1/info response is missing required fields: {exc}")

        if not contract.normalization:
            raise EmbeddingContractError(
                "embedding service reports normalization=false; "
                "cosine similarity can no longer be computed as a dot product"
            )
        self._contract = contract
        return contract

    def is_ready(self) -> bool:
        """True when /health reports a loaded model (does not raise on failure)."""
        try:
            return bool(self.health().get("model_loaded"))
        except (EmbeddingServiceUnavailable, EmbeddingRequestRejected, EmbeddingContractError):
            return False

    # ------------------------------------------------------------------ embeddings

    def embed_query(self, text: str) -> list[float]:
        """Embed one search query. Uses /v1/embed/query (search-query prompt applied server-side)."""
        contract = self.contract()
        payload = self._request_json("POST", "/v1/embed/query", {"query": text})
        vector = self._extract_vector(payload, "embedding", contract)
        return vector

    def embed_documents(self, documents: Sequence[Mapping[str, str | None]]) -> list[list[float]]:
        """Embed documents, batching to the service's max_batch_size.

        `documents` must be `{"id": str, "text": str, "title": str | None}` mappings. Returns one
        vector per input document, in input order. Only id/text/title are sent, so extra mapping
        keys are never leaked to the service.
        """
        contract = self.contract()
        documents = list(documents)
        if not documents:
            return []

        batch_size = max(1, min(contract.max_batch_size, len(documents)))
        vectors: list[list[float]] = []

        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            wire = [
                {
                    "id": str(document["id"]),
                    "text": str(document["text"]),
                    **({"title": document["title"]} if document.get("title") else {}),
                }
                for document in batch
            ]
            payload = self._request_json("POST", "/v1/embed/documents", {"documents": wire})

            items = payload.get("embeddings")
            if not isinstance(items, list) or len(items) != len(batch):
                raise EmbeddingContractError(
                    f"expected {len(batch)} embeddings, received "
                    f"{len(items) if isinstance(items, list) else type(items).__name__}"
                )
            if not all(isinstance(item, Mapping) for item in items):
                raise EmbeddingContractError(
                    "document batch contained a non-object embedding entry"
                )
            returned_ids = [item.get("id") for item in items]
            expected_ids = [document["id"] for document in wire]
            if returned_ids != expected_ids:
                raise EmbeddingContractError(
                    "document batch order was not preserved by the service"
                )

            for item in items:
                vectors.append(self._extract_vector(item, "embedding", contract))

        return vectors

    # ------------------------------------------------------------------ internals

    def _extract_vector(
        self, payload: Mapping[str, Any], key: str, contract: ServiceContract
    ) -> list[float]:
        raw = payload.get(key)
        if not isinstance(raw, list) or not raw:
            raise EmbeddingContractError(f"response is missing a non-empty '{key}' array")
        try:
            vector = [float(value) for value in raw]
        except (TypeError, ValueError) as exc:
            raise EmbeddingContractError(f"'{key}' contains a non-numeric value: {exc}")

        reported = payload.get("dimensions")
        if reported is not None:
            try:
                reported_int = int(reported)
            except (TypeError, ValueError) as exc:
                raise EmbeddingContractError(f"response reports a non-numeric 'dimensions': {exc}")
            if reported_int != len(vector):
                raise EmbeddingContractError(
                    f"response reports dimensions={reported} but returned {len(vector)} values"
                )
        validate_vector(vector, expected_dimensions=contract.dimensions)
        return vector

    def _request_json(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Perform one request, retrying transient failures with exponential backoff."""
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            retry_after: float | None = None
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return _decode(response.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                error = _error_envelope(exc)
                if status in PERMANENT_STATUS:
                    raise EmbeddingRequestRejected(status, error["code"], error["message"]) from exc
                retry_after = _retry_after_seconds(exc.headers)
                last_error = EmbeddingServiceUnavailable(
                    f"{status} {error['code']}: {error['message']} ({method} {path})"
                )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = EmbeddingServiceUnavailable(
                    f"cannot reach embedding service at {self.base_url}{path}: {exc}"
                )

            if attempt < self.max_attempts:
                delay = (
                    retry_after
                    if retry_after is not None
                    else self.backoff_seconds * (2 ** (attempt - 1))
                )
                time.sleep(delay)

        raise (
            last_error
            if last_error is not None
            else EmbeddingServiceUnavailable(f"{method} {path} failed")
        )


def _retry_after_seconds(headers: Any) -> float | None:
    """Parse a `Retry-After` header (delta-seconds or HTTP-date), capped to a sane maximum."""
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if not raw:
        return None
    raw = raw.strip()
    try:
        return max(0.0, min(float(raw), MAX_RETRY_AFTER_SECONDS))
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    now = datetime.now(parsed.tzinfo or UTC)
    return max(0.0, min((parsed - now).total_seconds(), MAX_RETRY_AFTER_SECONDS))


def _error_envelope(http_error: urllib.error.HTTPError) -> dict[str, str]:
    """Extract the documented {"error": {code, message}} envelope from a failed response."""
    fallback = {"code": f"HTTP_{http_error.code}", "message": str(http_error.reason)}
    try:
        payload = _decode(http_error.read())
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, EmbeddingContractError):
        return fallback
    error = payload.get("error")
    if not isinstance(error, dict):
        return fallback
    return {
        "code": str(error.get("code", fallback["code"])),
        "message": str(error.get("message", fallback["message"])),
    }


def _decode(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EmbeddingContractError(f"response is not valid JSON: {exc}")
    if not isinstance(decoded, dict):
        raise EmbeddingContractError(f"expected a JSON object, received {type(decoded).__name__}")
    return decoded

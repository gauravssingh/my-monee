"""OpenRouter provider — the online transport for AI classification suggestions.

Every outbound AI call goes through OpenRouter (``https://openrouter.ai/api/v1``):

* ``typesafe/*`` (or ``jev-*``) model IDs use the **System One** endpoint ``/systemone`` and
  return typed choices with probabilities — no generated text, so no malformed JSON.
* any other model ID uses ``/chat/completions`` with a JSON-schema ``response_format``.

Only the sanitized ``TransactionContext`` and the verified taxonomy are sent; the API key is
attached to the request headers and never appears in a payload or a log line.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from mymonee.config import Settings
from mymonee.services.ai.base import (
    AIProvider,
    AIProviderAuthError,
    AIProviderError,
    MissingAPIKeyError,
    require_external_ai_permission,
)
from mymonee.services.ai.prompts import (
    CLASSIFICATION_JSON_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
)
from mymonee.services.ai.schemas import ClassificationResult, TransactionContext

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# Wrong key (401/403) or no credits (402): retrying another model cannot help.
AUTH_STATUS = frozenset({401, 402, 403})
# Malformed / unsupported requests: a different model may still accept them.
PERMANENT_STATUS = frozenset({400, 404, 413, 422})
MAX_RETRY_AFTER_SECONDS = 30.0

# `(path, payload) -> decoded response`. Injectable so tests never touch the network.
Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class OpenRouterProvider(AIProvider):
    """Classify transactions through OpenRouter (chat models or Jev System One)."""

    def __init__(self, settings: Settings, *, transport: Transport | None = None) -> None:
        require_external_ai_permission(settings)
        self.settings = settings
        config = settings.ai

        self.model = (config.model or "").strip() or "google/gemini-3.7-flash"
        self.fallback_models = [
            model for model in (config.fallback_models or []) if model != self.model
        ]
        self.base_url = (config.base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_seconds = config.timeout_seconds
        self.max_attempts = max(1, config.max_attempts)
        self.backoff_seconds = config.backoff_seconds
        self.prompt_version = PROMPT_VERSION
        self._transport: Transport = transport or self._post_json

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise MissingAPIKeyError(
                "OPENROUTER_API_KEY is not set. Add it to the project .env "
                "(OPENROUTER_API_KEY=...) or the environment, then restart the server."
            )
        self._api_key = api_key

    # ------------------------------------------------------------------ provider API

    def classify_transaction(
        self,
        context: TransactionContext,
        categories: list[dict[str, Any]],
    ) -> ClassificationResult:
        """Classify against the verified taxonomy, falling back to chat models on failure."""
        if self.is_system_one(self.model):
            try:
                return self._classify_system_one(context, categories)
            except AIProviderAuthError:
                raise
            except AIProviderError as err:
                if not any(not self.is_system_one(m) for m in self.fallback_models):
                    raise
                logger.warning("Jev failed (%s); falling back to a chat model", err)
        return self._classify_chat(context, categories)

    @staticmethod
    def is_system_one(model: str) -> bool:
        name = (model or "").strip().lower()
        return name.startswith(("typesafe/", "~typesafe/", "jev-"))

    # ------------------------------------------------------------------ chat models

    def _classify_chat(
        self, context: TransactionContext, categories: list[dict[str, Any]]
    ) -> ClassificationResult:
        errors: list[str] = []
        # Taxonomy UUIDs are ~10 tokens each; short ids keep the prompt small and stop the model
        # from paraphrasing an identifier. They are mapped back to real ids before returning.
        taxonomy, reverse_ids = _compact_taxonomy(categories)
        for candidate in self._candidates():
            try:
                data = self._call_chat(candidate, context, taxonomy)
                return _remap_ids(self._parse_chat(data, candidate), reverse_ids)
            except AIProviderAuthError:
                # Bad key or no credits: another model would hit the same wall.
                raise
            except AIProviderError as err:
                errors.append(f"{candidate}: {err}")
                logger.warning("OpenRouter model %s failed: %s", candidate, err)
        raise AIProviderError("OpenRouter classification failed: " + "; ".join(errors))

    def _call_chat(
        self,
        model: str,
        context: TransactionContext,
        taxonomy: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """POST once, degrading optional payload features the endpoint rejects.

        Providers differ on two optional knobs: ``reasoning`` (Gemini flash mandates it) and
        ``response_format`` (not every model supports JSON schema). Both are optional because the
        system prompt already asks for JSON, so drop whichever is refused and retry.
        """
        reasoning = self.settings.ai.disable_reasoning
        structured = True
        for _ in range(3):
            payload = self._chat_payload(
                context, taxonomy, model, structured=structured, reasoning=reasoning
            )
            try:
                return self._transport("/chat/completions", payload)
            except AIProviderAuthError:
                raise
            except AIProviderError as err:
                message = str(err).lower()
                if reasoning and "reasoning" in message:
                    logger.debug("%s requires reasoning; using the endpoint default", model)
                    reasoning = False
                    continue
                if structured and ("response_format" in message or "json_schema" in message):
                    logger.debug("%s rejected structured output; retrying prompt-only", model)
                    structured = False
                    continue
                raise
        raise AIProviderError(f"{model}: provider rejected every supported payload variant")

    def _chat_payload(
        self,
        context: TransactionContext,
        taxonomy: list[dict[str, Any]],
        model: str,
        *,
        structured: bool,
        reasoning: bool,
    ) -> dict[str, Any]:
        user_content = (
            "Classify this transaction into one of the allowed categories:\n\n"
            + json.dumps(
                {"transaction_data": self._state(context), "allowed_taxonomy": taxonomy},
                indent=2,
            )
        )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
        }
        if reasoning:
            # OpenRouter's unified reasoning control: a label pick does not need a chain of
            # thought, and reasoning tokens dominate both latency and cost.
            payload["reasoning"] = {"enabled": False}
        if structured:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "transaction_classification",
                    "strict": True,
                    "schema": CLASSIFICATION_JSON_SCHEMA,
                },
            }
        return payload

    def _parse_chat(self, data: dict[str, Any], model: str) -> ClassificationResult:
        self._raise_for_error(data)
        choices = data.get("choices") or []
        if not choices:
            raise AIProviderError("OpenRouter response contained no choices")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list):  # some providers return content parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("OpenRouter returned an empty classification")
        try:
            result = ClassificationResult.model_validate_json(_strip_fences(content))
        except ValidationError as err:
            raise AIProviderError(f"malformed structured output: {err}") from err
        result.model_used = data.get("model") or model
        return result

    # ------------------------------------------------------------------ Jev / System One

    def _classify_system_one(
        self, context: TransactionContext, categories: list[dict[str, Any]]
    ) -> ClassificationResult:
        # One question over every label (categories *and* subcategories), so the pair is
        # consistent by construction: picking "Food › Cafe" also determines the category.
        # Two independent questions cost ~2x and can disagree, which silently loses the
        # subcategory (measured: "Food › Cafe" degraded to "Food").
        labels, subcategory_parents, category_ids = _system_one_labels(categories)
        if not labels:
            raise AIProviderError("cannot classify against an empty taxonomy")

        data = self._transport(
            "/systemone",
            {
                "model": self.model,
                "state": {"transaction": self._state(context)},
                "questions": {
                    "classification": {
                        "type": "choice",
                        "instructions": (
                            "Pick the single best label for this transaction. Choose a "
                            "subcategory when one clearly fits; otherwise choose the category."
                        ),
                        "criteria": labels,
                    }
                },
            },
        )
        self._raise_for_error(data)

        answer = (data.get("answers") or {}).get("classification") or {}
        choice = answer.get("choice")
        confidence = _clamp(answer.get("confidence"))

        subcategory_id: str | None = None
        if choice in subcategory_parents:
            category_id, subcategory_id = subcategory_parents[choice]
        elif choice in category_ids:
            category_id = category_ids[choice]
        else:
            raise AIProviderError(f"Jev returned an unknown label: {choice!r}")

        signals = [f"label={labels[choice]} p={confidence:.3f}"]
        probabilities = answer.get("probabilities")
        if isinstance(probabilities, dict):
            ranked = sorted(
                (float(v) for v in probabilities.values() if isinstance(v, (int, float))),
                reverse=True,
            )
            if len(ranked) >= 2:
                signals.append(f"margin={ranked[0] - ranked[1]:.3f}")

        return ClassificationResult(
            category_id=category_id,
            subcategory_id=subcategory_id,
            confidence=confidence,
            signals=signals,
            model_used=data.get("model") or self.model,
        )

    # ------------------------------------------------------------------ transport

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "X-Title": "MyMonee",
            },
        )

        last_error: AIProviderError | None = None
        for attempt in range(1, self.max_attempts + 1):
            retry_after: float | None = None
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return _decode(response.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                detail = _error_detail(exc)
                if status in AUTH_STATUS:
                    raise AIProviderAuthError(
                        f"OpenRouter rejected the credentials ({status}): {detail}"
                    ) from exc
                if status in PERMANENT_STATUS:
                    raise AIProviderError(
                        f"OpenRouter rejected the request ({status}): {detail}"
                    ) from exc
                retry_after = _retry_after(exc.headers)
                last_error = AIProviderError(f"OpenRouter {status}: {detail}")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = AIProviderError(f"cannot reach OpenRouter: {exc}")

            if attempt < self.max_attempts:
                delay = (
                    retry_after
                    if retry_after is not None
                    else self.backoff_seconds * (2 ** (attempt - 1))
                )
                time.sleep(delay)

        raise last_error or AIProviderError("OpenRouter request failed")

    # ------------------------------------------------------------------ helpers

    def _candidates(self) -> list[str]:
        """Chat models only: System One ids cannot be sent to /chat/completions."""
        candidates: list[str] = []
        for model in (self.model, *self.fallback_models):
            if model and not self.is_system_one(model) and model not in candidates:
                candidates.append(model)
        if not candidates:  # pragma: no cover - guarded by classify_transaction
            raise AIProviderError("no chat model configured to classify with")
        return candidates

    @staticmethod
    def _state(context: TransactionContext) -> dict[str, Any]:
        """Sanitized transaction fields — no card number, identifiers, or credentials."""
        state: dict[str, Any] = {
            "merchant_raw": context.merchant_raw,
            "merchant_normalized": context.merchant_normalized,
            "description": context.description,
            "amount": context.amount,
            "currency": context.currency,
            "direction": context.direction,
            "transaction_type": context.transaction_type,
            "payment_method": context.payment_method,
            "account": context.account,
        }
        if context.merchant_history:
            state["merchant_history"] = list(context.merchant_history)
        return state

    @staticmethod
    def _raise_for_error(data: dict[str, Any]) -> None:
        error = data.get("error")
        if isinstance(error, dict):
            raise AIProviderError(
                f"OpenRouter error: {error.get('message') or error.get('code') or 'unknown'}"
            )


def _system_one_labels(
    categories: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, tuple[str, str]], dict[str, str]]:
    """One flat label space for Jev.

    Returns ``(criteria, sub_key -> (category_id, subcategory_id), cat_key -> category_id)``.
    Short keys keep the prompt small; Jev also echoes a probability for every option, so their
    length shows up in the output tokens too.
    """
    labels: dict[str, str] = {}
    subcategory_parents: dict[str, tuple[str, str]] = {}
    category_ids: dict[str, str] = {}
    for category_index, category in enumerate(categories, start=1):
        category_key = f"c{category_index:02d}"
        labels[category_key] = f"Category: {category['name']}"
        category_ids[category_key] = category["id"]
        for sub_index, sub in enumerate(category.get("subcategories", []), start=1):
            sub_key = f"s{category_index:02d}{sub_index:02d}"
            labels[sub_key] = f"{category['name']} › {sub['name']}"
            subcategory_parents[sub_key] = (category["id"], sub["id"])
    return labels, subcategory_parents, category_ids


def _compact_taxonomy(
    categories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Replace UUIDs with short ids for the prompt; return the mapping back to real ids."""
    reverse: dict[str, str] = {}
    compact: list[dict[str, Any]] = []
    sub_index = 0
    for cat_index, category in enumerate(categories, start=1):
        category_key = f"c{cat_index:02d}"
        reverse[category_key] = category["id"]
        subcategories = []
        for sub in category.get("subcategories", []):
            sub_index += 1
            sub_key = f"s{sub_index:02d}"
            reverse[sub_key] = sub["id"]
            subcategories.append({"subcategory_id": sub_key, "subcategory_name": sub["name"]})
        compact.append(
            {
                "category_id": category_key,
                "category_name": category["name"],
                "subcategories": subcategories,
            }
        )
    return compact, reverse


def _remap_ids(result: ClassificationResult, reverse: dict[str, str]) -> ClassificationResult:
    result.category_id = reverse.get(result.category_id, result.category_id)
    if result.subcategory_id:
        result.subcategory_id = reverse.get(result.subcategory_id, result.subcategory_id)
    return result


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.removesuffix("```")
    return cleaned.strip()


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, number))


def _retry_after(headers: Any) -> float | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, min(float(raw), MAX_RETRY_AFTER_SECONDS))
    except ValueError:
        return None


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:  # noqa: BLE001
        return str(exc.reason)
    text = raw.decode("utf-8", "replace")[:500]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text or str(exc.reason)
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or text)
    return text


def _decode(raw: bytes) -> dict[str, Any]:
    if not raw:
        raise AIProviderError("OpenRouter returned an empty body")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AIProviderError(f"OpenRouter returned invalid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise AIProviderError(
            f"OpenRouter returned {type(decoded).__name__}, expected a JSON object"
        )
    return decoded

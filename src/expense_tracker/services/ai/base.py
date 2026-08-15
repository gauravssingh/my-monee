"""Base exceptions and protocols for AI services."""

from __future__ import annotations

from typing import Any, Protocol

from expense_tracker.config import Settings
from expense_tracker.services.ai.schemas import ClassificationResult, TransactionContext


class ExternalAIOptInRequired(Exception):
    """Raised when external AI operations are attempted while privacy.allow_external_ai is False."""


class MissingAPIKeyError(Exception):
    """Raised when GEMINI_API_KEY or provider API key is not found in environment."""


class InvalidClassificationError(Exception):
    """Raised when model returns non-existent category or subcategory IDs."""


class AIProviderError(Exception):
    """Raised when the AI provider encounters an upstream network, quota, or execution error."""


def require_external_ai_permission(settings: Settings) -> None:
    """Backend hard gate enforcing that no external AI requests leave the Mac without explicit opt-in."""
    if not settings.privacy.allow_external_ai:
        raise ExternalAIOptInRequired(
            "External AI is disabled by default for privacy. "
            "Set privacy.allow_external_ai=true in config.local.yaml to permit outbound AI suggestions."
        )


class AIProvider(Protocol):
    """Protocol for AI suggestion providers."""

    def classify_transaction(
        self,
        context: TransactionContext,
        categories: list[dict[str, Any]],
    ) -> ClassificationResult:
        """Classify a transaction against a verified taxonomy of categories and subcategories."""
        ...

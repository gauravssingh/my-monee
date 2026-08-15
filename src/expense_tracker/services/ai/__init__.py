"""AI intelligence services for MyMonee."""

from __future__ import annotations

from expense_tracker.services.ai.base import (
    AIProvider,
    AIProviderError,
    ExternalAIOptInRequired,
    InvalidClassificationError,
    MissingAPIKeyError,
    require_external_ai_permission,
)
from expense_tracker.services.ai.gemini_provider import GeminiProvider, PROMPT_VERSION
from expense_tracker.services.ai.schemas import (
    AISuggestionResponse,
    ClassificationResult,
    TransactionContext,
)
from expense_tracker.services.ai.service import (
    get_ai_provider,
    get_ai_suggestion,
    track_user_classification_feedback,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AISuggestionResponse",
    "ClassificationResult",
    "ExternalAIOptInRequired",
    "GeminiProvider",
    "InvalidClassificationError",
    "MissingAPIKeyError",
    "PROMPT_VERSION",
    "TransactionContext",
    "get_ai_provider",
    "get_ai_suggestion",
    "require_external_ai_permission",
    "track_user_classification_feedback",
]

"""Re-export AI provider interfaces."""

from __future__ import annotations

from expense_tracker.services.ai.base import (
    AIProvider,
    AIProviderError,
    ExternalAIOptInRequired,
    InvalidClassificationError,
    MissingAPIKeyError,
    require_external_ai_permission,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "ExternalAIOptInRequired",
    "InvalidClassificationError",
    "MissingAPIKeyError",
    "require_external_ai_permission",
]

"""Pydantic schemas for the AI provider interface and structured responses."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator


class TransactionContext(BaseModel):
    """Sanitized, data-only context representation of a transaction for AI classification."""

    transaction_id: str
    amount: float
    currency: str = "INR"
    direction: str = "debit"
    merchant_raw: str | None = None
    merchant_normalized: str | None = None
    description: str | None = None
    transaction_type: str | None = None
    payment_method: str | None = None
    account: str | None = None
    card_last4: str | None = None


class CategoryOption(BaseModel):
    id: str
    name: str
    subcategories: list[SubcategoryOption] = Field(default_factory=list)


class SubcategoryOption(BaseModel):
    id: str
    name: str


class ClassificationResult(BaseModel):
    """Structured output expected from AI classification providers."""

    category_id: str = Field(description="The internal system ID of the selected Category.")
    subcategory_id: str | None = Field(
        default=None,
        description="The internal system ID of the selected Subcategory if applicable, or null.",
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    signals: list[str] = Field(
        default_factory=list,
        description="List of concise reasoning signals or evidence extracted from transaction data.",
    )
    model_used: str | None = Field(
        default=None,
        description="The exact model from the preference chain that produced this result.",
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {v}")
        return round(v, 4)


class AISuggestionResponse(BaseModel):
    """API response model for AI classification suggestions."""

    transaction_id: str
    category_id: str
    subcategory_id: str | None = None
    category_name: str
    subcategory_name: str | None = None
    confidence: float
    signals: list[str]
    cached: bool = False
    provider: str
    model: str
    prompt_version: str
    operation_id: str

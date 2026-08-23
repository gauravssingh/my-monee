"""High-level AI classification suggestion service with caching and audit logging."""

from __future__ import annotations

import hashlib
import json
import logging

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from mymonee.config import Settings
from mymonee.db.models import AIOperation, Category, Subcategory, Transaction
from mymonee.services.ai.base import (
    AIProvider,
    AIProviderError,
    require_external_ai_permission,
)
from mymonee.services.ai.gemini_provider import GeminiProvider, PROMPT_VERSION
from mymonee.services.ai.schemas import (
    AISuggestionResponse,
    ClassificationResult,
    TransactionContext,
)
from mymonee.services.categories import list_categories

logger = logging.getLogger(__name__)


def get_ai_provider(settings: Settings) -> AIProvider:
    """Factory to get the configured AI provider."""
    require_external_ai_permission(settings)
    provider_name = (settings.ai.provider or "gemini").lower()
    if provider_name == "gemini":
        return GeminiProvider(settings)
    raise ValueError(f"Unsupported AI provider: {provider_name}")


def _build_sanitized_context(tx: Transaction) -> TransactionContext:
    """Extract strictly sanitized data fields for AI classification. No tokens, credentials, or PII."""
    return TransactionContext(
        transaction_id=tx.id,
        amount=float(tx.amount) if tx.amount is not None else 0.0,
        currency=tx.currency or "INR",
        direction=tx.direction or "debit",
        merchant_raw=tx.merchant_raw,
        merchant_normalized=tx.merchant_normalized,
        description=tx.description,
        transaction_type=tx.transaction_type,
        payment_method=tx.payment_method,
        account=tx.account,
        card_last4=tx.card,
    )


def _compute_input_hash(context: TransactionContext) -> str:
    """Compute deterministic SHA-256 hash of the sanitized input data."""
    serialized = json.dumps(context.model_dump(), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_ai_suggestion(
    session: Session,
    transaction_id: str,
    settings: Settings,
    *,
    force_refresh: bool = False,
) -> AISuggestionResponse:
    """Get or compute an AI category suggestion for a transaction in Needs Review.

    Guaranteed not to modify the transaction row in the database.
    """
    require_external_ai_permission(settings)

    tx = session.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    context = _build_sanitized_context(tx)
    input_hash = _compute_input_hash(context)
    provider_name = (settings.ai.provider or "gemini").lower()
    model_name = settings.ai.model or "gemini-3.7-flash"

    # 1. Check cache: existing valid audit record matching input hash
    if not force_refresh:
        cached_op = session.scalars(
            select(AIOperation)
            .where(
                AIOperation.source_type == "transaction",
                AIOperation.source_id == tx.id,
                AIOperation.provider == provider_name,
                AIOperation.model == model_name,
                AIOperation.prompt_version == PROMPT_VERSION,
                AIOperation.input_hash == input_hash,
                AIOperation.status.in_(["suggested", "accepted", "corrected"]),
                AIOperation.output_json.is_not(None),
            )
            .order_by(desc(AIOperation.created_at))
        ).first()

        if cached_op and cached_op.output_json:
            try:
                result = ClassificationResult.model_validate(cached_op.output_json)
                cat = session.get(Category, result.category_id)
                if cat:
                    sub = session.get(Subcategory, result.subcategory_id) if result.subcategory_id else None
                    return AISuggestionResponse(
                        transaction_id=tx.id,
                        category_id=cat.id,
                        subcategory_id=sub.id if sub else None,
                        category_name=cat.name,
                        subcategory_name=sub.name if sub else None,
                        confidence=result.confidence,
                        signals=result.signals,
                        cached=True,
                        provider=provider_name,
                        model=model_name,
                        prompt_version=PROMPT_VERSION,
                        operation_id=cached_op.id,
                    )
            except Exception as err:
                logger.debug("Cached AI result failed to re-validate: %s", err)

    # 2. Retrieve valid taxonomy
    categories = list_categories(session)
    valid_categories_map = {c["id"]: c for c in categories}
    valid_subcategories_map = {
        sub["id"]: (c["id"], sub["name"])
        for c in categories
        for sub in c.get("subcategories", [])
    }

    # 3. Call configured AI provider
    provider = get_ai_provider(settings)
    try:
        result = provider.classify_transaction(context, categories)
    except Exception as err:
        # Record failed operation
        failed_op = AIOperation(
            operation_type="classification",
            provider=provider_name,
            model=model_name,
            prompt_version=PROMPT_VERSION,
            source_type="transaction",
            source_id=tx.id,
            input_hash=input_hash,
            input_metadata=context.model_dump(),
            output_json=None,
            confidence=None,
            status="failed",
            validation_error=str(err),
        )
        session.add(failed_op)
        session.commit()
        raise HTTPException(
            status_code=502 if isinstance(err, AIProviderError) else 500,
            detail=f"AI suggestion failed: {err}",
        ) from err

    # 4. Validate category and subcategory exist in DB
    category_id = result.category_id
    subcategory_id = result.subcategory_id

    if category_id not in valid_categories_map:
        invalid_err = f"AI returned non-existent category_id: {category_id}"
        invalid_op = AIOperation(
            operation_type="classification",
            provider=provider_name,
            model=model_name,
            prompt_version=PROMPT_VERSION,
            source_type="transaction",
            source_id=tx.id,
            input_hash=input_hash,
            input_metadata=context.model_dump(),
            output_json=result.model_dump(),
            confidence=result.confidence,
            status="invalid",
            validation_error=invalid_err,
        )
        session.add(invalid_op)
        session.commit()
        raise HTTPException(status_code=422, detail=invalid_err)

    if subcategory_id:
        if subcategory_id not in valid_subcategories_map:
            invalid_err = f"AI returned non-existent subcategory_id: {subcategory_id}"
            invalid_op = AIOperation(
                operation_type="classification",
                provider=provider_name,
                model=model_name,
                prompt_version=PROMPT_VERSION,
                source_type="transaction",
                source_id=tx.id,
                input_hash=input_hash,
                input_metadata=context.model_dump(),
                output_json=result.model_dump(),
                confidence=result.confidence,
                status="invalid",
                validation_error=invalid_err,
            )
            session.add(invalid_op)
            session.commit()
            raise HTTPException(status_code=422, detail=invalid_err)

        parent_cat_id, sub_name = valid_subcategories_map[subcategory_id]
        if parent_cat_id != category_id:
            invalid_err = (
                f"AI returned subcategory_id {subcategory_id} that does not belong to category {category_id}"
            )
            invalid_op = AIOperation(
                operation_type="classification",
                provider=provider_name,
                model=model_name,
                prompt_version=PROMPT_VERSION,
                source_type="transaction",
                source_id=tx.id,
                input_hash=input_hash,
                input_metadata=context.model_dump(),
                output_json=result.model_dump(),
                confidence=result.confidence,
                status="invalid",
                validation_error=invalid_err,
            )
            session.add(invalid_op)
            session.commit()
            raise HTTPException(status_code=422, detail=invalid_err)

    # 5. Persist audit log
    actual_model = getattr(result, "model_used", None) or model_name
    audit_op = AIOperation(
        operation_type="classification",
        provider=provider_name,
        model=actual_model,
        prompt_version=PROMPT_VERSION,
        source_type="transaction",
        source_id=tx.id,
        input_hash=input_hash,
        input_metadata=context.model_dump(),
        output_json=result.model_dump(),
        confidence=result.confidence,
        status="suggested",
        validation_error=None,
    )
    session.add(audit_op)
    session.commit()
    session.refresh(audit_op)

    cat_name = valid_categories_map[category_id]["name"]
    sub_name = valid_subcategories_map[subcategory_id][1] if subcategory_id else None

    return AISuggestionResponse(
        transaction_id=tx.id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        category_name=cat_name,
        subcategory_name=sub_name,
        confidence=result.confidence,
        signals=result.signals,
        cached=False,
        provider=provider_name,
        model=actual_model,
        prompt_version=PROMPT_VERSION,
        operation_id=audit_op.id,
    )


def track_user_classification_feedback(
    session: Session,
    transaction_id: str,
    chosen_category_id: str,
    chosen_subcategory_id: str | None,
) -> None:
    """Update AI audit record status based on whether user accepted or corrected the AI suggestion."""
    recent_op = session.scalars(
        select(AIOperation)
        .where(
            AIOperation.source_type == "transaction",
            AIOperation.source_id == transaction_id,
            AIOperation.operation_type == "classification",
            AIOperation.status == "suggested",
        )
        .order_by(desc(AIOperation.created_at))
    ).first()

    if not recent_op or not recent_op.output_json:
        return

    try:
        ai_cat = recent_op.output_json.get("category_id")
        ai_sub = recent_op.output_json.get("subcategory_id")

        if ai_cat == chosen_category_id and ai_sub == chosen_subcategory_id:
            recent_op.status = "accepted"
        else:
            recent_op.status = "corrected"
        session.flush()
    except Exception as err:
        logger.debug("Failed to update AI operation feedback status: %s", err)

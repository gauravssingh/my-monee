"""API routes for AI assistance and structured suggestions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session, settings_dep
from expense_tracker.config import Settings
from expense_tracker.services.ai.base import ExternalAIOptInRequired, MissingAPIKeyError
from expense_tracker.services.ai.schemas import AISuggestionResponse
from expense_tracker.services.ai.service import get_ai_suggestion

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ClassifyTransactionRequest(BaseModel):
    transaction_id: str
    force_refresh: bool = False


@router.post("/classify-transaction", response_model=AISuggestionResponse)
def classify_transaction_ai(
    body: ClassifyTransactionRequest,
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> AISuggestionResponse:
    """Generate or retrieve a structured AI category suggestion for a transaction.

    This operation is human-in-the-loop and does NOT modify the transaction record.
    """
    try:
        return get_ai_suggestion(
            session=session,
            transaction_id=body.transaction_id,
            settings=settings,
            force_refresh=body.force_refresh,
        )
    except ExternalAIOptInRequired as err:
        raise HTTPException(
            status_code=403,
            detail=str(err),
        ) from err
    except MissingAPIKeyError as err:
        raise HTTPException(
            status_code=400,
            detail=str(err),
        ) from err

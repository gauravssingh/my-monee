"""System status API."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session, settings_dep
from expense_tracker.config import Settings
from expense_tracker.ingestion.gmail.oauth import is_connected
from expense_tracker.services.dashboard import get_system_status

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def system_status(
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    summary = {
        "name": settings.app.name,
        "host": settings.app.host,
        "port": settings.app.port,
        "data_dir": str(settings.resolved_data_dir()),
        "database_path": str(settings.database_path()),
        "gmail_enabled": settings.gmail.enabled,
        "scheduler_enabled": settings.scheduler.enabled,
        "allow_external_ai": settings.privacy.allow_external_ai,
        "currency": settings.dashboard.default_currency,
        "upi_handles": settings.banking.upi_handles,
    }
    status = get_system_status(session, summary)
    status["gmail"]["connected"] = is_connected(settings)
    status["gmail"]["credentials_file"] = str(settings.gmail_credentials_path())
    status["gmail"]["credentials_file_present"] = settings.gmail_credentials_path().exists()
    return status

"""Health check endpoints for container orchestrators, reverse proxies, and monitoring."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Response, status

from mymonee.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
@router.get("/api/health")
def liveness() -> dict[str, str]:
    """Lightweight liveness probe (always returns 200 OK if process is responding)."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(response: Response) -> dict[str, Any]:
    """Readiness probe checking database connectivity and schema readiness without exposing sensitive paths."""
    settings = get_settings()
    db_path = settings.database_path()

    db_ready = False
    if db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM transactions LIMIT 1;")
            _ = cur.fetchone()
            conn.close()
            db_ready = True
        except Exception:
            try:
                # Fresh database before any transactions
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
                count = cur.fetchone()[0]
                conn.close()
                db_ready = count > 0
            except Exception:
                db_ready = False

    if not db_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unavailable",
            "ready": False,
            "database": "not_ready",
        }

    return {
        "status": "ok",
        "ready": True,
        "database": "connected",
    }

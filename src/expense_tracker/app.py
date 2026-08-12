"""FastAPI application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from expense_tracker.api.routes import (
    categories,
    data_issues,
    gmail,
    health,
    overview,
    system,
    transactions,
)
from expense_tracker.config import Settings, get_settings
from expense_tracker.db.session import init_db
from expense_tracker.parsers.bootstrap import bootstrap_parsers

logger = logging.getLogger(__name__)


def _web_dist_dir() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[2] / "web" / "dist",
        Path(__file__).resolve().parents[3] / "web" / "dist",
    ]
    for path in candidates:
        if (path / "index.html").exists():
            return path
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_db(settings)
    bootstrap_parsers()

    app = FastAPI(
        title=settings.app.name,
        version="0.2.0",
        description="Local-first personal expense tracker",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://{settings.app.host}:{settings.app.port}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(overview.router)
    app.include_router(transactions.router)
    app.include_router(system.router)
    app.include_router(gmail.router)
    app.include_router(categories.router)
    app.include_router(data_issues.router)

    dist = _web_dist_dir()
    if dist is not None:
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            try:
                candidate = (dist / full_path).resolve()
                if not candidate.is_relative_to(dist.resolve()):
                    return FileResponse(dist / "index.html")
            except ValueError:
                return FileResponse(dist / "index.html")
            
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:

        @app.get("/")
        def index_fallback() -> dict[str, str]:
            return {
                "message": (
                    "Expense Tracker API is running. Build the web UI "
                    "(cd web && npm run build) or use Vite dev server on :5173."
                ),
                "health": "/api/health",
                "overview": "/api/overview",
            }

    logger.info(
        "App ready — data_dir=%s db=%s",
        settings.resolved_data_dir(),
        settings.database_path(),
    )
    return app

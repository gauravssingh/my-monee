"""FastAPI application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mymonee.api.routes import (
    accounts,
    ai,
    analytics,
    auth,
    backup,
    categories,
    data_issues,
    gmail,
    health,
    intelligence,
    merchants,
    onboarding,
    overview,
    recurring,
    statements,
    system,
    transactions,
)
from mymonee.config import Settings, get_settings
from mymonee.db.session import get_session_factory, init_db
from mymonee.logging_setup import setup_logging
from mymonee.parsers.bootstrap import bootstrap_parsers
from mymonee.services.auth import is_auth_configured, verify_session_token

from contextlib import asynccontextmanager
from mymonee.scheduler.worker import get_scheduler

logger = logging.getLogger(__name__)

_AUTH_EXEMPT_PATHS = {"/api/health", "/health", "/health/live", "/health/ready"}
_AUTH_EXEMPT_PREFIXES = ("/api/auth/", "/api/onboarding/")

_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8477",
    "http://localhost:8477",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]


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
    setup_logging(settings)
    init_db(settings)
    bootstrap_parsers()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        scheduler = None
        if settings.scheduler.enabled:
            scheduler = get_scheduler(settings)
            await scheduler.start()
        yield
        # Graceful Shutdown on SIGTERM
        if scheduler:
            await scheduler.stop()
        from mymonee.db.session import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass

    app = FastAPI(
        title=settings.app.name,
        version="0.8.0",
        description="Local-first personal expense tracker",
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def enforce_auth(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in _AUTH_EXEMPT_PATHS and not path.startswith(
            _AUTH_EXEMPT_PREFIXES
        ):
            db_session = get_session_factory()()
            try:
                if is_auth_configured(db_session):
                    token = request.cookies.get(auth.COOKIE_NAME)
                    if not token:
                        authorization = request.headers.get("authorization")
                        if authorization and authorization.startswith("Bearer "):
                            token = authorization.removeprefix("Bearer ").strip()
                    if not verify_session_token(db_session, token):
                        return JSONResponse(
                            status_code=401, content={"detail": "Authentication required"}
                        )
            finally:
                db_session.close()
        return await call_next(request)

    # Registered after enforce_auth so it wraps outermost — CORS preflight
    # (OPTIONS) responses must never be blocked by the auth check.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(overview.router)
    app.include_router(analytics.router)
    app.include_router(transactions.router)
    app.include_router(system.router)
    app.include_router(gmail.router)
    app.include_router(categories.router)
    app.include_router(data_issues.router)
    app.include_router(accounts.router)
    app.include_router(merchants.router)
    app.include_router(recurring.router)
    app.include_router(statements.router)
    app.include_router(onboarding.router)
    app.include_router(backup.router)
    app.include_router(intelligence.router)
    app.include_router(ai.router)
    app.include_router(auth.router)

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

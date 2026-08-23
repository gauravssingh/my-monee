"""In-process background worker & periodic scheduler."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from expense_tracker.config import Settings, get_settings
from expense_tracker.db.session import get_session_factory
from expense_tracker.services.reconciliation import run_full_reconciliation

logger = logging.getLogger(__name__)


class BackgroundScheduler:
    """Lightweight in-process periodic task scheduler."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Background scheduler started (interval: %d min)", self.settings.scheduler.interval_minutes)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background scheduler stopped gracefully")

    async def _run_loop(self) -> None:
        interval_secs = max(60, self.settings.scheduler.interval_minutes * 60)
        # Initial delay of 30 seconds before first periodic run
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._run_periodic_jobs()
            except Exception as e:
                logger.error("Error during periodic scheduler run: %s", e)

            try:
                await asyncio.sleep(interval_secs)
            except asyncio.CancelledError:
                break

    async def _run_periodic_jobs(self) -> None:
        logger.debug("Executing scheduled maintenance tasks…")
        SessionFactory = get_session_factory()
        with SessionFactory() as session:
            try:
                # Periodic reconciliation pass
                run_full_reconciliation(session)
            except Exception as e:
                logger.warning("Periodic reconciliation error: %s", e)


_global_scheduler: BackgroundScheduler | None = None


def get_scheduler(settings: Settings | None = None) -> BackgroundScheduler:
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = BackgroundScheduler(settings)
    return _global_scheduler

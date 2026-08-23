"""CLI entry: python -m expense_tracker"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from expense_tracker.config import reload_settings
from expense_tracker.logging_setup import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal Expense Tracker")
    parser.add_argument("--host", default=None, help="Bind host (default from config)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default from config)")
    parser.add_argument("--reload", action="store_true", help="Dev auto-reload")
    args = parser.parse_args()

    settings = reload_settings()
    setup_logging(settings)
    log = logging.getLogger("expense_tracker")

    host = args.host or settings.app.host
    port = args.port or settings.app.port
    log.info("Starting %s on http://%s:%s", settings.app.name, host, port)

    uvicorn.run(
        "expense_tracker.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        log_level=settings.logging.level.lower(),
    )


if __name__ == "__main__":
    main()

"""CLI: connect Gmail using Desktop OAuth local-server flow."""

from __future__ import annotations

import argparse
import logging
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from expense_tracker.config import reload_settings
from expense_tracker.ingestion.gmail.oauth import GmailAuthError, save_credentials
from expense_tracker.logging_setup import setup_logging


def connect(port: int = 8480) -> None:
    settings = reload_settings()
    setup_logging(settings)
    log = logging.getLogger("expense_tracker.connect_gmail")

    path = settings.gmail_credentials_path()
    if not path.exists():
        raise GmailAuthError(
            f"Missing OAuth client secrets at {path}. "
            "Download a Desktop OAuth client JSON from Google Cloud Console and save it there, "
            "or paste it in the System UI."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(path), scopes=settings.gmail.scopes)
    log.info("Opening browser for Google consent (local port %s)…", port)
    creds = flow.run_local_server(
        host="127.0.0.1",
        port=port,
        authorization_prompt_message="Please authorize Expense Tracker in your browser.",
        success_message="Gmail connected. You can close this window and return to the app.",
        open_browser=True,
    )
    save_credentials(creds)
    log.info("Gmail connected — tokens stored in macOS Keychain")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Connect Gmail via OAuth (Desktop local server)")
    parser.add_argument("--port", type=int, default=8480)
    args = parser.parse_args(argv)
    try:
        connect(port=args.port)
    except GmailAuthError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

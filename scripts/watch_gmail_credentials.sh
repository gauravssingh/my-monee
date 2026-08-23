#!/usr/bin/env bash
# Watches Downloads for Google OAuth client JSON and installs it for Expense Tracker.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

DEST="$HOME/Library/Application Support/ExpenseTracker/gmail_credentials.json"
echo "Watching ~/Downloads for client_secret*.json …"
echo "Target: $DEST"

while true; do
  if [[ -f "$DEST" ]]; then
    echo "Credentials already present at $DEST"
    curl -s http://127.0.0.1:8477/api/gmail/status || true
    echo
    echo "Next: python -m mymonee.connect_gmail"
    echo "Then: python -m mymonee.sync_gmail --full-year"
    exit 0
  fi

  match="$(ls -t "$HOME"/Downloads/client_secret*.json 2>/dev/null | head -1 || true)"
  if [[ -n "${match}" ]]; then
    echo "Found $match — installing…"
    curl -s -X POST "http://127.0.0.1:8477/api/gmail/credentials/from-path?path=$(python -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$match")"
    echo
    echo "Installed. Run:"
    echo "  cd $ROOT && source .venv/bin/activate"
    echo "  python -m mymonee.connect_gmail"
    echo "  python -m mymonee.sync_gmail --full-year"
    exit 0
  fi
  sleep 2
done

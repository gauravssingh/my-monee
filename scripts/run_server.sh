#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
LOG_DIR="$HOME/Library/Logs/ExpenseTracker"
mkdir -p "$LOG_DIR"
cd "$ROOT"
exec "$PYTHON" -m mymonee

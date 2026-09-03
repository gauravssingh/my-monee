#!/usr/bin/env bash
# Open the SQLite database interactive shell or execute queries passed as arguments.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Resolve DB path via the canonical application config resolver if python/venv is available
RESOLVED_DB=""
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  RESOLVED_DB="$("$REPO_ROOT/.venv/bin/python" -c 'from mymonee.config import Settings; print(Settings().database_path())' 2>/dev/null || true)"
elif command -v python3 >/dev/null 2>&1; then
  RESOLVED_DB="$(python3 -c 'from mymonee.config import Settings; print(Settings().database_path())' 2>/dev/null || true)"
fi

DB_PATH="${MYMONEE_DB_PATH:-${EXPENSE_TRACKER_DB_PATH:-${RESOLVED_DB:-}}}"

# Fallback heuristic if resolution was empty
if [[ -z "$DB_PATH" ]]; then
  DATA_DIR="${MYMONEE_DATA_DIR:-$HOME/Library/Application Support/ExpenseTracker}"
  if [[ -f "$DATA_DIR/expense_tracker.db" ]]; then
    DB_PATH="$DATA_DIR/expense_tracker.db"
  else
    DB_PATH="$DATA_DIR/mymonee.db"
  fi
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "Error: SQLite database not found at '$DB_PATH'" >&2
  exit 1
fi

# Print database and size info to stderr so stdout remains clean for piping/subshells
DB_SIZE="$(du -h "$DB_PATH" 2>/dev/null | cut -f1 | xargs || echo "unknown")"
echo "Database: $DB_PATH ($DB_SIZE)" >&2

if [[ $# -eq 0 ]]; then
  sqlite3 -column -header "$DB_PATH"
else
  sqlite3 -column -header "$DB_PATH" "$@"
fi

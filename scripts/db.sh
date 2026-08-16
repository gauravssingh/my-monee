#!/usr/bin/env bash
# Open the SQLite database interactive shell or execute queries passed as arguments.
set -euo pipefail

DB_PATH="${EXPENSE_TRACKER_DB_PATH:-$HOME/Library/Application Support/ExpenseTracker/expense_tracker.db}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Error: SQLite database not found at '$DB_PATH'" >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  sqlite3 -column -header "$DB_PATH"
else
  sqlite3 -column -header "$DB_PATH" "$@"
fi

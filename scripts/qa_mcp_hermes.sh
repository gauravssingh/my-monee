#!/usr/bin/env bash
# ==============================================================================
# QA Suite: MyMonee ↔ Hermes Agent MCP Integration
#
# Runs:
# 1. MCP package linter & type hygiene (ruff)
# 2. Local MCP unit tests & SQLite read-only invariants (pytest)
# 3. Live Hermes Agent one-shot benchmark evaluation (scripts/benchmark_hermes_mcp.py)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

if [ -z "${VIRTUAL_ENV:-}" ] && [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "================================================================="
echo " MyMonee ↔ Hermes Agent MCP Integration QA Repertoire"
echo "================================================================="

# 1. Lint checks
echo -e "\n[1/3] Running Ruff Linter on MCP..."
ruff check src/mymonee/mcp/ src/mymonee/cli/ tests/mcp/ scripts/benchmark_hermes_mcp.py
echo "✓ Linter passed cleanly."

# 2. Fast unit tests & read-only mutation checks
echo -e "\n[2/3] Running MCP Unit & Invariant Tests (pytest)..."
pytest tests/mcp/ -q -m "not hermes"
echo "✓ Unit and invariant tests passed."

# 3. Hermes Live End-to-End Benchmark
echo -e "\n[3/3] Running Live Hermes Agent Evaluation Benchmark..."
python scripts/benchmark_hermes_mcp.py

echo -e "\n================================================================="
echo "✓ All MyMonee MCP & Hermes Agent QA checks completed successfully!"
echo "================================================================="

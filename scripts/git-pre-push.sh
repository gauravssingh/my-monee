#!/usr/bin/env bash
# ==============================================================================
# MyMonee Git Pre-Push Hook
# Fast local quality gate executed before any 'git push'.
# Runs in ~4 seconds: ruff lint, format check on changed files, and pytest.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# 1. Activate Python virtual environment if available
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "🔍 MyMonee pre-push checks..."

# Determine base commit for comparison
BASE=""
if git rev-parse --verify origin/main >/dev/null 2>&1; then
    BASE="$(git merge-base HEAD origin/main 2>/dev/null || true)"
fi

if [ -z "$BASE" ] && git rev-parse --verify main >/dev/null 2>&1; then
    BASE="$(git merge-base HEAD main 2>/dev/null || true)"
fi

if [ -z "$BASE" ]; then
    # Fallback if neither origin/main nor main are reachable: compare against parent commit
    BASE="HEAD~1"
fi

# Collect added/copied/modified Python files (macOS bash 3.2 compatible)
CHANGED_PYTHON_FILES=()
if git rev-parse --verify "$BASE" >/dev/null 2>&1; then
    while IFS= read -r file; do
        if [ -n "$file" ] && [ -f "$file" ]; then
            CHANGED_PYTHON_FILES+=("$file")
        fi
    done < <(git diff --name-only --diff-filter=ACM "$BASE" HEAD -- '*.py' ':(exclude)web/**' 2>/dev/null || true)
fi

if [ "${#CHANGED_PYTHON_FILES[@]}" -gt 0 ]; then
    # 2. Ruff Lint on changed Python files
    echo ""
    echo "→ [1/3] Ruff lint on ${#CHANGED_PYTHON_FILES[@]} changed Python file(s)..."
    ruff check "${CHANGED_PYTHON_FILES[@]}"
    echo "✓ Lint passed."

    # 3. Ruff Format check on changed Python files
    echo ""
    echo "→ [2/3] Ruff format check..."
    ruff format --check "${CHANGED_PYTHON_FILES[@]}"
    echo "✓ Format verified."
else
    echo ""
    echo "→ [1/3] No changed Python files to lint."
    echo "→ [2/3] No changed Python files to format."
fi

# 4. Pytest (Fast offline unit & invariant tests)
echo ""
echo "→ [3/3] Pytest unit & invariant tests..."
pytest -q -m "not hermes"
echo "✓ All unit tests passed."

echo ""
echo "================================================================="
echo "✓ All MyMonee pre-push checks passed cleanly. Pushing to remote."
echo "================================================================="

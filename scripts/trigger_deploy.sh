#!/usr/bin/env bash
# ==============================================================================
# MyMonee Automated Deployment Trigger
# Triggered by Hermes when a GitHub PR is merged to main.
# Strict guardrails: ABORTS on dirty working tree or non-main branch.
# Does NOT stash or touch active development checkouts.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "================================================================="
echo " MyMonee Automated Deployment Trigger"
echo " Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================="

# 1. Guardrail: Must be on branch 'main'
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "❌ Deployment ABORTED: Repository is on branch '$CURRENT_BRANCH' (expected 'main')." >&2
    echo "   Aborting to protect active feature development from unexpected branch switching." >&2
    exit 1
fi
echo "✓ On branch 'main'."

# 2. Guardrail: Working tree must be completely clean (no staged, unstaged, or untracked changes)
DIRTY_STATE="$(git status --porcelain)"
if [ -n "$DIRTY_STATE" ]; then
    echo "❌ Deployment ABORTED: Working tree has uncommitted or untracked changes:" >&2
    echo "$DIRTY_STATE" >&2
    echo "   Aborting to protect local changes from unexpected modifications." >&2
    exit 1
fi
echo "✓ Working tree is clean."

# 3. Pull latest changes from origin/main
echo "→ Synchronizing with origin/main..."
git fetch origin main
git pull --ff-only origin main

LATEST_SHA="$(git rev-parse --short HEAD)"
LATEST_MSG="$(git log -1 --pretty=%B | head -n 1)"
echo "✓ Synchronized to commit $LATEST_SHA: $LATEST_MSG"

# 4. Execute release script
echo ""
echo "→ Executing release script (deploy_local.sh)..."
bash "$SCRIPT_DIR/deploy_local.sh"

echo ""
echo "================================================================="
echo "✓ Automated deployment completed successfully for commit $LATEST_SHA!"
echo "================================================================="

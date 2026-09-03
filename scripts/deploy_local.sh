#!/usr/bin/env bash
# ==============================================================================
# MyMonee Local Release & Deployment Script
# Explicit deployment boundary from Git 'main' into your live macOS launchd daemon.
#
# Enforces:
# 1. Must be on branch 'main'
# 2. Working tree must be completely clean
# 3. Local 'main' must be synchronized with 'origin/main'
# 4. Rebuilds frontend production bundle
# 5. Kickstarts local launchd daemon and verifies health check
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "================================================================="
echo " MyMonee Local Deployment & Daemon Release"
echo "================================================================="

# 1. Guardrail: Must be on branch 'main'
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "❌ Deployment rejected: You must be on branch 'main' (currently on '$CURRENT_BRANCH')." >&2
    echo "   Please merge your feature branch to 'main' first." >&2
    exit 1
fi
echo "✓ On branch 'main'."

# 2. Guardrail: Working tree must be clean
if ! git diff-index --quiet HEAD --; then
    echo "❌ Deployment rejected: Working tree has uncommitted changes." >&2
    echo "   Please commit or stash changes before deploying to live daemon." >&2
    exit 1
fi
echo "✓ Working tree is clean."

# 3. Guardrail: Local main must match origin/main
echo "→ Fetching latest origin/main..."
git fetch origin main >/dev/null 2>&1 || true

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main 2>/dev/null || echo "$LOCAL_SHA")"

if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    echo "❌ Deployment rejected: Local 'main' ($LOCAL_SHA) differs from 'origin/main' ($REMOTE_SHA)." >&2
    echo "   Please pull or push to synchronize before deploying." >&2
    exit 1
fi
echo "✓ Branch 'main' is synchronized with origin/main."

# 4. Build Frontend Bundle
echo ""
echo "→ Building React frontend bundle (web/dist)..."
(
    cd web
    npm run build
)
echo "✓ Frontend bundle built successfully."

# 5. Restart macOS launchd daemon
echo ""
echo "→ Restarting macOS launchd service (com.personal.my-monee)..."
USER_ID="$(id -u)"
SERVICE_TARGET="gui/$USER_ID/com.personal.my-monee"

if launchctl print "$SERVICE_TARGET" >/dev/null 2>&1; then
    launchctl kickstart -k "$SERVICE_TARGET"
    echo "✓ launchd service kickstarted ($SERVICE_TARGET)."
else
    echo "⚠ launchd service ($SERVICE_TARGET) is not currently loaded."
    echo "  To load: launchctl load ~/Library/LaunchAgents/com.personal.my-monee.plist"
fi

# 6. Verify Health Check
echo ""
echo "→ Verifying daemon health check..."
HEALTH_URL="http://127.0.0.1:8477/api/health"
HEALTHY=false

for i in {1..10}; do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 1
done

if [ "$HEALTHY" = true ]; then
    echo "✓ Daemon health check passed (HTTP 200 at $HEALTH_URL)."
else
    echo "⚠ Daemon health check did not respond within 10s. Check logs: ~/Library/Logs/ExpenseTracker/"
fi

echo ""
echo "================================================================="
echo "✓ MyMonee local deployment completed successfully!"
echo "================================================================="

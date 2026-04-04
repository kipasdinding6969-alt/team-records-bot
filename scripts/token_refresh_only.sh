#!/bin/bash
# token_refresh_only.sh — Safe token refresh for cron jobs
# This script ONLY refreshes tokens. It cannot restart the gateway.
# Used by the 🔑 Token Refresh cron job.
set -euo pipefail

REFRESH_SCRIPT="/home/baiwan/openclaw-env-refresh.sh"
ENV_FILE="/home/baiwan/.openclaw/gateway.env"

if [ ! -f "$REFRESH_SCRIPT" ]; then
    echo "ERROR: refresh script not found at $REFRESH_SCRIPT"
    exit 1
fi

# Run the refresh
bash "$REFRESH_SCRIPT"

# Verify
if grep -q "ANTHROPIC_OAUTH_TOKEN" "$ENV_FILE" 2>/dev/null; then
    echo "OK: token refreshed in $ENV_FILE"
else
    echo "WARN: no ANTHROPIC_OAUTH_TOKEN found in $ENV_FILE after refresh"
    exit 1
fi

#!/usr/bin/env bash
# deploy_dashboard.sh — Build and start the Team Records Web Dashboard
# Usage: ./deploy_dashboard.sh [--build-only | --start-only]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_DIR="$REPO_DIR/web_dashboard"
LOG_FILE="$REPO_DIR/logs/dashboard.log"
PID_FILE="$REPO_DIR/logs/dashboard.pid"

mkdir -p "$REPO_DIR/logs"

BUILD_ONLY=false
START_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --build-only) BUILD_ONLY=true ;;
    --start-only) START_ONLY=true ;;
  esac
done

if [ "$START_ONLY" != true ]; then
  echo "[dashboard] Installing Node.js dependencies..."
  cd "$DASHBOARD_DIR"
  npm install

  echo "[dashboard] Building React app..."
  npm run build

  echo "[dashboard] Build complete → $DASHBOARD_DIR/dist/"
  cd "$REPO_DIR"
fi

if [ "$BUILD_ONLY" = true ]; then
  echo "[dashboard] Build-only mode, exiting."
  exit 0
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[dashboard] Stopping existing instance (PID $OLD_PID)..."
    kill "$OLD_PID" || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

fuser -k 8501/tcp 2>/dev/null || true

echo "[dashboard] Starting web_dashboard_api on port 8501..."
cd "$REPO_DIR"
nohup python3 -m uvicorn web_dashboard_api:app --host 127.0.0.1 --port 8501 --workers 1 >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo "[dashboard] Started (PID $(cat "$PID_FILE"))"
echo "[dashboard] Logs: $LOG_FILE"
echo "[dashboard] Health: http://localhost:8501/health"
echo ""

sleep 2
if curl -sf http://localhost:8501/health > /dev/null; then
  echo "[dashboard] OK — Dashboard is running at http://localhost:8501"
else
  echo "[dashboard] ERROR — Health check failed. Check logs: $LOG_FILE"
fi

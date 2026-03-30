#!/usr/bin/env bash
# Deploy script for Team Records Mini App
# Usage: ./deploy_mini_app.sh [--no-build] [--port PORT]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINI_APP_DIR="$REPO_DIR/mini_app"
PORT="${PORT:-8500}"
BUILD=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) BUILD=false; shift ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "=== Team Records Mini App Deployment ==="
echo "Repo:  $REPO_DIR"
echo "Port:  $PORT"
echo "Build: $BUILD"
echo "========================================"

# Install Python deps
echo "[1/4] Installing Python dependencies..."
pip3 install -q fastapi "uvicorn[standard]" python-multipart httpx aiosqlite python-dotenv

# Build React app
if [ "$BUILD" = true ]; then
  echo "[2/4] Building React app..."
  cd "$MINI_APP_DIR"

  if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js not found. Install Node.js 18+ first."
    exit 1
  fi

  echo "  Installing npm deps..."
  npm install --silent

  echo "  Building production bundle..."
  npm run build

  echo "  Build complete: $MINI_APP_DIR/dist/"
  cd "$REPO_DIR"
else
  echo "[2/4] Skipping build (--no-build)"
fi

# Stop existing uvicorn if running
echo "[3/4] Stopping existing API server (if running)..."
pkill -f "uvicorn mini_app_api:app" 2>/dev/null && echo "  Stopped existing server." || echo "  No existing server found."
sleep 1

# Start FastAPI server
echo "[4/4] Starting Mini App API on port $PORT..."
cd "$REPO_DIR"

nohup uvicorn mini_app_api:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workers 2 \
  --log-level info \
  >> "$REPO_DIR/mini_app_api.log" 2>&1 &

echo "  PID: $!"
echo "$!" > "$REPO_DIR/mini_app_api.pid"

# Wait and verify
sleep 2
if curl -sf "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
  echo ""
  echo "SUCCESS: Mini App API running at http://127.0.0.1:$PORT"
  echo "  Dashboard: http://127.0.0.1:$PORT/app/"
  echo "  Health:    http://127.0.0.1:$PORT/health"
  echo "  API docs:  http://127.0.0.1:$PORT/docs"
  echo ""
  echo "To expose via Cloudflare tunnel, add route:"
  echo "  /app/* -> http://127.0.0.1:$PORT/app/*"
  echo "  /api/*  -> http://127.0.0.1:$PORT/api/*"
else
  echo "WARNING: Health check failed. Check logs: $REPO_DIR/mini_app_api.log"
  exit 1
fi

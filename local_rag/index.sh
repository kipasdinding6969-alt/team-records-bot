#!/bin/bash
# index.sh — Wrapper for index.py
#
# The original bash implementation had a bug in JSON payload construction:
# - cut -c works per-line, not per-string (chunking was wrong)
# - Shell string concat created invalid JSON when $ESCAPED had its own quotes
#
# Now delegates to index.py which handles JSON correctly via Python's json module.
#
# Usage: ./local_rag/index.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Use the venv Python if available, else system Python
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

exec "$PYTHON" "$SCRIPT_DIR/index.py" "$@"

#!/usr/bin/env bash
# router.sh — Model router: dispatches tasks to the right model via OpenCode REST API
#
# Usage: ./router.sh <task-type> <message>
#
# Right model for right work:
#   code-edit    → Big Pickle (Anthropic/Claude SDK, engineering quality, free)
#   code-review  → Big Pickle (same — code needs Claude-quality)
#   test-write   → Big Pickle (same — tests need Claude-quality)
#   large-read   → Qwen3.6 Plus (1M context for reading huge files)
#   research     → Gemini 3.1 Pro (via OpenClaw, Google OAuth auto-refresh)
#   quick-check  → Ollama josiefied-7b (instant, local, trivial tasks)
#   embed        → Ollama nomic-embed-text (semantic search, RAG)
#   rag-query    → Ollama nomic-embed + josiefied-7b (search + answer)
#   fallback     → Nemotron 3 Super (reasoning, free)
#
# Requires: OpenCode serve running on :4096

set -euo pipefail

OPENCODE_URL="http://127.0.0.1:4096"
OPENCODE_AUTH="baiwan:QianHub2026!"
OLLAMA_URL="http://127.0.0.1:11434"

TASK_TYPE="${1:?Usage: $0 <task-type> <message>}"
MESSAGE="${2:?Usage: $0 <task-type> <message>}"

# Model mapping
declare -A MODEL_MAP=(
    [code-edit]="opencode/big-pickle"
    [large-read]="opencode/qwen3.6-plus-free"
    [test-write]="opencode/big-pickle"
    [quick-check]="ollama:josiefied"
    [embed]="ollama:nomic"
    [fallback]="opencode/nemotron-3-super-free"
    [visual]="opencode/gpt-5-nano"
    [research]="openclaw:gemini"
)

MODEL="${MODEL_MAP[$TASK_TYPE]:-${MODEL_MAP[fallback]}}"

# ── Ollama direct (local, no OpenCode) ─────────────────────────────────────
if [[ "$MODEL" == ollama:josiefied ]]; then
    curl -sf "$OLLAMA_URL/api/generate" \
        -d "{\"model\":\"goonsai/josiefied-qwen2.5-7b-abliterated-v2\",\"prompt\":$(printf '%s' "$MESSAGE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))'),\"stream\":false}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('response',''))"
    exit 0
fi

if [[ "$MODEL" == ollama:nomic ]]; then
    curl -sf "$OLLAMA_URL/api/embeddings" \
        -d "{\"model\":\"nomic-embed-text\",\"prompt\":$(printf '%s' "$MESSAGE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}"
    exit 0
fi

# ── OpenClaw Gemini (research tasks) ───────────────────────────────────────
if [[ "$MODEL" == openclaw:gemini ]]; then
    openclaw agent --agent main --message "$MESSAGE" --timeout 1800 2>&1
    exit $?
fi

# ── OpenCode REST API (free models) ────────────────────────────────────────

# Create session
SESSION_ID=$(curl -sf -u "$OPENCODE_AUTH" \
    -X POST "$OPENCODE_URL/session" \
    -H "Content-Type: application/json" \
    -d "{\"title\":\"${TASK_TYPE}-$(date +%s)\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")

if [[ -z "$SESSION_ID" ]]; then
    echo "ERROR: Failed to create OpenCode session" >&2
    exit 1
fi

# Send message with model override
RESPONSE=$(curl -sf -u "$OPENCODE_AUTH" \
    -X POST "$OPENCODE_URL/session/$SESSION_ID/message" \
    -H "Content-Type: application/json" \
    --max-time 1800 \
    -d "{
        \"parts\": [{\"type\": \"text\", \"text\": $(printf '%s' "$MESSAGE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}],
        \"providerID\": \"opencode\",
        \"modelID\": \"${MODEL#opencode/}\"
    }")

echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    parts = data.get('parts', [])
    for p in parts:
        if p.get('type') == 'text':
            print(p['text'])
except:
    print(sys.stdin.read())
" 2>/dev/null

exit 0

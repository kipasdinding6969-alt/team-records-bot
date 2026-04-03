#!/usr/bin/env bash
# run-agent.sh — Spawn agent via OpenCode serve (free models) with OpenClaw orchestration
#
# Usage: ./run-agent.sh <agent-id> [message] [model-override]
#
# Model routing per agent:
#   role-doctor     → big-pickle (code edits, reasoning)
#   api-contract    → big-pickle (code edits, reasoning)
#   sheet-verifier  → qwen3.6-plus-free (large context for reading sync code)
#   test-builder    → big-pickle (code generation)
#   ui-auditor      → gpt-5-nano (can read images, large context)
#
# Fallback chain: big-pickle → nemotron-3-super-free → qwen3.6-plus-free
#
# Features:
# - Routes through OpenCode serve :4096 (free models, no auth expiry)
# - Auto-retry on timeout (3 attempts, 30min each)
# - Falls back to OpenClaw Gemini if OpenCode is down
# - Logs to .openclaw/logs/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

AGENT_ID="${1:?Usage: $0 <agent-id> [message] [model]}"
MESSAGE="${2:-Read the file at .openclaw/agents/$AGENT_ID/AGENTS.md for your full instructions. Execute them autonomously. You are working in $PROJECT_ROOT. Use bash to run commands, read/write files, run tests. Report when done.}"
MODEL_OVERRIDE="${3:-}"

MAX_RETRIES=3
TIMEOUT_SEC=1800
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/${AGENT_ID}-$(date +%Y%m%d).log"

OPENCODE_URL="http://127.0.0.1:4096"
OPENCODE_AUTH="baiwan:QianHub2026!"
OLLAMA_URL="http://127.0.0.1:11434"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ── Model selection ────────────────────────────────────────────────────────
# Engineering = Claude Sonnet 4.6 (real Anthropic, via opencode-claude-auth plugin)
# Uses Claude Max subscription, auto-refresh from ~/.claude/.credentials.json
# Fallback: big-pickle → nemotron → qwen → Gemini → Ollama
declare -A AGENT_MODELS=(
    [role-doctor]="claude-opus-4-6"
    [api-contract]="claude-opus-4-6"
    [sheet-verifier]="claude-opus-4-6"
    [test-builder]="claude-opus-4-6"
    [ui-auditor]="claude-opus-4-6"
)

# Provider for Claude models (via opencode-claude-auth plugin)
declare -A AGENT_PROVIDERS=(
    [role-doctor]="anthropic"
    [api-contract]="anthropic"
    [sheet-verifier]="anthropic"
    [test-builder]="anthropic"
    [ui-auditor]="anthropic"
)

MODEL="${MODEL_OVERRIDE:-${AGENT_MODELS[$AGENT_ID]:-claude-sonnet-4-6}}"
PROVIDER="${AGENT_PROVIDERS[$AGENT_ID]:-anthropic}"
FALLBACK_MODELS=("big-pickle" "nemotron-3-super-free" "qwen3.6-plus-free")
FALLBACK_PROVIDERS=("opencode" "opencode" "opencode")

# ── Health check ───────────────────────────────────────────────────────────
check_opencode() {
    curl -sf -u "$OPENCODE_AUTH" "$OPENCODE_URL/global/health" >/dev/null 2>&1
}

check_ollama() {
    curl -sf "$OLLAMA_URL/api/tags" >/dev/null 2>&1
}

# ── OpenCode session management ────────────────────────────────────────────
create_session() {
    local title="$1"
    curl -sf -u "$OPENCODE_AUTH" \
        -X POST "$OPENCODE_URL/session" \
        -H "Content-Type: application/json" \
        -d "{\"title\":\"$title\"}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null
}

send_message() {
    local session_id="$1"
    local message="$2"
    local model="$3"
    local escaped_msg
    escaped_msg=$(printf '%s' "$message" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')

    curl -sf -u "$OPENCODE_AUTH" \
        -X POST "$OPENCODE_URL/session/$session_id/message" \
        -H "Content-Type: application/json" \
        --max-time "$TIMEOUT_SEC" \
        -d "{
            \"parts\": [{\"type\": \"text\", \"text\": $escaped_msg}],
            \"providerID\": \"$PROVIDER\",
            \"modelID\": \"$model\"
        }" 2>&1
}

send_message_async() {
    local session_id="$1"
    local message="$2"
    local model="$3"
    local escaped_msg
    escaped_msg=$(printf '%s' "$message" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')

    curl -sf -u "$OPENCODE_AUTH" \
        -X POST "$OPENCODE_URL/session/$session_id/prompt_async" \
        -H "Content-Type: application/json" \
        -d "{
            \"parts\": [{\"type\": \"text\", \"text\": $escaped_msg}],
            \"providerID\": \"$PROVIDER\",
            \"modelID\": \"$model\"
        }" 2>&1
}

extract_response() {
    python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    # Handle different response formats
    if isinstance(data, dict):
        parts = data.get('parts', data.get('content', []))
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict) and p.get('type') == 'text':
                    print(p['text'])
                elif isinstance(p, str):
                    print(p)
        elif isinstance(parts, str):
            print(parts)
        # Check for error
        err = data.get('error', '')
        if err:
            print(f'ERROR: {err}', file=sys.stderr)
    else:
        print(data)
except Exception as e:
    print(f'Parse error: {e}', file=sys.stderr)
    print(sys.stdin.read() if hasattr(sys.stdin, 'read') else '')
" 2>/dev/null
}

# ── Fallback to OpenClaw Gemini ────────────────────────────────────────────
run_openclaw_fallback() {
    local msg="$1"
    log "Falling back to OpenClaw Gemini"
    openclaw agent \
        --agent "$AGENT_ID" \
        --message "$msg" \
        --thinking high \
        --timeout "$TIMEOUT_SEC" \
        2>&1
}

# ── Fallback to Ollama local ──────────────────────────────────────────────
run_ollama_fallback() {
    local msg="$1"
    log "Falling back to Ollama local (josiefied-7b)"
    local escaped_msg
    escaped_msg=$(printf '%s' "$msg" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
    curl -sf "$OLLAMA_URL/api/generate" \
        -d "{\"model\":\"goonsai/josiefied-qwen2.5-7b-abliterated-v2\",\"prompt\":$escaped_msg,\"stream\":false}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('response',''))" 2>/dev/null
}

# ── Main execution ─────────────────────────────────────────────────────────
log "Starting agent: $AGENT_ID"
log "Model: $MODEL (fallbacks: ${FALLBACK_MODELS[*]})"
log "Timeout: ${TIMEOUT_SEC}s, Max retries: $MAX_RETRIES"

# Check OpenCode is up
if ! check_opencode; then
    log "OpenCode serve is down — falling back to OpenClaw"
    run_openclaw_fallback "$MESSAGE"
    exit $?
fi

# Create session
SESSION_ID=$(create_session "$AGENT_ID-$(date +%s)")
if [[ -z "$SESSION_ID" ]]; then
    log "Failed to create session — falling back to OpenClaw"
    run_openclaw_fallback "$MESSAGE"
    exit $?
fi
log "Session: $SESSION_ID"

# Attempt loop with model fallback
attempt=0
current_model="$MODEL"
while [ $attempt -lt $MAX_RETRIES ]; do
    attempt=$((attempt + 1))
    log "Attempt $attempt/$MAX_RETRIES (model: $current_model)"

    if [ $attempt -eq 1 ]; then
        msg="$MESSAGE"
    else
        msg="Continue where you left off. Complete your remaining tasks. If you already finished, report your final summary."
    fi

    set +e
    output=$(send_message "$SESSION_ID" "$msg" "$current_model" 2>&1)
    exit_code=$?
    set -e

    echo "$output" >> "$LOG_FILE"

    if [ $exit_code -eq 0 ] && [ -n "$output" ]; then
        # Check for model errors
        if echo "$output" | grep -qi "error\|rate.limit\|quota\|capacity"; then
            log "Model $current_model ($PROVIDER) error — trying fallback"
            # Try next fallback model + provider
            for i in "${!FALLBACK_MODELS[@]}"; do
                fb="${FALLBACK_MODELS[$i]}"
                fp="${FALLBACK_PROVIDERS[$i]}"
                if [[ "$fb" != "$current_model" ]]; then
                    current_model="$fb"
                    PROVIDER="$fp"
                    log "Switching to fallback: $current_model ($PROVIDER)"
                    break
                fi
            done
            continue
        fi

        # Check for timeout/abort
        if echo "$output" | grep -qi "aborted\|timed out\|timeout"; then
            log "Attempt $attempt timed out — retrying..."
            continue
        fi

        # Success
        response=$(echo "$output" | extract_response)
        log "Agent $AGENT_ID completed on attempt $attempt (model: $current_model)"
        echo "$response"
        exit 0
    else
        log "Attempt $attempt failed (exit $exit_code) — retrying..."
    fi
done

# All OpenCode attempts failed — try OpenClaw, then Ollama
log "OpenCode exhausted — trying OpenClaw Gemini"
if output=$(run_openclaw_fallback "$MESSAGE" 2>&1); then
    echo "$output"
    exit 0
fi

log "OpenClaw failed — trying Ollama local"
if output=$(run_ollama_fallback "$MESSAGE" 2>&1); then
    echo "$output"
    exit 0
fi

log "All providers exhausted for $AGENT_ID"
exit 1

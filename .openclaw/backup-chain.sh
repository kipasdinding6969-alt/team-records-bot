#!/usr/bin/env bash
# backup-chain.sh — 4-tier fallback for task execution
#
# Tier 1: Claude Opus 4.6 via OpenClaw (native, auto-refresh auth)
# Tier 2: Claude Opus 4.6 via OpenCode serve :4096 (opencode-claude-auth plugin)
# Tier 3: Gemini 3.1 Pro via google-gemini-cli (Google OAuth, free)
# Tier 4: Ollama josiefied-7b (local, offline capable)
# Tier 5: Queue to file + Telegram notify (everything down)
#
# Usage:
#   ./backup-chain.sh "task description" [task-type] [timeout]
#
# task-type: code-edit|code-review|research|test|quick-check (default: code-edit)
# timeout: seconds (default: 600)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

MESSAGE="${1:?Usage: $0 <message> [task-type] [timeout]}"
TASK_TYPE="${2:-code-edit}"
TIMEOUT="${3:-600}"
QUEUE_DIR="$SCRIPT_DIR/queue"
TELEGRAM_CHAT_ID="7715010221"

OPENCODE_URL="http://127.0.0.1:4096"
OPENCODE_AUTH="baiwan:QianHub2026!"
OLLAMA_URL="http://127.0.0.1:11434"

TS=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="$LOG_DIR/backup-chain-$(date +%Y%m%d).log"

log() { echo "[$TS] $*" | tee -a "$LOG_FILE"; }
log "Task: $TASK_TYPE | Timeout: ${TIMEOUT}s"

# ── Tier 1: OpenClaw native (Claude Opus via auto-refresh credentials) ─────
tier1_openclaw() {
    log "Tier 1: OpenClaw native (Claude Opus 4.6)"
    local result
    result=$(timeout "$TIMEOUT" openclaw agent \
        --agent pipeline-engineer \
        --message "$MESSAGE" \
        --thinking high \
        --timeout "$TIMEOUT" 2>&1) || return 1
    
    if echo "$result" | grep -qi "error\|rate.limit\|unauthorized\|failed"; then
        log "Tier 1 failed: $result"
        return 1
    fi
    echo "$result"
    return 0
}

# ── Tier 2: OpenCode serve (Claude via opencode-claude-auth plugin) ────────
tier2_opencode() {
    log "Tier 2: OpenCode serve (Claude Opus 4.6)"
    
    # Health check
    if ! curl -sf -u "$OPENCODE_AUTH" "$OPENCODE_URL/global/health" >/dev/null 2>&1; then
        log "Tier 2: OpenCode not reachable"
        return 1
    fi
    
    # Create session
    local session_id
    session_id=$(curl -sf -u "$OPENCODE_AUTH" \
        -X POST "$OPENCODE_URL/session" \
        -H "Content-Type: application/json" \
        -d "{\"title\":\"backup-${TASK_TYPE}-$(date +%s)\"}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null) || return 1
    
    if [[ -z "$session_id" ]]; then
        log "Tier 2: Failed to create session"
        return 1
    fi
    
    local escaped_msg
    escaped_msg=$(printf '%s' "$MESSAGE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
    
    local result
    result=$(curl -sf -u "$OPENCODE_AUTH" \
        -X POST "$OPENCODE_URL/session/$session_id/message" \
        -H "Content-Type: application/json" \
        --max-time "$TIMEOUT" \
        -d "{
            \"parts\": [{\"type\": \"text\", \"text\": $escaped_msg}],
            \"providerID\": \"anthropic\",
            \"modelID\": \"claude-opus-4-6\"
        }" 2>&1) || return 1
    
    if echo "$result" | grep -qi "error\|rate.limit\|unauthorized"; then
        log "Tier 2 failed: $(echo "$result" | head -1)"
        return 1
    fi
    
    echo "$result" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    for p in data.get('parts', []):
        if isinstance(p, dict) and p.get('type') == 'text':
            print(p['text'])
except: pass
" 2>/dev/null
    return 0
}

# ── Tier 3: Gemini via google-gemini-cli (free, Google OAuth) ──────────────
tier3_gemini() {
    log "Tier 3: Gemini 3.1 Pro (Google OAuth)"
    
    if ! command -v gemini &>/dev/null; then
        log "Tier 3: gemini CLI not found"
        return 1
    fi
    
    local result
    result=$(echo "$MESSAGE" | timeout "$TIMEOUT" gemini -m "gemini-3.1-pro-preview" 2>&1) || return 1
    
    if [[ -z "$result" ]] || echo "$result" | grep -qi "error\|quota\|unauthorized"; then
        log "Tier 3 failed"
        return 1
    fi
    echo "$result"
    return 0
}

# ── Tier 4: Ollama local (offline capable) ─────────────────────────────────
tier4_ollama() {
    log "Tier 4: Ollama josiefied-7b (local)"
    
    if ! curl -sf "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
        log "Tier 4: Ollama not reachable"
        return 1
    fi
    
    local escaped_msg
    escaped_msg=$(printf '%s' "$MESSAGE" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
    
    local result
    result=$(curl -sf "$OLLAMA_URL/api/generate" \
        --max-time "$TIMEOUT" \
        -d "{\"model\":\"goonsai/josiefied-qwen2.5-7b-abliterated-v2\",\"prompt\":$escaped_msg,\"stream\":false}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('response',''))" 2>/dev/null) || return 1
    
    if [[ -z "$result" ]]; then
        log "Tier 4 failed: empty response"
        return 1
    fi
    echo "$result"
    return 0
}

# ── Tier 5: Queue + Telegram notify (everything down) ─────────────────────
tier5_queue() {
    log "Tier 5: Queue + Telegram notify (all tiers exhausted)"
    
    mkdir -p "$QUEUE_DIR"
    local queue_file="$QUEUE_DIR/$(date +%Y%m%d_%H%M%S)_${TASK_TYPE}.json"
    
    python3 -c "
import json, sys
task = {
    'timestamp': '$TS',
    'task_type': '$TASK_TYPE',
    'timeout': $TIMEOUT,
    'message': sys.stdin.read(),
    'status': 'queued',
    'tiers_tried': ['openclaw', 'opencode', 'gemini', 'ollama'],
    'all_failed': True
}
print(json.dumps(task, indent=2))
" <<< "$MESSAGE" > "$queue_file"
    
    log "Queued to: $queue_file"
    
    # Telegram notification (best-effort)
    if command -v curl &>/dev/null; then
        local tg_msg="🚨 ALL TIERS DOWN — task queued\n\nType: $TASK_TYPE\nTime: $TS\nFile: $queue_file\n\nMessage: ${MESSAGE:0:200}..."
        local tg_escaped
        tg_escaped=$(printf '%s' "$tg_msg" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null)
        
        # Try via OpenClaw message tool (might work even if agent models are down)
        openclaw message send --channel telegram --to "$TELEGRAM_CHAT_ID" \
            --message "🚨 ALL TIERS DOWN — task queued to $queue_file" 2>/dev/null || true
    fi
    
    echo "QUEUED: All tiers exhausted. Task saved to $queue_file"
    return 0
}

# ── Execute with fallback ──────────────────────────────────────────────────

# For code tasks, try Claude first. For research, try Gemini first.
if [[ "$TASK_TYPE" == "research" || "$TASK_TYPE" == "planning" ]]; then
    # Research: Gemini → Claude → Ollama → Queue
    for tier in tier3_gemini tier1_openclaw tier2_opencode tier4_ollama tier5_queue; do
        if result=$($tier 2>&1); then
            log "Success via: $tier"
            echo "$result"
            exit 0
        fi
    done
else
    # Engineering: Claude(OpenClaw) → Claude(OpenCode) → Gemini → Ollama → Queue
    for tier in tier1_openclaw tier2_opencode tier3_gemini tier4_ollama tier5_queue; do
        if result=$($tier 2>&1); then
            log "Success via: $tier"
            echo "$result"
            exit 0
        fi
    done
fi

log "CRITICAL: Even tier5 queue failed"
exit 1

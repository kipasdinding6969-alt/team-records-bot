#!/bin/bash
# index.sh — Index team-records-bot-v2 codebase into Ollama embeddings
#
# Uses nomic-embed-text (768-dim) on localhost:11434
# Stores in local_rag/embeddings.jsonl
#
# Indexes: Python backend, TypeScript frontend, SQL schemas, configs, agent prompts
# Chunks: splits large files into ~3000 char segments with overlap
#
# Usage: ./local_rag/index.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OLLAMA_URL="http://localhost:11434"
EMBED_MODEL="nomic-embed-text"
OUTPUT="$SCRIPT_DIR/embeddings.jsonl"
CHUNK_SIZE=2000
OVERLAP=500

# ── Preflight ──────────────────────────────────────────────────────────────
if ! curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    echo "ERROR: Ollama not running at $OLLAMA_URL"
    exit 1
fi

if ! curl -sf "$OLLAMA_URL/api/tags" | grep -q "$EMBED_MODEL"; then
    echo "ERROR: Model $EMBED_MODEL not found. Run: ollama pull $EMBED_MODEL"
    exit 1
fi

echo "Indexing team-records-bot-v2 codebase..."
> "$OUTPUT"

# ── Collect files ──────────────────────────────────────────────────────────
FILES=$(find "$PROJECT_ROOT" \
    -type f \
    \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.json" \
       -o -name "*.md" -o -name "*.sh" -o -name "*.sql" -o -name "*.ini" \
       -o -name "*.css" -o -name "*.txt" \) \
    ! -path "*/.venv/*" \
    ! -path "*/__pycache__/*" \
    ! -path "*/node_modules/*" \
    ! -path "*/dist/*" \
    ! -path "*/.git/*" \
    ! -path "*/.claude/*" \
    ! -path "*/.openclaw/logs/*" \
    ! -path "*/local_rag/embeddings.jsonl" \
    ! -path "*/.handoff/events/*" \
    ! -path "*/archive/*" \
    | sort)

TOTAL=$(echo "$FILES" | wc -l)
COUNT=0
INDEXED=0
CHUNKS=0

# ── Chunking + embedding ──────────────────────────────────────────────────
for FILE in $FILES; do
    COUNT=$((COUNT + 1))
    REL_PATH="${FILE#$PROJECT_ROOT/}"

    # Skip empty
    [ ! -s "$FILE" ] && continue

    # Read full file
    FULL_CONTENT=$(cat "$FILE" 2>/dev/null) || continue
    FILE_LEN=${#FULL_CONTENT}

    if [ "$FILE_LEN" -eq 0 ]; then
        continue
    fi

    # Split into chunks
    OFFSET=0
    CHUNK_IDX=0
    while [ $OFFSET -lt $FILE_LEN ]; do
        CHUNK=$(echo "$FULL_CONTENT" | cut -c$((OFFSET + 1))-$((OFFSET + CHUNK_SIZE)))

        if [ -z "$CHUNK" ]; then
            break
        fi

        # Escape for JSON
        ESCAPED=$(printf '%s' "$CHUNK" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null)

        # Get embedding
        EMBEDDING=$(curl -sf "$OLLAMA_URL/api/embeddings" \
            -d "{\"model\": \"$EMBED_MODEL\", \"prompt\": \"File: $REL_PATH (chunk $CHUNK_IDX)\\n\"$ESCAPED\"\"}" \
            2>/dev/null | python3 -c "import sys,json; e=json.load(sys.stdin).get('embedding',[]); print(json.dumps(e) if e else '')" 2>/dev/null)

        if [ -n "$EMBEDDING" ] && [ "$EMBEDDING" != "[]" ] && [ "$EMBEDDING" != "" ]; then
            printf '{"file":"%s","chunk":%d,"offset":%d,"len":%d,"embedding":%s}\n' \
                "$REL_PATH" "$CHUNK_IDX" "$OFFSET" "${#CHUNK}" "$EMBEDDING" >> "$OUTPUT"
            CHUNKS=$((CHUNKS + 1))
        fi

        CHUNK_IDX=$((CHUNK_IDX + 1))
        OFFSET=$((OFFSET + CHUNK_SIZE - OVERLAP))
    done

    INDEXED=$((INDEXED + 1))
    printf "\r  [%d/%d] %d chunks | %s" "$COUNT" "$TOTAL" "$CHUNKS" "$REL_PATH"
done

echo ""
echo "Done. $INDEXED files, $CHUNKS chunks → $OUTPUT"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"

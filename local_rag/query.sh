#!/bin/bash
# query.sh — Semantic search over team-records-bot-v2 codebase
#
# Uses mxbai-embed-large for query embedding, cosine similarity for ranking,
# then optionally feeds results to josiefied-qwen2.5-7b for answer generation.
#
# Usage:
#   ./local_rag/query.sh "how does role assignment work"
#   ./local_rag/query.sh "sheet sync pipeline" --no-llm    (embeddings only)
#   ./local_rag/query.sh "kill detection" --top 10

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OLLAMA_URL="http://localhost:11434"
EMBED_MODEL="nomic-embed-text"
LLM_MODEL="goonsai/josiefied-qwen2.5-7b-abliterated-v2"
INDEX="$SCRIPT_DIR/embeddings.jsonl"
TOP_K=5
USE_LLM=true

QUERY="${1:?Usage: $0 <query> [--no-llm] [--top N]}"
shift

while [ $# -gt 0 ]; do
    case "$1" in
        --no-llm) USE_LLM=false ;;
        --top) TOP_K="$2"; shift ;;
        *) ;;
    esac
    shift
done

if [ ! -f "$INDEX" ]; then
    echo "ERROR: No index found. Run ./local_rag/index.sh first"
    exit 1
fi

# Get query embedding
QUERY_ESCAPED=$(printf '%s' "$QUERY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
QUERY_EMBEDDING=$(curl -sf "$OLLAMA_URL/api/embeddings" \
    -d "{\"model\": \"$EMBED_MODEL\", \"prompt\": $QUERY_ESCAPED}" \
    | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('embedding',[])))")

# Search by cosine similarity
RESULTS=$(python3 -c "
import json, math, sys

def cosine_sim(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na and nb else 0

query_emb = json.loads('$QUERY_EMBEDDING')
results = []

with open('$INDEX') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        sim = cosine_sim(query_emb, entry['embedding'])
        results.append({
            'file': entry['file'],
            'chunk': entry.get('chunk', 0),
            'score': round(sim, 4)
        })

results.sort(key=lambda x: x['score'], reverse=True)
for r in results[:$TOP_K]:
    print(json.dumps(r))
")

echo "Top $TOP_K results for: $QUERY"
echo "─────────────────────────────"
echo "$RESULTS" | python3 -c "
import sys, json
for line in sys.stdin:
    r = json.loads(line.strip())
    print(f\"  {r['score']:.4f}  {r['file']}  (chunk {r['chunk']})\")"

if [ "$USE_LLM" = true ]; then
    echo ""
    echo "Generating answer..."

    # Read the top file contents
    CONTEXT=""
    for FILE_PATH in $(echo "$RESULTS" | python3 -c "
import sys, json
seen = set()
for line in sys.stdin:
    r = json.loads(line.strip())
    if r['file'] not in seen:
        seen.add(r['file'])
        print(r['file'])
" | head -3); do
        FULL_PATH="$PROJECT_ROOT/$FILE_PATH"
        if [ -f "$FULL_PATH" ]; then
            CONTENT=$(head -c 3000 "$FULL_PATH" 2>/dev/null)
            CONTEXT="$CONTEXT\n\n--- $FILE_PATH ---\n$CONTENT"
        fi
    done

    PROMPT="Based on these code files from team-records-bot-v2, answer: $QUERY\n\nContext:$CONTEXT\n\nAnswer concisely:"
    PROMPT_ESCAPED=$(printf '%s' "$PROMPT" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')

    curl -sf "$OLLAMA_URL/api/generate" \
        -d "{\"model\": \"$LLM_MODEL\", \"prompt\": $PROMPT_ESCAPED, \"stream\": false}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('response',''))"
fi

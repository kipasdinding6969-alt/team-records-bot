#!/bin/bash
# search.sh — Lightweight RAG search wrapper for agent use
# Returns top-K file paths + scores (no LLM generation, fast)
#
# Usage:
#   ./local_rag/search.sh "role assignment logic"
#   ./local_rag/search.sh "kill system" 10

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OLLAMA_URL="http://localhost:11434"
EMBED_MODEL="nomic-embed-text"
INDEX="$SCRIPT_DIR/embeddings.jsonl"
TOP_K="${2:-5}"
QUERY="${1:?Usage: $0 <query> [top_k]}"

if [ ! -f "$INDEX" ]; then
    echo "ERROR: No index. Run ./local_rag/index.sh first" >&2
    exit 1
fi

# Check Ollama is alive
if ! curl -sf "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    echo "ERROR: Ollama not reachable at $OLLAMA_URL" >&2
    exit 1
fi

QUERY_ESCAPED=$(printf '%s' "$QUERY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
QUERY_EMBEDDING=$(curl -sf "$OLLAMA_URL/api/embeddings" \
    -d "{\"model\": \"$EMBED_MODEL\", \"prompt\": $QUERY_ESCAPED}" \
    | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('embedding',[])))")

python3 -c "
import json, math, sys

def cosine_sim(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na and nb else 0

query_emb = json.loads(sys.argv[1])
top_k = int(sys.argv[2])
results = []

with open(sys.argv[3]) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        sim = cosine_sim(query_emb, entry['embedding'])
        results.append({
            'file': entry['file'],
            'chunk': entry.get('chunk', 0),
            'score': round(sim, 4),
            'preview': entry.get('text', '')[:120]
        })

results.sort(key=lambda x: x['score'], reverse=True)
for r in results[:top_k]:
    print(f\"{r['score']:.4f}  {r['file']}  (chunk {r['chunk']})  {r['preview'][:80]}...\")
" "$QUERY_EMBEDDING" "$TOP_K" "$INDEX"

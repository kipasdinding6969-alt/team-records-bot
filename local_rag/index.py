#!/usr/bin/env python3
"""Index team-records-bot-v2 codebase into Ollama nomic-embed-text embeddings."""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"  # 768-dim, ~8192 token context (~4000 chars safe)
CHUNK_SIZE = 2000  # reduced from 3000 to avoid token limit with CJK/complex text
OVERLAP = 400
MAX_RETRIES = 3
RETRY_DELAY = 1

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT = SCRIPT_DIR / "embeddings.jsonl"

EXTENSIONS = {".py", ".ts", ".tsx", ".json", ".md", ".sh", ".sql", ".ini", ".css", ".txt"}
SKIP_DIRS = {".venv", "venv", "__pycache__", "node_modules", "dist", ".git", ".claude",
             "archive", ".handoff", ".openclaw", ".opencode", ".ruff_cache", ".pytest_cache",
             "local_rag"}


def get_embedding(text: str) -> list:
    """Get embedding from Ollama with retry logic."""
    # Truncate to ~4000 chars to stay safely within token limit
    if len(text) > 4000:
        text = text[:4000]
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data.get("embedding", [])
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"\n  FAIL after {MAX_RETRIES} retries: {e}", file=sys.stderr)
                return []


def collect_files() -> list:
    """Collect all indexable source files."""
    files = []
    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in sorted(filenames):
            fpath = Path(root) / fname
            if fpath.suffix in EXTENSIONS and fpath.stat().st_size > 0:
                if fpath.stat().st_size > 500_000:
                    continue
                files.append(fpath)
    return files


def chunk_file(content: str) -> list:
    """Split content into overlapping chunks."""
    chunks = []
    offset = 0
    while offset < len(content):
        chunk = content[offset:offset + CHUNK_SIZE]
        if chunk.strip():
            chunks.append((offset, chunk))
        offset += CHUNK_SIZE - OVERLAP
    return chunks


def main():
    print(f"Indexing {PROJECT_ROOT.name} codebase with {EMBED_MODEL}...")

    files = collect_files()
    total = len(files)
    indexed = 0
    total_chunks = 0
    errors = 0

    with open(OUTPUT, "w") as out:
        for i, fpath in enumerate(files, 1):
            rel_path = str(fpath.relative_to(PROJECT_ROOT))

            try:
                content = fpath.read_text(errors="replace")
            except Exception:
                continue

            chunks = chunk_file(content)

            for chunk_idx, (offset, chunk_text) in enumerate(chunks):
                prompt = f"File: {rel_path} (chunk {chunk_idx})\n{chunk_text}"
                embedding = get_embedding(prompt)

                if embedding:
                    entry = {
                        "file": rel_path,
                        "chunk": chunk_idx,
                        "offset": offset,
                        "len": len(chunk_text),
                        "embedding": embedding,
                    }
                    out.write(json.dumps(entry) + "\n")
                    total_chunks += 1
                else:
                    errors += 1

            indexed += 1
            print(f"\r  [{i}/{total}] {total_chunks} chunks ({errors} errors) | {rel_path}", end="", flush=True)

    print(f"\nDone. {indexed} files, {total_chunks} chunks, {errors} errors → {OUTPUT}")
    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"Size: {size_mb:.1f}MB")


if __name__ == "__main__":
    main()

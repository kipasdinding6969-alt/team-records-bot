"""RAG engine — Ollama nomic-embed-text embeddings stored in SQLite."""
import asyncio
import logging
import math
import time
from typing import Any, Dict, List, Optional

import aiohttp

from database_v2 import database_v2

logger = logging.getLogger(__name__)

OLLAMA_URL = 'http://localhost:11434'
EMBED_MODEL = 'nomic-embed-text'

# In-memory embedding cache — refreshed every 5 minutes.
_embedding_cache: List[Dict] = []
_cache_ts: float = 0.0
_CACHE_TTL = 300  # seconds


async def embed_text(text: str) -> List[float]:
    """Get embedding vector from Ollama nomic-embed-text."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f'{OLLAMA_URL}/api/embeddings',
            json={'model': EMBED_MODEL, 'prompt': text},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data['embedding']


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def _get_cached_embeddings() -> List[Dict]:
    """Return all embeddings, refreshing the in-memory cache every 5 minutes."""
    global _embedding_cache, _cache_ts
    if time.time() - _cache_ts > _CACHE_TTL or not _embedding_cache:
        _embedding_cache = await database_v2.get_all_embeddings()
        _cache_ts = time.time()
    return _embedding_cache


def _invalidate_cache():
    """Force next search_similar call to re-fetch from DB."""
    global _cache_ts
    _cache_ts = 0.0


async def search_similar(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search embeddings store for chunks most similar to query."""
    try:
        query_vec = await embed_text(query)
    except Exception as e:
        logger.error(f'RAG embed_text failed: {e}')
        return []

    all_embeddings = await _get_cached_embeddings()
    if not all_embeddings:
        return []

    scored = []
    for entry in all_embeddings:
        score = _cosine_similarity(query_vec, entry['embedding'])
        scored.append({
            'id': entry['id'],
            'source_type': entry['source_type'],
            'source_id': entry['source_id'],
            'text_chunk': entry['text_chunk'],
            'score': round(score, 4),
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_k]


async def index_client_notes(client_id: int):
    """Embed all notes for a client and store in embeddings table."""
    notes = await database_v2.get_client_notes(client_id, limit=50)
    if not notes:
        return

    # Concatenate all notes into one text chunk per client
    parts = []
    for n in notes:
        if n.content:
            parts.append(n.content)
        if n.old_status and n.new_status:
            parts.append(f'status: {n.old_status} → {n.new_status}')

    if not parts:
        return

    text_chunk = ' | '.join(parts)
    try:
        vec = await embed_text(text_chunk)
        await database_v2.upsert_embedding('client_notes', client_id, text_chunk, vec)
        _invalidate_cache()
        logger.debug(f'Indexed notes for client {client_id}')
    except Exception as e:
        logger.error(f'Failed to index notes for client {client_id}: {e}')


async def index_client_status(client_id: int, phone: str, status: str, note: Optional[str] = None):
    """Embed ALL status history for a client as a single concatenated chunk."""
    notes = await database_v2.get_client_notes(client_id, limit=50)
    status_changes = [n for n in notes if n.note_type.value == 'status_change']

    if status_changes:
        parts = []
        for n in status_changes:
            parts.append(f'client {phone}: {n.old_status} → {n.new_status}')
            if n.content:
                parts.append(n.content)
    else:
        # Fallback for very first status change (notes not yet in DB)
        parts = [f'client {phone} status {status}']
        if note:
            parts.append(note)

    text_chunk = ' | '.join(parts)
    try:
        vec = await embed_text(text_chunk)
        await database_v2.upsert_embedding('client_status', client_id, text_chunk, vec)
        _invalidate_cache()
    except Exception as e:
        logger.error(f'Failed to index status change for client {client_id}: {e}')


async def rebuild_index():
    """Rebuild full embeddings index from all client notes."""
    staff_list = await database_v2.get_all_staff()
    total = 0
    for s in staff_list:
        clients = await database_v2.export_clients_csv(frontdesk_id=s.id)
        for c in clients:
            await index_client_notes(c['id'])
            total += 1
            await asyncio.sleep(0.1)  # rate-limit Ollama calls
    _invalidate_cache()
    logger.info(f'RAG index rebuilt: {total} clients indexed')
    return total

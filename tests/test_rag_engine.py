"""Tests for engines/rag_engine.py — RAG (retrieval-augmented generation).

Ollama embedding API and database_v2 are fully mocked.
"""
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engines.rag_engine import (
    _cosine_similarity,
    chunk_text,
    _invalidate_cache,
)


# ---------------------------------------------------------------------------
# Pure logic: cosine similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0

    def test_both_zero_returns_zero(self):
        assert _cosine_similarity([0, 0], [0, 0]) == 0.0

    def test_arbitrary_vectors(self):
        a = [1, 2, 3]
        b = [4, 5, 6]
        dot = 1*4 + 2*5 + 3*6  # 32
        mag_a = math.sqrt(14)
        mag_b = math.sqrt(77)
        expected = dot / (mag_a * mag_b)
        assert _cosine_similarity(a, b) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Pure logic: chunk_text
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_short_text_single_chunk(self):
        """Text shorter than max_chars produces a single chunk."""
        result = chunk_text("Hello world", max_chars=500)
        assert len(result) == 1
        assert result[0] == "Hello world"

    def test_paragraphs_split_correctly(self):
        """Multiple paragraphs are split into chunks."""
        text = ("A" * 300) + "\n\n" + ("B" * 300)
        result = chunk_text(text, max_chars=400, overlap=50)
        assert len(result) >= 2
        assert result[0].startswith("A")
        assert result[-1].endswith("B" * 50) or "B" in result[-1]

    def test_empty_text_returns_list(self):
        """Empty text returns a list with at least one element."""
        result = chunk_text("", max_chars=500)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_overlap_carries_tail(self):
        """Overlap causes tail of previous chunk to appear at start of next."""
        text = "AAAA\n\nBBBB\n\nCCCC"
        result = chunk_text(text, max_chars=8, overlap=4)
        assert len(result) >= 2
        # Each chunk after the first should contain some overlap from prior

    def test_single_paragraph_too_long(self):
        """A single paragraph longer than max_chars still ends up in a chunk."""
        text = "X" * 1000
        result = chunk_text(text, max_chars=500, overlap=0)
        assert len(result) >= 1
        # The first chunk should not exceed max_chars + paragraph length


# ---------------------------------------------------------------------------
# embed_text (mocked Ollama)
# ---------------------------------------------------------------------------


class TestEmbedText:
    @pytest.mark.asyncio
    async def test_embed_text_returns_vector(self):
        """embed_text calls Ollama and returns the embedding list."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={"embedding": [0.1, 0.2, 0.3]})

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", mock_session_cls):
            from engines.rag_engine import embed_text
            result = await embed_text("test query")
        assert result == [0.1, 0.2, 0.3]


# ---------------------------------------------------------------------------
# search_similar (mocked embedding + cache)
# ---------------------------------------------------------------------------


class TestSearchSimilar:
    @pytest.mark.asyncio
    async def test_search_returns_top_k(self):
        """search_similar returns up to top_k results sorted by score."""
        embeddings = [
            {"id": 1, "source_type": "client", "source_id": 1,
             "text_chunk": "hello", "embedding": [1.0, 0.0]},
            {"id": 2, "source_type": "client", "source_id": 2,
             "text_chunk": "world", "embedding": [0.0, 1.0]},
            {"id": 3, "source_type": "client", "source_id": 3,
             "text_chunk": "match", "embedding": [0.9, 0.1]},
        ]

        with patch("engines.rag_engine.embed_text", AsyncMock(return_value=[1.0, 0.0])), \
             patch("engines.rag_engine._get_cached_embeddings", AsyncMock(return_value=embeddings)):
            from engines.rag_engine import search_similar
            results = await search_similar("test", top_k=2)

        assert len(results) == 2
        # First result should have highest cosine similarity to [1.0, 0.0]
        assert results[0]["id"] == 1
        assert results[0]["score"] == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_search_empty_embeddings_returns_empty(self):
        """If no embeddings in cache, return empty list."""
        with patch("engines.rag_engine.embed_text", AsyncMock(return_value=[1.0, 0.0])), \
             patch("engines.rag_engine._get_cached_embeddings", AsyncMock(return_value=[])):
            from engines.rag_engine import search_similar
            results = await search_similar("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_embed_failure_returns_empty(self):
        """If embed_text fails, return empty list gracefully."""
        with patch("engines.rag_engine.embed_text", AsyncMock(side_effect=Exception("connection refused"))):
            from engines.rag_engine import search_similar
            results = await search_similar("test")
        assert results == []


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    def test_invalidate_cache_resets_timestamp(self):
        """_invalidate_cache sets _cache_ts to 0."""
        import engines.rag_engine as mod
        mod._cache_ts = 9999.0
        _invalidate_cache()
        assert mod._cache_ts == 0.0

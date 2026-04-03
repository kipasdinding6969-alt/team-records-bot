"""Tests for engines/voice_engine.py — transcription + intent parsing.

NOTE: test_voice.py already covers voice_engine exhaustively. This file adds
a few targeted smoke tests for the engine module's standalone functions and
constants to ensure module-level invariants hold.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engines.voice_engine import (
    _PIPELINE_STATUSES,
    _INTENT_SYSTEM,
)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_pipeline_statuses_complete(self):
        """All expected pipeline statuses are defined."""
        expected = {
            "new", "contacted", "replied", "registered",
            "training", "withdrew", "ordered", "ghosted", "blocked", "dead",
        }
        assert set(_PIPELINE_STATUSES) == expected

    def test_intent_system_prompt_mentions_json(self):
        """System prompt instructs the LLM to return JSON."""
        assert "JSON" in _INTENT_SYSTEM or "json" in _INTENT_SYSTEM

    def test_intent_system_prompt_mentions_statuses(self):
        """System prompt lists pipeline statuses for the LLM."""
        for status in ("registered", "training", "ghosted"):
            assert status in _INTENT_SYSTEM


# ---------------------------------------------------------------------------
# transcribe()
# ---------------------------------------------------------------------------


class TestTranscribeSmoke:
    @pytest.mark.asyncio
    async def test_transcribe_nonexistent_file_returns_none(self):
        """Non-existent path returns None gracefully."""
        from engines.voice_engine import transcribe
        result = await transcribe("/tmp/no_such_file_xyz.ogg")
        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_empty_text_returns_none(self):
        """If whisper produces empty text, returns None."""
        mock_segment = MagicMock()
        mock_segment.text = ""

        mock_model = MagicMock()
        mock_model.transcribe = MagicMock(return_value=([mock_segment], None))

        mock_fw = MagicMock()
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        with patch.dict("sys.modules", {"faster_whisper": mock_fw}):
            from engines.voice_engine import transcribe
            result = await transcribe("/tmp/fake.ogg")
        assert result is None


# ---------------------------------------------------------------------------
# parse_intent()
# ---------------------------------------------------------------------------


class TestParseIntentSmoke:
    def _mock_session(self, status, body):
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=body)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_session_cls

    @pytest.mark.asyncio
    async def test_parse_intent_returns_four_keys(self):
        """Result always has client_name, client_phone, new_status, note."""
        payload = {"response": json.dumps({
            "client_name": "Test",
            "client_phone": "123",
            "new_status": "new",
            "note": "hi",
        })}
        with patch("aiohttp.ClientSession", self._mock_session(200, payload)):
            from engines.voice_engine import parse_intent
            result = await parse_intent("test text")
        assert set(result.keys()) == {"client_name", "client_phone", "new_status", "note"}

    @pytest.mark.asyncio
    async def test_parse_intent_bad_json_returns_empty(self):
        """Malformed JSON from Ollama returns all-None dict."""
        payload = {"response": "NOT VALID JSON {{{"}
        with patch("aiohttp.ClientSession", self._mock_session(200, payload)):
            from engines.voice_engine import parse_intent
            result = await parse_intent("test text")
        assert result == {"client_name": None, "client_phone": None, "new_status": None, "note": None}

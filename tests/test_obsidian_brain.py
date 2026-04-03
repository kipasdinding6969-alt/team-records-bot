"""Tests for engines/obsidian_brain.py — Obsidian REST API client.

All HTTP requests to the Obsidian REST API are fully mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engines.obsidian_brain import ObsidianBrain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status, json_body=None, text_body="", content_type="application/json"):
    """Build an async context manager for aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body or {})
    resp.text = AsyncMock(return_value=text_body)
    resp.headers = {"content-type": content_type}
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_session(response_ctx):
    """Build a mock aiohttp.ClientSession that returns a fixed response."""
    session = MagicMock()
    session.get = MagicMock(return_value=response_ctx)
    session.put = MagicMock(return_value=response_ctx)
    session.post = MagicMock(return_value=response_ctx)

    session_cls = MagicMock()
    session_cls.return_value.__aenter__ = AsyncMock(return_value=session)
    session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return session_cls


# ---------------------------------------------------------------------------
# Tests: low-level HTTP methods
# ---------------------------------------------------------------------------


class TestGet:
    @pytest.mark.asyncio
    async def test_get_json_response(self):
        """_get returns parsed JSON when content-type is json."""
        resp_ctx = _mock_response(200, json_body={"files": ["a.md", "b.md"]})
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain._get("/vault/docs/", {"list": "true"})
        assert result == {"files": ["a.md", "b.md"]}

    @pytest.mark.asyncio
    async def test_get_text_response(self):
        """_get returns text when content-type is not json."""
        resp_ctx = _mock_response(200, text_body="# Hello", content_type="text/markdown")
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain._get("/vault/note.md", None)
        assert result == "# Hello"

    @pytest.mark.asyncio
    async def test_get_non_200_returns_none(self):
        """_get returns None for non-200 status."""
        resp_ctx = _mock_response(404)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain._get("/vault/missing.md", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_exception_returns_none(self):
        """_get returns None on network error."""
        with patch("aiohttp.ClientSession", side_effect=Exception("connection refused")):
            brain = ObsidianBrain()
            result = await brain._get("/vault/x.md", None)
        assert result is None


class TestPut:
    @pytest.mark.asyncio
    async def test_put_success(self):
        """_put returns True on 200/201/204."""
        for status in (200, 201, 204):
            resp_ctx = _mock_response(status)
            with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
                brain = ObsidianBrain()
                result = await brain._put("/vault/note.md", "content")
            assert result is True

    @pytest.mark.asyncio
    async def test_put_failure(self):
        """_put returns False on error status."""
        resp_ctx = _mock_response(500)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain._put("/vault/note.md", "content")
        assert result is False


class TestPost:
    @pytest.mark.asyncio
    async def test_post_success(self):
        """_post returns True on success."""
        resp_ctx = _mock_response(200)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain._post("/vault/note.md", "appended")
        assert result is True


# ---------------------------------------------------------------------------
# Tests: high-level API
# ---------------------------------------------------------------------------


class TestListFiles:
    @pytest.mark.asyncio
    async def test_list_files_returns_file_list(self):
        """list_files returns files from vault directory."""
        resp_ctx = _mock_response(200, json_body={"files": ["a.md", "b.md", "c.md"]})
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            files = await brain.list_files("docs")
        assert files == ["a.md", "b.md", "c.md"]

    @pytest.mark.asyncio
    async def test_list_files_empty_on_error(self):
        """list_files returns [] when API fails."""
        resp_ctx = _mock_response(500)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            files = await brain.list_files("docs")
        assert files == []


class TestReadNote:
    @pytest.mark.asyncio
    async def test_read_note_returns_content(self):
        """read_note returns note content as string."""
        resp_ctx = _mock_response(200, text_body="# My Note\nSome content", content_type="text/markdown")
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            content = await brain.read_note("workspace/note.md")
        assert "# My Note" in content

    @pytest.mark.asyncio
    async def test_read_note_missing_returns_empty(self):
        """read_note returns '' for missing note."""
        resp_ctx = _mock_response(404)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            content = await brain.read_note("missing.md")
        assert content == ""


class TestWriteNote:
    @pytest.mark.asyncio
    async def test_write_note_success(self):
        """write_note returns True on success."""
        resp_ctx = _mock_response(201)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain.write_note("workspace/new.md", "# New Note")
        assert result is True


class TestAppendNote:
    @pytest.mark.asyncio
    async def test_append_note_success(self):
        """append_note returns True on success."""
        resp_ctx = _mock_response(200)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain.append_note("workspace/log.md", "\n## New Entry")
        assert result is True


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """search returns list of matching results."""
        results = [
            {"filename": "docs/sop.md", "matches": [{"match": "hello"}]},
            {"filename": "docs/guide.md", "matches": [{"match": "hello"}]},
        ]
        resp_ctx = _mock_response(200, json_body=results)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            found = await brain.search("hello")
        assert len(found) == 2

    @pytest.mark.asyncio
    async def test_search_empty_on_error(self):
        """search returns [] on API failure."""
        resp_ctx = _mock_response(500)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            found = await brain.search("test")
        assert found == []


# ---------------------------------------------------------------------------
# Tests: domain operations
# ---------------------------------------------------------------------------


class TestLogClientInteraction:
    @pytest.mark.asyncio
    async def test_append_succeeds(self):
        """log_client_interaction appends to existing note."""
        resp_ctx = _mock_response(200)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            await brain.log_client_interaction("0123456789", "阿YIM", "Called client")
        # No exception means success

    @pytest.mark.asyncio
    async def test_creates_new_note_on_append_failure(self):
        """If append fails, log_client_interaction creates a new note."""
        fail_resp = _mock_response(404)
        success_resp = _mock_response(201)

        session = MagicMock()
        session.post = MagicMock(return_value=fail_resp)  # append fails
        session.put = MagicMock(return_value=success_resp)  # write succeeds

        session_cls = MagicMock()
        session_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", session_cls):
            brain = ObsidianBrain()
            await brain.log_client_interaction("0123456789", "阿YIM", "Called client")
        # write_note should be called as fallback
        session.put.assert_called()


class TestSaveDailyReport:
    @pytest.mark.asyncio
    async def test_save_report(self):
        """save_daily_report writes to memory/reports/."""
        resp_ctx = _mock_response(201)
        with patch("aiohttp.ClientSession", _mock_session(resp_ctx)):
            brain = ObsidianBrain()
            result = await brain.save_daily_report("2024-03-15", "Report text here")
        assert result is True


class TestGetSop:
    @pytest.mark.asyncio
    async def test_get_sop_no_results(self):
        """get_sop returns '' when no search results."""
        empty_resp = _mock_response(200, json_body=[])
        with patch("aiohttp.ClientSession", _mock_session(empty_resp)):
            brain = ObsidianBrain()
            result = await brain.get_sop("nonexistent")
        assert result == ""

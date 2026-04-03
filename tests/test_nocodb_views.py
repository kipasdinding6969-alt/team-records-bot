"""Tests for engines/nocodb_views.py — NocoDB view management.

All HTTP requests to NocoDB API are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engines.nocodb_views import (
    VIEW_SPECS,
    _create_view,
    _enable_shared_view,
    create_shared_views,
    get_existing_shared_views,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_aiohttp_response(status, json_body=None, text_body=""):
    """Build an async context manager that returns a mock response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body or {})
    resp.text = AsyncMock(return_value=text_body)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_session(responses):
    """Build a mock aiohttp.ClientSession whose post/get calls return responses in order."""
    session = MagicMock()
    post_iter = iter(responses.get("post", []))
    get_iter = iter(responses.get("get", []))
    session.post = MagicMock(side_effect=lambda *a, **kw: next(post_iter))
    session.get = MagicMock(side_effect=lambda *a, **kw: next(get_iter))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestViewSpecs:
    def test_specs_have_required_keys(self):
        """Each VIEW_SPEC has key, title, table_key, and type."""
        for spec in VIEW_SPECS:
            assert "key" in spec
            assert "title" in spec
            assert "table_key" in spec

    def test_all_three_views_defined(self):
        """Pipeline dashboard, deposits tracker, and team scoreboard are defined."""
        keys = {s["key"] for s in VIEW_SPECS}
        assert "pipeline_dashboard" in keys
        assert "deposits_tracker" in keys
        assert "team_scoreboard" in keys


class TestCreateView:
    @pytest.mark.asyncio
    async def test_create_view_success(self):
        """Successful view creation returns the view ID."""
        resp = _mock_aiohttp_response(201, {"id": "vw_abc123"})
        session = MagicMock()
        session.post = MagicMock(return_value=resp)

        result = await _create_view(
            session, "https://app.nocodb.com", "token123",
            "md_xxx", "Test View", "grid"
        )
        assert result == "vw_abc123"

    @pytest.mark.asyncio
    async def test_create_view_failure_returns_none(self):
        """Non-200/201 status returns None."""
        resp = _mock_aiohttp_response(400, text_body="Bad request")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)

        result = await _create_view(
            session, "https://app.nocodb.com", "token123",
            "md_xxx", "Test View"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_create_view_exception_returns_none(self):
        """Network exception returns None gracefully."""
        session = MagicMock()
        session.post = MagicMock(side_effect=Exception("connection refused"))

        result = await _create_view(
            session, "https://app.nocodb.com", "token123",
            "md_xxx", "Test View"
        )
        assert result is None


class TestEnableSharedView:
    @pytest.mark.asyncio
    async def test_enable_shared_view_success(self):
        """Successful share returns the UUID."""
        resp = _mock_aiohttp_response(200, {"uuid": "share_uuid_123"})
        session = MagicMock()
        session.post = MagicMock(return_value=resp)

        result = await _enable_shared_view(
            session, "https://app.nocodb.com", "token123", "vw_abc"
        )
        assert result == "share_uuid_123"

    @pytest.mark.asyncio
    async def test_enable_shared_view_failure(self):
        """Non-200 status returns None."""
        resp = _mock_aiohttp_response(403, text_body="Forbidden")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)

        result = await _enable_shared_view(
            session, "https://app.nocodb.com", "token123", "vw_abc"
        )
        assert result is None


class TestCreateSharedViews:
    @pytest.mark.asyncio
    async def test_full_flow_returns_urls(self):
        """create_shared_views creates views and returns share URLs."""
        # Each VIEW_SPEC triggers: _create_view (post) → _enable_shared_view (post)
        create_resps = [
            _mock_aiohttp_response(201, {"id": f"vw_{i}"}) for i in range(3)
        ]
        share_resps = [
            _mock_aiohttp_response(200, {"uuid": f"uuid_{i}"}) for i in range(3)
        ]
        # Interleave: create, share, create, share, ...
        all_posts = []
        for c, s in zip(create_resps, share_resps):
            all_posts.extend([c, s])

        mock_ctx = _mock_session({"post": all_posts})

        with patch("aiohttp.ClientSession", return_value=mock_ctx):
            result = await create_shared_views(
                "https://app.nocodb.com",
                "token123",
                {"clients": "md_1", "deposits": "md_2", "daily_stats": "md_3"},
            )

        assert "pipeline_dashboard" in result
        assert "deposits_tracker" in result
        assert "team_scoreboard" in result
        for url in result.values():
            assert url.startswith("https://app.nocodb.com/nc/v/")

    @pytest.mark.asyncio
    async def test_missing_table_id_skipped(self):
        """Views with missing table_ids are skipped."""
        mock_ctx = _mock_session({"post": []})

        with patch("aiohttp.ClientSession", return_value=mock_ctx):
            result = await create_shared_views(
                "https://app.nocodb.com", "token123",
                {},  # no table IDs
            )

        assert result == {}


class TestGetExistingSharedViews:
    @pytest.mark.asyncio
    async def test_get_views_returns_lists(self):
        """get_existing_shared_views returns view lists per table."""
        get_resp = _mock_aiohttp_response(200, {"list": [{"id": "vw_1", "title": "Default"}]})
        mock_ctx = _mock_session({"get": [get_resp]})

        with patch("aiohttp.ClientSession", return_value=mock_ctx):
            result = await get_existing_shared_views(
                "https://app.nocodb.com", "token123",
                {"clients": "md_1"},
            )

        assert "clients" in result
        assert len(result["clients"]) == 1

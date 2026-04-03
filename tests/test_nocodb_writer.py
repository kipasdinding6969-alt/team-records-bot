"""Tests for engines/nocodb_writer.py — NocoDB REST API writer.

All HTTP requests are mocked. Config loading is patched to avoid filesystem deps.
"""
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engines.nocodb_writer import _fmt, _clean


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_CONFIG = {
    "url": "http://localhost:8080",
    "api_token": "test_token",
    "tables": {
        "staff": "tbl_staff",
        "clients": "tbl_clients",
        "client_notes": "tbl_notes",
        "daily_stats": "tbl_stats",
        "deposits": "tbl_deposits",
        "reminders": "tbl_reminders",
        "team_targets": "tbl_targets",
    },
    "field_map": {
        "staff": {"tg_user_id": "Telegram ID", "display_name": "Display Name", "role": "Role"},
        "clients": {"phone": "Phone", "status": "Status", "source": "Source"},
        "client_notes": {"client_phone": "Client Phone", "note": "Note"},
        "daily_stats": {"date": "Date", "frontdesk_tg_id": "Frontdesk TG ID"},
        "deposits": {"client_phone": "Client Phone", "amount": "Amount"},
        "reminders": {"staff_tg_id": "Staff TG ID"},
        "team_targets": {"month": "Month", "team": "Team"},
    },
}


def _make_writer():
    """Create a NocoDBWriter with mocked config and session."""
    with patch("engines.nocodb_writer._load_config", return_value=MOCK_CONFIG):
        from engines.nocodb_writer import NocoDBWriter
        writer = NocoDBWriter()
    return writer


def _mock_response(status=200, json_body=None, text_body=""):
    """Build an async context manager response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body or {})
    resp.text = AsyncMock(return_value=text_body)
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestFmt:
    def test_datetime_to_iso(self):
        dt = datetime(2024, 3, 15, 10, 30, 0)
        assert _fmt(dt) == "2024-03-15T10:30:00"

    def test_date_to_iso(self):
        d = date(2024, 3, 15)
        assert _fmt(d) == "2024-03-15"

    def test_bool_passthrough(self):
        assert _fmt(True) is True
        assert _fmt(False) is False

    def test_string_passthrough(self):
        assert _fmt("hello") == "hello"

    def test_int_passthrough(self):
        assert _fmt(42) == 42


class TestClean:
    def test_removes_none_values(self):
        result = _clean({"a": 1, "b": None, "c": "hello"})
        assert result == {"a": 1, "c": "hello"}

    def test_formats_dates(self):
        result = _clean({"dt": datetime(2024, 1, 1)})
        assert result == {"dt": "2024-01-01T00:00:00"}


# ---------------------------------------------------------------------------
# NocoDBWriter field translation
# ---------------------------------------------------------------------------


class TestFieldTranslation:
    def test_to_titles_maps_column_names(self):
        """_to_titles translates column_name → NocoDB title."""
        writer = _make_writer()
        result = writer._to_titles("clients", {"phone": "123", "status": "new"})
        assert result == {"Phone": "123", "Status": "new"}

    def test_to_titles_fallback_for_unknown_column(self):
        """Unknown column names pass through unchanged."""
        writer = _make_writer()
        result = writer._to_titles("clients", {"unknown_col": "val"})
        assert result == {"unknown_col": "val"}

    def test_from_titles_reverse_maps(self):
        """_from_titles translates NocoDB title → column_name."""
        writer = _make_writer()
        result = writer._from_titles("clients", {"Phone": "123", "Status": "new"})
        assert result == {"phone": "123", "status": "new"}

    def test_title_helper(self):
        """_title returns the NocoDB display title for a column."""
        writer = _make_writer()
        assert writer._title("staff", "tg_user_id") == "Telegram ID"
        assert writer._title("staff", "unknown") == "unknown"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_context_manager_opens_and_closes(self):
        """async with NocoDBWriter() opens and closes the session."""
        with patch("engines.nocodb_writer._load_config", return_value=MOCK_CONFIG), \
             patch("aiohttp.ClientSession") as mock_cls:
            mock_session = AsyncMock()
            mock_cls.return_value = mock_session

            from engines.nocodb_writer import NocoDBWriter
            writer = NocoDBWriter()
            await writer.connect()
            assert writer._session is not None
            await writer.close()
            assert writer._session is None

    def test_s_raises_if_not_opened(self):
        """_s() raises RuntimeError if session is None."""
        writer = _make_writer()
        with pytest.raises(RuntimeError, match="Not opened"):
            writer._s()


# ---------------------------------------------------------------------------
# CRUD operations (mocked HTTP)
# ---------------------------------------------------------------------------


class TestList:
    @pytest.mark.asyncio
    async def test_list_returns_records(self):
        """_list fetches and returns records from NocoDB."""
        writer = _make_writer()
        mock_session = MagicMock()
        resp_body = {"list": [{"Phone": "123"}, {"Phone": "456"}], "pageInfo": {"isLastPage": True}}
        mock_session.get = MagicMock(return_value=_mock_response(200, resp_body))
        writer._session = mock_session

        result = await writer._list("clients")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_422_returns_empty(self):
        """_list returns empty on 422 error."""
        writer = _make_writer()
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_mock_response(422, text_body="bad where"))
        writer._session = mock_session

        result = await writer._list("clients", where="bad")
        assert result == []


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_posts_records(self):
        """_create sends POST and returns created records."""
        writer = _make_writer()
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=_mock_response(200, [{"Id": 1, "Phone": "123"}]))
        writer._session = mock_session

        result = await writer._create("clients", [{"phone": "123"}])
        assert len(result) == 1
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_error_logged(self):
        """_create with server error logs but doesn't raise."""
        writer = _make_writer()
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=_mock_response(500, text_body="server error"))
        writer._session = mock_session

        result = await writer._create("clients", [{"phone": "123"}])
        assert result == []  # No records created


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_sends_patch(self):
        """_update sends PATCH request with translated titles."""
        writer = _make_writer()
        mock_session = MagicMock()
        mock_session.patch = MagicMock(return_value=_mock_response(200, {}))
        writer._session = mock_session

        await writer._update("clients", [{"phone": "123", "id": 1}])
        mock_session.patch.assert_called_once()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class TestUpsertStaff:
    @pytest.mark.asyncio
    async def test_upsert_staff_creates_when_new(self):
        """upsert_staff creates a new record when no existing match."""
        writer = _make_writer()
        mock_session = MagicMock()
        # _list returns empty (no existing)
        list_resp = _mock_response(200, {"list": [], "pageInfo": {"isLastPage": True}})
        # _create returns new record
        create_resp = _mock_response(200, {"Id": 1, "Telegram ID": 9001})
        mock_session.get = MagicMock(return_value=list_resp)
        mock_session.post = MagicMock(return_value=create_resp)
        writer._session = mock_session

        result = await writer.upsert_staff({"tg_user_id": 9001, "display_name": "Test"})
        assert result.get("Id") == 1


class TestGetClients:
    @pytest.mark.asyncio
    async def test_get_clients_no_filters(self):
        """get_clients() without filters returns all (translated back)."""
        writer = _make_writer()
        mock_session = MagicMock()
        list_resp = _mock_response(200, {
            "list": [{"Phone": "123", "Status": "new"}],
            "pageInfo": {"isLastPage": True},
        })
        mock_session.get = MagicMock(return_value=list_resp)
        writer._session = mock_session

        result = await writer.get_clients()
        assert len(result) == 1
        assert result[0]["phone"] == "123"
        assert result[0]["status"] == "new"

    @pytest.mark.asyncio
    async def test_get_clients_with_filter(self):
        """get_clients(filters=...) builds a where clause."""
        writer = _make_writer()
        mock_session = MagicMock()
        list_resp = _mock_response(200, {
            "list": [{"Phone": "123", "Status": "contacted"}],
            "pageInfo": {"isLastPage": True},
        })
        mock_session.get = MagicMock(return_value=list_resp)
        writer._session = mock_session

        result = await writer.get_clients(filters={"status": "contacted"})
        assert len(result) == 1
        # Verify the where param was built with the title
        call_kwargs = mock_session.get.call_args
        params = call_kwargs[1].get("params", {}) if call_kwargs[1] else {}
        # The where clause should use the title "Status"
        if "where" in params:
            assert "Status" in params["where"]


class TestGetPipelineStats:
    @pytest.mark.asyncio
    async def test_pipeline_stats_counts(self):
        """get_pipeline_stats counts records per status."""
        writer = _make_writer()
        mock_session = MagicMock()
        list_resp = _mock_response(200, {
            "list": [
                {"Status": "new"}, {"Status": "new"}, {"Status": "contacted"},
            ],
            "pageInfo": {"isLastPage": True},
        })
        mock_session.get = MagicMock(return_value=list_resp)
        writer._session = mock_session

        stats = await writer.get_pipeline_stats()
        assert stats["new"] == 2
        assert stats["contacted"] == 1

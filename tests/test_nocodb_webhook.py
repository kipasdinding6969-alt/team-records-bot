"""Tests for engines/nocodb_webhook.py — NocoDB webhook handler.

database_v2 and aiohttp are fully mocked.
"""
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engines.nocodb_webhook import (
    _verify_hmac,
    _parse_event,
    process_webhook_event,
)


# ---------------------------------------------------------------------------
# _verify_hmac
# ---------------------------------------------------------------------------


class TestVerifyHmac:
    def test_no_secret_configured_passes(self):
        """When WEBHOOK_SECRET is empty, all signatures pass."""
        with patch("engines.nocodb_webhook.WEBHOOK_SECRET", ""):
            assert _verify_hmac(b"anything", "whatever") is True

    def test_valid_signature_passes(self):
        """Correct HMAC-SHA256 signature is accepted."""
        secret = "testsecret"
        body = b'{"type":"records.update","data":{}}'
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        with patch("engines.nocodb_webhook.WEBHOOK_SECRET", secret):
            assert _verify_hmac(body, expected) is True

    def test_invalid_signature_fails(self):
        """Wrong HMAC signature is rejected."""
        with patch("engines.nocodb_webhook.WEBHOOK_SECRET", "testsecret"):
            assert _verify_hmac(b"body", "wrong_sig") is False

    def test_sha256_prefix_lstrip_behavior(self):
        """lstrip('sha256=') strips individual chars, not the literal prefix.

        This is a known quirk of the source code. We verify the function
        behaves consistently with Python's str.lstrip semantics.
        """
        secret = "testsecret"
        body = b"data"
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # lstrip removes all leading chars in the character set {'s','h','a','2','5','6','='}
        stripped = f"sha256={digest}".lstrip("sha256=")

        with patch("engines.nocodb_webhook.WEBHOOK_SECRET", secret):
            # The function compares digest to stripped — they may or may not match
            result = _verify_hmac(body, f"sha256={digest}")
            expected = hmac.compare_digest(digest, stripped)
            assert result == expected


# ---------------------------------------------------------------------------
# _parse_event
# ---------------------------------------------------------------------------


class TestParseEvent:
    def test_insert_event(self):
        """records.insert is parsed as op='insert'."""
        payload = {
            "type": "records.insert",
            "data": {
                "table_name": "Clients",
                "rows": [{"phone": "123", "status": "new"}],
            },
        }
        result = _parse_event(payload)
        assert result["table"] == "clients"
        assert result["op"] == "insert"
        assert len(result["rows"]) == 1

    def test_update_event(self):
        """records.update is parsed as op='update'."""
        payload = {
            "type": "records.update",
            "data": {
                "table_name": "clients",
                "rows": [{"phone": "123", "status": "contacted"}],
            },
        }
        result = _parse_event(payload)
        assert result["op"] == "update"

    def test_delete_event(self):
        """records.delete is parsed as op='delete'."""
        payload = {
            "type": "records.delete",
            "data": {
                "table_name": "clients",
                "rows": [{"phone": "123"}],
            },
        }
        result = _parse_event(payload)
        assert result["op"] == "delete"

    def test_create_event(self):
        """records.create maps to op='insert'."""
        payload = {
            "type": "records.create",
            "data": {"table_name": "Staff", "rows": [{"tg_user_id": 123}]},
        }
        result = _parse_event(payload)
        assert result["op"] == "insert"

    def test_single_record_dict_wrapped_in_list(self):
        """If 'record' is a dict (not list), it's wrapped in a list."""
        payload = {
            "type": "records.update",
            "data": {
                "tableName": "clients",
                "record": {"phone": "123"},
            },
        }
        result = _parse_event(payload)
        assert len(result["rows"]) == 1
        assert result["rows"][0]["phone"] == "123"

    def test_table_name_case_insensitive(self):
        """Table name is always lowercased."""
        payload = {
            "type": "records.update",
            "data": {"table_name": "CLIENTS", "rows": []},
        }
        result = _parse_event(payload)
        assert result["table"] == "clients"

    def test_fallback_tablename_key(self):
        """data.tableName fallback when table_name missing."""
        payload = {
            "type": "records.insert",
            "data": {"tableName": "Staff", "rows": []},
        }
        result = _parse_event(payload)
        assert result["table"] == "staff"


# ---------------------------------------------------------------------------
# process_webhook_event
# ---------------------------------------------------------------------------


class TestProcessWebhookEvent:
    @pytest.mark.asyncio
    async def test_client_insert_calls_upsert(self):
        """Client table insert dispatches to _upsert_client."""
        with patch("engines.nocodb_webhook._upsert_client", new_callable=AsyncMock) as mock_upsert:
            event = {
                "table": "clients",
                "op": "insert",
                "rows": [{"phone": "123", "status": "new", "frontdesk_id": 1}],
            }
            await process_webhook_event(event)
            mock_upsert.assert_called_once_with(event["rows"][0])

    @pytest.mark.asyncio
    async def test_client_delete_skipped(self):
        """Delete operations on clients are skipped (not upserted)."""
        with patch("engines.nocodb_webhook._upsert_client", new_callable=AsyncMock) as mock_upsert:
            event = {"table": "clients", "op": "delete", "rows": [{"phone": "123"}]}
            await process_webhook_event(event)
            mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_staff_insert_calls_upsert_staff(self):
        """Staff table insert dispatches to _upsert_staff."""
        with patch("engines.nocodb_webhook._upsert_staff", new_callable=AsyncMock) as mock_upsert:
            event = {
                "table": "staff",
                "op": "insert",
                "rows": [{"tg_user_id": 9001, "role": "frontdesk"}],
            }
            await process_webhook_event(event)
            mock_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_table_ignored(self):
        """Unknown tables are silently ignored."""
        with patch("engines.nocodb_webhook._upsert_client", new_callable=AsyncMock) as mock_client, \
             patch("engines.nocodb_webhook._upsert_staff", new_callable=AsyncMock) as mock_staff:
            event = {"table": "unknown_table", "op": "insert", "rows": [{"x": 1}]}
            await process_webhook_event(event)
            mock_client.assert_not_called()
            mock_staff.assert_not_called()

    @pytest.mark.asyncio
    async def test_row_error_does_not_stop_processing(self):
        """An error in one row doesn't prevent others from being processed."""
        call_count = 0

        async def _fake_upsert(row):
            nonlocal call_count
            call_count += 1
            if row.get("phone") == "bad":
                raise ValueError("bad row")

        with patch("engines.nocodb_webhook._upsert_client", side_effect=_fake_upsert):
            event = {
                "table": "clients",
                "op": "insert",
                "rows": [
                    {"phone": "bad", "frontdesk_id": 1},
                    {"phone": "good", "frontdesk_id": 1},
                ],
            }
            await process_webhook_event(event)
        assert call_count == 2  # Both rows attempted


# ---------------------------------------------------------------------------
# _upsert_client (mocked database_v2)
# ---------------------------------------------------------------------------


class TestUpsertClient:
    @pytest.mark.asyncio
    async def test_new_client_inserted(self):
        """New phone number creates a new client in DB."""
        mock_db = MagicMock()
        mock_db.get_client_by_phone = AsyncMock(return_value=None)
        mock_db.create_client = AsyncMock(return_value=1)

        with patch("engines.nocodb_webhook.database_v2", mock_db):
            from engines.nocodb_webhook import _upsert_client
            await _upsert_client({
                "phone": "0123456789",
                "status": "new",
                "frontdesk_id": 1,
                "source": "telegram",
            })
        mock_db.create_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_phone_skipped(self):
        """Row without phone is skipped."""
        mock_db = MagicMock()
        mock_db.get_client_by_phone = AsyncMock()
        mock_db.create_client = AsyncMock()

        with patch("engines.nocodb_webhook.database_v2", mock_db):
            from engines.nocodb_webhook import _upsert_client
            await _upsert_client({"status": "new", "frontdesk_id": 1})
        mock_db.create_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_frontdesk_id_skipped(self):
        """Row without frontdesk_id is skipped."""
        mock_db = MagicMock()
        mock_db.get_client_by_phone = AsyncMock(return_value=None)
        mock_db.create_client = AsyncMock()

        with patch("engines.nocodb_webhook.database_v2", mock_db):
            from engines.nocodb_webhook import _upsert_client
            await _upsert_client({"phone": "123"})
        mock_db.create_client.assert_not_called()

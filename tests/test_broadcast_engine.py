"""Tests for engines/broadcast_engine.py — template rendering, segment targeting, send tracking."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from engines.broadcast_engine import (
    _render_template, get_segment_targets, send_broadcast,
    get_segment_types, get_status_values,
)


# ─── Template rendering ───────────────────────────────────────────────────────

class TestRenderTemplate:
    def test_substitute_name(self):
        result = _render_template('Hello {name}!', {'nickname': 'Alice', 'phone': '123'})
        assert result == 'Hello Alice!'

    def test_fallback_to_phone(self):
        result = _render_template('Hi {name}', {'phone': '9876'})
        assert result == 'Hi 9876'

    def test_substitute_status(self):
        result = _render_template('Status: {status}', {'status': 'contacted'})
        assert result == 'Status: contacted'

    def test_days_since_contact_with_datetime(self):
        two_days_ago = datetime.now(timezone.utc).replace(microsecond=0)
        result = _render_template('{days_since_contact}d ago', {
            'contacted_at': two_days_ago,
        })
        assert '0d ago' in result

    def test_days_since_contact_with_string(self):
        iso_str = datetime.now(timezone.utc).isoformat()
        result = _render_template('{days_since_contact} days', {
            'contacted_at': iso_str,
        })
        assert '0 days' in result

    def test_days_since_contact_none(self):
        result = _render_template('{days_since_contact} days', {})
        assert '0 days' in result

    def test_no_substitution_needed(self):
        result = _render_template('Plain text', {'name': 'A'})
        assert result == 'Plain text'

    def test_all_placeholders(self):
        result = _render_template('{name} {status} {days_since_contact}', {
            'nickname': 'Bob', 'status': 'new',
        })
        assert 'Bob' in result
        assert 'new' in result
        assert '0' in result

    def test_empty_nickname_and_phone(self):
        result = _render_template('Hi {name}', {})
        assert result == 'Hi '


# ─── Segment targets ──────────────────────────────────────────────────────────

class TestGetSegmentTargets:
    @pytest.mark.asyncio
    async def test_delegates_to_db(self):
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=[
            {'phone': '111', 'status': 'new'},
            {'phone': '222', 'status': 'new'},
        ])

        with patch('engines.broadcast_engine.database_v2', mock_db):
            targets = await get_segment_targets('status', 'new')

        assert len(targets) == 2
        mock_db.get_broadcast_targets.assert_awaited_once_with('status', 'new', None, None)

    @pytest.mark.asyncio
    async def test_passes_date_range(self):
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=[])

        with patch('engines.broadcast_engine.database_v2', mock_db):
            await get_segment_targets('date_range', 'all', '2024-01-01', '2024-12-31')

        mock_db.get_broadcast_targets.assert_awaited_once_with(
            'date_range', 'all', '2024-01-01', '2024-12-31')


# ─── Send broadcast ───────────────────────────────────────────────────────────

class TestSendBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_segment(self):
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=[])
        mock_db.create_broadcast_log = AsyncMock(return_value=1)
        mock_db.update_broadcast_log = AsyncMock()
        mock_tg = MagicMock()

        with patch('engines.broadcast_engine.database_v2', mock_db), \
             patch('engines.broadcast_engine.telegram_handler', mock_tg):
            result = await send_broadcast(
                staff_id=1, template='Hi {name}',
                segment_type='status', segment_value='new')

        assert result['total'] == 0
        assert result['sent'] == 0
        assert result['failed'] == 0
        mock_db.update_broadcast_log.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_targets(self):
        targets = [
            {'phone': '111', 'nickname': 'A', 'status': 'new'},
            {'phone': '222', 'nickname': 'B', 'status': 'new'},
        ]
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=targets)
        mock_db.create_broadcast_log = AsyncMock(return_value=5)
        mock_db.update_broadcast_log = AsyncMock()

        mock_client = MagicMock()
        mock_client.send_message = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.client = mock_client

        with patch('engines.broadcast_engine.database_v2', mock_db), \
             patch('engines.broadcast_engine.telegram_handler', mock_tg), \
             patch('engines.broadcast_engine._SEND_INTERVAL', 0):
            result = await send_broadcast(
                staff_id=1, template='Hello {name}!',
                segment_type='status', segment_value='new')

        assert result['total'] == 2
        assert result['sent'] == 2
        assert result['failed'] == 0
        assert result['log_id'] == 5

    @pytest.mark.asyncio
    async def test_broadcast_tracks_blocked(self):
        targets = [{'phone': '111', 'status': 'new'}]
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=targets)
        mock_db.create_broadcast_log = AsyncMock(return_value=1)
        mock_db.update_broadcast_log = AsyncMock()

        mock_client = MagicMock()
        mock_client.send_message = AsyncMock(side_effect=Exception('User blocked'))
        mock_tg = MagicMock()
        mock_tg.client = mock_client

        with patch('engines.broadcast_engine.database_v2', mock_db), \
             patch('engines.broadcast_engine.telegram_handler', mock_tg), \
             patch('engines.broadcast_engine._SEND_INTERVAL', 0):
            result = await send_broadcast(
                staff_id=1, template='Hi', segment_type='status', segment_value='new')

        assert result['blocked'] == 1
        assert result['sent'] == 0

    @pytest.mark.asyncio
    async def test_broadcast_tracks_failed(self):
        targets = [{'phone': '111', 'status': 'new'}]
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=targets)
        mock_db.create_broadcast_log = AsyncMock(return_value=1)
        mock_db.update_broadcast_log = AsyncMock()

        mock_client = MagicMock()
        mock_client.send_message = AsyncMock(side_effect=Exception('Network error'))
        mock_tg = MagicMock()
        mock_tg.client = mock_client

        with patch('engines.broadcast_engine.database_v2', mock_db), \
             patch('engines.broadcast_engine.telegram_handler', mock_tg), \
             patch('engines.broadcast_engine._SEND_INTERVAL', 0):
            result = await send_broadcast(
                staff_id=1, template='Hi', segment_type='status', segment_value='new')

        assert result['failed'] == 1

    @pytest.mark.asyncio
    async def test_broadcast_skips_empty_phone(self):
        targets = [{'phone': '', 'status': 'new'}, {'phone': '  ', 'status': 'new'}]
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=targets)
        mock_db.create_broadcast_log = AsyncMock(return_value=1)
        mock_db.update_broadcast_log = AsyncMock()

        mock_tg = MagicMock()
        mock_tg.client = MagicMock()
        mock_tg.client.send_message = AsyncMock()

        with patch('engines.broadcast_engine.database_v2', mock_db), \
             patch('engines.broadcast_engine.telegram_handler', mock_tg), \
             patch('engines.broadcast_engine._SEND_INTERVAL', 0):
            result = await send_broadcast(
                staff_id=1, template='Hi', segment_type='status', segment_value='new')

        assert result['failed'] == 2
        assert result['sent'] == 0

    @pytest.mark.asyncio
    async def test_progress_callback_called(self):
        targets = [{'phone': str(i), 'status': 'new', 'nickname': f'N{i}'} for i in range(10)]
        mock_db = MagicMock()
        mock_db.get_broadcast_targets = AsyncMock(return_value=targets)
        mock_db.create_broadcast_log = AsyncMock(return_value=1)
        mock_db.update_broadcast_log = AsyncMock()

        mock_client = MagicMock()
        mock_client.send_message = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.client = mock_client

        progress_calls = []

        async def progress_cb(current, total):
            progress_calls.append((current, total))

        with patch('engines.broadcast_engine.database_v2', mock_db), \
             patch('engines.broadcast_engine.telegram_handler', mock_tg), \
             patch('engines.broadcast_engine._SEND_INTERVAL', 0):
            await send_broadcast(
                staff_id=1, template='Hi {name}',
                segment_type='status', segment_value='new',
                progress_callback=progress_cb)

        # Called every 5 sends → at index 4 (5th) and 9 (10th)
        assert len(progress_calls) == 2
        assert progress_calls[0] == (5, 10)
        assert progress_calls[1] == (10, 10)


# ─── Segment/status helpers ───────────────────────────────────────────────────

class TestSegmentHelpers:
    def test_segment_types_non_empty(self):
        types = get_segment_types()
        assert len(types) >= 3
        keys = [t[0] for t in types]
        assert 'status' in keys
        assert 'team' in keys

    def test_status_values_non_empty(self):
        values = get_status_values()
        assert len(values) >= 5
        status_keys = [v[0] for v in values]
        assert 'new' in status_keys
        assert 'registered' in status_keys
        assert 'ghosted' in status_keys

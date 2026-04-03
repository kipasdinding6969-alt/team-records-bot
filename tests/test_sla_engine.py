"""Tests for engines/sla_engine.py — SLA breach detection and XP awards."""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta

from engines.sla_engine import (
    check_sla_breaches,
    award_sla_xp,
    check_perfect_sla_day,
    open_sla_for_new_client,
    close_sla_on_status_update,
    XP_SLA_MET,
    XP_PERFECT_DAY,
    _notified_events,
)


_P_DB = 'engines.sla_engine.database_v2'
_P_T = 'engines.sla_engine.t'


@pytest.fixture(autouse=True)
def clear_notified():
    """Clear notified set between tests."""
    _notified_events.clear()
    yield
    _notified_events.clear()


# ── check_sla_breaches ──────────────────────────────────────────────────────

class TestCheckSlaBreaches:

    @pytest.mark.asyncio
    async def test_no_open_events(self):
        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(return_value=[])
            await check_sla_breaches()
            # Should return without error

    @pytest.mark.asyncio
    async def test_no_telegram_handler_skips(self):
        """When telegram_handler is None, skip all notifications."""
        now = datetime.utcnow()
        events = [{
            'id': 1, 'event_type': 'first_response',
            'started_at': (now - timedelta(minutes=120)).isoformat(),
            'tg_chat_id': 100, 'staff_name': 'Test', 'client_phone': '+123',
        }]
        configs = [{'event_type': 'first_response', 'target_minutes': 60,
                     'warning_minutes': 30, 'critical_minutes': 90}]
        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.get_sla_config = AsyncMock(return_value=configs)
            await check_sla_breaches(telegram_handler=None)
            # No errors, just skipped

    @pytest.mark.asyncio
    async def test_warning_notification(self):
        now = datetime.utcnow()
        events = [{
            'id': 10, 'event_type': 'first_response',
            'started_at': (now - timedelta(minutes=35)).isoformat(),
            'tg_chat_id': 100, 'staff_name': 'Worker', 'client_phone': '+111',
        }]
        configs = [{'event_type': 'first_response', 'target_minutes': 60,
                     'warning_minutes': 30, 'critical_minutes': 90}]
        th = Mock()
        th.send_message = AsyncMock()
        with patch(_P_DB) as db, patch(_P_T, return_value='SLA warning'):
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.get_sla_config = AsyncMock(return_value=configs)
            await check_sla_breaches(telegram_handler=th)
            th.send_message.assert_awaited_once()
            # Check notified set
            assert (10, 'warn') in _notified_events

    @pytest.mark.asyncio
    async def test_critical_notification(self):
        now = datetime.utcnow()
        events = [{
            'id': 20, 'event_type': 'first_response',
            'started_at': (now - timedelta(minutes=100)).isoformat(),
            'tg_chat_id': 100, 'staff_name': 'Worker', 'client_phone': '+222',
        }]
        configs = [{'event_type': 'first_response', 'target_minutes': 60,
                     'warning_minutes': 30, 'critical_minutes': 90}]
        th = Mock()
        th.send_message = AsyncMock()
        with patch(_P_DB) as db, patch(_P_T, return_value='SLA critical'):
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.get_sla_config = AsyncMock(return_value=configs)
            await check_sla_breaches(telegram_handler=th, team_leader_chat_id=999)
            # Should notify both leader and staff
            assert th.send_message.await_count == 2
            assert (20, 'crit') in _notified_events

    @pytest.mark.asyncio
    async def test_duplicate_notification_suppressed(self):
        """Second call for same event should not re-notify."""
        now = datetime.utcnow()
        events = [{
            'id': 30, 'event_type': 'first_response',
            'started_at': (now - timedelta(minutes=35)).isoformat(),
            'tg_chat_id': 100, 'staff_name': 'W', 'client_phone': '+333',
        }]
        configs = [{'event_type': 'first_response', 'target_minutes': 60,
                     'warning_minutes': 30, 'critical_minutes': 90}]
        th = Mock()
        th.send_message = AsyncMock()
        with patch(_P_DB) as db, patch(_P_T, return_value='warn'):
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.get_sla_config = AsyncMock(return_value=configs)
            await check_sla_breaches(telegram_handler=th)
            await check_sla_breaches(telegram_handler=th)
            # Only one notification
            assert th.send_message.await_count == 1

    @pytest.mark.asyncio
    async def test_no_config_for_event_type(self):
        now = datetime.utcnow()
        events = [{
            'id': 40, 'event_type': 'unknown_type',
            'started_at': (now - timedelta(minutes=100)).isoformat(),
            'tg_chat_id': 100, 'staff_name': 'W', 'client_phone': '+444',
        }]
        configs = [{'event_type': 'first_response', 'target_minutes': 60,
                     'warning_minutes': 30, 'critical_minutes': 90}]
        th = Mock()
        th.send_message = AsyncMock()
        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.get_sla_config = AsyncMock(return_value=configs)
            await check_sla_breaches(telegram_handler=th)
            th.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bad_started_at_skipped(self):
        events = [{
            'id': 50, 'event_type': 'first_response',
            'started_at': 'not-a-date',
            'tg_chat_id': 100, 'staff_name': 'W', 'client_phone': '+555',
        }]
        configs = [{'event_type': 'first_response', 'target_minutes': 60,
                     'warning_minutes': 30, 'critical_minutes': 90}]
        th = Mock()
        th.send_message = AsyncMock()
        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.get_sla_config = AsyncMock(return_value=configs)
            await check_sla_breaches(telegram_handler=th)
            th.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_critical_no_leader_chat(self):
        """Critical without leader chat should still notify staff."""
        now = datetime.utcnow()
        events = [{
            'id': 60, 'event_type': 'first_response',
            'started_at': (now - timedelta(minutes=100)).isoformat(),
            'tg_chat_id': 100, 'staff_name': 'W', 'client_phone': '+666',
        }]
        configs = [{'event_type': 'first_response', 'target_minutes': 60,
                     'warning_minutes': 30, 'critical_minutes': 90}]
        th = Mock()
        th.send_message = AsyncMock()
        with patch(_P_DB) as db, patch(_P_T, return_value='critical'):
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.get_sla_config = AsyncMock(return_value=configs)
            await check_sla_breaches(telegram_handler=th, team_leader_chat_id=None)
            # Only staff notification (no leader)
            assert th.send_message.await_count == 1


# ── award_sla_xp ────────────────────────────────────────────────────────────

class TestAwardSlaXp:

    @pytest.mark.asyncio
    async def test_award_xp_when_met(self):
        with patch(_P_DB) as db:
            db.award_xp = AsyncMock()
            await award_sla_xp(1, met=True)
            db.award_xp.assert_awaited_once_with(1, 'sla_met', XP_SLA_MET)

    @pytest.mark.asyncio
    async def test_no_award_when_not_met(self):
        with patch(_P_DB) as db:
            db.award_xp = AsyncMock()
            await award_sla_xp(1, met=False)
            db.award_xp.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_award_xp_error_handled(self):
        with patch(_P_DB) as db:
            db.award_xp = AsyncMock(side_effect=Exception('db error'))
            # Should not raise
            await award_sla_xp(1, met=True)


# ── check_perfect_sla_day ───────────────────────────────────────────────────

class TestCheckPerfectSlaDay:

    @pytest.mark.asyncio
    async def test_perfect_day_awarded(self):
        mock_conn = AsyncMock()
        # First query: total=5, met=5
        mock_cursor1 = AsyncMock()
        mock_cursor1.fetchone = AsyncMock(return_value={'total': 5, 'met_count': 5})
        # Second query: not already awarded
        mock_cursor2 = AsyncMock()
        mock_cursor2.fetchone = AsyncMock(return_value=(0,))
        mock_conn.execute = AsyncMock(side_effect=[mock_cursor1, mock_cursor2])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch(_P_DB) as db:
            db.get_connection = Mock(return_value=mock_conn)
            db.award_xp = AsyncMock()
            await check_perfect_sla_day(staff_id=1)
            db.award_xp.assert_awaited_once_with(1, 'perfect_sla_day', XP_PERFECT_DAY)

    @pytest.mark.asyncio
    async def test_not_perfect_day(self):
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        # total=5, met=3 (not perfect)
        mock_cursor.fetchone = AsyncMock(return_value={'total': 5, 'met_count': 3})
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch(_P_DB) as db:
            db.get_connection = Mock(return_value=mock_conn)
            db.award_xp = AsyncMock()
            await check_perfect_sla_day(staff_id=1)
            db.award_xp.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_too_few_events(self):
        """Need at least 3 events for perfect day bonus."""
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value={'total': 2, 'met_count': 2})
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch(_P_DB) as db:
            db.get_connection = Mock(return_value=mock_conn)
            db.award_xp = AsyncMock()
            await check_perfect_sla_day(staff_id=1)
            db.award_xp.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_handled(self):
        with patch(_P_DB) as db:
            db.get_connection = Mock(side_effect=Exception('db fail'))
            # Should not raise
            await check_perfect_sla_day(staff_id=1)


# ── open_sla_for_new_client ─────────────────────────────────────────────────

class TestOpenSlaForNewClient:

    @pytest.mark.asyncio
    async def test_opens_sla_event(self):
        configs = [{'event_type': 'first_response', 'target_minutes': 60}]
        with patch(_P_DB) as db:
            db.get_sla_config = AsyncMock(return_value=configs)
            db.start_sla_event = AsyncMock()
            await open_sla_for_new_client(client_id=10, staff_id=1)
            db.start_sla_event.assert_awaited_once_with(10, 1, 'first_response', 60)

    @pytest.mark.asyncio
    async def test_no_config_does_nothing(self):
        with patch(_P_DB) as db:
            db.get_sla_config = AsyncMock(return_value=[])
            db.start_sla_event = AsyncMock()
            await open_sla_for_new_client(client_id=10, staff_id=1)
            db.start_sla_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_handled(self):
        with patch(_P_DB) as db:
            db.get_sla_config = AsyncMock(side_effect=Exception('fail'))
            # Should not raise
            await open_sla_for_new_client(client_id=10, staff_id=1)


# ── close_sla_on_status_update ───────────────────────────────────────────────

class TestCloseSlaOnStatusUpdate:

    @pytest.mark.asyncio
    async def test_closes_matching_event(self):
        events = [{'id': 5, 'client_id': 10, 'staff_id': 1}]
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value={'met': 1})
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.complete_sla_event = AsyncMock(return_value=True)
            db.get_connection = Mock(return_value=mock_conn)
            db.award_xp = AsyncMock()
            await close_sla_on_status_update(client_id=10, staff_id=1, new_status='registered')
            db.complete_sla_event.assert_awaited_once_with(5)
            db.award_xp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_matching_event(self):
        events = [{'id': 5, 'client_id': 99, 'staff_id': 2}]
        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.complete_sla_event = AsyncMock()
            await close_sla_on_status_update(client_id=10, staff_id=1, new_status='registered')
            db.complete_sla_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_handled(self):
        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(side_effect=Exception('fail'))
            # Should not raise
            await close_sla_on_status_update(client_id=10, staff_id=1, new_status='registered')

    @pytest.mark.asyncio
    async def test_complete_returns_false(self):
        """If complete_sla_event returns False, skip XP."""
        events = [{'id': 5, 'client_id': 10, 'staff_id': 1}]
        with patch(_P_DB) as db:
            db.get_open_sla_events = AsyncMock(return_value=events)
            db.complete_sla_event = AsyncMock(return_value=False)
            db.award_xp = AsyncMock()
            await close_sla_on_status_update(client_id=10, staff_id=1, new_status='registered')
            db.award_xp.assert_not_awaited()

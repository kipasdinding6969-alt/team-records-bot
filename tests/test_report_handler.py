"""Tests for handlers_v2/report_handler.py — /report, /funnel, period parsing, bar chart."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from handlers_v2.report_handler import (
    handle_report, handle_funnel,
    _week_range, _month_range, _last_week_range, _bar, _parse_period,
    format_funnel_text,
    REPORT_COMMANDS,
)
from models_v2 import Staff, StaffRole


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _staff(sid=1, role=StaffRole.MANAGER, name='Manager', uid=1001,
           chat_id=2001, lang='zh', team='阿俊'):
    return Staff(tg_user_id=uid, tg_chat_id=chat_id, display_name=name,
                 id=sid, role=role, language=lang, team=team)


def _task(user_id=1001, chat_id=2001, args='', callback_data=''):
    return {
        'user_id': user_id, 'chat_id': chat_id, 'args': args,
        'callback_data': callback_data,
    }


def _mock_report_db():
    mock_db = MagicMock()
    mock_db.get_conversion_rates = AsyncMock(return_value={
        'total': 100, 'contacted': 80, 'replied': 60,
        'registered': 40, 'deposited': 10,
        'contact_rate': 80, 'reply_rate': 75, 'register_rate': 67, 'deposit_rate': 25,
    })
    mock_db.get_deposit_total = AsyncMock(return_value=5000.0)
    mock_db.get_staff_rankings = AsyncMock(return_value=[
        {'display_name': '阿YIM', 'count': 5, 'total_amount': 2500.0},
    ])
    mock_db.get_stale_clients_analytics = AsyncMock(return_value=[])
    mock_db.get_commission_summary = AsyncMock(return_value={
        'total_amount': 100, 'pending_amount': 50, 'approved_amount': 50, 'total_count': 3,
    })
    mock_db.get_period_comparison = AsyncMock(return_value={
        'total': {'current': 100, 'previous': 80, 'delta': 20, 'pct_change': 25.0},
        'contacted': {'current': 80, 'previous': 60, 'delta': 20, 'pct_change': 33.3},
        'replied': {'current': 60, 'previous': 50, 'delta': 10, 'pct_change': 20.0},
        'registered': {'current': 40, 'previous': 30, 'delta': 10, 'pct_change': 33.3},
        'deposited': {'current': 10, 'previous': 5, 'delta': 5, 'pct_change': 100.0},
    })
    return mock_db


# ─── Tests: Pure functions ─────────────────────────────────────────────────────

class TestWeekRange:
    def test_returns_monday_to_sunday(self):
        dt = datetime(2026, 3, 30)  # Monday
        start, end = _week_range(dt)
        assert start == '2026-03-30'
        assert end == '2026-04-05'

    def test_defaults_to_now(self):
        start, end = _week_range()
        assert start is not None
        assert end is not None


class TestMonthRange:
    def test_march(self):
        dt = datetime(2026, 3, 15)
        start, end = _month_range(dt)
        assert start == '2026-03-01'
        assert end == '2026-03-31'

    def test_february_non_leap(self):
        dt = datetime(2025, 2, 10)
        start, end = _month_range(dt)
        assert end == '2025-02-28'

    def test_december(self):
        dt = datetime(2026, 12, 1)
        start, end = _month_range(dt)
        assert start == '2026-12-01'
        assert end == '2026-12-31'


class TestLastWeekRange:
    def test_returns_7_day_range(self):
        start, end = _last_week_range()
        from datetime import date as d
        s = d.fromisoformat(start)
        e = d.fromisoformat(end)
        assert (e - s).days == 6


class TestBar:
    def test_full_bar(self):
        result = _bar(100, 100, width=20)
        assert len(result) == 20

    def test_half_bar(self):
        result = _bar(50, 100, width=20)
        assert len(result) == 10

    def test_zero_max(self):
        result = _bar(0, 0, width=20)
        assert result == ''

    def test_minimum_one_char(self):
        result = _bar(1, 1000, width=20)
        assert len(result) >= 1


class TestParsePeriod:
    def test_week_format(self):
        start, end = _parse_period('2026-W13')
        from datetime import date as d
        s = d.fromisoformat(start)
        e = d.fromisoformat(end)
        assert (e - s).days == 6

    def test_month_format(self):
        start, end = _parse_period('2026-03')
        assert start == '2026-03-01'
        assert end == '2026-03-31'

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            _parse_period('invalid')

    def test_invalid_format_short(self):
        with pytest.raises(ValueError):
            _parse_period('2026')


class TestFormatFunnelText:
    def test_output_contains_stages(self):
        rates = {'total': 100, 'contacted': 80, 'replied': 60, 'registered': 40, 'deposited': 10}
        text = format_funnel_text(rates, '2026-03-01', '2026-03-31')
        assert 'New' in text
        assert 'Contacted' in text
        assert 'Registered' in text
        assert 'Deposited' in text
        assert '█' in text

    def test_all_zeros(self):
        rates = {'total': 0, 'contacted': 0, 'replied': 0, 'registered': 0, 'deposited': 0}
        text = format_funnel_text(rates, '2026-01-01', '2026-01-07')
        assert '0%' in text


# ─── Tests: Handlers (with mocks) ─────────────────────────────────────────────

def _patch_handler(staff_obj, mock_db=None, mock_tg=None):
    """Return a list of patch context managers for handlers using @require_permission."""
    if mock_tg is None:
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
    if mock_db is None:
        mock_db = MagicMock()
    return [
        patch('handlers_v2.report_handler.database_v2', mock_db),
        patch('handlers_v2.report_handler.telegram_handler', mock_tg),
        patch('handlers_v2.report_handler._get_staff', AsyncMock(return_value=staff_obj)),
        # Also patch the decorator's paths so require_permission works
        patch('handlers_v2.get_staff', AsyncMock(return_value=staff_obj)),
        patch('handlers_v2.database_v2', mock_db),
        patch('telegram_handler.telegram_handler', mock_tg),
    ]


class TestHandleReport:
    @pytest.mark.asyncio
    async def test_non_manager_denied(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_tg=mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            await handle_report(_task())

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_weekly_report_default(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = _mock_report_db()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_db, mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch('handlers_v2.report_handler.resolve_team_scope', return_value='阿俊'):
            await handle_report(_task())

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Report' in msg
        assert 'Pipeline' in msg

    @pytest.mark.asyncio
    async def test_monthly_report(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = _mock_report_db()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_db, mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch('handlers_v2.report_handler.resolve_team_scope', return_value=None):
            await handle_report(_task(args='monthly'))

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Report' in msg

    @pytest.mark.asyncio
    async def test_compare_report(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = _mock_report_db()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_db, mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch('handlers_v2.report_handler.resolve_team_scope', return_value=None):
            await handle_report(_task(args='compare 2026-W12 2026-W13'))

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Comparison' in msg
        assert 'vs' in msg

    @pytest.mark.asyncio
    async def test_compare_invalid_period(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_tg=mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch('handlers_v2.report_handler.resolve_team_scope', return_value=None):
            await handle_report(_task(args='compare bad1 bad2'))

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Invalid' in msg


class TestHandleFunnel:
    @pytest.mark.asyncio
    async def test_funnel_default_period(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = _mock_report_db()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_db, mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch('handlers_v2.report_handler.resolve_team_scope', return_value=None):
            await handle_funnel(_task())

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Funnel' in msg
        assert '█' in msg

    @pytest.mark.asyncio
    async def test_funnel_with_period(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = _mock_report_db()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_db, mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch('handlers_v2.report_handler.resolve_team_scope', return_value=None):
            await handle_funnel(_task(args='2026-W13'))

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Funnel' in msg

    @pytest.mark.asyncio
    async def test_funnel_invalid_period(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        patches = _patch_handler(staff, mock_tg=mock_tg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch('handlers_v2.report_handler.resolve_team_scope', return_value=None):
            await handle_funnel(_task(args='bad'))

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Invalid' in msg


class TestRegistryExports:
    def test_commands_registered(self):
        assert 'report' in REPORT_COMMANDS
        assert 'funnel' in REPORT_COMMANDS

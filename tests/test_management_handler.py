"""Tests for handlers_v2/management.py — /dashboard, /team, /target, /export, /sync, /setteam, /teams."""
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from handlers_v2.management import (
    handle_dashboard, handle_team_stats, handle_target,
    handle_export, handle_sync, handle_setteam, handle_teams,
    MANAGEMENT_COMMANDS,
)
from models_v2 import DailyStat, PeriodType, Staff, StaffRole, TeamTarget


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _staff(sid=1, role=StaffRole.MANAGER, name='Manager', uid=1001,
           chat_id=2001, lang='zh', team='阿俊'):
    return Staff(tg_user_id=uid, tg_chat_id=chat_id, display_name=name,
                 id=sid, role=role, language=lang, team=team)


def _task(user_id=1001, chat_id=2001, args=''):
    return {'user_id': user_id, 'chat_id': chat_id, 'args': args}


def _stat(staff_id=1, new_leads=10, registered=5, new_orders=2, total_deposit=500.0):
    return DailyStat(staff_id=staff_id, stat_date=date.today(),
                     new_leads=new_leads, registered=registered,
                     new_orders=new_orders, total_deposit=total_deposit)


# ─── Tests ─────────────────────────────────────────────────────────────────────

class TestHandleDashboard:
    @pytest.mark.asyncio
    async def test_unregistered_user(self):
        mock_db = MagicMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=None)):
            await handle_dashboard(_task())

        mock_tg.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_manager_denied(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)), \
             patch('engines.policy_engine.check_permission', return_value=True):
            await handle_dashboard(_task())

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_manager_sees_dashboard(self):
        staff = _staff(role=StaffRole.MANAGER)
        member = _staff(sid=2, name='FD', role=StaffRole.FRONTDESK)
        stats = [_stat(staff_id=1), _stat(staff_id=2, new_leads=20)]

        mock_db = MagicMock()
        mock_db.recalculate_all_today_stats = AsyncMock()
        mock_db.get_team_daily_stats = AsyncMock(return_value=stats)
        mock_db.get_all_staff = AsyncMock(return_value=[staff, member])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_dashboard(_task())

        msg = mock_tg.send_message.call_args[0][1]
        assert '30' in msg or '20' in msg  # new_leads total


class TestHandleTeamStats:
    @pytest.mark.asyncio
    async def test_no_team_name(self):
        staff = _staff(team=None)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_team_stats(_task(args=''))

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_team_not_found(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_all_staff = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_team_stats(_task(args='NonExistent'))

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_team_with_members(self):
        staff = _staff(role=StaffRole.MANAGER)
        member = _staff(sid=2, name='FD1', team='阿俊')

        mock_db = MagicMock()
        mock_db.get_all_staff = AsyncMock(return_value=[staff, member])
        mock_db.get_daily_stats = AsyncMock(return_value=_stat())
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_team_stats(_task(args='阿俊'))

        msg = mock_tg.send_message.call_args[0][1]
        assert '阿俊' in msg


class TestHandleTarget:
    @pytest.mark.asyncio
    async def test_view_existing_target(self):
        staff = _staff()
        target = TeamTarget(team='阿俊', period_type=PeriodType.WEEKLY,
                            period_start=date.today(), period_end=date.today() + timedelta(days=6),
                            target_leads=50, target_registers=20, target_orders=10)

        mock_db = MagicMock()
        mock_db.get_team_target = AsyncMock(return_value=target)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_target(_task(args=''))

        msg = mock_tg.send_message.call_args[0][1]
        assert '50' in msg or '20' in msg

    @pytest.mark.asyncio
    async def test_no_target_set(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_team_target = AsyncMock(return_value=None)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_target(_task(args=''))

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_set_target(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = MagicMock()
        mock_db.upsert_team_target = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_target(_task(args='set 阿俊 100 50 20'))

        mock_db.upsert_team_target.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_target_bad_numbers(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_target(_task(args='set 阿俊 abc def ghi'))

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_set_target_non_manager(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_target(_task(args='set 阿俊 100 50 20'))

        mock_tg.send_message.assert_awaited()


class TestHandleExport:
    @pytest.mark.asyncio
    async def test_export_empty(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = MagicMock()
        mock_db.export_clients_csv = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_export(_task())

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_export_with_data(self):
        staff = _staff(role=StaffRole.MANAGER)
        rows = [{'phone': '111', 'status': 'new', 'source': 'test'}]
        mock_db = MagicMock()
        mock_db.export_clients_csv = AsyncMock(return_value=rows)
        mock_tg = MagicMock()
        mock_tg.send_file = AsyncMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_export(_task())

        mock_tg.send_file.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_export_file_send_fails_sends_preview(self):
        staff = _staff(role=StaffRole.MANAGER)
        rows = [{'phone': '111', 'status': 'new', 'source': 'test'}]
        mock_db = MagicMock()
        mock_db.export_clients_csv = AsyncMock(return_value=rows)
        mock_tg = MagicMock()
        mock_tg.send_file = AsyncMock(side_effect=Exception('send failed'))
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_export(_task())

        # Falls back to text preview
        mock_tg.send_message.assert_awaited()


class TestHandleSync:
    @pytest.mark.asyncio
    async def test_non_manager_denied(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_sync(_task())

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_sync_success(self):
        staff = _staff(role=StaffRole.ADMIN)
        mock_db = MagicMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        mock_sync_mod = MagicMock()
        mock_sync_mod.sheet_sync_v2 = MagicMock()
        mock_sync_mod.sheet_sync_v2.full_sync = AsyncMock(return_value={
            'total_imported': 10, 'total_exported': 5})

        mock_dash_mod = MagicMock()
        mock_dash_mod.dashboard_sheets = MagicMock()
        mock_dash_mod.dashboard_sheets.refresh_all_tabs = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)), \
             patch.dict('sys.modules', {
                 'engines.sheet_sync_v2': mock_sync_mod,
                 'engines.dashboard_sheets': mock_dash_mod}):
            await handle_sync(_task())

        # At least 2 messages: "sync started" + "sync complete"
        assert mock_tg.send_message.await_count >= 2


class TestHandleSetteam:
    @pytest.mark.asyncio
    async def test_missing_args(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_setteam(_task(args=''))

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_only_username_no_team(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_setteam(_task(args='@user'))

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = MagicMock()
        mock_db.get_staff_by_username = AsyncMock(return_value=None)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_setteam(_task(args='@nobody 阿俊'))

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_setteam_success(self):
        staff = _staff(role=StaffRole.MANAGER)
        target = _staff(sid=2, name='Target')
        mock_db = MagicMock()
        mock_db.get_staff_by_username = AsyncMock(return_value=target)
        mock_db.set_staff_team = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_setteam(_task(args='@target 何军'))

        mock_db.set_staff_team.assert_awaited_once()


class TestHandleTeams:
    @pytest.mark.asyncio
    async def test_no_teams(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_all_teams = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_teams(_task())

        mock_tg.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_teams_with_members(self):
        staff = _staff()
        member = _staff(sid=2, name='FD1', team='阿俊')
        mock_db = MagicMock()
        mock_db.get_all_teams = AsyncMock(return_value=['阿俊'])
        mock_db.get_staff_by_team = AsyncMock(return_value=[member])
        mock_db.get_daily_stats = AsyncMock(return_value=_stat(staff_id=2))
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.management.database_v2', mock_db), \
             patch('handlers_v2.management.telegram_handler', mock_tg), \
             patch('handlers_v2.management._get_staff', AsyncMock(return_value=staff)):
            await handle_teams(_task())

        msg = mock_tg.send_message.call_args[0][1]
        assert '阿俊' in msg


class TestRegistryExports:
    def test_all_commands_registered(self):
        assert 'dashboard' in MANAGEMENT_COMMANDS
        assert 'team' in MANAGEMENT_COMMANDS
        assert 'target' in MANAGEMENT_COMMANDS
        assert 'export' in MANAGEMENT_COMMANDS
        assert 'sync' in MANAGEMENT_COMMANDS
        assert 'setteam' in MANAGEMENT_COMMANDS
        assert 'teams' in MANAGEMENT_COMMANDS

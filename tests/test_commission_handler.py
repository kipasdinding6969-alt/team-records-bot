"""Tests for handlers_v2/commission_handler.py — commission commands, callbacks, auto-calculation."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from handlers_v2.commission_handler import (
    handle_commission, handle_commission_callback,
    _show_my_commission, _show_team_commission, _show_rules, _set_rule,
    _approve_commissions, _commission_buttons,
    auto_calculate_deposit_commission, auto_calculate_registration_commission,
    COMMISSION_COMMANDS, COMMISSION_CALLBACKS,
)
from models_v2 import Client, ClientStatus, Commission, CommissionRule, Staff, StaffRole


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _staff(sid=1, role=StaffRole.FRONTDESK, name='阿YIM', uid=1001,
           chat_id=2001, lang='zh', team='阿俊'):
    return Staff(tg_user_id=uid, tg_chat_id=chat_id, display_name=name,
                 id=sid, role=role, language=lang, team=team)


def _commission(cid=1, staff_id=1, trigger='deposit', amount=50.0,
                status='pending', client_id=1):
    return Commission(staff_id=staff_id, trigger_type=trigger, amount=amount,
                      id=cid, client_id=client_id, status=status, period='2026-W13')


def _commission_summary(total=100.0, pending=60.0, approved=30.0, paid=10.0, count=5):
    return {
        'total_amount': total, 'pending_amount': pending,
        'approved_amount': approved, 'paid_amount': paid,
        'total_count': count,
    }


def _task(user_id=1001, chat_id=2001, args='', callback_data=''):
    return {
        'user_id': user_id, 'chat_id': chat_id, 'args': args,
        'callback_data': callback_data,
    }


# ─── Tests ─────────────────────────────────────────────────────────────────────

class TestShowMyCommission:
    @pytest.mark.asyncio
    async def test_shows_summary(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db._current_week_period = Mock(return_value='2026-W13')
        mock_db.get_commission_summary = AsyncMock(return_value=_commission_summary())
        mock_db.get_commissions = AsyncMock(return_value=[_commission()])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _show_my_commission(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert '$100.00' in msg
        assert 'Pending' in msg
        assert 'Approved' in msg

    @pytest.mark.asyncio
    async def test_shows_with_custom_period(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_commission_summary = AsyncMock(return_value=_commission_summary(total=0, count=0))
        mock_db.get_commissions = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _show_my_commission(2001, staff, '2026-03')

        msg = mock_tg.send_message.call_args[0][1]
        assert '2026-03' in msg

    @pytest.mark.asyncio
    async def test_shows_breakdown_items(self):
        staff = _staff()
        commissions = [
            _commission(trigger='deposit', amount=30, status='pending'),
            _commission(trigger='first_deposit', amount=50, status='approved'),
        ]
        mock_db = MagicMock()
        mock_db._current_week_period = Mock(return_value='2026-W13')
        mock_db.get_commission_summary = AsyncMock(return_value=_commission_summary())
        mock_db.get_commissions = AsyncMock(return_value=commissions)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _show_my_commission(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'deposit' in msg
        assert 'Breakdown' in msg


class TestShowTeamCommission:
    @pytest.mark.asyncio
    async def test_non_manager_denied(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _show_team_commission(2001, staff)

        mock_tg.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_manager_sees_team_breakdown(self):
        staff = _staff(role=StaffRole.MANAGER)
        member = _staff(sid=2, name='Member')

        mock_db = MagicMock()
        mock_db._current_week_period = Mock(return_value='2026-W13')
        mock_db.get_commission_summary = AsyncMock(return_value=_commission_summary())
        mock_db.get_all_staff = AsyncMock(return_value=[staff, member])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg), \
             patch('handlers_v2.commission_handler.resolve_team_scope', return_value='阿俊'):
            await _show_team_commission(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Team Commission' in msg


class TestShowRules:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _show_rules(2001, staff)

        mock_tg.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_sees_rules(self):
        staff = _staff(role=StaffRole.ADMIN)
        rule = CommissionRule(status_trigger='deposit', rate_type='percentage',
                              rate_value=0.05, id=1)
        mock_db = MagicMock()
        mock_db.get_active_commission_rules = AsyncMock(return_value=[rule])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _show_rules(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Commission Rules' in msg
        assert '5.0%' in msg

    @pytest.mark.asyncio
    async def test_no_rules(self):
        staff = _staff(role=StaffRole.ADMIN)
        mock_db = MagicMock()
        mock_db.get_active_commission_rules = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _show_rules(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'No active' in msg


class TestSetRule:
    @pytest.mark.asyncio
    async def test_invalid_trigger(self):
        staff = _staff(role=StaffRole.ADMIN)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _set_rule(2001, staff, 'invalid', 'percentage', '0.1')

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Invalid trigger' in msg

    @pytest.mark.asyncio
    async def test_invalid_rate_type(self):
        staff = _staff(role=StaffRole.ADMIN)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _set_rule(2001, staff, 'deposit', 'invalid', '0.1')

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Invalid rate type' in msg

    @pytest.mark.asyncio
    async def test_negative_rate(self):
        staff = _staff(role=StaffRole.ADMIN)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _set_rule(2001, staff, 'deposit', 'fixed', '-5')

        msg = mock_tg.send_message.call_args[0][1]
        assert 'negative' in msg.lower()

    @pytest.mark.asyncio
    async def test_percentage_out_of_range(self):
        staff = _staff(role=StaffRole.ADMIN)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _set_rule(2001, staff, 'deposit', 'percentage', '1.5')

        msg = mock_tg.send_message.call_args[0][1]
        assert 'between' in msg.lower()

    @pytest.mark.asyncio
    async def test_valid_rule_set(self):
        staff = _staff(role=StaffRole.ADMIN)
        mock_db = MagicMock()
        mock_db.set_commission_rule = AsyncMock(return_value=1)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _set_rule(2001, staff, 'deposit', 'percentage', '0.1')

        msg = mock_tg.send_message.call_args[0][1]
        assert '✅' in msg

    @pytest.mark.asyncio
    async def test_non_admin_denied(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _set_rule(2001, staff, 'deposit', 'fixed', '50')

        mock_tg.send_message.assert_awaited_once()


class TestApproveCommissions:
    @pytest.mark.asyncio
    async def test_non_manager_denied(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _approve_commissions(2001, staff)

        mock_tg.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_success(self):
        staff = _staff(role=StaffRole.MANAGER)
        mock_db = MagicMock()
        mock_db._current_week_period = Mock(return_value='2026-W13')
        mock_db.approve_commissions = AsyncMock(return_value=3)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db), \
             patch('handlers_v2.commission_handler.telegram_handler', mock_tg):
            await _approve_commissions(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert '3' in msg
        assert '✅' in msg


class TestCommissionButtons:
    def test_non_manager_buttons(self):
        buttons = _commission_buttons(1, '2026-W13', is_manager=False)
        all_text = str(buttons)
        assert 'Approve' not in all_text
        assert 'Breakdown' in all_text

    def test_manager_buttons_have_approve(self):
        buttons = _commission_buttons(1, '2026-W13', is_manager=True)
        all_text = str(buttons)
        assert 'Approve' in all_text
        assert 'Last Week' in all_text
        assert 'This Month' in all_text


class TestAutoCalculateDeposit:
    @pytest.mark.asyncio
    async def test_standard_deposit(self):
        mock_db = MagicMock()
        mock_db.is_first_deposit = AsyncMock(return_value=False)
        mock_db.calculate_commission = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db):
            await auto_calculate_deposit_commission(
                staff_id=1, client_id=10, deposit_id=5, amount=500.0, team='阿俊')

        # Only standard deposit, not first_deposit
        assert mock_db.calculate_commission.await_count == 1
        call_kwargs = mock_db.calculate_commission.call_args[1]
        assert call_kwargs['trigger_type'] == 'deposit'

    @pytest.mark.asyncio
    async def test_first_deposit_bonus(self):
        mock_db = MagicMock()
        mock_db.is_first_deposit = AsyncMock(return_value=True)
        mock_db.calculate_commission = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db):
            await auto_calculate_deposit_commission(
                staff_id=1, client_id=10, deposit_id=5, amount=500.0)

        assert mock_db.calculate_commission.await_count == 2


class TestAutoCalculateRegistration:
    @pytest.mark.asyncio
    async def test_non_registered_status_skipped(self):
        mock_db = MagicMock()
        mock_db.is_first_registration = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db):
            await auto_calculate_registration_commission(client_id=1, new_status='contacted')

        mock_db.is_first_registration.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_first_registration_skipped(self):
        mock_db = MagicMock()
        mock_db.is_first_registration = AsyncMock(return_value=False)

        with patch('handlers_v2.commission_handler.database_v2', mock_db):
            await auto_calculate_registration_commission(client_id=1, new_status='registered')

        mock_db.is_first_registration.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_first_registration_creates_commission(self):
        client = Client(frontdesk_id=1, phone='123', source='test', id=10)
        staff = _staff()

        mock_db = MagicMock()
        mock_db.is_first_registration = AsyncMock(return_value=True)
        mock_db.get_client_by_id = AsyncMock(return_value=client)
        mock_db.get_staff_by_id = AsyncMock(return_value=staff)
        mock_db.calculate_commission = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db):
            await auto_calculate_registration_commission(client_id=10, new_status='registered')

        mock_db.calculate_commission.assert_awaited_once()
        call_kwargs = mock_db.calculate_commission.call_args[1]
        assert call_kwargs['trigger_type'] == 'registration'

    @pytest.mark.asyncio
    async def test_client_not_found(self):
        mock_db = MagicMock()
        mock_db.is_first_registration = AsyncMock(return_value=True)
        mock_db.get_client_by_id = AsyncMock(return_value=None)
        mock_db.calculate_commission = AsyncMock()

        with patch('handlers_v2.commission_handler.database_v2', mock_db):
            await auto_calculate_registration_commission(client_id=999, new_status='registered')

        mock_db.calculate_commission.assert_not_awaited()


class TestRegistryExports:
    def test_commands_registered(self):
        assert 'commission' in COMMISSION_COMMANDS

    def test_callbacks_registered(self):
        assert len(COMMISSION_CALLBACKS) >= 1

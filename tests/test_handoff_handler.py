"""Tests for handlers_v2/handoff_handler.py — shift handoff creation, accept, decline, list."""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from handlers_v2.handoff_handler import (
    handle_handoff, handle_handoff_callback,
    _create_handoff, _accept_handoff, _list_handoffs,
    HANDOFF_COMMANDS, HANDOFF_CALLBACKS,
)
from models_v2 import Client, ClientStatus, ShiftHandoff, Staff, StaffRole


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _staff(sid=1, chat_id=2001, name='阿YIM', role=StaffRole.FRONTDESK,
           team='阿俊', uid=1001, lang='zh'):
    return Staff(tg_user_id=uid, tg_chat_id=chat_id, display_name=name,
                 id=sid, role=role, team=team, language=lang)


def _client(cid=1, phone='12345', status=ClientStatus.CONTACTED, nickname=None):
    c = Client(frontdesk_id=1, phone=phone, source='test', id=cid, status=status,
               nickname=nickname, updated_at=datetime.utcnow())
    c.status_note = None
    return c


def _handoff(hid=1, from_id=1, to_id=2, status='pending', client_ids=None):
    return ShiftHandoff(
        from_staff_id=from_id, id=hid, to_staff_id=to_id, status=status,
        client_ids=json.dumps(client_ids or [1, 2]),
        team='阿俊', created_at=datetime.utcnow(),
    )


def _task(user_id=1001, chat_id=2001, args='', callback_data=''):
    return {
        'user_id': user_id, 'chat_id': chat_id, 'args': args,
        'callback_data': callback_data,
    }


def _patch_all(mock_db, mock_tg, staff_obj):
    """Return a context manager that patches db, tg, and get_staff."""
    return (
        patch('handlers_v2.handoff_handler.database_v2', mock_db),
        patch('handlers_v2.handoff_handler.telegram_handler', mock_tg),
        patch('handlers_v2.handoff_handler._get_staff', new_callable=lambda: lambda: AsyncMock(return_value=staff_obj)),
    )


# ─── Tests ─────────────────────────────────────────────────────────────────────

class TestCreateHandoff:
    @pytest.mark.asyncio
    async def test_no_active_clients(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_active_clients_for_staff = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _create_handoff(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'No active clients' in msg

    @pytest.mark.asyncio
    async def test_creates_handoff_with_target(self):
        staff = _staff(sid=1)
        target = _staff(sid=2, name='Target', uid=2000)
        clients = [_client(cid=1), _client(cid=2)]

        mock_db = MagicMock()
        mock_db.get_active_clients_for_staff = AsyncMock(return_value=clients)
        mock_db.get_all_staff = AsyncMock(return_value=[staff, target])
        mock_db.create_handoff = AsyncMock(return_value=99)
        mock_db.get_staff_by_id = AsyncMock(return_value=target)
        mock_db.log_event = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _create_handoff(2001, staff, 'Target')

        mock_db.create_handoff.assert_awaited_once()
        # Should send to both target and creator
        assert mock_tg.send_message.await_count >= 2

    @pytest.mark.asyncio
    async def test_creates_handoff_without_target(self):
        staff = _staff()
        clients = [_client()]

        mock_db = MagicMock()
        mock_db.get_active_clients_for_staff = AsyncMock(return_value=clients)
        mock_db.create_handoff = AsyncMock(return_value=1)
        mock_db.log_event = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _create_handoff(2001, staff, None)

        mock_db.create_handoff.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_target_not_found_fallback(self):
        staff = _staff()
        clients = [_client()]

        mock_db = MagicMock()
        mock_db.get_active_clients_for_staff = AsyncMock(return_value=clients)
        mock_db.get_all_staff = AsyncMock(return_value=[staff])
        mock_db.create_handoff = AsyncMock(return_value=1)
        mock_db.log_event = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _create_handoff(2001, staff, 'NonExistent')

        # Still creates handoff
        mock_db.create_handoff.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_more_than_10_clients_truncated(self):
        staff = _staff()
        clients = [_client(cid=i) for i in range(15)]

        mock_db = MagicMock()
        mock_db.get_active_clients_for_staff = AsyncMock(return_value=clients)
        mock_db.create_handoff = AsyncMock(return_value=1)
        mock_db.log_event = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _create_handoff(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert '5 more' in msg


class TestAcceptHandoff:
    @pytest.mark.asyncio
    async def test_accept_success(self):
        staff = _staff(sid=2, name='Acceptor')
        handoff = _handoff(hid=10, from_id=1, to_id=2)
        from_staff = _staff(sid=1)

        mock_db = MagicMock()
        mock_db.get_handoff_by_id = AsyncMock(return_value=handoff)
        mock_db.accept_handoff = AsyncMock(return_value=True)
        mock_db.get_staff_by_id = AsyncMock(return_value=from_staff)
        mock_db.log_event = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _accept_handoff(2001, staff, 10)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'accepted' in msg.lower() or '✅' in msg

    @pytest.mark.asyncio
    async def test_accept_not_found(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_handoff_by_id = AsyncMock(return_value=None)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _accept_handoff(2001, staff, 999)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'not found' in msg.lower()

    @pytest.mark.asyncio
    async def test_accept_already_processed(self):
        staff = _staff()
        handoff = _handoff(hid=10, status='accepted')
        mock_db = MagicMock()
        mock_db.get_handoff_by_id = AsyncMock(return_value=handoff)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _accept_handoff(2001, staff, 10)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'already' in msg.lower()

    @pytest.mark.asyncio
    async def test_accept_failure(self):
        staff = _staff()
        handoff = _handoff(hid=10)
        mock_db = MagicMock()
        mock_db.get_handoff_by_id = AsyncMock(return_value=handoff)
        mock_db.accept_handoff = AsyncMock(return_value=False)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _accept_handoff(2001, staff, 10)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'Failed' in msg


class TestListHandoffs:
    @pytest.mark.asyncio
    async def test_no_pending_handoffs(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_pending_handoffs = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _list_handoffs(2001, staff)

        msg = mock_tg.send_message.call_args[0][1]
        assert 'No pending' in msg

    @pytest.mark.asyncio
    async def test_list_shows_handoffs(self):
        staff = _staff(sid=2)
        h1 = _handoff(hid=1, from_id=1, to_id=2)
        from_staff = _staff(sid=1, name='Creator')

        mock_db = MagicMock()
        mock_db.get_pending_handoffs = AsyncMock(return_value=[h1])
        mock_db.get_staff_by_id = AsyncMock(return_value=from_staff)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg):
            await _list_handoffs(2001, staff)

        mock_tg.send_message.assert_awaited_once()
        call_kwargs = mock_tg.send_message.call_args[1]
        assert 'reply_markup' in call_kwargs


class TestHandoffCallback:
    @pytest.mark.asyncio
    async def test_accept_callback(self):
        staff = _staff()
        handoff = _handoff(hid=5)
        from_staff = _staff(sid=1, name='From')

        mock_db = MagicMock()
        mock_db.get_handoff_by_id = AsyncMock(return_value=handoff)
        mock_db.accept_handoff = AsyncMock(return_value=True)
        mock_db.get_staff_by_id = AsyncMock(return_value=from_staff)
        mock_db.log_event = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg), \
             patch('handlers_v2.handoff_handler._get_staff', AsyncMock(return_value=staff)):
            await handle_handoff_callback(
                _task(callback_data='handoff:accept:5'))

    @pytest.mark.asyncio
    async def test_decline_callback_authorized(self):
        staff = _staff(sid=1)  # from_staff_id matches
        handoff = _handoff(hid=5, from_id=1, to_id=2)

        mock_db = MagicMock()
        mock_db.get_handoff_by_id = AsyncMock(return_value=handoff)
        mock_db.decline_handoff = AsyncMock(return_value=True)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg), \
             patch('handlers_v2.handoff_handler._get_staff', AsyncMock(return_value=staff)):
            await handle_handoff_callback(
                _task(callback_data='handoff:decline:5'))

        msg = mock_tg.send_message.call_args[0][1]
        assert 'declined' in msg.lower() or '❌' in msg

    @pytest.mark.asyncio
    async def test_decline_callback_unauthorized(self):
        staff = _staff(sid=99, role=StaffRole.FRONTDESK)
        handoff = _handoff(hid=5, from_id=1, to_id=2)

        mock_db = MagicMock()
        mock_db.get_handoff_by_id = AsyncMock(return_value=handoff)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.database_v2', mock_db), \
             patch('handlers_v2.handoff_handler.telegram_handler', mock_tg), \
             patch('handlers_v2.handoff_handler._get_staff', AsyncMock(return_value=staff)):
            await handle_handoff_callback(
                _task(callback_data='handoff:decline:5'))

    @pytest.mark.asyncio
    async def test_callback_invalid_format(self):
        staff = _staff()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.telegram_handler', mock_tg), \
             patch('handlers_v2.handoff_handler._get_staff', AsyncMock(return_value=staff)):
            # Only 2 parts — should return early
            await handle_handoff_callback(
                _task(callback_data='handoff:bad'))

    @pytest.mark.asyncio
    async def test_callback_no_staff(self):
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.handoff_handler.telegram_handler', mock_tg), \
             patch('handlers_v2.handoff_handler._get_staff', AsyncMock(return_value=None)):
            await handle_handoff_callback(
                _task(callback_data='handoff:accept:1'))


class TestRegistryExports:
    def test_commands_registered(self):
        assert 'handoff' in HANDOFF_COMMANDS

    def test_callbacks_registered(self):
        assert len(HANDOFF_CALLBACKS) >= 1

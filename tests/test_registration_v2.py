"""Tests for handlers_v2/registration_v2.py — /start, /profile, /lang, /setname, /bind."""
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from handlers_v2.registration_v2 import (
    handle_start_v2, handle_reg_lang_step, handle_reg_role_step,
    handle_reg_name_step, handle_profile, handle_lang, handle_setname,
    handle_bind, _pending, REGISTRATION_V2_COMMANDS, REGISTRATION_V2_CONVERSATIONS,
)
from models_v2 import Staff, StaffRole


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _staff(uid=1001, chat_id=2001, name='阿YIM', role=StaffRole.FRONTDESK,
           lang='zh', team=None, daily_target=40):
    return Staff(tg_user_id=uid, tg_chat_id=chat_id, display_name=name,
                 id=1, role=role, language=lang, team=team, daily_target=daily_target)


def _task(user_id=1001, chat_id=2001, text='', username='test_user',
          first_name='Test', args=''):
    return {
        'user_id': user_id, 'chat_id': chat_id, 'text': text,
        'username': username, 'first_name': first_name, 'args': args,
    }


@pytest.fixture(autouse=True)
def clear_pending():
    """Clear pending registrations before each test."""
    _pending.clear()
    yield
    _pending.clear()


# ─── Tests ─────────────────────────────────────────────────────────────────────

class TestHandleStartV2:
    @pytest.mark.asyncio
    async def test_existing_user_gets_welcome_back(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=staff)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_start_v2(_task())

        mock_tg.send_message.assert_awaited_once()
        assert 1001 not in _pending

    @pytest.mark.asyncio
    async def test_new_user_begins_registration(self):
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=None)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_start_v2(_task(user_id=2000))

        assert 2000 in _pending
        assert _pending[2000]['chat_id'] == 2001
        mock_tg.set_conversation_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_stores_username_and_first_name(self):
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=None)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_start_v2(_task(user_id=3000, username='myuser', first_name='Alice'))

        assert _pending[3000]['tg_username'] == 'myuser'
        assert _pending[3000]['first_name'] == 'Alice'


class TestRegLangStep:
    @pytest.mark.asyncio
    async def test_valid_zh(self):
        _pending[1001] = {'chat_id': 2001}
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_lang_step(_task(text='zh'))

        assert _pending[1001]['lang'] == 'zh'
        mock_tg.set_conversation_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_en(self):
        _pending[1001] = {'chat_id': 2001}
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_lang_step(_task(text='en'))

        assert _pending[1001]['lang'] == 'en'

    @pytest.mark.asyncio
    async def test_invalid_lang_rejected(self):
        _pending[1001] = {'chat_id': 2001}
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_lang_step(_task(text='fr'))

        assert 'lang' not in _pending.get(1001, {})
        mock_tg.set_conversation_state.assert_not_awaited()


class TestRegRoleStep:
    @pytest.mark.asyncio
    async def test_numeric_role_1(self):
        _pending[1001] = {'chat_id': 2001, 'lang': 'zh'}
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_role_step(_task(text='1'))

        assert _pending[1001]['role'] == StaffRole.FRONTDESK

    @pytest.mark.asyncio
    async def test_text_role_manager(self):
        _pending[1001] = {'chat_id': 2001, 'lang': 'en'}
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_role_step(_task(text='manager'))

        assert _pending[1001]['role'] == StaffRole.MANAGER

    @pytest.mark.asyncio
    async def test_invalid_role_rejected(self):
        _pending[1001] = {'chat_id': 2001, 'lang': 'zh'}
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.set_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_role_step(_task(text='ceo'))

        assert 'role' not in _pending.get(1001, {})


class TestRegNameStep:
    @pytest.mark.asyncio
    async def test_completes_registration(self):
        _pending[1001] = {'chat_id': 2001, 'lang': 'zh', 'role': StaffRole.FRONTDESK,
                          'tg_username': 'test_user', 'first_name': 'Test'}
        mock_db = MagicMock()
        mock_db.create_staff = AsyncMock(return_value=42)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.clear_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_name_step(_task(text='我的名字'))

        mock_db.create_staff.assert_awaited_once()
        created_staff = mock_db.create_staff.call_args[0][0]
        assert created_staff.display_name == '我的名字'
        assert created_staff.role == StaffRole.FRONTDESK
        assert created_staff.language == 'zh'
        mock_tg.clear_conversation_state.assert_called_once()
        assert 1001 not in _pending

    @pytest.mark.asyncio
    async def test_empty_name_uses_first_name(self):
        _pending[1001] = {'chat_id': 2001, 'lang': 'en', 'role': StaffRole.ADMIN,
                          'first_name': 'Alice'}
        mock_db = MagicMock()
        mock_db.create_staff = AsyncMock(return_value=1)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.clear_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_name_step(_task(text=''))

        created = mock_db.create_staff.call_args[0][0]
        assert created.display_name == 'Alice'

    @pytest.mark.asyncio
    async def test_empty_name_and_first_name_uses_fallback(self):
        _pending[1001] = {'chat_id': 2001, 'lang': 'zh', 'role': StaffRole.FRONTDESK}
        mock_db = MagicMock()
        mock_db.create_staff = AsyncMock(return_value=1)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()
        mock_tg.clear_conversation_state = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_reg_name_step(_task(text=''))

        created = mock_db.create_staff.call_args[0][0]
        assert 'User' in created.display_name


class TestHandleProfile:
    @pytest.mark.asyncio
    async def test_registered_user_sees_profile(self):
        staff = _staff(team='阿俊')
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=staff)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_profile(_task())

        msg = mock_tg.send_message.call_args[0][1]
        assert '阿YIM' in msg or staff.display_name in msg

    @pytest.mark.asyncio
    async def test_unregistered_user_gets_error(self):
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=None)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_profile(_task())

        mock_tg.send_message.assert_awaited_once()


class TestHandleLang:
    @pytest.mark.asyncio
    async def test_change_language(self):
        staff = _staff(lang='zh')
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=staff)
        mock_db.update_staff = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg), \
             patch('handlers_v2.registration_v2.t', return_value='Language changed'):
            await handle_lang(_task(args='en'))

        mock_db.update_staff.assert_awaited_once()
        assert staff.language == 'en'

    @pytest.mark.asyncio
    async def test_invalid_language(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=staff)
        mock_db.update_staff = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_lang(_task(args='jp'))

        mock_db.update_staff.assert_not_awaited()


class TestHandleSetname:
    @pytest.mark.asyncio
    async def test_change_name(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=staff)
        mock_db.update_staff = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_setname(_task(args='新名字'))

        assert staff.display_name == '新名字'
        mock_db.update_staff.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_name_shows_usage(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=staff)
        mock_db.update_staff = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_setname(_task(args=''))

        mock_db.update_staff.assert_not_awaited()


class TestHandleBind:
    @pytest.mark.asyncio
    async def test_bind_no_args_shows_usage(self):
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_bind(_task(args=''))

        msg = mock_tg.send_message.call_args[0][1]
        assert '/bind' in msg

    @pytest.mark.asyncio
    async def test_already_linked_user(self):
        staff = _staff()
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=staff)
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_bind(_task(args='阿YIM'))

        mock_tg.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bind_success(self):
        target = Staff(tg_user_id=0, tg_chat_id=0, display_name='阿毛',
                       id=5, role=StaffRole.FRONTDESK, team='阿俊')
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=None)
        mock_db.get_all_staff = AsyncMock(return_value=[target])
        mock_db.update_staff = AsyncMock()
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_bind(_task(user_id=5000, args='阿毛', username='realuser'))

        mock_db.update_staff.assert_awaited_once()
        assert target.tg_user_id == 5000
        assert target.tg_username == 'realuser'
        msg = mock_tg.send_message.call_args[0][1]
        assert '绑定成功' in msg or 'Bound' in msg

    @pytest.mark.asyncio
    async def test_bind_name_not_found(self):
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=None)
        mock_db.get_all_staff = AsyncMock(return_value=[])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_bind(_task(args='Nobody'))

        msg = mock_tg.send_message.call_args[0][1]
        assert '找不到' in msg or 'not found' in msg.lower()

    @pytest.mark.asyncio
    async def test_bind_already_bound_to_another(self):
        target = Staff(tg_user_id=999, tg_chat_id=999, display_name='阿毛',
                       id=5, role=StaffRole.FRONTDESK)
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=None)
        mock_db.get_all_staff = AsyncMock(return_value=[target])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_bind(_task(args='阿毛'))

        msg = mock_tg.send_message.call_args[0][1]
        assert '已经绑定' in msg or 'Already bound' in msg

    @pytest.mark.asyncio
    async def test_bind_multiple_matches(self):
        s1 = Staff(tg_user_id=0, tg_chat_id=0, display_name='阿毛1', id=1)
        s2 = Staff(tg_user_id=0, tg_chat_id=0, display_name='阿毛2', id=2)
        mock_db = MagicMock()
        mock_db.get_staff_by_tg_id = AsyncMock(return_value=None)
        mock_db.get_all_staff = AsyncMock(return_value=[s1, s2])
        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('handlers_v2.registration_v2.database_v2', mock_db), \
             patch('handlers_v2.registration_v2.telegram_handler', mock_tg):
            await handle_bind(_task(args='阿毛'))

        msg = mock_tg.send_message.call_args[0][1]
        assert '多个匹配' in msg or 'Multiple' in msg


class TestRegistryExports:
    def test_commands_registered(self):
        assert 'start' in REGISTRATION_V2_COMMANDS
        assert 'profile' in REGISTRATION_V2_COMMANDS
        assert 'lang' in REGISTRATION_V2_COMMANDS
        assert 'setname' in REGISTRATION_V2_COMMANDS
        assert 'bind' in REGISTRATION_V2_COMMANDS

    def test_conversations_registered(self):
        assert 'reg_v2_lang' in REGISTRATION_V2_CONVERSATIONS
        assert 'reg_v2_role' in REGISTRATION_V2_CONVERSATIONS
        assert 'reg_v2_name' in REGISTRATION_V2_CONVERSATIONS

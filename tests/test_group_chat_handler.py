"""Tests for handlers_v2/group_chat.py — group middleware, /linkgroup, /unlinkgroup."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from models_v2 import Staff, StaffRole


# ── Helpers ──────────────────────────────────────────────────────────────────

def _staff(role=StaffRole.FRONTDESK, lang='zh', staff_id=1, name='TestUser', tg_user_id=100):
    return Staff(
        id=staff_id, tg_user_id=tg_user_id, tg_chat_id=tg_user_id,
        display_name=name, role=role, language=lang,
    )


def _td(chat_type='private', text='', user_id=100, chat_id=-100, args='', **extra):
    d = {'chat_type': chat_type, 'text': text, 'user_id': user_id,
         'chat_id': chat_id, 'args': args}
    d.update(extra)
    return d


_P_STAFF = 'handlers_v2.group_chat._get_staff'
_P_TH = 'handlers_v2.group_chat.telegram_handler'
_P_DB = 'handlers_v2.group_chat.database_v2'
_P_T = 'handlers_v2.group_chat.t'
_P_TEAM_STRUCT = 'handlers_v2.group_chat.TEAM_STRUCTURE'


# ── is_group_chat / is_command_message ───────────────────────────────────────

class TestUtilities:

    def test_is_group_chat_private(self):
        from handlers_v2.group_chat import is_group_chat
        assert is_group_chat({'chat_type': 'private'}) is False

    def test_is_group_chat_group(self):
        from handlers_v2.group_chat import is_group_chat
        assert is_group_chat({'chat_type': 'group'}) is True

    def test_is_group_chat_supergroup(self):
        from handlers_v2.group_chat import is_group_chat
        assert is_group_chat({'chat_type': 'supergroup'}) is True

    def test_is_group_chat_missing_type(self):
        from handlers_v2.group_chat import is_group_chat
        # Default is 'private'
        assert is_group_chat({}) is False

    def test_is_command_message_yes(self):
        from handlers_v2.group_chat import is_command_message
        assert is_command_message({'text': '/start'}) is True

    def test_is_command_message_no(self):
        from handlers_v2.group_chat import is_command_message
        assert is_command_message({'text': 'hello'}) is False

    def test_is_command_message_empty(self):
        from handlers_v2.group_chat import is_command_message
        assert is_command_message({}) is False
        assert is_command_message({'text': None}) is False


# ── get_group_team ───────────────────────────────────────────────────────────

class TestGetGroupTeam:

    @pytest.mark.asyncio
    async def test_returns_team_when_linked(self):
        with patch(_P_DB) as db:
            db.get_group = AsyncMock(return_value={'team': 'TeamA'})
            from handlers_v2.group_chat import get_group_team
            result = await get_group_team(-12345)
            assert result == 'TeamA'

    @pytest.mark.asyncio
    async def test_returns_none_when_not_linked(self):
        with patch(_P_DB) as db:
            db.get_group = AsyncMock(return_value=None)
            from handlers_v2.group_chat import get_group_team
            result = await get_group_team(-99999)
            assert result is None


# ── group_middleware ─────────────────────────────────────────────────────────

class TestGroupMiddleware:

    @pytest.mark.asyncio
    async def test_dm_always_passes(self):
        from handlers_v2.group_chat import group_middleware
        td = _td(chat_type='private', text='hello')
        assert await group_middleware(td) is True

    @pytest.mark.asyncio
    async def test_group_non_command_blocked(self):
        from handlers_v2.group_chat import group_middleware
        td = _td(chat_type='group', text='just chatting')
        assert await group_middleware(td) is False

    @pytest.mark.asyncio
    async def test_group_command_passes(self):
        with patch(_P_DB) as db:
            db.get_group = AsyncMock(return_value=None)
            from handlers_v2.group_chat import group_middleware
            td = _td(chat_type='supergroup', text='/status')
            result = await group_middleware(td)
            assert result is True

    @pytest.mark.asyncio
    async def test_group_command_injects_team(self):
        with patch(_P_DB) as db:
            db.get_group = AsyncMock(return_value={'team': 'Sales'})
            from handlers_v2.group_chat import group_middleware
            td = _td(chat_type='group', text='/pipeline', chat_id=-555)
            await group_middleware(td)
            assert td.get('group_team') == 'Sales'


# ── /linkgroup ───────────────────────────────────────────────────────────────

class TestHandleLinkgroup:

    @pytest.mark.asyncio
    async def test_linkgroup_ignored_in_dm(self):
        """Should silently return in DM context."""
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=_staff(role=StaffRole.ADMIN)), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.group_chat import handle_linkgroup
            await handle_linkgroup(_td(chat_type='private', args='MyTeam'))
            th.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_linkgroup_not_registered(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th, patch(_P_T, return_value='err'):
            th.send_message = AsyncMock()
            from handlers_v2.group_chat import handle_linkgroup
            await handle_linkgroup(_td(chat_type='group'))
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_linkgroup_not_admin(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, patch(_P_T, return_value='denied'):
            th.send_message = AsyncMock()
            from handlers_v2.group_chat import handle_linkgroup
            await handle_linkgroup(_td(chat_type='group', args='Team'))
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_linkgroup_no_args(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, patch(_P_T, return_value='usage msg'):
            th.send_message = AsyncMock()
            from handlers_v2.group_chat import handle_linkgroup
            await handle_linkgroup(_td(chat_type='group', args=''))
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_linkgroup_team_not_found(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='not found') as mock_t, \
             patch(_P_DB) as db, \
             patch(_P_TEAM_STRUCT, {}):
            th.send_message = AsyncMock()
            db.get_all_teams = AsyncMock(return_value=[])
            from handlers_v2.group_chat import handle_linkgroup
            await handle_linkgroup(_td(chat_type='group', args='GhostTeam'))
            th.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_linkgroup_success(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='linked!'), \
             patch(_P_DB) as db, \
             patch(_P_TEAM_STRUCT, {'Sales': []}):
            th.send_message = AsyncMock()
            db.get_all_teams = AsyncMock(return_value=[])
            db.link_group = AsyncMock()
            from handlers_v2.group_chat import handle_linkgroup
            await handle_linkgroup(_td(chat_type='group', args='Sales', chat_title='My Group'))
            db.link_group.assert_awaited_once()


# ── /unlinkgroup ─────────────────────────────────────────────────────────────

class TestHandleUnlinkgroup:

    @pytest.mark.asyncio
    async def test_unlinkgroup_success(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='unlinked'), \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.unlink_group = AsyncMock(return_value=True)
            from handlers_v2.group_chat import handle_unlinkgroup
            await handle_unlinkgroup(_td(chat_type='group'))
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unlinkgroup_not_linked(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='not linked'), \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.unlink_group = AsyncMock(return_value=False)
            from handlers_v2.group_chat import handle_unlinkgroup
            await handle_unlinkgroup(_td(chat_type='group'))
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unlinkgroup_ignored_in_dm(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=_staff(role=StaffRole.ADMIN)), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.group_chat import handle_unlinkgroup
            await handle_unlinkgroup(_td(chat_type='private'))
            th.send_message.assert_not_awaited()


# ── Registry ─────────────────────────────────────────────────────────────────

class TestGroupRegistry:

    def test_group_commands_keys(self):
        from handlers_v2.group_chat import GROUP_COMMANDS
        assert 'linkgroup' in GROUP_COMMANDS
        assert 'unlinkgroup' in GROUP_COMMANDS

    def test_group_callbacks_empty(self):
        from handlers_v2.group_chat import GROUP_CALLBACKS
        assert isinstance(GROUP_CALLBACKS, dict)

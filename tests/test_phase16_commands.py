"""Tests for handlers_v2/phase16_commands.py — /link, /unlink, /links, /override,
/perms, /grant, /revoke, /comment, /stats."""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone

from models_v2 import Staff, StaffRole


# ── Helpers ──────────────────────────────────────────────────────────────────

def _staff(role=StaffRole.FRONTDESK, lang='zh', staff_id=1, name='TestUser', tg_user_id=100):
    return Staff(
        id=staff_id, tg_user_id=tg_user_id, tg_chat_id=tg_user_id,
        display_name=name, role=role, language=lang,
    )


def _td(user_id=100, chat_id=100, args='', **extra):
    d = {'user_id': user_id, 'chat_id': chat_id, 'args': args}
    d.update(extra)
    return d


# Patch targets
_P_STAFF = 'handlers_v2.phase16_commands._get_staff'
_P_TH = 'handlers_v2.phase16_commands.telegram_handler'
_P_DB = 'handlers_v2.phase16_commands.database_v2'
_P_T = 'handlers_v2.phase16_commands.t'


# ── /link ────────────────────────────────────────────────────────────────────

class TestHandleLink:

    @pytest.mark.asyncio
    async def test_link_not_registered(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th, patch(_P_T, return_value='not registered') as mock_t:
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_link
            await handle_link(_td())
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_link_missing_args(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_link
            await handle_link(_td(args=''))
            msg = th.send_message.call_args[0][1]
            assert 'Usage' in msg or '/link' in msg

    @pytest.mark.asyncio
    async def test_link_invalid_ids(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, patch(_P_T, return_value='invalid id'):
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_link
            await handle_link(_td(args='abc def'))
            th.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_link_invalid_type(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_link
            await handle_link(_td(args='1 2 badtype'))
            msg = th.send_message.call_args[0][1]
            assert 'Invalid type' in msg

    @pytest.mark.asyncio
    async def test_link_client_not_found(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_by_id = AsyncMock(return_value=None)
            from handlers_v2.phase16_commands import handle_link
            await handle_link(_td(args='1 2'))
            msg = th.send_message.call_args[0][1]
            assert 'not found' in msg

    @pytest.mark.asyncio
    async def test_link_success(self):
        staff = _staff()
        client = Mock(id=1)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_by_id = AsyncMock(return_value=client)
            db.create_client_link = AsyncMock()
            from handlers_v2.phase16_commands import handle_link
            await handle_link(_td(args='1 2 referral a note'))
            msg = th.send_message.call_args[0][1]
            assert '#1' in msg and '#2' in msg and 'referral' in msg

    @pytest.mark.asyncio
    async def test_link_duplicate(self):
        staff = _staff()
        client = Mock(id=1)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_by_id = AsyncMock(return_value=client)
            db.create_client_link = AsyncMock(side_effect=Exception('UNIQUE constraint'))
            from handlers_v2.phase16_commands import handle_link
            await handle_link(_td(args='1 2'))
            msg = th.send_message.call_args[0][1]
            assert 'Already linked' in msg


# ── /unlink ──────────────────────────────────────────────────────────────────

class TestHandleUnlink:

    @pytest.mark.asyncio
    async def test_unlink_not_registered(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th, patch(_P_T, return_value='err'):
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_unlink
            await handle_unlink(_td())
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unlink_success(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.remove_client_link = AsyncMock(return_value=True)
            from handlers_v2.phase16_commands import handle_unlink
            await handle_unlink(_td(args='1 2'))
            msg = th.send_message.call_args[0][1]
            assert 'Unlinked' in msg

    @pytest.mark.asyncio
    async def test_unlink_not_found(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.remove_client_link = AsyncMock(return_value=False)
            from handlers_v2.phase16_commands import handle_unlink
            await handle_unlink(_td(args='1 2'))
            msg = th.send_message.call_args[0][1]
            assert 'not found' in msg


# ── /links ───────────────────────────────────────────────────────────────────

class TestHandleLinks:

    @pytest.mark.asyncio
    async def test_links_no_args(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_links
            await handle_links(_td(args=''))
            msg = th.send_message.call_args[0][1]
            assert 'Usage' in msg

    @pytest.mark.asyncio
    async def test_links_empty(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_links = AsyncMock(return_value=[])
            from handlers_v2.phase16_commands import handle_links
            await handle_links(_td(args='5'))
            msg = th.send_message.call_args[0][1]
            assert 'No links' in msg

    @pytest.mark.asyncio
    async def test_links_shows_results(self):
        staff = _staff()
        link_data = [{
            'client_id_a': 5, 'client_id_b': 10,
            'phone_a': '+1111', 'phone_b': '+2222',
            'link_type': 'family',
        }]
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_links = AsyncMock(return_value=link_data)
            from handlers_v2.phase16_commands import handle_links
            await handle_links(_td(args='5'))
            msg = th.send_message.call_args[0][1]
            assert '#10' in msg and 'family' in msg


# ── /override ────────────────────────────────────────────────────────────────

class TestHandleOverride:

    @pytest.mark.asyncio
    async def test_override_permission_denied(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, patch(_P_T, return_value='denied'):
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_override
            await handle_override(_td(args='+123'))
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_override_phone_not_found(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.phone_registry_lookup = AsyncMock(return_value=None)
            from handlers_v2.phase16_commands import handle_override
            await handle_override(_td(args='+123'))
            msg = th.send_message.call_args[0][1]
            assert 'not in registry' in msg

    @pytest.mark.asyncio
    async def test_override_success(self):
        staff = _staff(role=StaffRole.ADMIN, name='Boss')
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.phone_registry_lookup = AsyncMock(return_value={'submitter_name': 'OldGuy'})
            db.phone_registry_override = AsyncMock()
            db.phone_registry_log_action = AsyncMock()
            from handlers_v2.phase16_commands import handle_override
            await handle_override(_td(args='+123'))
            msg = th.send_message.call_args[0][1]
            assert 'Override' in msg and 'Boss' in msg


# ── /perms ───────────────────────────────────────────────────────────────────

class TestHandlePerms:

    @pytest.mark.asyncio
    async def test_perms_own(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_all_permission_overrides = AsyncMock(return_value=[])
            from handlers_v2.phase16_commands import handle_perms
            await handle_perms(_td(args=''))
            msg = th.send_message.call_args[0][1]
            assert 'Permissions' in msg and 'TestUser' in msg

    @pytest.mark.asyncio
    async def test_perms_other_as_admin(self):
        staff = _staff(role=StaffRole.ADMIN)
        target = _staff(name='Other', staff_id=2, tg_user_id=200)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_all_staff = AsyncMock(return_value=[target])
            db.get_all_permission_overrides = AsyncMock(return_value=[
                {'command': 'export', 'allowed': True, 'reason': 'test'}
            ])
            from handlers_v2.phase16_commands import handle_perms
            await handle_perms(_td(args='Other'))
            msg = th.send_message.call_args[0][1]
            assert 'Other' in msg and 'GRANT' in msg

    @pytest.mark.asyncio
    async def test_perms_other_denied_for_frontdesk(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, patch(_P_T, return_value='denied'):
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_perms
            await handle_perms(_td(args='OtherPerson'))
            th.send_message.assert_awaited_once()


# ── /grant & /revoke ─────────────────────────────────────────────────────────

class TestHandleGrantRevoke:

    @pytest.mark.asyncio
    async def test_grant_success(self):
        staff = _staff(role=StaffRole.ADMIN)
        target = _staff(name='Worker', staff_id=2, tg_user_id=200)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_all_staff = AsyncMock(return_value=[target])
            db.set_permission_override = AsyncMock()
            from handlers_v2.phase16_commands import handle_grant
            await handle_grant(_td(args='Worker export reason here'))
            msg = th.send_message.call_args[0][1]
            assert 'Granted' in msg and '/export' in msg

    @pytest.mark.asyncio
    async def test_revoke_success(self):
        staff = _staff(role=StaffRole.ADMIN)
        target = _staff(name='Worker', staff_id=2, tg_user_id=200)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_all_staff = AsyncMock(return_value=[target])
            db.set_permission_override = AsyncMock()
            from handlers_v2.phase16_commands import handle_revoke
            await handle_revoke(_td(args='Worker export'))
            msg = th.send_message.call_args[0][1]
            assert 'Revoked' in msg

    @pytest.mark.asyncio
    async def test_grant_missing_args(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_grant
            await handle_grant(_td(args=''))
            msg = th.send_message.call_args[0][1]
            assert 'Usage' in msg

    @pytest.mark.asyncio
    async def test_grant_staff_not_found(self):
        staff = _staff(role=StaffRole.ADMIN)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_all_staff = AsyncMock(return_value=[])
            from handlers_v2.phase16_commands import handle_grant
            await handle_grant(_td(args='Nobody export'))
            msg = th.send_message.call_args[0][1]
            assert 'not found' in msg


# ── /comment ─────────────────────────────────────────────────────────────────

class TestHandleComment:

    @pytest.mark.asyncio
    async def test_comment_success_by_id(self):
        staff = _staff()
        client = Mock(id=5, phone='+999')
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_by_id = AsyncMock(return_value=client)
            db.add_client_comment = AsyncMock()
            db.normalize_phone = Mock(return_value='999')
            from handlers_v2.phase16_commands import handle_comment
            await handle_comment(_td(args='5 hello world'))
            msg = th.send_message.call_args[0][1]
            assert '#5' in msg

    @pytest.mark.asyncio
    async def test_comment_missing_args(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.phase16_commands import handle_comment
            await handle_comment(_td(args=''))
            msg = th.send_message.call_args[0][1]
            assert '/comment' in msg.lower() or 'usage' in msg.lower() or '用法' in msg

    @pytest.mark.asyncio
    async def test_comment_client_not_found(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_by_id = AsyncMock(return_value=None)
            db.get_client_by_phone = AsyncMock(return_value=None)
            from handlers_v2.phase16_commands import handle_comment
            await handle_comment(_td(args='99999 some text'))
            msg = th.send_message.call_args[0][1]
            assert '找不到' in msg or 'not found' in msg.lower()


# ── /stats ───────────────────────────────────────────────────────────────────

class TestHandleStats:

    @pytest.mark.asyncio
    async def test_stats_no_data(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_performance_daily = AsyncMock(return_value=[])
            from handlers_v2.phase16_commands import handle_stats
            await handle_stats(_td())
            msg = th.send_message.call_args[0][1]
            assert '暂无' in msg or 'No data' in msg

    @pytest.mark.asyncio
    async def test_stats_with_data_zh(self):
        staff = _staff(lang='zh')
        daily = [{'staff_id': 1, 'new_leads': 10, 'reply_rate': 80,
                   'registered': 5, 'training': 3, 'withdrew': 2,
                   'new_orders': 4, 'conversion_rate': 40,
                   'total_deposit': 1000, 'dead': 1}]
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_performance_daily = AsyncMock(return_value=daily)
            from handlers_v2.phase16_commands import handle_stats
            await handle_stats(_td())
            msg = th.send_message.call_args[0][1]
            assert '新粉丝' in msg and '10' in msg

    @pytest.mark.asyncio
    async def test_stats_with_data_en(self):
        staff = _staff(lang='en')
        daily = [{'staff_id': 1, 'new_leads': 7, 'reply_rate': 90,
                   'registered': 3, 'training': 2, 'withdrew': 1,
                   'new_orders': 2, 'conversion_rate': 66,
                   'total_deposit': 500, 'dead': 0}]
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_performance_daily = AsyncMock(return_value=daily)
            from handlers_v2.phase16_commands import handle_stats
            await handle_stats(_td(args='2024-01-15'))
            msg = th.send_message.call_args[0][1]
            assert 'New Leads' in msg and '7' in msg


# ── Command dispatch registry ────────────────────────────────────────────────

class TestCommandRegistry:

    def test_phase16_commands_keys(self):
        from handlers_v2.phase16_commands import PHASE16_COMMANDS
        expected = {'link', 'unlink', 'links', 'override', 'perms', 'grant', 'revoke', 'comment', 'stats'}
        assert set(PHASE16_COMMANDS.keys()) == expected

    def test_phase16_callbacks_empty(self):
        from handlers_v2.phase16_commands import PHASE16_CALLBACKS
        assert isinstance(PHASE16_CALLBACKS, dict)

    def test_phase16_conversations_empty(self):
        from handlers_v2.phase16_commands import PHASE16_CONVERSATIONS
        assert isinstance(PHASE16_CONVERSATIONS, dict)

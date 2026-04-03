"""Tests for handlers_v2/nl_handler.py — natural language CRM handler."""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from models_v2 import Staff, StaffRole, Client, ClientStatus, ClientNote, NoteType


# ── Helpers ──────────────────────────────────────────────────────────────────

def _staff(role=StaffRole.FRONTDESK, lang='zh', staff_id=1, name='TestFD', tg_user_id=100):
    return Staff(
        id=staff_id, tg_user_id=tg_user_id, tg_chat_id=tg_user_id,
        display_name=name, role=role, language=lang,
    )


def _client(cid=10, phone='+8612345', nickname='TestClient', status=ClientStatus.NEW,
            frontdesk_id=1, source='telegram'):
    return Client(
        id=cid, frontdesk_id=frontdesk_id, phone=phone, nickname=nickname,
        status=status, source=source,
    )


def _td(user_id=100, chat_id=100, text='', **extra):
    d = {'user_id': user_id, 'chat_id': chat_id, 'text': text}
    d.update(extra)
    return d


_P_STAFF = 'handlers_v2.nl_handler._get_staff'
_P_TH = 'handlers_v2.nl_handler.telegram_handler'
_P_DB = 'handlers_v2.nl_handler.database_v2'


# ── Keyboard builders ───────────────────────────────────────────────────────

class TestKeyboardBuilders:

    def test_kb_client_actions(self):
        with patch(_P_TH) as th:
            th.create_inline_keyboard = Mock(return_value='keyboard')
            from handlers_v2.nl_handler import _kb_client_actions
            result = _kb_client_actions(42)
            th.create_inline_keyboard.assert_called_once()
            args = th.create_inline_keyboard.call_args[0][0]
            # Verify callback data contains client_id
            flat = [btn for row in args for btn in row]
            cbs = [b['callback_data'] for b in flat]
            assert any('42' in cb for cb in cbs)

    def test_kb_fallback_menu(self):
        with patch(_P_TH) as th:
            th.create_inline_keyboard = Mock(return_value='kb')
            from handlers_v2.nl_handler import _kb_fallback_menu
            result = _kb_fallback_menu()
            th.create_inline_keyboard.assert_called_once()

    def test_kb_status_updated_with_old(self):
        with patch(_P_TH) as th:
            th.create_inline_keyboard = Mock(return_value='kb')
            from handlers_v2.nl_handler import _kb_status_updated
            _kb_status_updated(5, 'new')
            args = th.create_inline_keyboard.call_args[0][0]
            flat = [btn for row in args for btn in row]
            cbs = [b['callback_data'] for b in flat]
            assert any('nl_undo:5:new' in cb for cb in cbs)

    def test_kb_search_results(self):
        with patch(_P_TH) as th:
            th.create_inline_keyboard = Mock(return_value='kb')
            from handlers_v2.nl_handler import _kb_search_results
            _kb_search_results(99)
            args = th.create_inline_keyboard.call_args[0][0]
            flat = [btn for row in args for btn in row]
            cbs = [b['callback_data'] for b in flat]
            assert any('99' in cb for cb in cbs)


# ── _client_card ─────────────────────────────────────────────────────────────

class TestClientCard:

    def test_client_card_full(self):
        from handlers_v2.nl_handler import _client_card
        c = _client(nickname='Bob', phone='+123', status=ClientStatus.REGISTERED, source='sms')
        card = _client_card(c)
        assert 'Bob' in card
        assert '+123' in card
        assert 'registered' in card
        assert 'sms' in card

    def test_client_card_no_nickname(self):
        from handlers_v2.nl_handler import _client_card
        c = _client(nickname=None, phone='+999')
        card = _client_card(c)
        assert 'Name' not in card or '姓名' not in card
        assert '+999' in card

    def test_client_card_no_phone(self):
        from handlers_v2.nl_handler import _client_card
        c = _client(phone=None)
        card = _client_card(c)
        assert 'Phone' not in card or 'phone' not in card.lower() or '电话' not in card


# ── _find_client ─────────────────────────────────────────────────────────────

class TestFindClient:

    @pytest.mark.asyncio
    async def test_find_by_phone(self):
        client = _client()
        with patch(_P_DB) as db:
            db.get_client_by_phone = AsyncMock(return_value=client)
            from handlers_v2.nl_handler import _find_client
            c, amb = await _find_client(1, {'phone': '+123'})
            assert c is client
            assert amb == []

    @pytest.mark.asyncio
    async def test_find_by_name_single(self):
        client = _client()
        with patch(_P_DB) as db:
            db.get_client_by_phone = AsyncMock(return_value=None)
            db.search_clients = AsyncMock(return_value=[client])
            from handlers_v2.nl_handler import _find_client
            c, amb = await _find_client(1, {'client_name': 'Bob'})
            assert c is client

    @pytest.mark.asyncio
    async def test_find_by_name_ambiguous(self):
        c1, c2 = _client(cid=1), _client(cid=2)
        with patch(_P_DB) as db:
            db.get_client_by_phone = AsyncMock(return_value=None)
            db.search_clients = AsyncMock(return_value=[c1, c2])
            from handlers_v2.nl_handler import _find_client
            c, amb = await _find_client(1, {'client_name': 'test'})
            assert c is None
            assert len(amb) == 2

    @pytest.mark.asyncio
    async def test_find_no_match(self):
        with patch(_P_DB) as db:
            db.get_client_by_phone = AsyncMock(return_value=None)
            db.search_clients = AsyncMock(return_value=[])
            from handlers_v2.nl_handler import _find_client
            c, amb = await _find_client(1, {'client_name': 'nobody'})
            assert c is None
            assert amb == []


# ── handle_nl_message ────────────────────────────────────────────────────────

class TestHandleNlMessage:

    @pytest.mark.asyncio
    async def test_not_registered(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_message
            await handle_nl_message(_td(text='hello'))
            th.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_text(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=_staff()), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_message
            await handle_nl_message(_td(text=''))
            th.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_intent_shows_fallback(self):
        staff = _staff()
        parse_result = {'intent': 'UNKNOWN', 'confidence': 0.2, 'entities': {}}
        mock_nl = MagicMock()
        mock_nl.parse = AsyncMock(return_value=parse_result)
        mock_nl.QUERY_CLIENT = 'QUERY_CLIENT'
        mock_nl.UPDATE_STATUS = 'UPDATE_STATUS'
        mock_nl.ADD_NOTE = 'ADD_NOTE'
        mock_nl.LIST_PIPELINE = 'LIST_PIPELINE'
        mock_nl.SEARCH = 'SEARCH'
        mock_nl.HELP = 'HELP'
        mock_nl.UNKNOWN = 'UNKNOWN'
        mock_nl.CONFIDENCE_THRESHOLD = 0.7
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch.dict('sys.modules', {'engines.nl_engine': mock_nl}):
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            from handlers_v2.nl_handler import handle_nl_message
            await handle_nl_message(_td(text='asdfghjkl'))
            # Should have sent 'Processing...' + fallback
            assert th.send_message.await_count >= 1

    @pytest.mark.asyncio
    async def test_query_client_intent(self):
        staff = _staff()
        client = _client(frontdesk_id=1)
        parse_result = {
            'intent': 'QUERY_CLIENT', 'confidence': 0.95,
            'entities': {'phone': '+123'},
        }
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            db.get_client_by_phone = AsyncMock(return_value=client)
            with patch.dict('sys.modules', {'engines.nl_engine': MagicMock(
                parse=AsyncMock(return_value=parse_result),
                QUERY_CLIENT='QUERY_CLIENT', UPDATE_STATUS='UPDATE_STATUS',
                ADD_NOTE='ADD_NOTE', LIST_PIPELINE='LIST_PIPELINE',
                SEARCH='SEARCH', HELP='HELP', UNKNOWN='UNKNOWN',
                CONFIDENCE_THRESHOLD=0.7,
            )}):
                from handlers_v2.nl_handler import handle_nl_message
                await handle_nl_message(_td(text='check +123'))
                # Should send processing + client card
                assert th.send_message.await_count >= 2

    @pytest.mark.asyncio
    async def test_help_intent(self):
        staff = _staff()
        parse_result = {'intent': 'HELP', 'confidence': 0.9, 'entities': {}}
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            with patch.dict('sys.modules', {'engines.nl_engine': MagicMock(
                parse=AsyncMock(return_value=parse_result),
                QUERY_CLIENT='QUERY_CLIENT', UPDATE_STATUS='UPDATE_STATUS',
                ADD_NOTE='ADD_NOTE', LIST_PIPELINE='LIST_PIPELINE',
                SEARCH='SEARCH', HELP='HELP', UNKNOWN='UNKNOWN',
                CONFIDENCE_THRESHOLD=0.7,
            )}):
                from handlers_v2.nl_handler import handle_nl_message
                await handle_nl_message(_td(text='help'))
                # Should send processing + help text
                calls = th.send_message.call_args_list
                assert any('指南' in str(c) or 'Guide' in str(c) for c in calls)


# ── Callback handlers ────────────────────────────────────────────────────────

class TestNlCallbacks:

    @pytest.mark.asyncio
    async def test_nl_ok(self):
        with patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_ok
            await handle_nl_ok({'chat_id': 1})
            assert 'OK' in th.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_nl_cancel(self):
        with patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.clear_conversation_state = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_cancel
            await handle_nl_cancel({'chat_id': 1, 'user_id': 100})
            msg = th.send_message.call_args[0][1]
            assert '取消' in msg or 'Cancel' in msg

    @pytest.mark.asyncio
    async def test_nl_next_client(self):
        with patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            from handlers_v2.nl_handler import handle_nl_next_client
            await handle_nl_next_client({'chat_id': 1})
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nl_search_more(self):
        with patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            from handlers_v2.nl_handler import handle_nl_search_more
            await handle_nl_search_more({'chat_id': 1})
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nl_menu_add(self):
        with patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_menu_add
            await handle_nl_menu_add({'chat_id': 1})
            msg = th.send_message.call_args[0][1]
            assert '/add' in msg

    @pytest.mark.asyncio
    async def test_nl_menu_voice(self):
        with patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_menu_voice
            await handle_nl_menu_voice({'chat_id': 1})
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nl_client_detail_not_found(self):
        with patch(_P_TH) as th, patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.get_client_by_id = AsyncMock(return_value=None)
            from handlers_v2.nl_handler import handle_nl_client_detail
            await handle_nl_client_detail({'chat_id': 1, 'callback_data': 'nl_client_detail:999'})
            msg = th.send_message.call_args[0][1]
            assert 'not found' in msg.lower() or '不存在' in msg

    @pytest.mark.asyncio
    async def test_nl_client_detail_success(self):
        client = _client()
        with patch(_P_TH) as th, patch(_P_DB) as db:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            db.get_client_by_id = AsyncMock(return_value=client)
            db.get_client_notes = AsyncMock(return_value=[])
            from handlers_v2.nl_handler import handle_nl_client_detail
            await handle_nl_client_detail({'chat_id': 1, 'callback_data': 'nl_client_detail:10'})
            msg = th.send_message.call_args[0][1]
            assert 'Client Info' in msg or '客户信息' in msg

    @pytest.mark.asyncio
    async def test_nl_confirm_update_bad_data(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_confirm_update
            await handle_nl_confirm_update({
                'chat_id': 1, 'user_id': 100,
                'callback_data': 'nl_confirm_update:baddata'
            })
            msg = th.send_message.call_args[0][1]
            assert '错误' in msg or 'Bad' in msg or '数据' in msg


# ── Conversation steps ───────────────────────────────────────────────────────

class TestConversationSteps:

    @pytest.mark.asyncio
    async def test_await_note_success(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            th.get_conversation_state = AsyncMock(return_value={
                'step': 'nl_await_note', 'pending': {'client_id': 10}
            })
            th.clear_conversation_state = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            db.add_client_note = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_await_note
            await handle_nl_await_note({
                'chat_id': 1, 'user_id': 100, 'message': 'my note text'
            })
            db.add_client_note.assert_awaited_once()
            msg = th.send_message.call_args[0][1]
            assert '备注' in msg or 'Note' in msg

    @pytest.mark.asyncio
    async def test_await_note_no_state(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.get_conversation_state = AsyncMock(return_value=None)
            th.clear_conversation_state = AsyncMock()
            from handlers_v2.nl_handler import handle_nl_await_note
            await handle_nl_await_note({
                'chat_id': 1, 'user_id': 100, 'message': 'text'
            })
            msg = th.send_message.call_args[0][1]
            assert '失败' in msg or 'failed' in msg.lower()


# ── Registry ─────────────────────────────────────────────────────────────────

class TestNlRegistry:

    def test_nl_callbacks_keys(self):
        from handlers_v2.nl_handler import NL_HANDLER_CALLBACKS
        assert 'nl_cancel' in NL_HANDLER_CALLBACKS
        assert 'nl_next_client' in NL_HANDLER_CALLBACKS

    def test_nl_conversations_keys(self):
        from handlers_v2.nl_handler import NL_HANDLER_CONVERSATIONS
        assert 'nl_await_status' in NL_HANDLER_CONVERSATIONS
        assert 'nl_await_note' in NL_HANDLER_CONVERSATIONS

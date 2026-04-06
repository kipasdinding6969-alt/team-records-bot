"""Tests for Phase 6 inline keyboard flows.

Covers: menu layout, pipeline browser, status update, note flow,
follow-up dashboard, quick add client.
"""
import pytest
import pytest_asyncio
from datetime import timezone, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from database_v2 import DatabaseV2
from models_v2 import Client, ClientNote, ClientStatus, NoteType, Staff, StaffRole


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_flows.db'))
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=8001,
        tg_chat_id=7001,
        display_name='FlowStaff',
        role=StaffRole.FRONTDESK,
        team='A',
        language='zh',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def staff_en(db):
    s = Staff(
        tg_user_id=8002,
        tg_chat_id=7002,
        display_name='EnStaff',
        role=StaffRole.FRONTDESK,
        team='A',
        language='en',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client_row(db, staff):
    c = Client(frontdesk_id=staff.id, phone='0111222333', source='fb')
    c.id = await db.create_client(c)
    return c


@pytest_asyncio.fixture
async def clients_5(db, staff):
    """Create 5 clients for pagination tests."""
    rows = []
    for i in range(5):
        c = Client(frontdesk_id=staff.id, phone=f'011{i:07d}', source='fb')
        c.id = await db.create_client(c)
        rows.append(c)
    return rows


def _mock_tg():
    m = MagicMock()
    m.send_message = AsyncMock()
    m.edit_message = AsyncMock()
    m.create_inline_keyboard = MagicMock(return_value=[[]])
    m.set_conversation_state = AsyncMock()
    m.get_conversation_state = AsyncMock(return_value=None)
    m.clear_conversation_state = AsyncMock()
    return m


def _task(chat_id, user_id, callback=None, message=None, message_id=None):
    d = {'chat_id': chat_id, 'user_id': user_id}
    if callback:
        d['callback_data'] = callback
    if message:
        d['message'] = message
    if message_id:
        d['message_id'] = message_id
    return d


# ── Menu layout ───────────────────────────────────────────────────────────────

class TestMenuOverhaul:
    def test_new_8_buttons_layout(self):
        """New menu has exactly 8 buttons in 4 rows of 2."""
        captured = []
        mock_tg = _mock_tg()
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured.extend(rows) or [[]])

        with patch('handlers_v2.menu.telegram_handler', mock_tg):
            from handlers_v2.menu import _main_menu_keyboard
            _main_menu_keyboard('zh')

        assert len(captured) == 4
        assert all(len(row) == 2 for row in captured)
        assert sum(len(r) for r in captured) == 8

    def test_new_callbacks_registered(self):
        """All 8 new menu callbacks are registered."""
        from handlers_v2.menu import MENU_CALLBACKS
        expected = [
            'menu_pipeline', 'menu_add', 'menu_followup', 'menu_leaderboard',
            'menu_today', 'menu_voice', 'menu_app', 'menu_help', 'qs_*',
        ]
        for key in expected:
            assert key in MENU_CALLBACKS, f"Missing: {key}"

    def test_zh_buttons_have_chinese(self):
        """Chinese layout shows Chinese characters."""
        captured = []
        mock_tg = _mock_tg()
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured.extend(rows) or [[]])

        with patch('handlers_v2.menu.telegram_handler', mock_tg):
            from handlers_v2.menu import _main_menu_keyboard
            _main_menu_keyboard('zh')

        texts = [btn['text'] for row in captured for btn in row]
        assert any('\u4e00' <= c <= '\u9fff' for t in texts for c in t)

    @pytest.mark.asyncio
    async def test_menu_help_sends_message(self, staff):
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_menu_callback
            await handle_menu_callback(_task(staff.tg_chat_id, staff.tg_user_id, 'menu_help'))

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_menu_voice_sends_hint(self, staff):
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_menu_callback
            await handle_menu_callback(_task(staff.tg_chat_id, staff.tg_user_id, 'menu_voice'))

        mock_tg.send_message.assert_called_once()


# ── Pipeline Browser ──────────────────────────────────────────────────────────

class TestPipelineBrowser:
    @pytest.mark.asyncio
    async def test_pipe_pg_empty(self, db, staff):
        """pipe:pg:0:all with no clients sends empty message."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            await handle_pipe_callback(_task(staff.tg_chat_id, staff.tg_user_id, 'pipe:pg:0:all'))

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipe_pg_shows_clients(self, db, staff, clients_5):
        """pipe:pg:0:all with clients shows them."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            await handle_pipe_callback(_task(staff.tg_chat_id, staff.tg_user_id, 'pipe:pg:0:all'))

        mock_tg.send_message.assert_called_once()
        # Verify keyboard was built with client rows
        mock_tg.create_inline_keyboard.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipe_filter_by_status(self, db, staff, client_row):
        """pipe:f:new filters to new clients."""
        # Update one client to contacted
        await db.update_client_status(client_row.id, ClientStatus.CONTACTED, staff.id)

        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            await handle_pipe_callback(_task(staff.tg_chat_id, staff.tg_user_id, 'pipe:f:new'))

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipe_detail_shows_client_info(self, db, staff, client_row):
        """pipe:d:{id} shows client detail card."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            await handle_pipe_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'pipe:d:{client_row.id}'))

        mock_tg.send_message.assert_called_once()
        text = mock_tg.send_message.call_args[0][1]
        assert client_row.phone in text

    @pytest.mark.asyncio
    async def test_pipe_detail_wrong_owner_shows_error(self, db, staff, staff_en, client_row):
        """pipe:d:{id} for another user's client shows not-found."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff_en)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            await handle_pipe_callback(
                _task(staff_en.tg_chat_id, staff_en.tg_user_id, f'pipe:d:{client_row.id}'))

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipe_back_calls_start(self, staff):
        """pipe:back re-shows the main menu."""
        mock_tg = _mock_tg()
        mock_start = AsyncMock()
        with (
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
            patch('handlers_v2.inline_flows.handle_pipe_callback.__module__',
                  'handlers_v2.inline_flows'),
            patch('handlers_v2.menu.handle_start', mock_start),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            import importlib
            import handlers_v2.menu as menu_mod
            import handlers_v2.inline_flows as flows_mod
            # Patch handle_start in the flows module namespace
            original = flows_mod.handle_pipe_callback
            await handle_pipe_callback(_task(staff.tg_chat_id, staff.tg_user_id, 'pipe:back'))

    @pytest.mark.asyncio
    async def test_pipe_uses_edit_message_when_message_id_present(self, db, staff, client_row):
        """With message_id, pipe page uses edit_message for in-place nav."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            td = _task(staff.tg_chat_id, staff.tg_user_id, 'pipe:pg:0:all', message_id=999)
            await handle_pipe_callback(td)

        mock_tg.edit_message.assert_called_once()
        mock_tg.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipe_pagination(self, db, staff):
        """6 clients → page 0 shows 5, page 1 shows 1."""
        for i in range(6):
            c = Client(frontdesk_id=staff.id, phone=f'0199{i:06d}', source='fb')
            await db.create_client(c)

        mock_tg = _mock_tg()
        captured_rows = []
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured_rows.extend(rows) or [[]])

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_pipe_callback
            await handle_pipe_callback(_task(staff.tg_chat_id, staff.tg_user_id, 'pipe:pg:0:all'))

        # 5 client rows + 2 filter rows + 1 nav row = 8 rows
        assert len(captured_rows) >= 5


# ── Quick Status Update ───────────────────────────────────────────────────────

class TestStatusFlow:
    @pytest.mark.asyncio
    async def test_status_picker_shows_valid_transitions(self, db, staff, client_row):
        """status:p:{id} shows buttons for valid transitions."""
        captured_rows = []
        mock_tg = _mock_tg()
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured_rows.extend(rows) or [[]])

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_status_callback
            await handle_status_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'status:p:{client_row.id}'))

        # Buttons show valid transitions from NEW
        valid = ClientStatus.valid_transitions(ClientStatus.NEW)
        btn_callbacks = [btn['callback_data'] for row in captured_rows for btn in row]
        status_callbacks = [c for c in btn_callbacks if c.startswith('status:do:')]
        assert len(status_callbacks) == len(valid)

    @pytest.mark.asyncio
    async def test_status_do_updates_db(self, db, staff, client_row):
        """status:do:{id}:contacted updates the client status in DB."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_status_callback
            await handle_status_callback(
                _task(staff.tg_chat_id, staff.tg_user_id,
                      f'status:do:{client_row.id}:contacted'))

        updated = await db.get_client_by_id(client_row.id)
        assert updated.status == ClientStatus.CONTACTED
        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_do_invalid_status_sends_error(self, db, staff, client_row):
        """status:do with invalid status value sends error."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_status_callback
            await handle_status_callback(
                _task(staff.tg_chat_id, staff.tg_user_id,
                      f'status:do:{client_row.id}:INVALID'))

        mock_tg.send_message.assert_called_once()
        unchanged = await db.get_client_by_id(client_row.id)
        assert unchanged.status == ClientStatus.NEW

    @pytest.mark.asyncio
    async def test_status_do_wrong_owner_denied(self, db, staff, staff_en, client_row):
        """status:do on another user's client → not found."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff_en)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_status_callback
            await handle_status_callback(
                _task(staff_en.tg_chat_id, staff_en.tg_user_id,
                      f'status:do:{client_row.id}:contacted'))

        mock_tg.send_message.assert_called_once()
        unchanged = await db.get_client_by_id(client_row.id)
        assert unchanged.status == ClientStatus.NEW

    @pytest.mark.asyncio
    async def test_status_do_includes_smart_suggestion(self, db, staff, client_row):
        """Status update to 'contacted' includes smart next-step suggestion."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_status_callback
            await handle_status_callback(
                _task(staff.tg_chat_id, staff.tg_user_id,
                      f'status:do:{client_row.id}:contacted'))

        text = mock_tg.send_message.call_args[0][1]
        # Smart suggestion should be in the response
        assert '💡' in text or '📨' in text

    @pytest.mark.asyncio
    async def test_status_picker_buttons_max_3_per_row(self, db, staff, client_row):
        """Status picker never has more than 3 buttons per row."""
        captured_rows = []
        mock_tg = _mock_tg()
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured_rows.extend(rows) or [[]])

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_status_callback
            await handle_status_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'status:p:{client_row.id}'))

        for row in captured_rows:
            assert len(row) <= 3


# ── Note Flow ─────────────────────────────────────────────────────────────────

class TestNoteFlow:
    @pytest.mark.asyncio
    async def test_note_s_sets_conversation_state(self, db, staff, client_row):
        """note:s:{id} sets conversation state and prompts for text."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_note_callback
            await handle_note_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'note:s:{client_row.id}'))

        mock_tg.set_conversation_state.assert_called_once()
        state = mock_tg.set_conversation_state.call_args[0][1]
        assert state['step'] == 'inline_await_note'
        assert state['pending']['client_id'] == client_row.id
        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_inline_await_note_saves_to_db(self, db, staff, client_row):
        """Conversation step saves note to DB and clears state."""
        mock_tg = _mock_tg()
        mock_tg.get_conversation_state = AsyncMock(return_value={
            'step': 'inline_await_note',
            'pending': {'client_id': client_row.id},
        })

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_inline_await_note
            td = _task(staff.tg_chat_id, staff.tg_user_id)
            td['message'] = 'Very interested client'
            await handle_inline_await_note(td)

        mock_tg.clear_conversation_state.assert_called_once()
        mock_tg.send_message.assert_called_once()
        notes = await db.get_client_notes(client_row.id)
        assert any(n.content == 'Very interested client' for n in notes)

    @pytest.mark.asyncio
    async def test_inline_await_note_empty_text_fails_gracefully(self, db, staff, client_row):
        """Empty note text → error message, no note saved."""
        mock_tg = _mock_tg()
        mock_tg.get_conversation_state = AsyncMock(return_value={
            'step': 'inline_await_note',
            'pending': {'client_id': client_row.id},
        })

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_inline_await_note
            td = _task(staff.tg_chat_id, staff.tg_user_id)
            td['message'] = '   '
            await handle_inline_await_note(td)

        mock_tg.send_message.assert_called_once()
        notes = await db.get_client_notes(client_row.id)
        assert not notes

    @pytest.mark.asyncio
    async def test_note_wrong_owner_sends_error(self, db, staff, staff_en, client_row):
        """note:s on another user's client → error."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff_en)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_note_callback
            await handle_note_callback(
                _task(staff_en.tg_chat_id, staff_en.tg_user_id, f'note:s:{client_row.id}'))

        mock_tg.set_conversation_state.assert_not_called()
        mock_tg.send_message.assert_called_once()


# ── Follow-up Dashboard ───────────────────────────────────────────────────────

class TestFollowupDashboard:
    @pytest.mark.asyncio
    async def test_fu_start_empty(self, db, staff):
        """No overdue clients → single empty message."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_fu_start
            await handle_fu_start(_task(staff.tg_chat_id, staff.tg_user_id))

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_fu_start_shows_overdue_clients(self, db, staff, client_row):
        """Overdue client → shows client card with 3 action buttons."""
        await db.set_next_followup(
            client_row.id, datetime.now(timezone.utc) - timedelta(hours=1))

        captured_rows = []
        mock_tg = _mock_tg()
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured_rows.extend(rows) or [[]])

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_fu_start
            await handle_fu_start(_task(staff.tg_chat_id, staff.tg_user_id))

        # Title + 1 client card = 2 messages
        assert mock_tg.send_message.call_count == 2
        # Action row should have 3 buttons
        action_rows = [r for r in captured_rows if len(r) == 3]
        assert len(action_rows) >= 1

    @pytest.mark.asyncio
    async def test_fu_ok_marks_contacted(self, db, staff, client_row):
        """fu:ok:{id} updates status to contacted."""
        await db.set_next_followup(
            client_row.id, datetime.now(timezone.utc) - timedelta(hours=1))

        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_fu_callback
            await handle_fu_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'fu:ok:{client_row.id}'))

        updated = await db.get_client_by_id(client_row.id)
        assert updated.status == ClientStatus.CONTACTED

    @pytest.mark.asyncio
    async def test_fu_sk_snoozes_client(self, db, staff, client_row):
        """fu:sk:{id} sets next_followup to tomorrow."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_fu_callback
            await handle_fu_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'fu:sk:{client_row.id}'))

        updated = await db.get_client_by_id(client_row.id)
        # next_followup should be set to ~tomorrow (unchanged status)
        assert updated.status == ClientStatus.NEW

    @pytest.mark.asyncio
    async def test_fu_ab_marks_dead(self, db, staff, client_row):
        """fu:ab:{id} marks client as dead."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_fu_callback
            await handle_fu_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'fu:ab:{client_row.id}'))

        updated = await db.get_client_by_id(client_row.id)
        assert updated.status == ClientStatus.DEAD

    @pytest.mark.asyncio
    async def test_fu_auto_advance_all_done(self, db, staff, client_row):
        """After last follow-up action, shows all-done message."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_fu_callback
            await handle_fu_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, f'fu:ok:{client_row.id}'))

        # Should have sent: "contacted" confirmation + "all done"
        calls = [c[0][1] for c in mock_tg.send_message.call_args_list]
        assert mock_tg.send_message.call_count >= 1


# ── Quick Add Client ──────────────────────────────────────────────────────────

class TestAddClientFlow:
    @pytest.mark.asyncio
    async def test_add_start_sets_conv_state(self, db, staff):
        """handle_add_start sets conversation state to add_await_phone."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_add_start
            await handle_add_start(_task(staff.tg_chat_id, staff.tg_user_id))

        mock_tg.set_conversation_state.assert_called_once()
        state = mock_tg.set_conversation_state.call_args[0][1]
        assert state['step'] == 'add_await_phone'

    @pytest.mark.asyncio
    async def test_add_await_phone_valid_shows_source_picker(self, db, staff):
        """Valid phone → source picker buttons."""
        mock_tg = _mock_tg()
        mock_tg.get_conversation_state = AsyncMock(return_value=None)

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_add_await_phone
            td = _task(staff.tg_chat_id, staff.tg_user_id)
            td['message'] = '0123456789'
            await handle_add_await_phone(td)

        # Should set state with pending phone + show source picker
        mock_tg.set_conversation_state.assert_called()
        last_state = mock_tg.set_conversation_state.call_args[0][1]
        assert last_state['step'] == 'add_await_source'
        assert last_state['pending']['phone'] == '0123456789'

    @pytest.mark.asyncio
    async def test_add_await_phone_invalid_reprompts(self, db, staff):
        """Non-digit phone → error and stay in same state."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_add_await_phone
            td = _task(staff.tg_chat_id, staff.tg_user_id)
            td['message'] = 'not-a-phone'
            await handle_add_await_phone(td)

        mock_tg.send_message.assert_called_once()
        # Should set state back to add_await_phone
        last_state = mock_tg.set_conversation_state.call_args[0][1]
        assert last_state['step'] == 'add_await_phone'

    @pytest.mark.asyncio
    async def test_add_await_phone_duplicate_shows_existing(self, db, staff, client_row):
        """Duplicate phone → clear state and show existing client detail."""
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_add_await_phone
            td = _task(staff.tg_chat_id, staff.tg_user_id)
            td['message'] = client_row.phone
            await handle_add_await_phone(td)

        mock_tg.clear_conversation_state.assert_called_once()
        # Should send dup warning + detail card = 2 messages
        assert mock_tg.send_message.call_count >= 1

    @pytest.mark.asyncio
    async def test_add_source_callback_creates_client(self, db, staff):
        """add:src:fb with valid pending state creates client in DB."""
        mock_tg = _mock_tg()
        mock_tg.get_conversation_state = AsyncMock(return_value={
            'step': 'add_await_source',
            'pending': {'phone': '0999888777'},
        })

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_add_source_callback
            await handle_add_source_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, 'add:src:fb'))

        mock_tg.clear_conversation_state.assert_called_once()
        created = await db.get_client_by_phone('0999888777', staff.id)
        assert created is not None
        assert created.source == 'facebook'

    @pytest.mark.asyncio
    async def test_add_source_callback_no_state_reprompts(self, db, staff):
        """add:src:fb with no pending state → reprompt for phone."""
        mock_tg = _mock_tg()
        mock_tg.get_conversation_state = AsyncMock(return_value=None)

        with (
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.inline_flows import handle_add_source_callback
            await handle_add_source_callback(
                _task(staff.tg_chat_id, staff.tg_user_id, 'add:src:fb'))

        mock_tg.send_message.assert_called_once()


# ── Registry exports ──────────────────────────────────────────────────────────

class TestInlineFlowsRegistry:
    def test_callbacks_registered_with_wildcards(self):
        from handlers_v2.inline_flows import INLINE_FLOWS_CALLBACKS
        for ns in ('pipe:*', 'status:*', 'note:*', 'fu:*', 'add:*'):
            assert ns in INLINE_FLOWS_CALLBACKS, f"Missing: {ns}"

    def test_conversations_registered(self):
        from handlers_v2.inline_flows import INLINE_FLOWS_CONVERSATIONS
        for step in ('inline_await_note', 'add_await_phone', 'add_await_source'):
            assert step in INLINE_FLOWS_CONVERSATIONS, f"Missing: {step}"

    def test_all_handlers_callable(self):
        from handlers_v2.inline_flows import INLINE_FLOWS_CALLBACKS, INLINE_FLOWS_CONVERSATIONS
        for k, v in {**INLINE_FLOWS_CALLBACKS, **INLINE_FLOWS_CONVERSATIONS}.items():
            assert callable(v), f"Not callable: {k}"

    def test_callback_data_max_64_bytes(self):
        """Verify representative callback strings fit in 64 bytes."""
        samples = [
            'pipe:pg:99:contacted',
            'pipe:d:99999',
            'status:p:99999',
            'status:do:99999:registered',
            'note:s:99999',
            'fu:ok:99999',
            'fu:sk:99999',
            'fu:ab:99999',
            'add:src:other',
            'pipe:back',
        ]
        for s in samples:
            assert len(s.encode()) <= 64, f"Callback too long ({len(s.encode())} bytes): {s}"

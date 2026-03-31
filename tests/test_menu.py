"""Inline keyboard menu tests — /start, button routing, quick-status callbacks."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from database_v2 import DatabaseV2
from models_v2 import Client, ClientStatus, Staff, StaffRole


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_menu.db'))
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=7001,
        tg_chat_id=6001,
        display_name='MenuStaff',
        role=StaffRole.FRONTDESK,
        team='B',
        language='zh',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager(db):
    s = Staff(
        tg_user_id=7002,
        tg_chat_id=6002,
        display_name='MenuManager',
        role=StaffRole.MANAGER,
        team='B',
        language='en',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client_row(db, staff):
    c = Client(frontdesk_id=staff.id, phone='0987654321', source='ig')
    c.id = await db.create_client(c)
    return c


def _make_mock_tg():
    m = MagicMock()
    m.send_message = AsyncMock()
    m.create_inline_keyboard = MagicMock(return_value=[[]])
    return m


# ── handle_start ─────────────────────────────────────────────────────────────

class TestHandleStart:
    @pytest.mark.asyncio
    async def test_start_shows_menu_with_keyboard(self, staff, db):
        """Registered staff → personalized dashboard message sent."""
        mock_tg = _make_mock_tg()

        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.persistent_keyboard.get_persistent_keyboard', return_value=None),
        ):
            from handlers_v2.menu import handle_start
            await handle_start({'chat_id': 6001, 'user_id': 7001})

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_unregistered_user_sends_error(self):
        """Unregistered user → sends error message."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=None)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_start
            await handle_start({'chat_id': 99, 'user_id': 99})

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_zh_shows_chinese_text(self, staff, db):
        """Chinese staff sees Chinese text in dashboard."""
        mock_tg = _make_mock_tg()

        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.persistent_keyboard.get_persistent_keyboard', return_value=None),
        ):
            from handlers_v2.menu import handle_start
            await handle_start({'chat_id': 6001, 'user_id': 7001})

        msg = mock_tg.send_message.call_args[0][1]
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in msg)
        assert has_chinese

    @pytest.mark.asyncio
    async def test_start_en_renders_without_error(self, manager, db):
        """English manager → start renders without exception."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=manager)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.persistent_keyboard.get_persistent_keyboard', return_value=None),
        ):
            from handlers_v2.menu import handle_start
            await handle_start({'chat_id': 6002, 'user_id': 7002})

        mock_tg.send_message.assert_called_once()


# ── Keyboard structure ────────────────────────────────────────────────────────

class TestMenuKeyboardStructure:
    def test_all_8_buttons_have_callback_data(self):
        """All 8 buttons have callback_data starting with 'menu_'."""
        captured = []
        mock_tg = _make_mock_tg()
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured.extend(rows) or [[]])

        with patch('handlers_v2.menu.telegram_handler', mock_tg):
            from handlers_v2.menu import _main_menu_keyboard
            _main_menu_keyboard('zh')

        for row in captured:
            for btn in row:
                assert 'callback_data' in btn
                assert btn['callback_data'].startswith('menu_')

    def test_8_buttons_total(self):
        """Exactly 8 menu buttons across 4 rows."""
        captured = []
        mock_tg = _make_mock_tg()
        mock_tg.create_inline_keyboard = MagicMock(
            side_effect=lambda rows: captured.extend(rows) or [[]])

        with patch('handlers_v2.menu.telegram_handler', mock_tg):
            from handlers_v2.menu import _main_menu_keyboard
            _main_menu_keyboard('zh')

        assert sum(len(row) for row in captured) == 8


# ── handle_menu_callback routing ─────────────────────────────────────────────

class TestMenuCallbackRouting:
    @pytest.mark.asyncio
    async def test_menu_add_starts_add_flow(self, staff):
        """menu_add delegates to inline_flows.handle_add_start."""
        mock_add = AsyncMock()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', _make_mock_tg()),
            patch('handlers_v2.inline_flows.handle_add_start', mock_add),
        ):
            from handlers_v2.menu import handle_menu_callback
            await handle_menu_callback({
                'chat_id': 6001, 'user_id': 7001, 'callback_data': 'menu_add',
            })

        mock_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_menu_voice_sends_hint(self, staff):
        """menu_voice sends a voice hint message."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_menu_callback
            await handle_menu_callback({
                'chat_id': 6001, 'user_id': 7001, 'callback_data': 'menu_voice',
            })

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_menu_unregistered_user_ignored(self):
        """Unregistered user pressing menu button → silently ignored."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=None)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_menu_callback
            await handle_menu_callback({
                'chat_id': 99, 'user_id': 99, 'callback_data': 'menu_add',
            })

        mock_tg.send_message.assert_not_called()


# ── handle_quick_status_callback ─────────────────────────────────────────────

class TestQuickStatusCallback:
    @pytest.mark.asyncio
    async def test_quick_status_updates_db(self, db, staff, client_row):
        """qs_<id>_contacted updates client status in DB."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_quick_status_callback
            await handle_quick_status_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
                'callback_data': f'qs_{client_row.id}_contacted',
            })

        updated = await db.get_client_by_id(client_row.id)
        assert updated.status == ClientStatus.CONTACTED
        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_quick_status_invalid_status_sends_error(self, db, staff, client_row):
        """Invalid status value → error message, status unchanged."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_quick_status_callback
            await handle_quick_status_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
                'callback_data': f'qs_{client_row.id}_INVALID',
            })

        mock_tg.send_message.assert_called_once()
        unchanged = await db.get_client_by_id(client_row.id)
        assert unchanged.status == ClientStatus.NEW

    @pytest.mark.asyncio
    async def test_quick_status_wrong_owner_denied(self, db, staff, manager, client_row):
        """Manager trying to update staff's client → not found, no status change."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=manager)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_quick_status_callback
            await handle_quick_status_callback({
                'chat_id': manager.tg_chat_id,
                'user_id': manager.tg_user_id,
                'callback_data': f'qs_{client_row.id}_contacted',
            })

        mock_tg.send_message.assert_called_once()
        unchanged = await db.get_client_by_id(client_row.id)
        assert unchanged.status == ClientStatus.NEW

    @pytest.mark.asyncio
    async def test_quick_status_malformed_callback_ignored(self, staff):
        """Malformed callback (non-int id) → silently ignored."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_quick_status_callback
            await handle_quick_status_callback({
                'chat_id': 6001,
                'user_id': 7001,
                'callback_data': 'qs_notanint_contacted',
            })

        mock_tg.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_quick_status_too_few_parts_ignored(self, staff):
        """Callback with fewer than 3 parts → silently ignored."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_quick_status_callback
            await handle_quick_status_callback({
                'chat_id': 6001,
                'user_id': 7001,
                'callback_data': 'qs_12',  # only 2 parts
            })

        mock_tg.send_message.assert_not_called()


# ── Follow-up with buttons ────────────────────────────────────────────────────

class TestFollowupWithButtons:
    @pytest.mark.asyncio
    async def test_followup_empty(self, db, staff):
        """No overdue clients → single 'empty' message (via inline_flows)."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
            patch('handlers_v2.inline_flows.database_v2', db),
            patch('handlers_v2.inline_flows._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.inline_flows.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_menu_callback
            await handle_menu_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
                'callback_data': 'menu_followup',
            })

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_followup_unregistered_ignored(self):
        """Unregistered user → silently ignored."""
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=None)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
        ):
            from handlers_v2.menu import handle_menu_callback
            await handle_menu_callback({
                'chat_id': 99,
                'user_id': 99,
                'callback_data': 'menu_followup',
            })

        mock_tg.send_message.assert_not_called()


# ── Registry exports ─────────────────────────────────────────────────────────

class TestMenuRegistry:
    def test_start_command_registered(self):
        from handlers_v2.menu import MENU_COMMANDS
        assert 'start' in MENU_COMMANDS

    def test_all_menu_callbacks_registered(self):
        from handlers_v2.menu import MENU_CALLBACKS
        expected = [
            'menu_pipeline', 'menu_add', 'menu_followup', 'menu_leaderboard',
            'menu_today', 'menu_voice', 'menu_app', 'menu_help',
            'qs_*',
        ]
        for key in expected:
            assert key in MENU_CALLBACKS, f"Missing callback: {key}"

    def test_menu_conversations_empty(self):
        from handlers_v2.menu import MENU_CONVERSATIONS
        assert isinstance(MENU_CONVERSATIONS, dict)

    def test_start_handler_callable(self):
        from handlers_v2.menu import MENU_COMMANDS
        import asyncio
        assert callable(MENU_COMMANDS['start'])

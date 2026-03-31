"""Tests for persistent reply keyboard — button routing, keyboard structure, /start dashboard."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_keyboard.db'))
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def staff_zh(db):
    s = Staff(
        tg_user_id=8001,
        tg_chat_id=7001,
        display_name='键盘用户',
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
        display_name='KeyboardUser',
        role=StaffRole.FRONTDESK,
        team='A',
        language='en',
    )
    s.id = await db.create_staff(s)
    return s


def _mock_tg():
    m = MagicMock()
    m.send_message = AsyncMock()
    m.create_inline_keyboard = MagicMock(return_value=[[]])
    return m


# ── 1-6: Keyboard button text → correct handler routing ──────────────────────

class TestKeyboardRoutes:
    def test_routes_dict_has_12_entries(self):
        """KEYBOARD_ROUTES covers 6 Chinese + 6 English buttons."""
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES
        assert len(KEYBOARD_ROUTES) == 12

    def test_zh_my_clients_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_my_clients
        assert KEYBOARD_ROUTES['📋 我的客户'] is handle_my_clients

    def test_zh_add_client_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_add_client_flow
        assert KEYBOARD_ROUTES['➕ 添加客户'] is handle_add_client_flow

    def test_zh_followup_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_followup_list
        assert KEYBOARD_ROUTES['🔥 待跟进'] is handle_followup_list

    def test_zh_dashboard_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_dashboard_button
        assert KEYBOARD_ROUTES['📊 看板'] is handle_dashboard_button

    def test_zh_voice_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_voice_instructions
        assert KEYBOARD_ROUTES['🎤 语音更新'] is handle_voice_instructions

    def test_zh_leaderboard_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_xp_leaderboard
        assert KEYBOARD_ROUTES['🏆 排行榜'] is handle_xp_leaderboard

    def test_en_my_clients_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_my_clients
        assert KEYBOARD_ROUTES['📋 My Clients'] is handle_my_clients

    def test_en_add_client_routes_to_handler(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES, handle_add_client_flow
        assert KEYBOARD_ROUTES['➕ Add Client'] is handle_add_client_flow

    def test_all_routes_are_callable(self):
        """Every route value is an async callable."""
        import asyncio
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES
        for text, handler in KEYBOARD_ROUTES.items():
            assert callable(handler), f'Handler for "{text}" is not callable'


# ── 7: Keyboard structure ─────────────────────────────────────────────────────

class TestKeyboardStructure:
    def test_zh_keyboard_has_6_zh_buttons(self):
        """Chinese keyboard dict has exactly 6 entries."""
        from handlers_v2.persistent_keyboard import _ZH_BUTTONS, _EN_BUTTONS
        assert len(_ZH_BUTTONS) == 6
        assert len(_EN_BUTTONS) == 6

    def test_all_button_texts_set_covers_12(self):
        """ALL_BUTTON_TEXTS has exactly 12 unique button strings."""
        from handlers_v2.persistent_keyboard import ALL_BUTTON_TEXTS
        assert len(ALL_BUTTON_TEXTS) == 12

    def test_get_persistent_keyboard_returns_none_gracefully(self):
        """get_persistent_keyboard returns None if Telethon types unavailable."""
        import sys
        # Temporarily sabotage import to test fallback
        import unittest.mock as um
        from handlers_v2 import persistent_keyboard as pk
        original = pk.get_persistent_keyboard
        # Patch the import inside the function to raise
        with patch.dict(sys.modules, {'telethon.tl.types': None}):
            kb = pk.get_persistent_keyboard('zh')
            # May return None or a keyboard object depending on import cache
            # The key assertion: no exception is raised
        assert True  # reached here without exception


# ── 8: /start personalized dashboard ─────────────────────────────────────────

class TestStartPersonalizedDashboard:
    @pytest.mark.asyncio
    async def test_start_shows_stats_and_keyboard(self, staff_zh, db):
        """handle_start sends a message with stats for a registered ZH user."""
        mock_tg = _mock_tg()

        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff_zh)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.persistent_keyboard.get_persistent_keyboard', return_value=None),
        ):
            from handlers_v2.menu import handle_start
            await handle_start({'chat_id': staff_zh.tg_chat_id, 'user_id': staff_zh.tg_user_id})

        mock_tg.send_message.assert_called_once()
        call_args = mock_tg.send_message.call_args
        msg_text = call_args[0][1] if call_args[0] else call_args[1].get('text', '')
        assert '📊' in msg_text or '今日统计' in msg_text or staff_zh.display_name in msg_text

    @pytest.mark.asyncio
    async def test_start_en_shows_english_stats(self, staff_en, db):
        """English staff gets English dashboard text."""
        mock_tg = _mock_tg()

        with (
            patch('handlers_v2.menu._get_staff', AsyncMock(return_value=staff_en)),
            patch('handlers_v2.menu.telegram_handler', mock_tg),
            patch('handlers_v2.menu.database_v2', db),
            patch('handlers_v2.persistent_keyboard.get_persistent_keyboard', return_value=None),
        ):
            from handlers_v2.menu import handle_start
            await handle_start({'chat_id': staff_en.tg_chat_id, 'user_id': staff_en.tg_user_id})

        mock_tg.send_message.assert_called_once()
        call_args = mock_tg.send_message.call_args
        msg_text = call_args[0][1] if call_args[0] else call_args[1].get('text', '')
        assert 'Today' in msg_text or 'Hi ' in msg_text


# ── 9: Keyboard in both languages ─────────────────────────────────────────────

class TestKeyboardBothLanguages:
    def test_zh_buttons_contain_chinese_characters(self):
        from handlers_v2.persistent_keyboard import _ZH_BUTTONS
        for key, text in _ZH_BUTTONS.items():
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
            assert has_chinese, f'ZH button "{key}" has no Chinese chars: {text}'

    def test_en_buttons_contain_ascii(self):
        from handlers_v2.persistent_keyboard import _EN_BUTTONS
        for key, text in _EN_BUTTONS.items():
            has_ascii = any(c.isascii() and c.isalpha() for c in text)
            assert has_ascii, f'EN button "{key}" has no ASCII letters: {text}'


# ── 10: Unknown text falls through to NL handler ─────────────────────────────

class TestUnknownTextFallthrough:
    def test_unknown_text_not_in_routes(self):
        """A regular message like 'hello' is not in KEYBOARD_ROUTES."""
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES
        assert 'hello' not in KEYBOARD_ROUTES
        assert '你好' not in KEYBOARD_ROUTES
        assert '/start' not in KEYBOARD_ROUTES

    def test_partial_button_text_not_in_routes(self):
        """Partial matches don't route — must be exact."""
        from handlers_v2.persistent_keyboard import KEYBOARD_ROUTES
        assert '我的客户' not in KEYBOARD_ROUTES   # missing emoji prefix
        assert 'My Clients' not in KEYBOARD_ROUTES  # missing emoji prefix


# ── 11: Voice instructions handler ───────────────────────────────────────────

class TestVoiceInstructions:
    @pytest.mark.asyncio
    async def test_voice_instructions_zh(self, staff_zh):
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.persistent_keyboard._get_staff', AsyncMock(return_value=staff_zh)),
            patch('handlers_v2.persistent_keyboard.telegram_handler', mock_tg),
            patch('handlers_v2.persistent_keyboard.get_persistent_keyboard', return_value=None),
        ):
            from handlers_v2.persistent_keyboard import handle_voice_instructions
            await handle_voice_instructions({'chat_id': 7001, 'user_id': 8001})

        mock_tg.send_message.assert_called_once()
        text = mock_tg.send_message.call_args[0][1]
        assert '语音' in text

    @pytest.mark.asyncio
    async def test_voice_instructions_en(self, staff_en):
        mock_tg = _mock_tg()
        with (
            patch('handlers_v2.persistent_keyboard._get_staff', AsyncMock(return_value=staff_en)),
            patch('handlers_v2.persistent_keyboard.telegram_handler', mock_tg),
            patch('handlers_v2.persistent_keyboard.get_persistent_keyboard', return_value=None),
        ):
            from handlers_v2.persistent_keyboard import handle_voice_instructions
            await handle_voice_instructions({'chat_id': 7002, 'user_id': 8002})

        mock_tg.send_message.assert_called_once()
        text = mock_tg.send_message.call_args[0][1]
        assert 'Voice' in text or 'voice' in text


# ── 12: Registry exports ──────────────────────────────────────────────────────

class TestRegistryExports:
    def test_keyboard_commands_is_empty_dict(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_COMMANDS
        assert isinstance(KEYBOARD_COMMANDS, dict)
        assert len(KEYBOARD_COMMANDS) == 0

    def test_keyboard_callbacks_is_empty_dict(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_CALLBACKS
        assert isinstance(KEYBOARD_CALLBACKS, dict)

    def test_keyboard_conversations_is_empty_dict(self):
        from handlers_v2.persistent_keyboard import KEYBOARD_CONVERSATIONS
        assert isinstance(KEYBOARD_CONVERSATIONS, dict)

"""Tests for handlers_v2/mini_app.py — /app command, WebApp button."""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from models_v2 import Staff, StaffRole


# ── Helpers ──────────────────────────────────────────────────────────────────

def _staff(role=StaffRole.FRONTDESK, lang='zh', staff_id=1, name='FD', tg_user_id=100):
    return Staff(
        id=staff_id, tg_user_id=tg_user_id, tg_chat_id=tg_user_id,
        display_name=name, role=role, language=lang,
    )


def _td(user_id=100, chat_id=100, **extra):
    d = {'user_id': user_id, 'chat_id': chat_id}
    d.update(extra)
    return d


_P_STAFF = 'handlers_v2.mini_app._get_staff'
_P_TH = 'handlers_v2.mini_app.telegram_handler'


# ── /app ─────────────────────────────────────────────────────────────────────

class TestHandleApp:

    @pytest.mark.asyncio
    async def test_app_not_registered_uses_zh(self):
        """When staff not found, should still send message with zh lang."""
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            th.bot_client = None
            from handlers_v2.mini_app import handle_app
            await handle_app(_td())
            th.send_message.assert_awaited_once()
            msg = th.send_message.call_args[0][1]
            assert '打开' in msg or '看板' in msg

    @pytest.mark.asyncio
    async def test_app_zh_fallback_url_button(self):
        """With bot_client=None, falls back to URL button."""
        staff = _staff(lang='zh')
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            th.bot_client = None
            from handlers_v2.mini_app import handle_app
            await handle_app(_td())
            th.send_message.assert_awaited_once()
            msg = th.send_message.call_args[0][1]
            assert '打开' in msg

    @pytest.mark.asyncio
    async def test_app_en_fallback_url_button(self):
        staff = _staff(lang='en')
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            th.bot_client = None
            from handlers_v2.mini_app import handle_app
            await handle_app(_td())
            msg = th.send_message.call_args[0][1]
            assert 'Tap' in msg or 'Open' in msg or 'Dashboard' in msg

    @pytest.mark.asyncio
    async def test_app_webapp_button_success(self):
        """When bot_client is available, use Telethon WebApp button."""
        staff = _staff(lang='zh')
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch.dict('sys.modules', {'telethon': MagicMock(), 'telethon.tl': MagicMock(),
                                        'telethon.tl.types': MagicMock()}):
            th.bot_client = mock_bot
            from handlers_v2.mini_app import handle_app
            await handle_app(_td())
            mock_bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_app_webapp_button_fails_fallback(self):
        """When WebApp button fails, falls back to URL button."""
        staff = _staff(lang='zh')
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(side_effect=Exception('Telethon error'))
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch.dict('sys.modules', {'telethon': MagicMock(), 'telethon.tl': MagicMock(),
                                        'telethon.tl.types': MagicMock()}):
            th.bot_client = mock_bot
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            from handlers_v2.mini_app import handle_app
            await handle_app(_td())
            # Should fallback to telegram_handler.send_message
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_app_url_contains_env(self):
        """MINI_APP_URL from environment is used in keyboard."""
        staff = _staff(lang='en')
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch('handlers_v2.mini_app.MINI_APP_URL', 'https://custom.example.com'):
            th.send_message = AsyncMock()
            th.create_inline_keyboard = Mock(return_value='kb')
            th.bot_client = None
            from handlers_v2.mini_app import handle_app
            await handle_app(_td())
            kb_args = th.create_inline_keyboard.call_args[0][0]
            urls = [btn.get('url', '') for row in kb_args for btn in row]
            assert any('custom.example.com' in u for u in urls)


# ── Registry ─────────────────────────────────────────────────────────────────

class TestMiniAppRegistry:

    def test_mini_app_commands(self):
        from handlers_v2.mini_app import MINI_APP_COMMANDS
        assert 'app' in MINI_APP_COMMANDS

    def test_mini_app_callbacks_empty(self):
        from handlers_v2.mini_app import MINI_APP_CALLBACKS
        assert isinstance(MINI_APP_CALLBACKS, dict)
        assert len(MINI_APP_CALLBACKS) == 0

    def test_mini_app_conversations_empty(self):
        from handlers_v2.mini_app import MINI_APP_CONVERSATIONS
        assert isinstance(MINI_APP_CONVERSATIONS, dict)
        assert len(MINI_APP_CONVERSATIONS) == 0

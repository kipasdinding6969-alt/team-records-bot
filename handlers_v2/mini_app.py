"""Mini App handler — /app command sends a WebApp button to the user."""
import logging
import os
from pathlib import Path
from typing import Any, Dict

from telegram_handler import telegram_handler
from database_v2 import database_v2
from handlers_v2 import get_staff as _get_staff
from i18n import t

logger = logging.getLogger(__name__)

MINI_APP_URL = os.getenv('MINI_APP_URL', 'https://sem-rush.com/app/')


async def handle_app(task_data: Dict[str, Any]):
    """/app — send Mini App WebApp button."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    lang = staff.language if staff else 'zh'

    # Try to send a WebApp button using raw Telethon types.
    # Falls back to a plain URL button if bot_client is unavailable.
    bot_client = telegram_handler.bot_client
    if bot_client is not None:
        try:
            from telethon.tl.types import (
                KeyboardButtonWebView,
                ReplyInlineMarkup,
                KeyboardButtonRow,
            )
            markup = ReplyInlineMarkup(rows=[
                KeyboardButtonRow(buttons=[
                    KeyboardButtonWebView(
                        text='📊 打开看板' if lang == 'zh' else '📊 Open Dashboard',
                        url=MINI_APP_URL,
                    )
                ])
            ])
            msg = '📊 点击下方按钮打开可视化看板' if lang == 'zh' else '📊 Tap to open the visual pipeline dashboard'
            await bot_client.send_message(chat_id, msg, buttons=markup)
            return
        except Exception as e:
            logger.warning(f'WebApp button failed, falling back to URL button: {e}')

    # Fallback: plain URL button via telegram_handler
    keyboard = telegram_handler.create_inline_keyboard([[
        {'text': '📊 打开看板' if lang == 'zh' else '📊 Open Dashboard', 'url': MINI_APP_URL}
    ]])
    msg = '📊 点击下方按钮打开可视化看板' if lang == 'zh' else '📊 Tap to open the visual pipeline dashboard'
    await telegram_handler.send_message(chat_id, msg, reply_markup=keyboard)


MINI_APP_COMMANDS = {
    'app': handle_app,
}

MINI_APP_CALLBACKS: Dict[str, Any] = {}
MINI_APP_CONVERSATIONS: Dict[str, Any] = {}

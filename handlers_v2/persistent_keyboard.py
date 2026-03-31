"""Persistent reply keyboard — always-visible 6-button tray for frontdesk workers.

Buttons send plain text messages. This module:
  1. Defines the keyboard layout (get_persistent_keyboard)
  2. Maps button texts to handler functions (KEYBOARD_ROUTES)
  3. Provides thin handler wrappers that delegate to existing handlers
"""
import logging
from typing import Any, Dict

from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

# Button texts (must match exactly what Telegram sends back)
_ZH_BUTTONS = {
    'my_clients':    '📋 我的客户',
    'add_client':    '➕ 添加客户',
    'followup':      '🔥 待跟进',
    'dashboard':     '📊 看板',
    'voice':         '🎤 语音更新',
    'leaderboard':   '🏆 排行榜',
}

_EN_BUTTONS = {
    'my_clients':    '📋 My Clients',
    'add_client':    '➕ Add Client',
    'followup':      '🔥 Follow-up',
    'dashboard':     '📊 Dashboard',
    'voice':         '🎤 Voice Update',
    'leaderboard':   '🏆 Leaderboard',
}

# All button texts across both languages (for routing)
ALL_BUTTON_TEXTS = set(_ZH_BUTTONS.values()) | set(_EN_BUTTONS.values())


def get_persistent_keyboard(lang: str = 'zh'):
    """Return the always-visible ReplyKeyboardMarkup for DM chats."""
    try:
        from telethon.tl.types import ReplyKeyboardMarkup, KeyboardButtonRow, KeyboardButton
        if lang == 'zh':
            b = _ZH_BUTTONS
        else:
            b = _EN_BUTTONS
        return ReplyKeyboardMarkup(
            rows=[
                KeyboardButtonRow(buttons=[KeyboardButton(text=b['my_clients']), KeyboardButton(text=b['add_client'])]),
                KeyboardButtonRow(buttons=[KeyboardButton(text=b['followup']),   KeyboardButton(text=b['dashboard'])]),
                KeyboardButtonRow(buttons=[KeyboardButton(text=b['voice']),      KeyboardButton(text=b['leaderboard'])]),
            ],
            resize=True,
            single_use=False,
            persistent=True,
        )
    except Exception as e:
        logger.warning(f'get_persistent_keyboard failed: {e}')
        return None


# ── Button handlers ──────────────────────────────────────────────────────────

async def handle_my_clients(task_data: Dict[str, Any]):
    """📋 我的客户 / My Clients — show pipeline view."""
    from handlers_v2.inline_flows import handle_pipe_callback
    td = dict(task_data)
    td['callback_data'] = 'pipe:pg:0:all'
    await handle_pipe_callback(td)


async def handle_add_client_flow(task_data: Dict[str, Any]):
    """➕ 添加客户 / Add Client — start add flow."""
    from handlers_v2.inline_flows import handle_add_start
    await handle_add_start(task_data)


async def handle_followup_list(task_data: Dict[str, Any]):
    """🔥 待跟进 / Follow-up — show overdue follow-ups."""
    from handlers_v2.inline_flows import handle_fu_start
    await handle_fu_start(task_data)


async def handle_dashboard_button(task_data: Dict[str, Any]):
    """📊 看板 / Dashboard — open Mini App."""
    from handlers_v2.mini_app import handle_app
    await handle_app(task_data)


async def handle_voice_instructions(task_data: Dict[str, Any]):
    """🎤 语音更新 / Voice Update — show voice instructions."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    lang = staff.language if staff else 'zh'

    if lang == 'zh':
        msg = (
            '🎤 语音更新说明\n\n'
            '发送语音消息，说出客户名字和更新内容。\n'
            '例如："张伟，已联系，约好明天面谈"\n\n'
            '系统会自动识别并更新客户状态。'
        )
    else:
        msg = (
            '🎤 Voice Update\n\n'
            'Send a voice message with the client name and update.\n'
            'Example: "John Smith, contacted, meeting tomorrow"\n\n'
            'The bot will automatically update client status.'
        )

    kb = get_persistent_keyboard(lang)
    await telegram_handler.send_message(chat_id, msg, reply_markup=kb)


async def handle_xp_leaderboard(task_data: Dict[str, Any]):
    """🏆 排行榜 / Leaderboard — XP leaderboard."""
    from handlers_v2.gamification_v2 import handle_xp_leaderboard as _leaderboard
    await _leaderboard(task_data)


# ── Routing table ─────────────────────────────────────────────────────────────

KEYBOARD_ROUTES: Dict[str, Any] = {
    # Chinese
    '📋 我的客户': handle_my_clients,
    '➕ 添加客户': handle_add_client_flow,
    '🔥 待跟进':   handle_followup_list,
    '📊 看板':     handle_dashboard_button,
    '🎤 语音更新': handle_voice_instructions,
    '🏆 排行榜':   handle_xp_leaderboard,
    # English
    '📋 My Clients':   handle_my_clients,
    '➕ Add Client':   handle_add_client_flow,
    '🔥 Follow-up':    handle_followup_list,
    '📊 Dashboard':    handle_dashboard_button,
    '🎤 Voice Update': handle_voice_instructions,
    '🏆 Leaderboard':  handle_xp_leaderboard,
}


# ── Registry exports ──────────────────────────────────────────────────────────

KEYBOARD_COMMANDS: dict = {}
KEYBOARD_CALLBACKS: dict = {}
KEYBOARD_CONVERSATIONS: dict = {}

"""Inline keyboard main menu — zero-typing UX for frontdesk workers.

/start → 8-button grid:
  Row 1: [📊 我的管道]  [➕ 新客户]
  Row 2: [🔔 待跟进]   [🏆 排行榜]
  Row 3: [📈 今日统计]  [🎤 语音更新]
  Row 4: [📱 打开面板]  [❓ 帮助]

All actions are tap-based — no slash commands needed.
"""
import logging
from typing import Any, Dict

from database_v2 import database_v2
from models_v2 import ClientStatus
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)


def _main_menu_keyboard(lang: str):
    return telegram_handler.create_inline_keyboard([
        [
            {'text': t('menu_btn_pipeline', lang),  'callback_data': 'menu_pipeline'},
            {'text': t('menu_btn_add', lang),        'callback_data': 'menu_add'},
        ],
        [
            {'text': t('menu_btn_followup', lang),   'callback_data': 'menu_followup'},
            {'text': t('menu_btn_leaderboard', lang), 'callback_data': 'menu_leaderboard'},
        ],
        [
            {'text': t('menu_btn_today', lang),      'callback_data': 'menu_today'},
            {'text': t('menu_btn_voice', lang),      'callback_data': 'menu_voice'},
        ],
        [
            {'text': t('menu_btn_app', lang),        'callback_data': 'menu_app'},
            {'text': t('menu_btn_help', lang),       'callback_data': 'menu_help'},
        ],
    ])


async def handle_start(task_data: Dict[str, Any]):
    """/start — show the visual main menu."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    keyboard = _main_menu_keyboard(lang)
    msg = t('main_menu_title', lang) + '\n' + t('main_menu_select', lang)
    await telegram_handler.send_message(chat_id, msg, parse_mode='markdown',
                                        reply_markup=keyboard)


async def handle_menu_callback(task_data: Dict[str, Any]):
    """Route menu_* callbacks to the appropriate handler."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language

    if callback == 'menu_pipeline':
        from handlers_v2.inline_flows import handle_pipe_callback
        task_data['callback_data'] = 'pipe:pg:0:all'
        await handle_pipe_callback(task_data)

    elif callback == 'menu_add':
        from handlers_v2.inline_flows import handle_add_start
        await handle_add_start(task_data)

    elif callback == 'menu_followup':
        from handlers_v2.inline_flows import handle_fu_start
        await handle_fu_start(task_data)

    elif callback == 'menu_leaderboard':
        from handlers_v2.gamification import handle_leaderboard
        await handle_leaderboard(task_data)

    elif callback == 'menu_today':
        from handlers_v2.pipeline import handle_today
        await handle_today(task_data)

    elif callback == 'menu_voice':
        voice_hint = (
            '🎤 发送语音消息即可更新状态！\n'
            'Send a voice message to update client status.'
        ) if lang == 'zh' else (
            '🎤 Send a voice message to update client status!'
        )
        await telegram_handler.send_message(chat_id, voice_hint)

    elif callback == 'menu_app':
        from handlers_v2.mini_app import handle_app
        await handle_app(task_data)

    elif callback == 'menu_help':
        title = t('help_title', lang)
        body = t('help_body', lang)
        kb = telegram_handler.create_inline_keyboard([
            [{'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'}],
        ])
        await telegram_handler.send_message(chat_id, f"{title}\n\n{body}", reply_markup=kb)


async def handle_quick_status_callback(task_data: Dict[str, Any]):
    """qs_<client_id>_<status> — legacy one-tap status update (kept for compat)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback_data = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language

    parts = callback_data.split('_', 2)
    if len(parts) < 3:
        return

    _, client_id_str, status_str = parts
    try:
        client_id = int(client_id_str)
    except ValueError:
        return

    try:
        new_status = ClientStatus(status_str)
    except ValueError:
        await telegram_handler.send_message(chat_id, t('err_invalid_status', lang))
        return

    client = await database_v2.get_client_by_id(client_id)
    if not client or client.frontdesk_id != staff.id:
        await telegram_handler.send_message(chat_id, t('err_not_found', lang))
        return

    await database_v2.update_client_status(client_id, new_status, staff.id)
    await telegram_handler.send_message(
        chat_id,
        t('quick_status_updated', lang, phone=client.phone, status=status_str),
    )
    logger.info(f"Quick status: staff {staff.display_name} → {client.phone} → {status_str}")


# ── Handler registries ──────────────────────────────────────────────────────

MENU_COMMANDS = {
    'start': handle_start,
}

MENU_CALLBACKS = {
    'menu_pipeline':    handle_menu_callback,
    'menu_add':         handle_menu_callback,
    'menu_followup':    handle_menu_callback,
    'menu_leaderboard': handle_menu_callback,
    'menu_today':       handle_menu_callback,
    'menu_voice':       handle_menu_callback,
    'menu_app':         handle_menu_callback,
    'menu_help':        handle_menu_callback,
    'qs_*':             handle_quick_status_callback,
}

MENU_CONVERSATIONS: dict = {}

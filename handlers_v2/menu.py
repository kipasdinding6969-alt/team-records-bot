"""Inline keyboard main menu and quick-status handlers.

/start → 8-button visual grid (replaces typing 36 slash commands).
Each button triggers the corresponding existing handler.
Follow-up view shows overdue clients with one-tap status buttons.
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
            {'text': t('menu_btn_pipeline', lang),     'callback_data': 'menu_pipeline'},
            {'text': t('menu_btn_add', lang),          'callback_data': 'menu_add'},
        ],
        [
            {'text': t('menu_btn_followup', lang),     'callback_data': 'menu_followup'},
            {'text': t('menu_btn_search', lang),       'callback_data': 'menu_search'},
        ],
        [
            {'text': t('menu_btn_leaderboard', lang),  'callback_data': 'menu_leaderboard'},
            {'text': t('menu_btn_hot', lang),          'callback_data': 'menu_hot'},
        ],
        [
            {'text': t('menu_btn_templates', lang),    'callback_data': 'menu_templates'},
            {'text': t('menu_btn_settings', lang),     'callback_data': 'menu_settings'},
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
    """Route menu_* callbacks to the appropriate existing handler."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language

    # Handlers that can be called directly with the same task_data shape
    if callback == 'menu_pipeline':
        from handlers_v2.pipeline import handle_pipeline
        await handle_pipeline(task_data)
    elif callback == 'menu_followup':
        await _handle_followup_with_buttons(task_data)
    elif callback == 'menu_leaderboard':
        from handlers_v2.gamification import handle_leaderboard
        await handle_leaderboard(task_data)
    elif callback == 'menu_hot':
        from handlers_v2.gamification import handle_hot_leads
        await handle_hot_leads(task_data)
    elif callback == 'menu_templates':
        from handlers_v2.gamification import handle_template
        task_data.setdefault('args', '')
        await handle_template(task_data)
    elif callback == 'menu_settings':
        from handlers_v2.pipeline import handle_me
        await handle_me(task_data)
    elif callback == 'menu_add':
        await telegram_handler.send_message(
            chat_id,
            t('menu_add_hint', lang),
        )
    elif callback == 'menu_search':
        await telegram_handler.send_message(
            chat_id,
            t('menu_search_hint', lang),
        )


async def _handle_followup_with_buttons(task_data: Dict[str, Any]):
    """Show overdue follow-up clients with quick-action buttons."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    clients = await database_v2.get_followup_due(staff.id)

    if not clients:
        await telegram_handler.send_message(chat_id, t('followup_empty', lang))
        return

    for client in clients[:10]:  # Cap at 10 to avoid message spam
        info = (
            f"📱 `{client.phone}` — **{client.status.value}**"
            + (f"\n🏷 #{client.account_id}" if client.account_id else '')
        )
        buttons = telegram_handler.create_inline_keyboard([[
            {'text': t('followup_btn_contacted', lang),
             'callback_data': f'qs_{client.id}_contacted'},
            {'text': t('followup_btn_snooze', lang),
             'callback_data': f'qs_{client.id}_scheduled'},
            {'text': t('followup_btn_dead', lang),
             'callback_data': f'qs_{client.id}_dead'},
        ]])
        await telegram_handler.send_message(chat_id, info, parse_mode='markdown',
                                            reply_markup=buttons)


async def handle_quick_status_callback(task_data: Dict[str, Any]):
    """qs_<client_id>_<status> — one-tap status update from follow-up list."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback_data = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language

    # callback_data format: qs_<id>_<status>
    parts = callback_data.split('_', 2)
    if len(parts) < 3:
        return

    _, client_id_str, status_str = parts
    try:
        client_id = int(client_id_str)
    except ValueError:
        return  # Malformed callback — not from our UI, ignore silently

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
    'menu_search':      handle_menu_callback,
    'menu_leaderboard': handle_menu_callback,
    'menu_hot':         handle_menu_callback,
    'menu_templates':   handle_menu_callback,
    'menu_settings':    handle_menu_callback,
    'qs_*':             handle_quick_status_callback,
}

MENU_CONVERSATIONS: dict = {}

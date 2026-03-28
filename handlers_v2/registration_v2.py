"""V2 registration handlers — /start, /profile, /lang, /setname."""
import logging
from typing import Any, Dict, Optional

from database_v2 import database_v2
from models_v2 import Staff, StaffRole
from i18n import t
from telegram_handler import telegram_handler

logger = logging.getLogger(__name__)

# In-memory pending-registration state keyed by tg_user_id.
# Stores partial data while the multi-step onboarding conversation is in progress.
_pending: Dict[int, Dict] = {}


async def handle_start_v2(task_data: Dict[str, Any]):
    """/start — welcome back or begin multi-step registration."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    username = task_data.get('username')
    first_name = task_data.get('first_name', '')

    existing = await database_v2.get_staff_by_tg_id(user_id)

    if existing:
        lang = existing.language
        msg = t('welcome_back', lang, name=existing.display_name, role=existing.role.value)
        await telegram_handler.send_message(chat_id, msg)
        return

    # Begin registration: ask for language first.
    _pending[user_id] = {
        'chat_id': chat_id,
        'tg_username': username,
        'first_name': first_name,
    }
    await telegram_handler.send_message(chat_id, t('reg_lang_prompt', 'zh'))
    await telegram_handler.set_conversation_state(user_id, {'step': 'reg_v2_lang'})


async def handle_reg_lang_step(task_data: Dict[str, Any]):
    """Conversation step: receive language choice (zh/en)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    text = (task_data.get('text') or '').strip().lower()

    if text not in ('zh', 'en'):
        await telegram_handler.send_message(chat_id, t('reg_lang_invalid', 'zh'))
        return

    state = _pending.get(user_id, {})
    state['lang'] = text
    _pending[user_id] = state

    await telegram_handler.send_message(chat_id, t('reg_role_prompt', text))
    await telegram_handler.set_conversation_state(user_id, {'step': 'reg_v2_role'})


async def handle_reg_role_step(task_data: Dict[str, Any]):
    """Conversation step: receive role choice (1/2/3 or frontdesk/manager/admin)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    text = (task_data.get('text') or '').strip().lower()

    role_map = {
        '1': StaffRole.FRONTDESK, 'frontdesk': StaffRole.FRONTDESK,
        '2': StaffRole.MANAGER,   'manager': StaffRole.MANAGER,
        '3': StaffRole.ADMIN,     'admin': StaffRole.ADMIN,
    }
    role = role_map.get(text)

    state = _pending.get(user_id, {})
    lang = state.get('lang', 'zh')

    if role is None:
        await telegram_handler.send_message(chat_id, t('reg_role_invalid', lang))
        return

    state['role'] = role
    _pending[user_id] = state

    await telegram_handler.send_message(chat_id, t('reg_name_prompt', lang))
    await telegram_handler.set_conversation_state(user_id, {'step': 'reg_v2_name'})


async def handle_reg_name_step(task_data: Dict[str, Any]):
    """Conversation step: receive display_name and complete registration."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    text = (task_data.get('text') or '').strip()

    state = _pending.pop(user_id, {})
    lang = state.get('lang', 'zh')

    display_name = text or state.get('first_name') or f'User{user_id}'

    new_staff = Staff(
        tg_user_id=user_id,
        tg_chat_id=chat_id,
        tg_username=state.get('tg_username'),
        display_name=display_name,
        role=state.get('role', StaffRole.FRONTDESK),
        language=lang,
    )
    staff_id = await database_v2.create_staff(new_staff)

    await telegram_handler.clear_conversation_state(user_id)
    msg = t('registered_v2', lang, name=display_name, id=staff_id)
    await telegram_handler.send_message(chat_id, msg)
    logger.info(f'New staff registered: {display_name} role={new_staff.role.value} (tg_id={user_id})')


async def handle_profile(task_data: Dict[str, Any]):
    """/profile — show own profile."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await database_v2.get_staff_by_tg_id(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    lines = [
        t('profile_title', lang),
        '',
        f'👤 {t("display_name_label", lang)}: {staff.display_name}',
        f'🎭 {t("role_label", lang)}: {staff.role.value}',
    ]
    if staff.team:
        lines.append(f'👥 {t("team_label", lang)}: {staff.team}')
    lines.append(f'🎯 {t("daily_target_label", lang)}: {staff.daily_target}')
    lines.append(f'🌐 {t("language_label", lang)}: {staff.language}')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_lang(task_data: Dict[str, Any]):
    """/lang <zh|en> — change display language."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = (task_data.get('args') or '').strip().lower()

    staff = await database_v2.get_staff_by_tg_id(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    if args not in ('zh', 'en'):
        await telegram_handler.send_message(chat_id, t('lang_usage', staff.language))
        return

    staff.language = args
    await database_v2.update_staff(staff)
    await telegram_handler.send_message(chat_id, t('lang_changed', args, lang=args))


async def handle_setname(task_data: Dict[str, Any]):
    """/setname <new name> — change display name."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = (task_data.get('args') or '').strip()

    staff = await database_v2.get_staff_by_tg_id(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    if not args:
        await telegram_handler.send_message(chat_id, t('setname_usage', lang))
        return

    old_name = staff.display_name
    staff.display_name = args
    await database_v2.update_staff(staff)
    await telegram_handler.send_message(chat_id, t('name_changed', lang, old=old_name, new=args))


REGISTRATION_V2_COMMANDS = {
    'start': handle_start_v2,
    'profile': handle_profile,
    'lang': handle_lang,
    'setname': handle_setname,
}

REGISTRATION_V2_CALLBACKS = {}

REGISTRATION_V2_CONVERSATIONS = {
    'reg_v2_lang': handle_reg_lang_step,
    'reg_v2_role': handle_reg_role_step,
    'reg_v2_name': handle_reg_name_step,
}

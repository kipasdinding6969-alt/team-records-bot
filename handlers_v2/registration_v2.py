"""V2 simplified registration — /start and /profile."""
import logging
from typing import Any, Dict

from database_v2 import database_v2
from models_v2 import Staff, StaffRole
from i18n import t
from telegram_handler import telegram_handler

logger = logging.getLogger(__name__)


async def handle_start_v2(task_data: Dict[str, Any]):
    """/start — register or show welcome."""
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

    # Auto-register with display_name from Telegram first_name
    display_name = first_name or f'User{user_id}'
    new_staff = Staff(
        tg_user_id=user_id,
        tg_chat_id=chat_id,
        tg_username=username,
        display_name=display_name,
        role=StaffRole.FRONTDESK,
        language='zh',
    )
    staff_id = await database_v2.create_staff(new_staff)

    msg = t('registered_v2', 'zh', name=display_name, id=staff_id)
    await telegram_handler.send_message(chat_id, msg)
    logger.info(f'New staff registered: {display_name} (tg_id={user_id})')


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


REGISTRATION_V2_COMMANDS = {
    'start_v2': handle_start_v2,
    'profile': handle_profile,
}

REGISTRATION_V2_CALLBACKS = {}
REGISTRATION_V2_CONVERSATIONS = {}

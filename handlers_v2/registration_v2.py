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


async def handle_bind(task_data: Dict[str, Any]):
    """/bind <display_name> — Link your Telegram account to an existing staff record.

    For staff who were pre-seeded (阿毛, Juan Juan, etc.) and need to bind their
    real Telegram account. Matches by display_name, replaces placeholder tg_user_id.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    username = task_data.get('username')
    args = (task_data.get('args') or '').strip()
    lang = 'zh'

    if not args:
        await telegram_handler.send_message(chat_id,
            "用法: /bind <你的名字>\n"
            "例如: /bind 阿毛\n\n"
            "Usage: /bind <your name>\n"
            "Example: /bind Juan Juan")
        return

    # Check if this Telegram account is already linked
    existing = await database_v2.get_staff_by_tg_id(user_id)
    if existing:
        lang = existing.language
        await telegram_handler.send_message(chat_id,
            t('bind_already_linked', lang, name=existing.display_name))
        return

    # Search for the target staff record by display_name
    all_staff = await database_v2.get_all_staff()
    target = None
    for s in all_staff:
        if s.display_name.lower().strip() == args.lower().strip():
            target = s
            break

    if not target:
        # Fuzzy: try partial match
        matches = [s for s in all_staff if args.lower() in s.display_name.lower()]
        if len(matches) == 1:
            target = matches[0]
        elif len(matches) > 1:
            names = ', '.join(s.display_name for s in matches)
            await telegram_handler.send_message(chat_id,
                f"❌ 找到多个匹配: {names}\n请输入完整名字 / Multiple matches, use exact name")
            return
        else:
            await telegram_handler.send_message(chat_id,
                f"❌ 找不到 '{args}'\n请确认名字正确 / Name not found, check spelling")
            return

    # Check if the target already has a real Telegram ID (not placeholder)
    if target.tg_user_id and target.tg_user_id > 0:
        await telegram_handler.send_message(chat_id,
            f"❌ {target.display_name} 已经绑定了另一个 Telegram 账号\n"
            f"Already bound to another account. Contact admin.")
        return

    # Bind: update tg_user_id and tg_chat_id
    target.tg_user_id = user_id
    target.tg_chat_id = chat_id
    if username:
        target.tg_username = username
    await database_v2.update_staff(target)

    logger.info(f"Bind: {target.display_name} (id={target.id}) → tg_user_id={user_id}")

    lang = target.language or 'zh'
    await telegram_handler.send_message(chat_id,
        f"✅ 绑定成功! / Bound successfully!\n\n"
        f"👤 {target.display_name}\n"
        f"🏷 {target.role.value}\n"
        f"👥 {target.team or '未分组'}\n\n"
        f"现在可以使用所有命令了 / You can now use all commands")


REGISTRATION_V2_COMMANDS = {
    'start': handle_start_v2,
    'profile': handle_profile,
    'lang': handle_lang,
    'setname': handle_setname,
    'bind': handle_bind,
}

REGISTRATION_V2_CALLBACKS = {}

REGISTRATION_V2_CONVERSATIONS = {
    'reg_v2_lang': handle_reg_lang_step,
    'reg_v2_role': handle_reg_role_step,
    'reg_v2_name': handle_reg_name_step,
}

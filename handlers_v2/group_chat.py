"""V2 group chat handlers — group detection, /linkgroup, /unlinkgroup, team-scoped commands."""
import logging
from typing import Any, Dict, Optional

from database_v2 import database_v2, TEAM_STRUCTURE
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

# Telegram chat types that are groups
_GROUP_TYPES = {'group', 'supergroup'}


def is_group_chat(task_data: Dict[str, Any]) -> bool:
    """Return True if the update originated from a group/supergroup."""
    chat_type = task_data.get('chat_type', 'private')
    return chat_type in _GROUP_TYPES


def is_command_message(task_data: Dict[str, Any]) -> bool:
    """Return True if the message starts with /."""
    text = task_data.get('text', '') or ''
    return text.startswith('/')


async def get_group_team(tg_group_id: int) -> Optional[str]:
    """Return team name linked to this group, or None."""
    rec = await database_v2.get_group(tg_group_id)
    return rec['team'] if rec else None


async def handle_linkgroup(task_data: Dict[str, Any]):
    """/linkgroup <teamname> — link current group to a team (admin only)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    if not is_group_chat(task_data):
        # Silently ignore in DMs
        return

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    if not staff.is_admin():
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    if not args:
        await telegram_handler.send_message(chat_id, t('linkgroup_usage', lang))
        return

    team_name = args
    # Validate team exists in TEAM_STRUCTURE or in DB
    known_teams = list(TEAM_STRUCTURE.keys()) + await database_v2.get_all_teams()
    if team_name not in known_teams:
        await telegram_handler.send_message(
            chat_id, t('linkgroup_team_not_found', lang, team=team_name))
        return

    group_name = task_data.get('chat_title', f'Group_{chat_id}')
    await database_v2.link_group(chat_id, group_name, team_name, group_type='team')
    await telegram_handler.send_message(
        chat_id, t('linkgroup_success', lang, team=team_name))


async def handle_unlinkgroup(task_data: Dict[str, Any]):
    """/unlinkgroup — remove team link from current group (admin only)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    if not is_group_chat(task_data):
        return

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    if not staff.is_admin():
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    deleted = await database_v2.unlink_group(chat_id)
    if deleted:
        await telegram_handler.send_message(chat_id, t('unlinkgroup_success', lang))
    else:
        await telegram_handler.send_message(chat_id, t('unlinkgroup_not_linked', lang))


async def group_middleware(task_data: Dict[str, Any]) -> bool:
    """Call before dispatching a command in a group.

    Returns True if the command should be processed, False to silently drop it.

    Rules:
    - In groups: only process /commands (drop plain text messages).
    - Inject group_team into task_data so handlers can scope queries.
    """
    if not is_group_chat(task_data):
        return True  # DMs: always process

    # In groups: ignore non-command messages
    if not is_command_message(task_data):
        return False

    # Inject linked team so downstream handlers can filter by team
    chat_id = task_data.get('chat_id')
    if chat_id:
        team = await get_group_team(chat_id)
        if team:
            task_data['group_team'] = team

    return True


GROUP_COMMANDS = {
    'linkgroup': handle_linkgroup,
    'unlinkgroup': handle_unlinkgroup,
}

GROUP_CALLBACKS: Dict[str, Any] = {}
GROUP_CONVERSATIONS: Dict[str, Any] = {}

"""V2 handler package — shared utilities."""
import functools
import logging
from typing import Any, Callable, Dict, List, Optional

from database_v2 import database_v2
from models_v2 import Staff, check_permission

logger = logging.getLogger(__name__)


async def get_staff(user_id: int) -> Optional[Staff]:
    """Look up staff by Telegram user ID. Shared across all V2 handlers."""
    return await database_v2.get_staff_by_tg_id(user_id)


def resolve_team_scope(task_data: Dict[str, Any], staff: Staff) -> Optional[str]:
    """Determine the team scope for a command.

    Priority:
    1. group_team from task_data (set by group_middleware or auto-detect)
    2. staff.team (the user's own team)

    Returns team name (e.g. '阿俊', '何军', '全线') or None for no scope.
    """
    group_team = task_data.get('group_team')
    if group_team:
        # Map team_config IDs to DB team names
        _ID_TO_TEAM = {
            'quanxian': '全线',
            'ajun': '阿俊',
            'hejun': '何军',
            'chaoqun': '炒群',
        }
        return _ID_TO_TEAM.get(group_team, group_team)
    return staff.team if staff.team else None


async def get_team_staff_ids(team: str) -> List[int]:
    """Get all staff IDs for a team."""
    all_staff = await database_v2.get_all_staff()
    return [s.id for s in all_staff if s.team == team]


def is_group_context(task_data: Dict[str, Any]) -> bool:
    """Return True if this command came from a group/supergroup."""
    return task_data.get('chat_type', 'private') in ('group', 'supergroup')


def require_permission(command: str):
    """Decorator: rejects handler if staff lacks permission for command.

    Wrapped handler must receive task_data dict with 'chat_id' and 'user_id'.
    Sends i18n error and returns early if denied.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(task_data: Dict[str, Any], *args, **kwargs):
            from i18n import t
            from telegram_handler import telegram_handler

            chat_id = task_data.get('chat_id')
            user_id = task_data.get('user_id')
            staff = await get_staff(user_id)
            if not staff:
                await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
                return
            if not check_permission(staff, command):
                await telegram_handler.send_message(
                    chat_id, t('err_permission_denied', staff.language))
                return
            return await fn(task_data, *args, **kwargs)
        return wrapper
    return decorator

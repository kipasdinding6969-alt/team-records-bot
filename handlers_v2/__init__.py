"""V2 handler package — shared utilities."""
import functools
import logging
from typing import Any, Callable, Dict, Optional

from database_v2 import database_v2
from models_v2 import Staff, check_permission

logger = logging.getLogger(__name__)


async def get_staff(user_id: int) -> Optional[Staff]:
    """Look up staff by Telegram user ID. Shared across all V2 handlers."""
    return await database_v2.get_staff_by_tg_id(user_id)


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

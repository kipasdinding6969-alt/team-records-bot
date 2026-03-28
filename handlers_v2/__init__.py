"""V2 handler package — shared utilities."""
from typing import Optional
from database_v2 import database_v2
from models_v2 import Staff


async def get_staff(user_id: int) -> Optional[Staff]:
    """Look up staff by Telegram user ID. Shared across all V2 handlers."""
    return await database_v2.get_staff_by_tg_id(user_id)

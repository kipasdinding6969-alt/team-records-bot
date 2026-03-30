"""Gamification V2 handlers — /xp, /badges, enhanced /leaderboard (XP-based)."""
import logging
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff
from engines.gamification_v2 import build_xp_status_message, build_badges_message

logger = logging.getLogger(__name__)


# ─── /xp ──────────────────────────────────────────────────────────────────────

async def handle_xp(task_data: Dict[str, Any]):
    """/xp — Show your XP total, streak, and next badge."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    msg = await build_xp_status_message(staff.id, staff.display_name, staff.language)
    await telegram_handler.send_message(chat_id, msg, parse_mode='markdown')
    logger.info(f'Staff {staff.display_name} viewed XP status')


# ─── /badges ──────────────────────────────────────────────────────────────────

async def handle_badges(task_data: Dict[str, Any]):
    """/badges — Show earned + locked badges grid."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    msg = await build_badges_message(staff.id, staff.language)
    await telegram_handler.send_message(chat_id, msg, parse_mode='markdown')
    logger.info(f'Staff {staff.display_name} viewed badges')


# ─── /xpleaderboard ───────────────────────────────────────────────────────────

async def handle_xp_leaderboard(task_data: Dict[str, Any]):
    """/xpleaderboard [today|week|month] — XP-based leaderboard with streaks."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip().lower()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    period = args if args in ('today', 'week', 'month') else 'today'

    team_filter = None
    if not staff.is_manager_or_above() and staff.team:
        team_filter = staff.team

    rows = await database_v2.get_xp_leaderboard(period=period, team_id=team_filter)

    period_label = t(f'leaderboard_period_{period}', lang)
    lines = [t('xp_leaderboard_title', lang, period=period_label), '']

    if not rows:
        lines.append(t('leaderboard_empty', lang))
    else:
        for i, row in enumerate(rows, 1):
            streak = row.get('current_streak', 0)
            streak_str = f' 🔥{streak}' if streak >= 3 else ''
            lines.append(
                t('xp_leaderboard_row', lang,
                  rank=i,
                  name=row['display_name'],
                  xp=int(row['total_xp']),
                  streak=streak_str)
            )

    await telegram_handler.send_message(chat_id, '\n'.join(lines), parse_mode='markdown')
    logger.info(f'Staff {staff.display_name} viewed XP leaderboard ({period})')


# ─── Handler registry ─────────────────────────────────────────────────────────

GAMIFICATION_V2_COMMANDS = {
    'xp':            handle_xp,
    'badges':        handle_badges,
    'xpleaderboard': handle_xp_leaderboard,
}

GAMIFICATION_V2_CALLBACKS: dict = {}
GAMIFICATION_V2_CONVERSATIONS: dict = {}

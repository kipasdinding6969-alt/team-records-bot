"""Digest engine — morning and evening summaries for staff and managers."""
import logging
from typing import Any, Dict, List

from database_v2 import database_v2
from models_v2 import Staff

logger = logging.getLogger(__name__)

DAILY_XP_GOAL = 50

_STATUS_ORDER = ['new', 'contacted', 'replied', 'registered', 'training', 'ordered']
_STATUS_LABELS = {
    'new': '新线索', 'contacted': '已联系', 'replied': '已回复',
    'registered': '已注册', 'training': '培训中', 'ordered': '已下单',
}


def _is_morning_hour(hour: int) -> bool:
    """Return True if hour == 8 (morning digest window)."""
    return hour == 8


def _is_evening_hour(hour: int) -> bool:
    """Return True if hour == 18 (evening digest window)."""
    return hour == 18


async def build_morning_digest(staff: Staff) -> str:
    """Build personalized morning digest for a frontdesk staff member."""
    from engines.gamification_v2 import _find_next_badge

    pipeline = await database_v2.get_pipeline_counts(staff.id)
    hot_leads = await database_v2.get_hot_leads(frontdesk_id=staff.id, limit=3)
    overdue = await database_v2.get_followup_due(staff.id)
    streak = await database_v2.get_streak(staff.id)
    today_xp = await database_v2.get_staff_xp(staff.id, 'today')
    total_xp = await database_v2.get_staff_xp(staff.id, 'all')
    badges = await database_v2.get_staff_badges(staff.id)
    all_badges = await database_v2.get_all_badges()
    next_badge = _find_next_badge(all_badges, badges, total_xp, streak.get('current_streak', 0))
    current_streak = streak.get('current_streak', 0)

    lines = [f'☀️ **早安，{staff.display_name}！**', '']

    # Pipeline summary
    lines.append('📊 **流水线概况**')
    has_any = False
    for s in _STATUS_ORDER:
        cnt = pipeline.get(s, 0)
        if cnt > 0:
            lines.append(f'  {_STATUS_LABELS.get(s, s)}: **{cnt}**')
            has_any = True
    if not has_any:
        lines.append('  暂无客户')
    lines.append('')

    # Hot leads
    if hot_leads:
        lines.append('🔥 **热门线索 Top 3**')
        for lead in hot_leads[:3]:
            name = lead.get('nickname') or lead.get('phone', '')
            score = lead.get('score', 0)
            status = lead.get('status', '')
            lines.append(f'  • {name} [{status}] — 评分 {score}')
        lines.append('')

    # Overdue follow-ups
    overdue_count = len(overdue)
    if overdue_count > 0:
        lines.append(f'⏰ **待跟进**: {overdue_count} 位客户逾期跟进')
        lines.append('')

    # Streak status
    if current_streak >= 3:
        lines.append(f'🔥 连续打卡 **{current_streak} 天**，保持住！')
    elif current_streak >= 1:
        lines.append(f'📅 已连续 **{current_streak} 天**，继续努力！')
    else:
        lines.append('💪 开始你的连续打卡之旅！')

    # XP goal
    xp_remaining = max(0, DAILY_XP_GOAL - today_xp)
    if xp_remaining > 0:
        lines.append(f'⭐ 今日目标: 还需 **{xp_remaining}** XP（目标 {DAILY_XP_GOAL}）')
    else:
        lines.append(f'⭐ 今日目标已达成！已获 **{today_xp}** XP 🎉')

    # Next badge progress
    if next_badge and next_badge.get('xp_threshold'):
        remaining_xp = next_badge['xp_threshold'] - total_xp
        lines.append(
            f'🎯 下一徽章: {next_badge["emoji"]} {next_badge["name"]} — 还需 **{remaining_xp}** XP'
        )

    lines.append('')
    lines.append('今天也要努力！加油！💪')
    return '\n'.join(lines)


async def build_evening_digest(staff: Staff) -> str:
    """Build personalized evening digest for a frontdesk staff member."""
    stat = await database_v2.calculate_daily_stats(staff.id)
    today_xp = await database_v2.get_staff_xp(staff.id, 'today')
    streak = await database_v2.get_streak(staff.id)
    overdue = await database_v2.get_followup_due(staff.id)
    current_streak = streak.get('current_streak', 0)

    lines = [f'🌙 **晚安，{staff.display_name}！今日总结**', '']

    lines.append('📈 **今日成果**')
    lines.append(f'  🆕 新增客户: **{stat.new_leads}**')
    if stat.contacted:
        lines.append(f'  📞 已联系: **{stat.contacted}**')
    if stat.registered:
        lines.append(f'  ✅ 注册转化: **{stat.registered}**')
    if stat.total_deposit and stat.total_deposit > 0:
        lines.append(f'  💰 今日存款: **{stat.total_deposit:.0f}**')
    lines.append('')

    lines.append(f'⭐ 今日 XP: **{today_xp}**')

    if current_streak >= 1:
        lines.append(f'🔥 连续打卡: **{current_streak} 天** — 太棒了！')
    else:
        lines.append('💪 明天再来，开始新的连续打卡！')
    lines.append('')

    if overdue:
        lines.append(f'⏰ **明日待跟进**: {len(overdue)} 位客户需要跟进')

    lines.append('晚安，明天继续加油！🌟')
    return '\n'.join(lines)


async def build_manager_digest(manager: Staff) -> str:
    """Build team-wide digest for a manager."""
    all_staff = await database_v2.get_all_staff()
    frontdesk_staff = [s for s in all_staff if not s.is_manager_or_above()]

    # Team-wide pipeline
    total_pipeline: Dict[str, int] = {}
    for s in frontdesk_staff:
        counts = await database_v2.get_pipeline_counts(s.id)
        for status, cnt in counts.items():
            total_pipeline[status] = total_pipeline.get(status, 0) + cnt

    # Top performers by XP today
    leaderboard = await database_v2.get_xp_leaderboard(period='today')
    top3 = leaderboard[:3]

    # Team streak stats
    active_streaks = []
    for s in frontdesk_staff:
        streak = await database_v2.get_streak(s.id)
        days = streak.get('current_streak', 0)
        if days >= 1:
            active_streaks.append((s.display_name, days))
    active_streaks.sort(key=lambda x: x[1], reverse=True)

    # Pending follow-ups across team
    total_overdue = 0
    for s in frontdesk_staff:
        overdue = await database_v2.get_followup_due(s.id)
        total_overdue += len(overdue)

    lines = [f'📋 **团队早报 — {manager.display_name}**', '']

    lines.append('📊 **团队流水线**')
    has_any = False
    for s in _STATUS_ORDER:
        cnt = total_pipeline.get(s, 0)
        if cnt > 0:
            lines.append(f'  {_STATUS_LABELS.get(s, s)}: **{cnt}**')
            has_any = True
    if not has_any:
        lines.append('  暂无数据')
    lines.append('')

    if top3:
        lines.append('🏆 **今日表现 Top 3**')
        medals = ['🥇', '🥈', '🥉']
        for i, row in enumerate(top3):
            medal = medals[i] if i < 3 else f'{i + 1}.'
            lines.append(f'  {medal} {row["display_name"]}: **{row["total_xp"]}** XP')
        lines.append('')

    if active_streaks:
        lines.append('🔥 **连续打卡**')
        for name, days in active_streaks[:5]:
            lines.append(f'  {name}: {days} 天')
        lines.append('')

    if total_overdue > 0:
        lines.append(f'⏰ **团队待跟进**: {total_overdue} 位客户逾期跟进')

    return '\n'.join(lines)


async def send_morning_digests():
    """Send morning digest to all active staff. Runs at 8:00 AM."""
    from telegram_handler import telegram_handler

    all_staff = await database_v2.get_all_staff()
    sent = errors = 0
    for staff in all_staff:
        try:
            if staff.is_manager_or_above():
                msg = await build_manager_digest(staff)
            else:
                msg = await build_morning_digest(staff)
            await telegram_handler.send_message(staff.tg_chat_id, msg)
            sent += 1
        except Exception as e:
            logger.error(f'send_morning_digests: failed for {staff.display_name}: {e}')
            errors += 1
    logger.info(f'Morning digests sent: {sent} ok, {errors} errors')


async def send_evening_digests():
    """Send evening digest to all active staff. Runs at 6:00 PM."""
    from telegram_handler import telegram_handler

    all_staff = await database_v2.get_all_staff()
    sent = errors = 0
    for staff in all_staff:
        try:
            if staff.is_manager_or_above():
                msg = await build_manager_digest(staff)
            else:
                msg = await build_evening_digest(staff)
            await telegram_handler.send_message(staff.tg_chat_id, msg)
            sent += 1
        except Exception as e:
            logger.error(f'send_evening_digests: failed for {staff.display_name}: {e}')
            errors += 1
    logger.info(f'Evening digests sent: {sent} ok, {errors} errors')

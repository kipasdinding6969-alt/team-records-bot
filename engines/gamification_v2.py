"""Gamification V2 engine — XP awards, streak logic, badge checks, motivation."""
import logging
from typing import Any, Dict, List, Optional

from database_v2 import database_v2

logger = logging.getLogger(__name__)

# XP values per action
XP_RULES: Dict[str, int] = {
    'add_client':               10,
    'update_status':             5,
    'voice_update':             15,
    'first_registration_today': 20,
    'reply_within_1h':          10,
}

# Streak milestone messages (zh)
STREAK_MILESTONES: Dict[int, str] = {
    7:   '🔥 **连续7天！** 你是勤劳蜜蜂，继续加油！',
    30:  '💎 **连续30天！** 钻石级别的坚持，太棒了！',
    100: '👑 **连续100天！** 传奇成就解锁！你是团队的骄傲！',
}


async def award_action_xp(staff_id: int, action: str, extra_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Award XP for an action. Returns dict with xp_awarded, new_badges, streak_milestone."""
    amount = XP_RULES.get(action, 0)
    if amount == 0:
        return {'xp_awarded': 0, 'new_badges': [], 'streak_milestone': None}

    await database_v2.award_xp(staff_id, action, amount)

    # Check for first_registration_today bonus
    if action == 'add_client' and extra_context and extra_context.get('is_first_today'):
        bonus = XP_RULES['first_registration_today']
        await database_v2.award_xp(staff_id, 'first_registration_today', bonus)
        amount += bonus

    # Auto-award badges
    new_badges = await database_v2.check_and_award_badges(staff_id)

    # Check streak milestone
    streak = await database_v2.get_streak(staff_id)
    current = streak.get('current_streak', 0)
    milestone_msg = STREAK_MILESTONES.get(current)

    logger.info(f'XP awarded: staff={staff_id} action={action} xp={amount}')
    return {
        'xp_awarded': amount,
        'new_badges': new_badges,
        'streak_milestone': milestone_msg,
    }


async def get_morning_motivation(staff_id: int, display_name: str) -> str:
    """Build a personalized morning motivation message."""
    streak = await database_v2.get_streak(staff_id)
    total_xp = await database_v2.get_staff_xp(staff_id, 'all')
    today_xp = await database_v2.get_staff_xp(staff_id, 'today')
    current_streak = streak.get('current_streak', 0)
    badges = await database_v2.get_staff_badges(staff_id)

    lines = [f'☀️ **早安，{display_name}！**', '']

    if current_streak >= 3:
        lines.append(f'🔥 连续打卡 **{current_streak} 天**，保持住！')
    elif current_streak == 0:
        lines.append('💪 新的一天，开始你的连续打卡之旅吧！')
    else:
        lines.append(f'📅 已连续 **{current_streak} 天**，加油！')

    lines.append(f'⭐ 今日 XP: **{today_xp}** | 总 XP: **{total_xp}**')

    if badges:
        lines.append(f'🏅 已获徽章: **{len(badges)}** 枚')

    lines.append('')
    lines.append('今天也要努力！加油！💪')
    return '\n'.join(lines)


async def build_xp_status_message(staff_id: int, display_name: str, lang: str = 'zh') -> str:
    """Build /xp command response message."""
    total_xp = await database_v2.get_staff_xp(staff_id, 'all')
    today_xp = await database_v2.get_staff_xp(staff_id, 'today')
    week_xp = await database_v2.get_staff_xp(staff_id, 'week')
    streak = await database_v2.get_streak(staff_id)
    current_streak = streak.get('current_streak', 0)
    longest_streak = streak.get('longest_streak', 0)
    freeze_available = streak.get('freeze_available', 0)
    badges = await database_v2.get_staff_badges(staff_id)
    all_badges = await database_v2.get_all_badges()

    # Find next badge to earn
    next_badge = _find_next_badge(all_badges, badges, total_xp, current_streak)

    if lang == 'zh':
        lines = [
            f'⭐ **{display_name} 的 XP 状态**',
            '',
            f'今日 XP: **{today_xp}**',
            f'本周 XP: **{week_xp}**',
            f'总计 XP: **{total_xp}**',
            '',
            f'🔥 当前连续: **{current_streak} 天**',
            f'🏆 最长连续: **{longest_streak} 天**',
            f'❄️ 冻结次数: **{freeze_available}**',
            '',
            f'🏅 已获徽章: **{len(badges)}** / {len(all_badges)}',
        ]
        if next_badge:
            lines.append(f'🎯 下一个徽章: {next_badge["emoji"]} {next_badge["name"]}')
            if next_badge.get('xp_threshold'):
                remaining = next_badge['xp_threshold'] - total_xp
                lines.append(f'   还需 **{remaining}** XP')
    else:
        lines = [
            f'⭐ **{display_name}\'s XP Status**',
            '',
            f'Today XP: **{today_xp}**',
            f'This Week XP: **{week_xp}**',
            f'Total XP: **{total_xp}**',
            '',
            f'🔥 Current Streak: **{current_streak} days**',
            f'🏆 Longest Streak: **{longest_streak} days**',
            f'❄️ Freeze Available: **{freeze_available}**',
            '',
            f'🏅 Badges: **{len(badges)}** / {len(all_badges)}',
        ]
        if next_badge:
            lines.append(f'🎯 Next Badge: {next_badge["emoji"]} {next_badge["name"]}')
            if next_badge.get('xp_threshold'):
                remaining = next_badge['xp_threshold'] - total_xp
                lines.append(f'   Need **{remaining}** more XP')

    return '\n'.join(lines)


async def build_badges_message(staff_id: int, lang: str = 'zh') -> str:
    """Build /badges command response message — earned + locked grid."""
    earned = await database_v2.get_staff_badges(staff_id)
    all_badges = await database_v2.get_all_badges()
    earned_ids = {b['id'] for b in earned}

    locked = [b for b in all_badges if b['id'] not in earned_ids]

    if lang == 'zh':
        lines = ['🏅 **我的徽章**', '']
        if earned:
            lines.append('**已获得：**')
            for b in earned:
                lines.append(f'{b["emoji"]} {b["name"]} — {b["description"]}')
        else:
            lines.append('暂无徽章，开始行动获取吧！')
        lines.append('')
        if locked:
            lines.append('**未解锁：**')
            row = []
            for b in locked:
                row.append(b['emoji'])
                if len(row) == 5:
                    lines.append(' '.join(row))
                    row = []
            if row:
                lines.append(' '.join(row))
    else:
        lines = ['🏅 **My Badges**', '']
        if earned:
            lines.append('**Earned:**')
            for b in earned:
                lines.append(f'{b["emoji"]} {b["name"]} — {b["description"]}')
        else:
            lines.append('No badges yet — start earning!')
        lines.append('')
        if locked:
            lines.append('**Locked:**')
            row = []
            for b in locked:
                row.append(b['emoji'])
                if len(row) == 5:
                    lines.append(' '.join(row))
                    row = []
            if row:
                lines.append(' '.join(row))

    return '\n'.join(lines)


def _find_next_badge(
    all_badges: List[Dict[str, Any]],
    earned: List[Dict[str, Any]],
    total_xp: int,
    current_streak: int,
) -> Optional[Dict[str, Any]]:
    """Return the next XP-based badge the staff member can earn."""
    earned_ids = {b['id'] for b in earned}
    xp_badges = [b for b in all_badges if b.get('xp_threshold') and b['id'] not in earned_ids]
    xp_badges.sort(key=lambda b: b['xp_threshold'])
    for badge in xp_badges:
        if total_xp < badge['xp_threshold']:
            return badge
    return None

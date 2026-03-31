"""Phase 9D: Performance Coaching — /coaching command with Ollama AI."""
import logging
from typing import Any, Dict, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

_OLLAMA_MODEL = 'goonsai/josiefied-qwen2.5-7b-abliterated-v2'
_OLLAMA_URL = 'http://localhost:11434/api/generate'


async def _call_ollama(prompt: str) -> str:
    """Call Ollama generate API. Returns text or fallback message."""
    try:
        if aiohttp is None:
            return '（AI建议暂不可用，请稍后重试）'
        payload = {
            'model': _OLLAMA_MODEL,
            'prompt': prompt,
            'stream': False,
            'options': {'temperature': 0.7, 'num_predict': 300},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(_OLLAMA_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('response', '').strip()
    except Exception as e:
        logger.warning(f'Ollama coaching call failed: {e}')
    return '（AI建议暂不可用，请稍后重试）'


async def _gather_staff_metrics(staff_id: int, team: Optional[str] = None) -> Dict:
    """Collect metrics for a staff member for coaching analysis."""
    # SLA compliance
    sla_stats = await database_v2.get_sla_stats(staff_id=staff_id, days=7)
    total_met = sum(v['met'] for v in sla_stats.values())
    total_sla = sum(v['total'] for v in sla_stats.values())
    sla_pct = round(total_met / total_sla * 100, 1) if total_sla > 0 else 0.0

    avg_response = 0.0
    if sla_stats:
        all_avgs = [v['avg_minutes'] for v in sla_stats.values() if v['avg_minutes'] > 0]
        avg_response = round(sum(all_avgs) / len(all_avgs), 1) if all_avgs else 0.0

    # XP this week
    xp_week = await database_v2.get_staff_xp(staff_id, 'week')
    xp_prev = await database_v2.get_staff_xp(staff_id, 'all') - xp_week

    # Pipeline stats — from daily_stats
    async with database_v2.get_connection() as db:
        cur = await db.execute(
            """SELECT SUM(replied) as total_replied,
                      SUM(contacted) as total_contacted,
                      SUM(registered) as total_registered,
                      SUM(new_leads) as total_leads
               FROM daily_stats
               WHERE staff_id=? AND stat_date >= DATE('now', '-7 days')""",
            (staff_id,))
        row = await cur.fetchone()

    total_replied = (row['total_replied'] or 0) if row else 0
    total_contacted = (row['total_contacted'] or 0) if row else 0
    total_registered = (row['total_registered'] or 0) if row else 0
    total_leads = (row['total_leads'] or 0) if row else 0

    reply_rate = round(total_replied / total_contacted * 100, 1) if total_contacted > 0 else 0.0
    conv_rate = round(total_registered / total_contacted * 100, 1) if total_contacted > 0 else 0.0

    # Streak
    streak = await database_v2.get_streak(staff_id)
    current_streak = streak.get('current_streak', 0)

    # Team averages for context
    team_sla_summary = await database_v2.get_staff_sla_summary(days=7)
    if team_sla_summary:
        team_avg_pct = round(
            sum(r['compliance_pct'] for r in team_sla_summary) / len(team_sla_summary), 1)
    else:
        team_avg_pct = 0.0

    return {
        'sla_pct': sla_pct,
        'team_avg_sla': team_avg_pct,
        'reply_rate': reply_rate,
        'conv_rate': conv_rate,
        'avg_response_min': avg_response,
        'xp_week': xp_week,
        'xp_trend': '+' if xp_week >= (xp_prev / max(1, 1)) else '-',
        'streak': current_streak,
        'total_leads': total_leads,
    }


async def _build_coaching_report(display_name: str, metrics: Dict, ai_tips: str) -> str:
    sla = metrics['sla_pct']
    team_sla = metrics['team_avg_sla']
    reply = metrics['reply_rate']
    conv = metrics['conv_rate']
    avg_resp = metrics['avg_response_min']
    xp = metrics['xp_week']
    streak = metrics['streak']

    sla_icon = '✅' if sla >= team_sla else '⚠️'
    reply_icon = '✅' if reply >= 60 else '⚠️'
    conv_icon = '✅' if conv >= 25 else '⚠️'

    lines = [
        f'📊 教练报告: {display_name}',
        '━━━━━━━━━━━━━━━━━━━━━',
        f'{sla_icon} SLA合规率: {sla}% (团队均值: {team_sla}%)',
        f'{reply_icon} 回复率: {reply}%',
        f'{conv_icon} 转化率: {conv}%',
        f'⚡ 平均响应: {avg_resp}分钟',
        f'🔥 本周XP: {xp}分 | 连续: {streak}天',
        '',
        '🤖 AI建议:',
    ]
    # Number the AI tips
    for i, tip in enumerate(ai_tips.split('\n'), 1):
        tip = tip.strip()
        if tip:
            if not tip[0].isdigit():
                tip = f'{i}. {tip}'
            lines.append(tip)

    return '\n'.join(lines)


async def handle_coaching(task_data: Dict[str, Any]):
    """/coaching [staff_name|team]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from models_v2 import StaffRole
    is_manager = staff.role in (StaffRole.MANAGER, StaffRole.ADMIN)

    # /coaching team
    if args.lower() == 'team':
        if not is_manager:
            await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
            return
        await _handle_team_coaching(chat_id, staff.team)
        return

    # /coaching <staff_name>
    if args and is_manager:
        all_staff = await database_v2.get_all_staff()
        target = next((s for s in all_staff if args.lower() in s.display_name.lower()), None)
        if not target:
            await telegram_handler.send_message(chat_id, f'❌ 找不到员工: {args}')
            return
        await _handle_individual_coaching(chat_id, target.id, target.display_name)
        return

    # /coaching (self)
    await _handle_individual_coaching(chat_id, staff.id, staff.display_name)


async def _handle_individual_coaching(chat_id: int, staff_id: int, display_name: str):
    await telegram_handler.send_message(chat_id, f'⏳ 正在生成 {display_name} 的教练报告...')
    metrics = await _gather_staff_metrics(staff_id)

    prompt = (
        f'Based on these CRM metrics for {display_name}:\n'
        f'- SLA compliance: {metrics["sla_pct"]}%\n'
        f'- Reply rate: {metrics["reply_rate"]}%\n'
        f'- Conversion rate: {metrics["conv_rate"]}%\n'
        f'- Avg response time: {metrics["avg_response_min"]} minutes\n'
        f'- XP this week: {metrics["xp_week"]}\n\n'
        'Provide 3 specific, actionable coaching tips in Chinese. '
        'Be encouraging but honest. Focus on the weakest metric. '
        'Keep each tip under 2 sentences.'
    )
    ai_tips = await _call_ollama(prompt)
    report = await _build_coaching_report(display_name, metrics, ai_tips)
    await telegram_handler.send_message(chat_id, report)


async def _handle_team_coaching(chat_id: int, team: Optional[str]):
    all_staff = await database_v2.get_all_staff()
    if team:
        members = [s for s in all_staff if s.team == team]
    else:
        members = all_staff

    if not members:
        await telegram_handler.send_message(chat_id, '❌ 没有找到团队成员')
        return

    await telegram_handler.send_message(chat_id, f'⏳ 正在生成团队教练报告 ({len(members)}人)...')

    all_metrics = []
    for s in members:
        m = await _gather_staff_metrics(s.id, team)
        all_metrics.append({'name': s.display_name, **m})

    if not all_metrics:
        await telegram_handler.send_message(chat_id, '暂无足够数据生成报告')
        return

    avg_sla = round(sum(m['sla_pct'] for m in all_metrics) / len(all_metrics), 1)
    avg_reply = round(sum(m['reply_rate'] for m in all_metrics) / len(all_metrics), 1)
    avg_conv = round(sum(m['conv_rate'] for m in all_metrics) / len(all_metrics), 1)
    total_xp = sum(m['xp_week'] for m in all_metrics)

    # Top and bottom performers
    sorted_by_sla = sorted(all_metrics, key=lambda x: x['sla_pct'], reverse=True)
    top = sorted_by_sla[0] if sorted_by_sla else None
    bottom = sorted_by_sla[-1] if len(sorted_by_sla) > 1 else None

    lines = [
        f'📊 团队教练报告',
        '━━━━━━━━━━━━━━━━━━━━━',
        f'👥 成员: {len(members)}人',
        f'⏱️ 团队SLA: {avg_sla}%',
        f'💬 平均回复率: {avg_reply}%',
        f'📈 平均转化率: {avg_conv}%',
        f'⚡ 本周总XP: {total_xp}分',
    ]
    if top:
        lines.append(f'\n🏆 最佳: {top["name"]} (SLA {top["sla_pct"]}%)')
    if bottom:
        lines.append(f'📉 需关注: {bottom["name"]} (SLA {bottom["sla_pct"]}%)')

    prompt = (
        f'Team CRM performance summary:\n'
        f'- Team SLA compliance: {avg_sla}%\n'
        f'- Avg reply rate: {avg_reply}%\n'
        f'- Avg conversion: {avg_conv}%\n'
        f'- Total XP this week: {total_xp}\n\n'
        'Give 3 team-level coaching suggestions in Chinese. '
        'Be encouraging and action-focused. Under 2 sentences each.'
    )
    ai_tips = await _call_ollama(prompt)
    lines.append('\n🤖 AI团队建议:')
    for i, tip in enumerate(ai_tips.split('\n'), 1):
        tip = tip.strip()
        if tip:
            lines.append(f'{i}. {tip}' if not tip[0].isdigit() else tip)

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


COACHING_COMMANDS = {
    'coaching': handle_coaching,
}
COACHING_CALLBACKS: Dict = {}
COACHING_CONVERSATIONS: Dict = {}

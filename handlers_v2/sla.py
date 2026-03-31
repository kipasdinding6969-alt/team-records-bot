"""Phase 9C: SLA Tracking — /sla command."""
import logging
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)


async def handle_sla(task_data: Dict[str, Any]):
    """/sla [staff_name | config <type> <target> [warn] [critical]]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from models_v2 import StaffRole
    is_manager = staff.role in (StaffRole.MANAGER, StaffRole.ADMIN)

    parts = args.split()

    # /sla config <type> <target_min> [warn_min] [critical_min]
    if parts and parts[0].lower() == 'config':
        if not is_manager:
            await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
            return
        await _handle_sla_config(chat_id, parts[1:])
        return

    # /sla <staff_name> — individual report
    if parts:
        target_name = ' '.join(parts)
        all_staff = await database_v2.get_all_staff()
        # Exact match first
        target_staff = next((s for s in all_staff if target_name.lower() == s.display_name.lower()), None)
        if not target_staff:
            # Fuzzy fallback
            fuzzy = [s for s in all_staff if target_name.lower() in s.display_name.lower()]
            if len(fuzzy) > 1:
                names = ', '.join(s.display_name for s in fuzzy[:5])
                await telegram_handler.send_message(
                    chat_id, f'⚠️ 找到多个匹配: {names}\n请使用更精确的名字')
                return
            target_staff = fuzzy[0] if fuzzy else None
        if not target_staff:
            await telegram_handler.send_message(chat_id, f'❌ 找不到员工: {target_name}')
            return
        await _show_staff_sla(chat_id, target_staff.id, target_staff.display_name)
        return

    # /sla — team dashboard
    if is_manager:
        await _show_team_sla(chat_id, staff.team)
    else:
        await _show_staff_sla(chat_id, staff.id, staff.display_name)


async def _show_staff_sla(chat_id: int, staff_id: int, display_name: str):
    stats = await database_v2.get_sla_stats(staff_id=staff_id, days=7)
    configs = await database_v2.get_sla_config()
    config_map = {c['event_type']: c for c in configs}

    lines = [f'⏱️ SLA报告: {display_name} (近7天)',
             '━━━━━━━━━━━━━━━━━━━━━']
    if not stats:
        lines.append('暂无SLA数据')
    else:
        _labels = {
            'first_response':     '首次响应',
            'status_update':      '状态更新',
            'follow_up_response': '跟进响应',
        }
        for ev_type, row in stats.items():
            label = _labels.get(ev_type, ev_type)
            cfg = config_map.get(ev_type, {})
            target = cfg.get('target_minutes', '?')
            pct = row['compliance_pct']
            avg = row['avg_minutes']
            met = row['met']
            total = row['total']
            status_icon = '✅' if pct >= 80 else ('⚠️' if pct >= 60 else '❌')
            lines.append(
                f'{status_icon} {label}: {pct}% ({met}/{total}次) | '
                f'平均{avg}分钟 (目标{target}分钟)')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def _show_team_sla(chat_id: int, team: str):
    summary = await database_v2.get_staff_sla_summary(days=7)
    if team:
        # Filter to team members
        all_staff = await database_v2.get_all_staff()
        team_ids = {s.id for s in all_staff if s.team == team}
        summary = [r for r in summary if r['staff_id'] in team_ids]

    lines = [f'📊 团队SLA仪表板 (近7天)',
             '━━━━━━━━━━━━━━━━━━━━━']
    if not summary:
        lines.append('暂无SLA数据')
    else:
        total_met = sum(r['met'] for r in summary)
        total_all = sum(r['total'] for r in summary)
        team_pct = round(total_met / total_all * 100, 1) if total_all > 0 else 0.0
        lines.append(f'🏆 团队合规率: {team_pct}% ({total_met}/{total_all}次)')
        lines.append('')
        for r in summary[:10]:
            pct = r['compliance_pct']
            icon = '✅' if pct >= 80 else ('⚠️' if pct >= 60 else '❌')
            lines.append(
                f'{icon} {r["display_name"]}: {pct}% | 平均{r["avg_minutes"]}分钟')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def _handle_sla_config(chat_id: int, parts: list):
    if len(parts) < 2:
        await telegram_handler.send_message(
            chat_id,
            '用法: /sla config <类型> <目标分钟> [警告分钟] [危急分钟]\n'
            '类型: first_response | status_update | follow_up_response\n'
            '例: /sla config first_response 30 20 45')
        return

    ev_type = parts[0]
    valid_types = {'first_response', 'status_update', 'follow_up_response'}
    if ev_type not in valid_types:
        await telegram_handler.send_message(
            chat_id, f'❌ 无效类型。有效类型: {", ".join(valid_types)}')
        return

    try:
        target = int(parts[1])
        warn = int(parts[2]) if len(parts) > 2 else int(target * 0.67)
        crit = int(parts[3]) if len(parts) > 3 else int(target * 1.5)
    except ValueError:
        await telegram_handler.send_message(chat_id, '❌ 分钟数必须是整数')
        return

    await database_v2.set_sla_config(ev_type, target, warn, crit)
    await telegram_handler.send_message(
        chat_id,
        f'✅ SLA配置已更新:\n'
        f'类型: {ev_type}\n'
        f'目标: {target}分钟 | 警告: {warn}分钟 | 危急: {crit}分钟')


SLA_COMMANDS = {
    'sla': handle_sla,
}
SLA_CALLBACKS: Dict = {}
SLA_CONVERSATIONS: Dict = {}

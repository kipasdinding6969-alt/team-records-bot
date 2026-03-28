"""V2 management handlers — /dashboard, /team, /target, /export, /sync."""
import csv
import io
import logging
from datetime import date, timedelta
from typing import Any, Dict

from database_v2 import database_v2
from models_v2 import PeriodType, Staff, TeamTarget
from i18n import t
from telegram_handler import telegram_handler

logger = logging.getLogger(__name__)


async def _get_staff(user_id: int):
    return await database_v2.get_staff_by_tg_id(user_id)


async def handle_dashboard(task_data: Dict[str, Any]):
    """/dashboard — team overview for managers."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'dashboard'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_manager_only', staff.language))
        return

    lang = staff.language
    today = date.today()

    await database_v2.recalculate_all_today_stats()
    stats_list = await database_v2.get_team_daily_stats(today)

    all_staff = await database_v2.get_all_staff()
    staff_map = {s.id: s for s in all_staff}

    totals = dict(new_leads=0, contacted=0, replied=0, registered=0,
                  training=0, withdrew=0, new_orders=0, total_deposit=0.0)
    for stat in stats_list:
        for k in totals:
            totals[k] += getattr(stat, k, 0)

    today_str = today.strftime('%Y-%m-%d')
    lines = [t('dashboard_title', lang), f'📅 {today_str}', '']
    lines.append(t('team_stats_title', lang))
    lines.append(f'👥 {t("active_frontdesks", lang)}: {len(all_staff)}')
    lines.append(f'🆕 {t("new_leads_label", lang)}: {totals["new_leads"]}')
    lines.append(f'✅ {t("registered_label", lang)}: {totals["registered"]}')
    lines.append(f'🎯 {t("orders_label", lang)}: {totals["new_orders"]}')
    if totals['total_deposit']:
        lines.append(f'💵 {t("total_deposit_label", lang)}: ${totals["total_deposit"]:.2f}')

    lines.append('')
    lines.append(t('individual_breakdown', lang))
    for stat in sorted(stats_list, key=lambda s: s.new_leads, reverse=True)[:10]:
        member = staff_map.get(stat.staff_id)
        name = member.display_name if member else f'Staff#{stat.staff_id}'
        lines.append(f'• {name}: 🆕{stat.new_leads} ✅{stat.registered} 🎯{stat.new_orders}')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_team_stats(task_data: Dict[str, Any]):
    """/team <name> — stats for a specific team."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'team'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_manager_only', staff.language))
        return

    lang = staff.language
    team_name = args or staff.team

    if not team_name:
        await telegram_handler.send_message(chat_id, t('team_usage', lang))
        return

    all_staff = await database_v2.get_all_staff()
    team_members = [s for s in all_staff if s.team == team_name]

    if not team_members:
        await telegram_handler.send_message(chat_id, t('team_not_found', lang, team=team_name))
        return

    today = date.today()
    lines = [t('team_report_title', lang, team=team_name), f'📅 {today}', '']

    total_new = 0
    for member in team_members:
        stat = await database_v2.get_daily_stats(member.id, today)
        if stat:
            total_new += stat.new_leads
            lines.append(f'• {member.display_name}: 🆕{stat.new_leads} ✅{stat.registered} 🎯{stat.new_orders}')
        else:
            lines.append(f'• {member.display_name}: —')

    lines.append('')
    lines.append(t('pipeline_total', lang, total=total_new))

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_target(task_data: Dict[str, Any]):
    """/target [set <team> <leads> <registers> <orders>] — view or set team targets."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'target'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language
    today = date.today()

    if args.lower().startswith('set '):
        if not staff.is_manager_or_above():
            await telegram_handler.send_message(chat_id, t('err_manager_only', lang))
            return
        parts = args.split()
        if len(parts) < 5:
            await telegram_handler.send_message(chat_id, t('target_set_usage', lang))
            return
        _, team_name, leads_s, registers_s, orders_s = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            leads = int(leads_s)
            registers = int(registers_s)
            orders = int(orders_s)
        except ValueError:
            await telegram_handler.send_message(chat_id, t('target_set_usage', lang))
            return
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        target = TeamTarget(
            team=team_name,
            period_type=PeriodType.WEEKLY,
            period_start=week_start,
            period_end=week_end,
            target_leads=leads,
            target_registers=registers,
            target_orders=orders,
            created_by=staff.id,
        )
        await database_v2.upsert_team_target(target)
        await telegram_handler.send_message(
            chat_id, t('target_set_success', lang,
                        team=team_name, leads=leads, registers=registers, orders=orders))
        return

    team = staff.team or 'default'
    week_start = today - timedelta(days=today.weekday())

    target = await database_v2.get_team_target(team, PeriodType.WEEKLY, week_start)

    if not target:
        await telegram_handler.send_message(
            chat_id, t('no_target_set', lang, team=team))
        return

    lines = [t('target_title', lang, team=team), '']
    if target.target_leads:
        lines.append(f'🆕 {t("new_leads_label", lang)}: {target.target_leads}')
    if target.target_registers:
        lines.append(f'✅ {t("registered_label", lang)}: {target.target_registers}')
    if target.target_orders:
        lines.append(f'🎯 {t("orders_label", lang)}: {target.target_orders}')
    if target.target_deposit:
        lines.append(f'💵 {t("total_deposit_label", lang)}: ${target.target_deposit:.2f}')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_export(task_data: Dict[str, Any]):
    """/export — export clients as CSV."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'export'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language

    if staff.is_manager_or_above():
        rows = await database_v2.export_clients_csv()
    else:
        rows = await database_v2.export_clients_csv(frontdesk_id=staff.id)

    if not rows:
        await telegram_handler.send_message(chat_id, t('export_empty', lang))
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = output.getvalue().encode('utf-8-sig')

    filename = f'clients_{date.today().isoformat()}.csv'
    try:
        await telegram_handler.send_file(chat_id, csv_bytes, filename)
    except Exception:
        preview_lines = [t('export_success', lang, count=len(rows)), '']
        for r in rows[:20]:
            preview_lines.append(f"{r.get('phone','')} | {r.get('status','')} | {r.get('source','')}")
        if len(rows) > 20:
            preview_lines.append(t('and_more_clients', lang, count=len(rows) - 20))
        await telegram_handler.send_message(chat_id, '\n'.join(preview_lines))


async def handle_sync(task_data: Dict[str, Any]):
    """/sync — force full Sheets sync + dashboard refresh (admin only)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'sync'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_manager_only', staff.language))
        return

    lang = staff.language
    await telegram_handler.send_message(chat_id, t('sync_started', lang))

    import engines.sheet_sync_v2 as _sync_mod
    import engines.dashboard_sheets as _dash_mod

    imported = exported = 0
    tabs_refreshed = 0
    errors = []

    if _sync_mod.sheet_sync_v2 is not None:
        try:
            stats = await _sync_mod.sheet_sync_v2.full_sync()
            imported = stats.get('total_imported', 0)
            exported = stats.get('total_exported', 0)
        except Exception as e:
            errors.append(f'sync: {e}')
            logger.error(f'handle_sync: full_sync error: {e}')
    else:
        errors.append('Sheets not connected')

    if _dash_mod.dashboard_sheets is not None:
        try:
            await _dash_mod.dashboard_sheets.refresh_all_tabs()
            tabs_refreshed = 5
        except Exception as e:
            errors.append(f'dashboard: {e}')
            logger.error(f'handle_sync: dashboard refresh error: {e}')

    if errors:
        await telegram_handler.send_message(
            chat_id, t('sync_error', lang, error='; '.join(errors)))
    else:
        await telegram_handler.send_message(
            chat_id,
            t('sync_complete', lang, imported=imported, exported=exported, tabs=tabs_refreshed))


MANAGEMENT_COMMANDS = {
    'dashboard': handle_dashboard,
    'team': handle_team_stats,
    'target': handle_target,
    'export': handle_export,
    'sync': handle_sync,
}

MANAGEMENT_CALLBACKS = {}
MANAGEMENT_CONVERSATIONS = {}

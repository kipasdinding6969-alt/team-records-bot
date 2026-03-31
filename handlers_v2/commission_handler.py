"""Phase 10A: Commission tracking handler — commands + callbacks."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff, require_permission, resolve_team_scope

logger = logging.getLogger(__name__)


@require_permission('commission')
async def handle_commission(task_data: Dict[str, Any]):
    """Handle /commission command with subcommands."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()
    staff = await _get_staff(user_id)
    if not staff:
        return
    lang = staff.language or 'zh'

    parts = args.split() if args else []
    subcmd = parts[0] if parts else ''

    if subcmd == 'rules':
        await _show_rules(chat_id, staff)
    elif subcmd == 'set' and len(parts) >= 4:
        await _set_rule(chat_id, staff, parts[1], parts[2], parts[3])
    elif subcmd == 'approve':
        try:
            target_staff_id = int(parts[1]) if len(parts) > 1 else None
        except ValueError:
            await telegram_handler.send_message(chat_id, "Invalid staff ID.")
            return
        period = parts[2] if len(parts) > 2 else None
        await _approve_commissions(chat_id, staff, target_staff_id, period)
    elif subcmd == 'team':
        period = parts[1] if len(parts) > 1 else None
        await _show_team_commission(chat_id, staff, period)
    else:
        period = subcmd if subcmd else None
        await _show_my_commission(chat_id, staff, period)


async def _show_my_commission(chat_id: int, staff, period: str = None):
    """Show personal commission for a period."""
    if not period:
        period = database_v2._current_week_period()

    summary = await database_v2.get_commission_summary(staff_id=staff.id, period=period)
    commissions = await database_v2.get_commissions(staff_id=staff.id, period=period)

    text = f"💰 Commission — {period}\n"
    text += "━" * 25 + "\n"
    text += f"Total: ${summary['total_amount']:.2f}\n"
    text += f"Pending: ${summary['pending_amount']:.2f}\n"
    text += f"Approved: ${summary['approved_amount']:.2f}\n"
    text += f"Paid: ${summary['paid_amount']:.2f}\n"

    if commissions:
        text += "\nBreakdown:\n"
        for c in commissions[:10]:
            status_icon = {'pending': '⏳', 'approved': '✅', 'paid': '💵', 'rejected': '❌'}.get(c.status, '❓')
            text += f"  {status_icon} {c.trigger_type}: ${c.amount:.2f}\n"

    buttons = _commission_buttons(staff.id, period)
    await telegram_handler.send_message(chat_id, text, reply_markup={'inline_keyboard': buttons})


async def _show_team_commission(chat_id: int, staff, period: str = None):
    """Show team commission breakdown (manager+)."""
    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not period:
        period = database_v2._current_week_period()

    team = resolve_team_scope({}, staff)
    summary = await database_v2.get_commission_summary(period=period, team=team)

    # Per-staff breakdown
    all_staff = await database_v2.get_all_staff()
    team_staff = [s for s in all_staff if not team or s.team == team]

    text = f"💰 Team Commission — {period}\n"
    text += "━" * 25 + "\n"
    text += f"Total: ${summary['total_amount']:.2f}\n"
    text += f"Pending: ${summary['pending_amount']:.2f}\n\n"
    text += "Staff Breakdown:\n"

    for s in team_staff:
        s_summary = await database_v2.get_commission_summary(staff_id=s.id, period=period)
        if s_summary['total_count'] > 0:
            text += f"  {s.display_name}: ${s_summary['total_amount']:.2f} ({s_summary['total_count']} items)\n"

    await telegram_handler.send_message(chat_id, text)


async def _show_rules(chat_id: int, staff):
    """Show active commission rules (admin only)."""
    if not staff.is_admin():
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    rules = await database_v2.get_active_commission_rules()
    if not rules:
        await telegram_handler.send_message(chat_id, "No active commission rules.")
        return

    text = "📋 Commission Rules\n" + "━" * 25 + "\n"
    for r in rules:
        rate_str = f"{r.rate_value * 100:.1f}%" if r.rate_type == 'percentage' else f"${r.rate_value:.2f}"
        team_str = r.team or 'All teams'
        text += f"\n{r.status_trigger} ({team_str}):\n"
        text += f"  Rate: {rate_str} ({r.rate_type})\n"
        if r.min_amount:
            text += f"  Min amount: ${r.min_amount:.2f}\n"
        if r.max_commission:
            text += f"  Cap: ${r.max_commission:.2f}\n"

    await telegram_handler.send_message(chat_id, text)


async def _set_rule(chat_id: int, staff, trigger: str, rate_type: str, rate_value_str: str):
    """Set commission rule (admin only)."""
    if not staff.is_admin():
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    valid_triggers = ('deposit', 'first_deposit', 'registration')
    valid_types = ('percentage', 'fixed')
    if trigger not in valid_triggers:
        await telegram_handler.send_message(chat_id, f"Invalid trigger. Use: {', '.join(valid_triggers)}")
        return
    if rate_type not in valid_types:
        await telegram_handler.send_message(chat_id, f"Invalid rate type. Use: {', '.join(valid_types)}")
        return

    try:
        rate_value = float(rate_value_str)
    except ValueError:
        await telegram_handler.send_message(chat_id, "Invalid rate value.")
        return

    rule_id = await database_v2.set_commission_rule(trigger, rate_type, rate_value)
    await telegram_handler.send_message(chat_id, f"✅ Commission rule updated: {trigger} = {rate_value} ({rate_type})")


async def _approve_commissions(chat_id: int, staff, target_staff_id: int = None, period: str = None):
    """Approve pending commissions (manager+)."""
    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not period:
        period = database_v2._current_week_period()

    count = await database_v2.approve_commissions(staff.id, target_staff_id, period)
    await telegram_handler.send_message(chat_id, f"✅ Approved {count} commission(s) for {period}")


def _commission_buttons(staff_id: int, period: str):
    """Build inline keyboard for commission display."""
    now = datetime.utcnow()
    week = f'{now.year}-W{now.isocalendar()[1]:02d}'
    month = f'{now.year}-{now.month:02d}'
    last_week_dt = now - timedelta(weeks=1)
    lw_iso = last_week_dt.isocalendar()
    last_week = f'{lw_iso[0]}-W{lw_iso[1]:02d}'

    return [
        [
            {'text': '✅ Approve All', 'callback_data': f'comm:approve:{period}'},
            {'text': '📊 Breakdown', 'callback_data': f'comm:detail:{staff_id}:{period}'},
        ],
        [
            {'text': '📅 Last Week', 'callback_data': f'comm:period:{last_week}'},
            {'text': '📅 This Month', 'callback_data': f'comm:period:{month}'},
        ],
    ]


async def handle_commission_callback(task_data: Dict[str, Any]):
    """Handle commission inline keyboard callbacks."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback_data = task_data.get('callback_data', '')
    staff = await _get_staff(user_id)
    if not staff:
        return

    parts = callback_data.split(':')
    if len(parts) < 3:
        return

    action = parts[1]

    if action == 'approve':
        period = parts[2]
        if staff.is_manager_or_above():
            count = await database_v2.approve_commissions(staff.id, period=period)
            await telegram_handler.send_message(chat_id, f"✅ Approved {count} commission(s)")
        else:
            await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))

    elif action == 'detail':
        try:
            s_id = int(parts[2])
        except ValueError:
            return
        period = parts[3] if len(parts) > 3 else None
        commissions = await database_v2.get_commissions(staff_id=s_id, period=period)
        text = f"📊 Commission Detail — {period or 'all'}\n" + "━" * 25 + "\n"
        for c in commissions[:20]:
            status_icon = {'pending': '⏳', 'approved': '✅', 'paid': '💵', 'rejected': '❌'}.get(c.status, '❓')
            text += f"{status_icon} {c.trigger_type}: ${c.amount:.2f} (client #{c.client_id})\n"
        if not commissions:
            text += "No commissions found.\n"
        await telegram_handler.send_message(chat_id, text)

    elif action == 'period':
        period = parts[2]
        await _show_my_commission(chat_id, staff, period)


async def auto_calculate_deposit_commission(staff_id: int, client_id: int,
                                             deposit_id: int, amount: float,
                                             team: str = None):
    """Hook: auto-create commission on deposit creation."""
    # Check if this is a first deposit
    is_first = await database_v2.is_first_deposit(client_id)

    # Standard deposit commission
    await database_v2.calculate_commission(
        staff_id=staff_id, client_id=client_id,
        deposit_id=deposit_id, trigger_type='deposit',
        amount=amount, team=team)

    # First deposit bonus
    if is_first:
        await database_v2.calculate_commission(
            staff_id=staff_id, client_id=client_id,
            deposit_id=deposit_id, trigger_type='first_deposit',
            amount=amount, team=team)


async def auto_calculate_registration_commission(client_id: int, new_status: str):
    """Hook: auto-create registration commission on status change to 'registered'."""
    if new_status != 'registered':
        return

    is_first = await database_v2.is_first_registration(client_id)
    if not is_first:
        return

    # Look up the client to get staff info
    client = await database_v2.get_client_by_id(client_id)
    if not client:
        return

    staff = await database_v2.get_staff_by_id(client.frontdesk_id)
    team = staff.team if staff else None

    await database_v2.calculate_commission(
        staff_id=client.frontdesk_id, client_id=client_id,
        deposit_id=None, trigger_type='registration',
        amount=0, team=team)


# ─── Handler registry ─────────────────────────────────────────────────────

COMMISSION_COMMANDS: Dict[str, Any] = {
    'commission': handle_commission,
}

COMMISSION_CALLBACKS: Dict[str, Any] = {
    'comm_*': handle_commission_callback,
}

COMMISSION_CONVERSATIONS: Dict = {}

"""Phase 10B: Advanced analytics & reports handler."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff, require_permission, resolve_team_scope

logger = logging.getLogger(__name__)


def _week_range(dt: Optional[datetime] = None):
    """Return (start, end) date strings for the ISO week containing dt."""
    if dt is None:
        dt = datetime.utcnow()
    iso = dt.isocalendar()
    start = datetime.strptime(f'{iso[0]} {iso[1]} 1', '%G %V %u').date()
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _month_range(dt: Optional[datetime] = None):
    """Return (start, end) date strings for the month containing dt."""
    if dt is None:
        dt = datetime.utcnow()
    start = dt.replace(day=1).date()
    if dt.month == 12:
        end = dt.replace(year=dt.year + 1, month=1, day=1).date() - timedelta(days=1)
    else:
        end = dt.replace(month=dt.month + 1, day=1).date() - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _last_week_range():
    """Return (start, end) for last week."""
    return _week_range(datetime.utcnow() - timedelta(weeks=1))


def _bar(value: int, max_value: int, width: int = 20) -> str:
    """Render a text bar chart segment."""
    if max_value <= 0:
        return ''
    filled = max(1, round(value / max_value * width))
    return '█' * filled


@require_permission('report')
async def handle_report(task_data: Dict[str, Any]):
    """Handle /report command."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()
    staff = await _get_staff(user_id)
    if not staff:
        return

    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    parts = args.split() if args else []
    subcmd = parts[0] if parts else 'weekly'
    team = resolve_team_scope(task_data, staff)

    if subcmd == 'compare' and len(parts) >= 3:
        await _report_compare(chat_id, staff, parts[1], parts[2], team)
    elif subcmd == 'monthly':
        await _report_monthly(chat_id, staff, team)
    else:
        await _report_weekly(chat_id, staff, team)


async def _report_weekly(chat_id: int, staff, team: Optional[str] = None):
    """Generate weekly report."""
    now = datetime.utcnow()
    period_start, period_end = _week_range(now)
    iso = now.isocalendar()
    week_label = f"Week {iso[1]} ({period_start} — {period_end})"

    await _generate_report(chat_id, staff, period_start, period_end, week_label, team)


async def _report_monthly(chat_id: int, staff, team: Optional[str] = None):
    """Generate monthly report."""
    now = datetime.utcnow()
    period_start, period_end = _month_range(now)
    month_label = f"{now.strftime('%B %Y')} ({period_start} — {period_end})"

    await _generate_report(chat_id, staff, period_start, period_end, month_label, team)


async def _generate_report(chat_id: int, staff, period_start: str, period_end: str,
                            label: str, team: Optional[str] = None):
    """Build and send the report text."""
    # Pipeline stats
    rates = await database_v2.get_conversion_rates(period_start, period_end, team)
    deposit_total = await database_v2.get_deposit_total(period_start, period_end, team)
    rankings = await database_v2.get_staff_rankings(period_start, period_end, team, 'deposits')
    stale = await database_v2.get_stale_clients_analytics(days=7, team=team)

    # Commission summary
    comm_summary = await database_v2.get_commission_summary(period=None, team=team)

    text = f"📊 Report — {label}\n"
    text += "━" * 30 + "\n\n"

    # Pipeline summary
    text += "Pipeline Summary:\n"
    text += f"├ New clients: {rates.get('total', 0)}\n"
    text += f"├ Contacted: {rates.get('contacted', 0)} ({rates.get('contact_rate', 0)}% contact rate)\n"
    text += f"├ Replied: {rates.get('replied', 0)} ({rates.get('reply_rate', 0)}% reply rate)\n"
    text += f"├ Registered: {rates.get('registered', 0)} ({rates.get('register_rate', 0)}% register rate)\n"
    text += f"├ Deposited: {rates.get('deposited', 0)} ({rates.get('deposit_rate', 0)}% deposit rate)\n"
    text += f"└ Total deposits: ${deposit_total:,.2f}\n"

    # Staff rankings
    if rankings:
        text += "\nStaff Rankings:\n"
        for i, r in enumerate(rankings[:5], 1):
            if r['count'] > 0:
                text += f"│ #{i} {r['display_name']} — {r['count']} deposits, ${r['total_amount']:,.2f}\n"

    # Commission summary
    if comm_summary['total_count'] > 0:
        text += "\nCommission Summary:\n"
        text += f"├ Total earned: ${comm_summary['total_amount']:,.2f}\n"
        text += f"├ Pending approval: ${comm_summary['pending_amount']:,.2f}\n"
        text += f"└ Approved: ${comm_summary['approved_amount']:,.2f}\n"

    # Stale clients warning
    if stale:
        text += f"\n⚠️ {len(stale)} client(s) stale >7 days — need follow-up\n"

    await telegram_handler.send_message(chat_id, text)


async def _report_compare(chat_id: int, staff, period1: str, period2: str,
                           team: Optional[str] = None):
    """Compare two weekly periods."""
    # Parse periods like '2026-W13' into date ranges
    try:
        p1_start, p1_end = _parse_period(period1)
        p2_start, p2_end = _parse_period(period2)
    except ValueError:
        await telegram_handler.send_message(chat_id, "Invalid period format. Use YYYY-Wnn (e.g. 2026-W13)")
        return

    comparison = await database_v2.get_period_comparison(p1_start, p1_end, p2_start, p2_end, team)

    text = f"📊 Period Comparison: {period1} vs {period2}\n"
    text += "━" * 30 + "\n\n"

    for key in ['total', 'contacted', 'replied', 'registered', 'deposited']:
        data = comparison.get(key, {})
        delta = data.get('delta', 0)
        pct = data.get('pct_change', 0)
        arrow = '📈' if delta > 0 else ('📉' if delta < 0 else '➡️')
        text += f"{key.title()}: {data.get('current', 0)} vs {data.get('previous', 0)} "
        text += f"{arrow} {delta:+d} ({pct:+.1f}%)\n"

    await telegram_handler.send_message(chat_id, text)


def _parse_period(period: str):
    """Parse 'YYYY-Wnn' or 'YYYY-MM' into (start, end) date strings."""
    if '-W' in period:
        year, week = period.split('-W')
        start = datetime.strptime(f'{year} {int(week)} 1', '%G %V %u').date()
        end = start + timedelta(days=6)
        return start.isoformat(), end.isoformat()
    elif len(period) == 7:  # YYYY-MM
        year, month = period.split('-')
        dt = datetime(int(year), int(month), 1)
        return _month_range(dt)
    else:
        raise ValueError(f"Unknown period format: {period}")


@require_permission('funnel')
async def handle_funnel(task_data: Dict[str, Any]):
    """Handle /funnel command — conversion funnel visualization."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()
    staff = await _get_staff(user_id)
    if not staff:
        return

    team = resolve_team_scope(task_data, staff)
    period_start, period_end = _week_range()

    if args:
        try:
            period_start, period_end = _parse_period(args)
        except ValueError:
            await telegram_handler.send_message(chat_id, "Invalid period format. Use YYYY-Wnn or YYYY-MM.")
            return

    rates = await database_v2.get_conversion_rates(period_start, period_end, team)
    max_val = max(rates.get('total', 1), 1)

    stages = [
        ('New', rates.get('total', 0)),
        ('Contacted', rates.get('contacted', 0)),
        ('Replied', rates.get('replied', 0)),
        ('Registered', rates.get('registered', 0)),
        ('Deposited', rates.get('deposited', 0)),
    ]

    text = f"📈 Conversion Funnel — {period_start} to {period_end}\n"
    text += "━" * 27 + "\n"
    for label, count in stages:
        bar = _bar(count, max_val)
        pct = round(count / max_val * 100) if max_val > 0 else 0
        text += f"{bar} {count} {label} ({pct}%)\n"

    await telegram_handler.send_message(chat_id, text)


def format_funnel_text(rates: Dict, period_start: str, period_end: str) -> str:
    """Public helper to format funnel text (used by report and tests)."""
    max_val = max(rates.get('total', 1), 1)
    stages = [
        ('New', rates.get('total', 0)),
        ('Contacted', rates.get('contacted', 0)),
        ('Replied', rates.get('replied', 0)),
        ('Registered', rates.get('registered', 0)),
        ('Deposited', rates.get('deposited', 0)),
    ]
    text = f"📈 Conversion Funnel — {period_start} to {period_end}\n"
    text += "━" * 27 + "\n"
    for label, count in stages:
        bar = _bar(count, max_val)
        pct = round(count / max_val * 100) if max_val > 0 else 0
        text += f"{bar} {count} {label} ({pct}%)\n"
    return text


# ─── Handler registry ─────────────────────────────────────────────────────

REPORT_COMMANDS: Dict[str, Any] = {
    'report': handle_report,
    'funnel': handle_funnel,
}

REPORT_CALLBACKS: Dict[str, Any] = {}

REPORT_CONVERSATIONS: Dict = {}

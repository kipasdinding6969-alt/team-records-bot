"""Policy engine — all business rules as enforceable checks."""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Role Permissions ──────────────────────────────────────────────────────────

_FRONTDESK_CMDS = [
    'add', 'u', 'num', 'info', 'note', 'remind', 'req', 'me', 'pipeline', 'followup', 'today',
    'search', 'rag', 'handoff', 'profile', 'export', 'sop', 'bind',
    'leaderboard', 'hot', 'summary', 'template', 'contest',
]
_MAINTENANCE_CMDS = _FRONTDESK_CMDS + ['dashboard', 'team']
_ALL_COMMANDS = _MAINTENANCE_CMDS + ['target', 'overview', 'setname', 'lang', 'setteam', 'teams', 'linkgroup', 'unlinkgroup', 'bulkupdate']
_ADMIN_COMMANDS = _ALL_COMMANDS + ['sync']
_VIEWER_CMDS = ['me', 'dashboard', 'pipeline', 'search', 'rag', 'export', 'help', 'today', 'info', 'leaderboard']
_NEWBIE_CMDS = ['add', 'me', 'note', 'help', 'req', 'bind', 'info']
_CS_CMDS = ['search', 'note', 'info', 'pipeline', 'dashboard', 'rag', 'export', 'me', 'help', 'today', 'req', 'leaderboard', 'hot', 'summary', 'template']
# leader gets all commands (team-scoped)
_LEADER_CMDS = _ALL_COMMANDS

ROLE_PERMISSIONS: dict = {
    'frontdesk': _FRONTDESK_CMDS,
    'maintenance': _MAINTENANCE_CMDS,
    'manager': _ALL_COMMANDS,
    'admin': _ADMIN_COMMANDS,
    'leader': _LEADER_CMDS,
    'customer_service': _CS_CMDS,
    'newbie': _NEWBIE_CMDS,
    'viewer': _VIEWER_CMDS,
}


def check_permission(role: str, command: str) -> bool:
    """O(1) permission check. Returns True if role is allowed to run command."""
    allowed = ROLE_PERMISSIONS.get(role, [])
    return command in allowed


# ── Constants ─────────────────────────────────────────────────────────────────

TIMEZONE = 'Europe/Paris'
WORK_START = 10   # 10 AM
WORK_END = 22     # 10 PM

MAX_NEW_CLIENTS_PER_DAY = 50
STALE_WARNING_HOURS = 48
STALE_CRITICAL_HOURS = 72
AUTO_DEAD_DAYS = 14

HANDOFF_REQUIRED_STATUS = 'registered'
HANDOFF_NOTIFY_MAINTENANCE = True

ADMIN_REQUIRED_FOR: List[str] = [
    'delete_client',
    'change_role',
    'export_all',
    'set_target',
]

DEPOSIT_REQUIRES_CLIENT = True
MIN_DEPOSIT_AMOUNT = 1.0
MAX_KNIFE_NUMBER = 8

MAX_REMINDERS_PER_CLIENT = 5
MAX_NOTES_PER_DAY = 50
MIN_REMIND_MINUTES = 5
MAX_REMIND_DAYS = 30

NOTIFY_MAINTENANCE_ON: List[str] = [
    'client_stale_72h',
    'handoff_requested',
    'client_ordered',
    'client_withdrew',
]
NOTIFY_ADMIN_ON: List[str] = [
    'client_stale_7d',
    'daily_target_missed',
    'error_rate_high',
]


# ── Checks ────────────────────────────────────────────────────────────────────

async def check_can_add_client(staff_id: int) -> Tuple[bool, str]:
    """Check if staff can add another client today (max 50/day)."""
    try:
        from database_v2 import database_v2
        stat = await database_v2.calculate_daily_stats(staff_id)
        if stat.new_leads >= MAX_NEW_CLIENTS_PER_DAY:
            return False, f'Daily client limit reached ({MAX_NEW_CLIENTS_PER_DAY}/day). Try again tomorrow.'
        return True, ''
    except Exception as e:
        logger.warning(f'check_can_add_client error: {e}')
        return True, ''  # Fail open


async def check_can_handoff(client) -> Tuple[bool, str]:
    """Check if client is ready for handoff (must be registered+)."""
    from models_v2 import ClientStatus
    pipeline_order = [s.value for s in ClientStatus.pipeline_order()]
    registered_idx = pipeline_order.index('registered') if 'registered' in pipeline_order else 3
    try:
        current_idx = pipeline_order.index(client.status.value)
    except ValueError:
        return False, f'Client status "{client.status.value}" is not in pipeline — cannot handoff.'
    if current_idx < registered_idx:
        return False, f'Client must be at least "registered" before handoff (currently: {client.status.value}).'
    if client.status.value in ('blocked', 'scammed', 'dead'):
        return False, f'Cannot handoff terminal client ({client.status.value}).'
    return True, ''


def check_remind_limits(delta: timedelta) -> Tuple[bool, str]:
    """Check reminder timing against policy (5m min, 30d max)."""
    total_minutes = delta.total_seconds() / 60
    if total_minutes < MIN_REMIND_MINUTES:
        return False, f'Reminder must be at least {MIN_REMIND_MINUTES} minutes from now.'
    if total_minutes > MAX_REMIND_DAYS * 24 * 60:
        return False, f'Reminder cannot be more than {MAX_REMIND_DAYS} days out.'
    return True, ''


def check_working_hours() -> bool:
    """Check if current Paris time is within 10:00–22:00."""
    try:
        import pytz
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        return WORK_START <= now.hour < WORK_END
    except Exception:
        return True  # Fail open


async def enforce_on_status_change(client, new_status, staff) -> Tuple[bool, str]:
    """Master policy check before any status change.

    Returns (allowed, reason). Reason is empty string if allowed.
    """
    from models_v2 import ClientStatus
    # Can't change to 'ordered' without at least one deposit
    if new_status == ClientStatus.ORDERED:
        try:
            from database_v2 import database_v2
            deposits = await database_v2.get_deposits_by_client(client.id)
            if not deposits and client.total_deposited <= 0:
                return False, 'Cannot mark as ordered — no deposits recorded for this client.'
        except Exception as e:
            logger.warning(f'enforce_on_status_change deposit check error: {e}')

    return True, ''


async def auto_mark_dead_clients() -> int:
    """Mark clients dead after AUTO_DEAD_DAYS days of inactivity. Returns count."""
    try:
        from database_v2 import database_v2
        from models_v2 import ClientStatus
        dead_hours = AUTO_DEAD_DAYS * 24
        stale = await database_v2.get_all_stale_clients(hours=dead_hours)
        count = 0
        # Use a system staff_id=0 for auto-actions (will not exist in staff table, but that's OK for notes)
        for client in stale:
            if client.status not in ClientStatus.terminal_statuses():
                try:
                    await database_v2.update_client_status(client.id, ClientStatus.DEAD, 0)
                    count += 1
                    logger.info(f'Policy: auto-marked client {client.phone} as DEAD (14d inactive)')
                except Exception as e:
                    logger.warning(f'auto_mark_dead_clients failed for {client.phone}: {e}')
        return count
    except Exception as e:
        logger.error(f'auto_mark_dead_clients error: {e}')
        return 0


async def check_daily_targets_missed() -> List[dict]:
    """Check which teams missed their daily targets. Returns list of {team, target, actual}."""
    missed = []
    try:
        from datetime import date
        from database_v2 import database_v2
        from models_v2 import PeriodType
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        all_staff = await database_v2.get_all_staff()
        teams = set(s.team for s in all_staff if s.team)
        for team in teams:
            target = await database_v2.get_team_target(team, PeriodType.WEEKLY, week_start)
            if not target or not target.target_orders:
                continue
            members = [s for s in all_staff if s.team == team]
            total_orders = 0
            for m in members:
                stat = await database_v2.get_daily_stats(m.id, today)
                if stat:
                    total_orders += stat.new_orders
            daily_target = target.target_orders / 7
            if total_orders < daily_target * 0.5:  # Less than 50% of daily target
                missed.append({
                    'team': team,
                    'target': round(daily_target, 1),
                    'actual': total_orders,
                })
    except Exception as e:
        logger.warning(f'check_daily_targets_missed error: {e}')
    return missed

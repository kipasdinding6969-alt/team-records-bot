"""Phase 9C: SLA Engine — Ralph Loop integration for SLA breach detection and XP awards."""
import logging
from datetime import datetime
from typing import Optional

from database_v2 import database_v2

logger = logging.getLogger(__name__)

# XP awards for SLA compliance
XP_SLA_MET = 5      # +5 XP per SLA response met
XP_PERFECT_DAY = 20  # +20 bonus XP for perfect SLA day


async def check_sla_breaches(telegram_handler=None, team_leader_chat_id: Optional[int] = None):
    """
    Called by Ralph Loop every cycle.
    - Warns staff approaching SLA breach via PM.
    - Escalates to team leader if critical threshold exceeded.
    """
    open_events = await database_v2.get_open_sla_events()
    if not open_events:
        return

    configs_list = await database_v2.get_sla_config()
    configs = {c['event_type']: c for c in configs_list}

    now = datetime.utcnow()

    for ev in open_events:
        ev_type = ev.get('event_type', '')
        cfg = configs.get(ev_type, {})
        if not cfg:
            continue

        started_str = ev.get('started_at', '')
        try:
            started = datetime.fromisoformat(started_str)
        except Exception:
            continue

        elapsed_minutes = int((now - started).total_seconds() / 60)
        target = cfg.get('target_minutes', 60)
        warn = cfg.get('warning_minutes', target)
        crit = cfg.get('critical_minutes', target * 2)
        staff_chat = ev.get('tg_chat_id')
        staff_name = ev.get('staff_name', '')
        client_phone = ev.get('client_phone', '')

        if telegram_handler is None:
            continue

        if elapsed_minutes >= crit:
            # Critical — escalate to team leader
            msg = (
                f'🚨 SLA危急!\n'
                f'员工: {staff_name}\n'
                f'客户: {client_phone}\n'
                f'类型: {ev_type}\n'
                f'已超时: {elapsed_minutes}分钟 (危急阈值: {crit}分钟)'
            )
            if team_leader_chat_id:
                try:
                    await telegram_handler.send_message(team_leader_chat_id, msg)
                except Exception as e:
                    logger.warning(f'SLA critical escalation failed: {e}')
            # Also notify staff
            if staff_chat:
                try:
                    await telegram_handler.send_message(
                        staff_chat,
                        f'🚨 SLA已严重超时! 客户 {client_phone} 的{ev_type}已超 {elapsed_minutes} 分钟！')
                except Exception as e:
                    logger.warning(f'SLA staff critical notify failed: {e}')

        elif elapsed_minutes >= warn:
            # Warning — notify staff
            if staff_chat:
                remaining = target - elapsed_minutes
                try:
                    await telegram_handler.send_message(
                        staff_chat,
                        f'⚠️ SLA预警: 客户 {client_phone} 的{ev_type}\n'
                        f'已用 {elapsed_minutes} 分钟，还剩约 {remaining} 分钟达标。')
                except Exception as e:
                    logger.warning(f'SLA warning notify failed: {e}')


async def award_sla_xp(staff_id: int, met: bool):
    """Award XP based on SLA outcome. Called when completing an SLA event."""
    if not met:
        return
    try:
        await database_v2.award_xp(staff_id, 'sla_met', XP_SLA_MET)
        logger.debug(f'SLA XP awarded: staff={staff_id} xp={XP_SLA_MET}')
    except Exception as e:
        logger.warning(f'SLA XP award failed: {e}')


async def check_perfect_sla_day(staff_id: int):
    """Award bonus XP if all of today's SLA events were met (perfect day)."""
    try:
        async with database_v2.get_connection() as db:
            cur = await db.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN met=1 THEN 1 ELSE 0 END) as met_count
                   FROM sla_events
                   WHERE staff_id=? AND DATE(created_at)=DATE('now')
                   AND completed_at IS NOT NULL""",
                (staff_id,))
            row = await cur.fetchone()
        if not row:
            return
        total = row['total'] or 0
        met_count = row['met_count'] or 0
        if total >= 3 and met_count == total:
            await database_v2.award_xp(staff_id, 'perfect_sla_day', XP_PERFECT_DAY)
            logger.info(f'Perfect SLA day bonus awarded: staff={staff_id}')
    except Exception as e:
        logger.warning(f'perfect_sla_day check failed: {e}')


async def open_sla_for_new_client(client_id: int, staff_id: int):
    """Open a 'first_response' SLA event when a new client is added."""
    try:
        configs = await database_v2.get_sla_config('first_response')
        if not configs:
            return
        target = configs[0]['target_minutes']
        await database_v2.start_sla_event(client_id, staff_id, 'first_response', target)
    except Exception as e:
        logger.warning(f'open_sla_for_new_client failed: {e}')


async def close_sla_on_status_update(client_id: int, staff_id: int, new_status: str):
    """Close any open SLA events for this client when status changes."""
    try:
        open_events = await database_v2.get_open_sla_events()
        for ev in open_events:
            if ev['client_id'] == client_id and ev['staff_id'] == staff_id:
                sla_id = ev['id']
                completed = await database_v2.complete_sla_event(sla_id)
                if completed:
                    # Determine if met
                    async with database_v2.get_connection() as db:
                        cur = await db.execute(
                            'SELECT met FROM sla_events WHERE id=?', (sla_id,))
                        row = await cur.fetchone()
                    if row:
                        await award_sla_xp(staff_id, bool(row['met']))
    except Exception as e:
        logger.warning(f'close_sla_on_status_update failed: {e}')

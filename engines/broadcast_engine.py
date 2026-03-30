"""Broadcast engine — send templated messages to filtered client segments via userbot."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from database_v2 import database_v2
from telegram_handler import telegram_handler

logger = logging.getLogger(__name__)

# Max 25 messages/second — sleep between sends
_SEND_INTERVAL = 1 / 25  # 0.04s


def _render_template(template: str, client: Dict[str, Any]) -> str:
    """Substitute {name}, {status}, {days_since_contact} in template."""
    name = client.get('nickname') or client.get('phone', '')
    status = client.get('status', '')
    contacted_at = client.get('contacted_at')
    if contacted_at:
        try:
            if isinstance(contacted_at, str):
                dt = datetime.fromisoformat(contacted_at.replace('Z', '+00:00'))
            else:
                dt = contacted_at
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (now - dt).days
        except Exception:
            days = 0
    else:
        days = 0
    return (template
            .replace('{name}', name)
            .replace('{status}', status)
            .replace('{days_since_contact}', str(days)))


async def get_segment_targets(segment_type: str, segment_value: str,
                              date_from: Optional[str] = None,
                              date_to: Optional[str] = None) -> List[Dict]:
    """Query clients matching the given segment filter."""
    return await database_v2.get_broadcast_targets(
        segment_type, segment_value, date_from, date_to)


async def send_broadcast(
    staff_id: int,
    template: str,
    segment_type: str,
    segment_value: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """Send broadcast to all clients in the segment.

    Uses Telethon userbot so messages appear as personal sends.

    Returns: {log_id, total, sent, failed, blocked}
    """
    targets = await get_segment_targets(segment_type, segment_value, date_from, date_to)
    total = len(targets)
    segment_filter = f'{segment_type}:{segment_value}'

    log_id = await database_v2.create_broadcast_log(
        staff_id=staff_id,
        template=template,
        segment_filter=segment_filter,
        total_targets=total,
    )

    sent = 0
    failed = 0
    blocked = 0

    for i, client in enumerate(targets):
        phone = client.get('phone', '').strip()
        if not phone:
            failed += 1
            continue

        text = _render_template(template, client)
        try:
            # Use userbot (Telethon user client) — looks like personal message
            await telegram_handler.client.send_message(phone, text)
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if 'blocked' in err or 'privacy' in err:
                blocked += 1
            else:
                failed += 1
            logger.debug(f'broadcast send failed for {phone}: {e}')

        # Rate limit: max 25/s
        await asyncio.sleep(_SEND_INTERVAL)

        # Progress callback every 5 sends
        if progress_callback and (i + 1) % 5 == 0:
            try:
                await progress_callback(i + 1, total)
            except Exception:
                pass

    await database_v2.update_broadcast_log(log_id, sent, failed + blocked, completed=True)

    return {
        'log_id': log_id,
        'total': total,
        'sent': sent,
        'failed': failed,
        'blocked': blocked,
    }


def get_segment_types() -> List[Tuple[str, str]]:
    """Return (segment_type, label_zh) pairs for inline keyboard."""
    return [
        ('status', '按状态'),
        ('team', '按团队'),
        ('source', '按来源'),
        ('date_range', '按日期范围'),
    ]


def get_status_values() -> List[Tuple[str, str]]:
    """Return (value, label_zh) pairs for status segment."""
    return [
        ('new', '新客户'),
        ('contacted', '已联系'),
        ('replied', '已回复'),
        ('registered', '已注册'),
        ('training', '培训中'),
        ('withdrew', '已提款'),
        ('ordered', '已下单'),
        ('ghosted', '未响应'),
    ]

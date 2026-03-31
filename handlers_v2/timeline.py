"""Phase 9B: Client Timeline — /timeline command."""
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

# Event type → display emoji + label
_EVENT_DISPLAY = {
    'status_change':  ('🔄', '状态变更'),
    'note_added':     ('📝', '备注'),
    'deposit':        ('💰', '入金'),
    'tag_added':      ('🏷️', '添加标签'),
    'tag_removed':    ('🏷️', '移除标签'),
    'voice_update':   ('📞', '语音更新'),
    'follow_up_sent': ('📤', '跟进发送'),
    'reminder_set':   ('⏰', '提醒设置'),
    'handoff':        ('🤝', '客户移交'),
    'client_created': ('🆕', '客户创建'),
}


def _format_event(ev: Dict) -> str:
    """Format a single timeline event row."""
    ev_type = ev.get('event_type', 'unknown')
    emoji, label = _EVENT_DISPLAY.get(ev_type, ('•', ev_type))
    staff_name = ev.get('staff_name') or ''
    created = ev.get('created_at', '')

    # Parse date/time
    try:
        dt = datetime.fromisoformat(created)
        ts = dt.strftime('%m-%d %H:%M')
    except Exception:
        ts = created[:16] if created else '?'

    # Build detail from event_data JSON
    detail = ''
    raw_data = ev.get('event_data')
    if raw_data:
        try:
            data = json.loads(raw_data)
            if ev_type == 'status_change':
                frm = data.get('from', '?')
                to = data.get('to', '?')
                detail = f'→ {to} (from {frm})'
            elif ev_type == 'note_added':
                note = data.get('note_preview', '')
                detail = f': "{note[:40]}"'
            elif ev_type == 'deposit':
                amount = data.get('amount', '')
                platform = data.get('platform', '')
                detail = f'${amount} via {platform}'
            elif ev_type in ('tag_added', 'tag_removed'):
                tag = data.get('tag', '')
                detail = f'[{tag}]'
            elif ev_type == 'voice_update':
                preview = data.get('preview', '')
                detail = f': "{preview[:40]}"' if preview else ''
            elif ev_type == 'handoff':
                frm = data.get('from_team', '')
                to = data.get('to_team', '')
                detail = f'{frm} → {to}'
            elif ev_type == 'client_created':
                by = data.get('by', staff_name)
                detail = f'by {by}'
        except Exception:
            detail = raw_data[:40] if raw_data else ''

    by_part = f' (by {staff_name})' if staff_name else ''
    return f'{emoji} {ts} — {label} {detail}{by_part}'.strip()


async def _resolve_client(staff_id: int, query: str, is_manager: bool = False):
    """Look up a client by phone or name."""
    client = await database_v2.get_client_by_phone(
        query, None if is_manager else staff_id)
    if client:
        return client
    matches = await database_v2.search_clients(
        staff_id if not is_manager else 0, query)
    if not matches and is_manager:
        async with database_v2.get_connection() as db:
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            q = f'%{escaped}%'
            cur = await db.execute(
                """SELECT * FROM clients
                   WHERE nickname LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\' OR account_id LIKE ? ESCAPE '\\'
                   ORDER BY updated_at DESC LIMIT 1""",
                (q, q, q))
            row = await cur.fetchone()
            if row:
                return database_v2._row_to_client(row)
    return matches[0] if matches else None


async def handle_timeline(task_data: Dict[str, Any]):
    """/timeline <phone_or_name> [count|today]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    if not args:
        await telegram_handler.send_message(
            chat_id,
            '用法: /timeline <手机号或姓名> [数量|today]\n'
            '例: /timeline 0123456789\n'
            '    /timeline 阿明 today')
        return

    parts = args.split()
    query = parts[0]
    modifier = parts[1].lower() if len(parts) > 1 else '10'

    today_only = modifier == 'today'
    try:
        limit = int(modifier) if not today_only else 50
    except ValueError:
        limit = 10

    from models_v2 import StaffRole
    is_manager = staff.role in (StaffRole.MANAGER, StaffRole.ADMIN)
    client = await _resolve_client(staff.id, query, is_manager)
    if not client:
        await telegram_handler.send_message(chat_id, f'❌ 找不到客户: {query}')
        return

    events = await database_v2.get_client_timeline(client.id, limit=limit, today_only=today_only)
    name = client.nickname or client.phone
    phone_display = client.phone if client.nickname else ''
    header_name = f'{name} ({phone_display})' if phone_display else name

    lines = [f'📋 Timeline: {header_name}',
             '━━━━━━━━━━━━━━━━━━━━━']

    if not events:
        if today_only:
            lines.append('今天暂无活动记录')
        else:
            lines.append('暂无活动记录')
    else:
        for ev in events:
            lines.append(_format_event(ev))

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


def log_status_change_event(client_id: int, staff_id: int,
                             old_status: str, new_status: str, by_name: str):
    """Convenience import for other handlers to log status change events."""
    import asyncio
    data = json.dumps({'from': old_status, 'to': new_status, 'by': by_name})
    return database_v2.log_event(client_id, 'status_change', data, staff_id)


TIMELINE_COMMANDS = {
    'timeline': handle_timeline,
}
TIMELINE_CALLBACKS: Dict = {}
TIMELINE_CONVERSATIONS: Dict = {}

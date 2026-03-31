"""Phase 9A: Smart Tags & Filters — /tag /untag /tags /filter commands."""
import json
import logging
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

# Quick-tag labels shown as inline buttons on client views
QUICK_TAGS = ['vip', 'whale', 'hot', 'problem', 'referral']
QUICK_TAG_EMOJIS = {
    'vip':      '🏷️',
    'whale':    '🐋',
    'hot':      '⭐',
    'problem':  '⚠️',
    'referral': '📎',
}


async def _resolve_client(staff_id: int, query: str, is_manager: bool = False):
    """Look up a client by phone or name. Returns Client or None."""
    # Try phone first
    client = await database_v2.get_client_by_phone(
        query, None if is_manager else staff_id)
    if client:
        return client
    # Fall back to name search
    matches = await database_v2.search_clients(
        staff_id if not is_manager else 0, query)
    # search_clients with id=0 won't match; re-run without scoping for managers
    if not matches and is_manager:
        async with database_v2.get_connection() as db:
            q = f'%{query}%'
            cur = await db.execute(
                """SELECT * FROM clients
                   WHERE nickname LIKE ? OR phone LIKE ? OR account_id LIKE ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (q, q, q))
            row = await cur.fetchone()
            if row:
                return database_v2._row_to_client(row)
    return matches[0] if matches else None


async def handle_tag(task_data: Dict[str, Any]):
    """/tag <phone_or_name> <tag1> [tag2...]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    parts = args.split()
    if len(parts) < 2:
        await telegram_handler.send_message(
            chat_id, '用法: /tag <手机号或姓名> <标签1> [标签2...]\n例: /tag 0123456789 vip whale')
        return

    query = parts[0]
    tags = [p.lower() for p in parts[1:]]

    from models_v2 import StaffRole
    is_manager = staff.role in (StaffRole.MANAGER, StaffRole.ADMIN)
    client = await _resolve_client(staff.id, query, is_manager)
    if not client:
        await telegram_handler.send_message(chat_id, f'❌ 找不到客户: {query}')
        return

    added = []
    skipped = []
    for tag in tags:
        ok = await database_v2.add_tag(client.id, tag, staff.id)
        if ok:
            added.append(tag)
            # Log timeline event
            await database_v2.log_event(
                client.id, 'tag_added',
                json.dumps({'tag': tag, 'by': staff.display_name}),
                staff.id)
        else:
            skipped.append(tag)

    name = client.nickname or client.phone
    lines = [f'🏷️ 标签更新: {name}']
    if added:
        lines.append(f'✅ 已添加: {" ".join(added)}')
    if skipped:
        lines.append(f'⚠️ 已存在: {" ".join(skipped)}')
    current = await database_v2.get_client_tags(client.id)
    if current:
        lines.append(f'📋 当前标签: {" ".join(current)}')
    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_untag(task_data: Dict[str, Any]):
    """/untag <phone_or_name> <tag>"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    parts = args.split()
    if len(parts) < 2:
        await telegram_handler.send_message(
            chat_id, '用法: /untag <手机号或姓名> <标签>')
        return

    query, tag = parts[0], parts[1].lower()

    from models_v2 import StaffRole
    is_manager = staff.role in (StaffRole.MANAGER, StaffRole.ADMIN)
    client = await _resolve_client(staff.id, query, is_manager)
    if not client:
        await telegram_handler.send_message(chat_id, f'❌ 找不到客户: {query}')
        return

    removed = await database_v2.remove_tag(client.id, tag)
    name = client.nickname or client.phone
    if removed:
        await database_v2.log_event(
            client.id, 'tag_removed',
            json.dumps({'tag': tag, 'by': staff.display_name}),
            staff.id)
        await telegram_handler.send_message(chat_id, f'✅ 已移除标签 [{tag}] 从 {name}')
    else:
        await telegram_handler.send_message(chat_id, f'⚠️ {name} 没有标签 [{tag}]')


async def handle_tags(task_data: Dict[str, Any]):
    """/tags [client] — show client tags or list all tags with counts."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from models_v2 import StaffRole
    is_manager = staff.role in (StaffRole.MANAGER, StaffRole.ADMIN)

    if args:
        # Show tags for a specific client
        client = await _resolve_client(staff.id, args, is_manager)
        if not client:
            await telegram_handler.send_message(chat_id, f'❌ 找不到客户: {args}')
            return
        tags = await database_v2.get_client_tags(client.id)
        name = client.nickname or client.phone
        if tags:
            tag_str = ' '.join(f'[{tag}]' for tag in tags)
            await telegram_handler.send_message(chat_id, f'🏷️ {name} 的标签:\n{tag_str}')
        else:
            await telegram_handler.send_message(chat_id, f'📋 {name} 暂无标签')
    else:
        # List all tags with counts scoped to team
        team = staff.team if not is_manager else None
        tags_counts = await database_v2.get_all_tags_with_counts(team)
        if not tags_counts:
            await telegram_handler.send_message(chat_id, '📋 暂无标签记录')
            return
        lines = ['🏷️ 标签统计:',
                 '━━━━━━━━━━━━━━']
        for item in tags_counts[:20]:
            emoji = QUICK_TAG_EMOJIS.get(item['tag'], '🔹')
            lines.append(f'{emoji} {item["tag"]}: {item["count"]}人')
        await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_filter(task_data: Dict[str, Any]):
    """/filter <criteria> — e.g. tag:vip status:replied stale:3d source:facebook registered:no"""
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
            '用法: /filter <条件>\n'
            '支持: tag:vip status:replied stale:3d source:facebook registered:no\n'
            '例: /filter tag:vip stale:2d')
        return

    # Parse criteria
    criteria: Dict = {}
    for part in args.split():
        if ':' in part:
            k, v = part.split(':', 1)
            if k == 'stale':
                # Parse "3d" → 3
                try:
                    criteria['stale'] = int(v.rstrip('d'))
                except ValueError:
                    pass
            else:
                criteria[k] = v
        else:
            criteria['tag'] = part  # bare word treated as tag

    from models_v2 import StaffRole
    is_manager = staff.role in (StaffRole.MANAGER, StaffRole.ADMIN)
    frontdesk_id = None if is_manager else staff.id
    team = staff.team if not is_manager else None

    clients = await database_v2.filter_clients_by_criteria(frontdesk_id, team, criteria)
    if not clients:
        await telegram_handler.send_message(chat_id, '🔍 没有符合条件的客户')
        return

    lines = [f'🔍 筛选结果 ({len(clients)}人):',
             '━━━━━━━━━━━━━━']
    for c in clients[:20]:
        name = c.get('nickname') or c.get('phone', '')
        status = c.get('status', '')
        fd_name = c.get('frontdesk_name', '')
        lines.append(f'• {name} [{status}] — {fd_name}')
    if len(clients) > 20:
        lines.append(f'...还有 {len(clients) - 20} 人')
    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_quicktag_callback(task_data: Dict[str, Any]):
    """Callback: quicktag_<client_id>_<tag>"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback_data = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    try:
        _, client_id_str, tag = callback_data.split('_', 2)
        client_id = int(client_id_str)
    except (ValueError, IndexError):
        return

    client = await database_v2.get_client_by_id(client_id)
    if not client:
        return

    added = await database_v2.add_tag(client_id, tag, staff.id)
    if added:
        await database_v2.log_event(
            client_id, 'tag_added',
            json.dumps({'tag': tag, 'by': staff.display_name}),
            staff.id)
        name = client.nickname or client.phone
        await telegram_handler.send_message(chat_id, f'✅ 已给 {name} 添加标签 [{tag}]')
    else:
        await telegram_handler.send_message(chat_id, f'⚠️ 标签 [{tag}] 已存在')


def build_quicktag_buttons(client_id: int) -> list:
    """Return inline button specs for quick-tagging a client."""
    return [
        {'text': f'{QUICK_TAG_EMOJIS[tag]} {tag.upper()}',
         'callback_data': f'quicktag_{client_id}_{tag}'}
        for tag in QUICK_TAGS
    ]


TAGS_COMMANDS = {
    'tag':    handle_tag,
    'untag':  handle_untag,
    'tags':   handle_tags,
    'filter': handle_filter,
}

TAGS_CALLBACKS = {
    'quicktag_*': handle_quicktag_callback,
}

TAGS_CONVERSATIONS: Dict = {}

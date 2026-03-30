"""Natural Language CRM Handler.

Intercepts plain-text messages from registered staff and routes them through
the NL engine to execute CRM operations without memorising slash commands.

Flow:
  text message → nl_engine.parse() → execute CRM op → card + inline buttons
  voice message → transcribe → nl_engine.parse() → same flow

Priority: lowest — only fires when no conversation state is active.
"""
import logging
from typing import Any, Dict, List, Optional

from database_v2 import database_v2
from models_v2 import Client, ClientNote, ClientStatus, NoteType
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

# ── Inline keyboard builders ────────────────────────────────────────────────

def _kb_client_actions(client_id: int) -> Any:
    return telegram_handler.create_inline_keyboard([[
        {'text': '📊 详情 / Details', 'callback_data': f'nl_client_detail:{client_id}'},
        {'text': '✏️ 更新状态 / Update', 'callback_data': f'nl_client_update:{client_id}'},
    ], [
        {'text': '📝 加备注 / Add Note', 'callback_data': f'nl_client_note:{client_id}'},
        {'text': '📞 下一个 / Next Client', 'callback_data': 'nl_next_client'},
    ]])


def _kb_status_updated(client_id: int) -> Any:
    return telegram_handler.create_inline_keyboard([[
        {'text': '✅ 确认 / Confirmed', 'callback_data': f'nl_ok:{client_id}'},
        {'text': '↩️ 撤销 / Undo', 'callback_data': f'nl_undo:{client_id}'},
    ], [
        {'text': '📊 查看客户 / View Client', 'callback_data': f'nl_client_detail:{client_id}'},
    ]])


def _kb_search_results() -> Any:
    return telegram_handler.create_inline_keyboard([[
        {'text': '📱 联系第一个 / Contact First', 'callback_data': 'nl_contact_first'},
        {'text': '📋 更多 / More', 'callback_data': 'nl_search_more'},
    ]])


def _kb_fallback_menu() -> Any:
    return telegram_handler.create_inline_keyboard([[
        {'text': '➕ 新客户 / New Client', 'callback_data': 'nl_menu_add'},
        {'text': '📊 我的管道 / Pipeline', 'callback_data': 'nl_menu_pipeline'},
    ], [
        {'text': '🏆 排行榜 / Leaderboard', 'callback_data': 'nl_menu_leaderboard'},
        {'text': '📬 跟进 / Follow-up', 'callback_data': 'nl_menu_followup'},
    ], [
        {'text': '🎤 语音更新 / Voice', 'callback_data': 'nl_menu_voice'},
        {'text': '❓ 帮助 / Help', 'callback_data': 'nl_menu_help'},
    ]])


def _kb_confirm_update(client_id: int, status: str) -> Any:
    return telegram_handler.create_inline_keyboard([[
        {'text': '✅ 确认更新 / Confirm', 'callback_data': f'nl_confirm_update:{client_id}:{status}'},
        {'text': '❌ 取消 / Cancel', 'callback_data': 'nl_cancel'},
    ]])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _resolve_client(staff_id: int, entities: Dict[str, Any]) -> Optional[Client]:
    """Find client by phone or name. Returns first match or None."""
    phone: Optional[str] = entities.get('phone')
    name: Optional[str] = entities.get('client_name')

    if phone:
        client = await database_v2.get_client_by_phone(phone, staff_id)
        if client:
            return client

    if name:
        matches = await database_v2.search_clients(staff_id, name)
        if matches:
            return matches[0]

    return None


def _client_card(client: Client) -> str:
    status_emoji = {
        'new': '🆕', 'contacted': '📞', 'replied': '💬',
        'registered': '✅', 'training': '🎓', 'withdrew': '↩️',
        'ordered': '🛒', 'ghosted': '👻', 'blocked': '🚫', 'dead': '💀',
    }
    emoji = status_emoji.get(client.status.value if hasattr(client.status, 'value') else str(client.status), '❓')
    name_line = f"姓名 / Name: **{client.nickname}**\n" if client.nickname else ''
    phone_line = f"电话 / Phone: `{client.phone}`\n" if client.phone else ''
    status_val = client.status.value if hasattr(client.status, 'value') else str(client.status)
    return (
        f"👤 **客户信息 / Client Info**\n"
        f"{name_line}"
        f"{phone_line}"
        f"状态 / Status: {emoji} {status_val}\n"
        f"来源 / Source: {client.source or '-'}"
    )


# ── Main handler ─────────────────────────────────────────────────────────────

async def handle_nl_message(task_data: Dict[str, Any]):
    """Handle plain-text NL message from a registered staff member.

    Sends '正在理解...' indicator, calls nl_engine.parse(), then dispatches
    the appropriate CRM operation and returns a result card.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    text: str = task_data.get('text', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        # Not registered — silently drop (registration handler handles this)
        return

    if not text:
        return

    # Typing indicator
    await telegram_handler.send_message(chat_id, '正在理解... / Processing...')

    from engines.nl_engine import (
        parse, QUERY_CLIENT, UPDATE_STATUS, ADD_NOTE,
        LIST_PIPELINE, SEARCH, HELP, UNKNOWN, CONFIDENCE_THRESHOLD,
    )

    result = await parse(text)
    intent = result['intent']
    confidence = result['confidence']
    entities = result['entities']

    logger.info(
        f"NL [{staff.display_name}]: {text[:60]!r} → {intent} "
        f"({confidence:.2f}) entities={entities}"
    )

    # Low confidence → show fallback menu
    if intent == UNKNOWN or confidence < CONFIDENCE_THRESHOLD:
        await _handle_fallback(chat_id, user_id, text)
        return

    if intent == QUERY_CLIENT:
        await _exec_query_client(chat_id, staff, entities)
    elif intent == UPDATE_STATUS:
        await _exec_update_status(chat_id, staff, entities)
    elif intent == ADD_NOTE:
        await _exec_add_note(chat_id, staff, entities)
    elif intent == LIST_PIPELINE:
        await _exec_list_pipeline(chat_id, staff, entities)
    elif intent == SEARCH:
        await _exec_search(chat_id, staff, entities)
    elif intent == HELP:
        await _exec_help(chat_id)
    else:
        await _handle_fallback(chat_id, user_id, text)


async def _handle_fallback(chat_id: int, user_id: int, original_text: str):
    """Show contextual help + quick-action keyboard."""
    msg = (
        "🤔 **没明白 / Not sure what you mean**\n\n"
        f"你说: _{original_text[:80]}_\n\n"
        "请选择操作 / Please choose an action:"
    )
    await telegram_handler.send_message(
        chat_id, msg, reply_markup=_kb_fallback_menu(), parse_mode='markdown'
    )


async def _exec_query_client(chat_id: int, staff: Any, entities: Dict[str, Any]):
    client = await _resolve_client(staff.id, entities)
    if not client:
        identifier = entities.get('client_name') or entities.get('phone') or '?'
        msg = f"❌ 找不到客户 / Client not found: **{identifier}**"
        await telegram_handler.send_message(chat_id, msg, parse_mode='markdown',
                                            reply_markup=_kb_fallback_menu())
        return

    card = _client_card(client)
    await telegram_handler.send_message(
        chat_id, card, parse_mode='markdown',
        reply_markup=_kb_client_actions(client.id)
    )


async def _exec_update_status(chat_id: int, staff: Any, entities: Dict[str, Any]):
    status_str: Optional[str] = entities.get('status')
    client = await _resolve_client(staff.id, entities)

    if not client:
        identifier = entities.get('client_name') or entities.get('phone') or '?'
        msg = f"❌ 找不到客户 / Client not found: **{identifier}**"
        await telegram_handler.send_message(chat_id, msg, parse_mode='markdown',
                                            reply_markup=_kb_fallback_menu())
        return

    if not status_str:
        # Ask which status to set
        msg = (
            f"👤 找到客户 / Found client: **{client.nickname or client.phone}**\n"
            "想更新到哪个状态 / Which status to update to?\n"
            "请输入状态名称: new / contacted / replied / registered / training / withdrew / ordered"
        )
        await telegram_handler.set_conversation_state(staff.tg_user_id, {
            'step': 'nl_await_status',
            'pending': {'client_id': client.id},
        })
        await telegram_handler.send_message(chat_id, msg, parse_mode='markdown')
        return

    try:
        new_status = ClientStatus(status_str)
    except ValueError:
        await telegram_handler.send_message(
            chat_id, f"❌ 无效状态 / Invalid status: {status_str}",
            reply_markup=_kb_fallback_menu()
        )
        return

    # Ask for confirmation before writing
    name_display = client.nickname or client.phone or str(client.id)
    msg = (
        f"确认更新？/ Confirm update?\n\n"
        f"👤 客户 / Client: **{name_display}**\n"
        f"📌 新状态 / New status: **{status_str}**"
    )
    await telegram_handler.send_message(
        chat_id, msg, parse_mode='markdown',
        reply_markup=_kb_confirm_update(client.id, status_str)
    )


async def _exec_add_note(chat_id: int, staff: Any, entities: Dict[str, Any]):
    note_text: Optional[str] = entities.get('note')
    client = await _resolve_client(staff.id, entities)

    if not client:
        identifier = entities.get('client_name') or entities.get('phone') or '?'
        msg = f"❌ 找不到客户 / Client not found: **{identifier}**"
        await telegram_handler.send_message(chat_id, msg, parse_mode='markdown',
                                            reply_markup=_kb_fallback_menu())
        return

    if not note_text:
        msg = (
            f"👤 找到客户 / Found: **{client.nickname or client.phone}**\n"
            "请输入备注内容 / Please enter the note:"
        )
        await telegram_handler.set_conversation_state(staff.tg_user_id, {
            'step': 'nl_await_note',
            'pending': {'client_id': client.id},
        })
        await telegram_handler.send_message(chat_id, msg, parse_mode='markdown')
        return

    cn = ClientNote(
        client_id=client.id,
        staff_id=staff.id,
        note_type=NoteType.NOTE,
        content=note_text,
    )
    await database_v2.add_client_note(cn)

    name_display = client.nickname or client.phone or str(client.id)
    msg = (
        f"✅ **备注已添加 / Note added**\n\n"
        f"👤 {name_display}\n"
        f"📝 {note_text}"
    )
    await telegram_handler.send_message(
        chat_id, msg, parse_mode='markdown',
        reply_markup=_kb_client_actions(client.id)
    )


async def _exec_list_pipeline(chat_id: int, staff: Any, entities: Dict[str, Any]):
    counts = await database_v2.get_pipeline_counts(staff.id)
    status_filter: Optional[str] = entities.get('status')

    if status_filter:
        count = counts.get(status_filter, 0)
        msg = (
            f"📊 **管道查询 / Pipeline Query**\n\n"
            f"状态 / Status: **{status_filter}**\n"
            f"数量 / Count: **{count}**"
        )
    else:
        lines = ['📊 **我的管道 / My Pipeline**\n']
        status_order = ['new', 'contacted', 'replied', 'registered', 'training', 'withdrew', 'ordered']
        for s in status_order:
            n = counts.get(s, 0)
            if n > 0:
                lines.append(f"  {s}: **{n}**")
        total = sum(counts.get(s, 0) for s in status_order)
        lines.append(f"\n总计 / Total: **{total}**")
        msg = '\n'.join(lines)

    await telegram_handler.send_message(
        chat_id, msg, parse_mode='markdown',
        reply_markup=telegram_handler.create_inline_keyboard([[
            {'text': '📊 详细视图 / Full View', 'callback_data': 'pipeline'},
            {'text': '🏠 菜单 / Menu', 'callback_data': 'nl_menu_pipeline'},
        ]])
    )


async def _exec_search(chat_id: int, staff: Any, entities: Dict[str, Any]):
    status_str: Optional[str] = entities.get('status')
    query: Optional[str] = entities.get('client_name') or entities.get('phone')

    clients: List[Client] = []

    if status_str:
        try:
            status_enum = ClientStatus(status_str)
            clients = await database_v2.get_clients_by_status(staff.id, status_enum)
        except ValueError:
            pass

    if not clients and query:
        clients = await database_v2.search_clients(staff.id, query)

    if not clients:
        criteria = status_str or query or '?'
        msg = f"🔍 **没有找到 / No results for:** {criteria}"
        await telegram_handler.send_message(chat_id, msg, parse_mode='markdown',
                                            reply_markup=_kb_fallback_menu())
        return

    lines = [f"🔍 **搜索结果 / Search Results** ({len(clients)} 个)\n"]
    for i, c in enumerate(clients[:10], 1):
        status_val = c.status.value if hasattr(c.status, 'value') else str(c.status)
        name = c.nickname or c.phone or f'#{c.id}'
        lines.append(f"{i}. **{name}** — {status_val}")

    if len(clients) > 10:
        lines.append(f"\n...还有 {len(clients) - 10} 个 / {len(clients) - 10} more")

    msg = '\n'.join(lines)
    await telegram_handler.send_message(
        chat_id, msg, parse_mode='markdown',
        reply_markup=_kb_search_results()
    )


async def _exec_help(chat_id: int):
    msg = (
        "💡 **自然语言使用指南 / Natural Language Guide**\n\n"
        "📌 **查客户 / Lookup:**\n"
        "  `阿明什么情况`\n"
        "  `查一下 0123456789`\n\n"
        "📌 **更新状态 / Update:**\n"
        "  `阿明已经注册了`\n"
        "  `0123456789 下单了`\n\n"
        "📌 **加备注 / Add Note:**\n"
        "  `给阿明备注：今天有兴趣`\n\n"
        "📌 **管道统计 / Pipeline:**\n"
        "  `我今天有多少新客户`\n\n"
        "📌 **搜索 / Search:**\n"
        "  `找所有培训中的客户`\n\n"
        "或使用快捷菜单 / Or use quick menu:"
    )
    await telegram_handler.send_message(
        chat_id, msg, parse_mode='markdown',
        reply_markup=_kb_fallback_menu()
    )


# ── Conversation step handlers ───────────────────────────────────────────────

async def handle_nl_await_status(task_data: Dict[str, Any]):
    """Conversation step: user typed a status after being prompted."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    text: str = (task_data.get('message') or '').strip().lower()

    staff = await _get_staff(user_id)
    if not staff:
        return

    state = await telegram_handler.get_conversation_state(user_id)
    pending = (state or {}).get('pending', {})
    client_id = pending.get('client_id')

    await telegram_handler.clear_conversation_state(user_id)

    if not client_id:
        await telegram_handler.send_message(chat_id, '❌ 状态丢失 / State lost, please try again.')
        return

    try:
        new_status = ClientStatus(text)
    except ValueError:
        await telegram_handler.send_message(
            chat_id,
            f"❌ 无效状态 / Invalid status: `{text}`\n"
            "请输入: new / contacted / replied / registered / training / withdrew / ordered",
            parse_mode='markdown'
        )
        return

    await database_v2.update_client_status(client_id, new_status, staff.id)
    msg = f"✅ **状态已更新 / Status updated → {text}**"
    client = await database_v2.get_client_by_id(client_id)
    await telegram_handler.send_message(
        chat_id, msg, parse_mode='markdown',
        reply_markup=_kb_status_updated(client_id) if client else None
    )


async def handle_nl_await_note(task_data: Dict[str, Any]):
    """Conversation step: user typed a note after being prompted."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    note_text: str = (task_data.get('message') or '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        return

    state = await telegram_handler.get_conversation_state(user_id)
    pending = (state or {}).get('pending', {})
    client_id = pending.get('client_id')

    await telegram_handler.clear_conversation_state(user_id)

    if not client_id or not note_text:
        await telegram_handler.send_message(chat_id, '❌ 备注失败 / Note failed, please try again.')
        return

    cn = ClientNote(
        client_id=client_id,
        staff_id=staff.id,
        note_type=NoteType.NOTE,
        content=note_text,
    )
    await database_v2.add_client_note(cn)
    await telegram_handler.send_message(
        chat_id, f"✅ **备注已保存 / Note saved:**\n📝 {note_text}",
        parse_mode='markdown',
        reply_markup=_kb_client_actions(client_id)
    )


# ── Callback handlers ────────────────────────────────────────────────────────

async def handle_nl_confirm_update(task_data: Dict[str, Any]):
    """nl_confirm_update:<client_id>:<status> — apply the update."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    cb: str = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    parts = cb.split(':')
    if len(parts) < 3:
        await telegram_handler.send_message(chat_id, '❌ 数据错误 / Bad data.')
        return

    try:
        client_id = int(parts[1])
        status_str = parts[2]
        new_status = ClientStatus(status_str)
    except (ValueError, IndexError):
        await telegram_handler.send_message(chat_id, '❌ 无效状态 / Invalid status.')
        return

    await database_v2.update_client_status(client_id, new_status, staff.id)
    msg = f"✅ **已更新 / Updated → {status_str}**"
    await telegram_handler.send_message(
        chat_id, msg, parse_mode='markdown',
        reply_markup=_kb_status_updated(client_id)
    )


async def handle_nl_client_detail(task_data: Dict[str, Any]):
    """nl_client_detail:<id> — show full client card."""
    chat_id = task_data.get('chat_id')
    cb: str = task_data.get('callback_data', '')
    parts = cb.split(':')
    try:
        client_id = int(parts[1])
    except (IndexError, ValueError):
        return

    client = await database_v2.get_client_by_id(client_id)
    if not client:
        await telegram_handler.send_message(chat_id, '❌ 客户不存在 / Client not found.')
        return

    card = _client_card(client)
    notes = await database_v2.get_client_notes(client_id, limit=3)
    if notes:
        card += '\n\n📝 **最近备注 / Recent Notes:**'
        for n in notes:
            content = n.content if hasattr(n, 'content') else str(n)
            card += f'\n  • {content[:80]}'

    await telegram_handler.send_message(
        chat_id, card, parse_mode='markdown',
        reply_markup=_kb_client_actions(client_id)
    )


async def handle_nl_client_note_cb(task_data: Dict[str, Any]):
    """nl_client_note:<id> — prompt for note."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    cb: str = task_data.get('callback_data', '')
    parts = cb.split(':')
    try:
        client_id = int(parts[1])
    except (IndexError, ValueError):
        return

    staff = await _get_staff(user_id)
    if not staff:
        return

    await telegram_handler.set_conversation_state(user_id, {
        'step': 'nl_await_note',
        'pending': {'client_id': client_id},
    })
    await telegram_handler.send_message(
        chat_id, '📝 请输入备注内容 / Please enter the note:'
    )


async def handle_nl_client_update_cb(task_data: Dict[str, Any]):
    """nl_client_update:<id> — prompt for new status."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    cb: str = task_data.get('callback_data', '')
    parts = cb.split(':')
    try:
        client_id = int(parts[1])
    except (IndexError, ValueError):
        return

    staff = await _get_staff(user_id)
    if not staff:
        return

    await telegram_handler.set_conversation_state(user_id, {
        'step': 'nl_await_status',
        'pending': {'client_id': client_id},
    })
    await telegram_handler.send_message(
        chat_id,
        '✏️ 请输入新状态 / Enter new status:\n'
        '`new` / `contacted` / `replied` / `registered` / `training` / `withdrew` / `ordered`',
        parse_mode='markdown'
    )


async def handle_nl_menu_pipeline(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    staff = await _get_staff(user_id)
    if not staff:
        return
    await _exec_list_pipeline(chat_id, staff, {})


async def handle_nl_menu_add(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(
        chat_id,
        '➕ 使用命令添加客户 / Use command to add client:\n`/add <电话> <来源>`',
        parse_mode='markdown'
    )


async def handle_nl_menu_leaderboard(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    task_data2 = dict(task_data, command='leaderboard')
    from handlers_v2.gamification import handle_leaderboard
    await handle_leaderboard(task_data2)


async def handle_nl_menu_followup(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(
        chat_id,
        '📬 使用命令查看跟进 / Use command:\n`/followup`',
        parse_mode='markdown'
    )


async def handle_nl_menu_voice(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(
        chat_id, '🎤 请直接发送语音消息 / Please send a voice message directly.'
    )


async def handle_nl_menu_help(task_data: Dict[str, Any]):
    await _exec_help(task_data.get('chat_id'))


async def handle_nl_cancel(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    if user_id:
        await telegram_handler.clear_conversation_state(user_id)
    await telegram_handler.send_message(chat_id, '❌ 已取消 / Cancelled.')


async def handle_nl_ok(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(chat_id, '✅ 好的 / OK.')


async def handle_nl_undo(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(
        chat_id, '↩️ 请使用 /u 命令手动撤销 / Use /u to manually revert.'
    )


async def handle_nl_next_client(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(
        chat_id, '📞 请用 /pipeline 查看所有客户 / Use /pipeline to view all clients.',
        reply_markup=_kb_fallback_menu()
    )


async def handle_nl_search_more(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(
        chat_id, '🔍 使用 /search 命令进行更多搜索 / Use /search for more results.',
        reply_markup=_kb_fallback_menu()
    )


async def handle_nl_contact_first(task_data: Dict[str, Any]):
    chat_id = task_data.get('chat_id')
    await telegram_handler.send_message(
        chat_id, '📱 请用 /pipeline 选择要联系的客户 / Use /pipeline to select client to contact.'
    )


# ── Handler registries ───────────────────────────────────────────────────────

NL_HANDLER_COMMANDS: dict = {}

NL_HANDLER_CALLBACKS = {
    'nl_confirm_update:*': handle_nl_confirm_update,
    'nl_client_detail:*': handle_nl_client_detail,
    'nl_client_note:*': handle_nl_client_note_cb,
    'nl_client_update:*': handle_nl_client_update_cb,
    'nl_ok:*': handle_nl_ok,
    'nl_undo:*': handle_nl_undo,
    'nl_cancel': handle_nl_cancel,
    'nl_next_client': handle_nl_next_client,
    'nl_search_more': handle_nl_search_more,
    'nl_contact_first': handle_nl_contact_first,
    'nl_menu_add': handle_nl_menu_add,
    'nl_menu_pipeline': handle_nl_menu_pipeline,
    'nl_menu_leaderboard': handle_nl_menu_leaderboard,
    'nl_menu_followup': handle_nl_menu_followup,
    'nl_menu_voice': handle_nl_menu_voice,
    'nl_menu_help': handle_nl_menu_help,
}

NL_HANDLER_CONVERSATIONS = {
    'nl_await_status': handle_nl_await_status,
    'nl_await_note': handle_nl_await_note,
}

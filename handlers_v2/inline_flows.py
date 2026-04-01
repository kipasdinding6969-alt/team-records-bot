"""Inline keyboard flows — zero-typing UX for frontdesk workers.

Namespaced callbacks (all < 64 bytes):
  pipe:*   — pipeline browser (paginated, 5/page, filter by status)
  status:* — quick status update (pick → execute)
  note:*   — quick note (tap → type → saved)
  fu:*     — follow-up dashboard (overdue list, auto-advance)
  add:*    — guided add client (phone → source → done)

edit_message used for in-place navigation. Max 3 buttons/row.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from database_v2 import database_v2
from models_v2 import Client, ClientNote, ClientStatus, NoteType
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

PAGE_SIZE = 10

_STATUS_LABELS = {
    'zh': {
        'new': '🆕 新客户',
        'contacted': '📱 已联系',
        'replied': '💬 已回复',
        'registered': '✅ 已注册',
        'training': '📚 培训中',
        'withdrew': '💸 已提款',
        'ordered': '🎉 已下单',
        'ghosted': '👻 未响应',
        'blocked': '🚫 已拉黑',
        'scammed': '⚠️ 诈骗',
        'scheduled': '📅 已预约',
        'dead': '💀 已放弃',
    },
    'en': {
        'new': '🆕 New',
        'contacted': '📱 Contacted',
        'replied': '💬 Replied',
        'registered': '✅ Registered',
        'training': '📚 Training',
        'withdrew': '💸 Withdrew',
        'ordered': '🎉 Ordered',
        'ghosted': '👻 Ghosted',
        'blocked': '🚫 Blocked',
        'scammed': '⚠️ Scam',
        'scheduled': '📅 Scheduled',
        'dead': '💀 Dead',
    },
}

_SOURCE_BUTTONS = [
    [
        {'text': '飞机筛选', 'callback_data': 'add:src:tg'},
        {'text': 'Facebook', 'callback_data': 'add:src:fb'},
        {'text': 'Instagram', 'callback_data': 'add:src:ins'},
    ],
    [
        {'text': 'TikTok', 'callback_data': 'add:src:tt'},
        {'text': 'WeChat', 'callback_data': 'add:src:wc'},
        {'text': '其他', 'callback_data': 'add:src:other'},
    ],
]

_SOURCE_MAP = {
    'tg': 'telegram',
    'fb': 'facebook',
    'ins': 'instagram',
    'tt': 'tiktok',
    'wc': 'wechat',
    'other': 'other',
}


def _status_label(status_val: str, lang: str) -> str:
    labels = _STATUS_LABELS.get(lang, _STATUS_LABELS['zh'])
    # Validate against ClientStatus enum; fall back to raw value
    try:
        canonical = ClientStatus(status_val).value
    except ValueError:
        canonical = status_val
    return labels.get(canonical, canonical)


def _smart_next(status: ClientStatus, lang: str) -> str:
    """Contextual suggestion after a status update."""
    zh = {
        ClientStatus.CONTACTED: '📨 发送招呼消息',
        ClientStatus.REPLIED: '📋 分享注册链接',
        ClientStatus.REGISTERED: '📚 安排培训时间',
        ClientStatus.TRAINING: '💰 确认首次下单',
        ClientStatus.GHOSTED: '⏰ 设置3天后提醒',
        ClientStatus.SCHEDULED: '📅 确认预约时间',
    }
    en = {
        ClientStatus.CONTACTED: '📨 Send greeting message',
        ClientStatus.REPLIED: '📋 Share registration link',
        ClientStatus.REGISTERED: '📚 Schedule training',
        ClientStatus.TRAINING: '💰 Confirm first order',
        ClientStatus.GHOSTED: '⏰ Set 3-day reminder',
        ClientStatus.SCHEDULED: '📅 Confirm appointment time',
    }
    return (en if lang == 'en' else zh).get(status, '')


# ── Pipeline Browser ──────────────────────────────────────────────────────────

async def handle_pipe_callback(task_data: Dict[str, Any]):
    """Route all pipe:* callbacks."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    message_id = task_data.get('message_id')
    cb = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language

    if cb == 'pipe:back':
        from handlers_v2.menu import handle_start
        await handle_start(task_data)
        return

    parts = cb.split(':')
    sub = parts[1] if len(parts) > 1 else ''

    if sub == 'pg':
        page = int(parts[2]) if len(parts) > 2 else 0
        flt = parts[3] if len(parts) > 3 else 'all'
        await _show_pipe_page(chat_id, message_id, staff, page, flt, lang)
    elif sub == 'f':
        flt = parts[2] if len(parts) > 2 else 'all'
        await _show_pipe_page(chat_id, message_id, staff, 0, flt, lang)
    elif sub == 'd':
        client_id = int(parts[2])
        await _show_client_detail(chat_id, message_id, staff, client_id, lang)


async def _show_pipe_page(chat_id, message_id, staff, page: int, flt: str, lang: str):
    if flt == 'all':
        clients = await database_v2.get_clients_by_frontdesk(staff.id, limit=200)
    else:
        try:
            clients = await database_v2.get_clients_by_status(staff.id, ClientStatus(flt))
        except ValueError:
            clients = await database_v2.get_clients_by_frontdesk(staff.id, limit=200)

    total = len(clients)
    if total == 0:
        kb = telegram_handler.create_inline_keyboard([
            [{'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'}],
        ])
        text = t('pipe_empty', lang)
        if message_id:
            await telegram_handler.edit_message(chat_id, message_id, text, reply_markup=kb)
        else:
            await telegram_handler.send_message(chat_id, text, reply_markup=kb)
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    slice_ = clients[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    header = t('pipe_title', lang, count=total)
    page_info = t('pipe_page_info', lang, page=page + 1, total=total_pages)
    text = f"{header}\n{page_info}"

    client_rows = [
        [{'text': f"{c.phone} — {_status_label(c.status.value, lang)}", 'callback_data': f'pipe:d:{c.id}'}]
        for c in slice_
    ]

    filter_rows = [
        [
            {'text': t('pipe_btn_all', lang), 'callback_data': 'pipe:pg:0:all'},
            {'text': '🆕', 'callback_data': 'pipe:f:new'},
            {'text': '📱', 'callback_data': 'pipe:f:contacted'},
        ],
        [
            {'text': '💬', 'callback_data': 'pipe:f:replied'},
            {'text': '✅', 'callback_data': 'pipe:f:registered'},
            {'text': '📚', 'callback_data': 'pipe:f:training'},
        ],
    ]

    nav = []
    if page > 0:
        nav.append({'text': t('pipe_btn_prev', lang), 'callback_data': f'pipe:pg:{page - 1}:{flt}'})
    nav.append({'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'})
    if page < total_pages - 1:
        nav.append({'text': t('pipe_btn_next', lang), 'callback_data': f'pipe:pg:{page + 1}:{flt}'})

    kb = telegram_handler.create_inline_keyboard(client_rows + filter_rows + [nav])

    if message_id:
        await telegram_handler.edit_message(chat_id, message_id, text, reply_markup=kb)
    else:
        await telegram_handler.send_message(chat_id, text, reply_markup=kb)


async def _show_client_detail(chat_id, message_id, staff, client_id: int, lang: str):
    client = await database_v2.get_client_by_id(client_id)
    if not client or client.frontdesk_id != staff.id:
        text = t('err_not_found', lang)
        if message_id:
            await telegram_handler.edit_message(chat_id, message_id, text)
        else:
            await telegram_handler.send_message(chat_id, text)
        return

    label = _status_label(client.status.value, lang)
    lines = [t('pipe_detail_title', lang), f"📱 {client.phone}", f"📊 {label}"]
    if client.source:
        lines.append(f"📲 {client.source}")
    if client.nickname:
        lines.append(f"🏷 {client.nickname}")
    if client.account_id:
        lines.append(f"🆔 #{client.account_id}")
    text = '\n'.join(lines)

    kb = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_change_status', lang), 'callback_data': f'status:p:{client_id}'},
            {'text': t('btn_add_note', lang), 'callback_data': f'note:s:{client_id}'},
        ],
        [{'text': t('pipe_btn_back', lang), 'callback_data': 'pipe:pg:0:all'}],
    ])

    if message_id:
        await telegram_handler.edit_message(chat_id, message_id, text, reply_markup=kb)
    else:
        await telegram_handler.send_message(chat_id, text, reply_markup=kb)


# ── Quick Status Update ───────────────────────────────────────────────────────

async def handle_status_callback(task_data: Dict[str, Any]):
    """Route all status:* callbacks."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    message_id = task_data.get('message_id')
    cb = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    parts = cb.split(':')
    sub = parts[1] if len(parts) > 1 else ''

    if sub == 'p':
        client_id = int(parts[2])
        await _show_status_picker(chat_id, message_id, staff, client_id, lang)
    elif sub == 'do':
        client_id = int(parts[2])
        status_str = parts[3]
        await _do_status_update(chat_id, message_id, staff, client_id, status_str, lang)


async def _show_status_picker(chat_id, message_id, staff, client_id: int, lang: str):
    client = await database_v2.get_client_by_id(client_id)
    if not client or client.frontdesk_id != staff.id:
        text = t('err_not_found', lang)
        if message_id:
            await telegram_handler.edit_message(chat_id, message_id, text)
        else:
            await telegram_handler.send_message(chat_id, text)
        return

    valid = ClientStatus.valid_transitions(client.status)
    btns = [
        {'text': _status_label(s.value, lang), 'callback_data': f'status:do:{client_id}:{s.value}'}
        for s in valid
    ]
    rows = [btns[i:i + 3] for i in range(0, len(btns), 3)]
    rows.append([{'text': t('pipe_btn_back', lang), 'callback_data': f'pipe:d:{client_id}'}])

    kb = telegram_handler.create_inline_keyboard(rows)
    text = f"📱 {client.phone}\n{t('status_pick_title', lang)}"

    if message_id:
        await telegram_handler.edit_message(chat_id, message_id, text, reply_markup=kb)
    else:
        await telegram_handler.send_message(chat_id, text, reply_markup=kb)


async def _do_status_update(chat_id, message_id, staff, client_id: int, status_str: str, lang: str):
    try:
        new_status = ClientStatus(status_str)
    except ValueError:
        await telegram_handler.send_message(chat_id, t('err_invalid_status', lang))
        return

    client = await database_v2.get_client_by_id(client_id)
    if not client or client.frontdesk_id != staff.id:
        await telegram_handler.send_message(chat_id, t('err_not_found', lang))
        return

    await database_v2.update_client_status(client_id, new_status, staff.id)

    label = _status_label(status_str, lang)
    text = t('status_updated_ok', lang, phone=client.phone, status=label)

    suggestion = _smart_next(new_status, lang)
    if suggestion:
        text += f"\n\n{t('smart_next', lang)}\n{suggestion}"

    kb = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_add_note', lang), 'callback_data': f'note:s:{client_id}'},
            {'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'},
        ],
    ])

    if message_id:
        await telegram_handler.edit_message(chat_id, message_id, text, reply_markup=kb)
    else:
        await telegram_handler.send_message(chat_id, text, reply_markup=kb)

    logger.info(f"Status update via inline: {staff.display_name} -> {client.phone} -> {status_str}")


# ── Quick Note ────────────────────────────────────────────────────────────────

async def handle_note_callback(task_data: Dict[str, Any]):
    """note:s:{id} — initiate note for a client."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    cb = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    parts = cb.split(':')
    if parts[1] != 's' or len(parts) < 3:
        return

    client_id = int(parts[2])
    client = await database_v2.get_client_by_id(client_id)
    if not client or client.frontdesk_id != staff.id:
        await telegram_handler.send_message(chat_id, t('err_not_found', lang))
        return

    await telegram_handler.set_conversation_state(user_id, {
        'step': 'inline_await_note',
        'pending': {'client_id': client_id},
    })
    await telegram_handler.send_message(
        chat_id,
        f"📱 {client.phone}\n{t('note_prompt', lang)}",
    )


async def handle_inline_await_note(task_data: Dict[str, Any]):
    """Conversation step: user typed the note content."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    note_text = (task_data.get('message') or '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    state = await telegram_handler.get_conversation_state(user_id)
    pending = (state or {}).get('pending', {})
    client_id = pending.get('client_id')

    await telegram_handler.clear_conversation_state(user_id)

    if not client_id or not note_text:
        await telegram_handler.send_message(chat_id, t('note_failed', lang))
        return

    note = ClientNote(
        client_id=client_id,
        staff_id=staff.id,
        note_type=NoteType.NOTE,
        content=note_text,
    )
    await database_v2.add_client_note(note)

    kb = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_change_status', lang), 'callback_data': f'status:p:{client_id}'},
            {'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'},
        ],
    ])
    await telegram_handler.send_message(chat_id, t('note_saved', lang), reply_markup=kb)
    logger.info(f"Note added via inline: {staff.display_name} -> client {client_id}")


# ── Follow-up Dashboard ───────────────────────────────────────────────────────

async def handle_fu_start(task_data: Dict[str, Any]):
    """Entry point: show follow-up dashboard from menu."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        return

    await _show_fu_dashboard(chat_id, None, staff, staff.language)


async def handle_fu_callback(task_data: Dict[str, Any]):
    """Route all fu:* callbacks (action buttons on overdue clients)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    cb = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    parts = cb.split(':')

    if len(parts) < 3:
        await _show_fu_dashboard(chat_id, None, staff, lang)
        return

    action = parts[1]
    try:
        client_id = int(parts[2])
    except ValueError:
        return

    client = await database_v2.get_client_by_id(client_id)
    if client and client.frontdesk_id == staff.id:
        if action == 'ok':
            await database_v2.update_client_status(client_id, ClientStatus.CONTACTED, staff.id)
            await telegram_handler.send_message(
                chat_id, t('fu_contacted_ok', lang, phone=client.phone))
        elif action == 'sk':
            await database_v2.set_next_followup(client_id, datetime.now() + timedelta(days=1))
            await telegram_handler.send_message(
                chat_id, t('fu_skip_ok', lang, phone=client.phone))
        elif action == 'ab':
            await database_v2.update_client_status(client_id, ClientStatus.DEAD, staff.id)
            await telegram_handler.send_message(
                chat_id, t('fu_dead_ok', lang, phone=client.phone))

    # Auto-advance: show next overdue client
    remaining = await database_v2.get_followup_due(staff.id)
    if not remaining:
        kb = telegram_handler.create_inline_keyboard([
            [{'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'}],
        ])
        await telegram_handler.send_message(chat_id, t('fu_all_done', lang), reply_markup=kb)
    else:
        await _send_fu_client(chat_id, remaining[0], lang)


async def _show_fu_dashboard(chat_id, message_id, staff, lang: str):
    clients = await database_v2.get_followup_due(staff.id)
    if not clients:
        kb = telegram_handler.create_inline_keyboard([
            [{'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'}],
        ])
        text = t('followup_empty', lang)
        if message_id:
            await telegram_handler.edit_message(chat_id, message_id, text, reply_markup=kb)
        else:
            await telegram_handler.send_message(chat_id, text, reply_markup=kb)
        return

    title = t('fu_title', lang, count=len(clients))
    await telegram_handler.send_message(chat_id, title)
    for c in clients[:10]:
        await _send_fu_client(chat_id, c, lang)


async def _send_fu_client(chat_id, client, lang: str):
    label = _status_label(client.status.value, lang)
    info = f"📱 {client.phone} — {label}"
    if client.account_id:
        info += f"\n🆔 #{client.account_id}"

    kb = telegram_handler.create_inline_keyboard([[
        {'text': t('fu_btn_contacted', lang), 'callback_data': f'fu:ok:{client.id}'},
        {'text': t('fu_btn_skip', lang), 'callback_data': f'fu:sk:{client.id}'},
        {'text': t('fu_btn_dead', lang), 'callback_data': f'fu:ab:{client.id}'},
    ]])
    await telegram_handler.send_message(chat_id, info, reply_markup=kb)


# ── Quick Add Client ──────────────────────────────────────────────────────────

async def handle_add_start(task_data: Dict[str, Any]):
    """Entry point: ask for phone number to add a new client."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    await telegram_handler.set_conversation_state(user_id, {'step': 'add_await_phone'})
    await telegram_handler.send_message(chat_id, t('add_ask_phone', lang))


async def handle_add_await_phone(task_data: Dict[str, Any]):
    """Conversation step: user entered a phone number."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    phone = (task_data.get('message') or '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    clean = phone.replace('+', '').replace('-', '').replace(' ', '')

    if not clean.isdigit() or not (7 <= len(clean) <= 15):
        await telegram_handler.set_conversation_state(user_id, {'step': 'add_await_phone'})
        await telegram_handler.send_message(chat_id, t('add_invalid_phone', lang))
        return

    existing = await database_v2.get_client_by_phone(phone)  # global check
    if existing:
        await telegram_handler.clear_conversation_state(user_id)
        if existing.frontdesk_id and existing.frontdesk_id != staff.id:
            other_staff = await database_v2.get_staff_by_id(existing.frontdesk_id)
            other_name = other_staff.display_name if other_staff else '其他员工 / Other staff'
            await telegram_handler.send_message(
                chat_id,
                f"⚠️ {phone}\n该号码已由 {other_name} 管理 / This number is already managed by {other_name}",
            )
        else:
            await telegram_handler.send_message(chat_id, t('add_dup', lang, phone=phone))
            await _show_client_detail(chat_id, None, staff, existing.id, lang)
        return

    # Phase 17: Phone registry duplicate guard (cross-frontdesk, catches ChatExport imports)
    registry_entry = await database_v2.phone_registry_lookup(phone)
    if registry_entry:
        owner_name = registry_entry['submitter_name']
        owner_staff_id = registry_entry['submitter_staff_id']
        submitted_at = registry_entry['submitted_at']
        if owner_staff_id and owner_staff_id != staff.id:
            import json
            await database_v2.phone_registry_log_action(
                phone, 'duplicate_blocked', staff.display_name, staff.id,
                json.dumps({'original_submitter': owner_name}, ensure_ascii=False))
            await telegram_handler.clear_conversation_state(user_id)
            await telegram_handler.send_message(chat_id,
                f"⚠️ 号码重复 / Duplicate Number\n"
                f"该号码已由 {owner_name} 于 {submitted_at} 提交\n"
                f"This number was submitted by {owner_name} on {submitted_at}\n"
                f"如需覆盖请联系管理员 / Contact admin to override")
            return
        # Same frontdesk — allow (fall through to source selection)

    await telegram_handler.set_conversation_state(user_id, {
        'step': 'add_await_source',
        'pending': {'phone': phone},
    })
    kb = telegram_handler.create_inline_keyboard(_SOURCE_BUTTONS)
    await telegram_handler.send_message(chat_id, t('add_ask_source', lang), reply_markup=kb)


async def handle_add_await_source(task_data: Dict[str, Any]):
    """Conversation step: user typed text instead of tapping source button."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    state = await telegram_handler.get_conversation_state(user_id)
    kb = telegram_handler.create_inline_keyboard(_SOURCE_BUTTONS)
    await telegram_handler.send_message(chat_id, t('add_ask_source', lang), reply_markup=kb)


async def handle_add_source_callback(task_data: Dict[str, Any]):
    """add:src:{code} — user tapped source button, create client."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    cb = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    state = await telegram_handler.get_conversation_state(user_id)

    if not state or state.get('step') != 'add_await_source':
        await telegram_handler.send_message(chat_id, t('add_ask_phone', lang))
        return

    phone = state.get('pending', {}).get('phone', '')
    await telegram_handler.clear_conversation_state(user_id)

    parts = cb.split(':')
    src_code = parts[2] if len(parts) > 2 else 'other'
    source = _SOURCE_MAP.get(src_code, src_code)

    c = Client(frontdesk_id=staff.id, phone=phone, source=source)
    client_id = await database_v2.create_client(c)

    # Phase 17: Register phone in registry if not already there
    existing_reg = await database_v2.phone_registry_lookup(phone)
    if not existing_reg:
        try:
            from datetime import datetime as _dt, timezone as _tz
            await database_v2.phone_registry_insert(
                phone, staff.display_name, _dt.now(_tz.utc).isoformat(),
                source='bot', submitter_staff_id=staff.id)
            await database_v2.phone_registry_log_action(
                phone, 'submit', staff.display_name, staff.id)
        except Exception as _e:
            logger.debug(f'Phone registry insert skipped (inline): {_e}')

    kb = telegram_handler.create_inline_keyboard([
        [
            {'text': t('menu_btn_pipeline', lang), 'callback_data': 'pipe:pg:0:all'},
            {'text': t('pipe_btn_back_menu', lang), 'callback_data': 'pipe:back'},
        ],
    ])
    await telegram_handler.send_message(chat_id, t('add_done', lang, phone=phone), reply_markup=kb)
    logger.info(f"Client added via inline: {staff.display_name} -> {phone} ({source})")


# ── Handler registries ────────────────────────────────────────────────────────

INLINE_FLOWS_COMMANDS: dict = {}

INLINE_FLOWS_CALLBACKS = {
    'pipe:*':   handle_pipe_callback,
    'status:*': handle_status_callback,
    'note:*':   handle_note_callback,
    'fu:*':     handle_fu_callback,
    'add:*':    handle_add_source_callback,
}

INLINE_FLOWS_CONVERSATIONS = {
    'inline_await_note': handle_inline_await_note,
    'add_await_phone':   handle_add_await_phone,
    'add_await_source':  handle_add_await_source,
}

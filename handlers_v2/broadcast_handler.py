"""Broadcast handler — /broadcast command for admins/managers."""
import json
import logging
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

# ─── Inline keyboard builders ─────────────────────────────────────────────────

def _segment_keyboard() -> list:
    from engines.broadcast_engine import get_segment_types
    rows = []
    for seg_type, label in get_segment_types():
        rows.append([{'text': label, 'callback_data': f'bc:seg:{seg_type}'}])
    rows.append([{'text': '❌ 取消', 'callback_data': 'bc:cancel'}])
    return rows


def _status_value_keyboard() -> list:
    from engines.broadcast_engine import get_status_values
    rows = []
    row = []
    for val, label in get_status_values():
        row.append({'text': label, 'callback_data': f'bc:val:{val}'})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{'text': '❌ 取消', 'callback_data': 'bc:cancel'}])
    return rows


def _confirm_keyboard(log_id: int) -> list:
    return [
        [
            {'text': '✅ 确认发送', 'callback_data': f'bc:confirm:{log_id}'},
            {'text': '❌ 取消', 'callback_data': 'bc:cancel'},
        ]
    ]


# ─── Command handler ──────────────────────────────────────────────────────────

async def handle_broadcast(task_data: Dict[str, Any]):
    """/broadcast — initiate broadcast flow (admin/manager only)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'broadcast'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_manager_only', staff.language))
        return

    await database_v2.clear_conversation_state(user_id)
    await database_v2.set_conversation_state(user_id, {'handler': 'broadcast', 'step': 'segment'})

    await telegram_handler.send_message(
        chat_id,
        '📢 <b>群发消息</b>\n\n选择目标群体：',
        parse_mode='html',
        reply_markup={'inline_keyboard': _segment_keyboard()},
    )


# ─── Callback handlers ────────────────────────────────────────────────────────

async def handle_bc_callback(task_data: Dict[str, Any]):
    """Handle bc:* inline callbacks."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    data = task_data.get('data', '')
    message_id = task_data.get('message_id')

    staff = await _get_staff(user_id)
    if not staff:
        return

    if not staff.is_manager_or_above():
        return

    parts = data.split(':', 2)
    action = parts[1] if len(parts) > 1 else ''

    if action == 'cancel':
        await database_v2.clear_conversation_state(user_id)
        await telegram_handler.edit_message(chat_id, message_id, '已取消群发。')
        return

    state = await database_v2.get_conversation_state(user_id) or {}
    if state.get('handler') != 'broadcast':
        await telegram_handler.send_message(chat_id, '请先使用 /broadcast 命令。')
        return

    if action == 'seg':
        seg_type = parts[2] if len(parts) > 2 else ''
        if seg_type == 'status':
            state['step'] = 'val_status'
            state['segment_type'] = 'status'
            await database_v2.set_conversation_state(user_id, state)
            await telegram_handler.edit_message(
                chat_id, message_id,
                '选择目标状态：',
                reply_markup={'inline_keyboard': _status_value_keyboard()},
            )
        elif seg_type == 'date_range':
            state['step'] = 'await_date_range'
            state['segment_type'] = 'date_range'
            await database_v2.set_conversation_state(user_id, state)
            await telegram_handler.edit_message(
                chat_id, message_id,
                '请输入日期范围，格式：<code>YYYY-MM-DD YYYY-MM-DD</code>\n例如：<code>2026-01-01 2026-03-31</code>',
                parse_mode='html',
            )
        else:
            # team or source — ask for text input
            label_map = {'team': '团队名称', 'source': '来源渠道'}
            state['step'] = f'await_{seg_type}'
            state['segment_type'] = seg_type
            await database_v2.set_conversation_state(user_id, state)
            await telegram_handler.edit_message(
                chat_id, message_id,
                f'请输入{label_map.get(seg_type, seg_type)}：',
            )

    elif action == 'val':
        seg_value = parts[2] if len(parts) > 2 else ''
        state['segment_value'] = seg_value
        state['step'] = 'await_template'
        await database_v2.set_conversation_state(user_id, state)

        from engines.broadcast_engine import get_segment_targets
        targets = await get_segment_targets(state['segment_type'], seg_value)
        await telegram_handler.edit_message(
            chat_id, message_id,
            f'✅ 找到 <b>{len(targets)}</b> 名客户\n\n'
            f'请输入消息模板。可用变量：\n'
            f'• <code>{{name}}</code> — 客户昵称\n'
            f'• <code>{{status}}</code> — 当前状态\n'
            f'• <code>{{days_since_contact}}</code> — 联系天数',
            parse_mode='html',
        )

    elif action == 'confirm':
        log_id = int(parts[2]) if len(parts) > 2 else 0
        # Fetch state and run broadcast
        seg_type = state.get('segment_type', '')
        seg_value = state.get('segment_value', '')
        template = state.get('template', '')
        date_from = state.get('date_from')
        date_to = state.get('date_to')

        if not seg_type or not template:
            await telegram_handler.send_message(chat_id, '状态错误，请重新使用 /broadcast。')
            await database_v2.clear_conversation_state(user_id)
            return

        await database_v2.clear_conversation_state(user_id)
        await telegram_handler.edit_message(chat_id, message_id, '📤 正在发送...')

        from engines.broadcast_engine import send_broadcast

        progress_msg_id = message_id

        async def on_progress(done: int, total: int):
            pct = int(done / total * 100) if total else 0
            try:
                await telegram_handler.edit_message(
                    chat_id, progress_msg_id,
                    f'📤 发送中... {done}/{total} ({pct}%)')
            except Exception:
                pass

        result = await send_broadcast(
            staff_id=staff.id,
            template=template,
            segment_type=seg_type,
            segment_value=seg_value,
            date_from=date_from,
            date_to=date_to,
            progress_callback=on_progress,
        )

        report = (
            f'📊 <b>群发完成</b>\n\n'
            f'目标人数：{result["total"]}\n'
            f'✅ 成功：{result["sent"]}\n'
            f'❌ 失败：{result["failed"]}\n'
            f'🚫 被屏蔽：{result["blocked"]}'
        )
        await telegram_handler.edit_message(chat_id, progress_msg_id, report, parse_mode='html')


# ─── Conversation handler ─────────────────────────────────────────────────────

async def handle_bc_conversation(task_data: Dict[str, Any]):
    """Handle text input steps of the broadcast flow."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    text = (task_data.get('text') or '').strip()

    state = await database_v2.get_conversation_state(user_id)
    if not state or state.get('handler') != 'broadcast':
        return False  # not our conversation

    step = state.get('step', '')

    if step.startswith('await_') and step not in ('await_template', 'await_date_range'):
        seg_type = state.get('segment_type', step.replace('await_', ''))
        state['segment_value'] = text
        state['step'] = 'await_template'
        await database_v2.set_conversation_state(user_id, state)

        from engines.broadcast_engine import get_segment_targets
        targets = await get_segment_targets(seg_type, text)
        await telegram_handler.send_message(
            chat_id,
            f'✅ 找到 <b>{len(targets)}</b> 名客户\n\n'
            f'请输入消息模板。可用变量：\n'
            f'• <code>{{name}}</code> — 客户昵称\n'
            f'• <code>{{status}}</code> — 当前状态\n'
            f'• <code>{{days_since_contact}}</code> — 联系天数',
            parse_mode='html',
        )
        return True

    if step == 'await_date_range':
        parts = text.split()
        if len(parts) != 2:
            await telegram_handler.send_message(chat_id, '格式错误，请输入：YYYY-MM-DD YYYY-MM-DD')
            return True
        state['date_from'] = parts[0]
        state['date_to'] = parts[1]
        state['segment_value'] = f'{parts[0]}~{parts[1]}'
        state['step'] = 'await_template'
        await database_v2.set_conversation_state(user_id, state)

        from engines.broadcast_engine import get_segment_targets
        targets = await get_segment_targets('date_range', '', parts[0], parts[1])
        await telegram_handler.send_message(
            chat_id,
            f'✅ 找到 <b>{len(targets)}</b> 名客户\n\n'
            f'请输入消息模板（可用 {{name}}, {{status}}, {{days_since_contact}}）：',
            parse_mode='html',
        )
        return True

    if step == 'await_template':
        state['template'] = text
        state['step'] = 'confirm'
        await database_v2.set_conversation_state(user_id, state)

        seg_type = state.get('segment_type', '')
        seg_value = state.get('segment_value', '')
        date_from = state.get('date_from')
        date_to = state.get('date_to')

        from engines.broadcast_engine import get_segment_targets
        targets = await get_segment_targets(seg_type, seg_value, date_from, date_to)

        # Preview with first target
        preview_text = text
        if targets:
            from engines.broadcast_engine import _render_template
            preview_text = _render_template(text, targets[0])

        # Create a placeholder log_id for confirm button
        staff_id = (await _get_staff(user_id)).id
        log_id = await database_v2.create_broadcast_log(
            staff_id=staff_id,
            template=text,
            segment_filter=f'{seg_type}:{seg_value}',
            total_targets=len(targets),
        )
        state['log_id'] = log_id
        await database_v2.set_conversation_state(user_id, state)

        msg = (
            f'📋 <b>预览</b>\n\n'
            f'{preview_text}\n\n'
            f'———\n'
            f'目标人数：<b>{len(targets)}</b>\n\n'
            f'确认发送？'
        )
        await telegram_handler.send_message(
            chat_id, msg, parse_mode='html',
            reply_markup={'inline_keyboard': _confirm_keyboard(log_id)},
        )
        return True

    return False


BROADCAST_COMMANDS = {'broadcast': handle_broadcast}

BROADCAST_CALLBACKS = {
    'bc': handle_bc_callback,
}

BROADCAST_CONVERSATIONS = {
    'broadcast': handle_bc_conversation,
}

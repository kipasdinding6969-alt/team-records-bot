"""Excel export/import handler — /export (xlsx), /import, /export_template."""
import logging
from datetime import date
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)


# ─── /export ─────────────────────────────────────────────────────────────────

async def handle_export(task_data: Dict[str, Any]):
    """/export [status] — export clients as Excel (.xlsx)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = (task_data.get('args') or '').strip().lower()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'export'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language

    # Parse optional status filter from args
    status_filter = args if args else None
    frontdesk_id = None if staff.is_manager_or_above() else staff.id

    await telegram_handler.send_message(chat_id, '⏳ 正在生成 Excel 文件...')

    from engines.excel_engine import build_export_rows, export_to_excel
    rows = await build_export_rows(
        frontdesk_id=frontdesk_id,
        status_filter=status_filter,
    )

    if not rows:
        await telegram_handler.send_message(chat_id, t('export_empty', lang))
        return

    xlsx_bytes = export_to_excel(rows)
    filename = f'clients_{date.today().isoformat()}.xlsx'
    if status_filter:
        filename = f'clients_{status_filter}_{date.today().isoformat()}.xlsx'

    try:
        await telegram_handler.send_document(chat_id, xlsx_bytes, caption=f'导出完成：{len(rows)} 条记录')
    except Exception as e:
        logger.error(f'handle_export send_document failed: {e}')
        await telegram_handler.send_message(
            chat_id, t('export_success', lang, count=len(rows)))


# ─── /export_template ────────────────────────────────────────────────────────

async def handle_export_template(task_data: Dict[str, Any]):
    """/export_template — send empty import template."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'export'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    from engines.excel_engine import generate_template
    template_bytes = generate_template()

    try:
        await telegram_handler.send_document(
            chat_id, template_bytes,
            caption='📋 导入模板\n\n填写后使用 /import 上传文件')
    except Exception as e:
        logger.error(f'handle_export_template failed: {e}')
        await telegram_handler.send_message(chat_id, '❌ 生成模板失败，请重试。')


# ─── /import ─────────────────────────────────────────────────────────────────

async def handle_import(task_data: Dict[str, Any]):
    """/import — prompt user to upload Excel file."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'import_excel'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_manager_only', staff.language))
        return

    await database_v2.set_conversation_state(user_id, {
        'handler': 'import_excel',
        'step': 'await_file',
    })

    await telegram_handler.send_message(
        chat_id,
        '📥 <b>导入客户</b>\n\n'
        '请上传 .xlsx 文件（使用 /export_template 下载模板）\n\n'
        '文件必须包含 <code>phone</code> 列（电话号码）。',
        parse_mode='html',
    )


async def handle_import_conversation(task_data: Dict[str, Any]):
    """Handle Excel file upload during import flow."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    state = await database_v2.get_conversation_state(user_id)
    if not state or state.get('handler') != 'import_excel':
        return False

    step = state.get('step', '')

    if step == 'await_file':
        # Expect a document attachment in task_data
        file_bytes = task_data.get('file_bytes')
        if not file_bytes:
            await telegram_handler.send_message(chat_id, '请上传 .xlsx 文件。')
            return True

        try:
            from engines.excel_engine import parse_import_file
            valid_rows, errors = parse_import_file(file_bytes)
        except Exception as e:
            logger.error(f'parse_import_file error: {e}')
            await telegram_handler.send_message(chat_id, f'❌ 解析文件失败：{e}')
            await database_v2.clear_conversation_state(user_id)
            return True

        if not valid_rows and not errors:
            await telegram_handler.send_message(chat_id, '文件为空或格式不正确。')
            await database_v2.clear_conversation_state(user_id)
            return True

        # Store parsed rows in state (as JSON-serialisable list)
        state['parsed_rows'] = valid_rows
        state['step'] = 'await_confirm'
        await database_v2.set_conversation_state(user_id, state)

        error_summary = ''
        if errors:
            error_preview = '\n'.join(errors[:5])
            if len(errors) > 5:
                error_preview += f'\n...以及 {len(errors) - 5} 个其他错误'
            error_summary = f'\n\n⚠️ 跳过的行：\n{error_preview}'

        preview_lines = []
        for r in valid_rows[:5]:
            preview_lines.append(f"• {r['phone']} | {r.get('status', 'new')} | {r.get('source', 'other')}")
        if len(valid_rows) > 5:
            preview_lines.append(f'... 以及 {len(valid_rows) - 5} 条')

        msg = (
            f'📊 <b>预览</b>\n\n'
            f'有效记录：<b>{len(valid_rows)}</b> 条{error_summary}\n\n'
            + '\n'.join(preview_lines) +
            '\n\n确认导入？'
        )
        await telegram_handler.send_message(
            chat_id, msg, parse_mode='html',
            reply_markup={'inline_keyboard': [
                [
                    {'text': '✅ 确认导入', 'callback_data': 'xl:confirm'},
                    {'text': '❌ 取消', 'callback_data': 'xl:cancel'},
                ]
            ]},
        )
        return True

    return False


async def handle_xl_callback(task_data: Dict[str, Any]):
    """Handle xl:confirm / xl:cancel callbacks."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    data = task_data.get('data', '')
    message_id = task_data.get('message_id')

    staff = await _get_staff(user_id)
    if not staff:
        return

    action = data.split(':', 1)[1] if ':' in data else ''

    state = await database_v2.get_conversation_state(user_id)
    if not state or state.get('handler') != 'import_excel':
        await telegram_handler.edit_message(chat_id, message_id, '会话已超时，请重新使用 /import。')
        return

    if action == 'cancel':
        await database_v2.clear_conversation_state(user_id)
        await telegram_handler.edit_message(chat_id, message_id, '已取消导入。')
        return

    if action == 'confirm':
        parsed_rows = state.get('parsed_rows', [])
        if not parsed_rows:
            await telegram_handler.edit_message(chat_id, message_id, '❌ 无有效数据，请重新上传。')
            await database_v2.clear_conversation_state(user_id)
            return

        await telegram_handler.edit_message(chat_id, message_id, '⏳ 正在导入...')
        await database_v2.clear_conversation_state(user_id)

        from engines.excel_engine import import_clients
        result = await import_clients(parsed_rows, frontdesk_id=staff.id)

        await telegram_handler.send_message(
            chat_id,
            f'✅ <b>导入完成</b>\n\n'
            f'总计：{result["total"]} 条\n'
            f'成功导入：{result["imported"]} 条\n'
            f'跳过（重复）：{result["skipped"]} 条',
            parse_mode='html',
        )


EXPORT_HANDLER_COMMANDS = {
    'export': handle_export,
    'export_template': handle_export_template,
    'import': handle_import,
}

EXPORT_HANDLER_CALLBACKS = {
    'xl': handle_xl_callback,
}

EXPORT_HANDLER_CONVERSATIONS = {
    'import_excel': handle_import_conversation,
}

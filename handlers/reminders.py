"""Reminder management handlers."""
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from telethon import Button

from database import database
from models import Reminder, BotTask
from telegram_handler import telegram_handler
from utils.formatting import format_reminder, format_datetime_chinese
from i18n import t


async def _get_lang(user_id):
    from database import database
    return (await database.get_user_language(user_id)) or 'zh'

logger = logging.getLogger(__name__)


async def handle_remind_command(task_data: Dict[str, Any]):
    """Handle /remind command for manual reminder management."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    args = task_data.get('args', [])

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    lang = await _get_lang(user_id)
    if not member or member.role not in ['admin']:
        await telegram_handler.send_message(
            chat_id,
            t('err_admin_only', lang)
        )
        return

    if not args:
        # Show reminder management options
        options_text = f"""
{t('reminder_management_title', lang)}

{t('choose_operation_type', lang)}

使用方法 / Usage:
• /remind [成员名] - 发送手动提醒给特定成员
• /remind list - 查看所有待处理提醒
• /remind stats - 查看提醒统计

示例 / Examples:
/remind 阿YIM
/remind list
/remind stats
        """.strip()

        await telegram_handler.send_message(chat_id, options_text)
        return

    if args[0].lower() == 'list':
        await show_pending_reminders(task_data)
    elif args[0].lower() == 'stats':
        await show_reminder_stats(task_data)
    else:
        # Send manual reminder to specific member
        member_name = ' '.join(args)
        await send_manual_reminder(task_data, member_name)


async def show_pending_reminders(task_data: Dict[str, Any]):
    """Show all pending reminders."""
    chat_id = task_data['chat_id']

    # Get pending reminders
    reminders = await database.get_pending_reminders()

    if not reminders:
        lang = await _get_lang(task_data['user_id'])
        no_reminders_text = f"""
{t('no_pending_reminders_title', lang)}

{t('no_pending_reminders_desc', lang)}
        """.strip()

        await telegram_handler.send_message(chat_id, no_reminders_text, parse_mode='markdown')
        return

    # Group reminders by type and user
    reminders_by_type = {'day1': [], 'day2': [], 'manual': []}
    reminders_by_user = {}

    for reminder in reminders:
        reminder_type = reminder.reminder_type
        if reminder_type in reminders_by_type:
            reminders_by_type[reminder_type].append(reminder)

        user_id = reminder.frontdesk_user_id
        if user_id not in reminders_by_user:
            reminders_by_user[user_id] = []
        reminders_by_user[user_id].append(reminder)

    reminders_text = f"""
🔔 **待处理提醒 / Pending Reminders** ({len(reminders)} 条)

**📊 按类型统计 / By Type:**
• 第一天提醒 / Day 1: {len(reminders_by_type['day1'])}
• 第二天提醒 / Day 2: {len(reminders_by_type['day2'])}
• 手动提醒 / Manual: {len(reminders_by_type.get('manual', []))}

**👥 按用户统计 / By User:**
"""

    # Get user details for each user with reminders
    for user_id, user_reminders in reminders_by_user.items():
        member = await database.get_team_member_by_user_id(user_id)
        member_name = member.frontdesk_name if member else f"User {user_id}"
        reminders_text += f"• {member_name}: {len(user_reminders)} 条\n"

    reminders_text += f"""

**🕒 最近提醒 / Recent Reminders:**
"""

    # Show first 10 reminders
    for i, reminder in enumerate(reminders[:10]):
        member = await database.get_team_member_by_user_id(reminder.frontdesk_user_id)
        member_name = member.frontdesk_name if member else f"User {reminder.frontdesk_user_id}"

        scheduled_time = reminder.scheduled_time.strftime('%m-%d %H:%M')
        reminders_text += f"{i+1}. {reminder.reminder_type} - {member_name} - {scheduled_time}\n"

    if len(reminders) > 10:
        reminders_text += f"\n... 还有 {len(reminders) - 10} 条提醒"

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '🔄 刷新 / Refresh', 'callback_data': 'refresh_reminders'},
            {'text': '📤 导出列表 / Export List', 'callback_data': 'export_reminders'}
        ],
        [
            {'text': '⚡ 发送所有 / Send All', 'callback_data': 'send_all_reminders'},
            {'text': '🗑️ 清理过期 / Clean Expired', 'callback_data': 'clean_expired_reminders'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        reminders_text.strip(),
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_reminder_stats(task_data: Dict[str, Any]):
    """Show reminder statistics."""
    chat_id = task_data['chat_id']

    # Get all reminders (sent and unsent)
    async with database.get_connection() as db:
        # Pending reminders
        cursor = await db.execute("SELECT COUNT(*) FROM reminders WHERE is_sent = FALSE")
        pending_count = (await cursor.fetchone())[0]

        # Sent reminders (last 7 days)
        week_ago = datetime.now() - timedelta(days=7)
        cursor = await db.execute("""
            SELECT COUNT(*) FROM reminders
            WHERE is_sent = TRUE AND sent_at >= ?
        """, (week_ago,))
        sent_week_count = (await cursor.fetchone())[0]

        # Total reminders
        cursor = await db.execute("SELECT COUNT(*) FROM reminders")
        total_count = (await cursor.fetchone())[0]

        # Reminders by type
        cursor = await db.execute("""
            SELECT reminder_type, COUNT(*) FROM reminders
            WHERE is_sent = FALSE
            GROUP BY reminder_type
        """)
        pending_by_type = dict(await cursor.fetchall())

        # Success rate (approximate)
        cursor = await db.execute("""
            SELECT
                COUNT(CASE WHEN is_sent = TRUE THEN 1 END) as sent,
                COUNT(*) as total
            FROM reminders
            WHERE created_at >= ?
        """, (week_ago,))
        sent, total = await cursor.fetchone()

    success_rate = (sent / total * 100) if total > 0 else 0

    stats_text = f"""
📊 **提醒系统统计 / Reminder System Statistics**

📅 **统计时间 / Statistics Time:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

**📈 基本统计 / Basic Statistics:**
• 待处理提醒 / Pending: {pending_count}
• 本周已发送 / Sent This Week: {sent_week_count}
• 总提醒数 / Total Reminders: {total_count}
• 发送成功率 / Success Rate: {success_rate:.1f}%

**📋 待处理分类 / Pending By Type:**
"""

    for reminder_type, count in pending_by_type.items():
        type_name = {
            'day1': '第一天提醒 / Day 1',
            'day2': '第二天提醒 / Day 2',
            'manual': '手动提醒 / Manual'
        }.get(reminder_type, reminder_type)
        stats_text += f"• {type_name}: {count}\n"

    # Get overdue reminders
    overdue_reminders = await database.get_pending_reminders(datetime.now() - timedelta(hours=1))
    overdue_count = len(overdue_reminders)

    stats_text += f"""

**⚠️ 系统健康状态 / System Health:**
• 过期未发送 / Overdue: {overdue_count}
• 系统状态 / Status: {'🟢 正常' if overdue_count < 10 else '🟡 注意' if overdue_count < 50 else '🔴 异常'}

**💡 建议操作 / Suggested Actions:**
"""

    if overdue_count > 0:
        stats_text += f"• 有 {overdue_count} 条过期提醒需要处理\n"
    if pending_count > 100:
        stats_text += "• 待处理提醒过多，考虑批量处理\n"
    if success_rate < 90:
        stats_text += "• 发送成功率较低，检查系统状态\n"

    if overdue_count == 0 and pending_count < 50 and success_rate >= 90:
        stats_text += "• ✅ 系统运行正常，无需特殊操作\n"

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📋 查看详情 / View Details', 'callback_data': 'reminder_list'},
            {'text': '🔄 刷新统计 / Refresh Stats', 'callback_data': 'refresh_reminder_stats'}
        ],
        [
            {'text': '⚡ 处理过期 / Process Overdue', 'callback_data': 'process_overdue_reminders'},
            {'text': '🛠️ 系统维护 / System Maintenance', 'callback_data': 'reminder_maintenance'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        stats_text.strip(),
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def send_manual_reminder(task_data: Dict[str, Any], member_name: str):
    """Send manual reminder to specific member."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Find the member
    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT user_id, chat_id, frontdesk_name FROM team_members
            WHERE frontdesk_name = ? AND is_active = TRUE
        """, (member_name,))
        member_data = await cursor.fetchone()

    if not member_data:
        error_text = f"""
❌ **成员未找到 / Member Not Found**

成员 "{member_name}" 未找到或已停用。
Member "{member_name}" not found or deactivated.

可用成员 / Available members:
        """.strip()

        # Get available members
        cursor = await db.execute("""
            SELECT frontdesk_name FROM team_members
            WHERE role = 'frontdesk' AND is_active = TRUE AND frontdesk_name IS NOT NULL
        """)
        available_members = [row[0] for row in await cursor.fetchall()]

        error_text += '\n'.join(f"• {member}" for member in available_members)

        await telegram_handler.send_message(chat_id, error_text, parse_mode='markdown')
        return

    target_user_id, target_chat_id, frontdesk_name = member_data

    # Show reminder message options
    reminder_text = f"""
🔔 **发送手动提醒 / Send Manual Reminder**

目标成员 / Target Member: **{frontdesk_name}**

请选择提醒类型或输入自定义消息：
Please select reminder type or enter custom message:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📊 更新客户状态 / Update Client Status', 'callback_data': f'manual_reminder_status_{target_user_id}'},
            {'text': '📋 提交今日报告 / Submit Today Report', 'callback_data': f'manual_reminder_report_{target_user_id}'}
        ],
        [
            {'text': '🎯 注意注册率 / Focus on Registration', 'callback_data': f'manual_reminder_focus_{target_user_id}'},
            {'text': '👥 联系客户 / Contact Clients', 'callback_data': f'manual_reminder_contact_{target_user_id}'}
        ],
        [
            {'text': '✏️ 自定义消息 / Custom Message', 'callback_data': f'custom_reminder_{target_user_id}'},
            {'text': '❌ 取消 / Cancel', 'callback_data': 'cancel_reminder'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        reminder_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_manual_reminder_callbacks(task_data: Dict[str, Any]):
    """Handle manual reminder callback selections."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data.startswith('manual_reminder_'):
        parts = callback_data.split('_')
        reminder_type = parts[2]
        target_user_id = int(parts[3])

        # Predefined reminder messages
        messages = {
            'status': """
🔔 **提醒：更新客户状态 / Reminder: Update Client Status**

请及时更新待处理客户的注册状态：
Please update the registration status of pending clients:

• 检查第一天和第二天的注册情况
• 更新客户状态为"注册"或"不注册"
• 如需帮助，请联系管理员

使用 /clients 查看待处理客户。
Use /clients to view pending clients.
            """.strip(),
            'report': """
🔔 **提醒：提交今日报告 / Reminder: Submit Today's Report**

请记得提交今日的工作报告：
Please remember to submit today's work report:

• 使用 /report 命令提交新客户记录
• 确保所有客户信息准确填写
• 及时更新客户状态

Thank you for your hard work!
            """.strip(),
            'focus': """
🔔 **提醒：注意注册率 / Reminder: Focus on Registration Rate**

您的注册率需要关注和提升：
Your registration rate needs attention and improvement:

• 优化与客户的沟通方式
• 及时跟进潜在客户
• 学习成功案例的经验

如需培训或帮助，请联系管理团队。
Contact management team if you need training or help.
            """.strip(),
            'contact': """
🔔 **提醒：主动联系客户 / Reminder: Proactively Contact Clients**

请主动联系您的客户：
Please proactively contact your clients:

• 跟进未响应的客户
• 确认已注册客户的状态
• 提供必要的支持和指导

客户关系是成功的关键！
Client relationships are the key to success!
            """.strip()
        }

        message = messages.get(reminder_type, "🔔 您有一条新提醒。")

        # Send reminder to target user
        await telegram_handler.send_message(target_user_id, message, parse_mode='markdown')

        # Confirm to admin
        target_member = await database.get_team_member_by_user_id(target_user_id)
        member_name = target_member.frontdesk_name if target_member else f"User {target_user_id}"

        confirmation_text = f"""
✅ **提醒已发送 / Reminder Sent**

已向 **{member_name}** 发送 {reminder_type} 类型的提醒。
Sent {reminder_type} reminder to **{member_name}**.

消息内容：
Message content:
{message[:200]}{'...' if len(message) > 200 else ''}
        """.strip()

        await telegram_handler.send_message(chat_id, confirmation_text, parse_mode='markdown')

        # Log the reminder
        logger.info(f"Manual reminder sent: {reminder_type} to user {target_user_id} by admin {user_id}")

    elif callback_data.startswith('custom_reminder_'):
        target_user_id = int(callback_data.split('custom_reminder_')[1])

        # Set conversation state for custom message
        telegram_handler.set_conversation_state(user_id, {
            'step': 'custom_reminder_message',
            'target_user_id': target_user_id
        })

        await telegram_handler.send_message(
            chat_id,
            "✏️ 请输入自定义提醒消息：\nPlease enter custom reminder message:"
        )


async def handle_custom_reminder_conversation(task_data: Dict[str, Any]):
    """Handle custom reminder message input."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    message = task_data['message']
    state = task_data['state']

    if state.get('step') == 'custom_reminder_message':
        target_user_id = state.get('target_user_id')

        # Send custom reminder
        custom_message = f"🔔 **管理员提醒 / Admin Reminder**\n\n{message}"
        await telegram_handler.send_message(target_user_id, custom_message, parse_mode='markdown')

        # Clear conversation state
        telegram_handler.clear_conversation_state(user_id)

        # Confirm to admin
        target_member = await database.get_team_member_by_user_id(target_user_id)
        member_name = target_member.frontdesk_name if target_member else f"User {target_user_id}"

        confirmation_text = f"""
✅ **自定义提醒已发送 / Custom Reminder Sent**

已向 **{member_name}** 发送自定义提醒。
Sent custom reminder to **{member_name}**.

消息内容：
Message content:
{message}
        """.strip()

        await telegram_handler.send_message(chat_id, confirmation_text, parse_mode='markdown')

        logger.info(f"Custom reminder sent to user {target_user_id} by admin {user_id}")


async def handle_reminder_system_callbacks(task_data: Dict[str, Any]):
    """Handle reminder system management callbacks."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data == 'refresh_reminders':
        await show_pending_reminders(task_data)

    elif callback_data == 'refresh_reminder_stats':
        await show_reminder_stats(task_data)

    elif callback_data == 'send_all_reminders':
        # Create task to send all pending reminders
        task = BotTask(
            task_type='reminder',
            priority=2,
            data={'action': 'send_all_pending'}
        )
        await database.create_task(task)

        await telegram_handler.send_message(
            chat_id,
            "⚡ 已安排发送所有待处理提醒。\nScheduled to send all pending reminders."
        )

    elif callback_data == 'clean_expired_reminders':
        # Clean expired reminders (older than 24 hours)
        expired_time = datetime.now() - timedelta(hours=24)
        async with database.get_connection() as db:
            cursor = await db.execute("""
                DELETE FROM reminders
                WHERE is_sent = FALSE AND scheduled_time < ?
            """, (expired_time,))
            await db.commit()
            deleted_count = cursor.rowcount

        await telegram_handler.send_message(
            chat_id,
            f"🗑️ 已清理 {deleted_count} 条过期提醒。\nCleaned {deleted_count} expired reminders."
        )

    elif callback_data == 'process_overdue_reminders':
        # Process overdue reminders immediately
        overdue_task = BotTask(
            task_type='reminder',
            priority=1,
            data={'action': 'process_overdue'}
        )
        await database.create_task(overdue_task)

        await telegram_handler.send_message(
            chat_id,
            "⚡ 正在处理过期提醒...\nProcessing overdue reminders..."
        )


# Command mapping for reminders module
REMINDERS_COMMANDS = {
    'remind': handle_remind_command
}

REMINDERS_CALLBACKS = {
    'refresh_reminders': handle_reminder_system_callbacks,
    'refresh_reminder_stats': handle_reminder_system_callbacks,
    'send_all_reminders': handle_reminder_system_callbacks,
    'clean_expired_reminders': handle_reminder_system_callbacks,
    'process_overdue_reminders': handle_reminder_system_callbacks,
    'reminder_list': lambda task_data: show_pending_reminders(task_data),
    'cancel_reminder': lambda task_data: telegram_handler.send_message(
        task_data['chat_id'], "操作已取消。 / Operation cancelled."
    )
}

# Add dynamic callbacks for manual reminders
for reminder_type in ['status', 'report', 'focus', 'contact']:
    REMINDERS_CALLBACKS[f'manual_reminder_{reminder_type}_*'] = handle_manual_reminder_callbacks

REMINDERS_CONVERSATIONS = {
    'custom_reminder_message': handle_custom_reminder_conversation
}
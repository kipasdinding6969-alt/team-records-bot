"""Client reporting handlers."""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from telethon import Button

from database import database
from models import ClientRecord, Reminder, BotTask
from telegram_handler import telegram_handler
from utils.formatting import format_client_record, format_date_chinese
from utils.validators import validate_phone_number, validate_date_format
from config import config, CATEGORY_TYPES, STATUS_TYPES

logger = logging.getLogger(__name__)


async def handle_report_command(task_data: Dict[str, Any]):
    """Handle /report command to start client record submission."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check if user is registered frontdesk staff
    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['frontdesk', 'manager', 'admin']:
        await telegram_handler.send_message(
            chat_id,
            "❌ 此功能仅限前台员工使用。\nThis feature is only for frontdesk staff."
        )
        return

    # Start client record wizard
    welcome_text = f"""
📋 **客户记录提交 / Client Record Submission**

您好 {member.frontdesk_name or member.first_name}！
Hello {member.frontdesk_name or member.first_name}!

请按步骤填写客户信息。点击开始：
Please fill in client information step by step. Click start:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [{'text': '🚀 开始填写 / Start Filling', 'callback_data': 'start_report_wizard'}],
        [{'text': '📊 查看今日记录 / View Today\'s Records', 'callback_data': 'view_today_records'}],
        [{'text': '❌ 取消 / Cancel', 'callback_data': 'cancel_report'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        welcome_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_start_report_wizard(task_data: Dict[str, Any]):
    """Start the client record submission wizard."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    message_id = task_data['message_id']

    member = await database.get_team_member_by_user_id(user_id)

    # Initialize wizard state
    wizard_state = {
        'step': 'date',
        'member': {
            'user_id': member.user_id,
            'frontdesk_name': member.frontdesk_name,
            'phone_number': member.phone_number
        },
        'record_data': {}
    }

    telegram_handler.set_conversation_state(user_id, wizard_state)

    # Ask for date
    date_text = f"""
📅 **步骤 1/11: 日期 / Step 1/11: Date**

请输入日期（格式：X月X日，例如：3月15日）
Please enter date (format: X月X日, e.g., 3月15日):

当前时间：{datetime.now().strftime('%m月%d日')}
Current time: {datetime.now().strftime('%m月%d日')}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [{'text': f'使用今日 / Use Today ({datetime.now().strftime("%m月%d日")})', 'callback_data': 'use_today_date'}],
        [{'text': '取消 / Cancel', 'callback_data': 'cancel_report'}]
    ])

    await telegram_handler.edit_message(
        chat_id,
        message_id,
        date_text,
        reply_markup=keyboard
    )


async def handle_report_wizard_conversation(task_data: Dict[str, Any]):
    """Handle wizard conversation messages."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    message = task_data['message']
    state = task_data['state']

    step = state.get('step')
    record_data = state.get('record_data', {})

    if step == 'date':
        await handle_date_input(user_id, chat_id, message, state)
    elif step == 'phone_remark':
        await handle_phone_remark_input(user_id, chat_id, message, state)
    elif step == 'category':
        await handle_category_selection(user_id, chat_id, message, state)
    elif step == 'recruiter':
        await handle_recruiter_input(user_id, chat_id, message, state)
    elif step == 'frontdesk_username':
        await handle_frontdesk_username_input(user_id, chat_id, message, state)
    elif step == 'client_number':
        await handle_client_number_input(user_id, chat_id, message, state)
    elif step == 'account_id':
        await handle_account_id_input(user_id, chat_id, message, state)
    elif step == 'client_condition':
        await handle_client_condition_input(user_id, chat_id, message, state)


async def handle_date_input(user_id: int, chat_id: int, date_input: str, state: Dict[str, Any]):
    """Handle date input validation and next step."""
    if not validate_date_format(date_input):
        error_text = """
❌ 日期格式错误。请使用格式：X月X日（例如：3月15日）
Invalid date format. Please use format: X月X日 (e.g., 3月15日)
        """.strip()
        await telegram_handler.send_message(chat_id, error_text)
        return

    # Save date and move to next step
    state['record_data']['date'] = date_input
    state['step'] = 'phone_remark'
    telegram_handler.set_conversation_state(user_id, state)

    next_text = """
📱 **步骤 2/11: 手机编辑 / Step 2/11: Phone Remark**

请输入设备信息（例如：65 IPHONE SE, 华为 P40）
Please enter device info (e.g., 65 IPHONE SE, Huawei P40):
    """.strip()

    await telegram_handler.send_message(chat_id, next_text)


async def handle_phone_remark_input(user_id: int, chat_id: int, phone_remark: str, state: Dict[str, Any]):
    """Handle phone remark input."""
    state['record_data']['phone_remark'] = phone_remark
    state['step'] = 'category'
    telegram_handler.set_conversation_state(user_id, state)

    # Show category options
    category_text = """
🏷️ **步骤 3/11: 类别 / Step 3/11: Category**

请选择来源类别：
Please select source category:
    """.strip()

    categories = list(CATEGORY_TYPES.keys())
    keyboard_rows = []
    for i in range(0, len(categories), 2):
        row = []
        for j in range(i, min(i + 2, len(categories))):
            row.append({'text': categories[j], 'callback_data': f'category_{CATEGORY_TYPES[categories[j]]}'})
        keyboard_rows.append(row)

    keyboard_rows.append([{'text': '取消 / Cancel', 'callback_data': 'cancel_report'}])
    keyboard = telegram_handler.create_inline_keyboard(keyboard_rows)

    await telegram_handler.send_message(chat_id, category_text, reply_markup=keyboard)


async def handle_category_selection(user_id: int, chat_id: int, category: str, state: Dict[str, Any]):
    """Handle category selection."""
    # Find Chinese name for category
    chinese_category = None
    for chinese, english in CATEGORY_TYPES.items():
        if english == category:
            chinese_category = chinese
            break

    if not chinese_category:
        await telegram_handler.send_message(chat_id, "❌ 无效的类别选择。\nInvalid category selection.")
        return

    state['record_data']['category'] = chinese_category
    state['step'] = 'recruiter'
    telegram_handler.set_conversation_state(user_id, state)

    recruiter_text = """
👤 **步骤 4/11: 招聘人员 / Step 4/11: Recruiter**

请输入招聘人员姓名：
Please enter recruiter name:
    """.strip()

    await telegram_handler.send_message(chat_id, recruiter_text)


async def handle_recruiter_input(user_id: int, chat_id: int, recruiter: str, state: Dict[str, Any]):
    """Handle recruiter input."""
    state['record_data']['recruiter'] = recruiter
    state['step'] = 'frontdesk_username'
    telegram_handler.set_conversation_state(user_id, state)

    # Auto-fill frontdesk info from member data
    member = state['member']
    state['record_data']['frontdesk'] = member['frontdesk_name']
    state['record_data']['frontdesk_number'] = member['phone_number']

    username_text = f"""
🆔 **步骤 5/11: 前台用户名 / Step 5/11: Frontdesk Username**

请输入前台Telegram用户名（例如：@ammeeeelia3589）：
Please enter frontdesk Telegram username (e.g., @ammeeeelia3589):

已自动填入前台信息：
Auto-filled frontdesk info:
• 前台 / Frontdesk: {member['frontdesk_name']}
• 前台号 / Phone: {member['phone_number']}
    """.strip()

    await telegram_handler.send_message(chat_id, username_text)


async def handle_frontdesk_username_input(user_id: int, chat_id: int, username: str, state: Dict[str, Any]):
    """Handle frontdesk username input."""
    # Ensure username starts with @
    if not username.startswith('@'):
        username = f'@{username}'

    state['record_data']['frontdesk_username'] = username
    state['step'] = 'client_number'
    telegram_handler.set_conversation_state(user_id, state)

    client_number_text = """
📞 **步骤 6/11: 客户号 / Step 6/11: Client Number**

请输入客户手机号码：
Please enter client phone number:
    """.strip()

    await telegram_handler.send_message(chat_id, client_number_text)


async def handle_client_number_input(user_id: int, chat_id: int, client_number: str, state: Dict[str, Any]):
    """Handle client number input."""
    if not validate_phone_number(client_number):
        error_text = """
❌ 无效的手机号码格式。请重新输入。
Invalid phone number format. Please re-enter.
        """.strip()
        await telegram_handler.send_message(chat_id, error_text)
        return

    state['record_data']['client_number'] = client_number
    state['step'] = 'account_id'
    telegram_handler.set_conversation_state(user_id, state)

    account_id_text = """
🆔 **步骤 7/11: 账户ID / Step 7/11: Account ID**

请输入账户ID：
Please enter account ID:
    """.strip()

    await telegram_handler.send_message(chat_id, account_id_text)


async def handle_account_id_input(user_id: int, chat_id: int, account_id: str, state: Dict[str, Any]):
    """Handle account ID input."""
    state['record_data']['account_id'] = account_id
    state['step'] = 'first_day_status'
    telegram_handler.set_conversation_state(user_id, state)

    first_day_text = """
📊 **步骤 8/11: 第一天状态 / Step 8/11: First Day Status**

请选择第一天状态：
Please select first day status:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '✅ 注册 / Registered', 'callback_data': 'first_day_registered'},
            {'text': '❌ 不注册 / Not Registered', 'callback_data': 'first_day_not_registered'}
        ],
        [{'text': '⏸️ 暂未确定 / TBD', 'callback_data': 'first_day_tbd'}],
        [{'text': '取消 / Cancel', 'callback_data': 'cancel_report'}]
    ])

    await telegram_handler.send_message(chat_id, first_day_text, reply_markup=keyboard)


async def handle_day_status_callback(task_data: Dict[str, Any]):
    """Handle day status callback selections."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    state = telegram_handler.get_conversation_state(user_id)
    if not state:
        return

    if callback_data.startswith('first_day_'):
        status = callback_data.split('first_day_')[1]
        if status == 'registered':
            state['record_data']['first_day'] = '注册'
        elif status == 'not_registered':
            state['record_data']['first_day'] = '不注册'
        else:  # tbd
            state['record_data']['first_day'] = '待定'

        state['step'] = 'second_day_status'
        telegram_handler.set_conversation_state(user_id, state)

        second_day_text = """
📊 **步骤 9/11: 第二天状态 / Step 9/11: Second Day Status**

请选择第二天状态：
Please select second day status:
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '✅ 注册 / Registered', 'callback_data': 'second_day_registered'},
                {'text': '❌ 不注册 / Not Registered', 'callback_data': 'second_day_not_registered'}
            ],
            [{'text': '⏸️ 暂未确定 / TBD', 'callback_data': 'second_day_tbd'}],
            [{'text': '取消 / Cancel', 'callback_data': 'cancel_report'}]
        ])

        await telegram_handler.send_message(chat_id, second_day_text, reply_markup=keyboard)

    elif callback_data.startswith('second_day_'):
        status = callback_data.split('second_day_')[1]
        if status == 'registered':
            state['record_data']['second_day'] = '注册'
        elif status == 'not_registered':
            state['record_data']['second_day'] = '不注册'
        else:  # tbd
            state['record_data']['second_day'] = '待定'

        state['step'] = 'client_condition'
        telegram_handler.set_conversation_state(user_id, state)

        condition_text = """
📝 **步骤 10/11: 客户情况 / Step 10/11: Client Condition**

请输入客户情况备注（可选，直接发送"跳过"可跳过此步骤）：
Please enter client condition notes (optional, send "skip" to skip this step):
        """.strip()

        await telegram_handler.send_message(chat_id, condition_text)


async def handle_client_condition_input(user_id: int, chat_id: int, condition: str, state: Dict[str, Any]):
    """Handle client condition input and show final confirmation."""
    if condition.lower() not in ['跳过', 'skip']:
        state['record_data']['client_condition'] = condition
    else:
        state['record_data']['client_condition'] = None

    # Show final confirmation
    await show_record_confirmation(user_id, chat_id, state)


async def show_record_confirmation(user_id: int, chat_id: int, state: Dict[str, Any]):
    """Show final record confirmation."""
    record_data = state['record_data']

    # Auto-generate row number (this would be calculated based on existing records)
    record_data['row_num'] = await get_next_row_number()

    confirmation_text = f"""
✅ **步骤 11/11: 确认提交 / Step 11/11: Confirm Submission**

请确认以下客户记录信息：
Please confirm the following client record information:

📋 **记录详情 / Record Details:**
• 行号 / Row: {record_data['row_num']}
• 日期 / Date: {record_data['date']}
• 设备 / Device: {record_data['phone_remark']}
• 前台 / Frontdesk: {record_data['frontdesk']}
• 类别 / Category: {record_data['category']}
• 招聘人员 / Recruiter: {record_data['recruiter']}
• 前台号 / Frontdesk Phone: {record_data['frontdesk_number']}
• 前台用户名 / Username: {record_data['frontdesk_username']}
• 客户号 / Client Phone: {record_data['client_number']}
• 账户ID / Account ID: {record_data['account_id']}
• 第一天 / Day 1: {record_data['first_day']}
• 第二天 / Day 2: {record_data['second_day']}
• 客户情况 / Condition: {record_data.get('client_condition', '无 / None')}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '✅ 确认提交 / Confirm Submit', 'callback_data': 'confirm_submit_record'},
            {'text': '✏️ 修改 / Edit', 'callback_data': 'edit_record'}
        ],
        [{'text': '❌ 取消 / Cancel', 'callback_data': 'cancel_report'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        confirmation_text,
        reply_markup=keyboard
    )


async def handle_confirm_submit_record(task_data: Dict[str, Any]):
    """Handle final record submission."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    state = telegram_handler.get_conversation_state(user_id)
    if not state:
        return

    record_data = state['record_data']

    try:
        # Create client record
        client_record = ClientRecord(
            row_num=record_data['row_num'],
            date=record_data['date'],
            phone_remark=record_data['phone_remark'],
            frontdesk=record_data['frontdesk'],
            category=record_data['category'],
            recruiter=record_data['recruiter'],
            frontdesk_number=record_data['frontdesk_number'],
            frontdesk_username=record_data['frontdesk_username'],
            client_number=record_data['client_number'],
            account_id=record_data['account_id'],
            first_day=record_data['first_day'],
            second_day=record_data['second_day'],
            client_condition=record_data.get('client_condition')
        )

        record_id = await database.create_client_record(client_record)

        # Create reminders for follow-up
        await create_follow_up_reminders(record_id, user_id, record_data)

        # Clear conversation state
        telegram_handler.clear_conversation_state(user_id)

        success_text = f"""
✅ **记录提交成功！/ Record Submitted Successfully!**

记录ID: {record_id}
客户: {record_data['client_number']}
账户: {record_data['account_id']}

🔔 已设置自动提醒：
Automatic reminders set:
• 24小时后第一天状态提醒
• 48小时后第二天状态提醒

感谢您的提交！
Thank you for your submission!
        """.strip()

        await telegram_handler.send_message(chat_id, success_text)

        # Notify managers about new record
        manager_notification = f"""
📋 **新客户记录 / New Client Record**

前台: {record_data['frontdesk']}
客户: {record_data['client_number']}
账户: {record_data['account_id']}
类别: {record_data['category']}
        """.strip()

        await telegram_handler.broadcast_to_managers(manager_notification)

        logger.info(f"New client record created: {record_id} by user {user_id}")

    except Exception as e:
        logger.error(f"Failed to create client record: {e}")
        error_text = """
❌ 记录提交失败，请稍后重试。
Record submission failed, please try again later.
        """.strip()

        await telegram_handler.send_message(chat_id, error_text)


async def get_next_row_number() -> int:
    """Get the next row number for client records."""
    async with database.get_connection() as db:
        cursor = await db.execute("SELECT MAX(row_num) FROM client_records")
        max_row = await cursor.fetchone()
        return (max_row[0] or 0) + 1


async def create_follow_up_reminders(record_id: int, user_id: int, record_data: Dict[str, Any]):
    """Create follow-up reminders for day 1 and day 2 status."""
    from datetime import timedelta

    now = datetime.now()

    # Day 1 reminder (24 hours)
    if record_data['first_day'] in ['待定', '暂未确定']:
        day1_reminder = Reminder(
            client_record_id=record_id,
            frontdesk_user_id=user_id,
            reminder_type='day1',
            scheduled_time=now + timedelta(hours=config.bot.day1_reminder_hours),
            message=f"🔔 请更新客户 {record_data['client_number']} 的第一天注册状态。"
        )
        await database.create_reminder(day1_reminder)

    # Day 2 reminder (48 hours)
    if record_data['second_day'] in ['待定', '暂未确定']:
        day2_reminder = Reminder(
            client_record_id=record_id,
            frontdesk_user_id=user_id,
            reminder_type='day2',
            scheduled_time=now + timedelta(hours=config.bot.day2_reminder_hours),
            message=f"🔔 请更新客户 {record_data['client_number']} 的第二天注册状态。"
        )
        await database.create_reminder(day2_reminder)


async def handle_view_today_records(task_data: Dict[str, Any]):
    """Handle viewing today's records for the user."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        return

    # Get today's records
    today_date = format_date_chinese(datetime.now())
    records = await database.get_client_records_by_frontdesk(member.frontdesk_name)

    today_records = [r for r in records if r.date == today_date]

    if not today_records:
        no_records_text = f"""
📊 **今日记录 / Today's Records**

暂无今日记录。
No records for today.

日期: {today_date}
前台: {member.frontdesk_name}
        """.strip()

        await telegram_handler.send_message(chat_id, no_records_text)
        return

    # Format records list
    records_text = f"📊 **今日记录 / Today's Records** ({len(today_records)} 条)\n\n"

    for i, record in enumerate(today_records[:5]):  # Show max 5 records
        records_text += f"**{i + 1}.** {format_client_record(record)}\n\n"

    if len(today_records) > 5:
        records_text += f"... 还有 {len(today_records) - 5} 条记录\n... {len(today_records) - 5} more records"

    keyboard = telegram_handler.create_inline_keyboard([
        [{'text': '📋 新增记录 / New Record', 'callback_data': 'start_report_wizard'}],
        [{'text': '📈 查看统计 / View Stats', 'callback_data': 'view_stats'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        records_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


# Command mapping for reporting module
REPORTING_COMMANDS = {
    'report': handle_report_command
}

REPORTING_CALLBACKS = {
    'start_report_wizard': handle_start_report_wizard,
    'view_today_records': handle_view_today_records,
    'use_today_date': lambda task_data: handle_date_input(
        task_data['user_id'],
        task_data['chat_id'],
        datetime.now().strftime("%m月%d日"),
        telegram_handler.get_conversation_state(task_data['user_id'])
    ),
    'confirm_submit_record': handle_confirm_submit_record,
    'cancel_report': lambda task_data: telegram_handler.send_message(
        task_data['chat_id'], "操作已取消。 / Operation cancelled."
    )
}

# Add category callbacks
for chinese, english in CATEGORY_TYPES.items():
    REPORTING_CALLBACKS[f'category_{english}'] = lambda task_data, cat=english: handle_category_selection(
        task_data['user_id'], task_data['chat_id'], cat,
        telegram_handler.get_conversation_state(task_data['user_id'])
    )

# Add day status callbacks
REPORTING_CALLBACKS.update({
    'first_day_registered': handle_day_status_callback,
    'first_day_not_registered': handle_day_status_callback,
    'first_day_tbd': handle_day_status_callback,
    'second_day_registered': handle_day_status_callback,
    'second_day_not_registered': handle_day_status_callback,
    'second_day_tbd': handle_day_status_callback,
})

REPORTING_CONVERSATIONS = {
    'date': handle_report_wizard_conversation,
    'phone_remark': handle_report_wizard_conversation,
    'category': handle_report_wizard_conversation,
    'recruiter': handle_report_wizard_conversation,
    'frontdesk_username': handle_report_wizard_conversation,
    'client_number': handle_report_wizard_conversation,
    'account_id': handle_report_wizard_conversation,
    'client_condition': handle_report_wizard_conversation
}
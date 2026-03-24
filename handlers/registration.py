"""Team member registration handlers."""
import logging
from typing import Dict, Any

from telethon import Button

from database import database
from models import TeamMember
from telegram_handler import telegram_handler
from utils.formatting import format_user_info
from utils.validators import validate_phone_number
from config import FRONTDESK_STAFF

logger = logging.getLogger(__name__)


async def handle_start_command(task_data: Dict[str, Any]):
    """Handle /start command for team member registration."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    username = task_data.get('username')
    first_name = task_data.get('first_name')
    last_name = task_data.get('last_name')

    # Check if user is already registered
    member = await database.get_team_member_by_user_id(user_id)

    if member and member.role != 'unregistered':
        welcome_text = f"""
👋 Welcome back, {member.frontdesk_name or first_name}!

You are already registered as: **{member.role}**

Available commands:
• /status - View your today's stats
• /clients - List your active clients
• /report - Submit daily client record

For managers/admins:
• /dashboard - Team overview
• /summary - Daily summary
• /team_report [team] - Team assessment
        """.strip()

        await telegram_handler.send_message(chat_id, welcome_text, parse_mode='markdown')
        return

    # New user registration flow
    welcome_text = """
🎯 **欢迎来到团队记录机器人！**
Welcome to Team Records Bot!

请选择您的角色 / Please select your role:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '前台员工 / Frontdesk Staff', 'callback_data': 'register_frontdesk'},
            {'text': '经理 / Manager', 'callback_data': 'register_manager'}
        ],
        [
            {'text': '管理员 / Admin', 'callback_data': 'register_admin'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        welcome_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )

    # Set conversation state
    telegram_handler.set_conversation_state(user_id, {
        'step': 'role_selection',
        'user_info': {
            'user_id': user_id,
            'chat_id': chat_id,
            'username': username,
            'first_name': first_name,
            'last_name': last_name
        }
    })


async def handle_registration_callback(task_data: Dict[str, Any]):
    """Handle registration callback buttons."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']
    message_id = task_data['message_id']

    state = telegram_handler.get_conversation_state(user_id)
    if not state or state.get('step') != 'role_selection':
        return

    role = callback_data.split('_')[1]  # Extract role from callback_data

    # Update state with selected role
    state['selected_role'] = role
    state['step'] = 'frontdesk_name' if role == 'frontdesk' else 'phone_number'
    telegram_handler.set_conversation_state(user_id, state)

    if role == 'frontdesk':
        # Ask for frontdesk name
        text = """
请输入您的前台名称（例如：阿YIM, 阿俊）
Please enter your frontdesk name (e.g., 阿YIM, 阿俊):
        """.strip()

        await telegram_handler.edit_message(chat_id, message_id, text)
    else:
        # Ask for phone number for managers/admins
        text = f"""
您选择了角色：**{role.capitalize()}**

请输入您的手机号码：
Please enter your phone number:
        """.strip()

        await telegram_handler.edit_message(chat_id, message_id, text, parse_mode='markdown')


async def handle_registration_conversation(task_data: Dict[str, Any]):
    """Handle registration conversation messages."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    message = task_data['message']
    state = task_data['state']

    if state.get('step') == 'frontdesk_name':
        await handle_frontdesk_name_input(user_id, chat_id, message, state)
    elif state.get('step') == 'phone_number':
        await handle_phone_number_input(user_id, chat_id, message, state)


async def handle_frontdesk_name_input(user_id: int, chat_id: int, frontdesk_name: str, state: Dict[str, Any]):
    """Handle frontdesk name input."""
    # Validate frontdesk name
    if frontdesk_name not in FRONTDESK_STAFF:
        available_names = ', '.join(FRONTDESK_STAFF.keys())
        error_text = f"""
❌ 无效的前台名称。可用的名称：{available_names}
Invalid frontdesk name. Available names: {available_names}

请重新输入您的前台名称：
Please re-enter your frontdesk name:
        """.strip()

        await telegram_handler.send_message(chat_id, error_text)
        return

    # Update state and ask for phone number
    state['frontdesk_name'] = frontdesk_name
    state['step'] = 'phone_number'
    telegram_handler.set_conversation_state(user_id, state)

    text = """
请输入您的手机号码：
Please enter your phone number:
    """.strip()

    await telegram_handler.send_message(chat_id, text)


async def handle_phone_number_input(user_id: int, chat_id: int, phone_number: str, state: Dict[str, Any]):
    """Handle phone number input and complete registration."""
    # Validate phone number
    if not validate_phone_number(phone_number):
        error_text = """
❌ 无效的手机号码格式。请输入有效的手机号码。
Invalid phone number format. Please enter a valid phone number.
        """.strip()

        await telegram_handler.send_message(chat_id, error_text)
        return

    # Create team member record
    user_info = state['user_info']
    member = TeamMember(
        user_id=user_info['user_id'],
        chat_id=user_info['chat_id'],
        username=user_info['username'],
        first_name=user_info['first_name'],
        last_name=user_info['last_name'],
        phone_number=phone_number,
        frontdesk_name=state.get('frontdesk_name'),
        role=state['selected_role'],
        is_active=True
    )

    try:
        await database.create_team_member(member)

        # Clear conversation state
        telegram_handler.clear_conversation_state(user_id)

        # Send success message
        success_text = f"""
✅ **注册成功！Registration Successful!**

**您的信息 / Your Information:**
• 用户名 / Username: {user_info['username'] or 'N/A'}
• 姓名 / Name: {user_info['first_name']} {user_info['last_name'] or ''}
• 角色 / Role: {state['selected_role'].capitalize()}
• 手机号 / Phone: {phone_number}
"""

        if state.get('frontdesk_name'):
            success_text += f"• 前台名称 / Frontdesk Name: {state['frontdesk_name']}\n"

        success_text += """

**可用命令 / Available Commands:**
• /status - 查看今日统计 / View today's stats
• /clients - 查看活跃客户 / View active clients
• /report - 提交客户记录 / Submit client record
        """.strip()

        # Add role-specific commands
        if state['selected_role'] in ['manager', 'admin']:
            success_text += """

**管理命令 / Management Commands:**
• /dashboard - 团队总览 / Team overview
• /summary - 日报 / Daily summary
• /team_report [team] - 团队评估 / Team assessment
• /finance - 财务概览 / Financial overview
• /performance [name] - 个人表现 / Individual performance
            """.strip()

        if state['selected_role'] == 'admin':
            success_text += """
• /remind [name] - 发送提醒 / Send reminder
• /export - 导出数据 / Export data
• /sync - 同步表格 / Sync sheets
            """.strip()

        await telegram_handler.send_message(chat_id, success_text, parse_mode='markdown')

        # Notify admins about new registration
        admin_notification = f"""
🆕 **新用户注册 / New User Registration**

• 用户 / User: {format_user_info(user_info)}
• 角色 / Role: {state['selected_role'].capitalize()}
• 前台名称 / Frontdesk: {state.get('frontdesk_name', 'N/A')}
• 手机 / Phone: {phone_number}
        """.strip()

        await telegram_handler.broadcast_to_admins(admin_notification)

        logger.info(f"New user registered: {user_id} as {state['selected_role']}")

    except Exception as e:
        logger.error(f"Failed to register user {user_id}: {e}")
        error_text = """
❌ 注册失败，请稍后重试。
Registration failed, please try again later.
        """.strip()

        await telegram_handler.send_message(chat_id, error_text)


async def handle_profile_command(task_data: Dict[str, Any]):
    """Handle /profile command to show user profile."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    member = await database.get_team_member_by_user_id(user_id)

    if not member or member.role == 'unregistered':
        await telegram_handler.send_message(
            chat_id,
            "❌ 您还未注册。请使用 /start 命令开始注册。\nYou are not registered. Please use /start to register."
        )
        return

    profile_text = f"""
👤 **个人资料 / Profile**

• **用户ID / User ID:** {member.user_id}
• **用户名 / Username:** @{member.username or 'N/A'}
• **姓名 / Name:** {member.first_name} {member.last_name or ''}
• **角色 / Role:** {member.role.capitalize()}
• **手机号 / Phone:** {member.phone_number or 'N/A'}
• **前台名称 / Frontdesk:** {member.frontdesk_name or 'N/A'}
• **注册时间 / Registered:** {member.registered_at.strftime('%Y-%m-%d %H:%M') if member.registered_at else 'N/A'}
• **最后活动 / Last Active:** {member.last_active.strftime('%Y-%m-%d %H:%M') if member.last_active else 'N/A'}
• **状态 / Status:** {'活跃 / Active' if member.is_active else '非活跃 / Inactive'}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [{'text': '更新资料 / Update Profile', 'callback_data': 'update_profile'}],
        [{'text': '注销账户 / Deactivate Account', 'callback_data': 'deactivate_account'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        profile_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_update_profile_callback(task_data: Dict[str, Any]):
    """Handle profile update callback."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data == 'update_profile':
        text = """
请选择要更新的信息 / Select information to update:
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '手机号 / Phone', 'callback_data': 'update_phone'},
                {'text': '前台名称 / Frontdesk Name', 'callback_data': 'update_frontdesk'}
            ],
            [{'text': '取消 / Cancel', 'callback_data': 'cancel_update'}]
        ])

        await telegram_handler.send_message(chat_id, text, reply_markup=keyboard)

    elif callback_data == 'deactivate_account':
        confirmation_text = """
⚠️ **确认注销账户 / Confirm Account Deactivation**

这将停用您的账户并清除所有数据。您确定要继续吗？
This will deactivate your account and clear all data. Are you sure you want to continue?
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '确认 / Confirm', 'callback_data': 'confirm_deactivate'},
                {'text': '取消 / Cancel', 'callback_data': 'cancel_deactivate'}
            ]
        ])

        await telegram_handler.send_message(
            chat_id,
            confirmation_text,
            parse_mode='markdown',
            reply_markup=keyboard
        )


async def handle_deactivate_account(task_data: Dict[str, Any]):
    """Handle account deactivation."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    try:
        # Deactivate account
        async with database.get_connection() as db:
            await db.execute("""
                UPDATE team_members SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            await db.commit()

        success_text = """
✅ **账户已注销 / Account Deactivated**

您的账户已被停用。如需重新激活，请联系管理员。
Your account has been deactivated. To reactivate, please contact an administrator.
        """.strip()

        await telegram_handler.send_message(chat_id, success_text, parse_mode='markdown')

        # Notify admins
        admin_notification = f"🚫 User {user_id} has deactivated their account."
        await telegram_handler.broadcast_to_admins(admin_notification)

        logger.info(f"User {user_id} deactivated their account")

    except Exception as e:
        logger.error(f"Failed to deactivate account for user {user_id}: {e}")
        error_text = """
❌ 注销失败，请稍后重试。
Deactivation failed, please try again later.
        """.strip()

        await telegram_handler.send_message(chat_id, error_text)


# Command mapping for registration module
REGISTRATION_COMMANDS = {
    'start': handle_start_command,
    'profile': handle_profile_command
}

REGISTRATION_CALLBACKS = {
    'register_frontdesk': handle_registration_callback,
    'register_manager': handle_registration_callback,
    'register_admin': handle_registration_callback,
    'update_profile': handle_update_profile_callback,
    'deactivate_account': handle_update_profile_callback,
    'confirm_deactivate': handle_deactivate_account,
    'cancel_deactivate': lambda task_data: telegram_handler.send_message(
        task_data['chat_id'], "操作已取消。 / Operation cancelled."
    ),
    'cancel_update': lambda task_data: telegram_handler.send_message(
        task_data['chat_id'], "更新已取消。 / Update cancelled."
    )
}

REGISTRATION_CONVERSATIONS = {
    'role_selection': handle_registration_conversation,
    'frontdesk_name': handle_registration_conversation,
    'phone_number': handle_registration_conversation
}
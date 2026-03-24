"""Main menu and navigation handlers."""
import logging
from typing import Dict, Any, List
from datetime import datetime

from telethon import Button

from database import database
from telegram_handler import telegram_handler

logger = logging.getLogger(__name__)


async def handle_start_command(task_data: Dict[str, Any]):
    """Handle /start command - show main menu."""
    await handle_menu_command(task_data)


async def handle_menu_command(task_data: Dict[str, Any]):
    """Handle /menu command - display main navigation menu."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check if user is registered
    member = await database.get_team_member_by_user_id(user_id)

    # Welcome text with main menu
    menu_text = f"""
🏠 **主菜单 / Main Menu**

欢迎来到团队记录机器人！
Welcome to Team Records Bot!

📅 **今日 / Today:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

请选择功能：
Please select a function:
    """.strip()

    # Create main menu keyboard
    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📊 今日总览 / Today Overview', 'callback_data': 'menu_today_overview'},
            {'text': '📈 数据分析 / Analytics', 'callback_data': 'menu_analytics'}
        ],
        [
            {'text': '📝 提交报告 / Submit Report', 'callback_data': 'menu_submit_report'},
            {'text': '👥 团队管理 / Team Manage', 'callback_data': 'menu_team_manage'}
        ],
        [
            {'text': '⏰ 提醒管理 / Reminders', 'callback_data': 'menu_reminders'},
            {'text': '💰 财务概览 / Finance', 'callback_data': 'menu_finance'}
        ],
        [
            {'text': '📋 我的客户 / My Clients', 'callback_data': 'menu_my_clients'},
            {'text': '⚙️ 设置 / Settings', 'callback_data': 'menu_settings'}
        ],
        [
            {'text': '📖 帮助 / Help', 'callback_data': 'menu_help'},
            {'text': '🔄 刷新 / Refresh', 'callback_data': 'menu_refresh'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        menu_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_today_overview(task_data: Dict[str, Any]):
    """Handle today overview from main menu."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        await telegram_handler.send_message(
            chat_id,
            "❌ 请先使用 /start 注册。\nPlease register using /start first."
        )
        return

    # Generate today's overview
    overview_data = await generate_today_overview(member)

    overview_text = f"""
📊 **今日总览 / Today Overview**

📅 **日期 / Date:** {datetime.now().strftime('%Y-%m-%d')} ({datetime.now().strftime('%m月%d日')})

{format_today_overview(overview_data)}

点击按钮查看详细信息：
Click buttons for detailed information:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📈 查看图表 / View Charts', 'callback_data': 'analytics_daily_funnel'},
            {'text': '📋 详细数据 / Detailed Data', 'callback_data': 'dashboard_today'}
        ],
        [
            {'text': '📝 新增记录 / New Record', 'callback_data': 'start_report_wizard'},
            {'text': '⏰ 待办提醒 / Pending Reminders', 'callback_data': 'dashboard_reminders'}
        ],
        [
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'},
            {'text': '🔄 刷新 / Refresh', 'callback_data': 'menu_today_overview'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        overview_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_today_overview(member) -> Dict[str, Any]:
    """Generate today's overview data."""
    today = datetime.now()
    today_str = today.strftime("%m月%d日")

    # Get user's own data if they're frontdesk
    if member.role == 'frontdesk':
        frontdesk_name = member.frontdesk_name or member.first_name
        records = await database.get_client_records_by_frontdesk(frontdesk_name)
        today_records = [r for r in records if r.date == today_str]

        personal_stats = {
            'new_clients': len(today_records),
            'registered': len([r for r in today_records if r.first_day == '注册']),
            'pending': len([r for r in today_records if r.first_day == '待定']),
            'training': len([r for r in today_records if r.second_day == '注册'])
        }
    else:
        personal_stats = None

    # Get team overview (for managers/admins or general stats)
    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT frontdesk_name FROM team_members
            WHERE role = 'frontdesk' AND is_active = TRUE
        """)
        frontdesks = [row[0] for row in await cursor.fetchall()]

    team_stats = {
        'total_new': 0,
        'total_registered': 0,
        'total_pending': 0,
        'total_training': 0,
        'active_frontdesks': len(frontdesks)
    }

    for frontdesk in frontdesks:
        records = await database.get_client_records_by_frontdesk(frontdesk)
        today_records = [r for r in records if r.date == today_str]

        team_stats['total_new'] += len(today_records)
        team_stats['total_registered'] += len([r for r in today_records if r.first_day == '注册'])
        team_stats['total_pending'] += len([r for r in today_records if r.first_day == '待定'])
        team_stats['total_training'] += len([r for r in today_records if r.second_day == '注册'])

    # Get pending reminders count
    pending_reminders = await database.get_pending_reminders()
    if member.role == 'frontdesk':
        user_reminders = [r for r in pending_reminders if r.frontdesk_user_id == member.user_id]
        reminders_count = len(user_reminders)
    else:
        reminders_count = len(pending_reminders)

    return {
        'member': member,
        'personal_stats': personal_stats,
        'team_stats': team_stats,
        'reminders_count': reminders_count,
        'date': today
    }


def format_today_overview(data: Dict[str, Any]) -> str:
    """Format today's overview for display."""
    member = data['member']
    personal_stats = data['personal_stats']
    team_stats = data['team_stats']
    reminders_count = data['reminders_count']

    overview_text = ""

    # Personal stats for frontdesk
    if personal_stats:
        conversion_rate = (personal_stats['registered'] / personal_stats['new_clients'] * 100) if personal_stats['new_clients'] > 0 else 0
        overview_text += f"""
**👤 个人统计 / Personal Stats ({member.frontdesk_name or member.first_name}):**
• 新增客户 / New Clients: {personal_stats['new_clients']}
• 成功注册 / Registered: {personal_stats['registered']} ({conversion_rate:.1f}%)
• 待处理 / Pending: {personal_stats['pending']}
• 完成培训 / Training: {personal_stats['training']}

"""

    # Team stats
    team_conversion = (team_stats['total_registered'] / team_stats['total_new'] * 100) if team_stats['total_new'] > 0 else 0
    overview_text += f"""
**🏢 团队统计 / Team Stats:**
• 活跃前台 / Active Frontdesk: {team_stats['active_frontdesks']}
• 团队新客户 / Team New Clients: {team_stats['total_new']}
• 团队注册 / Team Registered: {team_stats['total_registered']} ({team_conversion:.1f}%)
• 团队待处理 / Team Pending: {team_stats['total_pending']}
• 团队培训 / Team Training: {team_stats['total_training']}

**🔔 提醒 / Reminders:**
• 待处理提醒 / Pending Reminders: {reminders_count}
"""

    return overview_text.strip()


async def handle_menu_callbacks(task_data: Dict[str, Any]):
    """Handle menu-related callback queries."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data == 'menu_main' or callback_data == 'menu_refresh':
        # Return to main menu
        await handle_menu_command(task_data)

    elif callback_data == 'menu_today_overview':
        await handle_today_overview(task_data)

    elif callback_data == 'menu_analytics':
        # Show analytics submenu
        await show_analytics_submenu(task_data)

    elif callback_data == 'menu_submit_report':
        # Forward to reporting handler
        from handlers.reporting import handle_report_command
        await handle_report_command(task_data)

    elif callback_data == 'menu_team_manage':
        # Show team management options
        await show_team_management_submenu(task_data)

    elif callback_data == 'menu_reminders':
        # Forward to reminders handler
        from handlers.reminders import handle_reminders_command
        await handle_reminders_command(task_data)

    elif callback_data == 'menu_finance':
        # Forward to finance handler
        from handlers.finance import handle_finance_command
        await handle_finance_command(task_data)

    elif callback_data == 'menu_my_clients':
        # Show user's clients
        await show_my_clients(task_data)

    elif callback_data == 'menu_settings':
        # Show settings
        await show_settings_submenu(task_data)

    elif callback_data == 'menu_help':
        # Forward to help handler
        from handlers.help_guide import handle_help_command
        await handle_help_command(task_data)


async def show_analytics_submenu(task_data: Dict[str, Any]):
    """Show analytics submenu."""
    chat_id = task_data['chat_id']

    submenu_text = """
📈 **数据分析 / Analytics Menu**

选择要查看的分析类型：
Select the type of analysis to view:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📊 日报图表 / Daily Charts', 'callback_data': 'analytics_daily_charts'},
            {'text': '📈 趋势分析 / Trend Analysis', 'callback_data': 'analytics_trends'}
        ],
        [
            {'text': '🏆 排行榜 / Leaderboard', 'callback_data': 'analytics_leaderboard'},
            {'text': '🔥 转化漏斗 / Conversion Funnel', 'callback_data': 'analytics_funnel'}
        ],
        [
            {'text': '📉 对比分析 / Comparison', 'callback_data': 'analytics_comparison'},
            {'text': '🌡️ 热力图 / Heatmap', 'callback_data': 'analytics_heatmap'}
        ],
        [
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        submenu_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_team_management_submenu(task_data: Dict[str, Any]):
    """Show team management submenu."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['manager', 'admin']:
        await telegram_handler.send_message(
            chat_id,
            "❌ 此功能仅限管理员和经理使用。\nThis feature is only for managers and admins."
        )
        return

    submenu_text = """
👥 **团队管理 / Team Management**

选择管理功能：
Select management function:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📊 团队仪表板 / Team Dashboard', 'callback_data': 'dashboard_main'},
            {'text': '📝 日报生成 / Daily Summary', 'callback_data': 'generate_summary'}
        ],
        [
            {'text': '👥 团队评估 / Team Assessment', 'callback_data': 'team_assessment'},
            {'text': '📈 个人表现 / Individual Performance', 'callback_data': 'individual_performance'}
        ],
        [
            {'text': '📋 活跃成员 / Active Members', 'callback_data': 'active_members'},
            {'text': '⚙️ 权限管理 / Permission Management', 'callback_data': 'permission_management'}
        ],
        [
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        submenu_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_my_clients(task_data: Dict[str, Any]):
    """Show user's client list."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        await telegram_handler.send_message(
            chat_id,
            "❌ 请先使用 /start 注册。\nPlease register using /start first."
        )
        return

    if member.role not in ['frontdesk', 'manager', 'admin']:
        await telegram_handler.send_message(
            chat_id,
            "❌ 此功能仅限前台和管理人员使用。\nThis feature is only for frontdesk and management staff."
        )
        return

    # Get client records
    frontdesk_name = member.frontdesk_name or member.first_name
    records = await database.get_client_records_by_frontdesk(frontdesk_name)

    # Filter recent records (last 30 days)
    today = datetime.now()
    recent_records = []
    for record in records:
        try:
            record_date = datetime.strptime(f"2024年{record.date}", "%Y年%m月%d日")
            if (today - record_date).days <= 30:
                recent_records.append(record)
        except:
            continue

    clients_text = f"""
📋 **我的客户 / My Clients**

👤 **前台 / Frontdesk:** {frontdesk_name}
📅 **时间范围 / Time Range:** 最近30天 / Last 30 days

**📊 统计摘要 / Statistics:**
• 总客户数 / Total Clients: {len(recent_records)}
• 已注册 / Registered: {len([r for r in recent_records if r.first_day == '注册'])}
• 未注册 / Not Registered: {len([r for r in recent_records if r.first_day == '不注册'])}
• 待处理 / Pending: {len([r for r in recent_records if r.first_day == '待定'])}

点击按钮查看详细信息：
Click buttons for detailed information:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📝 新增客户 / New Client', 'callback_data': 'start_report_wizard'},
            {'text': '🔍 搜索客户 / Search Client', 'callback_data': 'search_clients'}
        ],
        [
            {'text': '📊 客户统计 / Client Stats', 'callback_data': 'client_statistics'},
            {'text': '📋 待跟进 / Follow-up List', 'callback_data': 'followup_list'}
        ],
        [
            {'text': '📈 我的图表 / My Charts', 'callback_data': 'my_charts'},
            {'text': '📤 导出数据 / Export Data', 'callback_data': 'export_my_data'}
        ],
        [
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        clients_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_settings_submenu(task_data: Dict[str, Any]):
    """Show settings submenu."""
    chat_id = task_data['chat_id']

    settings_text = """
⚙️ **设置 / Settings**

配置您的个人设置：
Configure your personal settings:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '🔔 通知设置 / Notifications', 'callback_data': 'settings_notifications'},
            {'text': '🌐 语言设置 / Language', 'callback_data': 'settings_language'}
        ],
        [
            {'text': '⏰ 时区设置 / Timezone', 'callback_data': 'settings_timezone'},
            {'text': '📊 报表偏好 / Report Preferences', 'callback_data': 'settings_reports'}
        ],
        [
            {'text': '👤 个人信息 / Profile', 'callback_data': 'settings_profile'},
            {'text': '🔐 隐私设置 / Privacy', 'callback_data': 'settings_privacy'}
        ],
        [
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        settings_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


# Command and callback mappings
MENU_COMMANDS = {
    'start': handle_start_command,
    'menu': handle_menu_command,
}

MENU_CALLBACKS = {
    'menu_main': handle_menu_callbacks,
    'menu_refresh': handle_menu_callbacks,
    'menu_today_overview': handle_menu_callbacks,
    'menu_analytics': handle_menu_callbacks,
    'menu_submit_report': handle_menu_callbacks,
    'menu_team_manage': handle_menu_callbacks,
    'menu_reminders': handle_menu_callbacks,
    'menu_finance': handle_menu_callbacks,
    'menu_my_clients': handle_menu_callbacks,
    'menu_settings': handle_menu_callbacks,
    'menu_help': handle_menu_callbacks,
}

MENU_CONVERSATIONS = {}
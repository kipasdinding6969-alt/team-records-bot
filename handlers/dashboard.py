"""Dashboard and management handlers."""
import logging
from typing import Dict, Any, List
from datetime import datetime, date, timedelta

from telethon import Button

from database import database
from models import DailySummaryRecord, TeamWeeklyRecord
from telegram_handler import telegram_handler
from utils.formatting import (
    format_dashboard_stats, format_daily_summary,
    format_team_assessment, format_number_with_percentage
)

logger = logging.getLogger(__name__)


async def handle_dashboard_command(task_data: Dict[str, Any]):
    """Handle /dashboard command for team overview."""
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

    # Generate dashboard
    dashboard_data = await generate_dashboard_data()

    dashboard_text = f"""
📊 **团队仪表板 / Team Dashboard**

📅 **日期 / Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

{format_dashboard_stats(dashboard_data)}

点击按钮查看详细信息：
Click buttons for detailed information:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📈 今日报告 / Today Report', 'callback_data': 'dashboard_today'},
            {'text': '📊 周报 / Weekly Report', 'callback_data': 'dashboard_weekly'}
        ],
        [
            {'text': '👥 团队详情 / Team Details', 'callback_data': 'dashboard_teams'},
            {'text': '🎯 个人表现 / Individual Performance', 'callback_data': 'dashboard_individual'}
        ],
        [
            {'text': '📋 活跃客户 / Active Clients', 'callback_data': 'dashboard_clients'},
            {'text': '⚠️ 待处理提醒 / Pending Reminders', 'callback_data': 'dashboard_reminders'}
        ],
        [{'text': '🔄 刷新 / Refresh', 'callback_data': 'refresh_dashboard'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        dashboard_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_dashboard_data() -> Dict[str, Any]:
    """Generate comprehensive dashboard data."""
    today = date.today()
    today_str = today.strftime("%m月%d日")

    # Get all frontdesk members
    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT frontdesk_name, COUNT(*) as active_clients
            FROM team_members tm
            LEFT JOIN client_records cr ON tm.frontdesk_name = cr.frontdesk
            WHERE tm.role = 'frontdesk' AND tm.is_active = TRUE
            GROUP BY tm.frontdesk_name
        """)
        frontdesk_stats = await cursor.fetchall()

    # Get today's statistics
    today_stats = {}
    for frontdesk_name, _ in frontdesk_stats:
        records = await database.get_client_records_by_frontdesk(frontdesk_name)
        today_records = [r for r in records if r.date == today_str]

        today_stats[frontdesk_name] = {
            'total_clients': len(records),
            'today_new': len(today_records),
            'today_registered': len([r for r in today_records if r.first_day == '注册']),
            'pending_day1': len([r for r in records if r.first_day not in ['注册', '不注册']]),
            'pending_day2': len([r for r in records if r.second_day not in ['注册', '不注册']])
        }

    # Get pending reminders
    pending_reminders = await database.get_pending_reminders()

    return {
        'date': today,
        'frontdesk_stats': frontdesk_stats,
        'today_stats': today_stats,
        'pending_reminders': len(pending_reminders),
        'total_frontdesk': len(frontdesk_stats),
        'total_clients': sum(stats['total_clients'] for stats in today_stats.values()),
        'today_new_total': sum(stats['today_new'] for stats in today_stats.values()),
        'today_registered_total': sum(stats['today_registered'] for stats in today_stats.values())
    }


async def handle_summary_command(task_data: Dict[str, Any]):
    """Handle /summary command for daily summary generation."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    args = task_data.get('args', [])

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['manager', 'admin']:
        await telegram_handler.send_message(
            chat_id,
            "❌ 此功能仅限管理员和经理使用。\nThis feature is only for managers and admins."
        )
        return

    # Parse date argument or use today
    target_date = date.today()
    if args:
        try:
            target_date = datetime.strptime(args[0], '%Y-%m-%d').date()
        except ValueError:
            await telegram_handler.send_message(
                chat_id,
                "❌ 日期格式错误。请使用格式：YYYY-MM-DD\nInvalid date format. Use: YYYY-MM-DD"
            )
            return

    # Generate daily summary
    summary_data = await generate_daily_summary(target_date)

    summary_text = f"""
📊 **日报 / Daily Summary Report**

📅 **日期 / Date:** {target_date.strftime('%Y-%m-%d')} ({target_date.strftime('%m月%d日')})

{format_daily_summary(summary_data)}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📤 导出Excel / Export Excel', 'callback_data': f'export_summary_{target_date}'},
            {'text': '📋 复制文本 / Copy Text', 'callback_data': f'copy_summary_{target_date}'}
        ],
        [
            {'text': '📅 选择日期 / Select Date', 'callback_data': 'select_summary_date'},
            {'text': '🔄 刷新 / Refresh', 'callback_data': f'refresh_summary_{target_date}'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        summary_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_daily_summary(target_date: date) -> Dict[str, Any]:
    """Generate daily summary data (Type 4 format)."""
    date_str = target_date.strftime("%m月%d日")

    # Get all frontdesk members
    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT frontdesk_name FROM team_members
            WHERE role = 'frontdesk' AND is_active = TRUE
        """)
        frontdesk_members = [row[0] for row in await cursor.fetchall()]

    summary_sections = {
        'today_stats': {},
        'cumulative_totals': {},
        'today_training_details': {},
        'total_training_details': {}
    }

    for frontdesk in frontdesk_members:
        # Get all records for this frontdesk
        records = await database.get_client_records_by_frontdesk(frontdesk)

        # Today's stats (Section A)
        today_records = [r for r in records if r.date == date_str]
        summary_sections['today_stats'][frontdesk] = {
            'new_powder': len(today_records),
            'today_reply': len([r for r in today_records if r.first_day != '待定']),
            'today_register': len([r for r in today_records if r.first_day == '注册']),
            'today_completed_training': len([r for r in today_records if r.second_day == '注册']),
            'today_withdraw': 0,  # This would come from financial records
            'today_new_order': 0   # This would come from financial records
        }

        # Cumulative totals (Section B)
        summary_sections['cumulative_totals'][frontdesk] = {
            'total_powder': len(records),
            'total_reply': len([r for r in records if r.first_day != '待定']),
            'total_register': len([r for r in records if r.first_day == '注册']),
            'total_completed_training': len([r for r in records if r.second_day == '注册']),
            'total_withdraw': 0,   # This would come from financial records
            'total_new_order': 0   # This would come from financial records
        }

        # Training details would be calculated from performance records
        # For now, using simplified calculations
        training_today = len([r for r in today_records if r.second_day == '注册'])
        summary_sections['today_training_details'][frontdesk] = {
            'today_training': training_today,
            'today_withdraw': 0,
            'today_not_withdraw': training_today,
            'today_training_and_withdraw': 0,
            'today_conversion': 0
        }

        training_total = len([r for r in records if r.second_day == '注册'])
        summary_sections['total_training_details'][frontdesk] = {
            'total_training': training_total,
            'total_withdraw': 0,
            'total_not_withdraw': training_total,
            'total_training_and_withdraw': 0,
            'total_conversion': 0
        }

    return {
        'date': target_date,
        'sections': summary_sections,
        'frontdesk_members': frontdesk_members
    }


async def handle_team_report_command(task_data: Dict[str, Any]):
    """Handle /team_report command for team assessment."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    args = task_data.get('args', [])

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['manager', 'admin']:
        await telegram_handler.send_message(
            chat_id,
            "❌ 此功能仅限管理员和经理使用。\nThis feature is only for managers and admins."
        )
        return

    if not args:
        # Show available teams
        available_teams = ['发财小组', '金鑫小组', '夏天小组']  # These could come from config
        teams_text = """
👥 **团队评估 / Team Assessment**

请指定团队名称：
Please specify team name:

可用团队 / Available teams:
""" + '\n'.join(f"• {team}" for team in available_teams) + """

使用方法 / Usage:
/team_report [团队名称]
/team_report 发财小组
        """.strip()

        await telegram_handler.send_message(chat_id, teams_text)
        return

    team_name = ' '.join(args)

    # Generate 5-day assessment report
    assessment_data = await generate_team_assessment(team_name)

    if not assessment_data:
        error_text = f"""
❌ **团队不存在 / Team Not Found**

团队 "{team_name}" 未找到或无数据。
Team "{team_name}" not found or no data available.
        """.strip()

        await telegram_handler.send_message(chat_id, error_text, parse_mode='markdown')
        return

    assessment_text = f"""
👥 **团队5天考核 / 5-Day Team Assessment**

{format_team_assessment(assessment_data)}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📤 导出报告 / Export Report', 'callback_data': f'export_team_{team_name}'},
            {'text': '📊 详细分析 / Detailed Analysis', 'callback_data': f'analyze_team_{team_name}'}
        ],
        [
            {'text': '🔄 刷新数据 / Refresh Data', 'callback_data': f'refresh_team_{team_name}'},
            {'text': '📋 其他团队 / Other Teams', 'callback_data': 'list_teams'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        assessment_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_team_assessment(team_name: str) -> Dict[str, Any]:
    """Generate 5-day team assessment data (Type 5 format)."""
    # For demo purposes, generate sample data
    # In real implementation, this would query actual team member data

    end_date = date.today()
    start_date = end_date - timedelta(days=4)  # 5-day period

    # Get team members (this would be configured per team)
    team_members = {
        '发财小组': ['阿YIM', '阿俊'],
        '金鑫小组': ['小王', '小李'],
        '夏天小组': ['阿明', '小红']
    }.get(team_name, [])

    if not team_members:
        return None

    date_range = f"{start_date.strftime('%-d/%-m/%Y')} - {end_date.strftime('%-d/%-m/%Y')}"

    assessment_data = {
        'team_name': team_name,
        'date_range': date_range,
        'start_date': start_date,
        'end_date': end_date,
        'members': {},
        'team_totals': {}
    }

    # Generate data for each team member
    for member in team_members:
        member_data = {
            'daily_activity': [],
            'training_conversion': [],
            'daily_totals': {
                'new_powder': 0,
                'today_reply': 0,
                'today_register': 0,
                'today_completed_training': 0,
                'today_withdraw': 0,
                'today_new_order': 0
            },
            'training_totals': {
                'today_training': 0,
                'today_withdraw': 0,
                'today_not_withdraw': 0,
                'today_training_and_withdraw': 0,
                'today_new_order': 0
            }
        }

        # Generate daily data for 5 days
        for day_offset in range(5):
            current_date = start_date + timedelta(days=day_offset)
            date_str = current_date.strftime("%m月%d日")

            # Get actual records for this member and date
            records = await database.get_client_records_by_frontdesk(member)
            day_records = [r for r in records if r.date == date_str]

            daily_activity = {
                'day': day_offset + 1,
                'date': current_date,
                'new_powder': len(day_records),
                'today_reply': len([r for r in day_records if r.first_day != '待定']),
                'today_register': len([r for r in day_records if r.first_day == '注册']),
                'today_completed_training': len([r for r in day_records if r.second_day == '注册']),
                'today_withdraw': 0,  # From financial records
                'today_new_order': 0  # From financial records
            }

            training_conversion = {
                'day': day_offset + 1,
                'date': current_date,
                'today_training': len([r for r in day_records if r.second_day == '注册']),
                'today_withdraw': 0,
                'today_not_withdraw': len([r for r in day_records if r.second_day == '注册']),
                'today_training_and_withdraw': 0,
                'today_new_order': 0
            }

            member_data['daily_activity'].append(daily_activity)
            member_data['training_conversion'].append(training_conversion)

            # Add to totals
            for key in member_data['daily_totals']:
                member_data['daily_totals'][key] += daily_activity.get(key, 0)

            for key in member_data['training_totals']:
                member_data['training_totals'][key] += training_conversion.get(key, 0)

        assessment_data['members'][member] = member_data

    # Calculate team totals
    team_daily_totals = {key: 0 for key in member_data['daily_totals'].keys()}
    team_training_totals = {key: 0 for key in member_data['training_totals'].keys()}

    for member_data in assessment_data['members'].values():
        for key, value in member_data['daily_totals'].items():
            team_daily_totals[key] += value
        for key, value in member_data['training_totals'].items():
            team_training_totals[key] += value

    assessment_data['team_totals'] = {
        'daily': team_daily_totals,
        'training': team_training_totals
    }

    return assessment_data


async def handle_status_command(task_data: Dict[str, Any]):
    """Handle /status command for personal stats."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role == 'unregistered':
        await telegram_handler.send_message(
            chat_id,
            "❌ 您还未注册。请使用 /start 命令开始注册。\nYou are not registered. Please use /start to register."
        )
        return

    # Generate personal stats
    stats = await generate_personal_stats(member)

    stats_text = f"""
📊 **个人统计 / Personal Statistics**

👤 **前台 / Frontdesk:** {member.frontdesk_name or member.first_name}
📅 **日期 / Date:** {datetime.now().strftime('%Y-%m-%d')}

{format_personal_stats(stats)}

💡 **提示 / Tips:**
• 使用 /report 提交新客户记录
• 使用 /clients 查看活跃客户
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📋 新增记录 / New Record', 'callback_data': 'start_report_wizard'},
            {'text': '👥 查看客户 / View Clients', 'callback_data': 'view_my_clients'}
        ],
        [
            {'text': '📈 历史统计 / Historical Stats', 'callback_data': 'view_historical_stats'},
            {'text': '🔄 刷新 / Refresh', 'callback_data': 'refresh_personal_stats'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        stats_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_personal_stats(member) -> Dict[str, Any]:
    """Generate personal statistics for a frontdesk member."""
    today = date.today()
    today_str = today.strftime("%m月%d日")

    # Get all records for this frontdesk
    records = await database.get_client_records_by_frontdesk(member.frontdesk_name or member.first_name)

    # Today's records
    today_records = [r for r in records if r.date == today_str]

    # Week's records
    week_start = today - timedelta(days=7)
    week_records = [r for r in records if datetime.strptime(f"2024年{r.date}", "%Y年%m月%d日").date() >= week_start]

    # Calculate statistics
    stats = {
        'today': {
            'total_records': len(today_records),
            'registered': len([r for r in today_records if r.first_day == '注册']),
            'not_registered': len([r for r in today_records if r.first_day == '不注册']),
            'pending': len([r for r in today_records if r.first_day not in ['注册', '不注册']])
        },
        'total': {
            'total_records': len(records),
            'registered': len([r for r in records if r.first_day == '注册']),
            'not_registered': len([r for r in records if r.first_day == '不注册']),
            'pending': len([r for r in records if r.first_day not in ['注册', '不注册']])
        },
        'week': {
            'total_records': len(week_records),
            'registered': len([r for r in week_records if r.first_day == '注册']),
            'not_registered': len([r for r in week_records if r.first_day == '不注册'])
        }
    }

    # Calculate rates
    if stats['today']['total_records'] > 0:
        stats['today']['registration_rate'] = (stats['today']['registered'] / stats['today']['total_records']) * 100
    else:
        stats['today']['registration_rate'] = 0

    if stats['total']['total_records'] > 0:
        stats['total']['registration_rate'] = (stats['total']['registered'] / stats['total']['total_records']) * 100
    else:
        stats['total']['registration_rate'] = 0

    # Get pending reminders
    pending_reminders = await database.get_pending_reminders()
    user_reminders = [r for r in pending_reminders if r.frontdesk_user_id == member.user_id]

    stats['reminders'] = {
        'pending': len(user_reminders),
        'day1': len([r for r in user_reminders if r.reminder_type == 'day1']),
        'day2': len([r for r in user_reminders if r.reminder_type == 'day2'])
    }

    return stats


def format_personal_stats(stats: Dict[str, Any]) -> str:
    """Format personal statistics for display."""
    today_rate = stats['today']['registration_rate']
    total_rate = stats['total']['registration_rate']

    return f"""
**📈 今日 / Today:**
• 新增客户 / New Clients: {stats['today']['total_records']}
• 成功注册 / Registered: {stats['today']['registered']} ({today_rate:.1f}%)
• 未注册 / Not Registered: {stats['today']['not_registered']}
• 待处理 / Pending: {stats['today']['pending']}

**📊 总计 / Total:**
• 总客户数 / Total Clients: {stats['total']['total_records']}
• 总注册数 / Total Registered: {stats['total']['registered']} ({total_rate:.1f}%)
• 总待处理 / Total Pending: {stats['total']['pending']}

**📅 本周 / This Week:**
• 本周新增 / Week New: {stats['week']['total_records']}
• 本周注册 / Week Registered: {stats['week']['registered']}

**🔔 提醒 / Reminders:**
• 待处理提醒 / Pending: {stats['reminders']['pending']}
• 第一天提醒 / Day 1: {stats['reminders']['day1']}
• 第二天提醒 / Day 2: {stats['reminders']['day2']}
    """.strip()


# Dashboard callback handlers
async def handle_dashboard_callbacks(task_data: Dict[str, Any]):
    """Handle dashboard-related callbacks."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data == 'refresh_dashboard':
        # Refresh dashboard
        await handle_dashboard_command(task_data)

    elif callback_data == 'dashboard_today':
        # Show today's detailed report
        today_data = await generate_daily_summary(date.today())
        today_text = f"📊 **今日详细报告 / Today's Detailed Report**\n\n{format_daily_summary(today_data)}"
        await telegram_handler.send_message(chat_id, today_text, parse_mode='markdown')

    elif callback_data == 'dashboard_reminders':
        # Show pending reminders
        reminders = await database.get_pending_reminders()
        if not reminders:
            await telegram_handler.send_message(chat_id, "✅ 无待处理提醒。\nNo pending reminders.")
            return

        reminders_text = f"🔔 **待处理提醒 / Pending Reminders** ({len(reminders)} 条)\n\n"
        for i, reminder in enumerate(reminders[:10]):  # Show max 10
            reminders_text += f"**{i+1}.** {reminder.reminder_type} - {reminder.message}\n"
            reminders_text += f"   ⏰ {reminder.scheduled_time.strftime('%m-%d %H:%M')}\n\n"

        if len(reminders) > 10:
            reminders_text += f"... 还有 {len(reminders) - 10} 条提醒\n"

        await telegram_handler.send_message(chat_id, reminders_text, parse_mode='markdown')

    # Add more dashboard callback handlers as needed


# Command mapping for dashboard module
DASHBOARD_COMMANDS = {
    'dashboard': handle_dashboard_command,
    'summary': handle_summary_command,
    'team_report': handle_team_report_command,
    'status': handle_status_command
}

DASHBOARD_CALLBACKS = {
    'refresh_dashboard': handle_dashboard_callbacks,
    'dashboard_today': handle_dashboard_callbacks,
    'dashboard_weekly': handle_dashboard_callbacks,
    'dashboard_teams': handle_dashboard_callbacks,
    'dashboard_individual': handle_dashboard_callbacks,
    'dashboard_clients': handle_dashboard_callbacks,
    'dashboard_reminders': handle_dashboard_callbacks,
    'refresh_personal_stats': lambda task_data: handle_status_command(task_data)
}

DASHBOARD_CONVERSATIONS = {}
"""Formatting utilities for messages and data display."""
import re
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, date
from dataclasses import asdict

from models import ClientRecord, FinancialRecord, PerformanceRecord, TeamMember

__all__ = [
    'format_user_info', 'format_client_record', 'format_financial_record',
    'format_performance_record', 'format_dashboard_stats', 'format_daily_summary',
    'format_team_assessment', 'format_reminder', 'format_currency',
    'format_percentage', 'format_number_with_percentage', 'format_date_chinese',
    'format_datetime_chinese', 'format_table_row', 'format_report_header',
    'format_performance_stats', 'convert_chinese_date', 'format_duration',
    'format_file_size', 'format_phone_number', 'truncate_text',
    'format_boolean_chinese', 'format_status_emoji', 'format_priority_emoji',
    'format_list_with_numbers', 'format_error_message', 'format_success_message',
    'validate_gsheet_data', 'format_validation_error'
]


def format_user_info(user_info: Dict[str, Any]) -> str:
    """Format user information for display."""
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    last_name = user_info.get('last_name', '')
    user_id = user_info.get('user_id', '')

    name_parts = []
    if first_name:
        name_parts.append(first_name)
    if last_name:
        name_parts.append(last_name)

    name = ' '.join(name_parts) if name_parts else 'Unknown'

    if username:
        return f"{name} (@{username}, ID: {user_id})"
    else:
        return f"{name} (ID: {user_id})"


def format_client_record(record: ClientRecord) -> str:
    """Format client record for display."""
    status_emoji = {
        '注册': '✅',
        '不注册': '❌',
        '待定': '⏸️'
    }

    day1_status = status_emoji.get(record.first_day, '❓')
    day2_status = status_emoji.get(record.second_day, '❓')

    return f"""
**客户 #{record.row_num}**
📞 {record.client_number} | 🆔 {record.account_id}
📱 {record.phone_remark} | 📅 {record.date}
🏷️ {record.category} | 👤 {record.recruiter}
第一天: {day1_status} {record.first_day} | 第二天: {day2_status} {record.second_day}
{f'📝 {record.client_condition}' if record.client_condition else ''}
    """.strip()


def format_financial_record(record: FinancialRecord) -> str:
    """Format financial record for display."""
    return f"""
**财务记录 - {record.date}**
🆔 账户: {record.account_id} | 👥 群组: {record.group_id}
👤 前台: {record.frontdesk} | 🏢 平台: {record.platform}
💰 新单: ${record.new_order_amount or 0:.2f} | 💵 承压: ${record.pressure_amount or 0:.2f}
💸 总收入: ${record.total_in or 0:.2f}
{f'📝 {record.note}' if record.note else ''}
    """.strip()


def format_performance_record(record: PerformanceRecord) -> str:
    """Format performance record for display."""
    return f"""
**表现记录 - {record.name}**
🏷️ 类别: {record.category} | 👥 粉量: {record.powder_count}
📞 回复率: {record.reply_rate:.1f}% | 📋 注册: {record.completed_register}
📈 审核率: {record.review_rate:.1f}% | 🎯 转换率: {record.conversion_rate:.1f}%
📊 培训: {record.completed_training} | 💰 提款: {record.withdrawal} | 📈 新单: {record.new_order}
    """.strip()


def format_dashboard_stats(dashboard_data: Dict[str, Any]) -> str:
    """Format dashboard statistics for display."""
    stats = f"""
**📈 整体统计 / Overall Statistics:**
• 前台成员 / Frontdesk Members: {dashboard_data['total_frontdesk']}
• 总客户数 / Total Clients: {dashboard_data['total_clients']}
• 今日新增 / Today New: {dashboard_data['today_new_total']}
• 今日注册 / Today Registered: {dashboard_data['today_registered_total']}
• 待处理提醒 / Pending Reminders: {dashboard_data['pending_reminders']}

**👥 前台表现 / Frontdesk Performance:**
"""

    for frontdesk_name, stats_data in dashboard_data['today_stats'].items():
        rate = (stats_data['today_registered'] / stats_data['today_new'] * 100) if stats_data['today_new'] > 0 else 0
        stats += f"• {frontdesk_name}: {stats_data['today_new']} 新增, {stats_data['today_registered']} 注册 ({rate:.1f}%)\n"

    return stats.strip()


def format_daily_summary(summary_data: Dict[str, Any]) -> str:
    """Format daily summary report."""
    sections = summary_data['sections']
    totals = summary_data['totals']

    summary = f"""
**📊 今日汇总 / Today's Summary:**
• 新粉总数 / Total New: {totals['today_stats']['new_powder']}
• 回复总数 / Total Reply: {totals['today_stats']['today_reply']}
• 注册总数 / Total Register: {totals['today_stats']['today_register']}
• 培训总数 / Total Training: {totals['today_stats']['today_completed_training']}

**👥 个人表现 / Individual Performance:**
"""

    for frontdesk, stats in sections['today_stats'].items():
        rate = (stats['today_register'] / stats['new_powder'] * 100) if stats['new_powder'] > 0 else 0
        summary += f"• {frontdesk}: {stats['new_powder']} 粉丝, {stats['today_register']} 注册 ({rate:.1f}%)\n"

    return summary.strip()


def format_team_assessment(assessment_data: Dict[str, Any]) -> str:
    """Format team assessment report."""
    team_name = assessment_data['team_name']
    date_range = assessment_data['date_range']
    team_totals = assessment_data['team_totals']

    assessment = f"""
**🏆 团队: {team_name}**
📅 **时间段:** {date_range}

**📊 5天汇总 / 5-Day Summary:**
• 新粉总数: {team_totals['daily']['new_powder']}
• 回复总数: {team_totals['daily']['today_reply']}
• 注册总数: {team_totals['daily']['today_register']}
• 培训总数: {team_totals['daily']['today_completed_training']}

**👥 成员表现 / Member Performance:**
"""

    for member, data in assessment_data['members'].items():
        totals = data['daily_totals']
        rate = (totals['today_register'] / totals['new_powder'] * 100) if totals['new_powder'] > 0 else 0
        assessment += f"• {member}: {totals['new_powder']} 粉丝, {totals['today_register']} 注册 ({rate:.1f}%)\n"

    return assessment.strip()


def format_reminder(reminder) -> str:
    """Format reminder for display."""
    from models import Reminder  # Import here to avoid circular import

    scheduled_time = reminder.scheduled_time.strftime('%Y-%m-%d %H:%M')
    return f"""
🔔 **提醒 #{reminder.id}**
类型: {reminder.reminder_type}
计划时间: {scheduled_time}
状态: {'已发送' if reminder.is_sent else '待发送'}
{f'消息: {reminder.message[:50]}...' if reminder.message and len(reminder.message) > 50 else f'消息: {reminder.message}' if reminder.message else ''}
    """.strip()


def format_currency(amount: Optional[float], currency: str = "USD") -> str:
    """Format currency amount."""
    if amount is None:
        return "N/A"

    if currency == "USD":
        return f"${amount:.2f}"
    elif currency == "CNY":
        return f"¥{amount:.2f}"
    else:
        return f"{amount:.2f} {currency}"


def format_percentage(value: Optional[float], decimal_places: int = 1) -> str:
    """Format percentage value."""
    if value is None:
        return "N/A"
    return f"{value:.{decimal_places}f}%"


def format_number_with_percentage(numerator: int, denominator: int) -> str:
    """Format number with percentage."""
    if denominator == 0:
        return f"{numerator}/0 (N/A)"

    percentage = (numerator / denominator) * 100
    return f"{numerator}/{denominator} ({percentage:.1f}%)"


def format_date_chinese(date_input: Union[datetime, date, str]) -> str:
    """Format date in Chinese format (X月X日)."""
    if isinstance(date_input, str):
        return date_input
    elif isinstance(date_input, datetime):
        return date_input.strftime("%m月%d日").replace("0", "")
    elif isinstance(date_input, date):
        return date_input.strftime("%m月%d日").replace("0", "")
    else:
        return str(date_input)


def format_datetime_chinese(datetime_input: datetime) -> str:
    """Format datetime in Chinese format."""
    return datetime_input.strftime("%Y年%m月%d日 %H:%M").replace("年0", "年").replace("月0", "月").replace("日0", "日")


def format_table_row(*values) -> str:
    """Format table row with proper spacing."""
    formatted_values = []
    for value in values:
        if isinstance(value, float):
            formatted_values.append(f"{value:.1f}")
        else:
            formatted_values.append(str(value))

    return " | ".join(formatted_values)


def format_report_header(title: str, date_info: str = None) -> str:
    """Format report header."""
    header = f"📊 **{title}**\n"
    if date_info:
        header += f"📅 {date_info}\n"
    header += "=" * 40
    return header


def format_performance_stats(stats: Dict[str, Any]) -> str:
    """Format performance statistics."""
    return f"""
**📈 表现统计 / Performance Statistics:**
• 总客户 / Total Clients: {stats.get('total_clients', 0)}
• 注册率 / Registration Rate: {format_percentage(stats.get('registration_rate', 0))}
• 响应率 / Response Rate: {format_percentage(stats.get('response_rate', 0))}
• 转换率 / Conversion Rate: {format_percentage(stats.get('conversion_rate', 0))}

**📊 今日数据 / Today's Data:**
• 新增客户 / New Clients: {stats.get('today_new', 0)}
• 成功注册 / Registered: {stats.get('today_registered', 0)}
• 待处理 / Pending: {stats.get('today_pending', 0)}
    """.strip()


def convert_chinese_date(chinese_date: str) -> Optional[date]:
    """Convert Chinese date format to Python date object."""
    try:
        # Parse format like "3月15日"
        match = re.match(r'(\d{1,2})月(\d{1,2})日', chinese_date)
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            # Assume current year if not specified
            year = datetime.now().year
            return date(year, month, day)
        return None
    except (ValueError, AttributeError):
        return None


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable format."""
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} 分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} 小时"


def format_file_size(bytes_size: int) -> str:
    """Format file size in bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


def format_phone_number(phone: str) -> str:
    """Format phone number for display."""
    if not phone:
        return "N/A"

    # Remove spaces and special characters
    clean_phone = re.sub(r'[^\d+]', '', phone)

    # Format based on length and pattern
    if clean_phone.startswith('+86') and len(clean_phone) == 14:
        # Chinese mobile number
        return f"+86 {clean_phone[3:6]} {clean_phone[6:10]} {clean_phone[10:]}"
    elif clean_phone.startswith('+') and len(clean_phone) > 10:
        # International number
        country_code = clean_phone[1:3] if clean_phone[1:3].isdigit() else clean_phone[1:4]
        rest = clean_phone[len(country_code)+1:]
        return f"+{country_code} {rest}"
    else:
        return phone


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to specified length."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_boolean_chinese(value: bool) -> str:
    """Format boolean value in Chinese."""
    return "是" if value else "否"


def format_status_emoji(status: str) -> str:
    """Get emoji for status."""
    status_emojis = {
        '注册': '✅',
        '不注册': '❌',
        '待定': '⏸️',
        '成功': '✅',
        '失败': '❌',
        '进行中': '🔄',
        '完成': '✅',
        '暂停': '⏸️',
        '错误': '⚠️'
    }
    return status_emojis.get(status, '❓')


def format_priority_emoji(priority: int) -> str:
    """Get emoji for priority level."""
    if priority == 1:
        return "🔴"  # High
    elif priority == 2:
        return "🟡"  # Medium
    elif priority == 3:
        return "🟢"  # Low
    else:
        return "⚪"  # Default


def format_list_with_numbers(items: List[str], start_number: int = 1) -> str:
    """Format list with Chinese numbers."""
    chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    formatted_items = []

    for i, item in enumerate(items):
        if i < len(chinese_numbers):
            number = chinese_numbers[i]
        else:
            number = str(i + start_number)
        formatted_items.append(f"{number}. {item}")

    return "\n".join(formatted_items)


def format_error_message(error: Exception) -> str:
    """Format error message for user display."""
    error_type = type(error).__name__
    error_msg = str(error)

    # Common error translations
    translations = {
        'ValueError': '数值错误',
        'TypeError': '类型错误',
        'KeyError': '键错误',
        'IndexError': '索引错误',
        'ConnectionError': '连接错误',
        'TimeoutError': '超时错误'
    }

    chinese_type = translations.get(error_type, error_type)
    return f"❌ {chinese_type}: {error_msg}"


def format_success_message(action: str, details: str = None) -> str:
    """Format success message."""
    message = f"✅ {action}成功"
    if details:
        message += f"\n\n{details}"
    return message


# Data validation helpers for formatting
class validate_gsheet_data:
    """Google Sheets data validation helpers."""

    @staticmethod
    def validate_chinese_date(date_str: str) -> bool:
        """Validate Chinese date format."""
        if not date_str:
            return False
        pattern = r'^\d{1,2}月\d{1,2}日$'
        return bool(re.match(pattern, date_str))

    @staticmethod
    def validate_phone_format(phone: str) -> bool:
        """Validate phone number format."""
        if not phone:
            return False
        # Allow international format and Chinese mobile
        pattern = r'^(\+\d{1,3}[-.\s]?)?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}$'
        return bool(re.match(pattern, phone))

    @staticmethod
    def validate_account_id(account_id: str) -> bool:
        """Validate account ID format."""
        if not account_id:
            return False
        # Allow alphanumeric and some special characters
        pattern = r'^[A-Za-z0-9_\-/\s]{3,50}$'
        return bool(re.match(pattern, account_id))

    @staticmethod
    def validate_amount(amount_str: str) -> bool:
        """Validate amount string."""
        if not amount_str or amount_str in ['-', 'N/A', '']:
            return True  # Optional field
        try:
            float(amount_str.replace('$', '').replace(',', ''))
            return True
        except ValueError:
            return False


def format_validation_error(field: str, value: str, expected: str) -> str:
    """Format validation error message."""
    return f"❌ 字段 '{field}' 的值 '{value}' 格式错误。期望格式: {expected}"
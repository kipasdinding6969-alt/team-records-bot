"""Performance tracking handlers."""
import logging
from typing import Dict, Any, List
from datetime import datetime, date, timedelta

from telethon import Button

from database import database
from models import PerformanceRecord
from telegram_handler import telegram_handler
from utils.formatting import format_performance_stats, format_percentage
from i18n import t


async def _get_lang(user_id):
    from database import database
    return (await database.get_user_language(user_id)) or 'zh'

logger = logging.getLogger(__name__)


async def handle_performance_command(task_data: Dict[str, Any]):
    """Handle /performance command for individual performance tracking."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    args = task_data.get('args', [])

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    lang = await _get_lang(user_id)
    if not member or member.role not in ['manager', 'admin']:
        await telegram_handler.send_message(
            chat_id,
            t('err_manager_admin_only', lang)
        )
        return

    if not args:
        # Show available frontdesk members for performance review
        available_members = await get_available_frontdesk_members()

        if not available_members:
            await telegram_handler.send_message(
                chat_id,
                t('no_frontdesk_data', lang)
            )
            return

        members_text = f"""
{t('performance_analysis_title', lang)}

{t('performance_specify_member', lang)}

{t('available_members', lang)}:
""" + '\n'.join(f"• {member}" for member in available_members) + f"""

{t('performance_usage', lang)}:
/performance [成员姓名]
/performance 阿YIM
        """.strip()

        await telegram_handler.send_message(chat_id, members_text)
        return

    member_name = ' '.join(args)

    # Generate performance analysis
    performance_data = await generate_performance_analysis(member_name)

    if not performance_data:
        error_text = f"""
❌ **成员不存在 / Member Not Found**

成员 "{member_name}" 未找到或无数据。
Member "{member_name}" not found or no data available.
        """.strip()

        await telegram_handler.send_message(chat_id, error_text, parse_mode='markdown')
        return

    performance_text = f"""
📈 **个人表现分析 / Individual Performance Analysis**

👤 **成员 / Member:** {member_name}
📅 **分析日期 / Analysis Date:** {datetime.now().strftime('%Y-%m-%d')}

{format_performance_analysis(performance_data)}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📊 详细报告 / Detailed Report', 'callback_data': f'performance_detailed_{member_name}'},
            {'text': '📈 趋势图 / Trend Chart', 'callback_data': f'performance_trend_{member_name}'}
        ],
        [
            {'text': '📋 添加记录 / Add Record', 'callback_data': f'add_performance_{member_name}'},
            {'text': '🔄 刷新数据 / Refresh Data', 'callback_data': f'refresh_performance_{member_name}'}
        ],
        [
            {'text': '👥 其他成员 / Other Members', 'callback_data': 'list_performance_members'},
            {'text': '📤 导出报告 / Export Report', 'callback_data': f'export_performance_{member_name}'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        performance_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def get_available_frontdesk_members() -> List[str]:
    """Get list of available frontdesk members."""
    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT DISTINCT frontdesk_name FROM team_members
            WHERE role = 'frontdesk' AND is_active = TRUE AND frontdesk_name IS NOT NULL
        """)
        members = [row[0] for row in await cursor.fetchall()]

    return members


async def generate_performance_analysis(member_name: str) -> Dict[str, Any]:
    """Generate comprehensive performance analysis for a member."""
    # Get client records for this member
    client_records = await database.get_client_records_by_frontdesk(member_name)

    if not client_records:
        return None

    # Get performance records
    performance_records = await database.get_performance_records_by_name(member_name)

    # Calculate time-based metrics
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    today_str = today.strftime("%m月%d日")
    week_records = []
    month_records = []

    for record in client_records:
        try:
            # Parse Chinese date format
            record_date = datetime.strptime(f"2024年{record.date}", "%Y年%m月%d日").date()
            if record_date >= week_ago:
                week_records.append(record)
            if record_date >= month_ago:
                month_records.append(record)
        except ValueError:
            # Skip invalid dates
            continue

    today_records = [r for r in client_records if r.date == today_str]

    # Calculate key metrics
    analysis = {
        'member_name': member_name,
        'total_records': len(client_records),
        'today': calculate_daily_metrics(today_records),
        'week': calculate_period_metrics(week_records),
        'month': calculate_period_metrics(month_records),
        'overall': calculate_period_metrics(client_records),
        'categories': calculate_category_breakdown(client_records),
        'performance_trends': analyze_performance_trends(client_records),
        'conversion_funnel': calculate_conversion_funnel(client_records)
    }

    return analysis


def calculate_daily_metrics(records: List) -> Dict[str, Any]:
    """Calculate daily performance metrics."""
    if not records:
        return {
            'total_clients': 0,
            'registered': 0,
            'not_registered': 0,
            'pending': 0,
            'registration_rate': 0.0,
            'response_rate': 0.0
        }

    registered = len([r for r in records if r.first_day == '注册'])
    not_registered = len([r for r in records if r.first_day == '不注册'])
    pending = len([r for r in records if r.first_day not in ['注册', '不注册']])
    responded = len([r for r in records if r.first_day != '待定'])

    return {
        'total_clients': len(records),
        'registered': registered,
        'not_registered': not_registered,
        'pending': pending,
        'registration_rate': (registered / len(records)) * 100 if records else 0.0,
        'response_rate': (responded / len(records)) * 100 if records else 0.0
    }


def calculate_period_metrics(records: List) -> Dict[str, Any]:
    """Calculate metrics for a time period."""
    if not records:
        return {
            'total_clients': 0,
            'day1_registered': 0,
            'day2_registered': 0,
            'day1_rate': 0.0,
            'day2_rate': 0.0,
            'conversion_rate': 0.0
        }

    day1_registered = len([r for r in records if r.first_day == '注册'])
    day2_registered = len([r for r in records if r.second_day == '注册'])

    return {
        'total_clients': len(records),
        'day1_registered': day1_registered,
        'day2_registered': day2_registered,
        'day1_rate': (day1_registered / len(records)) * 100 if records else 0.0,
        'day2_rate': (day2_registered / len(records)) * 100 if records else 0.0,
        'conversion_rate': (day2_registered / day1_registered) * 100 if day1_registered else 0.0
    }


def calculate_category_breakdown(records: List) -> Dict[str, Dict[str, Any]]:
    """Calculate breakdown by category."""
    breakdown = {}

    for record in records:
        category = record.category
        if category not in breakdown:
            breakdown[category] = {
                'total': 0,
                'registered': 0,
                'not_registered': 0,
                'rate': 0.0
            }

        breakdown[category]['total'] += 1
        if record.first_day == '注册':
            breakdown[category]['registered'] += 1
        elif record.first_day == '不注册':
            breakdown[category]['not_registered'] += 1

    # Calculate rates
    for category, stats in breakdown.items():
        if stats['total'] > 0:
            stats['rate'] = (stats['registered'] / stats['total']) * 100

    return breakdown


def analyze_performance_trends(records: List) -> Dict[str, Any]:
    """Analyze performance trends over time."""
    # Group records by date
    daily_stats = {}

    for record in records:
        date = record.date
        if date not in daily_stats:
            daily_stats[date] = {
                'total': 0,
                'registered': 0,
                'rate': 0.0
            }

        daily_stats[date]['total'] += 1
        if record.first_day == '注册':
            daily_stats[date]['registered'] += 1

    # Calculate rates and trends
    for date, stats in daily_stats.items():
        if stats['total'] > 0:
            stats['rate'] = (stats['registered'] / stats['total']) * 100

    # Sort by date and calculate trend
    sorted_dates = sorted(daily_stats.keys(), key=lambda x: datetime.strptime(f"2024年{x}", "%Y年%m月%d日"))

    recent_rates = []
    for date in sorted_dates[-7:]:  # Last 7 days
        recent_rates.append(daily_stats[date]['rate'])

    trend = 'stable'
    if len(recent_rates) >= 2:
        if recent_rates[-1] > recent_rates[0]:
            trend = 'improving'
        elif recent_rates[-1] < recent_rates[0]:
            trend = 'declining'

    return {
        'daily_stats': daily_stats,
        'trend': trend,
        'recent_rates': recent_rates,
        'average_rate': sum(recent_rates) / len(recent_rates) if recent_rates else 0.0
    }


def calculate_conversion_funnel(records: List) -> Dict[str, Any]:
    """Calculate conversion funnel metrics."""
    if not records:
        return {
            'total_leads': 0,
            'responded': 0,
            'day1_registered': 0,
            'day2_registered': 0,
            'funnel_rates': {
                'response_rate': 0.0,
                'day1_conversion': 0.0,
                'day2_conversion': 0.0,
                'overall_conversion': 0.0
            }
        }

    total_leads = len(records)
    responded = len([r for r in records if r.first_day != '待定'])
    day1_registered = len([r for r in records if r.first_day == '注册'])
    day2_registered = len([r for r in records if r.second_day == '注册'])

    funnel = {
        'total_leads': total_leads,
        'responded': responded,
        'day1_registered': day1_registered,
        'day2_registered': day2_registered,
        'funnel_rates': {
            'response_rate': (responded / total_leads) * 100 if total_leads else 0.0,
            'day1_conversion': (day1_registered / responded) * 100 if responded else 0.0,
            'day2_conversion': (day2_registered / day1_registered) * 100 if day1_registered else 0.0,
            'overall_conversion': (day2_registered / total_leads) * 100 if total_leads else 0.0
        }
    }

    return funnel


def format_performance_analysis(data: Dict[str, Any]) -> str:
    """Format performance analysis for display."""
    today = data['today']
    week = data['week']
    overall = data['overall']
    trends = data['performance_trends']
    funnel = data['conversion_funnel']

    analysis_text = f"""
**📊 今日表现 / Today's Performance:**
• 新增客户 / New Clients: {today['total_clients']}
• 成功注册 / Registered: {today['registered']} ({today['registration_rate']:.1f}%)
• 响应率 / Response Rate: {today['response_rate']:.1f}%

**📅 本周表现 / This Week:**
• 总客户数 / Total Clients: {week['total_clients']}
• 第一天注册率 / Day 1 Rate: {week['day1_rate']:.1f}%
• 第二天注册率 / Day 2 Rate: {week['day2_rate']:.1f}%
• 转换率 / Conversion Rate: {week['conversion_rate']:.1f}%

**📈 总体表现 / Overall Performance:**
• 总客户数 / Total Clients: {overall['total_clients']}
• 总体注册率 / Overall Rate: {overall['day1_rate']:.1f}%
• 趋势 / Trend: {trends['trend']} (平均 {trends['average_rate']:.1f}%)

**🎯 转换漏斗 / Conversion Funnel:**
• 总线索 / Total Leads: {funnel['total_leads']}
• 响应率 / Response Rate: {funnel['funnel_rates']['response_rate']:.1f}%
• 第一天转换 / Day 1 Conversion: {funnel['funnel_rates']['day1_conversion']:.1f}%
• 第二天转换 / Day 2 Conversion: {funnel['funnel_rates']['day2_conversion']:.1f}%
• 整体转换率 / Overall Rate: {funnel['funnel_rates']['overall_conversion']:.1f}%

**🏷️ 类别分解 / Category Breakdown:**
"""

    for category, stats in data['categories'].items():
        analysis_text += f"• {category}: {stats['registered']}/{stats['total']} ({stats['rate']:.1f}%)\n"

    return analysis_text.strip()


async def handle_add_performance_record(task_data: Dict[str, Any]):
    """Handle adding new performance record."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    # Extract member name from callback data
    member_name = callback_data.split('add_performance_')[1]

    # Start performance record wizard
    wizard_text = f"""
📈 **添加表现记录 / Add Performance Record**

为成员 **{member_name}** 添加表现记录：
Add performance record for member **{member_name}**:

请点击开始填写：
Please click to start filling:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [{'text': '🚀 开始填写 / Start Filling', 'callback_data': f'start_perf_wizard_{member_name}'}],
        [{'text': '❌ 取消 / Cancel', 'callback_data': 'cancel_performance'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        wizard_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_performance_callbacks(task_data: Dict[str, Any]):
    """Handle performance-related callbacks."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data.startswith('performance_detailed_'):
        member_name = callback_data.split('performance_detailed_')[1]
        await show_detailed_performance(chat_id, member_name)

    elif callback_data.startswith('performance_trend_'):
        member_name = callback_data.split('performance_trend_')[1]
        await show_performance_trend(chat_id, member_name)

    elif callback_data.startswith('refresh_performance_'):
        member_name = callback_data.split('refresh_performance_')[1]
        # Refresh performance data
        new_task_data = {**task_data, 'args': [member_name]}
        await handle_performance_command(new_task_data)

    elif callback_data == 'list_performance_members':
        members = await get_available_frontdesk_members()
        members_text = "👥 **可用成员 / Available Members:**\n\n" + '\n'.join(f"• {member}" for member in members)
        await telegram_handler.send_message(chat_id, members_text, parse_mode='markdown')


async def show_detailed_performance(chat_id: int, member_name: str):
    """Show detailed performance breakdown."""
    performance_data = await generate_performance_analysis(member_name)

    if not performance_data:
        await telegram_handler.send_message(chat_id, "❌ 无法获取详细数据。\nCannot fetch detailed data.")
        return

    # Create detailed breakdown
    categories = performance_data['categories']
    trends = performance_data['performance_trends']

    detailed_text = f"""
📊 **详细表现报告 / Detailed Performance Report**

👤 **成员 / Member:** {member_name}

**🏷️ 按类别详细分解 / Detailed Category Breakdown:**
"""

    for category, stats in categories.items():
        detailed_text += f"""
**{category}:**
• 总客户 / Total: {stats['total']}
• 注册数 / Registered: {stats['registered']}
• 未注册 / Not Registered: {stats['not_registered']}
• 注册率 / Rate: {stats['rate']:.1f}%

"""

    detailed_text += f"""
**📈 趋势分析 / Trend Analysis:**
• 趋势方向 / Trend: {trends['trend']}
• 平均注册率 / Average Rate: {trends['average_rate']:.1f}%
• 最近7天数据点 / Last 7 Days: {len(trends['recent_rates'])}

**🎯 改进建议 / Improvement Suggestions:**
"""

    # Add suggestions based on performance
    overall_rate = performance_data['overall']['day1_rate']
    if overall_rate < 30:
        detailed_text += "• 注册率较低，建议优化客户沟通策略\n• Low registration rate, suggest optimizing communication strategy\n"
    elif overall_rate < 50:
        detailed_text += "• 注册率中等，可进一步提升话术技巧\n• Average registration rate, can improve communication skills\n"
    else:
        detailed_text += "• 注册率良好，保持现有策略\n• Good registration rate, maintain current strategy\n"

    if trends['trend'] == 'declining':
        detailed_text += "• 注意表现下降趋势，需要及时调整\n• Pay attention to declining trend, adjustment needed\n"

    await telegram_handler.send_message(chat_id, detailed_text.strip(), parse_mode='markdown')


async def show_performance_trend(chat_id: int, member_name: str):
    """Show performance trend analysis."""
    performance_data = await generate_performance_analysis(member_name)

    if not performance_data:
        await telegram_handler.send_message(chat_id, "❌ 无法获取趋势数据。\nCannot fetch trend data.")
        return

    trends = performance_data['performance_trends']
    recent_rates = trends['recent_rates']

    trend_text = f"""
📈 **表现趋势图 / Performance Trend Chart**

👤 **成员 / Member:** {member_name}

**📊 最近7天注册率 / Last 7 Days Registration Rate:**
"""

    # Simple ASCII trend visualization
    for i, rate in enumerate(recent_rates):
        bar_length = int(rate / 5)  # Scale for display
        bar = '█' * bar_length + '░' * (20 - bar_length)
        trend_text += f"Day {i+1}: {bar} {rate:.1f}%\n"

    trend_text += f"""

**📉 趋势分析 / Trend Analysis:**
• 整体趋势 / Overall Trend: {trends['trend']}
• 平均注册率 / Average Rate: {trends['average_rate']:.1f}%
• 最高单日 / Highest Day: {max(recent_rates):.1f}%
• 最低单日 / Lowest Day: {min(recent_rates):.1f}%
• 波动范围 / Range: {max(recent_rates) - min(recent_rates):.1f}%

**💡 趋势说明 / Trend Description:**
"""

    if trends['trend'] == 'improving':
        trend_text += "📈 表现呈上升趋势，继续保持！\nPerformance is improving, keep it up!"
    elif trends['trend'] == 'declining':
        trend_text += "📉 表现呈下降趋势，需要关注和改进。\nPerformance is declining, needs attention and improvement."
    else:
        trend_text += "📊 表现相对稳定，可寻求突破机会。\nPerformance is stable, look for breakthrough opportunities."

    await telegram_handler.send_message(chat_id, trend_text.strip(), parse_mode='markdown')


# Command mapping for performance module
PERFORMANCE_COMMANDS = {
    'performance': handle_performance_command
}

PERFORMANCE_CALLBACKS = {
    'list_performance_members': handle_performance_callbacks,
    'cancel_performance': lambda task_data: telegram_handler.send_message(
        task_data['chat_id'], "操作已取消。 / Operation cancelled."
    )
}

# Add dynamic callbacks for member-specific actions
# These would be registered dynamically based on available members
def register_member_callbacks():
    """Register member-specific callbacks dynamically."""
    # This would be called when the module is loaded
    pass

PERFORMANCE_CONVERSATIONS = {}
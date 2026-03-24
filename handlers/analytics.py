"""Analytics charts handlers."""
import logging
import os
from typing import Dict, Any, List
from datetime import datetime, date, timedelta

from telethon import Button

from database import database
from telegram_handler import telegram_handler
from engines.chart_engine import chart_engine

logger = logging.getLogger(__name__)


async def handle_analytics_command(task_data: Dict[str, Any]):
    """Handle /analytics command - show analytics menu."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check if user is registered
    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        await telegram_handler.send_message(
            chat_id,
            "❌ 请先使用 /start 注册。\nPlease register using /start first."
        )
        return

    analytics_text = f"""
📈 **数据分析 / Analytics Dashboard**

📅 **日期 / Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

欢迎来到数据分析中心！选择您需要的图表类型：
Welcome to the Analytics Center! Select the chart type you need:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📊 日报图表 / Daily Charts', 'callback_data': 'analytics_daily_charts'},
            {'text': '📈 趋势分析 / Trend Analysis', 'callback_data': 'analytics_trends'}
        ],
        [
            {'text': '🏆 排行榜 / Leaderboard', 'callback_data': 'analytics_leaderboard'},
            {'text': '🔥 转化漏斗 / Conversion Funnel', 'callback_data': 'analytics_daily_funnel'}
        ],
        [
            {'text': '📉 对比分析 / Comparison', 'callback_data': 'analytics_frontdesk_comparison'},
            {'text': '🌡️ 热力图 / Heatmap', 'callback_data': 'analytics_heatmap'}
        ],
        [
            {'text': '🎯 个人表现 / Personal Performance', 'callback_data': 'analytics_personal'},
            {'text': '👥 团队分析 / Team Analysis', 'callback_data': 'analytics_team'}
        ],
        [
            {'text': '💰 财务分析 / Financial Analysis', 'callback_data': 'analytics_financial'},
            {'text': '📋 自定义图表 / Custom Charts', 'callback_data': 'analytics_custom'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        analytics_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_daily_funnel_chart(task_data: Dict[str, Any]):
    """Generate and send daily funnel chart."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    try:
        # Generate chart
        chart_path = await chart_engine.daily_funnel_chart()

        caption = f"""
🔥 **今日转化漏斗 / Today's Conversion Funnel**

📅 **日期 / Date:** {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%m月%d日')})

转化漏斗显示了从粉丝到最终成单的完整流程。
The conversion funnel shows the complete process from fans to final orders.

💡 **提示 / Tips:**
• 关注转化率较低的环节
• Focus on stages with lower conversion rates
        """.strip()

        # Create navigation keyboard
        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '📊 对比图表 / Comparison Chart', 'callback_data': 'analytics_frontdesk_comparison'},
                {'text': '📈 趋势分析 / Trend Analysis', 'callback_data': 'analytics_trends'}
            ],
            [
                {'text': '🌡️ 热力图 / Heatmap', 'callback_data': 'analytics_heatmap'},
                {'text': '💰 财务瀑布 / Financial Waterfall', 'callback_data': 'analytics_waterfall'}
            ],
            [
                {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
                {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
            ]
        ])

        await telegram_handler.send_photo(chat_id, chart_path, caption=caption, reply_markup=keyboard)

        # Clean up temporary file
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating daily funnel chart: {e}")
        await telegram_handler.send_message(
            chat_id,
            f"❌ 生成图表时出错：{str(e)}\nError generating chart: {str(e)}"
        )


async def handle_frontdesk_comparison_chart(task_data: Dict[str, Any]):
    """Generate and send frontdesk comparison chart."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    try:
        # Generate chart
        chart_path = await chart_engine.frontdesk_comparison_bar()

        caption = f"""
📉 **前台对比分析 / Frontdesk Comparison Analysis**

📅 **日期 / Date:** {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%m月%d日')})

横向条形图对比所有前台今日表现。
Horizontal bar chart comparing all frontdesk performance today.

💡 **分析重点 / Key Analysis:**
• 新客户获取能力对比
• 注册转化率对比
• 培训完成率对比
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '🔥 转化漏斗 / Conversion Funnel', 'callback_data': 'analytics_daily_funnel'},
                {'text': '📈 个人趋势 / Individual Trends', 'callback_data': 'analytics_personal_trend'}
            ],
            [
                {'text': '🎯 转化仪表 / Conversion Gauge', 'callback_data': 'analytics_conversion_gauge'},
                {'text': '🌡️ 热力图 / Heatmap', 'callback_data': 'analytics_heatmap'}
            ],
            [
                {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
                {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
            ]
        ])

        await telegram_handler.send_photo(chat_id, chart_path, caption=caption, reply_markup=keyboard)

        # Clean up
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating frontdesk comparison chart: {e}")
        await telegram_handler.send_message(
            chat_id,
            f"❌ 生成图表时出错：{str(e)}\nError generating chart: {str(e)}"
        )


async def handle_heatmap_chart(task_data: Dict[str, Any]):
    """Generate and send performance heatmap."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    try:
        # Generate chart
        chart_path = await chart_engine.performance_heatmap()

        caption = f"""
🌡️ **表现热力图 / Performance Heatmap**

📅 **时间范围 / Time Range:** 过去7天 / Last 7 days

热力图显示所有前台在过去7天的注册数表现。
Heatmap shows registration performance for all frontdesk over the last 7 days.

🎨 **颜色说明 / Color Legend:**
• 深红色 = 高表现 / Dark red = High performance
• 浅黄色 = 低表现 / Light yellow = Low performance

📊 **使用建议 / Usage Tips:**
• 识别表现趋势和模式
• 发现需要支持的前台
• 制定有针对性的培训计划
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '📊 对比分析 / Comparison Chart', 'callback_data': 'analytics_frontdesk_comparison'},
                {'text': '📈 趋势线图 / Trend Line Chart', 'callback_data': 'analytics_trends'}
            ],
            [
                {'text': '🎯 个人仪表 / Personal Gauge', 'callback_data': 'analytics_conversion_gauge'},
                {'text': '👥 团队饼图 / Team Pie Chart', 'callback_data': 'analytics_team_pie'}
            ],
            [
                {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
                {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
            ]
        ])

        await telegram_handler.send_photo(chat_id, chart_path, caption=caption, reply_markup=keyboard)

        # Clean up
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating heatmap chart: {e}")
        await telegram_handler.send_message(
            chat_id,
            f"❌ 生成图表时出错：{str(e)}\nError generating chart: {str(e)}"
        )


async def handle_personal_trend_chart(task_data: Dict[str, Any]):
    """Generate personal trend chart for the user or allow selection."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        await telegram_handler.send_message(
            chat_id,
            "❌ 请先使用 /start 注册。\nPlease register using /start first."
        )
        return

    # If user is frontdesk, show their trend. Otherwise, ask for selection.
    if member.role == 'frontdesk':
        frontdesk_name = member.frontdesk_name or member.first_name
        await generate_trend_chart_for_frontdesk(chat_id, frontdesk_name)
    else:
        await show_frontdesk_selection_for_trends(chat_id)


async def generate_trend_chart_for_frontdesk(chat_id: int, frontdesk_name: str):
    """Generate trend chart for specific frontdesk."""
    try:
        # Generate chart
        chart_path = await chart_engine.weekly_trend_line(frontdesk_name)

        caption = f"""
📈 **{frontdesk_name} - 7天趋势分析 / 7-Day Trend Analysis**

📅 **时间范围 / Time Range:** 过去7天 / Last 7 days

趋势线图显示该前台过去7天的表现变化。
Trend line chart shows performance changes for this frontdesk over the last 7 days.

💡 **分析要点 / Analysis Points:**
• 🔵 新客户获取趋势
• 🔴 注册转化趋势
• 🟠 培训完成趋势

📊 **改进建议 / Improvement Tips:**
• 分析下降趋势的原因
• 保持上升趋势的策略
• 关注数据波动规律
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '🎯 转化仪表 / Conversion Gauge', 'callback_data': f'analytics_gauge_{frontdesk_name}'},
                {'text': '📊 对比分析 / Comparison Chart', 'callback_data': 'analytics_frontdesk_comparison'}
            ],
            [
                {'text': '📈 其他前台 / Other Frontdesk', 'callback_data': 'analytics_select_frontdesk'},
                {'text': '🌡️ 热力图 / Heatmap', 'callback_data': 'analytics_heatmap'}
            ],
            [
                {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
                {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
            ]
        ])

        await telegram_handler.send_photo(chat_id, chart_path, caption=caption, reply_markup=keyboard)

        # Clean up
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating trend chart for {frontdesk_name}: {e}")
        await telegram_handler.send_message(
            chat_id,
            f"❌ 生成{frontdesk_name}趋势图时出错：{str(e)}\nError generating trend chart for {frontdesk_name}: {str(e)}"
        )


async def show_frontdesk_selection_for_trends(chat_id: int):
    """Show frontdesk selection menu for trend analysis."""
    # Get active frontdesks
    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT frontdesk_name FROM team_members
            WHERE role = 'frontdesk' AND is_active = TRUE
            ORDER BY frontdesk_name
        """)
        frontdesks = [row[0] for row in await cursor.fetchall()]

    selection_text = """
📈 **选择前台查看趋势 / Select Frontdesk for Trends**

选择要查看7天趋势的前台：
Select the frontdesk to view 7-day trends:
    """.strip()

    # Create keyboard with frontdesk options (max 2 per row)
    keyboard_rows = []
    for i in range(0, len(frontdesks), 2):
        row = []
        for j in range(2):
            if i + j < len(frontdesks):
                frontdesk = frontdesks[i + j]
                row.append({'text': f'📈 {frontdesk}', 'callback_data': f'analytics_trend_{frontdesk}'})
        keyboard_rows.append(row)

    # Add navigation row
    keyboard_rows.append([
        {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
        {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
    ])

    keyboard = telegram_handler.create_inline_keyboard(keyboard_rows)

    await telegram_handler.send_message(
        chat_id,
        selection_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_conversion_gauge_chart(task_data: Dict[str, Any]):
    """Generate conversion gauge for user or allow selection."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data.get('callback_data', '')

    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        await telegram_handler.send_message(
            chat_id,
            "❌ 请先使用 /start 注册。\nPlease register using /start first."
        )
        return

    # Extract frontdesk name from callback if available
    if callback_data.startswith('analytics_gauge_'):
        frontdesk_name = callback_data.replace('analytics_gauge_', '')
        await generate_gauge_chart_for_frontdesk(chat_id, frontdesk_name)
    elif member.role == 'frontdesk':
        frontdesk_name = member.frontdesk_name or member.first_name
        await generate_gauge_chart_for_frontdesk(chat_id, frontdesk_name)
    else:
        await show_frontdesk_selection_for_gauge(chat_id)


async def generate_gauge_chart_for_frontdesk(chat_id: int, frontdesk_name: str):
    """Generate gauge chart for specific frontdesk."""
    try:
        # Generate chart
        chart_path = await chart_engine.conversion_gauge(frontdesk_name)

        caption = f"""
🎯 **{frontdesk_name} - 转化率仪表 / Conversion Rate Gauge**

📅 **日期 / Date:** {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%m月%d日')})

仪表盘显示今日的转化率表现，范围从0%到100%。
Gauge shows today's conversion rate performance, ranging from 0% to 100%.

🎨 **仪表盘说明 / Gauge Legend:**
• 🔴 红色 (0-20%): 需要改进 / Needs improvement
• 🟠 橙色 (20-40%): 一般表现 / Fair performance
• 🟡 黄色 (40-60%): 中等表现 / Average performance
• 🟢 浅绿 (60-80%): 良好表现 / Good performance
• 🟢 深绿 (80-100%): 优秀表现 / Excellent performance

💡 **改进建议 / Improvement Tips:**
• 低于30%需要重点关注沟通技巧
• 30-60%可以优化话术和跟进策略
• 60%以上保持现有策略并总结经验
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '📈 趋势分析 / Trend Analysis', 'callback_data': f'analytics_trend_{frontdesk_name}'},
                {'text': '📊 对比分析 / Comparison Chart', 'callback_data': 'analytics_frontdesk_comparison'}
            ],
            [
                {'text': '🎯 其他前台 / Other Frontdesk', 'callback_data': 'analytics_conversion_gauge'},
                {'text': '🌡️ 热力图 / Heatmap', 'callback_data': 'analytics_heatmap'}
            ],
            [
                {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
                {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
            ]
        ])

        await telegram_handler.send_photo(chat_id, chart_path, caption=caption, reply_markup=keyboard)

        # Clean up
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating gauge chart for {frontdesk_name}: {e}")
        await telegram_handler.send_message(
            chat_id,
            f"❌ 生成{frontdesk_name}转化仪表时出错：{str(e)}\nError generating gauge chart for {frontdesk_name}: {str(e)}"
        )


async def show_frontdesk_selection_for_gauge(chat_id: int):
    """Show frontdesk selection menu for gauge analysis."""
    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT frontdesk_name FROM team_members
            WHERE role = 'frontdesk' AND is_active = TRUE
            ORDER BY frontdesk_name
        """)
        frontdesks = [row[0] for row in await cursor.fetchall()]

    selection_text = """
🎯 **选择前台查看转化仪表 / Select Frontdesk for Conversion Gauge**

选择要查看转化率仪表的前台：
Select the frontdesk to view conversion rate gauge:
    """.strip()

    keyboard_rows = []
    for i in range(0, len(frontdesks), 2):
        row = []
        for j in range(2):
            if i + j < len(frontdesks):
                frontdesk = frontdesks[i + j]
                row.append({'text': f'🎯 {frontdesk}', 'callback_data': f'analytics_gauge_{frontdesk}'})
        keyboard_rows.append(row)

    keyboard_rows.append([
        {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
        {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
    ])

    keyboard = telegram_handler.create_inline_keyboard(keyboard_rows)

    await telegram_handler.send_message(
        chat_id,
        selection_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_team_pie_chart(task_data: Dict[str, Any]):
    """Show team selection for pie chart analysis."""
    chat_id = task_data['chat_id']

    teams_text = """
👥 **团队饼图分析 / Team Pie Chart Analysis**

选择要分析的团队：
Select the team to analyze:
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '💰 发财小组', 'callback_data': 'analytics_pie_发财小组'},
            {'text': '💎 金鑫小组', 'callback_data': 'analytics_pie_金鑫小组'}
        ],
        [
            {'text': '☀️ 夏天小组', 'callback_data': 'analytics_pie_夏天小组'},
            {'text': '📊 全部团队对比', 'callback_data': 'analytics_all_teams_comparison'}
        ],
        [
            {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        teams_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_team_pie_chart(chat_id: int, team_name: str):
    """Generate pie chart for specific team."""
    try:
        # Generate chart
        chart_path = await chart_engine.team_pie_chart(team_name)

        caption = f"""
👥 **{team_name} 团队构成 / {team_name} Team Composition**

📅 **日期 / Date:** {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%m月%d日')})

饼图显示团队成员今日注册数的贡献比例。
Pie chart shows the contribution ratio of team members' registrations today.

📊 **分析要点 / Analysis Points:**
• 团队成员贡献度对比
• 识别表现突出的成员
• 发现需要支持的成员
• 团队协作效果评估

💡 **管理建议 / Management Tips:**
• 表扬优秀表现者
• 为较弱成员提供指导
• 促进成员间经验分享
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '📈 团队趋势 / Team Trends', 'callback_data': f'analytics_team_trend_{team_name}'},
                {'text': '👥 其他团队 / Other Teams', 'callback_data': 'analytics_team_pie'}
            ],
            [
                {'text': '📊 全部对比 / All Teams Comparison', 'callback_data': 'analytics_all_teams_comparison'},
                {'text': '🌡️ 热力图 / Heatmap', 'callback_data': 'analytics_heatmap'}
            ],
            [
                {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
                {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
            ]
        ])

        await telegram_handler.send_photo(chat_id, chart_path, caption=caption, reply_markup=keyboard)

        # Clean up
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating team pie chart for {team_name}: {e}")
        await telegram_handler.send_message(
            chat_id,
            f"❌ 生成{team_name}团队图表时出错：{str(e)}\nError generating team pie chart for {team_name}: {str(e)}"
        )


async def handle_financial_waterfall_chart(task_data: Dict[str, Any]):
    """Generate and send financial waterfall chart."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check permissions for financial data
    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['manager', 'admin']:
        await telegram_handler.send_message(
            chat_id,
            "❌ 财务数据仅限管理员和经理查看。\nFinancial data is only available for managers and admins."
        )
        return

    try:
        # Generate chart
        chart_path = await chart_engine.financial_waterfall()

        caption = f"""
💰 **财务瀑布图 / Financial Waterfall Chart**

📅 **日期 / Date:** {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%m月%d日')})

瀑布图显示今日财务数据的变化流程。
Waterfall chart shows the flow of today's financial data changes.

📊 **图表说明 / Chart Legend:**
• 🔵 蓝色柱 = 起始和结束数值
• 🟢 绿色柱 = 正增长项目
• 🔴 红色柱 = 负增长项目

💡 **财务分析要点 / Financial Analysis Points:**
• 监控资金流向和变化趋势
• 识别主要收入和支出来源
• 评估财务健康状况

⚠️ **注意 / Note:**
此为示例数据，实际财务数据需要连接财务系统。
This is sample data. Real financial data requires connection to financial system.
        """.strip()

        keyboard = telegram_handler.create_inline_keyboard([
            [
                {'text': '📊 收支对比 / Income vs Expense', 'callback_data': 'analytics_income_expense'},
                {'text': '📈 财务趋势 / Financial Trends', 'callback_data': 'analytics_financial_trends'}
            ],
            [
                {'text': '💎 盈利分析 / Profit Analysis', 'callback_data': 'analytics_profit_analysis'},
                {'text': '📋 财务报表 / Financial Report', 'callback_data': 'analytics_financial_report'}
            ],
            [
                {'text': '📈 返回分析菜单 / Back to Analytics', 'callback_data': 'analytics_main'},
                {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
            ]
        ])

        await telegram_handler.send_photo(chat_id, chart_path, caption=caption, reply_markup=keyboard)

        # Clean up
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating financial waterfall chart: {e}")
        await telegram_handler.send_message(
            chat_id,
            f"❌ 生成财务瀑布图时出错：{str(e)}\nError generating financial waterfall chart: {str(e)}"
        )


async def handle_analytics_callbacks(task_data: Dict[str, Any]):
    """Handle analytics-related callback queries."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data == 'analytics_main':
        # Return to analytics menu
        await handle_analytics_command(task_data)

    elif callback_data == 'analytics_daily_funnel':
        await handle_daily_funnel_chart(task_data)

    elif callback_data == 'analytics_frontdesk_comparison':
        await handle_frontdesk_comparison_chart(task_data)

    elif callback_data == 'analytics_heatmap':
        await handle_heatmap_chart(task_data)

    elif callback_data == 'analytics_trends' or callback_data == 'analytics_personal_trend':
        await handle_personal_trend_chart(task_data)

    elif callback_data == 'analytics_conversion_gauge':
        await handle_conversion_gauge_chart(task_data)

    elif callback_data == 'analytics_team_pie':
        await handle_team_pie_chart(task_data)

    elif callback_data == 'analytics_waterfall':
        await handle_financial_waterfall_chart(task_data)

    elif callback_data.startswith('analytics_trend_'):
        frontdesk_name = callback_data.replace('analytics_trend_', '')
        await generate_trend_chart_for_frontdesk(chat_id, frontdesk_name)

    elif callback_data.startswith('analytics_gauge_'):
        await handle_conversion_gauge_chart(task_data)

    elif callback_data.startswith('analytics_pie_'):
        team_name = callback_data.replace('analytics_pie_', '')
        await generate_team_pie_chart(chat_id, team_name)


# Command and callback mappings
ANALYTICS_COMMANDS = {
    'analytics': handle_analytics_command,
    'charts': handle_analytics_command,
}

ANALYTICS_CALLBACKS = {
    'analytics_main': handle_analytics_callbacks,
    'analytics_daily_charts': handle_analytics_callbacks,
    'analytics_daily_funnel': handle_analytics_callbacks,
    'analytics_frontdesk_comparison': handle_analytics_callbacks,
    'analytics_heatmap': handle_analytics_callbacks,
    'analytics_trends': handle_analytics_callbacks,
    'analytics_personal_trend': handle_analytics_callbacks,
    'analytics_conversion_gauge': handle_analytics_callbacks,
    'analytics_team_pie': handle_analytics_callbacks,
    'analytics_waterfall': handle_analytics_callbacks,
    'analytics_personal': handle_analytics_callbacks,
    'analytics_team': handle_analytics_callbacks,
    'analytics_financial': handle_analytics_callbacks,
    'analytics_custom': handle_analytics_callbacks,
}

# Dynamic callbacks for specific frontdesks and teams
# These will be handled in handle_analytics_callbacks based on callback_data prefix

ANALYTICS_CONVERSATIONS = {}
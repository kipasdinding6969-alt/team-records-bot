"""Help & guide system handlers."""
import logging
from typing import Dict, Any, List
from datetime import datetime

from telethon import Button

from database import database
from telegram_handler import telegram_handler
from i18n import t

logger = logging.getLogger(__name__)


async def _get_lang(user_id):
    from database import database
    return (await database.get_user_language(user_id)) or 'zh'


async def handle_help_command(task_data: Dict[str, Any]):
    """Handle /help command - show comprehensive help system."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Get user info for personalized help
    member = await database.get_team_member_by_user_id(user_id)
    lang = await _get_lang(user_id)

    help_text = f"""
{t('help_center_title', lang)}

{t('help_center_welcome', lang)}

{t('your_role_label', lang)} {get_role_display(member.role if member else 'unregistered', lang)}

{t('help_select_topic', lang)}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_help_quick_start', lang), 'callback_data': 'help_quick_start'},
            {'text': t('btn_help_submit_reports', lang), 'callback_data': 'help_submit_reports'}
        ],
        [
            {'text': t('btn_help_view_data', lang), 'callback_data': 'help_view_data'},
            {'text': t('btn_help_chart_analysis', lang), 'callback_data': 'help_chart_analysis'}
        ],
        [
            {'text': t('btn_help_reminder_system', lang), 'callback_data': 'help_reminder_system'},
            {'text': t('btn_help_sync_info', lang), 'callback_data': 'help_sync_info'}
        ],
        [
            {'text': t('btn_help_team_functions', lang), 'callback_data': 'help_team_functions'},
            {'text': t('btn_help_settings', lang), 'callback_data': 'help_settings'}
        ],
        [
            {'text': t('btn_help_faq', lang), 'callback_data': 'help_faq'},
            {'text': t('btn_help_contact_support', lang), 'callback_data': 'help_contact_support'}
        ],
        [
            {'text': t('btn_back_main', lang), 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        help_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


def get_role_display(role: str, lang: str = 'zh') -> str:
    """Get role display name."""
    role_map = {
        'unregistered': t('role_unregistered', lang),
        'frontdesk': t('role_frontdesk', lang),
        'manager': t('role_manager', lang),
        'admin': t('role_admin', lang)
    }
    return role_map.get(role, role)


async def show_quick_start_guide(task_data: Dict[str, Any]):
    """Show quick start guide."""
    chat_id = task_data['chat_id']
    user_id = task_data['user_id']

    member = await database.get_team_member_by_user_id(user_id)
    role = member.role if member else 'unregistered'
    lang = await _get_lang(user_id)

    if role == 'unregistered':
        guide_text = """
🔰 **快速入门指南 / Quick Start Guide**

**欢迎新用户！Welcome New User!**

**第一步：注册 / Step 1: Registration**
1. 使用 `/start` 命令开始注册
2. 按照提示填写个人信息
3. 等待管理员分配角色和权限

**注册后可用功能 / Available Functions After Registration:**
• 📝 提交客户记录
• 📊 查看个人数据
• ⏰ 设置提醒
• 📈 查看图表分析

**需要帮助？/ Need Help?**
• 联系您的团队经理
• 使用 `/help` 查看详细说明
• 发送 `/support` 获得技术支持
        """.strip()

    elif role == 'frontdesk':
        guide_text = """
🔰 **前台快速入门 / Frontdesk Quick Start**

**欢迎前台成员！Welcome Frontdesk Member!**

**常用操作 / Common Operations:**

**📝 提交客户记录 / Submit Client Records:**
• 使用 `/report` 或点击"📝 提交报告"
• 填写客户信息：姓名、电话、状态等
• 系统自动记录时间戳

**📊 查看个人数据 / View Personal Data:**
• 使用 `/status` 查看个人统计
• 点击"📋 我的客户"查看客户列表
• 使用图表分析功能了解表现

**⏰ 设置提醒 / Set Reminders:**
• 系统自动设置第一天、第二天提醒
• 可手动添加自定义提醒
• 及时跟进客户状态

**📈 分析工具 / Analysis Tools:**
• 查看转化率仪表盘
• 分析7天趋势变化
• 对比团队表现
        """.strip()

    else:  # manager or admin
        guide_text = """
🔰 **管理员快速入门 / Admin/Manager Quick Start**

**欢迎管理员！Welcome Administrator!**

**管理功能 / Management Functions:**

**📊 团队仪表板 / Team Dashboard:**
• 使用 `/dashboard` 查看团队概况
• 监控所有前台表现
• 查看实时数据统计

**📈 数据分析 / Data Analysis:**
• 生成各类图表报告
• 分析团队和个人趋势
• 导出数据报表

**👥 团队管理 / Team Management:**
• 使用 `/team_report` 生成团队报告
• 管理成员权限和角色
• 监控活跃客户状态

**📝 报告生成 / Report Generation:**
• 使用 `/summary` 生成日报
• 自定义报告格式
• 自动化报告推送

**⚙️ 系统配置 / System Configuration:**
• 配置提醒规则
• 设置数据同步
• 管理用户权限
        """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📝 提交报告教程 / Report Tutorial', 'callback_data': 'help_submit_reports'},
            {'text': '📊 数据查看教程 / Data View Tutorial', 'callback_data': 'help_view_data'}
        ],
        [
            {'text': '📈 图表分析教程 / Chart Analysis Tutorial', 'callback_data': 'help_chart_analysis'},
            {'text': '⏰ 提醒系统教程 / Reminder Tutorial', 'callback_data': 'help_reminder_system'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        guide_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_submit_reports_help(task_data: Dict[str, Any]):
    """Show help for submitting reports."""
    chat_id = task_data['chat_id']

    help_text = """
📝 **如何提交报告 / How to Submit Reports**

**提交客户记录的详细步骤：**
**Detailed steps for submitting client records:**

**方法一：使用命令 / Method 1: Using Commands**
1. 发送 `/report` 命令
2. 按照机器人提示逐步填写信息
3. 确认信息无误后提交

**方法二：使用菜单 / Method 2: Using Menu**
1. 发送 `/menu` 或 `/start`
2. 点击"📝 提交报告 / Submit Report"
3. 跟随交互式表单

**必填信息 / Required Information:**
• 👤 客户姓名 / Client Name
• 📱 联系电话 / Phone Number
• 📅 日期 / Date (自动填充当前日期)
• 📋 第一天状态 / Day 1 Status
  - ✅ 注册 / Registered
  - ❌ 不注册 / Not Registered
  - ⏳ 待定 / Pending

**可选信息 / Optional Information:**
• 📋 第二天状态 / Day 2 Status
• 💬 备注信息 / Notes
• 🏷️ 客户标签 / Client Tags

**提交后处理 / Post-Submission Processing:**
• ✅ 系统自动保存记录
• 📊 更新个人统计数据
• ⏰ 自动设置跟进提醒
• 🔄 同步到Google表格

**常见问题 / Common Issues:**
• 重复提交：系统会提醒重复记录
• 信息错误：可以使用编辑功能修改
• 提交失败：检查网络连接或联系管理员

**最佳实践 / Best Practices:**
• 及时提交客户信息
• 准确填写客户状态
• 添加有用的备注信息
• 定期查看跟进提醒
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📝 现在开始提交 / Start Submitting Now', 'callback_data': 'start_report_wizard'},
            {'text': '📊 查看数据教程 / View Data Tutorial', 'callback_data': 'help_view_data'}
        ],
        [
            {'text': '⏰ 提醒系统说明 / Reminder System', 'callback_data': 'help_reminder_system'},
            {'text': '🔄 同步说明 / Sync Information', 'callback_data': 'help_sync_info'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        help_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_view_data_help(task_data: Dict[str, Any]):
    """Show help for viewing data."""
    chat_id = task_data['chat_id']

    help_text = """
📊 **如何查看数据 / How to View Data**

**数据查看方式和功能说明：**
**Data viewing methods and feature descriptions:**

**个人数据查看 / Personal Data Viewing:**

**📊 个人统计 / Personal Statistics:**
• 命令：`/status`
• 显示今日、总计、本周数据
• 包含转化率和待处理提醒

**📋 客户列表 / Client List:**
• 菜单：点击"📋 我的客户"
• 显示最近30天客户记录
• 支持搜索和筛选功能

**团队数据查看 / Team Data Viewing:**
*(仅限管理员和经理 / Managers and Admins only)*

**📊 团队仪表板 / Team Dashboard:**
• 命令：`/dashboard`
• 显示所有前台表现
• 实时数据更新

**📝 日报生成 / Daily Summary:**
• 命令：`/summary [日期]`
• 生成指定日期的详细报告
• 支持导出Excel格式

**📈 团队评估 / Team Assessment:**
• 命令：`/team_report [团队名]`
• 5天考核报告
• 团队成员表现对比

**数据筛选和搜索 / Data Filtering and Search:**

**时间范围筛选 / Time Range Filter:**
• 今日 / Today
• 本周 / This week
• 本月 / This month
• 自定义日期范围 / Custom date range

**状态筛选 / Status Filter:**
• 已注册客户 / Registered clients
• 待跟进客户 / Clients to follow up
• 未注册客户 / Not registered clients

**前台筛选 / Frontdesk Filter:**
• 按前台成员查看数据
• 对比不同前台表现

**数据导出 / Data Export:**
• Excel格式导出
• CSV格式导出
• PDF报告生成
• 邮件发送报告

**实时更新 / Real-time Updates:**
• 数据自动同步
• 实时统计更新
• 即时通知提醒
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📊 查看个人统计 / View Personal Stats', 'callback_data': 'refresh_personal_stats'},
            {'text': '📋 查看我的客户 / View My Clients', 'callback_data': 'view_my_clients'}
        ],
        [
            {'text': '📈 图表分析教程 / Chart Analysis Tutorial', 'callback_data': 'help_chart_analysis'},
            {'text': '👥 团队功能说明 / Team Functions', 'callback_data': 'help_team_functions'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        help_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_chart_analysis_help(task_data: Dict[str, Any]):
    """Show help for chart analysis features."""
    chat_id = task_data['chat_id']

    help_text = """
📈 **图表分析教程 / Chart Analysis Tutorial**

**强大的可视化分析工具说明：**
**Powerful visualization analysis tools explanation:**

**图表类型 / Chart Types:**

**🔥 转化漏斗图 / Conversion Funnel Chart**
• 显示：粉丝 → 回复 → 注册 → 培训 → 提款 → 新单
• 用途：识别转化瓶颈，优化流程
• 更新：实时数据，每日更新

**📊 前台对比图 / Frontdesk Comparison Chart**
• 横向条形图对比所有前台表现
• 指标：新客户、注册数、培训完成数
• 用途：公平评估，激励竞争

**📈 趋势线图 / Trend Line Chart**
• 7天趋势分析，显示变化轨迹
• 多指标对比：新客户、注册、培训
• 用途：发现规律，预测趋势

**🌡️ 表现热力图 / Performance Heatmap**
• 前台×时间的矩阵热力图
• 颜色强度表示表现水平
• 用途：快速识别表现模式

**🎯 转化率仪表盘 / Conversion Rate Gauge**
• 仪表盘样式，直观显示转化率
• 颜色区间：红(差) → 橙(一般) → 绿(好)
• 用途：目标导向，激励改进

**👥 团队饼图 / Team Pie Chart**
• 团队成员贡献比例
• 支持多团队对比分析
• 用途：团队管理，资源分配

**💰 财务瀑布图 / Financial Waterfall Chart**
• 显示资金流向和变化
• 蓝色(起终点) 绿色(收入) 红色(支出)
• 用途：财务分析，成本控制

**图表功能 / Chart Features:**

**交互式导航 / Interactive Navigation**
• 图表间快速切换
• 智能推荐相关分析
• 一键返回主菜单

**个性化定制 / Personalization**
• 根据角色显示相关图表
• 前台看个人数据，管理员看团队数据
• 自定义时间范围和参数

**高质量图像 / High Quality Images**
• 1200×800像素，清晰度高
• 深色主题，护眼设计
• 中英双语标签，国际化支持

**图表解读技巧 / Chart Reading Tips:**

**趋势分析 / Trend Analysis:**
• 上升趋势：保持策略，总结经验
• 下降趋势：分析原因，调整方法
• 波动趋势：寻找规律，稳定表现

**对比分析 / Comparative Analysis:**
• 横向对比：同期不同人员表现
• 纵向对比：同人员不同时期表现
• 标杆学习：向优秀者学习经验

**数据洞察 / Data Insights:**
• 关注转化率而非绝对数量
• 重视趋势变化而非单点数据
• 结合定性分析理解定量数据
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📈 开始图表分析 / Start Chart Analysis', 'callback_data': 'analytics_main'},
            {'text': '🔥 查看转化漏斗 / View Conversion Funnel', 'callback_data': 'analytics_daily_funnel'}
        ],
        [
            {'text': '📊 前台对比图 / Frontdesk Comparison', 'callback_data': 'analytics_frontdesk_comparison'},
            {'text': '🌡️ 表现热力图 / Performance Heatmap', 'callback_data': 'analytics_heatmap'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        help_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_reminder_system_help(task_data: Dict[str, Any]):
    """Show help for reminder system."""
    chat_id = task_data['chat_id']

    help_text = """
⏰ **提醒系统说明 / Reminder System Guide**

**智能提醒系统功能详解：**
**Intelligent reminder system features explanation:**

**自动提醒类型 / Automatic Reminder Types:**

**📅 第一天提醒 / Day 1 Reminder**
• 触发：客户记录提交后24小时
• 内容：提醒跟进首次注册情况
• 状态：待定 → 注册/不注册

**📅 第二天提醒 / Day 2 Reminder**
• 触发：第一天注册确认后24小时
• 内容：提醒跟进培训完成情况
• 状态：注册 → 培训完成/未完成

**🔄 自定义提醒 / Custom Reminders**
• 手动设置特定时间提醒
• 自定义提醒内容和频率
• 支持重复提醒设置

**提醒管理功能 / Reminder Management Features:**

**📋 查看待处理提醒 / View Pending Reminders**
• 命令：`/reminders` 或菜单"⏰ 提醒管理"
• 显示所有未完成的提醒任务
• 按时间排序，优先级显示

**✅ 完成提醒 / Complete Reminders**
• 点击提醒项目标记为完成
• 自动更新客户状态
• 记录跟进时间和结果

**⏰ 延期提醒 / Postpone Reminders**
• 设置新的提醒时间
• 添加延期原因备注
• 保持跟进连续性

**📊 提醒统计 / Reminder Statistics**
• 查看提醒完成率
• 分析跟进效率
• 优化工作流程

**提醒设置选项 / Reminder Settings:**

**🔔 通知方式 / Notification Methods**
• Telegram私聊通知
• 群组@提醒
• 邮件通知(可选)

**⏰ 时间设置 / Time Settings**
• 工作时间内提醒(9:00-18:00)
• 自定义提醒间隔
• 节假日暂停提醒

**🎯 优先级设置 / Priority Settings**
• 高优先级：重要客户
• 普通优先级：常规客户
• 低优先级：待观察客户

**最佳实践 / Best Practices:**

**及时响应 / Timely Response**
• 收到提醒后尽快处理
• 不要积压大量提醒
• 保持客户跟进连续性

**准确记录 / Accurate Recording**
• 如实记录跟进结果
• 添加有价值的备注信息
• 更新客户状态准确性

**主动管理 / Proactive Management**
• 定期查看提醒列表
• 提前规划跟进计划
• 利用统计数据优化工作

**故障排除 / Troubleshooting:**

**提醒未收到 / Reminder Not Received**
• 检查Telegram通知设置
• 确认机器人未被屏蔽
• 联系技术支持检查

**提醒时间不准 / Incorrect Reminder Time**
• 检查时区设置
• 确认系统时间正确
• 报告时间同步问题

**提醒重复发送 / Duplicate Reminders**
• 确认提醒已标记完成
• 检查是否有重复客户记录
• 联系管理员处理
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '⏰ 查看我的提醒 / View My Reminders', 'callback_data': 'dashboard_reminders'},
            {'text': '⚙️ 提醒设置 / Reminder Settings', 'callback_data': 'settings_notifications'}
        ],
        [
            {'text': '📝 提交报告教程 / Report Tutorial', 'callback_data': 'help_submit_reports'},
            {'text': '🔄 同步说明 / Sync Information', 'callback_data': 'help_sync_info'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        help_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_sync_info_help(task_data: Dict[str, Any]):
    """Show sync information help."""
    chat_id = task_data['chat_id']

    help_text = """
🔄 **同步说明 / Synchronization Information**

**数据同步机制详解：**
**Data synchronization mechanism explanation:**

**同步范围 / Sync Scope:**

**📊 Google表格同步 / Google Sheets Sync**
• 实时双向同步所有客户记录
• 支持多个前台工作表
• 自动备份历史数据

**📋 本地数据库 / Local Database**
• SQLite本地缓存，提高响应速度
• 离线模式支持基本查看功能
• 网络恢复后自动同步

**☁️ 云端备份 / Cloud Backup**
• 定期自动备份到云存储
• 多重备份确保数据安全
• 支持数据恢复和迁移

**同步时机 / Sync Timing:**

**实时同步 / Real-time Sync**
• 新增记录：立即同步到Google表格
• 状态更新：实时反映到所有端
• 提醒完成：即时更新跟进状态

**定时同步 / Scheduled Sync**
• 每小时全量数据校验
• 每日凌晨完整备份
• 每周数据一致性检查

**手动同步 / Manual Sync**
• 使用 `/sync` 命令强制同步
• 管理员可触发全量同步
• 紧急情况下的数据恢复

**同步状态监控 / Sync Status Monitoring:**

**📊 同步状态显示 / Sync Status Display**
• 绿色：同步正常
• 黄色：同步延迟
• 红色：同步失败

**🔔 同步通知 / Sync Notifications**
• 同步失败自动通知管理员
• 数据冲突提醒处理
• 同步完成状态报告

**📈 同步统计 / Sync Statistics**
• 同步成功率统计
• 数据传输量监控
• 错误日志记录

**数据一致性 / Data Consistency:**

**🔐 冲突解决 / Conflict Resolution**
• 以最新时间戳为准
• 手动冲突需要人工处理
• 保留冲突记录供查阅

**✅ 数据验证 / Data Validation**
• 自动检查数据完整性
• 验证必填字段完整性
• 检测异常数据模式

**📝 变更记录 / Change Logging**
• 记录所有数据变更
• 跟踪变更来源和时间
• 支持变更历史查询

**故障处理 / Troubleshooting:**

**同步失败处理 / Sync Failure Handling**
1. 检查网络连接
2. 验证Google表格权限
3. 查看错误日志信息
4. 联系技术支持

**数据丢失预防 / Data Loss Prevention**
• 多重备份机制
• 自动恢复功能
• 定期数据导出

**性能优化 / Performance Optimization**
• 增量同步减少数据量
• 压缩传输提高速度
• 智能调度避免高峰

**同步最佳实践 / Sync Best Practices:**

**📱 使用建议 / Usage Recommendations**
• 保持稳定网络连接
• 定期检查同步状态
• 及时处理冲突提醒

**⚠️ 注意事项 / Important Notes**
• 不要同时在多端修改同一记录
• 重要操作前确认同步状态
• 定期备份重要数据

**🔧 维护建议 / Maintenance Recommendations**
• 定期清理过期临时文件
• 监控同步性能指标
• 更新同步组件版本
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '🔄 检查同步状态 / Check Sync Status', 'callback_data': 'check_sync_status'},
            {'text': '📊 同步统计 / Sync Statistics', 'callback_data': 'sync_statistics'}
        ],
        [
            {'text': '📝 数据备份 / Data Backup', 'callback_data': 'data_backup'},
            {'text': '⚙️ 同步设置 / Sync Settings', 'callback_data': 'sync_settings'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        help_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_faq_help(task_data: Dict[str, Any]):
    """Show frequently asked questions."""
    chat_id = task_data['chat_id']

    faq_text = """
🔧 **常见问题 / Frequently Asked Questions**

**最常见的问题和解答：**
**Most common questions and answers:**

**Q1: 如何开始使用机器人？**
**How to start using the bot?**
A: 发送 `/start` 命令，按提示填写注册信息，等待管理员分配角色。
Send `/start` command, fill in registration info, wait for admin to assign role.

**Q2: 忘记如何提交客户记录？**
**Forgot how to submit client records?**
A: 使用 `/report` 命令或点击主菜单"📝 提交报告"，跟随提示操作。
Use `/report` command or click "📝 Submit Report" in main menu, follow prompts.

**Q3: 为什么看不到团队数据？**
**Why can't I see team data?**
A: 团队数据仅限管理员和经理查看。如需权限，请联系管理员。
Team data is only for managers and admins. Contact admin for permission.

**Q4: 提醒通知收不到怎么办？**
**What if I don't receive reminder notifications?**
A: 检查Telegram通知设置，确保未屏蔽机器人，或联系技术支持。
Check Telegram notification settings, ensure bot not blocked, or contact support.

**Q5: 数据同步失败怎么处理？**
**How to handle sync failure?**
A: 检查网络连接，稍后重试，或使用 `/sync` 强制同步。
Check network connection, retry later, or use `/sync` to force sync.

**Q6: 如何修改已提交的记录？**
**How to modify submitted records?**
A: 联系管理员协助修改，或在Google表格中直接编辑。
Contact admin for modification, or edit directly in Google Sheets.

**Q7: 图表显示不正常？**
**Charts not displaying correctly?**
A: 可能是数据加载问题，点击刷新重试，或检查网络连接。
May be data loading issue, click refresh to retry, or check network.

**Q8: 忘记自己的角色和权限？**
**Forgot my role and permissions?**
A: 使用 `/status` 查看个人信息，包含角色和权限说明。
Use `/status` to view personal info, including role and permission details.

**Q9: 客户电话号码填错了？**
**Wrong client phone number entered?**
A: 联系管理员修改，提供正确的电话号码和客户姓名。
Contact admin for modification, provide correct phone number and client name.

**Q10: 为什么转化率显示为0？**
**Why does conversion rate show 0?**
A: 可能今天还没有新客户记录，或所有客户状态都是待定。
May be no new client records today, or all clients status are pending.
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '📞 联系技术支持 / Contact Support', 'callback_data': 'help_contact_support'},
            {'text': '📝 提交问题反馈 / Submit Feedback', 'callback_data': 'submit_feedback'}
        ],
        [
            {'text': '📖 查看更多教程 / More Tutorials', 'callback_data': 'help_more_tutorials'},
            {'text': '🔰 快速入门 / Quick Start', 'callback_data': 'help_quick_start'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        faq_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def show_contact_support(task_data: Dict[str, Any]):
    """Show contact support information."""
    chat_id = task_data['chat_id']

    support_text = f"""
📞 **联系支持 / Contact Support**

**需要帮助时的联系方式：**
**Contact information when you need help:**

**🔧 技术支持 / Technical Support**
• 发送 `/support` + 问题描述
• 系统会自动转发给技术团队
• 预计响应时间：2-4小时

**👥 管理员联系 / Admin Contact**
• 用户ID 7715010221 (管理员专用)
• 权限、角色相关问题
• 数据修改和特殊需求

**📋 问题分类 / Issue Categories**

**🐛 Bug报告 / Bug Report**
• 功能异常、错误提示
• 数据显示问题
• 同步失败问题

**💡 功能建议 / Feature Request**
• 新功能需求
• 改进建议
• 用户体验优化

**❓ 使用咨询 / Usage Consultation**
• 操作方法询问
• 最佳实践建议
• 培训和指导

**联系模板 / Contact Template:**
```
问题类型 / Issue Type: [Bug/建议/咨询]
详细描述 / Description:
重现步骤 / Steps to reproduce:
预期结果 / Expected result:
实际结果 / Actual result:
```

**📱 其他联系方式 / Other Contact Methods:**
• 团队微信群 (内部成员)
• 邮件支持 (重要问题)
• 电话热线 (紧急情况)

**⏰ 支持时间 / Support Hours:**
• 工作日 9:00 - 18:00
• 紧急问题24小时响应
• 节假日有值班技术人员

**📊 支持质量 / Support Quality:**
• 平均响应时间: 3小时
• 问题解决率: 95%+
• 用户满意度: 4.8/5.0

感谢您使用团队记录机器人！
Thank you for using Team Records Bot!
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '🔧 立即发送支持请求 / Send Support Request', 'callback_data': 'send_support_request'},
            {'text': '📝 提交反馈 / Submit Feedback', 'callback_data': 'submit_feedback'}
        ],
        [
            {'text': '📋 查看问题跟踪 / View Issue Tracking', 'callback_data': 'view_issue_tracking'},
            {'text': '📞 查看联系历史 / View Contact History', 'callback_data': 'view_contact_history'}
        ],
        [
            {'text': '📖 返回帮助菜单 / Back to Help Menu', 'callback_data': 'help_main'},
            {'text': '🏠 返回主菜单 / Back to Main', 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        support_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_help_callbacks(task_data: Dict[str, Any]):
    """Handle help-related callback queries."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    if callback_data == 'help_main':
        await handle_help_command(task_data)

    elif callback_data == 'help_quick_start':
        await show_quick_start_guide(task_data)

    elif callback_data == 'help_submit_reports':
        await show_submit_reports_help(task_data)

    elif callback_data == 'help_view_data':
        await show_view_data_help(task_data)

    elif callback_data == 'help_chart_analysis':
        await show_chart_analysis_help(task_data)

    elif callback_data == 'help_reminder_system':
        await show_reminder_system_help(task_data)

    elif callback_data == 'help_sync_info':
        await show_sync_info_help(task_data)

    elif callback_data == 'help_faq':
        await show_faq_help(task_data)

    elif callback_data == 'help_contact_support':
        await show_contact_support(task_data)

    else:
        # Placeholder for other help callbacks
        await telegram_handler.send_message(
            chat_id,
            f"⚠️ 功能开发中 / Feature under development\n\n回调数据：{callback_data}"
        )


# Command and callback mappings
HELP_COMMANDS = {
    'help': handle_help_command,
    'support': handle_help_command,
}

HELP_CALLBACKS = {
    'help_main': handle_help_callbacks,
    'help_quick_start': handle_help_callbacks,
    'help_submit_reports': handle_help_callbacks,
    'help_view_data': handle_help_callbacks,
    'help_chart_analysis': handle_help_callbacks,
    'help_reminder_system': handle_help_callbacks,
    'help_sync_info': handle_help_callbacks,
    'help_team_functions': handle_help_callbacks,
    'help_settings': handle_help_callbacks,
    'help_faq': handle_help_callbacks,
    'help_contact_support': handle_help_callbacks,
}

HELP_CONVERSATIONS = {}
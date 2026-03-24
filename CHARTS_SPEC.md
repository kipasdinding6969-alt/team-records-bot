# Visual Charts & Advanced Telegram UI Spec

## Goal
Add professional chart generation, interactive Telegram UI with buttons, and visual reports to the team records bot.

## Requirements

### 1. Chart Generator (engines/chart_engine.py)
Generate PNG chart images using matplotlib (Chinese font support with SimHei/WenQuanYi):

**Charts to implement:**
- `daily_funnel_chart(date)` — Funnel: 粉丝 → 回复 → 注册 → 培训 → 提款 → 新单
- `frontdesk_comparison_bar(date)` — Horizontal bar chart comparing all frontdesk staff
- `weekly_trend_line(frontdesk, days=7)` — Line chart showing 7-day trends
- `team_pie_chart(team_name)` — Pie chart of team composition/performance
- `financial_waterfall(date)` — Waterfall chart showing 刀数 progression
- `performance_heatmap()` — Heatmap of all frontdesk × all metrics
- `conversion_gauge(frontdesk)` — Gauge/meter showing conversion rate

All charts should:
- Use #7f848e slate gray theme (NO purple #c678dd)
- Support Chinese characters in labels
- Be 1200x800px PNG with transparent or dark background
- Have bilingual labels (Chinese primary, English secondary)
- Include date/timestamp watermark

### 2. Interactive Telegram Menus (update handlers)
Create a rich button-based navigation system:

**Main Menu (/menu or /start):**
```
🏠 主菜单 / Main Menu
┌─────────────────────────────┐
│ 📊 今日总览    │ 📈 数据分析  │
│ Today Overview │ Analytics    │
├─────────────────────────────┤
│ 📝 提交报告    │ 👥 团队管理  │
│ Submit Report  │ Team Manage  │
├─────────────────────────────┤
│ ⏰ 提醒管理    │ 💰 财务概览  │
│ Reminders      │ Finance      │
├─────────────────────────────┤
│ 📋 我的客户    │ ⚙️ 设置      │
│ My Clients     │ Settings     │
└─────────────────────────────┘
```

**Analytics submenu:**
- 📊 日报图表 / Daily Charts
- 📈 趋势分析 / Trend Analysis  
- 🏆 排行榜 / Leaderboard
- 🔥 转化漏斗 / Conversion Funnel
- 📉 对比分析 / Comparison

Each sends the corresponding chart as a photo with inline buttons for navigation.

### 3. Help & Guide System
**Help command (/help):**
Rich formatted help with sections:
- 🔰 快速入门 / Quick Start Guide
- 📝 如何提交报告 / How to Submit Reports
- 📊 如何查看数据 / How to View Data
- ⏰ 提醒系统说明 / Reminder System
- 🔄 同步说明 / Sync Info

With inline buttons to navigate between sections.

### 4. Daily Auto-Report
Send a morning summary with charts to the admin (user_id: 7715010221):
- Yesterday's performance chart
- Top performers
- Pending follow-ups
- Today's reminders

### Technical Notes
- Use telethon's `client.send_file()` to send chart images
- Charts saved as temp PNG files, deleted after sending
- Matplotlib backend: 'Agg' (non-interactive)
- Font: try SimHei → WenQuanYi Micro Hei → DejaVu Sans fallback
- Import from engines.gsheet_writer for real data

### File Structure
```
engines/chart_engine.py     — Chart generation
handlers/menu.py            — Main menu & navigation
handlers/analytics.py       — Analytics charts handlers
handlers/help_guide.py      — Help & guide system
```

# Team Records Bot — Full Rebuild Spec (V2)

## Context
Bot at /home/baiwan/team-records-bot — Telethon dual-mode (user + bot client).
Spreadsheet: "欧洲前台客户" (1rkgRG95lxUgeplceekMY3Z_NZIBKxjTKNwLSpw04xgQ)
Already working: dual Telegram clients, DB, Google Sheets read via gspread service account, i18n system.
Bot token: 8212984320:AAEuNCkWJxlLbvKIzewvGZloLANQtVXIBsE
User session: team_records_bot.session (千万富翁 @xmu41)

## CRITICAL: What Needs Fixing

### 1. REAL Sheet Sync (NOT simulated)
Currently `_sync_financial_records`, `_sync_performance_records` are FAKE (return empty, log "simulated").
Make ALL 5 schema types sync properly from the real spreadsheet.

#### Real Sheet Structure (from live data):

**Type 1 — Client Records (11 sheets: 阿YIM, ODDY, 燕燕, MEYMEY, 大杰, 阿勇, 小龙, 小宏, TINO, KUYA, 阿俊)**
- Skip 2 header rows
- Columns: [row_num, DATE, PHONE_REMARK, FRONTDESK, CATEGORY, RECRUITER, Frontdesk_Number, Frontdesk_Username, Client_NUMBER, ACCOUNT_ID, FIRST_DAY, SECOND_DAY, CLIENT_CONDITION, Date2, extra_col]
- Skip rows where DATE contains 'X月X日' (templates)
- Real data example: `['1', '3月1日', '65 IPHONE SE', '阿YIM', '飞机筛选', 'Homer Maier', '46702762359', '@ammeeeelia3589', '46702624812', '763', '不注册', '不注册', '到了提款阶段...']`

**Type 2 — Performance (sheet: "3月-前台数据", gid=794990782)**
- Complex multi-section layout with dates as section headers like "MAO UK 3/1"
- Each section has: 名字(name), 类别(category), 粉量, 开头不回复, 回复率, 卡解释, 拉黑/来玩, 被骗过, 给链接没回复, 完成注册, 审核率, 完成培训, 约时间, 提款
- Multiple rows per person (different categories: UK表单粉, CA表单粉, etc.)
- Parse each dated section separately

**Type 3 — Financial (sheet: "维护数据", gid=1395471353)**
- Headers: 日期, 账号/ID, 群号/ID, 前台, 维护, 前台号, 盘子, 新单$, 承压$, [note], 一刀~八刀, 共入, 前台
- Money values are formatted like `$60`, `$1,800`, `-$70,000`
- Skip template rows (X月XX日)

**Type 4 — Daily Summary (sheet: "3月-小组数据", gid=975912225)**
- Date section headers, then per-frontdesk metrics
- Columns: FRONTDESK, NEW_POWDER, TODAY_REPLY, %, TODAY_REGISTER, %, TODAY_COMPLETED_TRAINING, %, TODAY_WITHDRAW, %, TODAY_NEW_ORDER, %
- Second block: cumulative totals (FRONTDESK, TOTAL_POWDER, etc.)

**Type 5 — Weekly Assessment (sheet: "3月考核-自动", gid=265525062)**
- Same column layout as Type 4 but grouped by team (发财/金鑫/夏天) and 5-day periods

### 2. Stale Client Detection & Auto-Reminders
Scan for clients where:
- `FIRST_DAY` or `SECOND_DAY` is still '不注册' or empty
- Record is older than 3 days
- No status update in 3+ days

Action: Send reminder to the frontdesk person responsible. Create a scheduled task that runs every sync cycle.

### 3. Channel/Supergroup Auto-Posting
- Bot posts summary to a configurable Telegram channel/supergroup every 3 hours during working hours
- Summary includes: total new clients today, registrations, pending, team performance snapshot
- Config via .env: `REPORT_CHANNEL_ID` and `REPORT_INTERVAL_HOURS=3`
- The bot_client should be added to the channel as admin

### 4. Working Hours System
- Default: Europe/Paris timezone, 10:00 AM to 10:00 PM
- Configurable via .env: `TIMEZONE=Europe/Paris`, `WORK_START_HOUR=10`, `WORK_END_HOUR=22`
- Reminders and channel posts ONLY fire during working hours
- If a reminder is due outside working hours, queue it for next working hour start
- Settings panel in bot: `/settings` → Working Hours → edit start/end

### 5. Settings Panel (In-Bot Configuration)
Under `/settings` or Settings button, allow managers to configure:
- Working hours (start/end)
- Reminder frequency (days for stale client alerts)
- Report channel (set channel ID)
- Report interval (how often to post to channel)
- Language (already done)
- Sync interval (how often to sync sheets)

Store settings in a new `bot_settings` table (key-value pairs, scoped to user or global).

### 6. i18n Throughout ALL Handlers
Currently only menu.py uses i18n. ALL other handlers still have dual-language strings:
- handlers/analytics.py
- handlers/dashboard.py
- handlers/finance.py
- handlers/help_guide.py
- handlers/performance.py
- handlers/registration.py
- handlers/reminders.py
- handlers/reporting.py
- engines/reminder_engine.py (reminder messages)
- main.py (unknown command help text)

Convert ALL of them to use `from i18n import t` and single-language output based on user preference.
Add all needed strings to i18n.py.

### 7. Proper Sheet Name Mapping
- Sheet names are month-prefixed (e.g., "3月-前台数据", "3月-小组数据", "3月考核-自动")
- These change every month! The bot must detect the current month's sheets dynamically
- Pattern: look for sheets matching `{month}月-前台数据`, `{month}月-小组数据`, `{month}月考核-自动`
- Or just find sheets by GID (more reliable since GIDs don't change)
- Frontdesk sheets (阿YIM etc.) are permanent names — use those directly

### 8. Code Cleanup
- Remove all "simulated" placeholder code
- Fix the `date is not JSON serializable` bug in main.py perform_maintenance (line ~608)
  Change: `'parameters': {'date': current_time.date()}` → `'parameters': {'date': current_time.strftime('%Y-%m-%d')}`
- Fix `cleanup_old_conversation_states(hours_old=0)` error in shutdown
- Make reminder_engine messages use i18n (no dual language)

## Implementation Order
1. Fix critical bugs (date serialization, conversation cleanup)
2. Add `bot_settings` table + settings CRUD
3. Add working hours system with timezone support
4. Make ALL sheet syncs real (financial, performance, daily summary, weekly assessment)
5. Add stale client detection + auto-reminders
6. Add channel/supergroup auto-posting
7. Convert all handlers to i18n
8. Add settings panel UI
9. Run tests, fix any breaks

## .env Additions Needed
```
REPORT_CHANNEL_ID=       # Set to channel/supergroup ID
REPORT_INTERVAL_HOURS=3
TIMEZONE=Europe/Paris
WORK_START_HOUR=10
WORK_END_HOUR=22
STALE_CLIENT_DAYS=3
```

## Test Requirements
- All existing 112 tests must still pass
- Add tests for: working hours logic, stale client detection, settings CRUD
- Verify sheet sync reads real data (integration test optional)

## DO NOT
- Break the Ralph Loop architecture
- Change the dual-client setup (bot_client for interactive, user client for monitoring)
- Remove any existing functionality
- Create new files unnecessarily (modify existing ones where possible)
- Use dual-language strings anywhere — all text goes through i18n.py

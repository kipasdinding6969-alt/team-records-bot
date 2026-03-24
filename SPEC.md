# Team Records Bot — Full Specification

## Overview
Professional Telegram bot for managing European front desk team operations. Uses Telethon (userbot session with premium account) + aiogram (Bot API) dual-mode. Built on Ralph Loop architecture.

## Telegram Credentials
- api_id: 32326218
- api_hash: 2f44dfd151f291c8a4ec5c405eb51e94
- Phone: +31651036582
- Session file: team_records_bot.session (stored in project root)
- SOCKS5 proxy required: 127.0.0.1:9050 (Tor Docker container)

## Google Spreadsheet
- URL: https://docs.google.com/spreadsheets/d/1rkgRG95lxUgeplceekMY3Z_NZIBKxjTKNwLSpw04xgQ/
- Title: 欧洲前台客户 (European Front Desk Clients)
- 15 sheets total, 5 distinct schema types

## Schema Types

### Type 1: Client Records (11 sheets — one per frontdesk staff member)
GIDs: 550866614, 1230058767, 729968113, 1920827915, 776863779, 1279281320, 1592176479, 2126441720, 217401166, 91396268, 1698881195
Columns:
- ROW_NUM (integer, auto-increment)
- DATE (日期) — entry date, format "X月X日"
- PHONE_REMARK (手机编辑) — device info e.g. "65 IPHONE SE"
- FRONTDESK (前台) — staff name e.g. "阿YIM", "阿俊"
- CATEGORY (类别) — source/filter type e.g. "飞机筛选", "RCS筛选"
- RECRUITER (招聘人员) — recruiter name
- FRONTDESK_NUMBER (前台号) — staff phone number
- FRONTDESK_USERNAME (前台用户名) — TG username e.g. "@ammeeeelia3589"
- CLIENT_NUMBER (客户号) — client phone number
- ACCOUNT_ID (账户ID) — account identifier
- FIRST_DAY (第一天) — day 1 status: "注册"/"不注册"
- SECOND_DAY (第二天) — day 2 status: "注册"/"不注册"
- CLIENT_CONDITION (客户情况) — free text notes about client

Note: Each sheet has TWO side-by-side blocks (rows 1-181 in columns A-M, rows 182+ in columns O-AA) with same schema.

### Type 2: Performance Tracking (MAO UK)
GID: 794990782
Grouped by frontdesk person, with sub-rows per category (UK表单粉, CA表单粉, etc.)
Columns:
- NAME (名字) — frontdesk person
- CATEGORY (类别) — powder source type
- POWDER_COUNT (粉量) — total leads
- NO_INITIAL_REPLY (开头不回复) — leads that didn't reply initially
- REPLY_RATE (回复率) — percentage
- STUCK_EXPLANATION (卡解释)
- BLOCKED_OR_PLAY (拉黑/来玩)
- BEEN_SCAMMED (被骗过)
- SENT_LINK_NO_REPLY (给链接没回复)
- COMPLETED_REGISTER (完成注册)
- REVIEW_RATE (审核率) — percentage
- COMPLETED_TRAINING (完成培训)
- SCHEDULED_TIME (约时间)
- WITHDRAWAL (提款)
- NEW_ORDER (新单)
- CONVERSION_RATE (转换率) — percentage
- NEW_KILL (新杀)
- DEAD_CLIENT (死客)
SUM rows aggregate per person.

### Type 3: Financial Records (杀猪盘)
GID: 1395471353
Columns:
- DATE (日期)
- ACCOUNT_ID (账号/ID) — format "123456 / 123456"
- GROUP_ID (群号/ID) — format "1234 / 12345678910"
- FRONTDESK (前台)
- MAINTENANCE (维护)
- FRONTDESK_NUMBER (前台号)
- PLATFORM (盘子) — e.g. "Iconnect"
- NEW_ORDER_AMOUNT (新单$) — dollar amount
- PRESSURE_AMOUNT (承压$) — dollar amount
- NOTE — e.g. "工资杀6刀", "未回"
- KNIFE_1 through KNIFE_8 (一刀 through 八刀) — progressive amounts
- TOTAL_IN (共入) — total income
- Role columns: 前台, 开单, 小白, 炒群, 客服, 维护, 等等

### Type 4: Daily Summary Report
GID: 975912225
4 side-by-side sections:
Section A — Today's Stats:
  FRONTDESK, NEW_POWDER (当天粉丝), TODAY_REPLY (当天回复), TODAY_REGISTER (当天注册), TODAY_COMPLETED_TRAINING (当天完成培顺), TODAY_WITHDRAW (当天提款), TODAY_NEW_ORDER (当天新单)
Section B — Cumulative Totals:
  FRONTDESK, TOTAL_POWDER (共粉丝), TOTAL_REPLY (共回复), TOTAL_REGISTER (共注册), TOTAL_COMPLETED_TRAINING (共完成培顺), TOTAL_WITHDRAW (共提款), TOTAL_NEW_ORDER (共新单)
Section C — Today's Training Details:
  FRONTDESK, TODAY_TRAINING (当天培顺), TODAY_WITHDRAW (当天提款), TODAY_NOT_WITHDRAW (当天培顺没提款), TODAY_TRAINING_AND_WITHDRAW (当天培顺&提款), TODAY_CONVERSION (当天转换新单)
Section D — Total Training Details:
  Same as C but cumulative totals

### Type 5: Team Weekly Assessment (5天考核)
GID: 265525062
Multi-team comparison for 5-day evaluation periods.
Teams: 发财小组, 金鑫小组, 夏天小组 (and more)
Date range format: "1/6/2025 - 5/6/2025"
Each team has two sub-sections:
  A — Daily Activity: FRONTDESK, NEW_POWDER, TODAY_REPLY, TODAY_REGISTER, TODAY_COMPLETED_TRAINING, TODAY_WITHDRAW, TODAY_NEW_ORDER
  B — Training Conversion: FRONTDESK, TODAY_TRAINING, TODAY_WITHDRAW, TODAY_NOT_WITHDRAW, TODAY_TRAINING_AND_WITHDRAW, TODAY_NEW_ORDER
Rows per day (5 rows per frontdesk = 5天考核), with SUM row at bottom labeled "5天考核"

## Architecture: Ralph Loop

Single monolithic Python process. Core loop:
```
while running:
    refresh_context()     # Load fresh DB state
    task = select_task()  # Check: new messages? pending reminders? report due?
    execute_task(task)    # Process exactly ONE task
    sleep(interval)       # Brief pause
```

### Components:
1. **TelegramHandler** — Telethon client for receiving/sending messages
2. **Database** — SQLite with aiosqlite, mirrors all 5 schema types
3. **ReportEngine** — Generates formatted reports from DB
4. **ReminderEngine** — Tracks day1/day2 follow-ups, sends scheduled reminders
5. **SheetSync** — Bidirectional sync with Google Sheets (read existing + write new)
6. **RalphLoop** — Main loop orchestrator

### Bot Commands (Telegram):
Team members:
- /start — Register as team member
- /report — Submit daily client record (guided wizard)
- /status — View my today's stats
- /clients — List my active clients

Admin/Manager:
- /dashboard — Overview of all frontdesk performance
- /summary — Generate daily summary (Type 4 format)
- /team_report [team_name] — Team assessment (Type 5 format)
- /finance — Financial overview (Type 3)
- /performance [name] — Individual performance (Type 2)
- /remind [name] — Send manual reminder
- /export — Export data to Google Sheets
- /sync — Force sync from/to Google Sheets

### Automated Features:
- Day 1 reminder: Auto-notify frontdesk 24h after client entry if FIRST_DAY not updated
- Day 2 reminder: Auto-notify frontdesk 48h after client entry if SECOND_DAY not updated
- Daily summary: Auto-generate and post Type 4 report at configurable time
- Weekly assessment: Auto-generate Type 5 report at end of 5-day period
- Google Sheets sync: Periodic bidirectional sync

## File Structure:
```
team-records-bot/
├── main.py              # Entry point + Ralph Loop
├── config.py            # Configuration (credentials, settings)
├── database.py          # SQLite schema + CRUD operations
├── models.py            # Data models / dataclasses
├── telegram_handler.py  # Telethon client setup + message routing
├── handlers/
│   ├── __init__.py
│   ├── registration.py  # /start, team member registration
│   ├── reporting.py     # /report wizard, client record submission
│   ├── dashboard.py     # /dashboard, /summary, /team_report
│   ├── finance.py       # /finance commands
│   ├── performance.py   # /performance tracking
│   └── reminders.py     # Reminder management commands
├── engines/
│   ├── __init__.py
│   ├── report_engine.py # Report generation logic
│   ├── reminder_engine.py # Scheduled reminder logic
│   └── sheet_sync.py    # Google Sheets sync engine
├── utils/
│   ├── __init__.py
│   ├── formatting.py    # Message formatting helpers
│   └── validators.py    # Input validation
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # Shared fixtures
│   ├── test_database.py
│   ├── test_models.py
│   ├── test_report_engine.py
│   ├── test_reminder_engine.py
│   ├── test_handlers.py
│   └── test_sheet_sync.py
├── requirements.txt
├── .env.example
├── README.md
└── team_records_bot.session  # Telethon session (generated)
```

## Testing Requirements:
- ALL tests must pass before deployment
- Unit tests for every database operation
- Unit tests for every report generation function
- Unit tests for reminder scheduling logic
- Integration tests for handler flows
- Mock Telegram client for handler tests
- Use pytest + pytest-asyncio
- Target: 100% of core logic tested

## Deployment:
- Systemd service: team-records-bot.service
- Auto-restart on failure
- Logging to /var/log/team-records-bot/ or project ./logs/
- Tor SOCKS5 proxy (Docker container tor-proxy on port 9050)

## Key Design Decisions:
1. SQLite over PostgreSQL — simpler, no external dependency, sufficient for team size
2. Telethon over aiogram — userbot session for full account access + premium features
3. Google Sheets sync — bidirectional to maintain spreadsheet as source of truth
4. Ralph Loop — single process, one task per iteration, fresh context
5. Chinese + English bilingual — all user-facing text supports both

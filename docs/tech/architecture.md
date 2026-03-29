# 架构设计 Architecture

## Ralph Loop 架构

```
                    ┌──────────────────────┐
                    │   Telegram Updates    │
                    │  (commands, messages) │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  telegram_handler.py  │
                    │  - detect chat_type   │
                    │  - group_middleware   │
                    │  - auto-detect team   │
                    │  - create BotTask     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │     Ralph Loop        │
                    │    (main.py)          │
                    │  - 1 task per cycle   │
                    │  - priority queue     │
                    │  - 5s loop interval   │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
    │   handlers_v2  │ │   engines    │ │  maintenance │
    │  quick_actions │ │ policy_engine│ │ health_check │
    │  pipeline      │ │ report_engine│ │ reminder_eng │
    │  management    │ │ rag_engine   │ │ sheet_sync   │
    │  registration  │ │ chart_engine │ │ nocodb_sync  │
    │  group_chat    │ │ obsidian_bra │ │              │
    └────────┬───────┘ └──────┬───────┘ └──────────────┘
             │                │
    ┌────────▼────────────────▼────────┐
    │         database_v2.py           │
    │  SQLite (team_records_v2.db)     │
    └────────┬────────────────┬────────┘
             │                │
    ┌────────▼──────┐ ┌──────▼───────┐
    │   NocoDB      │ │ Google Sheets│
    │  (bidirectional│ │ (read-only)  │
    │   webhook)    │ │              │
    └───────────────┘ └──────────────┘
```

## 文件结构 File Structure

```
team-records-bot-v2/
├── main.py                  # Ralph Loop orchestrator
├── config.py                # Configuration loader
├── team_config.py           # Team structure (from JSON)
├── database.py              # V1 database (legacy)
├── database_v2.py           # V2 database (primary)
├── telegram_handler.py      # Telegram event handling
├── models.py                # V1 models
├── models_v2.py             # V2 models + pipeline
├── i18n.py                  # Internationalization (zh/en)
├── working_hours.py         # Working hours check
├── health_check.py          # System health checks
│
├── handlers/                # V1 handlers (legacy)
├── handlers_v2/             # V2 handlers
│   ├── __init__.py          # Shared utils (get_staff, resolve_team_scope)
│   ├── quick_actions.py     # /add, /u, /num, /info, /req, /note, /remind
│   ├── pipeline.py          # /pipeline, /followup, /today, /search
│   ├── management.py        # /dashboard, /team, /target
│   ├── registration_v2.py   # /start, /bind, /profile, /lang
│   └── group_chat.py        # /linkgroup, group_middleware
│
├── engines/                 # Business logic engines
│   ├── policy_engine.py     # RBAC, limits, validations
│   ├── report_engine.py     # Report generation
│   ├── reminder_engine.py   # Stale client scanning
│   ├── rag_engine.py        # Semantic search
│   ├── chart_engine.py      # Chart generation
│   ├── obsidian_brain.py    # Obsidian vault integration
│   ├── nocodb_writer.py     # NocoDB sync
│   ├── nocodb_webhook.py    # NocoDB webhook receiver
│   └── sheet_sync_v2.py     # Google Sheets sync
│
├── team_structure.json      # Telegram groups + topic IDs
├── nocodb_config.json       # NocoDB table/field mapping
│
├── tests/
│   ├── test_v2.py           # 101 V2 tests
│   ├── test_human_view.py   # 52 human-view tests
│   ├── test_database.py     # Database tests
│   ├── test_engines.py      # Engine tests
│   ├── test_handlers.py     # Handler tests
│   ├── test_models.py       # Model tests
│   └── test_validators.py   # Validator tests
│
└── docs/                    # This documentation (Docsify)
```

## 关键设计决策 Key Design Decisions

1. **Ralph Loop** — 单进程，一次一个任务，新鲜上下文
   Single process, one task per loop, fresh context

2. **Forum Supergroups** — 用话题替代多群，一组一个论坛
   Topics replace multiple groups, one forum per team

3. **SQLite 主库 + NocoDB 镜像** — SQLite 快速可靠，NocoDB 提供 UI
   SQLite primary + NocoDB mirror for UI

4. **chat_id 自动检测** — 不需要手动 linkgroup，team_config 自动匹配
   Auto-detect team from chat_id, no manual linking needed

5. **策略引擎分离** — 所有业务规则在 policy_engine.py，不散布在 handler 中
   All business rules in policy_engine.py, not scattered in handlers

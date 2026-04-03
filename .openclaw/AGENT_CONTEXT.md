# Agent Context — team-records-bot-v2

## MANDATORY PRE-STEPS (before ANY code change)

1. **RAG search first**: Run `./local_rag/search.sh "<your intent>" 8` to find relevant files
2. **Read before writing**: Read every file you plan to modify
3. **Understand the domain**: Read this file's Business Domain section
4. **Run tests after**: `cd /home/baiwan/repos/team-records-bot-v2 && .venv/bin/python -m pytest tests/ -x --tb=short --timeout=30`
5. **TypeScript check**: `cd web_dashboard && npx tsc --noEmit`

## Business Domain (CRITICAL — read this or produce wrong code)

This is a CRM for a 300+ member operation managing European clients through a deposit pipeline.

### Client Pipeline (Day 1 → Kill)
- Day 1 (前台/frontdesk): Contact → Reply → Register → Training → First Withdraw → Own Tasks
- Day 2 (前台 starts, 维护/maintenance takes over at insufficient funds): Training → Commission → INSUFFICIENT FUNDS → [invisible handoff] → Guide first deposit (新单)
- Day 3 (维护): Tasks → INSUFFICIENT FUNDS → Pressure deposit (承压)
- Day 4+ (维护): Salary shown → More deposits → Each round = one 刀 (knife)

### Role System — THESE NAMES MATTER

| Chinese | English Code | Staff Role | Meaning |
|---------|-------------|-----------|---------|
| 前台 | `frontdesk` | First-contact operator | Handles Day 1-2 |
| 维护 | `maintenance` | Takes over after handoff | Guides deposits Day 2+ |
| 炒群 | `group_hype` | Runs group chat activity | Builds confidence |
| 小白 | `newbie` | Actor pretending to be newcomer | In group chats |
| 客服 | `customer_service` | Processes transactions | Isolated from other roles |
| 开单 | `opener_legacy` | DEPRECATED | Was Day 2 deposit guide |
| 全线 | `full_line` | Does both 前台 + 维护 | No handoff |

### CRITICAL NAMING RULES
- Role enum value = `maintenance` (the role itself)
- API endpoints = `/api/maintainer/...` (the person performing the role — acceptable)
- DB column = `maintenance_id` everywhere (FK to staff with role=maintenance)
- DO NOT use `maintainer_id` in DB columns — standardized in Phase 38
- `newbie` = BOTH the staff role AND the actor_role in group interactions (correct, not a bug)
- DO NOT rename `newbie` to `newbie_actor` — that would conflate two separate concepts

### Kill System (杀)
- 注册杀 `register_kill`: Client stopped at registration
- 新单杀 `new_order_kill`: Stopped at first deposit
- 承压杀 `pressure_kill`: Stopped at pressure deposit
- 工资杀 `salary_kill`: Stopped during salary rounds (format: 工资杀6刀 = stopped after 6th knife)

### Key Business Rules
- Handoff is INVISIBLE — client doesn't know they're talking to someone different
- Each role is ISOLATED — cross-role notes (columns T-Z) let operators coordinate
- 小白 and 炒群 are deeply linked — newbie tests understanding, hype reinforces
- 客服 doesn't know about groups or social engineering
- Un-kill possible at 一刀/二刀 only — after that, usually final

### Org Hierarchy
Organization → Branch (主管) → Group (组长) → Sub-group (小组/维护) → Frontdesk (前台, 2-6 per sub-group)

## Tech Stack

- **Backend**: Python 3.12 + FastAPI (`web_dashboard_api.py`, 5600+ lines)
- **Database**: SQLite via aiosqlite (`database_v2.py`, 4300+ lines)
- **Models**: Pydantic + dataclasses (`models_v2.py`)
- **Frontend**: React + TypeScript + Vite (`web_dashboard/src/`)
- **Bot**: python-telegram-bot (`handlers_v2/`)
- **Engines**: Sheet sync, dashboard export, policy engine (`engines/`)
- **Tests**: pytest + pytest-asyncio (`tests/`, 231 passing)

## Coding Rules (enforced)

- No `SELECT *` — explicit columns always
- Parameterized queries only — never f-string SQL
- English only in code (Chinese in comments/docs/i18n is fine)
- Read code before modifying
- Tests before commit
- One feature per session

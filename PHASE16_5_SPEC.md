# Phase 16.5: Complete & Enhance — Build Spec

## Context
Phase 16 built phone_registry (22,327 numbers), i18n, light theme, Number Lookup, Permission Manager pages.
But `client_links` and `permission_overrides` tables exist in code (database_v2.py lines 513-538) but are NOT migrated yet.
Tests: 926 passed, 14 skipped. Committed as b01674c.

## Architecture Decision: NO Kubernetes
Stay monolithic. SQLite works fine for 300 members. Docker only for existing services (rustdesk, nocodb, tor-proxy).
Systemd for the bot. This is a single-server app. Ralph Loop = one process, one task.

## What to Build

### 1. Database Migration — Activate Pending Tables
The `client_links` and `permission_overrides` table CREATE statements already exist in `_init_db()` in database_v2.py.
- Verify they actually get created on startup (they should — they're in the same CREATE TABLE block)
- If not, add explicit migration
- Add new table: `client_notes` for commenting on client records:

```sql
CREATE TABLE IF NOT EXISTS client_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,           -- references clients.id
    phone_normalized TEXT,                 -- optional: link to phone_registry
    author_id INTEGER NOT NULL,           -- staff who wrote the note
    author_name TEXT NOT NULL,
    note_type TEXT DEFAULT 'comment',     -- comment|status_change|flag|link_note
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_client_notes_client ON client_notes(client_id);
CREATE INDEX IF NOT EXISTS idx_client_notes_phone ON client_notes(phone_normalized);
```

### 2. Enhanced Phone Registry Fields
Add columns to phone_registry (if not present):
- `category TEXT` — 类别 (UK表单粉, CA表单粉, etc.)
- `recruiter TEXT` — 招聘人员
- `account_id TEXT` — 账户ID
- `first_day_status TEXT` — 第一天 status
- `second_day_status TEXT` — 第二天 status  
- `client_condition TEXT` — 客户情况
- `team_name TEXT` — which 小组
- `leader_name TEXT` — which 组长

### 3. Client Linking System (Backend)
Methods already exist in database_v2.py (add_client_link, remove_client_link, get_client_links).
- Add API endpoints in web_dashboard_api.py:
  - `POST /api/clients/{id}/links` — link two clients
  - `DELETE /api/clients/{id}/links/{link_id}` — unlink
  - `GET /api/clients/{id}/links` — get all linked clients
  - `POST /api/clients/{id}/notes` — add a comment/note
  - `GET /api/clients/{id}/notes` — get all notes
  - `GET /api/clients/{id}/timeline` — unified timeline (status changes + notes + links + phone activity)

### 4. Admin Permission Editing (Backend)
Methods exist in database_v2.py (get_all_permission_overrides, set_permission_override).
- Add API endpoints:
  - `GET /api/admin/permissions/{staff_id}` — get permission overrides for a staff member
  - `POST /api/admin/permissions/{staff_id}` — set/update permission overrides
  - `DELETE /api/admin/permissions/{staff_id}/{section}` — remove a specific override
- RBAC: Only owner can edit admin permissions. Admins can edit member permissions within their team scope.

### 5. Performance Dashboard (Backend)
New endpoints matching the Google Sheets structure:
- `GET /api/performance/daily?date=YYYY-MM-DD&team=all` — daily stats per frontdesk
- `GET /api/performance/summary?from=DATE&to=DATE&team=TEAM` — date range summary
- Fields per frontdesk per day:
  - new_powder (新粉丝), today_reply, reply_rate
  - today_register, registration_rate
  - today_training, training_rate
  - today_withdraw, withdraw_count
  - today_new_order, conversion_rate
  - new_kills (新杀), dead_clients (死客)
- Auto-computed from existing client pipeline data

### 6. Dashboard React Pages

#### 6a. Client Detail Page (`/clients/:id`)
- Shows: phone number, owner (frontdesk), team, status, all linked numbers
- Timeline: chronological list of all interactions, notes, status changes
- Add Note button (modal with text + type selector)
- Link Number button (search + select another client)
- RBAC: Members see only their clients. Admins see team clients. Owner sees all.

#### 6b. Performance Dashboard (`/performance`)
- Date picker (single day or range)
- Team filter tabs (全线 | 阿毛组 | 阿俊组 | 何军组 | Juan Juan组)
- Per-frontdesk cards with metrics matching the sheets:
  - 粉量 | 回复率 | 注册 | 培训 | 提款 | 新单 | 转换率
- Summary row at bottom per team
- Light, happy colors. Use warm yellows, soft blues, gentle greens. NO dark mode. NO purple.
- Color scheme: backgrounds #f8fafc, cards #ffffff, borders #e2e8f0, accents #3b82f6 (blue), success #22c55e, warn #f59e0b

#### 6c. Enhanced Number Lookup (`/numbers` — already exists)
- Add: when viewing a number, show linked numbers as clickable chips
- Add: inline note/comment form
- Add: "Who owns this?" badge showing frontdesk + team

#### 6d. Enhanced Permission Manager (`/permissions` — already exists)
- Add: section-level toggle switches per staff member
- Add: admin can expand a member row and toggle permissions for:
  - view_clients, edit_clients, add_clients, view_performance, export_data, manage_team
- Visual: clean toggle switches, not checkboxes

### 7. Bot Commands Enhancement
- `/link <number1> <number2> [note]` — link two client numbers, log to client_links + client_notes
- `/comment <number> <text>` — add a note to a client record
- Enhanced `/add` flow: when duplicate detected, show FULL context:
  - "⚠️ 号码已存在！提交者: Tiger韦小宝 (2025-09-15) | 团队: 阿毛组 | 你的操作被记录。"
- `/stats [date]` — daily summary for the calling frontdesk's performance

### 8. i18n Extension
Extend i18n.py and i18n.ts for all new strings. Every user-facing string must have EN + ZH-CN.

### 9. Tests
Write tests for:
- client_links CRUD operations
- permission_overrides CRUD operations  
- client_notes CRUD operations
- Performance aggregation logic
- New API endpoints (at least 30 new tests)
- RBAC enforcement on new endpoints

## Important Notes
- Commit message: "Phase 16.5: Client linking, notes, performance dashboard, permission editing"
- Run ALL tests before committing — must pass 950+ (currently 926)
- Do NOT restart the bot service — just commit the code
- Theme: LIGHT ONLY. Happy mode. Warm colors. No purple (#c678dd is banned, use slate gray #7f848e).
- Dual language everywhere (EN/ZH-CN)
- Layout: responsive, mobile-friendly (frontdesk workers use phones)

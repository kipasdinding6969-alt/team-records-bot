# Phase 16: Duplicate Guard + Permission Engine + Dashboard i18n

## Overview
Replace the external Telegram "撞粉群" duplicate checking group with a built-in phone registry system. Add granular permission management for admins, client number cross-linking, and dashboard improvements (i18n, lighter theme).

## Data Source
- `data/phone_registry_import.json` — 22,327 unique phone numbers extracted from 53K messages in 撞粉群 (Aug 2025 - Mar 2026), 90 unique submitters, 1,489 duplicate conflicts.

---

## Part A: Phone Registry & Duplicate Guard

### New Table: `phone_registry`
```sql
CREATE TABLE IF NOT EXISTS phone_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    phone_normalized TEXT NOT NULL,  -- digits only, no +/spaces/dashes
    submitter_name TEXT NOT NULL,    -- display name of first submitter
    submitter_staff_id INTEGER REFERENCES staff(id),  -- linked staff (nullable for legacy imports)
    source TEXT DEFAULT 'telegram',  -- 'telegram' | 'bot' | 'import' | 'manual'
    submitted_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(phone_normalized)
);
CREATE INDEX idx_phone_registry_normalized ON phone_registry(phone_normalized);
CREATE INDEX idx_phone_registry_submitter ON phone_registry(submitter_name);
```

### New Table: `phone_registry_log` (audit trail)
```sql
CREATE TABLE IF NOT EXISTS phone_registry_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_normalized TEXT NOT NULL,
    action TEXT NOT NULL,  -- 'submit' | 'duplicate_blocked' | 'duplicate_self_edit' | 'admin_override' | 'import'
    actor_name TEXT NOT NULL,
    actor_staff_id INTEGER REFERENCES staff(id),
    details TEXT,  -- JSON: {original_submitter, conflict_info, etc}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Import Script: `import_phone_registry.py`
- Read `data/phone_registry_import.json`
- Normalize all numbers (strip +, spaces, dashes)
- Insert first submission as the owner record
- Log all duplicate attempts in `phone_registry_log`
- Try to match submitter names to existing staff (fuzzy match)
- Report: imported count, matched staff, unmatched submitters

### Bot Integration
- **On `/add` command**: Before creating client, check `phone_registry`:
  - If number NOT in registry → INSERT into registry + proceed with client creation
  - If number IN registry AND same frontdesk → ALLOW (can edit their own client)
  - If number IN registry AND different frontdesk → BLOCK with message:
    ```
    ⚠️ 号码重复 / Duplicate Number
    该号码已由 {submitter_name} 于 {date} 提交
    This number was submitted by {submitter_name} on {date}
    如需覆盖请联系管理员 / Contact admin to override
    ```
  - Admin/Leader can force-override with `/override <phone>`

### Dashboard Integration
- New page: **号码查询 / Number Lookup** — search any phone number, see who owns it, submission history
- In client list: show duplicate status icon (✅ clean / ⚠️ disputed)

---

## Part B: Client Number Cross-Linking

### New Table: `client_links`
```sql
CREATE TABLE IF NOT EXISTS client_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id_a INTEGER NOT NULL REFERENCES clients(id),
    client_id_b INTEGER NOT NULL REFERENCES clients(id),
    link_type TEXT NOT NULL DEFAULT 'related',  -- 'related' | 'same_person' | 'referral' | 'family'
    note TEXT,
    created_by INTEGER REFERENCES staff(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id_a, client_id_b)
);
```

### Bot Commands
- `/link <client_id_1> <client_id_2> [type] [note]` — link two clients
- `/unlink <client_id_1> <client_id_2>` — remove link
- `/links <client_id>` — show all linked clients

### Dashboard
- Client detail page: show linked clients section with link type badges
- Click to navigate between linked clients

---

## Part C: Granular Permission Management

### New Table: `permission_overrides`
```sql
CREATE TABLE IF NOT EXISTS permission_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL REFERENCES staff(id),
    command TEXT NOT NULL,           -- command name without /
    allowed BOOLEAN NOT NULL,       -- true=grant, false=deny
    granted_by INTEGER REFERENCES staff(id),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(staff_id, command)
);
```

### Permission Check Logic (update `check_permission`):
1. Check `permission_overrides` first (explicit grant/deny wins)
2. Fall back to role-based defaults from `models_v2.py`
3. Admins/Owners can always override

### Dashboard: Permission Management Page
- Owner/Admin can see all staff → click to manage permissions
- Show: role name, inherited permissions (grayed), overridden permissions (highlighted)
- Toggle switches for each command per staff member
- Bulk permission templates: "Frontdesk Standard", "Viewer Only", "Full Access"
- Admin can only manage permissions for staff in their team_scope
- Owner can manage anyone

### Bot Command
- `/perms <staff_name>` — show current permissions
- `/grant <staff_name> <command>` — grant command access
- `/revoke <staff_name> <command>` — revoke command access

---

## Part D: Dashboard i18n + Theme

### i18n System
- Language toggle in top nav: 🌐 EN | 中文
- Store preference in localStorage
- Translation file: `web_dashboard/src/i18n.ts`
- All UI strings use `t('key')` function
- Default: Chinese (current users are Chinese-speaking)

### Theme: Happy Mode
- Current theme: dark navy (#0d1117 bg)
- Add theme toggle: 🌙 Dark | ☀️ Light
- Light theme: white bg (#ffffff), soft gray cards (#f6f8fa), teal accents (#2dd4bf), warm text (#1f2937)
- NO pure black text — use dark gray
- NO purple anywhere — use slate gray (#7f848e) for secondary
- Cards: rounded corners (12px), subtle shadow, 1px border
- Status badges: soft pastel colors (green=#d1fae5, yellow=#fef3c7, red=#fee2e2)
- Charts: warm palette (teal, orange, sky blue — NO dark navy bars)

### Layout
- Responsive: mobile-first, breakpoints at 640/768/1024/1280px
- Sidebar: collapsible on mobile (hamburger menu)
- Cards: grid layout, 1 col mobile → 2 col tablet → 4 col desktop
- Tables: horizontal scroll on mobile, sticky first column

---

## Part E: New Dashboard Pages

### 1. 号码查询 / Number Lookup
- Search bar (phone number input)
- Results: owner, submission date, source, linked clients, duplicate history
- Admin: override button to reassign number ownership

### 2. 权限管理 / Permission Manager (Owner/Admin only)
- Staff list with role badges
- Click staff → permission detail panel
- Toggle switches per command
- Save button with confirmation

### 3. 关联客户 / Client Links (in existing client detail)
- Link panel showing connected clients
- Add link button with type selector
- Visual connection diagram (optional, stretch goal)

---

## Technical Notes
- NO Kubernetes — overkill for this scale. Keep SQLite + systemd
- NO new Docker containers — everything runs in existing bot process
- Import script runs once, then bot handles new entries
- All new tables created via migration in `database_v2.py initialize()`
- Tests: aim for 50+ new tests covering duplicate guard, permissions, links, i18n
- All API endpoints need RBAC scoping (owner sees all, admin sees team, member sees own)

## Build Order
1. Database migrations (4 new tables)
2. Import script + run it
3. Duplicate guard in bot handlers
4. Permission engine update
5. Client linking
6. Dashboard i18n system
7. Dashboard light theme
8. New dashboard pages (Number Lookup, Permission Manager)
9. Tests
10. Restart bot + verify

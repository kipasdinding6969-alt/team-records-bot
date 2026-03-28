# Schema V2 — Baiwan's Redesign for Team Records Bot

## Design Philosophy
The old schema mirrors Google Sheets columns. This one mirrors **what frontdesk actually does every day**:
1. Get assigned leads (粉丝)
2. Contact them → track response
3. Guide through registration → training → first order
4. Follow up on stale clients
5. Report progress

Everything flows from the **client lifecycle pipeline**.

---

## Core Tables

### 1. `staff` — Who works here
Replaces `team_members`. Simpler, role-aware.

```sql
CREATE TABLE staff (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id      INTEGER UNIQUE NOT NULL,
    tg_chat_id      INTEGER NOT NULL,
    tg_username     TEXT,
    display_name    TEXT NOT NULL,          -- "阿YIM", "阿俊" (their frontdesk name)
    role            TEXT NOT NULL DEFAULT 'frontdesk',  -- frontdesk | manager | admin
    team            TEXT,                  -- "发财小组", "金鑫小组", etc.
    phone           TEXT,
    language        TEXT DEFAULT 'zh',     -- zh | en
    is_active       BOOLEAN DEFAULT TRUE,
    daily_target    INTEGER DEFAULT 40,    -- configurable per-person target
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. `clients` — The actual pipeline (CORE TABLE)
Replaces `client_records`. One row = one client. Updated as they progress through the funnel.

```sql
CREATE TABLE clients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    frontdesk_id    INTEGER NOT NULL REFERENCES staff(id),
    
    -- Client identity
    phone           TEXT NOT NULL,
    account_id      TEXT,
    phone_remark    TEXT,                  -- "65 IPHONE SE"
    nickname        TEXT,
    
    -- Source tracking
    source          TEXT NOT NULL,         -- "飞机筛选", "RCS筛选", "UK表单粉", "CA表单粉"
    recruiter       TEXT,
    
    -- Pipeline status (THE KEY FIELD)
    status          TEXT NOT NULL DEFAULT 'new',
    -- new → contacted → replied → registered → training → withdrew → ordered
    -- Also: ghosted, blocked, scammed, scheduled, dead
    
    status_note     TEXT,                  -- "说明天再看", "被骗过不信"
    
    -- Milestone dates (auto-set on status change)
    contacted_at    TIMESTAMP,
    replied_at      TIMESTAMP,
    registered_at   TIMESTAMP,
    training_at     TIMESTAMP,
    withdrew_at     TIMESTAMP,
    first_order_at  TIMESTAMP,
    
    -- Follow-up
    next_followup   TIMESTAMP,
    followup_count  INTEGER DEFAULT 0,
    
    -- Financial
    platform        TEXT,                  -- "Iconnect" etc.
    total_deposited REAL DEFAULT 0,
    
    -- Compat
    sheet_gid       INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_clients_frontdesk ON clients(frontdesk_id);
CREATE INDEX idx_clients_status ON clients(status);
CREATE INDEX idx_clients_followup ON clients(next_followup);
CREATE INDEX idx_clients_created ON clients(created_at);
```

### 3. `client_notes` — Interaction log
Every touchpoint with a client. Replaces the old "第一天/第二天" binary.

```sql
CREATE TABLE client_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL REFERENCES clients(id),
    staff_id        INTEGER NOT NULL REFERENCES staff(id),
    note_type       TEXT NOT NULL,         -- status_change | followup | note | call | message
    old_status      TEXT,
    new_status      TEXT,
    content         TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notes_client ON client_notes(client_id);
CREATE INDEX idx_notes_created ON client_notes(created_at);
```

### 4. `daily_stats` — Auto-calculated daily snapshot
Replaces `performance_records` + `daily_summary_records`. Auto-generated, not manually entered.

```sql
CREATE TABLE daily_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id        INTEGER NOT NULL REFERENCES staff(id),
    stat_date       DATE NOT NULL,
    
    new_leads       INTEGER DEFAULT 0,
    contacted       INTEGER DEFAULT 0,
    replied         INTEGER DEFAULT 0,
    registered      INTEGER DEFAULT 0,
    training        INTEGER DEFAULT 0,
    withdrew        INTEGER DEFAULT 0,
    new_orders      INTEGER DEFAULT 0,
    
    ghosted         INTEGER DEFAULT 0,
    blocked         INTEGER DEFAULT 0,
    dead            INTEGER DEFAULT 0,
    
    reply_rate      REAL DEFAULT 0,
    conversion_rate REAL DEFAULT 0,
    total_deposit   REAL DEFAULT 0,
    
    UNIQUE(staff_id, stat_date),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_daily_stats_date ON daily_stats(stat_date);
CREATE INDEX idx_daily_stats_staff ON daily_stats(staff_id);
```

### 5. `deposits` — Money tracking
Per-transaction. Replaces `financial_records`.

```sql
CREATE TABLE deposits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL REFERENCES clients(id),
    frontdesk_id    INTEGER NOT NULL REFERENCES staff(id),
    
    amount          REAL NOT NULL,
    currency        TEXT DEFAULT 'USD',
    platform        TEXT,
    knife_number    INTEGER,               -- which knife (刀): 1-8
    role_type       TEXT,                  -- frontdesk | opener | newbie | group_chat | cs | maintenance
    
    note            TEXT,
    deposit_date    DATE NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deposits_client ON deposits(client_id);
CREATE INDEX idx_deposits_frontdesk ON deposits(frontdesk_id);
CREATE INDEX idx_deposits_date ON deposits(deposit_date);
```

### 6. `reminders` — Self-service (any role can create)

```sql
CREATE TABLE reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id        INTEGER NOT NULL REFERENCES staff(id),
    client_id       INTEGER REFERENCES clients(id),
    
    remind_at       TIMESTAMP NOT NULL,
    message         TEXT NOT NULL,
    is_sent         BOOLEAN DEFAULT FALSE,
    sent_at         TIMESTAMP,
    source          TEXT DEFAULT 'manual',  -- manual | auto_followup | auto_stale
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reminders_pending ON reminders(remind_at, is_sent);
CREATE INDEX idx_reminders_staff ON reminders(staff_id);
```

### 7. `team_targets` — Goals per team (new)

```sql
CREATE TABLE team_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    team            TEXT NOT NULL,
    period_type     TEXT NOT NULL,          -- weekly | monthly
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    
    target_leads    INTEGER,
    target_registers INTEGER,
    target_orders   INTEGER,
    target_deposit  REAL,
    
    created_by      INTEGER REFERENCES staff(id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team, period_type, period_start)
);
```

### 8. `bot_settings` — Global config (unchanged)
```sql
CREATE TABLE bot_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## New Frontdesk Commands

| Command | What it does | Old way |
|---------|-------------|---------|
| `/add 1234567890 飞机筛选` | Add client (2 fields) | 11-step wizard |
| `/u 1234567890 registered` | Update client status | No quick update existed |
| `/pipeline` | See your funnel view | Flat client list |
| `/remind 1234567890 2h 跟进` | Set own reminder | Admin only |
| `/today` | Today's stats (auto-calculated) | Manual Google Sheets |
| `/note 1234567890 说明天来` | Add note to client | No interaction log |
| `/followup` | See who needs follow-up | No tracking |
| `/search 阿YIM` | Search clients by any field | No search |

### Status Flow (inline buttons)
After viewing any client, quick-tap buttons:
`[📱 Contacted] [💬 Replied] [✅ Registered] [📚 Training] [💰 Withdrew] [🎯 Ordered] [💀 Dead]`

### Pipeline View (`/pipeline`)
```
📊 Your Pipeline (阿YIM)

🆕 New (12)
📱 Contacted (8)  
💬 Replied (5)
✅ Registered (3)
📚 Training (2)
💰 Withdrew (1)
🎯 Ordered (0)

⚠️ Needs follow-up: 4 clients
🔥 Stale >3 days: 2 clients
```

### Auto-Reminders (Ralph Loop)
- Client in "contacted" >24h, no reply → remind frontdesk
- Client "registered" >48h, no training → remind frontdesk  
- Client "training" >72h, no withdrawal → remind frontdesk
- Client in any non-terminal status >3 days → stale alert

---

## What This Fixes

| Problem | Old | New |
|---------|-----|-----|
| 11-step wizard to add client | Fill 11 fields one by one | `/add phone source` (2 fields) |
| Binary status (注册/不注册) | Day1/Day2 only | Full pipeline: 10+ statuses |
| No follow-up tracking | Admin-only reminders | Auto-reminders + self-service |
| No pipeline view | Flat list | Funnel with counts |
| Manual daily stats | Fill Google Sheets by hand | Auto-calculated from status changes |
| Admin-locked features | Most features need admin | Frontdesk self-sufficient |
| No interaction history | Just 注册/不注册 per day | Full note/log per client |
| Google Sheets = source of truth | Bot mirrors sheets | Bot is source, sheets are exports |

---

## Migration Path
1. `team_members` → `staff` (rename + add `team`, `daily_target`)
2. `client_records` → `clients` (map 注册 → status, flatten)
3. `financial_records` → `deposits` (per-transaction)
4. `performance_records` + `daily_summary` → `daily_stats` (auto-calculated)
5. Google Sheets sync flips: bot → sheets (export), not sheets → bot (import)

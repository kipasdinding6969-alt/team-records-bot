# Phase 10: Commission Tracking + Advanced Analytics + Shift Handoff

## Overview
Three features that close the loop on the MONEY pipeline — track what each frontdesk worker actually earns the company, generate manager-grade reports, and enable clean shift handoffs.

## 10A: Commission Tracking

### Problem
Deposits are logged but there's no commission calculation. Managers manually calculate bonuses. Workers have no incentive visibility.

### Database
```sql
CREATE TABLE IF NOT EXISTS commission_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team TEXT,  -- NULL = applies to all teams
    status_trigger TEXT NOT NULL,  -- 'deposit', 'first_deposit', 'registration'
    rate_type TEXT NOT NULL,  -- 'percentage', 'fixed'
    rate_value REAL NOT NULL,  -- 0.05 = 5% or 50 = $50 fixed
    min_amount REAL DEFAULT 0,  -- minimum deposit to qualify
    max_commission REAL,  -- cap per transaction
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS commissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL REFERENCES staff(id),
    client_id INTEGER REFERENCES clients(id),
    deposit_id INTEGER REFERENCES deposits(id),
    rule_id INTEGER REFERENCES commission_rules(id),
    trigger_type TEXT NOT NULL,  -- 'deposit', 'first_deposit', 'registration'
    amount REAL NOT NULL,  -- commission earned
    status TEXT DEFAULT 'pending',  -- pending, approved, paid, rejected
    approved_by INTEGER REFERENCES staff(id),
    period TEXT,  -- '2026-W13', '2026-03' for grouping
    created_at TIMESTAMP DEFAULT (datetime('now'))
);
CREATE INDEX idx_commissions_staff ON commissions(staff_id, period);
CREATE INDEX idx_commissions_status ON commissions(status, created_at);
```

### Default Rules (seeded on first run)
1. Deposit commission: 5% of deposit amount
2. First deposit bonus: $10 fixed
3. Registration bonus: $2 fixed

### Auto-Calculation
Hook into deposit creation and status changes:
- On deposit → auto-create commission record (pending)
- On status → 'registered' AND first registration → create registration bonus
- On first deposit for a client → create first_deposit bonus

### Commands
- `/commission [period]` — My commission this period (default: current week)
- `/commission team [period]` — Team commission breakdown (manager+)
- `/commission rules` — Show active commission rules (admin only)
- `/commission set <trigger> <rate_type> <rate_value>` — Set commission rule (admin only)
- `/commission approve [staff] [period]` — Approve pending commissions (manager+)

### Inline Keyboard
After showing commission:
`[✅ Approve All] [📊 Breakdown] [📅 Last Week] [📅 This Month]`

### Integration
- Commission totals in daily digest
- Commission column in web dashboard
- XP bonus for hitting commission targets

## 10B: Advanced Analytics & Reports

### Weekly/Monthly PDF Reports
Generate downloadable reports via `/report` command:

```
📊 Weekly Report — Week 13 (Mar 24-30)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pipeline Summary:
├ New clients: 45 (+12% vs last week)
├ Contacted: 38 (84% contact rate)
├ Replied: 28 (74% reply rate)
├ Registered: 18 (64% registration rate)
├ Deposited: 12 (67% deposit rate)
└ Total deposits: $15,400

Staff Rankings:
│ #1 小李 — 8 deposits, $6,200, ⭐ 92% SLA
│ #2 小王 — 5 deposits, $4,100, ⭐ 88% SLA
│ #3 小张 — 4 deposits, $3,200, ⭐ 95% SLA

Commission Summary:
├ Total earned: $770
├ Pending approval: $320
└ Top earner: 小李 ($310)

Insights:
⚡ Facebook leads convert 2x better than Telegram
⚠️ 6 clients stale >7 days — need follow-up
🎯 Team on track for monthly target (78%)
```

### Commands
- `/report [weekly|monthly] [team]` — Generate report (manager+)
- `/report compare <period1> <period2>` — Compare two periods
- `/funnel [period]` — Conversion funnel visualization

### Funnel Display
```
📈 Conversion Funnel — This Week
━━━━━━━━━━━━━━━━━━━━━━━━━━━
██████████████████████ 45 New
████████████████████  38 Contacted (84%)
██████████████        28 Replied (62%)
██████████            18 Registered (40%)
██████                12 Deposited (27%)
```

### Analytics Helpers (database_v2.py)
- `get_pipeline_stats(period, team)` — Counts per status
- `get_conversion_rates(period, team)` — Stage-to-stage rates
- `get_staff_rankings(period, team, metric)` — Ranked staff by metric
- `get_source_analysis(period, team)` — Breakdown by lead source
- `get_period_comparison(period1, period2, team)` — Delta analysis
- `get_stale_clients(days, team)` — Clients with no activity in N days

## 10C: Shift Handoff

### Problem
When frontdesk workers switch shifts, the next person has no context about active conversations.

### Database
```sql
CREATE TABLE IF NOT EXISTS shift_handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_staff_id INTEGER NOT NULL REFERENCES staff(id),
    to_staff_id INTEGER REFERENCES staff(id),  -- NULL = to any available
    team TEXT,
    status TEXT DEFAULT 'pending',  -- pending, accepted, completed
    notes TEXT,  -- handoff notes from outgoing staff
    client_ids TEXT,  -- JSON array of active client IDs being handed off
    created_at TIMESTAMP DEFAULT (datetime('now')),
    accepted_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### Commands
- `/handoff [@username]` — Start shift handoff (creates summary of your active clients)
- `/handoff accept <id>` — Accept incoming handoff
- `/handoff list` — Show pending handoffs for your team

### Handoff Flow
1. Staff types `/handoff @小王`
2. Bot generates active client summary:
```
🔄 Shift Handoff from 小李 → 小王
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Active Clients (5):

1. 阿明 (08123456) — replied, 等待注册
   📝 "今天下午会来注册，客户很积极"
   ⏰ Last contact: 2h ago

2. 小红 (09876543) — contacted, 需要跟进
   📝 "发了消息还没回，建议明天早上再联系"
   ⏰ Last contact: 5h ago

3. ...

[✅ Accept Handoff] [❌ Decline]
```
3. Receiving staff taps Accept → clients reassigned, event logged in timeline

### Integration
- Handoff events appear in client timeline
- Handoff summary in daily digest
- XP bonus for clean handoffs (all clients have notes)

## Files to Create

### New Files
- `handlers_v2/commission_handler.py` — Commission commands + callbacks
- `handlers_v2/report_handler.py` — Report generation + analytics
- `handlers_v2/handoff_handler.py` — Shift handoff flow
- `tests/test_commission.py` — Commission tests (minimum 20)
- `tests/test_report.py` — Report/analytics tests (minimum 15)
- `tests/test_handoff.py` — Handoff tests (minimum 10)

### Modified Files
- `database_v2.py` — New tables + analytics query methods
- `models_v2.py` — Commission, CommissionRule, ShiftHandoff models
- `main.py` — Register new handlers + hook commission into deposit/status flows

## Test Targets
- Commission auto-calculation on deposit
- Commission rules CRUD (admin only)
- Commission approval flow
- Period-based commission grouping
- Analytics query accuracy (funnel, rankings, source)
- Report text formatting
- Period comparison (week-over-week)
- Handoff creation with active client summary
- Handoff accept → client reassignment
- Handoff decline flow
- Permission checks (commission rules = admin, reports = manager+)
- Edge cases: zero deposits, no clients, new staff

## Commit Message
```
feat(money): Phase 10 — commission tracking, advanced analytics, shift handoff
```

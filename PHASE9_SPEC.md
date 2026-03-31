# Phase 9: Smart CRM Intelligence

## Overview
Four interconnected intelligence features that transform raw CRM data into actionable insights.

## 9A: Smart Tags & Filters
### Database
```sql
CREATE TABLE IF NOT EXISTS client_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    tag TEXT NOT NULL,
    tagged_by INTEGER REFERENCES staff(id),
    created_at TIMESTAMP DEFAULT (datetime('now')),
    UNIQUE(client_id, tag)
);
```

### Commands
- `/tag <phone_or_name> <tag1> [tag2...]` — Add tags to client (VIP, whale, referral, problem, hot, cold, etc.)
- `/untag <phone_or_name> <tag>` — Remove a tag
- `/tags [client]` — Show tags for a client, or list all tags with counts
- `/filter <criteria>` — Smart filter: `tag:vip status:replied`, `tag:whale stale:3d`, `source:facebook registered:no`

### Inline Keyboard
When viewing a client (via /info or NL query), show quick-tag buttons:
`[🏷️ VIP] [🐋 Whale] [⭐ Hot] [⚠️ Problem] [📎 Referral]`

### Integration
- Tags visible in Mini App client cards
- Tags in web dashboard filters
- Tags in daily digest ("3 VIP clients need attention")

## 9B: Client Timeline / Activity Feed
### Database
```sql
CREATE TABLE IF NOT EXISTS client_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    event_type TEXT NOT NULL, -- status_change, note_added, deposit, tag_added, tag_removed, voice_update, follow_up_sent, reminder_set, handoff
    event_data TEXT, -- JSON with details
    staff_id INTEGER REFERENCES staff(id),
    created_at TIMESTAMP DEFAULT (datetime('now'))
);
CREATE INDEX idx_client_events_client ON client_events(client_id, created_at DESC);
CREATE INDEX idx_client_events_type ON client_events(event_type, created_at DESC);
```

### Commands
- `/timeline <phone_or_name> [count]` — Show last N events (default 10)
- `/timeline <phone_or_name> today` — Today's events only

### Event Logging (automatic)
Hook into ALL existing actions to log events:
- Status changes → event_type='status_change', data={from, to, by}
- Notes added → event_type='note_added', data={note_preview}
- Deposits → event_type='deposit', data={amount, platform}
- Tags → event_type='tag_added'/'tag_removed'
- Voice updates → event_type='voice_update'
- Follow-ups → event_type='follow_up_sent'
- Reminders → event_type='reminder_set'
- Handoffs → event_type='handoff', data={from_team, to_team}

### Display Format
```
📋 Timeline for 阿明 (08123456)
━━━━━━━━━━━━━━━━━━━━━
🟢 03-31 14:30 — Status → registered (by 小李)
💰 03-31 12:15 — Deposit $500 via USDT (by 小李)
🏷️ 03-31 10:00 — Tagged as VIP (by 经理)
📝 03-30 16:45 — Note: "客户很积极，明天培训"
🔄 03-30 09:00 — Status → replied (by 小李)
📞 03-29 15:30 — Voice update: "新客户从FB来的"
🆕 03-29 14:00 — Client created (by 小李)
```

## 9C: SLA Tracking
### Database
```sql
CREATE TABLE IF NOT EXISTS sla_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    staff_id INTEGER NOT NULL REFERENCES staff(id),
    event_type TEXT NOT NULL, -- first_response, status_update, follow_up_response
    target_minutes INTEGER NOT NULL, -- SLA target
    actual_minutes INTEGER, -- NULL if still open
    met BOOLEAN, -- NULL if still open
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sla_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL UNIQUE,
    target_minutes INTEGER NOT NULL,
    warning_minutes INTEGER NOT NULL, -- when to warn
    critical_minutes INTEGER NOT NULL -- when to escalate
);
```

### Default SLA Targets
- first_response: 30 min (warn at 20, critical at 45)
- status_update: 120 min / 2h (warn at 90, critical at 180)
- follow_up_response: 60 min (warn at 45, critical at 90)

### Commands
- `/sla` — Team SLA dashboard (compliance %, avg response time)
- `/sla <staff_name>` — Individual SLA metrics
- `/sla config <type> <target_min> [warn_min] [critical_min]` — Configure SLA (admin only)

### Auto-Actions
- Ralph Loop checks open SLA events every cycle
- Warning: notify staff via PM when approaching SLA breach
- Critical: notify team leader + post to 问题 topic
- SLA compliance feeds into performance coaching

### Integration with XP
- Meeting SLA = +5 XP per response
- SLA breach = no XP for that interaction
- Perfect SLA day = +20 bonus XP

## 9D: Performance Coaching
### Commands
- `/coaching [staff_name]` — AI-generated coaching report
- `/coaching team` — Team-wide coaching summary

### Metrics Analyzed
1. SLA compliance rate
2. Reply rate (clients replied / total assigned)
3. Conversion rate (registered / contacted)
4. Average response time
5. XP velocity (XP earned per day trend)
6. Streak consistency
7. Client satisfaction (deposit follow-through rate)

### AI Coaching (Ollama)
Generate personalized coaching tips using the josiefied-qwen2.5-7b model:
```
Prompt: "Based on these CRM metrics for {staff_name}:
- SLA compliance: {sla_pct}%
- Reply rate: {reply_pct}%
- Conversion rate: {conv_pct}%
- Avg response time: {avg_resp} minutes
- XP this week: {xp}

Provide 3 specific, actionable coaching tips in Chinese. Be encouraging but honest.
Focus on the weakest metric. Keep each tip under 2 sentences."
```

### Display
```
📊 Coaching Report: 小李
━━━━━━━━━━━━━━━━━━━━━
⏱️ SLA Compliance: 87% (team avg: 82%)
💬 Reply Rate: 72% (team avg: 65%)  
📈 Conversion: 34% (team avg: 28%)
⚡ Avg Response: 22 min (team avg: 35 min)
🔥 XP Velocity: 45/day ↑ (was 38/day last week)

🤖 AI Coaching Tips:
1. 你的回复率在团队中名列前茅！试着在新客户注册后2小时内跟进培训安排，这样转化率能再提升。
2. 有3个VIP客户超过2天没联系了，优先处理他们。
3. 连续5天达标SLA，继续保持！目标设定为90%试试。
```

## Technical Requirements
- All new tables need migration in database_v2.py init
- All commands registered in handlers_v2/
- Timeline events auto-logged via hooks in existing handlers
- SLA check integrated into Ralph Loop main cycle
- Coaching uses existing Ollama integration
- All features respect team scoping (group = team filter)
- Tests: minimum 30 new tests covering all 4 sub-features
- i18n: Chinese primary, English fallback

## Files to Create/Modify
### New Files
- `handlers_v2/tags.py` — Tag commands + inline keyboards
- `handlers_v2/timeline.py` — Timeline command + display
- `handlers_v2/sla.py` — SLA commands + config
- `handlers_v2/coaching.py` — Coaching command + AI generation
- `engines/sla_engine.py` — SLA tracking logic + Ralph Loop integration
- `tests/test_tags.py` — Tag tests
- `tests/test_timeline.py` — Timeline tests
- `tests/test_sla.py` — SLA tests
- `tests/test_coaching.py` — Coaching tests

### Modified Files
- `database_v2.py` — New tables + CRUD methods
- `handlers_v2/__init__.py` — Register new handlers
- `main.py` — Wire SLA engine into Ralph Loop
- `engines/ralph_loop.py` or equivalent — Add SLA check cycle

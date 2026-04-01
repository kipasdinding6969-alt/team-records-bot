# Phase 19 — Gemini UI: Targets, Commissions, Templates, Contests, Gamification

Working directory: `/home/baiwan/repos/team-records-bot-v2/web_dashboard/`

## New Backend Endpoints (all working, tested)

### Targets
- `GET /api/targets?team=all` → `[{id, team, period_type, period_start, period_end, target_leads, target_registers, target_orders, target_deposit}]`
- `POST /api/targets` → `{team, period_type, period_start, period_end, target_leads?, target_registers?, target_orders?, target_deposit?}`

### Real Trends (replaces mock random sparklines)
- `GET /api/performance/trends-batch?team=all&days=7` → `{staff_id: [leads_day1, leads_day2, ...], ...}`
- `GET /api/performance/trend?staff_id=X&days=7` → `[{stat_date, new_leads, registered, ...}]`

### Commissions
- `GET /api/commissions?period=2026-W14&team=all` → `[{staff_name, trigger_type, amount, status, period}]`
- `GET /api/commissions/summary?period=2026-W14` → `[{display_name, team, approved_total, pending_total}]`

### Templates (5 already in DB)
- `GET /api/templates` → `[{id, name, content, category, is_default, created_by_name}]`
- `POST /api/templates` → `{name, content, category}`
- `PUT /api/templates/{id}` → same body
- `DELETE /api/templates/{id}`

### Contests
- `GET /api/contests` → `[{id, title, metric, target, team, start_date, end_date, status, winner_name}]`
- `POST /api/contests` → `{title, metric, target, team?, start_date, end_date}`
- `GET /api/contests/{id}/leaderboard` → `[{staff_id, display_name, team, score}]`

### Gamification
- `GET /api/gamification/{staff_id}` → `{total_xp, streak: {current_streak, longest_streak}, badges: [{name, emoji}], recent_xp: [{action, xp_amount}]}`

## Pages to Build

### 1. MODIFY: Performance.tsx
- Replace mock random sparklines with REAL data from `api.trendsBatch(team, 7)`
- Fetch once on mount, pass `trends[staff_id]` to each `<Sparkline>` component
- Add "Target vs Actual" progress bar if team has targets (fetch `api.getTargets(team)`)

### 2. NEW: Targets section in Team.tsx or separate Targets page
- Simple table: team | period | target leads | target orders | target deposit | actual (computed from daily_stats)
- "Set Target" button (admin/owner) → modal with form
- Progress bars: actual/target as colored bars (green if >80%, yellow 50-80%, red <50%)

### 3. NEW: Templates page (`/templates`) — admin only
- Card grid: each template as a card with name, category badge, preview of content
- Click → expand to full content
- "New Template" button → modal
- Edit/Delete inline
- Category filter tabs: general, followup, greeting, closing

### 4. NEW: Contests page (`/contests`) — for all users
- Active contests as hero cards with countdown timer
- Leaderboard table per contest
- "Create Contest" button (admin/owner) → modal
- Metric selector: new_leads, registered, deposits, orders
- Past contests in collapsed section

### 5. MODIFY: StaffDetailModal.tsx
- Add gamification section: XP bar, streak flame icon, badge collection
- Show recent XP events as small timeline
- If staff has 0 XP, show "No activity yet" placeholder

### 6. ADD to sidebar: new nav items
- `/templates` — icon: 📝, label: 'Templates' / '消息模板', adminOnly: true
- `/contests` — icon: 🏆, label: 'Contests' / '竞赛', adminOnly: false

### 7. ADD to App.tsx: new routes
- `/templates` → Templates page (AdminRoute)
- `/contests` → Contests page (ProtectedRoute)

## i18n Keys
```
nav.templates: '消息模板' / 'Templates'
nav.contests: '竞赛' / 'Contests'
targets.title: '团队目标' / 'Team Targets'
targets.set: '设置目标' / 'Set Target'
targets.leads: '目标粉量' / 'Target Leads'
targets.orders: '目标订单' / 'Target Orders'
targets.deposit: '目标充值' / 'Target Deposit'
targets.actual: '实际' / 'Actual'
targets.progress: '进度' / 'Progress'
templates.title: '消息模板' / 'Message Templates'
templates.new: '新建模板' / 'New Template'
templates.name: '模板名称' / 'Template Name'
templates.content: '模板内容' / 'Content'
templates.category: '分类' / 'Category'
contests.title: '竞赛' / 'Contests'
contests.new: '新建竞赛' / 'New Contest'
contests.metric: '指标' / 'Metric'
contests.target: '目标' / 'Target'
contests.leaderboard: '排行榜' / 'Leaderboard'
contests.active: '进行中' / 'Active'
contests.ended: '已结束' / 'Ended'
gamification.xp: '经验值' / 'XP'
gamification.streak: '连续天数' / 'Streak'
gamification.badges: '徽章' / 'Badges'
gamification.no_activity: '暂无活动' / 'No activity yet'
```

## Design
- Follow existing glassmorphism style (glass-card, glass-btn, data-grid-table)
- Happy mode: warm, light colors
- Progress bars: rounded, animated fill, green/yellow/red gradient
- Contest cards: hero style with gradient accent border
- Template cards: compact, monospace content preview, category color badges
- Gamification: XP as horizontal progress bar, streak as 🔥 icon, badges as emoji grid

## Build & Deploy
```bash
cd /home/baiwan/repos/team-records-bot-v2/web_dashboard && npm run build
cd /home/baiwan/repos/team-records-bot-v2 && bash deploy_dashboard.sh --start-only
```

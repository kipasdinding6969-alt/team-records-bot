# Phase 18 — Gemini UI/UX Build: Staff Management + Org Chart Polish + Add Client Flow

Working directory: `/home/baiwan/repos/team-records-bot-v2/web_dashboard/`

## Context
- React + TypeScript + Vite, API at `http://127.0.0.1:8501`
- Theme uses `useTheme()` from `ThemeContext.tsx`, glassmorphism classes (`glass-card`, `glass-btn`, `glass-panel`)
- **HAPPY MODE** — light preferred, warm colors, NO purple (#c678dd banned)
- **Dual language** EN/ZH via `t()` from `src/i18n.ts`
- **Responsive** — frontdesk uses phones

## New Backend Endpoints Available

### PUT /api/staff/{id}
Body: `{ team?, role?, display_name?, daily_target?, is_active? }`
RBAC: owner can do anything, admin can only modify frontdesk/newbie/cs in their team

### GET /api/staff/all
Returns: `[{ id, display_name, role, team, tg_username, daily_target, is_active, phone, language, client_count }]`
Scoped by user role.

### POST /api/performance/recalculate
Returns: `{ ok, date, staff_updated }`
Owner/Admin only.

### POST /api/clients
Body: `{ phone, source, account_id?, nickname?, platform?, phone_remark?, recruiter?, category? }`
Returns 200 `{ ok, client_id }` or 409 with duplicate info.

### GET /api/phone-registry/check?phone=XXX
Returns: `{ phone, normalized, status: 'available'|'own'|'taken', owner?, editable?, client_id?, ... }`

## Pages to Build/Modify

### 1. MODIFY: OrgChart.tsx (`/org-chart`)
Current version is functional but basic. Enhance:
- Add click-to-edit on each staff member: change team, role, daily_target via inline modal
- Show staff avatar initial (first char of name) in a colored circle
- Team cards should show team stats: total clients, total deposits, avg daily target
- "Assign Team" dropdown on unassigned staff cards
- Role change dropdown (only show roles the current user can assign)
- Add search/filter box at top

### 2. MODIFY: Clients.tsx (`/clients`)
The "➕ 新增客户" modal needs polish:
- Make the modal wider (520px) with 2-column grid layout
- Phone input: larger, prominent, with phone icon prefix
- Live duplicate indicator should be more visual:
  - Green pulsing dot + "Available" badge
  - Red pulsing dot + warning box with owner name for "Taken"
  - Yellow dot + "Your Number (editable)" for "Own"
- Category dropdown should have colored badges for each option
- Add a "Check Again" button next to phone input
- Smooth modal open/close animation

### 3. NEW: StaffDetail page or modal
When clicking a staff member in OrgChart or Team page, show:
- Profile card: name, role badge, team, daily target, phone, language
- Client count + list preview (top 5 clients)
- Permission overrides (if any)
- "Edit" button to change team/role/target/active status
- "View Clients" link → filtered clients page

### 4. MODIFY: Performance.tsx
- Add a "🔄 Recalculate" button (already wired in api.ts as `api.recalculateStats()`)
- Show a toast/notification when recalculation completes
- The data grid already exists — make sure "No data" state is more friendly
- Add a mini sparkline or bar chart per staff member showing 7-day trend (use inline SVG)

### 5. MODIFY: Team.tsx
- Add staff count per team as a badge
- Click team name → filter to that team in Clients page
- Add mini performance summary per team (using `/api/team/{team}/performance`)

## Design Rules (follow Gemini's existing glassmorphism style)
1. Glass cards: `glass-card` class with backdrop-filter
2. Buttons: `glass-btn` class with hover transform
3. Tables: `data-grid-table` class with sticky frosted headers
4. Modals: centered, backdrop blur, rounded-16px, max-width 520px
5. Badges: `pill-badge` class, rounded-full, role-specific colors
6. Transitions: 0.2-0.3s cubic-bezier(0.4, 0, 0.2, 1)
7. Empty states: `empty-state` class with centered icon + message
8. All text via `t()` with EN/ZH keys

## i18n Keys to Add
```
org.edit_staff: 'Edit Staff' / '编辑员工'
org.assign_team: 'Assign Team' / '分配团队'
org.change_role: 'Change Role' / '更改角色'
org.daily_target: 'Daily Target' / '日目标'
org.save_changes: 'Save Changes' / '保存更改'
org.staff_detail: 'Staff Detail' / '员工详情'
org.view_clients: 'View Clients' / '查看客户'
clients.check_again: 'Check Again' / '再次检查'
clients.phone_available: 'Number available' / '号码可用'
clients.phone_taken: 'Number taken by {owner}' / '号码已被 {owner} 占用'
clients.phone_own: 'Your number (editable)' / '你的号码 (可编辑)'
perf.recalculating: 'Recalculating...' / '重新计算中...'
perf.recalculated: 'Stats updated for {count} staff' / '已更新 {count} 位员工统计'
```

## Build
```bash
cd /home/baiwan/repos/team-records-bot-v2/web_dashboard && npm run build
```

## After Build
```bash
cd /home/baiwan/repos/team-records-bot-v2 && bash deploy_dashboard.sh --start-only
```

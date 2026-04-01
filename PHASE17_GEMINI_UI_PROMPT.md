# Phase 17 — Gemini UI/UX Build Prompt

You are building the frontend for Phase 17 of team-records-bot dashboard at `/home/baiwan/team-records-bot/web_dashboard/`.

## Context
- React + TypeScript + Vite
- API at `http://127.0.0.1:8501`
- Existing pages in `src/pages/`: Dashboard, Clients, ClientDetail, Pipeline, Performance, Reports, Team, UserManagement, PermissionManager, NumberLookup, Login, Setup
- Theme: **HAPPY MODE** — light backgrounds, warm colors. NO dark mode. NO purple (#c678dd is BANNED, use #7f848e slate gray).
- Color palette: bg #f8fafc, cards #ffffff, borders #e2e8f0, accent #3b82f6, success #22c55e, warn #f59e0b, danger #ef4444
- **Dual language**: EN/ZH-CN. Use i18n context from `src/i18n.ts`
- **Responsive**: Mobile-friendly (frontdesk uses phones)
- Font: monospace for numbers/dates, system font for labels

## New API Endpoints (already built in backend)

### GET /api/org-chart
Returns: `{ teams: [{ team, leader: {id, display_name, role, active_clients, override_count}, members: [{...}], member_count, total_clients }], unassigned: [...] }`

### GET /api/clients/{id}/linked-timeline
Returns: `{ client_id, linked_client_ids: [int], timeline: [{timeline_type: 'note'|'deposit'|'link', content, created_at, client_phone, staff_name, ...}] }`

### POST /api/clients
Body: `{ phone, source, account_id?, nickname?, platform? }`
Returns 200 `{ ok, client_id }` or 409 with duplicate info `{ detail: { type: 'duplicate', owner, submitted_at, message } }`

### GET /api/phone-registry/check?phone=XXX
Returns: `{ phone, normalized, status: 'available'|'own'|'taken', owner?, editable?, client_id?, ... }`

### POST /api/permissions/bulk
Body: `{ staff_id, permissions: {command: bool}, reason? }`

## Pages to Build/Modify

### 1. NEW: OrgChart.tsx (`/org-chart`)
- Tree visualization of team hierarchy
- Each team is a card with leader at top, members below
- Show: name, role badge, active client count, last active
- Click member → navigate to their permission page
- Leader card is highlighted (soft blue border)
- Unassigned staff shown in separate "unassigned" section
- Summary bar: total teams, total staff, total active clients

### 2. MODIFY: ClientDetail.tsx (`/clients/:id`)
- Add "Linked Timeline" tab alongside existing "Notes" and "Timeline" tabs
- Fetch from GET /api/clients/{id}/linked-timeline
- Show entries from ALL linked clients with color-coded badges:
  - Blue badge: notes from this client
  - Green badge: notes from linked client (show phone number)
  - Gold badge: deposits
  - Gray badge: link events
- Each entry shows: timestamp, author, content, source client phone
- "Link Client" button: modal with phone search → select → create link

### 3. MODIFY: NumberLookup.tsx (`/numbers`)
- Before search: show real-time duplicate check using GET /api/phone-registry/check
- When number found:
  - Show ownership badge: "Your Number" (green) or "Taken by {name}" (red) or "Available" (blue)
  - If own: show "Edit" button
  - If taken: show owner name, team, submitted date
  - Show all linked clients as clickable chips below
- Add inline comment form (POST /api/clients/{id}/notes)

### 4. MODIFY: PermissionManager.tsx (`/permissions`)
- Group by team (accordion sections)
- Each team section shows leader → members hierarchy
- Expandable row per staff member with toggle switches for:
  - add, search, export, note, pipeline, dashboard, override, link, comment, stats
- Toggle switches (not checkboxes) — soft rounded, green=allowed, gray=denied
- "Apply All" button per section (bulk POST /api/permissions/bulk)
- Admin can only see/modify their team. Owner sees all teams.
- Role badge next to staff name (color-coded by role)

### 5. MODIFY: Clients.tsx
- Add "New Client" button that opens a modal
- Modal: phone input with LIVE duplicate check (GET /api/phone-registry/check on debounced input)
  - Shows green checkmark if available
  - Shows red warning with owner name if taken
  - Shows yellow "Your number" if own
- Source selector (dropdown or buttons)
- Submit calls POST /api/clients
- On 409 duplicate, show clear error with owner info

### 6. MODIFY: Layout.tsx / Navigation
- Add "Org Chart" to sidebar nav (icon: sitemap/hierarchy)
- Route: `/org-chart` → OrgChart.tsx

## Design Rules
1. Cards: `rounded-xl shadow-sm border border-gray-200 bg-white`
2. Badges: `px-2 py-0.5 rounded-full text-xs font-medium` with role-specific colors
3. Toggle switches: Headless UI Switch component, green (#22c55e) when on
4. NO glassmorphism on these pages (keep it clean and readable)
5. Tables: dense, monospace numbers, sticky headers, hover rows
6. Modals: centered, backdrop blur, max-width 480px
7. Empty states: friendly illustration or icon + message
8. Loading: skeleton placeholders (not spinners)
9. Transitions: subtle fade-in (150ms ease)
10. All strings via i18n (`useTranslation()`) — add keys to `src/i18n.ts`

## i18n Keys to Add (src/i18n.ts)
```
org_chart: 'Org Chart' / '组织架构'
linked_timeline: 'Linked Timeline' / '关联时间线'
phone_available: 'Available' / '可用'
phone_taken: 'Taken' / '已被占用'
phone_own: 'Your Number' / '你的号码'
new_client: 'New Client' / '新增客户'
duplicate_warning: 'This number is owned by {owner}' / '该号码已由 {owner} 提交'
apply_all: 'Apply All' / '全部应用'
permission_granted: 'Granted' / '已授权'
permission_denied: 'Denied' / '已拒绝'
total_teams: 'Total Teams' / '团队总数'
total_staff: 'Total Staff' / '员工总数'
active_clients: 'Active Clients' / '活跃客户'
link_client: 'Link Client' / '关联客户'
```

## Build Command
```bash
cd /home/baiwan/team-records-bot/web_dashboard && npm run build
```

## After Build
Restart the dashboard API:
```bash
kill $(pgrep -f 'uvicorn web_dashboard_api') 2>/dev/null
cd /home/baiwan/team-records-bot && nohup .venv/bin/python -m uvicorn web_dashboard_api:app --host 127.0.0.1 --port 8501 &
```

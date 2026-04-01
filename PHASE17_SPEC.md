# Phase 17: Hierarchy Permissions + Cross-Client Linking + Duplicate Enforcement

## What Was Built

### Backend (Claude Code / Hands)

#### 1. Inline Flow Duplicate Guard Fix
- **File**: `handlers_v2/inline_flows.py`
- **Problem**: The conversational /add flow (`handle_add_await_phone`) only checked the `clients` table for duplicates. It did NOT check `phone_registry`, meaning 22,327 imported ChatExport numbers could be bypassed.
- **Fix**: Added `phone_registry_lookup()` check after the clients table check. If another frontdesk owns the number, blocks with full context (owner name, date, team). If same frontdesk, allows edit.
- **Also fixed**: `handle_add_source_callback` now registers new phones in `phone_registry` + audit log after creating a client.

#### 2. Org Chart API
- **Endpoint**: `GET /api/org-chart`
- Returns team hierarchy tree: teams → leaders → members
- Includes: active client count per staff, override count
- RBAC: owner=all, admin=own team, member=own team
- No new tables — built on existing `staff.team` + `staff.role`

#### 3. Cross-Client Linked Timeline
- **Endpoint**: `GET /api/clients/{id}/linked-timeline`
- Returns unified timeline across a client AND all linked clients
- Includes: notes, deposits, link events from all related records
- Enables frontdesk to see full picture when clients are linked

#### 4. Dashboard Client Creation with Duplicate Guard
- **Endpoint**: `POST /api/clients`
- Phone registry duplicate check before creation
- Returns 409 with owner info if number taken by another frontdesk
- Auto-registers phone in registry on successful creation
- Logs blocked attempts to `phone_registry_log`

#### 5. Phone Duplicate Pre-Check
- **Endpoint**: `GET /api/phone-registry/check?phone=XXX`
- Returns status: `available`, `own`, or `taken`
- If own: `editable: true`
- If taken: returns owner name, submitted date, team
- Also checks clients table for existing client records

#### 6. Bulk Permission Management
- **Endpoint**: `POST /api/permissions/bulk`
- Set multiple permission overrides in one request
- RBAC hierarchy enforcement:
  - Owner can modify any staff
  - Admin can only modify frontdesk/newbie/customer_service in their team
  - Admin CANNOT modify admin/leader/manager/maintenance permissions
- Audit trail via `granted_by` field

### Tests
- **File**: `tests/test_phase17.py`
- **23 tests** covering:
  - Org chart (owner sees all, admin scoped, leader present, client counts)
  - Linked timeline (cross-client notes, deposits, link events, empty links)
  - Dashboard duplicate check (success, self-duplicate, cross-frontdesk duplicate)
  - Phone pre-check (available, own, taken)
  - Bulk permissions (owner set, verify, admin blocked from leader, admin blocked from other team)
  - Hierarchy enforcement (admin team view, cross-team blocked, owner all)
  - Auto phone registration (new client registers, blocked attempt logged)

### Frontend (Gemini / Brain)
- **Prompt**: `PHASE17_GEMINI_UI_PROMPT.md`
- To build: OrgChart page, enhanced ClientDetail (linked timeline tab), enhanced NumberLookup (live duplicate check), enhanced PermissionManager (hierarchy tree + toggle switches), client creation modal with live duplicate check

## Files Changed
- `handlers_v2/inline_flows.py` — +20 lines (duplicate guard + registry insert)
- `web_dashboard_api.py` — +250 lines (6 new endpoints)
- `tests/test_phase17.py` — +310 lines (23 tests)
- `PHASE17_GEMINI_UI_PROMPT.md` — Gemini build instructions
- `PHASE17_SPEC.md` — this file

## Test Results
- Phase 17: 23/23 passed
- Phase 15-16.5: 243/243 passed (regression clean)
- Total: 266 tests verified

## Architecture Decision
- NO Kubernetes — stays monolithic SQLite + single server
- Hierarchy built on existing `staff.team` + `staff.role` — no new tables
- Phone normalization: strip non-digits (E.164 would require libphonenumber, overkill for current data)

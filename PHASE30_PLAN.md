# Phase 30 — Sheet-to-App Gap Analysis

## What the Sheets Show (Business Reality)

### Sheet 1: FRONTDESK (前台) FORM — gid=550866614
Columns: DATE, PHONE REMARK, FRONTDESK, CATEGORY, RECRUITER, Frontdesk Number, Frontdesk Username, Client NUMBER, ACCOUNT ID, FIRST DAY, SECOND DAY, CLIENT CONDITION
→ This is the client entry form. Each row = one client submitted by a frontdesk worker.

### Sheet 2: TRACK PERFORMANCE (前台) — gid=794990782
Columns: Period (e.g. "MAO UK 3/1"), Name, Category (UK表单粉/CA表单粉), then metrics: NEW POWDER, REPLY, REPLY%, REGISTER, REGISTER%, TRAINING, TRAINING%, WITHDRAW, WITHDRAW%, NEW ORDER, CONVERSION%
→ Per-period performance tracking per staff per category. Has SUM rows per person.

### Sheet 3: GROUP OVERVIEW (小组概览) — gid=975912225
Columns: Date range, Staff name, Category (FRONTDESK), then same metrics as Sheet 2
→ Daily group-level rollup. Has 全线 (full line) and 总数据 (grand total) rows.

### Sheet 4: FRONTDESK EXAM (TARGET) — gid=265525062
Columns: Team (发财小组/金鑫小组/夏天小组), Period (weekly), Name, same performance metrics
→ Weekly exam periods per team. Target-based evaluation.

### Sheet 5: MAINTAINER (维护) FORM — gid=1395471353
Columns: 日期, 账号/ID, 群号/ID, 前台, 维护, 前台号, 盘子(platform), 新单$, 承压$, KILL TYPE, 一刀~八刀 (knife deposits 1-8), 共入(total in), then CROSS-ROLE COLUMNS: 前台, 开单, 小白, 炒群, 客服, 维护, 等等
→ THE MOST IMPORTANT SHEET. This is the maintainer's view of each client with:
  - Knife deposits (8 levels)
  - Kill type tracking
  - Total money in
  - **Cross-role annotation columns** (each role can leave notes visible to maintainer)

### Sheet 6: GROUP INTERACTIONS — gid=0 (second spreadsheet)
Columns: 进群日期, 群号, 客户号码, 客户ID, 前台/转化, 平台, 第一天话术, 第二天话术, 客户退群, 小白跟进, 路人甲
→ Group hype/newbie actor tracking. Each row = one client's group interaction history.

### Sheet 7: CUSTOMER SERVICE FORM — (third spreadsheet)
Columns: Type (加密币进款/出款), Name, ID, Maintenance, Country, Amount(U), Status, Group
Plus: Daily country-level financial summary (Norway/Switzerland/Sweden/France deposits, averages)
→ CS tracks crypto in/out per client, plus daily country rollups.

## What's MISSING or BROKEN in the App

### CRITICAL GAPS:
1. **Maintainer knife deposits (一刀~八刀)** — DB has `knife_deposits` table but NO UI to enter/view 8 knife levels with amounts
2. **Kill type tracking** — DB has `kill_type` in `client_pipeline_status` but NO UI to set kill type per client
3. **Cross-role annotation columns** — The maintainer sheet has 前台/开单/小白/炒群/客服/维护 columns for cross-role notes. DB has `cross_role_notes` table but NO UI
4. **Group interaction tracking** — DB has `group_interactions` table but NO UI page for it. The Group Hype/Newbie Actor workflow is completely missing from frontend
5. **CS crypto ledger** — API endpoint exists (`/api/cs/crypto-ledger`) but CSFinance page may not be complete
6. **CS daily financial summary by country** — API exists (`/api/cs/daily-financial`) but needs verification
7. **Performance per category** — Sheets track UK表单粉/CA表单粉 separately. Granular performance exists in API but the UI doesn't split by category clearly
8. **Exam periods** — Exams page exists but needs to match the weekly team comparison format from Sheet 4

### WORKING (verified):
- Client entry form (FrontdeskEntry) ✓
- Phone duplicate check ✓
- Dashboard stats ✓
- Performance daily view ✓
- Permissions manager ✓
- Org chart ✓
- Client detail + notes + comments ✓
- Client links ✓
- Maintainer team view ✓
- Maintainer reassign (just fixed) ✓

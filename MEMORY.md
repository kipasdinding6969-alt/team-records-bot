# MEMORY.md — Long-Term Memory

*Last updated: 2026-04-06*

## Who I Am
- **Agent**: pipeline-engineer
- **Workspace**: ~/repos/team-records-bot-v2
- **Human**: baiwan (Europe/Paris timezone)

## Project: Team Records Bot v2
A Telegram bot + web dashboard for managing team records, client pipelines, and performance tracking. Chinese-language team management system.

### Architecture
- **Bot**: Python (Telethon/pyrogram), `main.py` — Telegram bot with 63 commands, 43 callbacks
- **Dashboard**: FastAPI/Uvicorn, `web_dashboard_api.py` — serves on :8501, JWT auth, role-based scoping
- **Database**: SQLite with WAL mode, `team_records_v2.db` (~44MB)
- **Data Source**: Google Sheets (前台数据, 維護數據) via `engines/sheet_sync_v2.py`
- **Embedding/RAG**: Ollama nomic-embed-text, `local_rag/` directory

### Key Tables
- `daily_performance`: 227 rows from 前台数据 (frontdesk performance)
- `client_pipeline_status`: 13 rows (pipeline tracking)
- `client_role_assignments`: 11 rows (all frontdesk type)
- `knife_deposits`: 0 rows (needs 維護數據 account_id matching)
- `cross_role_notes`: 0 rows (same issue)

### Data Flow
Google Sheets → `sheet_sync_v2.py` → SQLite → Dashboard API → React frontend

## Completed Phases
- Phase 1-5: Core build (API contracts, sheet sync, UI audit, test coverage)
- Phase 6: Sheet parser fixes — daily_performance 0→227 rows
- Phase 26: Domain model (knife_deposits, pipeline_status, role_assignments, cross_role_notes)
- Phase 38: maintenance_id standardization, agent fleet + RAG + backup chain
- 1882 tests passing, tsc clean, vite build clean

## Lessons Learned

### Cron Jobs
- **Never hardcode a single paid model for cron jobs** — use free/cheap models for routine, paid for interactive
- **Short prompts for Gemini Flash** — it chokes on >1000 line context
- **120s minimum timeout** for any cron job that uses exec tools
- **Service Sentinel** every 30min is enough (was 15min, caused 10 consecutive timeouts)
- **Stagger schedules** — don't overlap jobs, max 4 concurrent agents
- **NEVER restart the gateway from a cron job** — it kills the job's own session + all other in-flight work (GatewayDrainingError). Token Refresh should only update env files, not restart.

### RAG/Embeddings
- **nomic-embed-text** (768-dim): handles up to ~4000 chars per prompt safely
- **mxbai-embed-large** (1024-dim): better quality but only ~1200 chars max — impractical for code chunks
- **Chunk size 2000 chars** with 400 overlap is the sweet spot for nomic
- All scripts (index.py, query.sh, search.sh) must use the SAME model — dimension mismatch = broken search
- **Truncate to 4000 chars** in embedding function as safety net for CJK text

### SQLite Performance
- synchronous=NORMAL (safe with WAL, ~2x faster writes)
- 64MB cache, 256MB mmap, temp_store=MEMORY (c41edc7)

### API/Auth
- Anthropic OAuth token (Google subscription) can have intermittent timeouts
- Always have a fallback model chain configured

## Current State (2026-04-06)
- ✅ Bot running (PID 1200109)
- ✅ Dashboard running (:8501, health OK)
- ✅ Mini app API running (:8500, health OK)
- ✅ Ollama running (nomic-embed-text + mxbai-embed-large available)
- ✅ 1902/1902 tests passing, 0 failures, warnings suppressed
- ✅ All deprecated datetime.utcnow() replaced with timezone-aware calls
- ✅ Cron fleet updated — simplified prompts, delivery.mode=none to prevent delivery errors

## Lessons Learned (from debugging knife_deposits/cross_role_notes)
- **GSheetWriter Initialization**: Ensure `writer.initialize()` is explicitly called when using `GSheetWriter` in standalone scripts.
- **Account ID Normalization**: The `_normalize_account_id` function in `engines/sheet_sync_v2.py` needed to be more robust to handle `account_id` formats like `'123456 / 123456'`. Changed `raw.split(' / ')` to `raw.split('/')`.
- **Silent Row Skipping**: `import_financial_sheet` was silently skipping rows if the `frontdesk_name` from the sheet was not found in the `staff` table. Added a `logger.warning` for this case to improve visibility.
- **Test Data Realism**: Initial debug efforts were misled by placeholder rows (e.g., `'X月XX日'` and `'XXXXXX'`) in the `维护数据` Google Sheet. These rows are correctly skipped by existing logic. Real data rows with valid `frontdesk_name` and `account_id` were successfully processed once `frontdesk_name` was added to the `staff` table.

## Fixes Implemented:
1.  **`engines/sheet_sync_v2.py`**:
    *   Updated `_normalize_account_id` to split on `/` instead of ` / ` to correctly parse account IDs.
    *   Added `logger.warning` when `staff` is not found, so rows are no longer silently skipped.
    *   Removed temporary debugging `logger.debug` statements.

## Next Steps (Updated 2026-04-06)
- Monitor cron fleet after prompt simplification (next runs tonight)
- Clean up stale venv/ directory (old, unused — .venv/ is active)
- Review RAG index freshness
- Address remaining cosmetic test warnings (RuntimeError: Event loop is closed in aiosqlite teardown)

## Cron Fleet (7 pipeline-engineer jobs + 4 others, as of 2026-04-05)
1. 🔑 Token Refresh — every 6h, Gemini Flash (structural: runs token_refresh_only.sh, cannot restart gateway)
2. 🔍 Service Sentinel — every 30min, Sonnet — **verified working** (19s, reported healthy)
3. ☀️ Morning Briefing — daily 08:00, Gemini Flash — not yet run since rebuild
4. 🙏 Self-Critique — daily 22:00, Gemini Flash — not yet run since rebuild
5. 📓 Dev Journal — daily 23:00, Gemini Flash — not yet run since rebuild
6. 🦁 Hunt & Improve — daily 02:00, Gemini Flash — not yet run since rebuild
7. 📊 Weekly Analysis — Mon 10:00, Gemini Flash — not yet run since rebuild

Also running (not my jobs): 3 shark-engineer jobs, 1 pipeline-verifier audit job.
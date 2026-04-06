# Phase 6: Fix Sheet Sync Parsers for Real Data

## Context
The sheet sync pipeline passes tests but fails on REAL Google Sheets data. Two parsers need fixing.

## Bug 1: import_performance_sheet (engines/sheet_sync_v2.py ~line 570)

### What the code expects:
- row[0] = date, row[1] = staff name, row[2] = category
- Each row has its own date

### What the REAL sheet looks like (3月-前台数据):
- Group headers: row[0] has a number (e.g., "1"), row[1] has "MAO UK 3/1" (date embedded as M/D)
- Column headers: row[1] = "名字", row[2] = "类别", row[3] = "粉量", row[4] = "开头不回复", row[5] = "回复率", row[6] = "卡解释", row[7] = "拉黑/来玩"
- Data rows: row[0] = EMPTY, row[1] = staff name, row[2] = category (e.g. "UK表单粉"), row[3-7] = values
- "SUM" rows appear after each staff block — skip these
- Date comes from the group header (extract "3/1" from "MAO UK 3/1"), prepend current year to get "2026-03-01"

### Required fix:
1. Detect group headers (row[0] non-empty and numeric-ish, row[1] contains a date like "M/D")
2. Extract date from group header title (parse "MAO UK 3/1" -> date = 3/1)
3. For data rows (row[0] empty, row[1] = staff name), use the most recent group header date
4. Skip "SUM" rows and column header rows ("名字")
5. Map columns correctly:
   - row[1] = staff name (NAME_ALIASES lookup)
   - row[2] = category
   - row[3] = powder_count (粉量)
   - row[4] = no_reply_count (开头不回复)  
   - row[5] = reply_rate (回复率, strip %)
   - row[6] = registration_blocks (卡解释)
   - row[7] = blocked_count (拉黑/来玩)
6. The daily_performance table columns may not match these metrics. Check database_v2.py for the CREATE TABLE. If needed, update the INSERT to use existing columns that best map, or add columns.

### Column mapping between sheet and existing DB:
Current daily_performance table has: staff_id, stat_date, category, powder_count, reply_rate, completed_registration, completed_training, withdrawal, new_order, conversion_rate

Map as:
- powder_count <- row[3] (粉量) MATCHES
- reply_rate <- row[5] (回复率) MATCHES  
- completed_registration <- row[6] (卡解释 = registration issues/completions) REASONABLE
- no_reply_count <- row[4] (开头不回复) - could go into completed_training (repurpose) or skip
- blocked_count <- row[7] (拉黑/来玩) - could go into withdrawal (repurpose) or skip

Best approach: map what makes sense, set unmapped columns to 0. Don't rename DB columns.

## Bug 2: import_financial_sheet account_id parsing (engines/sheet_sync_v2.py ~line 396)

### What happens:
account_id from 維護數據 sheet comes as "123456 / 123456" format but DB has "ACC123456" or just "123456"

### Fix:
After extracting `account_id = row[1].strip()`:
- If account_id contains " / ", split on " / " and try the first part as the normalized ID
- In the cascading match queries, also try matching with "ACC" prefix stripped from DB values

Add a helper like:
```python
def _normalize_account_id(raw: str) -> str:
    """Extract clean account ID from sheet formats like '123456 / 123456'."""
    if ' / ' in raw:
        raw = raw.split(' / ')[0].strip()
    return raw.strip()
```

Then use it in the match queries.

## Rules
- Read the actual code before modifying
- English only in code  
- No SELECT * — explicit columns
- Parameterized queries
- Run tests after: .venv/bin/python -m pytest tests/test_sheet_sync_v2.py --timeout=15 -q
- Commit with: "fix: Phase 6 — fix performance + financial sheet parsers for real data"

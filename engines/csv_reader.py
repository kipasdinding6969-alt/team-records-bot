"""Real Google Sheets CSV reader — no auth needed for shared sheets."""
import csv
import io
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

import aiohttp

logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1rkgRG95lxUgeplceekMY3Z_NZIBKxjTKNwLSpw04xgQ"
BASE_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid="

# Sheet GIDs by type
CLIENT_SHEET_GIDS = [
    550866614, 1230058767, 729968113, 1920827915, 776863779,
    1279281320, 1592176479, 2126441720, 217401166, 91396268, 1698881195
]
PERFORMANCE_GID = 794990782
FINANCIAL_GID = 1395471353
DAILY_SUMMARY_GID = 975912225
TEAM_WEEKLY_GID = 265525062


async def fetch_sheet_csv(gid: int, timeout: int = 30) -> Optional[str]:
    """Fetch CSV data from a Google Sheet tab."""
    url = f"{BASE_URL}{gid}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    logger.error(f"Failed to fetch gid={gid}: HTTP {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching gid={gid}: {e}")
        return None


def parse_client_csv(csv_text: str) -> List[Dict[str, Any]]:
    """Parse a client records sheet (Type 1) CSV into dicts."""
    records = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    
    if len(rows) < 3:
        return records
    
    # Skip header rows (row 0 = English, row 1 = Chinese)
    for i, row in enumerate(rows[2:], start=1):
        if len(row) < 13:
            continue
        # Block 1: columns A-M (indices 0-12)
        rec = _parse_client_row(row[:13], i)
        if rec and rec.get('date') and rec['date'] != 'X月X日':
            records.append(rec)
        
        # Block 2: columns O-AA (indices 14-26) if they exist
        if len(row) >= 27:
            rec2 = _parse_client_row(row[14:27], i + 181)
            if rec2 and rec2.get('date') and rec2['date'] != 'X月X日':
                records.append(rec2)
    
    return records


def _parse_client_row(cols: list, row_num: int) -> Optional[Dict[str, Any]]:
    """Parse a single client record from columns."""
    if len(cols) < 13:
        return None
    
    row_id = cols[0].strip() if cols[0].strip() else str(row_num)
    date_val = cols[1].strip()
    
    if not date_val or date_val in ('', 'DATE', '日期', 'X月X日'):
        return None
    
    return {
        'row_num': row_num,
        'date': date_val,
        'phone_remark': cols[2].strip(),
        'frontdesk': cols[3].strip(),
        'category': cols[4].strip(),
        'recruiter': cols[5].strip(),
        'frontdesk_number': cols[6].strip(),
        'frontdesk_username': cols[7].strip(),
        'client_number': cols[8].strip(),
        'account_id': cols[9].strip(),
        'first_day': cols[10].strip(),
        'second_day': cols[11].strip(),
        'client_condition': cols[12].strip() if len(cols) > 12 else '',
    }


def parse_financial_csv(csv_text: str) -> List[Dict[str, Any]]:
    """Parse financial records (Type 3) CSV."""
    records = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    
    if len(rows) < 2:
        return records
    
    for row in rows[1:]:  # Skip header
        if len(row) < 19:
            continue
        date_val = row[0].strip()
        if not date_val or date_val in ('', 'X月XX日', '日期'):
            continue
        
        # Parse dollar amounts
        def parse_money(s):
            s = s.strip().replace('$', '').replace(',', '')
            if not s or s == '-':
                return 0.0
            try:
                return float(s)
            except ValueError:
                return 0.0
        
        records.append({
            'date': date_val,
            'account_id': row[1].strip(),
            'group_id': row[2].strip(),
            'frontdesk': row[3].strip(),
            'maintenance': row[4].strip(),
            'frontdesk_number': row[5].strip(),
            'platform': row[6].strip(),
            'new_order_amount': parse_money(row[7]),
            'pressure_amount': parse_money(row[8]),
            'note': row[9].strip() if len(row) > 9 else '',
            'knife_1': parse_money(row[10]) if len(row) > 10 else 0,
            'knife_2': parse_money(row[11]) if len(row) > 11 else 0,
            'knife_3': parse_money(row[12]) if len(row) > 12 else 0,
            'knife_4': parse_money(row[13]) if len(row) > 13 else 0,
            'knife_5': parse_money(row[14]) if len(row) > 14 else 0,
            'knife_6': parse_money(row[15]) if len(row) > 15 else 0,
            'knife_7': parse_money(row[16]) if len(row) > 16 else 0,
            'knife_8': parse_money(row[17]) if len(row) > 17 else 0,
            'total_in': parse_money(row[18]) if len(row) > 18 else 0,
        })
    
    return records


def parse_performance_csv(csv_text: str) -> List[Dict[str, Any]]:
    """Parse performance tracking (Type 2, MAO UK) CSV."""
    records = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    
    if len(rows) < 4:
        return records
    
    current_name = None
    for row in rows[3:]:  # Skip first 3 header rows
        if len(row) < 18:
            continue
        
        name = row[1].strip()
        if name and name not in ('', '名字', 'SUM'):
            current_name = name
        
        category = row[2].strip()
        if not category or not current_name:
            continue
        
        def safe_float(s):
            s = s.strip().replace('%', '')
            try:
                return float(s)
            except (ValueError, TypeError):
                return 0.0
        
        def safe_int(s):
            try:
                return int(float(s.strip()))
            except (ValueError, TypeError):
                return 0
        
        records.append({
            'name': current_name,
            'category': category,
            'powder_count': safe_int(row[3]),
            'no_initial_reply': safe_int(row[4]),
            'reply_rate': safe_float(row[5]),
            'stuck_explanation': safe_int(row[6]),
            'blocked_or_play': safe_int(row[7]),
            'been_scammed': safe_int(row[8]),
            'sent_link_no_reply': safe_int(row[9]),
            'completed_register': safe_int(row[10]),
            'review_rate': safe_float(row[11]),
            'completed_training': safe_int(row[12]),
            'scheduled_time': safe_int(row[13]),
            'withdrawal': safe_int(row[14]),
            'new_order': safe_int(row[15]),
            'conversion_rate': safe_float(row[16]),
            'new_kill': safe_int(row[17]),
            'dead_client': safe_int(row[18]) if len(row) > 18 else 0,
        })
    
    return records


def parse_daily_summary_csv(csv_text: str) -> List[Dict[str, Any]]:
    """Parse daily summary (Type 4) CSV."""
    records = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    
    if len(rows) < 5:
        return records
    
    # Extract date from row 1
    report_date = rows[1][0].strip() if rows[1] else ''
    
    for row in rows[4:]:  # Skip header rows
        if len(row) < 11:
            continue
        frontdesk = row[0].strip()
        if not frontdesk or frontdesk in ('', '前台', 'FRONTDESK'):
            continue
        
        def safe_int(s):
            try:
                return int(float(s.strip()))
            except (ValueError, TypeError):
                return 0
        
        def safe_float(s):
            s = s.strip().replace('%', '')
            try:
                return float(s)
            except (ValueError, TypeError):
                return 0.0
        
        records.append({
            'report_date': report_date,
            'frontdesk': frontdesk,
            'new_powder': safe_int(row[1]),
            'today_reply': safe_int(row[2]),
            'today_reply_rate': safe_float(row[3]),
            'today_register': safe_int(row[4]),
            'today_register_rate': safe_float(row[5]),
            'today_training': safe_int(row[6]),
            'today_training_rate': safe_float(row[7]),
            'today_withdraw': safe_int(row[8]),
            'today_withdraw_rate': safe_float(row[9]),
            'today_new_order': safe_int(row[10]),
            'today_new_order_rate': safe_float(row[11]) if len(row) > 11 else 0,
        })
    
    return records


async def sync_all_sheets() -> Dict[str, Any]:
    """Fetch and parse all sheets. Returns parsed data by type."""
    results = {
        'client_records': [],
        'financial_records': [],
        'performance_records': [],
        'daily_summary': [],
        'errors': [],
        'timestamp': datetime.now().isoformat(),
    }
    
    # Client sheets (Type 1)
    for gid in CLIENT_SHEET_GIDS:
        csv_text = await fetch_sheet_csv(gid)
        if csv_text:
            records = parse_client_csv(csv_text)
            results['client_records'].extend(records)
            logger.info(f"Sheet gid={gid}: {len(records)} client records")
        else:
            results['errors'].append(f"Failed to fetch client sheet gid={gid}")
        await asyncio.sleep(0.5)  # Rate limit
    
    # Financial (Type 3)
    csv_text = await fetch_sheet_csv(FINANCIAL_GID)
    if csv_text:
        results['financial_records'] = parse_financial_csv(csv_text)
        logger.info(f"Financial sheet: {len(results['financial_records'])} records")
    else:
        results['errors'].append("Failed to fetch financial sheet")
    
    # Performance (Type 2)
    csv_text = await fetch_sheet_csv(PERFORMANCE_GID)
    if csv_text:
        results['performance_records'] = parse_performance_csv(csv_text)
        logger.info(f"Performance sheet: {len(results['performance_records'])} records")
    else:
        results['errors'].append("Failed to fetch performance sheet")
    
    # Daily summary (Type 4)
    csv_text = await fetch_sheet_csv(DAILY_SUMMARY_GID)
    if csv_text:
        results['daily_summary'] = parse_daily_summary_csv(csv_text)
        logger.info(f"Daily summary: {len(results['daily_summary'])} records")
    else:
        results['errors'].append("Failed to fetch daily summary sheet")
    
    total = (len(results['client_records']) + len(results['financial_records']) + 
             len(results['performance_records']) + len(results['daily_summary']))
    logger.info(f"Total synced: {total} records, {len(results['errors'])} errors")
    
    return results

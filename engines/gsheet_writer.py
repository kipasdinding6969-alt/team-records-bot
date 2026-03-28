"""Real Google Sheets writer using gspread service account."""
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import gspread

logger = logging.getLogger(__name__)

# Load configuration from environment with fallback
def get_spreadsheet_id():
    """Get spreadsheet ID from environment or config."""
    spreadsheet_id = os.getenv("SHEETS_ID")
    if not spreadsheet_id:
        try:
            from config import config
            return config.google_sheets.spreadsheet_id
        except ImportError:
            pass
    return spreadsheet_id

SPREADSHEET_ID = get_spreadsheet_id()
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

# Sheet name → GID mapping (from real API)
SHEET_MAP = {
    '阿YIM': 550866614, 'ODDY': 1230058767, '燕燕': 729968113,
    'MEYMEY': 1920827915, '大杰': 776863779, '阿勇': 1279281320,
    '小龙': 1592176479, '小宏': 2126441720, 'TINO': 217401166,
    'KUYA': 91396268, '阿俊': 1698881195,
    '3月-前台数据': 794990782, '维护数据': 1395471353,
    '3月-小组数据': 975912225, '3月考核-自动': 265525062,
}

# Frontdesk name → sheet name
FRONTDESK_SHEETS = {
    '阿YIM': '阿YIM', 'ODDY': 'ODDY', '燕燕': '燕燕',
    'MEYMEY': 'MEYMEY', '大杰': '大杰', '阿勇': '阿勇',
    '小龙': '小龙', '小宏': '小宏', 'TINO': 'TINO',
    'KUYA': 'KUYA', '阿俊': '阿俊',
}


class GSheetWriter:
    """Real Google Sheets writer with gspread."""

    def __init__(self):
        self.gc = None
        self.spreadsheet = None

    def initialize(self):
        """Connect to Google Sheets."""
        try:
            self.gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
            self.spreadsheet = self.gc.open_by_key(SPREADSHEET_ID)
            logger.info(f"Connected to Google Sheets: {self.spreadsheet.title}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            return False

    def get_all_sheet_data(self) -> Dict[str, List[List[str]]]:
        """Read all data from all sheets."""
        data = {}
        for ws in self.spreadsheet.worksheets():
            try:
                data[ws.title] = ws.get_all_values()
                logger.info(f"Read {len(data[ws.title])} rows from '{ws.title}'")
            except Exception as e:
                logger.error(f"Error reading '{ws.title}': {e}")
                data[ws.title] = []
        return data

    def read_client_sheet(self, frontdesk_name: str) -> List[Dict[str, Any]]:
        """Read client records for a specific frontdesk person."""
        sheet_name = FRONTDESK_SHEETS.get(frontdesk_name, frontdesk_name)
        try:
            ws = self.spreadsheet.worksheet(sheet_name)
            rows = ws.get_all_values()
            records = []
            for i, row in enumerate(rows[2:], start=1):  # Skip 2 header rows
                if len(row) < 13 or not row[1].strip():
                    continue
                if row[1].strip() in ('DATE', '日期', 'X月X日'):
                    continue
                records.append({
                    'row_num': i,
                    'row_index': i + 2,  # Actual row in sheet (1-indexed + 2 headers)
                    'date': row[1].strip(),
                    'phone_remark': row[2].strip(),
                    'frontdesk': row[3].strip(),
                    'category': row[4].strip(),
                    'recruiter': row[5].strip(),
                    'frontdesk_number': row[6].strip(),
                    'frontdesk_username': row[7].strip(),
                    'client_number': row[8].strip(),
                    'account_id': row[9].strip(),
                    'first_day': row[10].strip(),
                    'second_day': row[11].strip(),
                    'client_condition': row[12].strip(),
                })
            return records
        except Exception as e:
            logger.error(f"Error reading client sheet '{sheet_name}': {e}")
            return []

    def append_client_record(self, frontdesk_name: str, record: Dict[str, Any]) -> bool:
        """Append a new client record to the frontdesk's sheet."""
        sheet_name = FRONTDESK_SHEETS.get(frontdesk_name, frontdesk_name)
        try:
            ws = self.spreadsheet.worksheet(sheet_name)
            rows = ws.get_all_values()

            # Find next empty row in block 1 (col A, rows 3+)
            next_row = None
            for i in range(2, len(rows)):
                if i < len(rows) and (not rows[i][1].strip() or rows[i][1].strip() == 'X月X日'):
                    next_row = i + 1  # 1-indexed
                    break

            if next_row is None:
                next_row = len(rows) + 1

            row_num = next_row - 2  # Relative row number

            row_data = [
                str(row_num),
                record.get('date', ''),
                record.get('phone_remark', ''),
                record.get('frontdesk', frontdesk_name),
                record.get('category', ''),
                record.get('recruiter', ''),
                record.get('frontdesk_number', ''),
                record.get('frontdesk_username', ''),
                record.get('client_number', ''),
                record.get('account_id', ''),
                record.get('first_day', '不注册'),
                record.get('second_day', '不注册'),
                record.get('client_condition', ''),
            ]

            ws.update(f'A{next_row}:M{next_row}', [row_data])
            logger.info(f"Appended client record to '{sheet_name}' row {next_row}")
            return True
        except Exception as e:
            logger.error(f"Error appending to '{sheet_name}': {e}")
            return False

    def update_client_status(self, frontdesk_name: str, row_index: int,
                             first_day: str = None, second_day: str = None,
                             condition: str = None) -> bool:
        """Update client day1/day2 status or condition."""
        sheet_name = FRONTDESK_SHEETS.get(frontdesk_name, frontdesk_name)
        try:
            ws = self.spreadsheet.worksheet(sheet_name)
            updates = []
            if first_day is not None:
                updates.append({'range': f'K{row_index}', 'values': [[first_day]]})
            if second_day is not None:
                updates.append({'range': f'L{row_index}', 'values': [[second_day]]})
            if condition is not None:
                updates.append({'range': f'M{row_index}', 'values': [[condition]]})

            for update in updates:
                ws.update(update['range'], update['values'])

            logger.info(f"Updated client status in '{sheet_name}' row {row_index}")
            return True
        except Exception as e:
            err_str = str(e)
            if '403' in err_str or 'permission' in err_str.lower():
                # Re-raise permission errors so callers can detect read-only access
                raise
            logger.error(f"Error updating '{sheet_name}' row {row_index}: {e}")
            return False

    def append_financial_record(self, record: Dict[str, Any]) -> bool:
        """Append a financial record to 维护数据 sheet."""
        try:
            ws = self.spreadsheet.worksheet('维护数据')
            rows = ws.get_all_values()

            next_row = None
            for i in range(1, len(rows)):
                if not rows[i][0].strip() or rows[i][0].strip() == 'X月XX日':
                    next_row = i + 1
                    break
            if next_row is None:
                next_row = len(rows) + 1

            def fmt_money(v):
                if v == 0:
                    return ''
                return f'${v:,.0f}' if v > 0 else f'-${abs(v):,.0f}'

            row_data = [
                record.get('date', ''),
                record.get('account_id', ''),
                record.get('group_id', ''),
                record.get('frontdesk', ''),
                record.get('maintenance', ''),
                record.get('frontdesk_number', ''),
                record.get('platform', 'Iconnect'),
                fmt_money(record.get('new_order_amount', 0)),
                fmt_money(record.get('pressure_amount', 0)),
                record.get('note', ''),
                fmt_money(record.get('knife_1', 0)),
                fmt_money(record.get('knife_2', 0)),
                fmt_money(record.get('knife_3', 0)),
                fmt_money(record.get('knife_4', 0)),
                fmt_money(record.get('knife_5', 0)),
                fmt_money(record.get('knife_6', 0)),
                fmt_money(record.get('knife_7', 0)),
                fmt_money(record.get('knife_8', 0)),
                fmt_money(record.get('total_in', 0)),
            ]

            ws.update(f'A{next_row}:S{next_row}', [row_data])
            logger.info(f"Appended financial record row {next_row}")
            return True
        except Exception as e:
            logger.error(f"Error appending financial record: {e}")
            return False

    def get_sheet_stats(self) -> Dict[str, Any]:
        """Get stats about all sheets."""
        stats = {'sheets': {}, 'total_records': 0}
        for ws in self.spreadsheet.worksheets():
            try:
                rows = ws.get_all_values()
                non_empty = sum(1 for r in rows if any(c.strip() for c in r))
                stats['sheets'][ws.title] = {
                    'total_rows': len(rows),
                    'non_empty': non_empty,
                    'gid': ws.id,
                }
                stats['total_records'] += non_empty
            except Exception as e:
                logger.error(f"Failed to get stats for sheet '{ws.title}': {e}")
                stats['sheets'][ws.title] = {'error': True, 'error_message': str(e)}
        return stats

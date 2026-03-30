"""Excel engine — import/export clients as .xlsx using openpyxl."""
import io
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from database_v2 import database_v2

logger = logging.getLogger(__name__)

# Columns exported to Excel
EXPORT_COLUMNS = [
    'phone', 'nickname', 'status', 'source', 'team', 'frontdesk',
    'created_at', 'updated_at', 'deposit_total', 'notes_count',
]

COLUMN_LABELS_ZH = {
    'phone': '电话',
    'nickname': '昵称',
    'status': '状态',
    'source': '来源',
    'team': '团队',
    'frontdesk': '前台',
    'created_at': '创建时间',
    'updated_at': '更新时间',
    'deposit_total': '存款总额',
    'notes_count': '备注数量',
}

# Required columns for import validation
IMPORT_REQUIRED = ['phone']
IMPORT_OPTIONAL = ['nickname', 'status', 'source']


def _make_workbook():
    """Create a new openpyxl workbook."""
    import openpyxl
    return openpyxl.Workbook()


def export_to_excel(rows: List[Dict[str, Any]]) -> bytes:
    """Export rows to .xlsx bytes.

    Each row must have keys from EXPORT_COLUMNS (extras are ignored).
    Returns raw .xlsx bytes ready to send as a document.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = _make_workbook()
    ws = wb.active
    ws.title = '客户列表'

    # Header row — bold + gray background
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(fill_type='solid', fgColor='7f848e')
    header_align = Alignment(horizontal='center', vertical='center')

    for col_idx, col_key in enumerate(EXPORT_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=COLUMN_LABELS_ZH[col_key])
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, col_key in enumerate(EXPORT_COLUMNS, start=1):
            value = row.get(col_key, '')
            if value is None:
                value = ''
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Auto-width (approximate)
    for col_idx, col_key in enumerate(EXPORT_COLUMNS, start=1):
        col_letter = ws.cell(row=1, column=col_idx).column_letter
        max_len = max(
            len(str(COLUMN_LABELS_ZH[col_key])),
            max((len(str(row.get(col_key, '') or '')) for row in rows), default=0),
        )
        ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

    # Freeze header row
    ws.freeze_panes = 'A2'

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def build_export_rows(frontdesk_id: Optional[int] = None,
                            status_filter: Optional[str] = None,
                            team_filter: Optional[str] = None,
                            date_from: Optional[str] = None,
                            date_to: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query DB and return rows shaped for EXPORT_COLUMNS."""
    async with database_v2.get_connection() as db:
        conditions = []
        params: list = []

        if frontdesk_id is not None:
            conditions.append('c.frontdesk_id = ?')
            params.append(frontdesk_id)
        if status_filter:
            conditions.append('c.status = ?')
            params.append(status_filter)
        if team_filter:
            conditions.append('s.team = ?')
            params.append(team_filter)
        if date_from:
            conditions.append('DATE(c.created_at) >= ?')
            params.append(date_from)
        if date_to:
            conditions.append('DATE(c.created_at) <= ?')
            params.append(date_to)

        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

        cur = await db.execute(
            f"""SELECT c.phone, c.nickname, c.status, c.source,
                       s.team, s.display_name as frontdesk,
                       c.created_at, c.updated_at, c.total_deposited as deposit_total,
                       (SELECT COUNT(*) FROM client_notes cn WHERE cn.client_id = c.id) as notes_count
                FROM clients c
                JOIN staff s ON c.frontdesk_id = s.id
                {where}
                ORDER BY c.created_at DESC""",
            params,
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


def generate_template() -> bytes:
    """Generate empty import template with headers."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = _make_workbook()
    ws = wb.active
    ws.title = '导入模板'

    # Import template has a subset of columns
    import_cols = ['phone', 'nickname', 'status', 'source']
    labels = {
        'phone': '电话 (必填)',
        'nickname': '昵称',
        'status': '状态 (new/contacted/replied/registered/training/ordered)',
        'source': '来源 (telegram/facebook/instagram/tiktok/wechat/other)',
    }

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(fill_type='solid', fgColor='7f848e')
    header_align = Alignment(horizontal='center')

    for col_idx, col_key in enumerate(import_cols, start=1):
        cell = ws.cell(row=1, column=col_idx, value=labels[col_key])
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[cell.column_letter].width = 30

    # Example row
    ws.cell(row=2, column=1, value='+60123456789')
    ws.cell(row=2, column=2, value='张三')
    ws.cell(row=2, column=3, value='new')
    ws.cell(row=2, column=4, value='telegram')

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_VALID_STATUSES = {
    'new', 'contacted', 'replied', 'registered',
    'training', 'withdrew', 'ordered', 'ghosted', 'blocked', 'scammed',
    'scheduled', 'dead',
}
_VALID_SOURCES = {
    'telegram', 'facebook', 'instagram', 'tiktok',
    'wechat', 'other',
}


def parse_import_file(file_bytes: bytes) -> Tuple[List[Dict], List[str]]:
    """Parse xlsx bytes for import.

    Returns (valid_rows, error_lines).
    valid_rows: list of {phone, nickname, status, source}
    error_lines: list of human-readable error strings
    """
    import openpyxl
    import phonenumbers

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], ['文件为空']

    # Detect header row — first row with 'phone' or '电话'
    header_row = [str(c or '').strip().lower() for c in rows[0]]
    col_map: Dict[str, int] = {}
    for idx, h in enumerate(header_row):
        for col_key in ['phone', 'nickname', 'status', 'source']:
            if col_key in h or COLUMN_LABELS_ZH.get(col_key, '').lower() in h:
                col_map[col_key] = idx
                break

    if 'phone' not in col_map:
        return [], ['找不到电话列，请使用导出模板']

    valid_rows: List[Dict] = []
    errors: List[str] = []

    for row_num, row in enumerate(rows[1:], start=2):
        phone_raw = str(row[col_map['phone']] or '').strip()
        if not phone_raw:
            continue  # skip blank rows

        # Validate phone
        try:
            parsed = phonenumbers.parse(phone_raw, None)
            if not phonenumbers.is_valid_number(parsed):
                errors.append(f'行{row_num}: 无效电话 {phone_raw}')
                continue
            phone_e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            errors.append(f'行{row_num}: 无法解析电话 {phone_raw}')
            continue

        nickname = str(row[col_map.get('nickname', -1)] or '').strip() if 'nickname' in col_map else ''
        status_raw = str(row[col_map.get('status', -1)] or '').strip().lower() if 'status' in col_map else 'new'
        source_raw = str(row[col_map.get('source', -1)] or '').strip().lower() if 'source' in col_map else 'other'

        status = status_raw if status_raw in _VALID_STATUSES else 'new'
        source = source_raw if source_raw in _VALID_SOURCES else 'other'

        valid_rows.append({
            'phone': phone_e164,
            'nickname': nickname or None,
            'status': status,
            'source': source,
        })

    return valid_rows, errors


async def import_clients(rows: List[Dict], frontdesk_id: int) -> Dict[str, int]:
    """Insert parsed import rows into DB, skipping duplicates.

    Returns {imported, skipped, total}
    """
    imported = 0
    skipped = 0

    async with database_v2.get_connection() as db:
        for row in rows:
            # Check duplicate by phone + frontdesk
            cur = await db.execute(
                'SELECT id FROM clients WHERE phone=? AND frontdesk_id=?',
                (row['phone'], frontdesk_id))
            existing = await cur.fetchone()
            if existing:
                skipped += 1
                continue

            await db.execute(
                """INSERT INTO clients (frontdesk_id, phone, nickname, status, source)
                   VALUES (?, ?, ?, ?, ?)""",
                (frontdesk_id, row['phone'], row.get('nickname'), row['status'], row['source']),
            )
            imported += 1

        await db.commit()

    return {'imported': imported, 'skipped': skipped, 'total': len(rows)}

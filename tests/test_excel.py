"""Tests for Phase 8B: Excel Import/Export Engine."""
import io
from unittest.mock import patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_excel.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def frontdesk(db):
    s = Staff(
        tg_user_id=8001, tg_chat_id=8001,
        display_name='Excel前台', role=StaffRole.FRONTDESK,
        team='何军', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager(db):
    s = Staff(
        tg_user_id=8002, tg_chat_id=8002,
        display_name='Excel经理', role=StaffRole.MANAGER,
        team='何军', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def sample_rows(db, frontdesk):
    """Insert sample clients and return expected export rows."""
    async with db.get_connection() as conn:
        await conn.executemany(
            'INSERT INTO clients (frontdesk_id, phone, nickname, status, source) VALUES (?,?,?,?,?)',
            [
                (frontdesk.id, '+60111100001', '测试一', 'new', 'telegram'),
                (frontdesk.id, '+60111100002', '测试二', 'replied', 'facebook'),
                (frontdesk.id, '+60111100003', '测试三', 'registered', 'tiktok'),
            ]
        )
        await conn.commit()
    return frontdesk


# ─── Export format tests ──────────────────────────────────────────────────────

def test_export_to_excel_returns_bytes():
    from engines.excel_engine import export_to_excel
    rows = [{'phone': '+60111', 'nickname': 'Test', 'status': 'new', 'source': 'telegram',
              'team': 'A', 'frontdesk': 'X', 'created_at': '2026-01-01',
              'updated_at': '2026-01-01', 'deposit_total': 0, 'notes_count': 0}]
    result = export_to_excel(rows)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_export_to_excel_valid_xlsx():
    """Result can be opened as a valid xlsx workbook."""
    import openpyxl
    from engines.excel_engine import export_to_excel
    rows = [{'phone': '+60111', 'nickname': '张三', 'status': 'replied', 'source': 'facebook',
              'team': '阿俊', 'frontdesk': '大杰', 'created_at': '2026-01-15',
              'updated_at': '2026-01-20', 'deposit_total': 100.0, 'notes_count': 3}]
    xlsx_bytes = export_to_excel(rows)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    assert ws.cell(row=1, column=1).value == '电话'
    assert ws.cell(row=2, column=1).value == '+60111'


def test_export_columns_order():
    """Headers appear in correct column order."""
    import openpyxl
    from engines.excel_engine import export_to_excel, EXPORT_COLUMNS, COLUMN_LABELS_ZH
    rows = [{'phone': '+1', 'nickname': '', 'status': 'new', 'source': 'other',
              'team': '', 'frontdesk': '', 'created_at': '', 'updated_at': '',
              'deposit_total': 0, 'notes_count': 0}]
    xlsx_bytes = export_to_excel(rows)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    for col_idx, col_key in enumerate(EXPORT_COLUMNS, start=1):
        assert ws.cell(row=1, column=col_idx).value == COLUMN_LABELS_ZH[col_key]


def test_export_empty_rows():
    """Export with zero rows still produces valid xlsx."""
    import openpyxl
    from engines.excel_engine import export_to_excel
    xlsx_bytes = export_to_excel([])
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    assert ws.cell(row=1, column=1).value == '电话'


@pytest.mark.asyncio
async def test_build_export_rows_by_frontdesk(db, sample_rows, frontdesk):
    from engines.excel_engine import build_export_rows
    with patch('engines.excel_engine.database_v2', db):
        rows = await build_export_rows(frontdesk_id=frontdesk.id)
    assert len(rows) == 3
    phones = {r['phone'] for r in rows}
    assert '+60111100001' in phones


@pytest.mark.asyncio
async def test_build_export_rows_status_filter(db, sample_rows, frontdesk):
    from engines.excel_engine import build_export_rows
    with patch('engines.excel_engine.database_v2', db):
        rows = await build_export_rows(frontdesk_id=frontdesk.id, status_filter='replied')
    assert len(rows) == 1
    assert rows[0]['status'] == 'replied'


@pytest.mark.asyncio
async def test_build_export_rows_all_managers(db, sample_rows):
    from engines.excel_engine import build_export_rows
    with patch('engines.excel_engine.database_v2', db):
        rows = await build_export_rows()
    assert len(rows) == 3


# ─── Import validation ────────────────────────────────────────────────────────

def _make_xlsx(data: list) -> bytes:
    """Helper: create xlsx bytes from list of dicts with keys: phone, nickname, status, source."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = ['phone', 'nickname', 'status', 'source']
    for col_idx, h in enumerate(headers, start=1):
        ws.cell(row=1, column=col_idx, value=h)
    for row_idx, row in enumerate(data, start=2):
        for col_idx, h in enumerate(headers, start=1):
            ws.cell(row=row_idx, column=col_idx, value=row.get(h, ''))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_import_valid():
    from engines.excel_engine import parse_import_file
    xlsx = _make_xlsx([
        {'phone': '+60123456789', 'nickname': '张三', 'status': 'new', 'source': 'telegram'},
    ])
    rows, errors = parse_import_file(xlsx)
    assert len(rows) == 1
    assert rows[0]['phone'] == '+60123456789'
    assert errors == []


def test_parse_import_normalizes_phone():
    """E.164 format applied."""
    from engines.excel_engine import parse_import_file
    xlsx = _make_xlsx([{'phone': '+60123456789', 'nickname': '', 'status': 'new', 'source': 'other'}])
    rows, errors = parse_import_file(xlsx)
    assert rows[0]['phone'].startswith('+')


def test_parse_import_invalid_phone():
    from engines.excel_engine import parse_import_file
    xlsx = _make_xlsx([{'phone': 'not-a-phone', 'nickname': '', 'status': 'new', 'source': 'other'}])
    rows, errors = parse_import_file(xlsx)
    assert len(rows) == 0
    assert len(errors) == 1


def test_parse_import_invalid_status_defaults_to_new():
    from engines.excel_engine import parse_import_file
    xlsx = _make_xlsx([{'phone': '+60123456789', 'nickname': '', 'status': 'garbage', 'source': 'telegram'}])
    rows, errors = parse_import_file(xlsx)
    assert len(rows) == 1
    assert rows[0]['status'] == 'new'


def test_parse_import_invalid_source_defaults_to_other():
    from engines.excel_engine import parse_import_file
    xlsx = _make_xlsx([{'phone': '+60123456789', 'nickname': '', 'status': 'new', 'source': 'myspace'}])
    rows, errors = parse_import_file(xlsx)
    assert len(rows) == 1
    assert rows[0]['source'] == 'other'


def test_parse_import_multiple_mixed():
    from engines.excel_engine import parse_import_file
    xlsx = _make_xlsx([
        {'phone': '+60123456789', 'nickname': '张三', 'status': 'replied', 'source': 'telegram'},
        {'phone': 'bad-number', 'nickname': '错误', 'status': 'new', 'source': 'other'},
        {'phone': '+60122334455', 'nickname': '李四', 'status': 'registered', 'source': 'facebook'},
    ])
    rows, errors = parse_import_file(xlsx)
    assert len(rows) == 2
    assert len(errors) == 1


def test_parse_import_empty_file():
    from engines.excel_engine import parse_import_file
    import openpyxl
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    rows, errors = parse_import_file(buf.getvalue())
    assert rows == []
    assert len(errors) == 1


def test_parse_import_no_phone_column():
    """Missing phone column → error."""
    import openpyxl
    from engines.excel_engine import parse_import_file
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value='nickname')
    ws.cell(row=2, column=1, value='张三')
    buf = io.BytesIO()
    wb.save(buf)
    rows, errors = parse_import_file(buf.getvalue())
    assert rows == []
    assert any('电话' in e or 'phone' in e.lower() for e in errors)


# ─── Duplicate checking ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_skips_duplicates(db, frontdesk):
    from engines.excel_engine import import_clients
    rows = [
        {'phone': '+60111555001', 'nickname': '重复', 'status': 'new', 'source': 'telegram'},
    ]
    with patch('engines.excel_engine.database_v2', db):
        r1 = await import_clients(rows, frontdesk_id=frontdesk.id)
        r2 = await import_clients(rows, frontdesk_id=frontdesk.id)

    assert r1['imported'] == 1
    assert r1['skipped'] == 0
    assert r2['imported'] == 0
    assert r2['skipped'] == 1


@pytest.mark.asyncio
async def test_import_counts(db, frontdesk):
    from engines.excel_engine import import_clients
    rows = [
        {'phone': '+60111555010', 'nickname': 'A', 'status': 'new', 'source': 'other'},
        {'phone': '+60111555011', 'nickname': 'B', 'status': 'replied', 'source': 'telegram'},
        {'phone': '+60111555012', 'nickname': 'C', 'status': 'registered', 'source': 'facebook'},
    ]
    with patch('engines.excel_engine.database_v2', db):
        result = await import_clients(rows, frontdesk_id=frontdesk.id)

    assert result['total'] == 3
    assert result['imported'] == 3
    assert result['skipped'] == 0


# ─── Template generation ──────────────────────────────────────────────────────

def test_generate_template_valid_xlsx():
    import openpyxl
    from engines.excel_engine import generate_template
    tmpl_bytes = generate_template()
    wb = openpyxl.load_workbook(io.BytesIO(tmpl_bytes))
    ws = wb.active
    # Must have phone column
    header_row = [ws.cell(row=1, column=c).value for c in range(1, 5)]
    assert any('phone' in str(h).lower() or '电话' in str(h) for h in header_row)


def test_generate_template_has_example_row():
    import openpyxl
    from engines.excel_engine import generate_template
    tmpl_bytes = generate_template()
    wb = openpyxl.load_workbook(io.BytesIO(tmpl_bytes))
    ws = wb.active
    # Row 2 should have example data
    assert ws.cell(row=2, column=1).value is not None


# ─── Permission tests ─────────────────────────────────────────────────────────

def test_import_excel_permission_manager():
    from engines.policy_engine import check_permission
    assert check_permission('manager', 'import_excel') is True


def test_import_excel_permission_admin():
    from engines.policy_engine import check_permission
    assert check_permission('admin', 'import_excel') is True


def test_import_excel_permission_frontdesk_denied():
    from engines.policy_engine import check_permission
    assert check_permission('frontdesk', 'import_excel') is False


def test_export_template_permission_frontdesk():
    from engines.policy_engine import check_permission
    assert check_permission('frontdesk', 'export_template') is True


def test_export_template_permission_newbie_denied():
    from engines.policy_engine import check_permission
    assert check_permission('newbie', 'export_template') is False

"""Tests for sheet_sync_v2 pipeline - Phase 26 tables.

Verifies that sheet_sync_v2 populates:
- knife_deposits (columns K-R: knife 1-8 amounts)
- client_pipeline_status (columns H-I: new_order/pressure, kill detection)
- client_role_assignments (columns D+E: frontdesk + maintenance pairing)
- cross_role_notes (columns T-Z: cross-role notes)
- daily_performance (前台数据 sheet)
"""

import pytest
import asyncio
import tempfile
import sqlite3
import os
from datetime import date, datetime
from unittest.mock import Mock, AsyncMock, patch
from typing import List

import aiosqlite

from database_v2 import DatabaseV2, NAME_ALIASES
from models_v2 import Client, Staff, StaffRole, ClientStatus, Deposit
from engines.sheet_sync_v2 import (
    SheetSyncV2,
    _parse_money,
    _CROSS_ROLE_COLUMNS,
    _KILL_PATTERNS,
)


class TestParseMoney:
    """Test _parse_money() handles Chinese currency formats correctly."""

    def test_parse_standard_dollar(self):
        assert _parse_money("$1,234.56") == 1234.56

    def test_parse_yuan_symbol(self):
        assert _parse_money("¥1,234") == 1234.0

    def test_parse_full_width_yuan(self):
        assert _parse_money("￥1,234") == 1234.0

    def test_parse_yuan_suffix(self):
        assert _parse_money("1234元") == 1234.0

    def test_parse_negative(self):
        assert _parse_money("-$500") == -500.0

    def test_parse_negative_yuan(self):
        assert _parse_money("-¥200") == -200.0

    def test_parse_empty_string(self):
        assert _parse_money("") == 0.0

    def test_parse_whitespace_only(self):
        assert _parse_money("   ") == 0.0

    def test_parse_none(self):
        assert _parse_money(None) == 0.0  # type: ignore[arg-type]

    def test_parse_invalid(self):
        assert _parse_money("abc") == 0.0

    def test_parse_zero(self):
        assert _parse_money("0") == 0.0

    def test_parse_integer(self):
        assert _parse_money("1234") == 1234.0

    def test_parse_no_comma(self):
        assert _parse_money("$1000") == 1000.0


class TestKillDetection:
    """Test kill type detection from note text."""

    def test_detect_register_kill(self):
        assert _KILL_PATTERNS["注册杀"] == "register_kill"

    def test_detect_new_order_kill(self):
        assert _KILL_PATTERNS["新单杀"] == "new_order_kill"

    def test_detect_pressure_kill(self):
        assert _KILL_PATTERNS["承压杀"] == "pressure_kill"

    def test_detect_salary_kill(self):
        assert _KILL_PATTERNS["工资杀"] == "salary_kill"


class TestCrossRoleColumns:
    """Test cross-role column mapping to normalized role names."""

    def test_column_mapping_exists(self):
        assert 19 in _CROSS_ROLE_COLUMNS
        assert 20 in _CROSS_ROLE_COLUMNS
        assert 21 in _CROSS_ROLE_COLUMNS
        assert 22 in _CROSS_ROLE_COLUMNS
        assert 23 in _CROSS_ROLE_COLUMNS
        assert 24 in _CROSS_ROLE_COLUMNS
        assert 25 in _CROSS_ROLE_COLUMNS

    def test_role_names_normalized(self):
        assert _CROSS_ROLE_COLUMNS[19] == "frontdesk"
        assert _CROSS_ROLE_COLUMNS[20] == "opener_legacy"
        assert _CROSS_ROLE_COLUMNS[21] == "newbie"
        assert _CROSS_ROLE_COLUMNS[22] == "group_hype"
        assert _CROSS_ROLE_COLUMNS[23] == "customer_service"
        assert _CROSS_ROLE_COLUMNS[24] == "maintenance"


@pytest.fixture
async def temp_v2_db():
    """Create a temporary V2 database for testing."""
    temp_file = tempfile.mktemp(suffix=".db")
    db = DatabaseV2(temp_file)
    await db.initialize()
    yield db
    try:
        os.unlink(temp_file)
    except FileNotFoundError:
        pass


@pytest.fixture
async def populated_v2_db(temp_v2_db):
    """Create a V2 database populated with test staff and clients.

    Uses real IDs from the DB (seed_team_structure may pre-insert rows).
    """
    async with temp_v2_db.get_connection() as db:
        # Insert test staff — ON CONFLICT to be safe if names already exist
        await db.execute(
            "INSERT OR IGNORE INTO staff (tg_user_id, tg_chat_id, display_name, role)"
            " VALUES (?, ?, ?, ?)",
            (111111, 111111, "阿YIM", "frontdesk"),
        )
        await db.execute(
            "INSERT OR IGNORE INTO staff (tg_user_id, tg_chat_id, display_name, role)"
            " VALUES (?, ?, ?, ?)",
            (222222, 222222, "小王", "maintenance"),
        )
        await db.execute(
            "INSERT OR IGNORE INTO staff (tg_user_id, tg_chat_id, display_name, role)"
            " VALUES (?, ?, ?, ?)",
            (333333, 333333, "ODDY", "frontdesk"),
        )
        await db.commit()

    # Look up actual IDs — seed_team_structure may have pre-inserted staff
    async with temp_v2_db.get_connection() as db:
        cur = await db.execute(
            "SELECT id FROM staff WHERE display_name=? LIMIT 1", ("阿YIM",)
        )
        row = await cur.fetchone()
        staff1_id = row["id"]

        cur = await db.execute(
            "SELECT id FROM staff WHERE display_name=? LIMIT 1", ("小王",)
        )
        row = await cur.fetchone()
        staff2_id = row["id"]

        cur = await db.execute(
            "SELECT id FROM staff WHERE display_name=? LIMIT 1", ("ODDY",)
        )
        row = await cur.fetchone()
        staff3_id = row["id"]

        await db.execute(
            "INSERT INTO clients (frontdesk_id, phone, source, status, account_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (staff1_id, "+8613800138000", "飞机筛选", "registered", "ACC001"),
        )
        await db.execute(
            "INSERT INTO clients (frontdesk_id, phone, source, status, account_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (staff1_id, "+8613800138001", "飞机筛选", "registered", "ACC002"),
        )
        await db.execute(
            "INSERT INTO clients (frontdesk_id, phone, source, status, account_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (staff3_id, "+8613800138002", "RCS筛选", "contacted", "ACC003"),
        )
        await db.commit()

        # Store actual IDs on the fixture for tests to use
        cur = await db.execute(
            "SELECT id FROM clients WHERE account_id='ACC001' LIMIT 1"
        )
        row = await cur.fetchone()
        temp_v2_db._test_client1_id = row["id"]
        temp_v2_db._test_staff1_id = staff1_id
        temp_v2_db._test_staff2_id = staff2_id
        temp_v2_db._test_staff3_id = staff3_id

    yield temp_v2_db


class TestKnifeDepositsSync:
    """Test _sync_knives_for_client populates knife_deposits correctly."""

    @pytest.mark.asyncio
    async def test_sync_knives_inserts_all_eight(self, populated_v2_db):
        """Test all 8 knife columns are parsed and inserted."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = (
            [""] * 10
            + ["100", "200", "300", "400", "500", "600", "700", "800"]
            + ["3600"]
        )

        async with populated_v2_db.get_connection() as db:
            await sync._sync_knives_for_client(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT knife_number, amount FROM knife_deposits"
            f" WHERE client_id={client_id} ORDER BY knife_number"
        )
        results = c.fetchall()
        conn.close()

        assert len(results) == 8
        expected = [
            (1, 100.0),
            (2, 200.0),
            (3, 300.0),
            (4, 400.0),
            (5, 500.0),
            (6, 600.0),
            (7, 700.0),
            (8, 800.0),
        ]
        assert results == expected

    @pytest.mark.asyncio
    async def test_sync_knives_skips_zero_amounts(self, populated_v2_db):
        """Test knife columns with 0 or empty values are skipped."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [""] * 10 + ["100", "", "0", "400", "", "", "", ""] + [""]

        async with populated_v2_db.get_connection() as db:
            await sync._sync_knives_for_client(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT knife_number, amount FROM knife_deposits"
            f" WHERE client_id={client_id} ORDER BY knife_number"
        )
        results = c.fetchall()
        conn.close()

        assert len(results) == 2
        assert results == [(1, 100.0), (4, 400.0)]

    @pytest.mark.asyncio
    async def test_sync_knives_handles_short_row(self, populated_v2_db):
        """Test short row (fewer than 18 columns) doesn't crash."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = ["a", "b", "c"]

        async with populated_v2_db.get_connection() as db:
            await sync._sync_knives_for_client(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM knife_deposits WHERE client_id={client_id}")
        count = c.fetchone()[0]
        conn.close()

        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_knives_upserts_on_conflict(self, populated_v2_db):
        """Test ON CONFLICT DO UPDATE replaces existing amounts."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row1 = [""] * 10 + ["100"] + ["0"] * 7 + ["100"]
        row2 = [""] * 10 + ["200"] + ["0"] * 7 + ["200"]

        async with populated_v2_db.get_connection() as db:
            await sync._sync_knives_for_client(db, client_id=client_id, row=row1)
            await sync._sync_knives_for_client(db, client_id=client_id, row=row2)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT knife_number, amount FROM knife_deposits"
            f" WHERE client_id={client_id} ORDER BY knife_number"
        )
        results = c.fetchall()
        conn.close()

        assert len(results) == 1
        assert results[0] == (1, 200.0)


class TestPipelineSync:
    """Test _sync_pipeline_for_client populates client_pipeline_status correctly."""

    @pytest.mark.asyncio
    async def test_sync_pipeline_inserts_new_order(self, populated_v2_db):
        """Test new_order_amount and new_order_at are set from column H."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [
            "date",
            "acc1",
            "group",
            "阿YIM",
            "小王",
            "123",
            "Iconnect",
            "1500",
            "0",
            "no kill",
        ] + [""] * 9
        note = "no kill"

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note=note
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT new_order_amount, pressure_amount, kill_type, total_deposited"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == 1500.0
        assert result[1] == 0.0
        assert result[2] is None

    @pytest.mark.asyncio
    async def test_sync_pipeline_inserts_pressure(self, populated_v2_db):
        """Test pressure_amount and pressure_at are set from column I."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "小王",
                "123",
                "Iconnect",
                "0",
                "800",
                "no kill",
            ]
            + [""] * 8
            + ["800"]
        )
        note = "no kill"

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note=note
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT new_order_amount, pressure_amount"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == 0.0
        assert result[1] == 800.0

    @pytest.mark.asyncio
    async def test_sync_pipeline_detects_register_kill(self, populated_v2_db):
        """Test register_kill detection from note text."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "0",
                "0",
                "客户不配合 注册杀",
            ]
            + [""] * 8
            + ["0"]
        )
        note = "客户不配合 注册杀"

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note=note
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT kill_type, kill_knife"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "register_kill"
        assert result[1] is None

    @pytest.mark.asyncio
    async def test_sync_pipeline_detects_salary_kill_with_knife(self, populated_v2_db):
        """Test salary_kill detection with knife number extraction."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "0",
                "0",
                "工资杀6刀",
            ]
            + [""] * 8
            + ["0"]
        )
        note = "工资杀6刀"

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note=note
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT kill_type, kill_knife"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "salary_kill"
        assert result[1] == 6

    @pytest.mark.asyncio
    async def test_sync_pipeline_handles_short_row(self, populated_v2_db):
        """Test short row doesn't crash and still upserts a pipeline row."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = ["a", "b"]
        note = ""

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note=note
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            f"SELECT COUNT(*) FROM client_pipeline_status WHERE client_id={client_id}"
        )
        count = c.fetchone()[0]
        conn.close()

        assert count == 1


class TestRoleAssignmentSync:
    """Test _sync_role_assignment populates client_role_assignments correctly."""

    @pytest.mark.asyncio
    async def test_sync_role_assignment_inserts(self, populated_v2_db):
        """Test role assignment is inserted."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id
        staff_id = populated_v2_db._test_staff1_id

        async with populated_v2_db.get_connection() as db:
            await sync._sync_role_assignment(
                db, client_id=client_id, staff_id=staff_id, role_type="frontdesk"
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT client_id, staff_id, role_type, is_active"
            f" FROM client_role_assignments WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == client_id
        assert result[1] == staff_id
        assert result[2] == "frontdesk"
        assert result[3] == 1

    @pytest.mark.asyncio
    async def test_sync_role_assignment_skips_duplicate(self, populated_v2_db):
        """Test duplicate assignment is not inserted."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id
        staff_id = populated_v2_db._test_staff1_id

        async with populated_v2_db.get_connection() as db:
            await sync._sync_role_assignment(
                db, client_id=client_id, staff_id=staff_id, role_type="frontdesk"
            )
            await sync._sync_role_assignment(
                db, client_id=client_id, staff_id=staff_id, role_type="frontdesk"
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            f"SELECT COUNT(*) FROM client_role_assignments WHERE client_id={client_id}"
        )
        count = c.fetchone()[0]
        conn.close()

        assert count == 1

    @pytest.mark.asyncio
    async def test_sync_role_assignment_allows_different_roles(self, populated_v2_db):
        """Test same client can have multiple role types."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id
        staff1_id = populated_v2_db._test_staff1_id
        staff2_id = populated_v2_db._test_staff2_id

        async with populated_v2_db.get_connection() as db:
            await sync._sync_role_assignment(
                db, client_id=client_id, staff_id=staff1_id, role_type="frontdesk"
            )
            await sync._sync_role_assignment(
                db, client_id=client_id, staff_id=staff2_id, role_type="maintenance"
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT role_type FROM client_role_assignments"
            f" WHERE client_id={client_id} ORDER BY role_type"
        )
        results = [r[0] for r in c.fetchall()]
        conn.close()

        assert len(results) == 2
        assert "frontdesk" in results
        assert "maintenance" in results


class TestCrossRoleNotesSync:
    """Test _sync_cross_role_notes populates cross_role_notes correctly."""

    @pytest.mark.asyncio
    async def test_sync_cross_role_notes_inserts_all_roles(self, populated_v2_db):
        """Test all cross-role note columns are inserted."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [""] * 30
        row[19] = "前台备注1"
        row[20] = "开单备注2"
        row[21] = "小白备注3"
        row[22] = "炒群备注4"
        row[23] = "客服备注5"
        row[24] = "维护备注6"
        row[25] = "等等备注7"

        async with populated_v2_db.get_connection() as db:
            await sync._sync_cross_role_notes(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT from_role, content FROM cross_role_notes"
            f" WHERE client_id={client_id} ORDER BY from_role"
        )
        results = c.fetchall()
        conn.close()

        assert len(results) == 7
        roles = [r[0] for r in results]
        assert "frontdesk" in roles
        assert "opener_legacy" in roles
        assert "newbie" in roles
        assert "group_hype" in roles
        assert "customer_service" in roles
        assert "maintenance" in roles
        assert "etc" in roles

    @pytest.mark.asyncio
    async def test_sync_cross_role_notes_skips_empty(self, populated_v2_db):
        """Test empty note columns are skipped."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [""] * 30
        row[19] = "前台备注"
        row[20] = ""
        row[21] = ""

        async with populated_v2_db.get_connection() as db:
            await sync._sync_cross_role_notes(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM cross_role_notes WHERE client_id={client_id}")
        count = c.fetchone()[0]
        conn.close()

        assert count == 1

    @pytest.mark.asyncio
    async def test_sync_cross_role_notes_skips_duplicates(self, populated_v2_db):
        """Test same content doesn't create duplicates on re-sync."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [""] * 30
        row[19] = "前台备注"

        async with populated_v2_db.get_connection() as db:
            await sync._sync_cross_role_notes(db, client_id=client_id, row=row)
            await sync._sync_cross_role_notes(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM cross_role_notes"
            f" WHERE client_id={client_id} AND from_role=?",
            ("frontdesk",),
        )
        count = c.fetchone()[0]
        conn.close()

        assert count == 1


class TestFinancialSheetImport:
    """Test import_financial_sheet populates all Phase 26 tables."""

    @pytest.fixture
    def mock_writer(self):
        writer = Mock()
        writer.spreadsheet = Mock()
        return writer

    @pytest.mark.asyncio
    async def test_financial_sheet_imports_knives(self, populated_v2_db, mock_writer):
        """Test import_financial_sheet populates knife_deposits."""
        staff1_id = populated_v2_db._test_staff1_id
        client_id = populated_v2_db._test_client1_id

        # Row 0 = header (skipped by import_financial_sheet via all_rows[1:])
        # Row 1 = actual data row
        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            # Header row — skipped
            [
                "日期",
                "account_id",
                "group",
                "frontdesk",
                "maintenance",
                "fd_num",
                "platform",
                "new_order",
                "pressure",
                "note",
                "k1",
                "k2",
                "k3",
                "k4",
                "k5",
                "k6",
                "k7",
                "k8",
                "total_in",
            ],
            # Data row
            [
                "04/01/2026",
                "ACC001",
                "group",
                "阿YIM",
                "小王",
                "123",
                "Iconnect",
                "1000",
                "500",
                "no kill",
                "",
                "100",
                "200",
                "300",
                "400",
                "500",
                "600",
                "700",
                "800",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with patch("engines.sheet_sync_v2.database_v2", populated_v2_db):
            await sync.import_financial_sheet()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM knife_deposits WHERE client_id={client_id}")
        knife_count = c.fetchone()[0]
        c.execute(f"SELECT SUM(amount) FROM knife_deposits WHERE client_id={client_id}")
        total = c.fetchone()[0]
        conn.close()

        # knife1 is index 10 = "" (skipped), knife2-8 = 100–800 → 7 knives
        assert knife_count == 7
        assert total == 2800.0

    @pytest.mark.asyncio
    async def test_financial_sheet_imports_pipeline(self, populated_v2_db, mock_writer):
        """Test import_financial_sheet populates client_pipeline_status with financial data."""
        client_id = populated_v2_db._test_client1_id

        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            # Header row
            [
                "日期",
                "account_id",
                "group",
                "frontdesk",
                "maintenance",
                "fd_num",
                "platform",
                "new_order",
                "pressure",
                "note",
            ]
            + [""] * 9,
            # Data row
            [
                "04/01/2026",
                "ACC001",
                "group",
                "阿YIM",
                "小王",
                "123",
                "Iconnect",
                "1500",
                "800",
                "no kill",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "2300",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with patch("engines.sheet_sync_v2.database_v2", populated_v2_db):
            await sync.import_financial_sheet()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT new_order_amount, pressure_amount, total_deposited"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == 1500.0
        assert result[1] == 800.0
        assert result[2] == 2300.0

    @pytest.mark.asyncio
    async def test_financial_sheet_imports_maintenance_role(
        self, populated_v2_db, mock_writer
    ):
        """Test maintenance staff from column E gets role assignment."""
        client_id = populated_v2_db._test_client1_id
        staff2_id = populated_v2_db._test_staff2_id

        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            # Header row
            [
                "日期",
                "account_id",
                "group",
                "frontdesk",
                "maintenance",
                "fd_num",
                "platform",
                "new_order",
                "pressure",
                "note",
            ]
            + [""] * 9,
            # Data row
            [
                "04/01/2026",
                "ACC001",
                "group",
                "阿YIM",
                "小王",
                "123",
                "Iconnect",
                "1000",
                "0",
                "no kill",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "1000",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with patch("engines.sheet_sync_v2.database_v2", populated_v2_db):
            await sync.import_financial_sheet()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT staff_id, role_type FROM client_role_assignments"
            f" WHERE client_id={client_id} ORDER BY role_type"
        )
        results = c.fetchall()
        conn.close()

        roles = {r[1]: r[0] for r in results}
        assert "frontdesk" in roles
        assert "maintenance" in roles
        assert roles["maintenance"] == staff2_id

    @pytest.mark.asyncio
    async def test_financial_sheet_imports_cross_role_notes(
        self, populated_v2_db, mock_writer
    ):
        """Test import_financial_sheet populates cross_role_notes."""
        client_id = populated_v2_db._test_client1_id

        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            # Header row
            [
                "日期",
                "account_id",
                "group",
                "frontdesk",
                "maintenance",
                "fd_num",
                "platform",
                "new_order",
                "pressure",
                "note",
            ]
            + [""] * 15,
            # Data row — note cols at indices 19-25
            [
                "04/01/2026",
                "ACC001",
                "group",
                "阿YIM",
                "小王",
                "123",
                "Iconnect",
                "1000",
                "0",
                "no kill",
                "",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "1000",
                "前台备注",
                "开单备注",
                "小白备注",
                "炒群备注",
                "客服备注",
                "维护备注",
                "等等备注",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with patch("engines.sheet_sync_v2.database_v2", populated_v2_db):
            await sync.import_financial_sheet()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM cross_role_notes WHERE client_id={client_id}")
        count = c.fetchone()[0]
        conn.close()

        assert count == 7

    @pytest.mark.asyncio
    async def test_financial_sheet_skips_header_rows(
        self, populated_v2_db, mock_writer
    ):
        """Test that rows with placeholder date values are skipped."""
        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            # Row 0 = actual header
            ["日期", "account_id", "group", "frontdesk", "maintenance"] + [""] * 14,
            # Row 1 = X月XX日 placeholder — should be skipped
            [
                "X月XX日",
                "ACC001",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "1000",
                "0",
                "no kill",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "1000",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with patch("engines.sheet_sync_v2.database_v2", populated_v2_db):
            count = await sync.import_financial_sheet()

        # Placeholder row should be skipped
        assert count == 0


class TestPerformanceSheetImport:
    """Test import_performance_sheet populates daily_performance correctly."""

    @pytest.fixture
    def mock_writer(self):
        writer = Mock()
        writer.spreadsheet = Mock()
        return writer

    @pytest.mark.asyncio
    async def test_performance_sheet_imports_stats(self, populated_v2_db, mock_writer):
        """Test import_performance_sheet populates daily_performance."""
        staff1_id = populated_v2_db._test_staff1_id

        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "04/01/2026",
                "阿YIM",
                "飞机筛选",
                "100",
                "80%",
                "50",
                "40",
                "30",
                "25",
                "75%",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.SHEET_MAP", {"3月-前台数据": "test"}),
        ):
            count = await sync.import_performance_sheet()

        assert count == 1

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT staff_id, powder_count, reply_rate, completed_registration,"
            " new_order, conversion_rate"
            f" FROM daily_performance WHERE staff_id={staff1_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == staff1_id
        assert result[1] == 100
        assert result[2] == 80.0
        assert result[3] == 50
        assert result[4] == 25
        assert result[5] == 75.0

    @pytest.mark.asyncio
    async def test_performance_sheet_upserts_on_conflict(
        self, populated_v2_db, mock_writer
    ):
        """Test ON CONFLICT DO UPDATE replaces existing stats."""
        staff1_id = populated_v2_db._test_staff1_id

        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "04/01/2026",
                "阿YIM",
                "飞机筛选",
                "100",
                "80%",
                "50",
                "40",
                "30",
                "25",
                "75%",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.SHEET_MAP", {"3月-前台数据": "test"}),
        ):
            await sync.import_performance_sheet()
            await sync.import_performance_sheet()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM daily_performance"
            f" WHERE staff_id={staff1_id} AND stat_date=?",
            ("2026-04-01",),
        )
        count = c.fetchone()[0]
        conn.close()

        assert count == 1

    @pytest.mark.asyncio
    async def test_performance_sheet_skips_unknown_staff(
        self, populated_v2_db, mock_writer
    ):
        """Test rows with unknown staff names are skipped."""
        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "04/01/2026",
                "未知员工",
                "飞机筛选",
                "100",
                "80%",
                "50",
                "40",
                "30",
                "25",
                "75%",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.SHEET_MAP", {"3月-前台数据": "test"}),
        ):
            count = await sync.import_performance_sheet()

        assert count == 0


class TestNameAliases:
    """Test NAME_ALIASES maps English display names to Chinese equivalents."""

    def test_name_aliases_maps_english_to_chinese(self):
        assert NAME_ALIASES.get("Ah YIM") == "阿YIM"

    def test_name_aliases_is_dict(self):
        assert isinstance(NAME_ALIASES, dict)

    def test_name_aliases_values_are_strings(self):
        for key, value in NAME_ALIASES.items():
            assert isinstance(key, str)
            assert isinstance(value, str)


class TestEndToEndPipeline:
    """End-to-end tests for the complete sync pipeline."""

    @pytest.fixture
    def mock_writer(self):
        writer = Mock()
        writer.spreadsheet = Mock()
        return writer

    @pytest.mark.asyncio
    async def test_full_sync_populates_all_tables(self, populated_v2_db, mock_writer):
        """Test full_sync via import_financial_sheet populates all 5 Phase 26 tables."""
        client_id = populated_v2_db._test_client1_id
        staff1_id = populated_v2_db._test_staff1_id

        maintenance_ws = Mock()
        maintenance_ws.get_all_values.return_value = [
            # Header
            [
                "日期",
                "account_id",
                "group",
                "frontdesk",
                "maintenance",
                "fd_num",
                "platform",
                "new_order",
                "pressure",
                "note",
            ]
            + [""] * 15,
            # Data row with knives + pipeline + cross-role notes
            [
                "04/01/2026",
                "ACC001",
                "group",
                "阿YIM",
                "小王",
                "123",
                "Iconnect",
                "1500",
                "800",
                "工资杀6刀",
                "",
                "100",
                "200",
                "300",
                "0",
                "0",
                "0",
                "0",
                "2100",
                "前台备注1",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ]
        performance_ws = Mock()
        performance_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "04/01/2026",
                "阿YIM",
                "飞机筛选",
                "100",
                "80%",
                "50",
                "40",
                "30",
                "25",
                "75%",
            ],
        ]
        client_ws = Mock()
        client_ws.get_all_values.return_value = []

        def get_worksheet(name):
            ws = Mock()
            if "维护数据" in name:
                ws.get_all_values = maintenance_ws.get_all_values
            elif "前台数据" in name:
                ws.get_all_values = performance_ws.get_all_values
            else:
                ws.get_all_values = client_ws.get_all_values
            return ws

        mock_writer.spreadsheet.worksheet.side_effect = get_worksheet

        sync = SheetSyncV2(mock_writer)
        # Prevent actual Google Sheets export from running
        sync._sheets_readonly = True

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.FRONTDESK_NAMES", ["阿YIM"]),
            patch(
                "engines.sheet_sync_v2.SHEET_MAP",
                {"阿YIM": 1, "3月-前台数据": "perf"},
            ),
        ):
            results = await sync.full_sync()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()

        # knife2-4 = 100,200,300 → 3 knives (knife1 index 10 is "")
        c.execute(f"SELECT COUNT(*) FROM knife_deposits WHERE client_id={client_id}")
        knife_count = c.fetchone()[0]

        c.execute(
            "SELECT new_order_amount, pressure_amount, kill_type, kill_knife"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        pipeline = c.fetchone()

        c.execute(
            f"SELECT COUNT(*) FROM client_role_assignments WHERE client_id={client_id}"
        )
        role_count = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM cross_role_notes WHERE client_id={client_id}")
        notes_count = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM daily_performance WHERE staff_id={staff1_id}")
        perf_count = c.fetchone()[0]

        conn.close()

        assert knife_count == 3
        assert pipeline is not None
        assert pipeline[0] == 1500.0
        assert pipeline[1] == 800.0
        assert pipeline[2] == "salary_kill"
        assert pipeline[3] == 6
        assert role_count >= 2
        assert notes_count == 1
        assert perf_count == 1


# ─── Additional coverage: edge cases per AGENTS.md verification checklist ─────


class TestParseMoneyEdgeCases:
    """Additional _parse_money edge cases from real sheet data."""

    def test_parse_currency_with_commas_and_decimals(self):
        assert _parse_money("$12,345.67") == 12345.67

    def test_parse_negative_yuan_suffix(self):
        assert _parse_money("-1234元") == -1234.0

    def test_parse_full_width_yen_with_commas(self):
        assert _parse_money("￥12,000") == 12000.0

    def test_parse_leading_trailing_whitespace(self):
        assert _parse_money("  $500  ") == 500.0

    def test_parse_just_currency_symbol(self):
        assert _parse_money("$") == 0.0

    def test_parse_just_yuan_suffix(self):
        assert _parse_money("元") == 0.0

    def test_parse_large_amount(self):
        assert _parse_money("$1,000,000") == 1000000.0

    def test_parse_decimal_only(self):
        assert _parse_money("0.50") == 0.50


class TestParseMoneySpecFromSpec:
    """Edge cases explicitly required by Phase 2 verification spec."""

    def test_parse_dollar_zero(self):
        """$0 should parse to 0.0."""
        assert _parse_money("$0") == 0.0

    def test_parse_just_yen_symbol(self):
        """Bare ¥ with no number should return 0.0."""
        assert _parse_money("¥") == 0.0

    def test_parse_negative_with_commas_and_decimals(self):
        """-$1,234.56 should parse correctly."""
        assert _parse_money("-$1,234.56") == -1234.56

    def test_parse_negative_large(self):
        """-$70,000 should parse correctly (real sheet edge case)."""
        assert _parse_money("-$70,000") == -70000.0

    def test_parse_negative_yen_with_commas(self):
        """-¥3,000 should parse correctly."""
        assert _parse_money("-¥3,000") == -3000.0


class TestKillExtractionEdgeCases:
    """Test kill type + knife number extraction edge cases."""

    @pytest.mark.asyncio
    async def test_new_order_kill_detection(self, populated_v2_db):
        """Test new_order_kill detection via _sync_pipeline_for_client."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "0",
                "0",
                "新单杀3刀",
            ]
            + [""] * 8
            + ["0"]
        )

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note="新单杀3刀"
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT kill_type, kill_knife"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result[0] == "new_order_kill"
        assert result[1] == 3

    @pytest.mark.asyncio
    async def test_pressure_kill_detection(self, populated_v2_db):
        """Test pressure_kill detection via _sync_pipeline_for_client."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "0",
                "0",
                "承压杀",
            ]
            + [""] * 8
            + ["0"]
        )

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note="承压杀"
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT kill_type, kill_knife"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result[0] == "pressure_kill"
        assert result[1] is None  # no knife number specified

    @pytest.mark.asyncio
    async def test_multi_digit_knife_extraction(self, populated_v2_db):
        """Test knife extraction with multi-digit number like 12."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "0",
                "0",
                "工资杀12刀",
            ]
            + [""] * 8
            + ["0"]
        )

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note="工资杀12刀"
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT kill_type, kill_knife"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result[0] == "salary_kill"
        assert result[1] == 12

    @pytest.mark.asyncio
    async def test_kill_with_surrounding_text(self, populated_v2_db):
        """Test kill detection when embedded in longer note text."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        note = "客户不配合，态度差，注册杀。已通知组长"
        row = (
            ["date", "acc1", "group", "阿YIM", "", "123", "Iconnect", "0", "0", note]
            + [""] * 8
            + ["0"]
        )

        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row, note=note
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT kill_type FROM client_pipeline_status WHERE client_id={0}".format(
                client_id
            )
        )
        result = c.fetchone()
        conn.close()

        assert result[0] == "register_kill"


class TestPipelineUpsertIdempotency:
    """Test that pipeline upsert preserves earlier timestamps on re-sync."""

    @pytest.mark.asyncio
    async def test_pipeline_preserves_existing_new_order_at(self, populated_v2_db):
        """Test re-sync doesn't overwrite new_order_at if already set."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        # First sync: new_order=1000
        row1 = (
            ["date", "acc1", "group", "阿YIM", "", "123", "Iconnect", "1000", "0", ""]
            + [""] * 8
            + ["1000"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row1, note=""
            )
            await db.commit()

        # Read first timestamp
        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT new_order_at FROM client_pipeline_status"
            f" WHERE client_id={client_id}"
        )
        first_ts = c.fetchone()[0]
        conn.close()

        assert first_ts is not None

        # Second sync: new_order=2000 — timestamp should NOT change
        row2 = (
            ["date", "acc1", "group", "阿YIM", "", "123", "Iconnect", "2000", "0", ""]
            + [""] * 8
            + ["2000"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row2, note=""
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT new_order_at, new_order_amount FROM client_pipeline_status"
            f" WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        # Timestamp should be preserved from first insert
        assert result[0] == first_ts
        # Amount should be updated to the higher value
        assert result[1] == 2000.0

    @pytest.mark.asyncio
    async def test_pipeline_total_deposited_takes_max(self, populated_v2_db):
        """Test total_deposited keeps the max value across re-syncs."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        # First sync: total=5000
        row1 = (
            ["date", "acc1", "group", "阿YIM", "", "123", "Iconnect", "0", "0", ""]
            + [""] * 8
            + ["5000"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row1, note=""
            )
            await db.commit()

        # Second sync with lower total (shouldn't overwrite)
        row2 = (
            ["date", "acc1", "group", "阿YIM", "", "123", "Iconnect", "0", "0", ""]
            + [""] * 8
            + ["3000"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row2, note=""
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT total_deposited FROM client_pipeline_status"
            f" WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result[0] == 5000.0  # max is preserved


class TestPipelinePressureTimestampPreservation:
    """Test that pressure_at timestamp is preserved on re-sync."""

    @pytest.mark.asyncio
    async def test_pipeline_preserves_existing_pressure_at(self, populated_v2_db):
        """Test re-sync doesn't overwrite pressure_at if already set."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        # First sync: pressure=800
        row1 = (
            ["date", "acc1", "group", "阿YIM", "", "123", "Iconnect", "0", "800", ""]
            + [""] * 8
            + ["800"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row1, note=""
            )
            await db.commit()

        # Read first timestamp
        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT pressure_at FROM client_pipeline_status"
            f" WHERE client_id={client_id}"
        )
        first_ts = c.fetchone()[0]
        conn.close()

        assert first_ts is not None

        # Second sync: pressure=1500 — timestamp should NOT change
        row2 = (
            ["date", "acc1", "group", "阿YIM", "", "123", "Iconnect", "0", "1500", ""]
            + [""] * 8
            + ["1500"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row2, note=""
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT pressure_at, pressure_amount FROM client_pipeline_status"
            f" WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        # Timestamp should be preserved from first insert
        assert result[0] == first_ts
        # Amount should be updated to the higher value
        assert result[1] == 1500.0


class TestKnifeNegativeAmounts:
    """Test knife deposits with negative amounts (losses)."""

    @pytest.mark.asyncio
    async def test_sync_knives_stores_negative_amounts(self, populated_v2_db):
        """Test negative amounts like -$70,000 are stored correctly."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [""] * 10 + ["-$70,000", "$1,000", "", "", "", "", "", ""] + [""]

        async with populated_v2_db.get_connection() as db:
            await sync._sync_knives_for_client(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT knife_number, amount FROM knife_deposits"
            f" WHERE client_id={client_id} ORDER BY knife_number"
        )
        results = c.fetchall()
        conn.close()

        assert len(results) == 2
        assert results[0] == (1, -70000.0)
        assert results[1] == (2, 1000.0)


class TestKnivesWithCurrencyFormatting:
    """Test knife sync when sheet cells contain currency-formatted values."""

    @pytest.mark.asyncio
    async def test_sync_knives_with_dollar_signs(self, populated_v2_db):
        """Test knife cells with $1,234 formatting parse correctly."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [""] * 10 + ["$1,000", "$2,500", "¥3,000", "", "", "", "", ""] + [""]

        async with populated_v2_db.get_connection() as db:
            await sync._sync_knives_for_client(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT knife_number, amount FROM knife_deposits"
            f" WHERE client_id={client_id} ORDER BY knife_number"
        )
        results = c.fetchall()
        conn.close()

        assert len(results) == 3
        assert results[0] == (1, 1000.0)
        assert results[1] == (2, 2500.0)
        assert results[2] == (3, 3000.0)


class TestCrossRoleNotesEdgeCases:
    """Additional cross_role_notes edge cases."""

    @pytest.mark.asyncio
    async def test_sync_cross_role_notes_handles_whitespace_only(self, populated_v2_db):
        """Test columns with only whitespace are treated as empty."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        row = [""] * 30
        row[19] = "   "  # whitespace only — should be skipped
        row[20] = "valid note"

        async with populated_v2_db.get_connection() as db:
            await sync._sync_cross_role_notes(db, client_id=client_id, row=row)
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM cross_role_notes WHERE client_id={client_id}")
        count = c.fetchone()[0]
        conn.close()

        assert count == 1  # only the valid note


class TestPerformanceSheetDateFormats:
    """Test import_performance_sheet handles different date formats."""

    @pytest.fixture
    def mock_writer(self):
        writer = Mock()
        writer.spreadsheet = Mock()
        return writer

    @pytest.mark.asyncio
    async def test_performance_sheet_iso_date_format(
        self, populated_v2_db, mock_writer
    ):
        """Test YYYY-MM-DD date format is parsed correctly."""
        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "2026-04-01",
                "阿YIM",
                "飞机筛选",
                "100",
                "80%",
                "50",
                "40",
                "30",
                "25",
                "75%",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.SHEET_MAP", {"3月-前台数据": "test"}),
        ):
            count = await sync.import_performance_sheet()

        assert count == 1

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        staff1_id = populated_v2_db._test_staff1_id
        c.execute(f"SELECT stat_date FROM daily_performance WHERE staff_id={staff1_id}")
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "2026-04-01"

    @pytest.mark.asyncio
    async def test_performance_sheet_invalid_date_skipped(
        self, populated_v2_db, mock_writer
    ):
        """Test rows with unparseable dates are skipped."""
        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "not-a-date",
                "阿YIM",
                "飞机筛选",
                "100",
                "80%",
                "50",
                "40",
                "30",
                "25",
                "75%",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.SHEET_MAP", {"3月-前台数据": "test"}),
        ):
            count = await sync.import_performance_sheet()

        assert count == 0


class TestPerformanceSheetEdgeCases:
    """Additional edge cases for performance sheet import."""

    @pytest.fixture
    def mock_writer(self):
        writer = Mock()
        writer.spreadsheet = Mock()
        return writer

    @pytest.mark.asyncio
    async def test_performance_sheet_empty_numeric_columns(
        self, populated_v2_db, mock_writer
    ):
        """Test rows with empty numeric columns get 0 defaults."""
        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "04/01/2026",
                "阿YIM",
                "飞机筛选",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.SHEET_MAP", {"3月-前台数据": "test"}),
        ):
            count = await sync.import_performance_sheet()

        assert count == 1

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        staff1_id = populated_v2_db._test_staff1_id
        c.execute(
            "SELECT powder_count, reply_rate, completed_registration, new_order"
            f" FROM daily_performance WHERE staff_id={staff1_id}"
        )
        result = c.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == 0  # powder_count
        assert result[1] == 0.0  # reply_rate
        assert result[2] == 0  # completed_registration
        assert result[3] == 0  # new_order

    @pytest.mark.asyncio
    async def test_performance_sheet_name_alias_resolution(
        self, populated_v2_db, mock_writer
    ):
        """Test NAME_ALIASES resolves English names to Chinese equivalents."""
        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            ["日期", "姓名", "类别", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", ""],
            [
                "04/01/2026",
                "Ah YIM",
                "飞机筛选",
                "100",
                "80%",
                "50",
                "40",
                "30",
                "25",
                "75%",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with (
            patch("engines.sheet_sync_v2.database_v2", populated_v2_db),
            patch("engines.sheet_sync_v2.SHEET_MAP", {"3月-前台数据": "test"}),
        ):
            count = await sync.import_performance_sheet()

        # Should resolve "Ah YIM" → "阿YIM" via NAME_ALIASES
        assert count == 1


class TestGroupInteractionsGap:
    """Document that group_interactions (Phase 26) is NOT populated by sheet_sync_v2.

    group_interactions is defined at database_v2.py:873-890 as a Phase 26 table,
    but sheet_sync_v2.py does not import data into it. This test documents
    the gap — the table exists but has no sync path from Google Sheets.
    """

    @pytest.mark.asyncio
    async def test_group_interactions_table_exists_but_empty(self, populated_v2_db):
        """Verify group_interactions table exists but has no sync path."""
        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()

        # Table should exist (created by schema)
        c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='group_interactions'"
        )
        assert c.fetchone() is not None, "group_interactions table should exist"

        # But it's never populated by sheet sync
        c.execute("SELECT COUNT(*) FROM group_interactions")
        assert c.fetchone()[0] == 0

        conn.close()


class TestPipelineKillPreservation:
    """Test that kill_type/kill_knife are preserved on re-sync with empty note."""

    @pytest.mark.asyncio
    async def test_pipeline_preserves_kill_on_resync_with_no_kill(
        self, populated_v2_db
    ):
        """Test re-sync with empty note doesn't wipe existing kill_type."""
        sync = SheetSyncV2(Mock())
        client_id = populated_v2_db._test_client1_id

        # First sync: salary_kill with knife 6
        row1 = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "1000",
                "0",
                "工资杀6刀",
            ]
            + [""] * 8
            + ["1000"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row1, note="工资杀6刀"
            )
            await db.commit()

        # Second sync: no kill in note — should preserve existing kill
        row2 = (
            [
                "date",
                "acc1",
                "group",
                "阿YIM",
                "",
                "123",
                "Iconnect",
                "2000",
                "0",
                "all good",
            ]
            + [""] * 8
            + ["2000"]
        )
        async with populated_v2_db.get_connection() as db:
            await sync._sync_pipeline_for_client(
                db, client_id=client_id, row=row2, note="all good"
            )
            await db.commit()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT kill_type, kill_knife FROM client_pipeline_status"
            f" WHERE client_id={client_id}"
        )
        result = c.fetchone()
        conn.close()

        # kill_type and kill_knife should be preserved via COALESCE
        assert result[0] == "salary_kill"
        assert result[1] == 6


class TestFinancialSheetRealisticRow:
    """Test import_financial_sheet with a realistic row combining all fields."""

    @pytest.fixture
    def mock_writer(self):
        writer = Mock()
        writer.spreadsheet = Mock()
        return writer

    @pytest.mark.asyncio
    async def test_realistic_row_populates_all_subtables(
        self, populated_v2_db, mock_writer
    ):
        """A single realistic 維護數據 row should populate knives + pipeline + roles + notes."""
        client_id = populated_v2_db._test_client1_id
        staff2_id = populated_v2_db._test_staff2_id

        mock_ws = Mock()
        mock_ws.get_all_values.return_value = [
            # Header
            [
                "日期",
                "account_id",
                "group",
                "frontdesk",
                "maintenance",
                "fd_num",
                "platform",
                "new_order",
                "pressure",
                "note",
                "k1",
                "k2",
                "k3",
                "k4",
                "k5",
                "k6",
                "k7",
                "k8",
                "total_in",
                "T",
                "U",
                "V",
                "W",
                "X",
                "Y",
                "Z",
            ],
            # Realistic data row: has knives, kill note, cross-role notes, maintenance
            [
                "04/02/2026",
                "ACC001",
                "group",
                "阿YIM",
                "小王",
                "123",
                "Iconnect",
                "$1,500",
                "$800",
                "承压杀4刀",
                "$100",
                "$200",
                "$300",
                "$400",
                "$500",
                "",
                "",
                "",
                "$3,300",
                "前台已联系",
                "",
                "小白已培训",
                "",
                "客服跟进中",
                "维护中",
                "",
            ],
        ]
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        sync = SheetSyncV2(mock_writer)

        with patch("engines.sheet_sync_v2.database_v2", populated_v2_db):
            await sync.import_financial_sheet()

        conn = sqlite3.connect(populated_v2_db.db_path)
        c = conn.cursor()

        # Verify knife_deposits
        c.execute(f"SELECT COUNT(*) FROM knife_deposits WHERE client_id={client_id}")
        knife_count = c.fetchone()[0]
        assert knife_count == 5  # k1-k5 have values

        # Verify pipeline with kill detection
        c.execute(
            "SELECT new_order_amount, pressure_amount, kill_type, kill_knife, total_deposited"
            f" FROM client_pipeline_status WHERE client_id={client_id}"
        )
        pipeline = c.fetchone()
        assert pipeline is not None
        assert pipeline[0] == 1500.0
        assert pipeline[1] == 800.0
        assert pipeline[2] == "pressure_kill"
        assert pipeline[3] == 4
        assert pipeline[4] == 3300.0

        # Verify role assignments — both frontdesk and maintenance
        c.execute(
            "SELECT role_type FROM client_role_assignments"
            f" WHERE client_id={client_id} ORDER BY role_type"
        )
        roles = [r[0] for r in c.fetchall()]
        assert "frontdesk" in roles
        assert "maintenance" in roles

        # Verify cross_role_notes — 4 non-empty notes at indices 19, 21, 23, 24
        c.execute(
            "SELECT from_role, content FROM cross_role_notes"
            f" WHERE client_id={client_id} ORDER BY from_role"
        )
        notes = c.fetchall()
        note_roles = [n[0] for n in notes]
        assert "frontdesk" in note_roles
        assert "newbie" in note_roles
        assert "customer_service" in note_roles
        assert "maintenance" in note_roles
        assert len(notes) == 4

        conn.close()

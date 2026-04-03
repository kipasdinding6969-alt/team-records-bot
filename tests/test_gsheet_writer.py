"""Tests for engines/gsheet_writer.py — Google Sheets write operations.

All gspread interactions are fully mocked.
"""
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_worksheet(rows=None):
    """Build a mock gspread Worksheet with configurable data."""
    ws = MagicMock()
    ws.get_all_values.return_value = rows or []
    ws.update = MagicMock()
    ws.title = "TestSheet"
    ws.id = 12345
    return ws


def _make_writer(worksheets=None):
    """Instantiate GSheetWriter with mocked gspread connection."""
    with patch("engines.gsheet_writer.gspread") as mock_gs:
        mock_gc = MagicMock()
        mock_spreadsheet = MagicMock()

        if worksheets is not None:
            mock_spreadsheet.worksheets.return_value = worksheets
            mock_spreadsheet.worksheet = MagicMock(
                side_effect=lambda name: next(
                    (ws for ws in worksheets if ws.title == name), None
                )
            )
        else:
            mock_spreadsheet.worksheets.return_value = []
            mock_spreadsheet.worksheet = MagicMock(return_value=_make_mock_worksheet())

        mock_spreadsheet.title = "Test Spreadsheet"
        mock_gc.open_by_key.return_value = mock_spreadsheet
        mock_gs.service_account.return_value = mock_gc

        from engines.gsheet_writer import GSheetWriter
        writer = GSheetWriter()
        writer.initialize()
        return writer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGSheetWriterInitialize:
    def test_initialize_success(self):
        """initialize() connects to Google Sheets and returns True."""
        writer = _make_writer()
        assert writer.gc is not None
        assert writer.spreadsheet is not None

    def test_initialize_failure_returns_false(self):
        """initialize() returns False when gspread raises."""
        with patch("engines.gsheet_writer.gspread") as mock_gs:
            mock_gs.service_account.side_effect = Exception("bad credentials")
            from engines.gsheet_writer import GSheetWriter
            writer = GSheetWriter()
            result = writer.initialize()
            assert result is False


class TestReadClientSheet:
    def test_read_client_sheet_parses_rows(self):
        """read_client_sheet returns parsed records, skipping headers."""
        header1 = ["", "header", "h", "h", "h", "h", "h", "h", "h", "h", "h", "h", "h"]
        header2 = ["", "DATE", "", "", "", "", "", "", "", "", "", "", ""]
        data_row = [
            "1", "3月15日", "IPHONE", "阿YIM", "飞机筛选", "小王",
            "+861234", "@user", "+869876", "ACC123", "注册", "注册", "培训中",
        ]
        ws = _make_mock_worksheet(rows=[header1, header2, data_row])
        ws.title = "阿YIM"
        writer = _make_writer(worksheets=[ws])

        records = writer.read_client_sheet("阿YIM")
        assert len(records) == 1
        assert records[0]["date"] == "3月15日"
        assert records[0]["frontdesk"] == "阿YIM"
        assert records[0]["account_id"] == "ACC123"

    def test_read_client_sheet_skips_template_rows(self):
        """Rows with 'X月X日' in the date column are skipped."""
        header1 = [""] * 13
        header2 = [""] * 13
        template_row = ["1", "X月X日", "", "", "", "", "", "", "", "", "", "", ""]
        ws = _make_mock_worksheet(rows=[header1, header2, template_row])
        ws.title = "阿YIM"
        writer = _make_writer(worksheets=[ws])

        records = writer.read_client_sheet("阿YIM")
        assert len(records) == 0

    def test_read_client_sheet_error_returns_empty(self):
        """If worksheet raises, return empty list."""
        ws = _make_mock_worksheet()
        ws.title = "阿YIM"
        ws.get_all_values.side_effect = Exception("API error")
        writer = _make_writer(worksheets=[ws])

        records = writer.read_client_sheet("阿YIM")
        assert records == []


class TestAppendClientRecord:
    def test_append_finds_empty_row_and_writes(self):
        """append_client_record writes to first empty row."""
        header1 = [""] * 13
        header2 = [""] * 13
        data_row = ["1", "3月15日", "P", "F", "C", "R", "N", "U", "C", "A", "注册", "注册", "OK"]
        empty_row = ["", "", "", "", "", "", "", "", "", "", "", "", ""]
        ws = _make_mock_worksheet(rows=[header1, header2, data_row, empty_row])
        ws.title = "阿YIM"
        writer = _make_writer(worksheets=[ws])

        record = {
            "date": "3月16日",
            "phone_remark": "SAMSUNG",
            "category": "RCS筛选",
        }
        result = writer.append_client_record("阿YIM", record)
        assert result is True
        ws.update.assert_called_once()
        call_args = ws.update.call_args
        assert "A4" in call_args[0][0]  # Row 4 (0-indexed row 3 → 1-indexed 4)

    def test_append_to_unknown_sheet_returns_false_on_error(self):
        """Appending to a non-existent sheet returns False."""
        ws = _make_mock_worksheet()
        ws.title = "阿YIM"
        writer = _make_writer(worksheets=[ws])
        # worksheet() will return None for unknown name, causing AttributeError
        writer.spreadsheet.worksheet = MagicMock(side_effect=Exception("not found"))

        result = writer.append_client_record("UNKNOWN", {"date": "3月16日"})
        assert result is False


class TestUpdateClientStatus:
    def test_update_first_day(self):
        """update_client_status writes to column K for first_day."""
        ws = _make_mock_worksheet()
        ws.title = "阿YIM"
        writer = _make_writer(worksheets=[ws])

        result = writer.update_client_status("阿YIM", row_index=5, first_day="注册")
        assert result is True
        ws.update.assert_called_once_with("K5", [["注册"]])

    def test_update_multiple_fields(self):
        """update_client_status writes multiple cells when multiple fields given."""
        ws = _make_mock_worksheet()
        ws.title = "阿YIM"
        writer = _make_writer(worksheets=[ws])

        result = writer.update_client_status(
            "阿YIM", row_index=5,
            first_day="注册", second_day="注册", condition="培训中"
        )
        assert result is True
        assert ws.update.call_count == 3

    def test_update_permission_error_raises(self):
        """403 errors are re-raised for caller detection."""
        ws = _make_mock_worksheet()
        ws.title = "阿YIM"
        ws.update.side_effect = Exception("403 Forbidden: insufficient permission")
        writer = _make_writer(worksheets=[ws])

        with pytest.raises(Exception, match="403"):
            writer.update_client_status("阿YIM", row_index=5, first_day="注册")

    def test_update_generic_error_returns_false(self):
        """Non-permission errors return False."""
        ws = _make_mock_worksheet()
        ws.title = "阿YIM"
        ws.update.side_effect = Exception("network timeout")
        writer = _make_writer(worksheets=[ws])

        result = writer.update_client_status("阿YIM", row_index=5, first_day="注册")
        assert result is False


class TestAppendFinancialRecord:
    def test_append_financial_record_formats_money(self):
        """Financial record formats currency values correctly."""
        header = ["date"] + [""] * 18
        empty_row = ["X月XX日"] + [""] * 18
        ws = _make_mock_worksheet(rows=[header, empty_row])
        ws.title = "维护数据"
        writer = _make_writer(worksheets=[ws])

        record = {
            "date": "3月15日",
            "account_id": "ACC123",
            "group_id": "GRP456",
            "frontdesk": "阿YIM",
            "maintenance": "维护员",
            "frontdesk_number": "+861234",
            "platform": "Iconnect",
            "new_order_amount": 1000,
            "pressure_amount": 500,
            "note": "测试",
            "total_in": 1500,
        }
        result = writer.append_financial_record(record)
        assert result is True
        ws.update.assert_called_once()
        row_data = ws.update.call_args[0][1][0]
        assert "$1,000" in row_data[7]  # new_order_amount
        assert "$500" in row_data[8]  # pressure_amount


class TestGetSheetStats:
    def test_get_sheet_stats_aggregates(self):
        """get_sheet_stats returns correct counts per sheet."""
        ws1 = _make_mock_worksheet(rows=[["a", "b"], ["", ""], ["c", "d"]])
        ws1.title = "Sheet1"
        ws1.id = 111
        ws2 = _make_mock_worksheet(rows=[["x", "y"]])
        ws2.title = "Sheet2"
        ws2.id = 222
        writer = _make_writer(worksheets=[ws1, ws2])

        stats = writer.get_sheet_stats()
        assert stats["sheets"]["Sheet1"]["total_rows"] == 3
        assert stats["sheets"]["Sheet1"]["non_empty"] == 2  # rows with non-empty cells
        assert stats["sheets"]["Sheet2"]["total_rows"] == 1
        assert stats["total_records"] == 3  # 2 + 1

    def test_get_sheet_stats_error_per_sheet(self):
        """If one sheet errors, it's marked with error but others still work."""
        ws1 = _make_mock_worksheet(rows=[["a"]])
        ws1.title = "Good"
        ws1.id = 1
        ws2 = _make_mock_worksheet()
        ws2.title = "Bad"
        ws2.id = 2
        ws2.get_all_values.side_effect = Exception("API limit")
        writer = _make_writer(worksheets=[ws1, ws2])

        stats = writer.get_sheet_stats()
        assert stats["sheets"]["Good"]["total_rows"] == 1
        assert stats["sheets"]["Bad"]["error"] is True

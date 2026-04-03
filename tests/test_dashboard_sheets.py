"""Tests for engines/dashboard_sheets.py — DashboardSheets class and helpers."""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime, timedelta

from engines.dashboard_sheets import (
    DashboardSheets,
    TEAM_STRUCTURE,
    STATUS_EMOJIS,
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    PIPELINE_STATUSES,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_writer():
    writer = Mock()
    writer.spreadsheet = MagicMock()
    return writer


@pytest.fixture
def dashboard(mock_writer):
    return DashboardSheets(mock_writer)


# ── Constants ────────────────────────────────────────────────────────────────

class TestConstants:

    def test_team_structure_has_teams(self):
        assert len(TEAM_STRUCTURE) >= 1
        for team, members in TEAM_STRUCTURE.items():
            assert isinstance(members, list)

    def test_status_emojis_cover_common_statuses(self):
        for s in ['new', 'contacted', 'replied', 'registered', 'training', 'dead']:
            assert s in STATUS_EMOJIS

    def test_active_statuses_list(self):
        assert 'new' in ACTIVE_STATUSES
        assert 'dead' not in ACTIVE_STATUSES

    def test_terminal_statuses_list(self):
        assert 'dead' in TERMINAL_STATUSES
        assert 'new' not in TERMINAL_STATUSES

    def test_pipeline_statuses_order(self):
        assert PIPELINE_STATUSES[0] == 'new'
        assert 'ordered' in PIPELINE_STATUSES


# ── Helpers ──────────────────────────────────────────────────────────────────

class TestHelpers:

    def test_fmt_pct_normal(self, dashboard):
        assert dashboard._fmt_pct(3, 10) == '30.0%'

    def test_fmt_pct_zero_denominator(self, dashboard):
        assert dashboard._fmt_pct(5, 0) == '0%'

    def test_fmt_pct_zero_numerator(self, dashboard):
        assert dashboard._fmt_pct(0, 10) == '0.0%'

    def test_days_since_recent(self, dashboard):
        ts = (datetime.now() - timedelta(days=2)).isoformat()
        assert dashboard._days_since(ts) == 2

    def test_days_since_none(self, dashboard):
        assert dashboard._days_since(None) == 999

    def test_days_since_bad_format(self, dashboard):
        assert dashboard._days_since('not-a-date') == 999

    def test_fmt_date_normal(self, dashboard):
        result = dashboard._fmt_date('2024-03-15T10:30:00')
        assert 'Mar' in result and '15' in result

    def test_fmt_date_none(self, dashboard):
        assert dashboard._fmt_date(None) == ''

    def test_fmt_date_bad_format(self, dashboard):
        assert dashboard._fmt_date('invalid') == ''


# ── Worksheet helpers ────────────────────────────────────────────────────────

class TestWorksheetHelpers:

    def test_get_or_create_ws_existing(self, dashboard, mock_writer):
        existing_ws = Mock()
        mock_writer.spreadsheet.worksheet.return_value = existing_ws
        result = dashboard._get_or_create_ws('Test Tab')
        assert result is existing_ws

    def test_get_or_create_ws_new(self, dashboard, mock_writer):
        import gspread
        mock_writer.spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound('not found')
        new_ws = Mock()
        mock_writer.spreadsheet.add_worksheet.return_value = new_ws
        result = dashboard._get_or_create_ws('New Tab')
        assert result is new_ws
        mock_writer.spreadsheet.add_worksheet.assert_called_once()

    def test_protect_worksheet_error_handled(self, dashboard, mock_writer):
        """Protection errors should be silently caught."""
        ws = Mock(id=1, title='Test')
        mock_writer.spreadsheet.batch_update.side_effect = Exception('API error')
        # Should not raise
        dashboard._protect_worksheet(ws)


# ── refresh_all_tabs ─────────────────────────────────────────────────────────

class TestRefreshAllTabs:

    @pytest.mark.asyncio
    async def test_refresh_all_tabs_no_spreadsheet(self, mock_writer):
        mock_writer.spreadsheet = None
        ds = DashboardSheets(mock_writer)
        # Should return early without errors
        await ds.refresh_all_tabs()

    @pytest.mark.asyncio
    async def test_refresh_all_tabs_permission_error(self, dashboard, mock_writer):
        """Permission error on first tab should skip remaining."""
        async def raise_403():
            raise Exception('403 Forbidden: permission denied')

        with patch.object(dashboard, 'refresh_tab1_pipeline', side_effect=raise_403), \
             patch('engines.dashboard_sheets.asyncio.sleep', new_callable=AsyncMock):
            await dashboard.refresh_all_tabs()
            # Should have set _perm_warned flag
            assert getattr(dashboard, '_perm_warned', False)

    @pytest.mark.asyncio
    async def test_refresh_all_tabs_non_permission_error(self, dashboard, mock_writer):
        """Non-permission errors should log but continue."""
        call_count = {'tab1': 0, 'tab2': 0}

        async def fail_tab1():
            call_count['tab1'] += 1
            raise Exception('some other error')

        async def succeed_tab2():
            call_count['tab2'] += 1

        with patch.object(dashboard, 'refresh_tab1_pipeline', side_effect=fail_tab1), \
             patch.object(dashboard, 'refresh_tab2_live_clients', side_effect=succeed_tab2), \
             patch.object(dashboard, 'refresh_tab3_revenue', new_callable=AsyncMock), \
             patch.object(dashboard, 'refresh_tab4_scoreboard', new_callable=AsyncMock), \
             patch.object(dashboard, 'refresh_tab5_action_required', new_callable=AsyncMock), \
             patch('engines.dashboard_sheets.asyncio.sleep', new_callable=AsyncMock):
            mock_writer.spreadsheet.worksheet = Mock(return_value=Mock(id=1))
            await dashboard.refresh_all_tabs()
            assert call_count['tab1'] == 1
            assert call_count['tab2'] == 1


# ── Tab 1: Pipeline Dashboard ───────────────────────────────────────────────

class TestTab1Pipeline:

    @pytest.mark.asyncio
    async def test_refresh_tab1_writes_data(self, dashboard, mock_writer):
        mock_ws = Mock()
        mock_writer.spreadsheet.worksheet.return_value = mock_ws

        # Mock DB connection
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch('engines.dashboard_sheets.db') as mock_db:
            mock_db.get_connection = Mock(return_value=mock_conn)
            await dashboard.refresh_tab1_pipeline()

        mock_ws.clear.assert_called_once()
        mock_ws.update.assert_called_once()
        # Verify first row contains title
        rows = mock_ws.update.call_args[0][1]
        assert 'PIPELINE DASHBOARD' in rows[0][0]


# ── Module-level singleton ───────────────────────────────────────────────────

class TestModuleSingleton:

    def test_dashboard_sheets_is_none_initially(self):
        from engines.dashboard_sheets import dashboard_sheets
        # At import time, it's None (set by main.py later)
        assert dashboard_sheets is None

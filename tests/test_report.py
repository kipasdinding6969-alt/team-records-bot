"""Phase 10B: Advanced analytics & report tests."""
import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import (
    Client, ClientNote, ClientStatus, Deposit, NoteType, Staff, StaffRole,
)


@pytest_asyncio.fixture
async def db(tmp_path):
    db_file = str(tmp_path / 'test_report.db')
    d = DatabaseV2(db_file)
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def staff_row(db):
    s = Staff(tg_user_id=5001, tg_chat_id=6001, display_name='ReportStaff',
              role=StaffRole.FRONTDESK, team='阿俊', language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def staff_row2(db):
    s = Staff(tg_user_id=5002, tg_chat_id=6002, display_name='ReportStaff2',
              role=StaffRole.FRONTDESK, team='阿俊', language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager_row(db):
    s = Staff(tg_user_id=5003, tg_chat_id=6003, display_name='ReportMgr',
              role=StaffRole.MANAGER, team='阿俊', language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def populated_db(db, staff_row, staff_row2):
    """DB with clients and deposits for analytics queries."""
    today = date.today()
    # Create clients with various statuses
    for i in range(5):
        c = Client(frontdesk_id=staff_row.id, phone=f'900{i}', source='telegram')
        cid = await db.create_client(c)
        if i < 3:
            await db.update_client_status(cid, ClientStatus.CONTACTED, staff_row.id)
        if i < 2:
            await db.update_client_status(cid, ClientStatus.REGISTERED, staff_row.id)

    # Clients for staff2
    for i in range(3):
        c = Client(frontdesk_id=staff_row2.id, phone=f'800{i}', source='facebook')
        cid = await db.create_client(c)
        if i < 2:
            await db.update_client_status(cid, ClientStatus.CONTACTED, staff_row2.id)

    # Deposits
    for i in range(3):
        c = Client(frontdesk_id=staff_row.id, phone=f'700{i}', source='telegram')
        cid = await db.create_client(c)
        d = Deposit(client_id=cid, frontdesk_id=staff_row.id, amount=100 * (i + 1),
                    deposit_date=today)
        await db.create_deposit(d)

    return db


class TestPipelineStats:
    @pytest.mark.asyncio
    async def test_pipeline_stats_returns_counts(self, populated_db, staff_row):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        stats = await populated_db.get_pipeline_stats(start, end)
        assert isinstance(stats, dict)
        # We created clients, some should appear
        total = sum(stats.values())
        assert total > 0

    @pytest.mark.asyncio
    async def test_pipeline_stats_empty_period(self, populated_db):
        stats = await populated_db.get_pipeline_stats('2020-01-01', '2020-01-02')
        assert sum(stats.values()) == 0

    @pytest.mark.asyncio
    async def test_pipeline_stats_team_filter(self, populated_db, staff_row):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        stats = await populated_db.get_pipeline_stats(start, end, team='阿俊')
        total = sum(stats.values())
        assert total > 0


class TestConversionRates:
    @pytest.mark.asyncio
    async def test_conversion_rates_structure(self, populated_db):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        rates = await populated_db.get_conversion_rates(start, end)
        assert 'total' in rates
        assert 'contacted' in rates
        assert 'replied' in rates
        assert 'registered' in rates
        assert 'deposited' in rates
        assert 'contact_rate' in rates
        assert 'reply_rate' in rates

    @pytest.mark.asyncio
    async def test_conversion_rates_values(self, populated_db):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        rates = await populated_db.get_conversion_rates(start, end)
        assert rates['total'] > 0
        assert rates['contacted'] <= rates['total']
        assert rates['registered'] <= rates['contacted']

    @pytest.mark.asyncio
    async def test_conversion_rates_empty(self, db):
        rates = await db.get_conversion_rates('2020-01-01', '2020-01-02')
        assert rates['total'] == 0
        assert rates['contact_rate'] == 0


class TestStaffRankings:
    @pytest.mark.asyncio
    async def test_rankings_by_deposits(self, populated_db, staff_row):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        rankings = await populated_db.get_staff_rankings(start, end, metric='deposits')
        assert isinstance(rankings, list)
        assert len(rankings) > 0
        # First should have most deposits
        assert rankings[0]['total_amount'] >= rankings[-1]['total_amount']

    @pytest.mark.asyncio
    async def test_rankings_by_new_clients(self, populated_db):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        rankings = await populated_db.get_staff_rankings(start, end, metric='new_clients')
        assert isinstance(rankings, list)

    @pytest.mark.asyncio
    async def test_rankings_team_filter(self, populated_db):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        rankings = await populated_db.get_staff_rankings(start, end, team='阿俊', metric='deposits')
        for r in rankings:
            assert isinstance(r['display_name'], str)


class TestSourceAnalysis:
    @pytest.mark.asyncio
    async def test_source_analysis(self, populated_db):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        sources = await populated_db.get_source_analysis(start, end)
        assert isinstance(sources, list)
        assert len(sources) > 0
        # Check structure
        for s in sources:
            assert 'source' in s
            assert 'total' in s
            assert 'converted' in s
            assert 'conversion_rate' in s

    @pytest.mark.asyncio
    async def test_source_analysis_empty(self, db):
        sources = await db.get_source_analysis('2020-01-01', '2020-01-02')
        assert len(sources) == 0


class TestPeriodComparison:
    @pytest.mark.asyncio
    async def test_comparison_structure(self, populated_db):
        today = date.today()
        p1_start = (today - timedelta(days=7)).isoformat()
        p1_end = today.isoformat()
        p2_start = (today - timedelta(days=14)).isoformat()
        p2_end = (today - timedelta(days=7)).isoformat()
        comp = await populated_db.get_period_comparison(p1_start, p1_end, p2_start, p2_end)
        for key in ['total', 'contacted', 'replied', 'registered', 'deposited']:
            assert key in comp
            assert 'current' in comp[key]
            assert 'previous' in comp[key]
            assert 'delta' in comp[key]
            assert 'pct_change' in comp[key]

    @pytest.mark.asyncio
    async def test_comparison_delta_sign(self, populated_db):
        today = date.today()
        # Current period has data, past period is empty
        p1_start = (today - timedelta(days=1)).isoformat()
        p1_end = (today + timedelta(days=1)).isoformat()
        p2_start = '2020-01-01'
        p2_end = '2020-01-07'
        comp = await populated_db.get_period_comparison(p1_start, p1_end, p2_start, p2_end)
        assert comp['total']['delta'] > 0  # Current has more data


class TestDepositTotal:
    @pytest.mark.asyncio
    async def test_deposit_total(self, populated_db):
        today = date.today()
        start = (today - timedelta(days=1)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        total = await populated_db.get_deposit_total(start, end)
        assert total == 600.0  # 100 + 200 + 300

    @pytest.mark.asyncio
    async def test_deposit_total_empty(self, db):
        total = await db.get_deposit_total('2020-01-01', '2020-01-02')
        assert total == 0.0


class TestStaleClientsAnalytics:
    @pytest.mark.asyncio
    async def test_stale_clients_returns_list(self, populated_db):
        # All clients were just created, so with days=0 they won't be stale
        stale = await populated_db.get_stale_clients_analytics(days=0)
        # With days=0, all active clients should be "stale"
        assert isinstance(stale, list)

    @pytest.mark.asyncio
    async def test_stale_clients_structure(self, populated_db):
        stale = await populated_db.get_stale_clients_analytics(days=0)
        if stale:
            assert 'id' in stale[0]
            assert 'staff_name' in stale[0]


class TestReportFormatting:
    def test_bar_rendering(self):
        from handlers_v2.report_handler import _bar
        bar = _bar(10, 10, width=10)
        assert len(bar) == 10
        bar_half = _bar(5, 10, width=10)
        assert len(bar_half) == 5
        bar_zero = _bar(0, 0, width=10)
        assert bar_zero == ''

    def test_week_range(self):
        from handlers_v2.report_handler import _week_range
        start, end = _week_range(datetime(2026, 3, 30))
        assert start < end

    def test_month_range(self):
        from handlers_v2.report_handler import _month_range
        start, end = _month_range(datetime(2026, 3, 15))
        assert start == '2026-03-01'
        assert end == '2026-03-31'

    def test_month_range_december(self):
        from handlers_v2.report_handler import _month_range
        start, end = _month_range(datetime(2026, 12, 15))
        assert start == '2026-12-01'
        assert end == '2026-12-31'

    def test_parse_period_week(self):
        from handlers_v2.report_handler import _parse_period
        start, end = _parse_period('2026-W13')
        assert start is not None
        assert end is not None

    def test_parse_period_month(self):
        from handlers_v2.report_handler import _parse_period
        start, end = _parse_period('2026-03')
        assert start == '2026-03-01'

    def test_parse_period_invalid(self):
        from handlers_v2.report_handler import _parse_period
        with pytest.raises(ValueError):
            _parse_period('invalid')

    def test_format_funnel_text(self):
        from handlers_v2.report_handler import format_funnel_text
        rates = {'total': 100, 'contacted': 80, 'replied': 60,
                 'registered': 40, 'deposited': 20}
        text = format_funnel_text(rates, '2026-03-24', '2026-03-30')
        assert 'Funnel' in text
        assert '100' in text
        assert '80' in text

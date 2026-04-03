"""Tests for engines/report_engine.py — daily/weekly/performance/financial/client-status reports."""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from engines.report_engine import ReportEngine
from models import ReportTemplate


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _fake_client_record(frontdesk='阿YIM', date_str='03月15日',
                        first_day='注册', second_day='注册', note=None):
    """Return a lightweight mock ClientRecord."""
    r = Mock()
    r.date = date_str
    r.frontdesk = frontdesk
    r.first_day = first_day
    r.second_day = second_day
    r.client_condition = '培训中'
    return r


def _fake_financial_record(frontdesk='阿YIM', new_order_amount=100.0,
                            pressure_amount=50.0, total_in=150.0, note=None):
    fr = Mock()
    fr.frontdesk = frontdesk
    fr.new_order_amount = new_order_amount
    fr.pressure_amount = pressure_amount
    fr.total_in = total_in
    fr.note = note
    return fr


class TestReportEngineInit:
    def test_template_registry_contains_all_types(self):
        engine = ReportEngine()
        expected = {'daily_summary', 'weekly_assessment', 'performance_analysis',
                    'financial_overview', 'client_status'}
        assert set(engine.template_registry.keys()) == expected

    def test_generate_report_dispatches(self):
        engine = ReportEngine()
        for ttype in engine.template_registry:
            assert callable(engine.template_registry[ttype])


class TestGenerateReport:
    @pytest.fixture
    def engine(self):
        return ReportEngine()

    @pytest.mark.asyncio
    async def test_unknown_template_raises(self, engine):
        template = ReportTemplate(template_type='nonexistent', parameters={})
        with pytest.raises(ValueError, match='Unknown report template'):
            await engine.generate_report(template)

    @pytest.mark.asyncio
    async def test_metadata_added_to_report(self, engine):
        """generate_report adds metadata to the result dict."""
        template = ReportTemplate(template_type='financial_overview',
                                  parameters={'date': date.today()})
        mock_db = MagicMock()
        mock_db.get_financial_records_by_date = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_report(template)
        assert 'metadata' in result
        assert result['metadata']['template_type'] == 'financial_overview'
        assert 'generated_at' in result['metadata']


class TestDailySummaryReport:
    @pytest.fixture
    def engine(self):
        return ReportEngine()

    def _mock_db(self, frontdesk_names, client_records_map, financial_records):
        """Build a mock database with team_members and client/financial records."""
        mock_db = MagicMock()

        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[(n,) for n in frontdesk_names])
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=cursor)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_db.get_connection = MagicMock(return_value=cm)

        mock_db.get_client_records_by_frontdesk = AsyncMock(
            side_effect=lambda name: client_records_map.get(name, []))
        mock_db.get_financial_records_by_date = AsyncMock(return_value=financial_records)
        return mock_db

    @pytest.mark.asyncio
    async def test_daily_summary_with_data(self, engine):
        today_str = date.today().strftime('%m月%d日')
        records = [_fake_client_record(date_str=today_str, first_day='注册', second_day='注册')]
        financial = [_fake_financial_record(note='提款', new_order_amount=500)]
        mock_db = self._mock_db(['阿YIM'], {'阿YIM': records}, financial)

        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_daily_summary_report(
                ReportTemplate(template_type='daily_summary', parameters={'date': date.today()}))

        assert result['report_type'] == 'daily_summary'
        assert result['date'] == date.today()
        assert 'sections' in result
        assert 'totals' in result
        assert 'formatted_report' in result
        assert result['frontdesk_count'] == 1

    @pytest.mark.asyncio
    async def test_daily_summary_empty_data(self, engine):
        mock_db = self._mock_db([], {}, [])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_daily_summary_report(
                ReportTemplate(template_type='daily_summary', parameters={'date': date.today()}))
        assert result['frontdesk_count'] == 0
        assert result['sections']['today_stats'] == {}

    @pytest.mark.asyncio
    async def test_daily_summary_string_date(self, engine):
        mock_db = self._mock_db([], {}, [])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_daily_summary_report(
                ReportTemplate(template_type='daily_summary', parameters={'date': '2024-03-15'}))
        assert result['date'] == date(2024, 3, 15)

    @pytest.mark.asyncio
    async def test_daily_summary_date_range_filter(self, engine):
        """Only records matching the target date string are counted in today_stats."""
        today_str = date.today().strftime('%m月%d日')
        yesterday_str = (date.today() - timedelta(days=1)).strftime('%m月%d日')
        records = [
            _fake_client_record(date_str=today_str),
            _fake_client_record(date_str=yesterday_str),
        ]
        mock_db = self._mock_db(['阿YIM'], {'阿YIM': records}, [])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_daily_summary_report(
                ReportTemplate(template_type='daily_summary', parameters={'date': date.today()}))
        today_stats = result['sections']['today_stats']['阿YIM']
        assert today_stats['new_powder'] == 1  # only today's record

    @pytest.mark.asyncio
    async def test_formatted_report_contains_sections(self, engine):
        mock_db = self._mock_db(['阿YIM'], {'阿YIM': []}, [])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_daily_summary_report(
                ReportTemplate(template_type='daily_summary', parameters={'date': date.today()}))
        report_text = result['formatted_report']
        assert 'Section A' in report_text
        assert 'Section B' in report_text


class TestWeeklyAssessmentReport:
    @pytest.fixture
    def engine(self):
        return ReportEngine()

    @pytest.mark.asyncio
    async def test_weekly_report_structure(self, engine):
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            template = ReportTemplate(
                template_type='weekly_assessment',
                team_name='测试团队',
                parameters={'team_name': '测试团队', 'members': ['阿YIM'], 'end_date': date.today()})
            result = await engine.generate_weekly_assessment_report(template)

        assert result['report_type'] == 'weekly_assessment'
        assert result['team_name'] == '测试团队'
        assert 'assessment_data' in result
        assert '阿YIM' in result['assessment_data']['members']

    @pytest.mark.asyncio
    async def test_weekly_report_5_day_period(self, engine):
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            template = ReportTemplate(
                template_type='weekly_assessment',
                team_name='T',
                parameters={'members': ['A'], 'end_date': date(2024, 3, 15)})
            result = await engine.generate_weekly_assessment_report(template)

        ad = result['assessment_data']
        assert ad['start_date'] == date(2024, 3, 11)
        assert ad['end_date'] == date(2024, 3, 15)
        assert len(ad['members']['A']['daily_activity']) == 5

    @pytest.mark.asyncio
    async def test_weekly_team_totals_aggregation(self, engine):
        """Team totals sum across members."""
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            template = ReportTemplate(
                template_type='weekly_assessment',
                team_name='T',
                parameters={'members': ['A', 'B'], 'end_date': date.today()})
            result = await engine.generate_weekly_assessment_report(template)

        team_totals = result['assessment_data']['team_totals']
        assert 'daily_activity' in team_totals
        assert 'training_conversion' in team_totals

    @pytest.mark.asyncio
    async def test_formatted_weekly_report_output(self, engine):
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            template = ReportTemplate(
                template_type='weekly_assessment',
                team_name='测试团队',
                parameters={'members': ['阿YIM'], 'end_date': date.today()})
            result = await engine.generate_weekly_assessment_report(template)
        assert '5-Day Team Assessment' in result['formatted_report']
        assert '测试团队' in result['formatted_report']


class TestPerformanceAnalysisReport:
    @pytest.fixture
    def engine(self):
        return ReportEngine()

    @pytest.mark.asyncio
    async def test_performance_report_with_data(self, engine):
        records = [_fake_client_record(first_day='注册'), _fake_client_record(first_day='不注册')]
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=records)
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_performance_analysis_report(
                ReportTemplate(template_type='performance_analysis',
                               frontdesk='阿YIM', parameters={'frontdesk': '阿YIM'}))
        assert result['report_type'] == 'performance_analysis'
        assert result['frontdesk'] == '阿YIM'
        assert result['analysis']['total_clients'] == 2
        assert result['analysis']['registration_rate'] == 50.0

    @pytest.mark.asyncio
    async def test_performance_report_no_data(self, engine):
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_performance_analysis_report(
                ReportTemplate(template_type='performance_analysis',
                               frontdesk='NoOne', parameters={'frontdesk': 'NoOne'}))
        assert result.get('error') == 'No data found'

    @pytest.mark.asyncio
    async def test_performance_report_missing_frontdesk_raises(self, engine):
        with pytest.raises(ValueError, match='Frontdesk name required'):
            await engine.generate_performance_analysis_report(
                ReportTemplate(template_type='performance_analysis', parameters={}))

    @pytest.mark.asyncio
    async def test_performance_formatted_output(self, engine):
        records = [_fake_client_record(first_day='注册')]
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=records)
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_performance_analysis_report(
                ReportTemplate(template_type='performance_analysis',
                               frontdesk='阿YIM', parameters={'frontdesk': '阿YIM'}))
        assert 'Performance Analysis' in result['formatted_report']


class TestFinancialOverviewReport:
    @pytest.fixture
    def engine(self):
        return ReportEngine()

    @pytest.mark.asyncio
    async def test_financial_report_with_records(self, engine):
        records = [
            _fake_financial_record(new_order_amount=1000, pressure_amount=200, total_in=1200),
            _fake_financial_record(new_order_amount=500, pressure_amount=100, total_in=600),
        ]
        mock_db = MagicMock()
        mock_db.get_financial_records_by_date = AsyncMock(return_value=records)
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_financial_overview_report(
                ReportTemplate(template_type='financial_overview', parameters={'date': date.today()}))
        assert result['report_type'] == 'financial_overview'
        assert result['records_count'] == 2
        assert result['totals']['new_orders'] == 1500
        assert result['totals']['pressure'] == 300
        assert result['totals']['income'] == 1800

    @pytest.mark.asyncio
    async def test_financial_report_empty(self, engine):
        mock_db = MagicMock()
        mock_db.get_financial_records_by_date = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_financial_overview_report(
                ReportTemplate(template_type='financial_overview', parameters={'date': date.today()}))
        assert result['records_count'] == 0
        assert result['totals']['new_orders'] == 0

    @pytest.mark.asyncio
    async def test_financial_report_string_date(self, engine):
        mock_db = MagicMock()
        mock_db.get_financial_records_by_date = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_financial_overview_report(
                ReportTemplate(template_type='financial_overview', parameters={'date': '2024-01-01'}))
        assert result['date'] == date(2024, 1, 1)

    @pytest.mark.asyncio
    async def test_financial_report_formatted_output(self, engine):
        mock_db = MagicMock()
        mock_db.get_financial_records_by_date = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_financial_overview_report(
                ReportTemplate(template_type='financial_overview', parameters={'date': date.today()}))
        assert 'Financial Overview' in result['formatted_report']


class TestClientStatusReport:
    @pytest.fixture
    def engine(self):
        return ReportEngine()

    @pytest.mark.asyncio
    async def test_client_status_with_frontdesk(self, engine):
        records = [
            _fake_client_record(first_day='注册', second_day='注册'),
            _fake_client_record(first_day='不注册', second_day='不注册'),
            _fake_client_record(first_day='待定', second_day='待定'),
        ]
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=records)
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_client_status_report(
                ReportTemplate(template_type='client_status',
                               frontdesk='阿YIM', parameters={'frontdesk': '阿YIM'}))
        assert result['report_type'] == 'client_status'
        assert result['total_clients'] == 3
        assert result['status_breakdown']['registered'] == 1
        assert result['status_breakdown']['not_registered'] == 1

    @pytest.mark.asyncio
    async def test_client_status_all_records(self, engine):
        """When no frontdesk specified, fetches all records."""
        mock_db = MagicMock()

        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=cursor)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_db.get_connection = MagicMock(return_value=cm)
        mock_db._row_to_client_record = Mock(return_value=None)

        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_client_status_report(
                ReportTemplate(template_type='client_status', parameters={}))
        assert result['total_clients'] == 0

    @pytest.mark.asyncio
    async def test_client_status_formatted_output(self, engine):
        mock_db = MagicMock()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=[])
        with patch('engines.report_engine.database', mock_db):
            result = await engine.generate_client_status_report(
                ReportTemplate(template_type='client_status',
                               frontdesk='阿YIM', parameters={'frontdesk': '阿YIM'}))
        assert 'Client Status Report' in result['formatted_report']


class TestCalculateTeamTotals:
    def test_team_totals_empty_members(self):
        engine = ReportEngine()
        result = engine._calculate_team_totals({})
        assert result == {'daily_activity': {}, 'training_conversion': {}}

    def test_team_totals_sums_correctly(self):
        engine = ReportEngine()
        members = {
            'A': {'daily_totals': {'new_powder': 10, 'today_reply': 5},
                  'training_totals': {'today_training': 3, 'today_withdraw': 1}},
            'B': {'daily_totals': {'new_powder': 20, 'today_reply': 8},
                  'training_totals': {'today_training': 7, 'today_withdraw': 2}},
        }
        result = engine._calculate_team_totals(members)
        assert result['daily_activity']['new_powder'] == 30
        assert result['daily_activity']['today_reply'] == 13
        assert result['training_conversion']['today_training'] == 10


class TestFormatPerformanceReport:
    def test_excellent_rating(self):
        engine = ReportEngine()
        analysis = {'frontdesk': 'A', 'total_clients': 100,
                    'today_clients': 10, 'registration_rate': 80.0, 'response_rate': 90.0}
        text = engine._format_performance_report(analysis)
        assert '优秀' in text

    def test_good_rating(self):
        engine = ReportEngine()
        analysis = {'frontdesk': 'A', 'total_clients': 100,
                    'today_clients': 10, 'registration_rate': 60.0, 'response_rate': 90.0}
        text = engine._format_performance_report(analysis)
        assert '良好' in text

    def test_needs_improvement_rating(self):
        engine = ReportEngine()
        analysis = {'frontdesk': 'A', 'total_clients': 100,
                    'today_clients': 10, 'registration_rate': 30.0, 'response_rate': 90.0}
        text = engine._format_performance_report(analysis)
        assert '需改进' in text

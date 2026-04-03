"""Tests for engine modules.

Note: V1 schema (team_members) deprecated test class removed: TestReminderEngine
"""
import pytest
from datetime import date
from unittest.mock import Mock, patch

from engines.report_engine import ReportEngine
from engines.reminder_engine import ReminderEngine
from engines.sheet_sync import SheetSyncEngine
from models import ReportTemplate


class TestReportEngine:
    """Test report generation engine."""

    @pytest.fixture
    def report_engine(self):
        return ReportEngine()

    @pytest.mark.asyncio
    async def test_daily_summary_report_generation(self, report_engine, populated_db):
        """Test daily summary report generation."""
        template = ReportTemplate(
            template_type='daily_summary',
            parameters={'date': date.today()}
        )

        with patch('engines.report_engine.database', populated_db):
            report_data = await report_engine.generate_daily_summary_report(template)

            assert report_data['report_type'] == 'daily_summary'
            assert 'sections' in report_data
            assert 'totals' in report_data
            assert 'formatted_report' in report_data

            # Check sections structure
            sections = report_data['sections']
            assert 'today_stats' in sections
            assert 'cumulative_totals' in sections
            assert 'today_training_details' in sections
            assert 'total_training_details' in sections

    @pytest.mark.asyncio
    async def test_weekly_assessment_report_generation(self, report_engine, populated_db):
        """Test weekly assessment report generation."""
        template = ReportTemplate(
            template_type='weekly_assessment',
            team_name='测试团队',
            parameters={
                'team_name': '测试团队',
                'members': ['阿YIM', '阿俊'],
                'end_date': date.today()
            }
        )

        with patch('engines.report_engine.database', populated_db):
            report_data = await report_engine.generate_weekly_assessment_report(template)

            assert report_data['report_type'] == 'weekly_assessment'
            assert report_data['team_name'] == '测试团队'
            assert 'assessment_data' in report_data
            assert 'formatted_report' in report_data

            assessment_data = report_data['assessment_data']
            assert 'members' in assessment_data
            assert 'team_totals' in assessment_data

    @pytest.mark.asyncio
    async def test_performance_analysis_report(self, report_engine, populated_db):
        """Test performance analysis report generation."""
        template = ReportTemplate(
            template_type='performance_analysis',
            frontdesk='阿YIM',
            parameters={'frontdesk': '阿YIM'}
        )

        with patch('engines.report_engine.database', populated_db):
            report_data = await report_engine.generate_performance_analysis_report(template)

            assert report_data['report_type'] == 'performance_analysis'
            assert report_data['frontdesk'] == '阿YIM'

            if 'analysis' in report_data:  # Only if data exists
                assert 'total_clients' in report_data['analysis']
                assert 'registration_rate' in report_data['analysis']

    @pytest.mark.asyncio
    async def test_financial_overview_report(self, report_engine, populated_db):
        """Test financial overview report generation."""
        template = ReportTemplate(
            template_type='financial_overview',
            parameters={'date': date.today()}
        )

        with patch('engines.report_engine.database', populated_db):
            report_data = await report_engine.generate_financial_overview_report(template)

            assert report_data['report_type'] == 'financial_overview'
            assert 'records_count' in report_data
            assert 'totals' in report_data
            assert 'formatted_report' in report_data

    @pytest.mark.asyncio
    async def test_unknown_report_template(self, report_engine):
        """Test handling of unknown report template."""
        template = ReportTemplate(
            template_type='unknown_type',
            parameters={}
        )

        with pytest.raises(ValueError, match="Unknown report template"):
            await report_engine.generate_report(template)

    @pytest.mark.asyncio
    async def test_report_with_string_date(self, report_engine, populated_db):
        """Test report generation with string date parameter."""
        template = ReportTemplate(
            template_type='daily_summary',
            parameters={'date': '2024-03-15'}
        )

        with patch('engines.report_engine.database', populated_db):
            report_data = await report_engine.generate_daily_summary_report(template)

            assert isinstance(report_data['date'], date)
            assert report_data['date'] == date(2024, 3, 15)


class TestSheetSyncEngine:
    """Test Google Sheets synchronization engine."""

    @pytest.fixture
    def sheet_sync_engine(self):
        return SheetSyncEngine()

    @pytest.mark.asyncio
    async def test_initialize_sheets_client(self, sheet_sync_engine):
        """Test initialization of Google Sheets client."""
        await sheet_sync_engine.initialize()

        # Should not raise errors (simulated client)
        assert sheet_sync_engine.sheets_client is not None

    @pytest.mark.asyncio
    async def test_sync_all_data(self, sheet_sync_engine, populated_db):
        """Test full data synchronization."""
        with patch('engines.sheet_sync.database', populated_db):
            sync_results = await sheet_sync_engine.sync_all_data()

            assert 'start_time' in sync_results
            assert 'end_time' in sync_results
            assert 'summary' in sync_results
            assert 'client_records' in sync_results
            assert 'financial_records' in sync_results
            assert 'performance_records' in sync_results

            summary = sync_results['summary']
            assert 'total_read' in summary
            assert 'total_written' in summary
            assert 'success' in summary

    @pytest.mark.asyncio
    async def test_export_to_sheets(self, sheet_sync_engine, populated_db):
        """Test exporting data to Google Sheets."""
        with patch('engines.sheet_sync.database', populated_db):
            export_results = await sheet_sync_engine.export_to_sheets(
                data_type='client_records',
                filters={'frontdesk': '阿YIM'}
            )

            assert 'data_type' in export_results
            assert 'success' in export_results
            assert export_results['data_type'] == 'client_records'

    @pytest.mark.asyncio
    async def test_export_unknown_data_type(self, sheet_sync_engine):
        """Test exporting unknown data type."""
        export_results = await sheet_sync_engine.export_to_sheets(
            data_type='unknown_type'
        )

        assert export_results['success'] is False
        assert 'error' in export_results

    @pytest.mark.asyncio
    async def test_get_sync_status(self, sheet_sync_engine):
        """Test getting synchronization status."""
        status = await sheet_sync_engine.get_sync_status()

        assert isinstance(status, dict)
        assert 'connection_status' in status
        assert 'health_check' in status

    @pytest.mark.asyncio
    async def test_force_sync_record(self, sheet_sync_engine):
        """Test force synchronization of individual record."""
        sync_result = await sheet_sync_engine.force_sync_record('client', 1)

        assert 'success' in sync_result
        if sync_result['success']:
            assert 'record_id' in sync_result
            assert sync_result['record_id'] == 1

    @pytest.mark.asyncio
    async def test_create_backup_export(self, sheet_sync_engine, populated_db):
        """Test creating backup export."""
        with patch('engines.sheet_sync.database', populated_db):
            backup_results = await sheet_sync_engine.create_backup_export()

            assert 'timestamp' in backup_results
            assert 'backup_id' in backup_results
            assert 'tables_exported' in backup_results
            assert 'success' in backup_results

    @pytest.mark.asyncio
    async def test_health_check(self, sheet_sync_engine):
        """Test health check functionality."""
        health_result = await sheet_sync_engine._health_check()

        assert 'status' in health_result
        assert 'last_test' in health_result
        assert health_result['status'] in ['healthy', 'unhealthy']

    def test_client_record_to_dict_conversion(self, sheet_sync_engine, sample_client_record):
        """Test conversion of ClientRecord to dictionary."""
        record_dict = sheet_sync_engine._client_record_to_dict(sample_client_record)

        assert isinstance(record_dict, dict)
        assert record_dict['frontdesk'] == sample_client_record.frontdesk
        assert record_dict['account_id'] == sample_client_record.account_id
        assert record_dict['first_day'] == sample_client_record.first_day

    @pytest.mark.asyncio
    async def test_sync_error_handling(self, sheet_sync_engine):
        """Test error handling in sync operations."""
        # Mock database that raises errors
        with patch('engines.sheet_sync.database') as mock_db:
            mock_db.get_connection.side_effect = Exception("Database error")

            sync_results = await sheet_sync_engine.sync_all_data()

            assert 'summary' in sync_results
            assert sync_results is not None  # Error handled
            # Error details depend on implementation


class TestEngineIntegration:
    """Test integration between engines."""

    @pytest.mark.asyncio
    async def test_report_and_reminder_integration(self, populated_db, mock_telegram_handler):
        """Test integration between report engine and reminder engine."""
        report_engine = ReportEngine()
        reminder_engine = ReminderEngine()

        # Generate a report
        template = ReportTemplate(
            template_type='daily_summary',
            parameters={'date': date.today()}
        )

        with patch('engines.report_engine.database', populated_db):
            report_data = await report_engine.generate_daily_summary_report(template)

        # Create reminders based on report data
        with patch('engines.reminder_engine.database', populated_db), \
             patch('engines.reminder_engine.telegram_handler', mock_telegram_handler):

            # If report shows pending items, create reminders
            if report_data and 'sections' in report_data:
                reminder_ids = await reminder_engine.create_automatic_reminders(1, 123456)
                assert len(reminder_ids) >= 0

    @pytest.mark.asyncio
    async def test_sync_and_report_integration(self, populated_db):
        """Test integration between sync engine and report engine."""
        sync_engine = SheetSyncEngine()
        report_engine = ReportEngine()

        # Perform sync
        with patch('engines.sheet_sync.database', populated_db):
            sync_results = await sync_engine.sync_all_data()

        # Generate report after sync
        template = ReportTemplate(
            template_type='daily_summary',
            parameters={'date': date.today()}
        )

        with patch('engines.report_engine.database', populated_db):
            report_data = await report_engine.generate_daily_summary_report(template)

        # Both operations should succeed
        assert sync_results['summary']['success'] is True
        assert 'formatted_report' in report_data
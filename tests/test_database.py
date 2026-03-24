"""Tests for database operations."""
import pytest
import asyncio
from datetime import datetime, timedelta

from database import Database
from models import ClientRecord, FinancialRecord, PerformanceRecord, TeamMember, Reminder, BotTask


class TestDatabase:
    """Test database operations."""

    @pytest.mark.asyncio
    async def test_database_initialization(self, temp_db):
        """Test database initialization."""
        # Database should be initialized by fixture
        stats = await temp_db.get_stats()
        assert isinstance(stats, dict)
        assert all(table in stats for table in [
            'client_records', 'financial_records', 'performance_records',
            'team_members', 'reminders', 'bot_tasks'
        ])

    @pytest.mark.asyncio
    async def test_client_record_crud(self, temp_db, sample_client_record):
        """Test client record CRUD operations."""
        # Create
        record_id = await temp_db.create_client_record(sample_client_record)
        assert record_id > 0

        # Read
        records = await temp_db.get_client_records_by_frontdesk(sample_client_record.frontdesk)
        assert len(records) == 1
        retrieved_record = records[0]

        # Compare fields (excluding auto-generated ones)
        assert retrieved_record.date == sample_client_record.date
        assert retrieved_record.frontdesk == sample_client_record.frontdesk
        assert retrieved_record.client_number == sample_client_record.client_number
        assert retrieved_record.account_id == sample_client_record.account_id
        assert retrieved_record.first_day == sample_client_record.first_day
        assert retrieved_record.second_day == sample_client_record.second_day

        # Update
        await temp_db.update_client_record_status(record_id, first_day="不注册")
        updated_records = await temp_db.get_client_records_by_frontdesk(sample_client_record.frontdesk)
        assert updated_records[0].first_day == "不注册"

    @pytest.mark.asyncio
    async def test_financial_record_crud(self, temp_db, sample_financial_record):
        """Test financial record CRUD operations."""
        # Create
        record_id = await temp_db.create_financial_record(sample_financial_record)
        assert record_id > 0

        # Read
        records = await temp_db.get_financial_records_by_date(sample_financial_record.date)
        assert len(records) == 1
        retrieved_record = records[0]

        assert retrieved_record.date == sample_financial_record.date
        assert retrieved_record.account_id == sample_financial_record.account_id
        assert retrieved_record.frontdesk == sample_financial_record.frontdesk
        assert retrieved_record.platform == sample_financial_record.platform
        assert retrieved_record.new_order_amount == sample_financial_record.new_order_amount

    @pytest.mark.asyncio
    async def test_performance_record_crud(self, temp_db, sample_performance_record):
        """Test performance record CRUD operations."""
        # Create
        record_id = await temp_db.create_performance_record(sample_performance_record)
        assert record_id > 0

        # Read
        records = await temp_db.get_performance_records_by_name(sample_performance_record.name)
        assert len(records) == 1
        retrieved_record = records[0]

        assert retrieved_record.name == sample_performance_record.name
        assert retrieved_record.category == sample_performance_record.category
        assert retrieved_record.powder_count == sample_performance_record.powder_count
        assert retrieved_record.reply_rate == sample_performance_record.reply_rate

    @pytest.mark.asyncio
    async def test_team_member_crud(self, temp_db, sample_team_member):
        """Test team member CRUD operations."""
        # Create
        member_id = await temp_db.create_team_member(sample_team_member)
        assert member_id > 0

        # Read
        retrieved_member = await temp_db.get_team_member_by_user_id(sample_team_member.user_id)
        assert retrieved_member is not None
        assert retrieved_member.user_id == sample_team_member.user_id
        assert retrieved_member.frontdesk_name == sample_team_member.frontdesk_name
        assert retrieved_member.role == sample_team_member.role
        assert retrieved_member.is_active == sample_team_member.is_active

        # Update activity
        await temp_db.update_team_member_activity(sample_team_member.user_id)
        # Should not raise an error

    @pytest.mark.asyncio
    async def test_reminder_crud(self, temp_db, sample_reminder):
        """Test reminder CRUD operations."""
        # Create
        reminder_id = await temp_db.create_reminder(sample_reminder)
        assert reminder_id > 0

        # Read pending reminders
        pending = await temp_db.get_pending_reminders()
        assert len(pending) == 1
        retrieved_reminder = pending[0]

        assert retrieved_reminder.reminder_type == sample_reminder.reminder_type
        assert retrieved_reminder.frontdesk_user_id == sample_reminder.frontdesk_user_id
        assert not retrieved_reminder.is_sent

        # Mark as sent
        await temp_db.mark_reminder_sent(reminder_id)
        pending_after = await temp_db.get_pending_reminders()
        assert len(pending_after) == 0

    @pytest.mark.asyncio
    async def test_bot_task_crud(self, temp_db, sample_bot_task):
        """Test bot task CRUD operations."""
        # Create
        task_id = await temp_db.create_task(sample_bot_task)
        assert task_id > 0

        # Get next task
        next_task = await temp_db.get_next_task()
        assert next_task is not None
        assert next_task.task_type == sample_bot_task.task_type
        assert next_task.priority == sample_bot_task.priority

        # Update task status
        await temp_db.update_task_status(task_id, 'completed')
        # Task should no longer be pending
        next_task_after = await temp_db.get_next_task()
        # Should be None or different task
        if next_task_after:
            assert next_task_after.id != task_id

    @pytest.mark.asyncio
    async def test_client_record_date_filtering(self, temp_db, mock_data_generator):
        """Test filtering client records by date."""
        # Create multiple records with different dates
        records = mock_data_generator.client_records(5)
        for record in records:
            await temp_db.create_client_record(record)

        # Test filtering by frontdesk
        yim_records = await temp_db.get_client_records_by_frontdesk("阿YIM")
        jun_records = await temp_db.get_client_records_by_frontdesk("阿俊")

        # Should have records for both frontdesk members
        assert len(yim_records) > 0
        assert len(jun_records) > 0
        assert len(yim_records) + len(jun_records) == 5

    @pytest.mark.asyncio
    async def test_financial_record_date_range(self, temp_db):
        """Test financial record date range queries."""
        # Create records with different dates
        dates = ["3月15日", "3月16日", "3月17日"]
        for i, date_str in enumerate(dates):
            record = FinancialRecord(
                date=date_str,
                account_id=f"ACC{i}",
                group_id=f"GRP{i} / GRP{i}",
                frontdesk="阿YIM",
                maintenance="维护",
                frontdesk_number="+86123456789",
                platform="Iconnect",
                new_order_amount=float(100 * (i + 1))
            )
            await temp_db.create_financial_record(record)

        # Test single date query
        records_single = await temp_db.get_financial_records_by_date("3月15日")
        assert len(records_single) == 1

        # Test date range query
        records_range = await temp_db.get_financial_records_by_date("3月15日", "3月17日")
        assert len(records_range) == 3

    @pytest.mark.asyncio
    async def test_reminder_scheduling(self, temp_db):
        """Test reminder scheduling and retrieval."""
        now = datetime.now()

        # Create reminders with different scheduled times
        past_reminder = Reminder(
            frontdesk_user_id=123456,
            reminder_type="day1",
            scheduled_time=now - timedelta(hours=1),  # Past
            message="Past reminder"
        )

        future_reminder = Reminder(
            frontdesk_user_id=123456,
            reminder_type="day2",
            scheduled_time=now + timedelta(hours=1),  # Future
            message="Future reminder"
        )

        await temp_db.create_reminder(past_reminder)
        await temp_db.create_reminder(future_reminder)

        # Get pending reminders before current time
        pending_now = await temp_db.get_pending_reminders(now)
        assert len(pending_now) == 1
        assert pending_now[0].reminder_type == "day1"

        # Get all pending reminders (scheduled before far future)
        all_pending = await temp_db.get_pending_reminders(now + timedelta(hours=2))
        assert len(all_pending) == 2

    @pytest.mark.asyncio
    async def test_task_priority_ordering(self, temp_db):
        """Test that tasks are retrieved in priority order."""
        # Create tasks with different priorities
        high_priority = BotTask(
            task_type="urgent",
            priority=1,
            data={"test": "high"},
            status="pending"
        )

        low_priority = BotTask(
            task_type="routine",
            priority=3,
            data={"test": "low"},
            status="pending"
        )

        medium_priority = BotTask(
            task_type="normal",
            priority=2,
            data={"test": "medium"},
            status="pending"
        )

        # Insert in reverse order
        await temp_db.create_task(low_priority)
        await temp_db.create_task(high_priority)
        await temp_db.create_task(medium_priority)

        # Should get high priority task first
        first_task = await temp_db.get_next_task()
        assert first_task.priority == 1
        assert first_task.task_type == "urgent"

        # Mark first task as completed
        await temp_db.update_task_status(first_task.id, 'completed')

        # Should get medium priority task next
        second_task = await temp_db.get_next_task()
        assert second_task.priority == 2
        assert second_task.task_type == "normal"

    @pytest.mark.asyncio
    async def test_database_stats(self, temp_db, mock_data_generator):
        """Test database statistics."""
        # Add some test data
        client_records = mock_data_generator.client_records(3)
        team_members = mock_data_generator.team_members(2)

        for record in client_records:
            await temp_db.create_client_record(record)

        for member in team_members:
            await temp_db.create_team_member(member)

        # Get stats
        stats = await temp_db.get_stats()

        assert stats['client_records'] == 3
        assert stats['team_members'] == 2
        assert stats['financial_records'] == 0
        assert stats['performance_records'] == 0
        assert stats['reminders'] == 0
        assert stats['bot_tasks'] == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_tasks(self, temp_db):
        """Test cleanup of old completed tasks."""
        # Create old completed task
        old_task = BotTask(
            task_type="old",
            priority=1,
            data={"test": "old"},
            status="completed"
        )

        task_id = await temp_db.create_task(old_task)

        # Manually update timestamp to make it old
        async with temp_db.get_connection() as db:
            old_time = datetime.now() - timedelta(days=10)
            await db.execute("""
                UPDATE bot_tasks SET updated_at = ? WHERE id = ?
            """, (old_time.isoformat(), task_id))
            await db.commit()

        # Run cleanup
        await temp_db.cleanup_old_tasks(days_old=7)

        # Task should be deleted
        stats = await temp_db.get_stats()
        assert stats['bot_tasks'] == 0

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, temp_db, sample_client_record):
        """Test concurrent database operations."""
        # Simulate concurrent record creation
        tasks = []
        for i in range(5):
            record = ClientRecord(
                row_num=i + 1,
                date=f"3月{15 + i}日",
                phone_remark=f"Device {i}",
                frontdesk="阿YIM",
                category="飞机筛选",
                recruiter="测试",
                frontdesk_number="+86123456789",
                frontdesk_username="@test",
                client_number=f"+8613800000{i:03d}",
                account_id=f"ACC{i}",
                first_day="注册",
                second_day="注册"
            )
            tasks.append(temp_db.create_client_record(record))

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)

        # All should succeed and return unique IDs
        assert len(results) == 5
        assert all(result > 0 for result in results)
        assert len(set(results)) == 5  # All IDs should be unique

        # Verify all records were created
        records = await temp_db.get_client_records_by_frontdesk("阿YIM")
        assert len(records) == 5

    @pytest.mark.asyncio
    async def test_error_handling(self, temp_db):
        """Test database error handling."""
        # Test invalid client record (missing required fields)
        with pytest.raises(Exception):
            invalid_record = ClientRecord(
                row_num=None,  # Invalid
                date="",  # Invalid
                phone_remark="",
                frontdesk="",
                category="",
                recruiter="",
                frontdesk_number="",
                frontdesk_username="",
                client_number="",
                account_id="",
                first_day="",
                second_day=""
            )
            await temp_db.create_client_record(invalid_record)

        # Test getting non-existent team member
        non_existent = await temp_db.get_team_member_by_user_id(999999)
        assert non_existent is None

        # Test updating non-existent client record
        await temp_db.update_client_record_status(999999, first_day="注册")
        # Should not raise error, just no effect

    @pytest.mark.asyncio
    async def test_row_conversion_methods(self, temp_db, sample_client_record,
                                        sample_financial_record, sample_team_member):
        """Test database row to model conversion methods."""
        # Create records
        client_id = await temp_db.create_client_record(sample_client_record)
        financial_id = await temp_db.create_financial_record(sample_financial_record)
        member_id = await temp_db.create_team_member(sample_team_member)

        # Test row conversion through database queries
        async with temp_db.get_connection() as db:
            # Test client record conversion
            cursor = await db.execute("SELECT * FROM client_records WHERE id = ?", (client_id,))
            client_row = await cursor.fetchone()
            converted_client = temp_db._row_to_client_record(client_row)
            assert converted_client.frontdesk == sample_client_record.frontdesk

            # Test financial record conversion
            cursor = await db.execute("SELECT * FROM financial_records WHERE id = ?", (financial_id,))
            financial_row = await cursor.fetchone()
            converted_financial = temp_db._row_to_financial_record(financial_row)
            assert converted_financial.platform == sample_financial_record.platform

            # Test team member conversion
            cursor = await db.execute("SELECT * FROM team_members WHERE id = ?", (member_id,))
            member_row = await cursor.fetchone()
            converted_member = temp_db._row_to_team_member(member_row)
            assert converted_member.frontdesk_name == sample_team_member.frontdesk_name

            # Test conversion with None input
            assert temp_db._row_to_client_record(None) is None
            assert temp_db._row_to_financial_record(None) is None
            assert temp_db._row_to_team_member(None) is None
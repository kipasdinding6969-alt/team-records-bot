"""Shared test fixtures and configuration."""
import pytest
import asyncio
import tempfile
import shutil
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, date
from unittest.mock import AsyncMock, Mock, patch

import aiosqlite

from database import Database
from models import ClientRecord, FinancialRecord, PerformanceRecord, TeamMember, BotTask, Reminder
from config import Config
from telegram_handler import TelegramHandler


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    temp_file = tempfile.mktemp(suffix='.db')
    db = Database(temp_file)
    await db.initialize()
    yield db
    try:
        import os
        os.unlink(temp_file)
    except FileNotFoundError:
        pass


@pytest.fixture
def mock_telegram_handler():
    """Create a mock Telegram handler."""
    handler = Mock(spec=TelegramHandler)
    handler.send_message = AsyncMock()
    handler.edit_message = AsyncMock()
    handler.delete_message = AsyncMock()
    handler.get_user_info = AsyncMock()
    handler.health_check = AsyncMock(return_value=True)
    handler.set_conversation_state = Mock()
    handler.get_conversation_state = Mock(return_value=None)
    handler.clear_conversation_state = Mock()
    handler.broadcast_to_admins = AsyncMock()
    handler.broadcast_to_managers = AsyncMock()
    return handler


@pytest.fixture
def sample_client_record():
    """Create a sample client record for testing."""
    return ClientRecord(
        row_num=1,
        date="3月15日",
        phone_remark="65 IPHONE SE",
        frontdesk="阿YIM",
        category="飞机筛选",
        recruiter="小王",
        frontdesk_number="+86123456789",
        frontdesk_username="@test_user",
        client_number="+86987654321",
        account_id="ACC123456",
        first_day="注册",
        second_day="注册",
        client_condition="培训中"
    )


@pytest.fixture
def sample_financial_record():
    """Create a sample financial record for testing."""
    return FinancialRecord(
        date="3月15日",
        account_id="123456 / 123456",
        group_id="1234 / 12345678910",
        frontdesk="阿YIM",
        maintenance="维护员",
        frontdesk_number="+86123456789",
        platform="Iconnect",
        new_order_amount=1000.0,
        pressure_amount=500.0,
        note="测试记录",
        total_in=1500.0
    )


@pytest.fixture
def sample_performance_record():
    """Create a sample performance record for testing."""
    return PerformanceRecord(
        name="阿YIM",
        category="飞机筛选",
        powder_count=100,
        no_initial_reply=20,
        reply_rate=80.0,
        stuck_explanation=5,
        blocked_or_play=10,
        been_scammed=2,
        sent_link_no_reply=15,
        completed_register=60,
        review_rate=90.0,
        completed_training=50,
        scheduled_time=45,
        withdrawal=40,
        new_order=30,
        conversion_rate=75.0,
        new_kill=25,
        dead_client=5
    )


@pytest.fixture
def sample_team_member():
    """Create a sample team member for testing."""
    return TeamMember(
        user_id=123456,
        chat_id=123456,
        username="test_user",
        first_name="Test",
        last_name="User",
        phone_number="+86123456789",
        frontdesk_name="阿YIM",
        role="frontdesk",
        is_active=True
    )


@pytest.fixture
def sample_bot_task():
    """Create a sample bot task for testing."""
    return BotTask(
        task_type="message",
        priority=1,
        data={
            'event_type': 'command',
            'command': 'test',
            'user_id': 123456,
            'chat_id': 123456
        },
        status="pending"
    )


@pytest.fixture
def sample_reminder():
    """Create a sample reminder for testing."""
    return Reminder(
        client_record_id=1,
        frontdesk_user_id=123456,
        reminder_type="day1",
        scheduled_time=datetime.now(),
        message="Test reminder"
    )


@pytest.fixture
def test_config():
    """Create test configuration."""
    config = Config()
    # Override with test values
    config.database.db_path = ":memory:"
    config.bot.admin_chat_ids = [123456]
    config.bot.manager_chat_ids = [123457]
    config.bot.loop_interval = 0.1  # Fast for tests
    return config


@pytest.fixture
def mock_telethon_client():
    """Create a mock Telethon client."""
    client = Mock()
    client.start = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_connected = Mock(return_value=True)
    client.send_message = AsyncMock()
    client.edit_message = AsyncMock()
    client.delete_messages = AsyncMock()
    client.get_entity = AsyncMock()
    client.get_me = AsyncMock(return_value=Mock(id=123, first_name="Bot"))
    return client


@pytest.fixture
async def populated_db(temp_db, sample_client_record, sample_financial_record,
                      sample_performance_record, sample_team_member):
    """Create a database populated with test data."""
    # Insert test data
    await temp_db.create_client_record(sample_client_record)
    await temp_db.create_financial_record(sample_financial_record)
    await temp_db.create_performance_record(sample_performance_record)
    await temp_db.create_team_member(sample_team_member)

    return temp_db


@pytest.fixture
def mock_datetime():
    """Mock datetime for consistent testing."""
    with patch('models.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2024, 3, 15, 10, 30, 0)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        yield mock_dt


@pytest.fixture
def task_data_command():
    """Sample command task data."""
    return {
        'event_type': 'command',
        'command': 'start',
        'args': [],
        'user_id': 123456,
        'chat_id': 123456,
        'username': 'test_user',
        'first_name': 'Test',
        'last_name': 'User'
    }


@pytest.fixture
def task_data_callback():
    """Sample callback task data."""
    return {
        'event_type': 'callback',
        'callback_data': 'test_callback',
        'user_id': 123456,
        'chat_id': 123456,
        'message_id': 1001
    }


@pytest.fixture
def task_data_conversation():
    """Sample conversation task data."""
    return {
        'event_type': 'conversation',
        'message': 'test message',
        'user_id': 123456,
        'chat_id': 123456,
        'state': {
            'step': 'test_step',
            'data': {}
        }
    }


# Async test helpers
def async_test(coro):
    """Decorator to run async tests."""
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro(*args, **kwargs))
        finally:
            loop.close()
    return wrapper


class AsyncContextManager:
    """Helper for async context managers in tests."""

    def __init__(self, async_func):
        self.async_func = async_func

    async def __aenter__(self):
        return await self.async_func()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# Test utilities
def assert_client_record_equal(record1: ClientRecord, record2: ClientRecord):
    """Assert two client records are equal (excluding timestamps)."""
    assert record1.row_num == record2.row_num
    assert record1.date == record2.date
    assert record1.phone_remark == record2.phone_remark
    assert record1.frontdesk == record2.frontdesk
    assert record1.category == record2.category
    assert record1.recruiter == record2.recruiter
    assert record1.frontdesk_number == record2.frontdesk_number
    assert record1.frontdesk_username == record2.frontdesk_username
    assert record1.client_number == record2.client_number
    assert record1.account_id == record2.account_id
    assert record1.first_day == record2.first_day
    assert record1.second_day == record2.second_day
    assert record1.client_condition == record2.client_condition


def assert_financial_record_equal(record1: FinancialRecord, record2: FinancialRecord):
    """Assert two financial records are equal."""
    assert record1.date == record2.date
    assert record1.account_id == record2.account_id
    assert record1.group_id == record2.group_id
    assert record1.frontdesk == record2.frontdesk
    assert record1.platform == record2.platform
    assert record1.new_order_amount == record2.new_order_amount
    assert record1.pressure_amount == record2.pressure_amount
    assert record1.total_in == record2.total_in


def assert_performance_record_equal(record1: PerformanceRecord, record2: PerformanceRecord):
    """Assert two performance records are equal."""
    assert record1.name == record2.name
    assert record1.category == record2.category
    assert record1.powder_count == record2.powder_count
    assert record1.reply_rate == record2.reply_rate
    assert record1.conversion_rate == record2.conversion_rate


# Mock data generators
class MockDataGenerator:
    """Generate mock data for tests."""

    @staticmethod
    def client_records(count: int = 5) -> List[ClientRecord]:
        """Generate multiple client records."""
        records = []
        for i in range(count):
            record = ClientRecord(
                row_num=i + 1,
                date=f"3月{15 + i}日",
                phone_remark=f"Device {i + 1}",
                frontdesk="阿YIM" if i % 2 == 0 else "阿俊",
                category="飞机筛选" if i % 2 == 0 else "RCS筛选",
                recruiter=f"Recruiter {i + 1}",
                frontdesk_number=f"+861234567{i:02d}",
                frontdesk_username=f"@user{i + 1}",
                client_number=f"+869876543{i:02d}",
                account_id=f"ACC{1000 + i}",
                first_day="注册" if i % 3 != 0 else "不注册",
                second_day="注册" if i % 2 == 0 else "不注册"
            )
            records.append(record)
        return records

    @staticmethod
    def team_members(count: int = 3) -> List[TeamMember]:
        """Generate multiple team members."""
        members = []
        roles = ["frontdesk", "manager", "admin"]
        names = ["阿YIM", "阿俊", "小王"]

        for i in range(count):
            member = TeamMember(
                user_id=123456 + i,
                chat_id=123456 + i,
                username=f"user{i + 1}",
                first_name=f"User{i + 1}",
                phone_number=f"+861234567{i:02d}",
                frontdesk_name=names[i % len(names)],
                role=roles[i % len(roles)],
                is_active=True
            )
            members.append(member)
        return members


@pytest.fixture
def mock_data_generator():
    """Provide mock data generator."""
    return MockDataGenerator
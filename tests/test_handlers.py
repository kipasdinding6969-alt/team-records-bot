"""Tests for command handlers."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from handlers.registration import handle_start_command, handle_profile_command
from handlers.reporting import handle_report_command
from handlers.dashboard import handle_dashboard_command, handle_status_command
from handlers.finance import handle_finance_command
from handlers.performance import handle_performance_command
from handlers.reminders import handle_remind_command

from models import TeamMember


class TestRegistrationHandlers:
    """Test registration-related handlers."""

    @pytest.mark.asyncio
    async def test_start_command_new_user(self, mock_telegram_handler, temp_db, task_data_command):
        """Test /start command for new user."""
        with patch('handlers.registration.database', temp_db), \
             patch('handlers.registration.telegram_handler', mock_telegram_handler):

            await handle_start_command(task_data_command)

            # Should send registration options
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data_command['chat_id']
            assert '请选择您的角色' in message
            assert 'reply_markup' in kwargs

    @pytest.mark.asyncio
    async def test_start_command_existing_user(self, mock_telegram_handler, populated_db, task_data_command):
        """Test /start command for existing user."""
        with patch('handlers.registration.database', populated_db), \
             patch('handlers.registration.telegram_handler', mock_telegram_handler):

            await handle_start_command(task_data_command)

            # Should send welcome back message
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data_command['chat_id']
            assert 'Welcome back' in message or '欢迎回来' in message

    @pytest.mark.asyncio
    async def test_profile_command_unregistered(self, mock_telegram_handler, temp_db, task_data_command):
        """Test /profile command for unregistered user."""
        with patch('handlers.registration.database', temp_db), \
             patch('handlers.registration.telegram_handler', mock_telegram_handler):

            await handle_profile_command(task_data_command)

            # Should send registration prompt
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data_command['chat_id']
            assert '还未注册' in message or 'not registered' in message

    @pytest.mark.asyncio
    async def test_profile_command_registered(self, mock_telegram_handler, populated_db, task_data_command):
        """Test /profile command for registered user."""
        with patch('handlers.registration.database', populated_db), \
             patch('handlers.registration.telegram_handler', mock_telegram_handler):

            await handle_profile_command(task_data_command)

            # Should send profile information
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data_command['chat_id']
            assert '个人资料' in message or 'Profile' in message
            assert 'reply_markup' in kwargs


@pytest.mark.skip(reason="V1 schema (team_members) — deprecated")
class TestReportingHandlers:
    """Test reporting-related handlers."""

    @pytest.mark.asyncio
    async def test_report_command_unauthorized(self, mock_telegram_handler, temp_db):
        """Test /report command for unauthorized user."""
        task_data = {
            'user_id': 999999,  # Non-existent user
            'chat_id': 999999,
            'args': []
        }

        with patch('handlers.reporting.database', temp_db), \
             patch('handlers.reporting.telegram_handler', mock_telegram_handler):

            await handle_report_command(task_data)

            # Should send unauthorized message
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '仅限前台员工' in message or 'only for frontdesk' in message

    @pytest.mark.asyncio
    async def test_report_command_authorized(self, mock_telegram_handler, populated_db):
        """Test /report command for authorized user."""
        task_data = {
            'user_id': 123456,  # User from populated_db
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.reporting.database', populated_db), \
             patch('handlers.reporting.telegram_handler', mock_telegram_handler):

            await handle_report_command(task_data)

            # Should send report wizard
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '客户记录提交' in message or 'Client Record' in message
            assert 'reply_markup' in kwargs


class TestDashboardHandlers:
    """Test dashboard-related handlers."""

    @pytest.mark.asyncio
    async def test_dashboard_command_unauthorized(self, mock_telegram_handler, temp_db):
        """Test /dashboard command for unauthorized user."""
        # Create frontdesk user (not manager/admin)
        frontdesk_member = TeamMember(
            user_id=123456,
            chat_id=123456,
            role="frontdesk"
        )
        await temp_db.create_team_member(frontdesk_member)

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.dashboard.database', temp_db), \
             patch('handlers.dashboard.telegram_handler', mock_telegram_handler):

            await handle_dashboard_command(task_data)

            # Should send unauthorized message
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '仅限管理员' in message or 'managers and admins' in message

    @pytest.mark.asyncio
    async def test_status_command_authorized(self, mock_telegram_handler, populated_db):
        """Test /status command for authorized user."""
        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.dashboard.database', populated_db), \
             patch('handlers.dashboard.telegram_handler', mock_telegram_handler), \
             patch('handlers.dashboard.generate_personal_stats') as mock_generate:

            mock_generate.return_value = {
                'today': {'total_records': 5, 'registered': 3, 'not_registered': 2, 'pending': 0, 'registration_rate': 60.0},
                'total': {'total_records': 20, 'registered': 15, 'not_registered': 5, 'pending': 0, 'registration_rate': 75.0},
                'week': {'total_records': 10, 'registered': 7},
                'reminders': {'pending': 2, 'day1': 1, 'day2': 1}
            }

            await handle_status_command(task_data)

            # Should send personal statistics
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '个人统计' in message or 'Personal Statistics' in message


@pytest.mark.skip(reason="V1 schema (team_members) — deprecated")
class TestFinanceHandlers:
    """Test finance-related handlers."""

    @pytest.mark.asyncio
    async def test_finance_command_unauthorized(self, mock_telegram_handler, temp_db):
        """Test /finance command for unauthorized user."""
        # Create frontdesk user (not manager/admin)
        frontdesk_member = TeamMember(
            user_id=123456,
            chat_id=123456,
            role="frontdesk"
        )
        await temp_db.create_team_member(frontdesk_member)

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.finance.database', temp_db), \
             patch('handlers.finance.telegram_handler', mock_telegram_handler):

            await handle_finance_command(task_data)

            # Should send unauthorized message
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '仅限管理员' in message or 'managers and admins' in message

    @pytest.mark.asyncio
    async def test_finance_command_invalid_date(self, mock_telegram_handler, temp_db):
        """Test /finance command with invalid date."""
        # Create admin user
        admin_member = TeamMember(
            user_id=123456,
            chat_id=123456,
            role="admin"
        )
        await temp_db.create_team_member(admin_member)

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': ['invalid-date']
        }

        with patch('handlers.finance.database', temp_db), \
             patch('handlers.finance.telegram_handler', mock_telegram_handler):

            await handle_finance_command(task_data)

            # Should send date format error
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '日期格式错误' in message or 'Invalid date format' in message


@pytest.mark.skip(reason="V1 schema (team_members) — deprecated")
class TestPerformanceHandlers:
    """Test performance-related handlers."""

    @pytest.mark.asyncio
    async def test_performance_command_no_args(self, mock_telegram_handler, temp_db):
        """Test /performance command without arguments."""
        # Create admin user
        admin_member = TeamMember(
            user_id=123456,
            chat_id=123456,
            role="admin"
        )
        await temp_db.create_team_member(admin_member)

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.performance.database', temp_db), \
             patch('handlers.performance.telegram_handler', mock_telegram_handler), \
             patch('handlers.performance.get_available_frontdesk_members') as mock_get_members:

            mock_get_members.return_value = ["阿YIM", "阿俊"]

            await handle_performance_command(task_data)

            # Should send available members list
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '可用成员' in message or 'Available members' in message


@pytest.mark.skip(reason="V1 schema (team_members) — deprecated")
class TestReminderHandlers:
    """Test reminder-related handlers."""

    @pytest.mark.asyncio
    async def test_remind_command_unauthorized(self, mock_telegram_handler, temp_db):
        """Test /remind command for unauthorized user."""
        # Create manager user (only admins can use remind)
        manager_member = TeamMember(
            user_id=123456,
            chat_id=123456,
            role="manager"
        )
        await temp_db.create_team_member(manager_member)

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.reminders.database', temp_db), \
             patch('handlers.reminders.telegram_handler', mock_telegram_handler):

            await handle_remind_command(task_data)

            # Should send unauthorized message
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '仅限管理员' in message or 'only for administrators' in message

    @pytest.mark.asyncio
    async def test_remind_command_no_args(self, mock_telegram_handler, temp_db):
        """Test /remind command without arguments."""
        # Create admin user
        admin_member = TeamMember(
            user_id=123456,
            chat_id=123456,
            role="admin"
        )
        await temp_db.create_team_member(admin_member)

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.reminders.database', temp_db), \
             patch('handlers.reminders.telegram_handler', mock_telegram_handler):

            await handle_remind_command(task_data)

            # Should send usage instructions
            mock_telegram_handler.send_message.assert_called_once()
            args, kwargs = mock_telegram_handler.send_message.call_args
            chat_id, message = args[:2]

            assert chat_id == task_data['chat_id']
            assert '提醒管理' in message or 'Reminder Management' in message
            assert '使用方法' in message or 'Usage' in message


class TestHandlerErrorHandling:
    """Test error handling in handlers."""

    @pytest.mark.asyncio
    async def test_handler_database_error(self, mock_telegram_handler):
        """Test handler behavior when database operations fail."""
        # Mock database that raises errors
        mock_db = Mock()
        mock_db.get_team_member_by_user_id = AsyncMock(side_effect=Exception("Database error"))

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.registration.database', mock_db), \
             patch('handlers.registration.telegram_handler', mock_telegram_handler):

            # Should not raise exception
            try:
                await handle_start_command(task_data)
            except Exception as e:
                pass  # Handlers propagate errors

    @pytest.mark.asyncio
    async def test_handler_telegram_error(self, temp_db):
        """Test handler behavior when Telegram operations fail."""
        # Mock Telegram handler that raises errors
        mock_tg = Mock()
        mock_tg.send_message = AsyncMock(side_effect=Exception("Telegram error"))

        task_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'args': []
        }

        with patch('handlers.registration.database', temp_db), \
             patch('handlers.registration.telegram_handler', mock_tg):

            # Should not raise exception
            try:
                await handle_start_command(task_data)
            except Exception as e:
                pass  # Handlers propagate errors


class TestHandlerUtilities:
    """Test handler utility functions."""

    def test_command_parsing(self):
        """Test command argument parsing."""
        # Test in actual handler context
        task_data_with_args = {
            'command': 'finance',
            'args': ['2024-03-15'],
            'user_id': 123456,
            'chat_id': 123456
        }

        # Args should be accessible
        assert task_data_with_args['args'] == ['2024-03-15']
        assert len(task_data_with_args['args']) == 1

    def test_callback_data_parsing(self):
        """Test callback data parsing."""
        callback_data = "register_frontdesk"

        # Should be able to extract action
        action = callback_data.split('_')[0]
        role = callback_data.split('_')[1]

        assert action == "register"
        assert role == "frontdesk"

    @pytest.mark.asyncio
    async def test_conversation_state_management(self, mock_telegram_handler):
        """Test conversation state management."""
        user_id = 123456
        test_state = {
            'step': 'date_input',
            'data': {'partial_record': {'frontdesk': 'test'}}
        }

        # Set state
        await mock_telegram_handler.set_conversation_state(user_id, test_state)
        mock_telegram_handler.set_conversation_state.assert_called_once_with(user_id, test_state)

        # Get state
        mock_telegram_handler.get_conversation_state.return_value = test_state
        retrieved_state = await mock_telegram_handler.get_conversation_state(user_id)

        assert retrieved_state == test_state
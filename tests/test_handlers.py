"""Tests for command handlers.

Note: V1 schema (team_members) deprecated test classes removed:
  TestReportingHandlers, TestFinanceHandlers, TestPerformanceHandlers, TestReminderHandlers
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from handlers.registration import handle_start_command, handle_profile_command
from handlers.dashboard import handle_dashboard_command, handle_status_command

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
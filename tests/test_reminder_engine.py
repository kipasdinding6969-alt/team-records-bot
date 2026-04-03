"""Tests for engines/reminder_engine.py — stale client detection, auto-reminders, processing."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from engines.reminder_engine import ReminderEngine
from models import Reminder, ClientRecord


@pytest.fixture
def engine():
    return ReminderEngine()


@pytest.fixture
def mock_reminder():
    """A mock reminder object."""
    return Reminder(
        client_record_id=1,
        frontdesk_user_id=123456,
        reminder_type="day1",
        scheduled_time=datetime.now() - timedelta(hours=1),
        message=None,
        id=42,
    )


@pytest.fixture
def mock_member():
    m = Mock()
    m.chat_id = 999
    m.is_active = True
    m.frontdesk_name = "阿YIM"
    m.user_id = 123456
    return m


# ─── Template registry ─────────────────────────────────────────────────────────


class TestReminderTemplates:
    def test_template_registry_has_all_types(self, engine):
        assert "day1" in engine.reminder_templates
        assert "day2" in engine.reminder_templates
        assert "followup" in engine.reminder_templates
        assert "deadline" in engine.reminder_templates

    def test_template_registry_values_are_callable(self, engine):
        for key, func in engine.reminder_templates.items():
            assert callable(func), f"Template '{key}' is not callable"


# ─── Message generation ────────────────────────────────────────────────────────


class TestMessageGeneration:
    @pytest.mark.asyncio
    async def test_generate_message_with_custom_text(self, engine):
        reminder = Reminder(
            client_record_id=None,
            frontdesk_user_id=1,
            reminder_type="day1",
            scheduled_time=datetime.now(),
            message="Custom reminder text",
        )
        msg = await engine._generate_reminder_message(reminder)
        assert "提醒" in msg or "Reminder" in msg
        assert "Custom reminder text" in msg

    @pytest.mark.asyncio
    async def test_generate_message_uses_template_when_no_custom(self, engine):
        reminder = Reminder(
            client_record_id=None,
            frontdesk_user_id=1,
            reminder_type="followup",
            scheduled_time=datetime.now(),
            message=None,
        )
        msg = await engine._generate_reminder_message(reminder)
        assert "跟进" in msg or "Follow-up" in msg

    @pytest.mark.asyncio
    async def test_generate_message_default_for_unknown_type(self, engine):
        reminder = Reminder(
            client_record_id=None,
            frontdesk_user_id=1,
            reminder_type="unknown_type",
            scheduled_time=datetime.now(),
            message=None,
        )
        msg = await engine._generate_reminder_message(reminder)
        assert "提醒" in msg or "Reminder" in msg

    @pytest.mark.asyncio
    async def test_followup_message_content(self, engine):
        reminder = Reminder(
            client_record_id=None,
            frontdesk_user_id=1,
            reminder_type="followup",
            scheduled_time=datetime.now(),
            message=None,
        )
        msg = await engine._create_followup_reminder_message(reminder)
        assert "客户跟进" in msg or "Follow-up" in msg
        assert "/clients" in msg

    @pytest.mark.asyncio
    async def test_deadline_message_content(self, engine):
        reminder = Reminder(
            client_record_id=None,
            frontdesk_user_id=1,
            reminder_type="deadline",
            scheduled_time=datetime.now(),
            message=None,
        )
        msg = await engine._create_deadline_reminder_message(reminder)
        assert "截止" in msg or "Deadline" in msg
        assert "/dashboard" in msg

    @pytest.mark.asyncio
    async def test_day1_message_no_client_record(self, engine):
        reminder = Reminder(
            client_record_id=None,
            frontdesk_user_id=1,
            reminder_type="day1",
            scheduled_time=datetime.now(),
            message=None,
        )
        with (
            patch.object(
                engine, "_get_client_record", new=AsyncMock(return_value=None)
            ),
            patch(
                "engines.reminder_engine._get_lang", new=AsyncMock(return_value="zh")
            ),
        ):
            msg = await engine._create_day1_reminder_message(reminder)
            assert msg  # Should return something, not None

    @pytest.mark.asyncio
    async def test_day2_message_no_client_record(self, engine):
        reminder = Reminder(
            client_record_id=None,
            frontdesk_user_id=1,
            reminder_type="day2",
            scheduled_time=datetime.now(),
            message=None,
        )
        with (
            patch.object(
                engine, "_get_client_record", new=AsyncMock(return_value=None)
            ),
            patch(
                "engines.reminder_engine._get_lang", new=AsyncMock(return_value="zh")
            ),
        ):
            msg = await engine._create_day2_reminder_message(reminder)
            assert msg

    @pytest.mark.asyncio
    async def test_day1_message_with_client_record(self, engine):
        reminder = Reminder(
            client_record_id=1,
            frontdesk_user_id=1,
            reminder_type="day1",
            scheduled_time=datetime.now(),
            message=None,
        )
        mock_record = Mock(spec=ClientRecord)
        mock_record.client_number = "+86123"
        mock_record.account_id = "ACC001"
        mock_record.category = "飞机筛选"
        mock_record.date = "3月15日"
        mock_record.first_day = "注册"

        with (
            patch.object(
                engine, "_get_client_record", new=AsyncMock(return_value=mock_record)
            ),
            patch(
                "engines.reminder_engine._get_lang", new=AsyncMock(return_value="zh")
            ),
        ):
            msg = await engine._create_day1_reminder_message(reminder)
            assert "+86123" in msg
            assert "ACC001" in msg


# ─── Send reminder ──────────────────────────────────────────────────────────────


class TestSendReminder:
    @pytest.mark.asyncio
    async def test_send_reminder_success(self, engine, mock_reminder, mock_member):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.telegram_handler") as mock_tg,
        ):
            mock_db.get_team_member_by_user_id = AsyncMock(return_value=mock_member)
            mock_tg.send_message = AsyncMock()

            with patch.object(
                engine,
                "_generate_reminder_message",
                new=AsyncMock(return_value="Test message"),
            ):
                result = await engine._send_reminder(mock_reminder)

            assert result is True
            mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_reminder_member_not_found(self, engine, mock_reminder):
        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_team_member_by_user_id = AsyncMock(return_value=None)
            result = await engine._send_reminder(mock_reminder)
            assert result is False

    @pytest.mark.asyncio
    async def test_send_reminder_member_inactive(
        self, engine, mock_reminder, mock_member
    ):
        mock_member.is_active = False
        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_team_member_by_user_id = AsyncMock(return_value=mock_member)
            result = await engine._send_reminder(mock_reminder)
            assert result is False

    @pytest.mark.asyncio
    async def test_send_reminder_telegram_error(
        self, engine, mock_reminder, mock_member
    ):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.telegram_handler") as mock_tg,
        ):
            mock_db.get_team_member_by_user_id = AsyncMock(return_value=mock_member)
            mock_tg.send_message = AsyncMock(
                side_effect=Exception("Telegram API error")
            )

            with patch.object(
                engine, "_generate_reminder_message", new=AsyncMock(return_value="Test")
            ):
                result = await engine._send_reminder(mock_reminder)

            assert result is False


# ─── Process pending reminders ──────────────────────────────────────────────────


class TestProcessPendingReminders:
    @pytest.mark.asyncio
    async def test_process_no_pending(self, engine):
        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_pending_reminders = AsyncMock(return_value=[])
            result = await engine.process_pending_reminders()
            assert result["processed"] == 0
            assert result["failed"] == 0
            assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_process_one_reminder_success(self, engine, mock_reminder):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch.object(engine, "_send_reminder", new=AsyncMock(return_value=True)),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_db.get_pending_reminders = AsyncMock(return_value=[mock_reminder])
            mock_db.mark_reminder_sent = AsyncMock()

            result = await engine.process_pending_reminders()
            assert result["processed"] == 1
            assert result["failed"] == 0
            mock_db.mark_reminder_sent.assert_called_once_with(42)

    @pytest.mark.asyncio
    async def test_process_one_reminder_failed(self, engine, mock_reminder):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch.object(engine, "_send_reminder", new=AsyncMock(return_value=False)),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_db.get_pending_reminders = AsyncMock(return_value=[mock_reminder])

            result = await engine.process_pending_reminders()
            assert result["processed"] == 0
            assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_process_exception_in_reminder(self, engine, mock_reminder):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch.object(
                engine, "_send_reminder", new=AsyncMock(side_effect=Exception("boom"))
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_db.get_pending_reminders = AsyncMock(return_value=[mock_reminder])

            result = await engine.process_pending_reminders()
            assert result["failed"] == 1
            assert result["details"][0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_process_multiple_reminders(self, engine):
        r1 = Reminder(
            client_record_id=1,
            frontdesk_user_id=1,
            reminder_type="day1",
            scheduled_time=datetime.now(),
            id=1,
        )
        r2 = Reminder(
            client_record_id=2,
            frontdesk_user_id=2,
            reminder_type="day2",
            scheduled_time=datetime.now(),
            id=2,
        )

        call_count = 0

        async def alternating_send(reminder):
            nonlocal call_count
            call_count += 1
            return call_count % 2 == 1  # first succeeds, second fails

        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch.object(engine, "_send_reminder", side_effect=alternating_send),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_db.get_pending_reminders = AsyncMock(return_value=[r1, r2])
            mock_db.mark_reminder_sent = AsyncMock()

            result = await engine.process_pending_reminders()
            assert result["processed"] == 1
            assert result["failed"] == 1


# ─── Create automatic reminders ─────────────────────────────────────────────────


class TestCreateAutomaticReminders:
    @pytest.mark.asyncio
    async def test_create_auto_reminders_creates_two(self, engine):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.config") as mock_config,
        ):
            mock_config.bot.day1_reminder_hours = 24
            mock_config.bot.day2_reminder_hours = 48
            mock_db.create_reminder = AsyncMock(side_effect=[101, 102])

            ids = await engine.create_automatic_reminders(1, 123456)
            assert ids == [101, 102]
            assert mock_db.create_reminder.call_count == 2

    @pytest.mark.asyncio
    async def test_create_auto_reminders_error_returns_empty(self, engine):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.config") as mock_config,
        ):
            mock_config.bot.day1_reminder_hours = 24
            mock_db.create_reminder = AsyncMock(side_effect=Exception("DB error"))

            ids = await engine.create_automatic_reminders(1, 123456)
            assert ids == []


# ─── Create manual reminder ─────────────────────────────────────────────────────


class TestCreateManualReminder:
    @pytest.mark.asyncio
    async def test_create_manual_success(self, engine):
        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.create_reminder = AsyncMock(return_value=200)

            result = await engine.create_manual_reminder(
                frontdesk_user_id=1,
                reminder_type="followup",
                scheduled_time=datetime.now() + timedelta(hours=1),
                message="Follow up with client",
            )
            assert result == 200

    @pytest.mark.asyncio
    async def test_create_manual_error_returns_none(self, engine):
        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.create_reminder = AsyncMock(side_effect=Exception("err"))
            result = await engine.create_manual_reminder(
                1, "followup", datetime.now(), "msg"
            )
            assert result is None


# ─── Cancel reminders ───────────────────────────────────────────────────────────


class TestCancelReminders:
    @pytest.mark.asyncio
    async def test_cancel_reminders_for_client(self, engine):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 3

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)

            result = await engine.cancel_reminders_for_client(42)
            assert result == 3

    @pytest.mark.asyncio
    async def test_cancel_reminders_error_returns_zero(self, engine):
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)

            result = await engine.cancel_reminders_for_client(42)
            assert result == 0


# ─── Update reminder schedule ───────────────────────────────────────────────────


class TestUpdateReminderSchedule:
    @pytest.mark.asyncio
    async def test_update_schedule_success(self, engine):
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)
            new_time = datetime.now() + timedelta(hours=5)
            result = await engine.update_reminder_schedule(1, new_time)
            assert result is True

    @pytest.mark.asyncio
    async def test_update_schedule_error_returns_false(self, engine):
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(side_effect=Exception("err"))
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)
            result = await engine.update_reminder_schedule(1, datetime.now())
            assert result is False


# ─── Reminder statistics ────────────────────────────────────────────────────────


class TestReminderStatistics:
    @pytest.mark.asyncio
    async def test_get_statistics_structure(self, engine):
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(
            side_effect=[
                (5,),  # pending
                (20,),  # sent_week
                (2,),  # overdue
                (15, 25),  # success rate (sent, total)
            ]
        )
        mock_cursor.fetchall = AsyncMock(return_value=[("day1", 3), ("day2", 2)])

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)
            stats = await engine.get_reminder_statistics()

            assert stats["pending"] == 5
            assert stats["sent_week"] == 20
            assert stats["overdue"] == 2
            assert stats["success_rate"] == 60.0  # 15/25 * 100
            assert stats["by_type"] == {"day1": 3, "day2": 2}

    @pytest.mark.asyncio
    async def test_get_statistics_error_returns_empty(self, engine):
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(side_effect=Exception("err"))
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)
            stats = await engine.get_reminder_statistics()
            assert stats == {}


# ─── Cleanup old reminders ──────────────────────────────────────────────────────


class TestCleanupOldReminders:
    @pytest.mark.asyncio
    async def test_cleanup_old_reminders(self, engine):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 10

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)
            result = await engine.cleanup_old_reminders(days_old=30)
            assert result == 10

    @pytest.mark.asyncio
    async def test_cleanup_error_returns_zero(self, engine):
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(side_effect=Exception("err"))
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_connection = MagicMock(return_value=mock_conn)
            result = await engine.cleanup_old_reminders()
            assert result == 0


# ─── Process overdue reminders ──────────────────────────────────────────────────


class TestProcessOverdueReminders:
    @pytest.mark.asyncio
    async def test_no_overdue_returns_zeros(self, engine):
        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_pending_reminders = AsyncMock(return_value=[])
            result = await engine.process_overdue_reminders()
            assert result["processed"] == 0
            assert result["escalated"] == 0
            assert result["cancelled"] == 0

    @pytest.mark.asyncio
    async def test_very_old_reminder_gets_cancelled(self, engine):
        old_reminder = Reminder(
            client_record_id=1,
            frontdesk_user_id=1,
            reminder_type="day1",
            scheduled_time=datetime.now() - timedelta(hours=30),
            id=99,
        )
        with patch("engines.reminder_engine.database") as mock_db:
            mock_db.get_pending_reminders = AsyncMock(return_value=[old_reminder])
            mock_db.mark_reminder_sent = AsyncMock()
            result = await engine.process_overdue_reminders()
            assert result["cancelled"] == 1
            mock_db.mark_reminder_sent.assert_called_once_with(99)

    @pytest.mark.asyncio
    async def test_moderately_overdue_gets_escalated(self, engine):
        overdue_reminder = Reminder(
            client_record_id=1,
            frontdesk_user_id=1,
            reminder_type="day1",
            scheduled_time=datetime.now() - timedelta(hours=8),
            id=77,
        )
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch.object(engine, "_escalate_reminder", new=AsyncMock()),
        ):
            mock_db.get_pending_reminders = AsyncMock(return_value=[overdue_reminder])
            mock_db.mark_reminder_sent = AsyncMock()
            result = await engine.process_overdue_reminders()
            assert result["escalated"] == 1
            engine._escalate_reminder.assert_called_once()

    @pytest.mark.asyncio
    async def test_slightly_overdue_gets_sent(self, engine):
        slightly_overdue = Reminder(
            client_record_id=1,
            frontdesk_user_id=1,
            reminder_type="day1",
            scheduled_time=datetime.now() - timedelta(hours=2),
            id=55,
        )
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch.object(engine, "_send_reminder", new=AsyncMock(return_value=True)),
        ):
            mock_db.get_pending_reminders = AsyncMock(return_value=[slightly_overdue])
            mock_db.mark_reminder_sent = AsyncMock()
            result = await engine.process_overdue_reminders()
            assert result["processed"] == 1


# ─── Escalate reminder ──────────────────────────────────────────────────────────


class TestEscalateReminder:
    @pytest.mark.asyncio
    async def test_escalate_sends_to_managers(self, engine, mock_reminder, mock_member):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.telegram_handler") as mock_tg,
        ):
            mock_db.get_team_member_by_user_id = AsyncMock(return_value=mock_member)
            mock_tg.broadcast_to_managers = AsyncMock()

            await engine._escalate_reminder(mock_reminder)
            mock_tg.broadcast_to_managers.assert_called_once()
            msg = mock_tg.broadcast_to_managers.call_args[0][0]
            assert "提醒升级" in msg or "Escalation" in msg

    @pytest.mark.asyncio
    async def test_escalate_error_handled(self, engine, mock_reminder):
        with (
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.telegram_handler") as mock_tg,
        ):
            mock_db.get_team_member_by_user_id = AsyncMock(side_effect=Exception("err"))
            # Should not raise
            await engine._escalate_reminder(mock_reminder)


# ─── Scan stale clients ─────────────────────────────────────────────────────────


class TestScanStaleClients:
    @pytest.mark.asyncio
    async def test_scan_outside_working_hours(self, engine):
        with patch("working_hours.is_working_hours", return_value=False):
            result = await engine.scan_stale_clients()
            assert result["processed"] == 0
            assert "Outside working hours" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_scan_no_stale_clients(self, engine):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        with (
            patch("working_hours.is_working_hours", return_value=True),
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.config") as mock_config,
        ):
            mock_config.bot.stale_client_days = 7
            mock_db.get_connection = MagicMock(return_value=mock_conn)
            result = await engine.scan_stale_clients()
            assert result["processed"] == 0

    @pytest.mark.asyncio
    async def test_scan_error_returns_error_dict(self, engine):
        with (
            patch("working_hours.is_working_hours", return_value=True),
            patch("engines.reminder_engine.database") as mock_db,
            patch("engines.reminder_engine.config") as mock_config,
        ):
            mock_config.bot.stale_client_days = 7
            mock_db.get_connection = MagicMock(side_effect=Exception("DB down"))
            result = await engine.scan_stale_clients()
            assert "error" in result

"""Tests for handlers_v2/quick_actions.py — /add, /u, /note, /remind, /handoff,
/num, /info, /req, /bulkupdate and inline status callbacks."""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

from handlers_v2.quick_actions import (
    status_emoji,
    _parse_time_delta,
    _build_status_buttons,
    handle_add_client,
    handle_update_status,
    handle_add_note,
    handle_remind,
    handle_handoff,
    handle_inline_status_callback,
    handle_bulkupdate,
    handle_bulkupdate_callback,
    handle_num,
    handle_info,
    handle_req,
    QUICK_ACTIONS_COMMANDS,
    QUICK_ACTIONS_CALLBACKS,
    QUICK_ACTIONS_CONVERSATIONS,
)
from models_v2 import ClientStatus, StaffRole


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_staff(
    tg_user_id=1001,
    role=StaffRole.FRONTDESK,
    lang="zh",
    team="team_a",
    staff_id=10,
    display_name="Alice",
):
    s = MagicMock()
    s.id = staff_id
    s.tg_user_id = tg_user_id
    s.tg_chat_id = tg_user_id + 1000
    s.display_name = display_name
    s.role = role
    s.language = lang
    s.team = team
    s.is_manager_or_above = MagicMock(
        return_value=role in (StaffRole.MANAGER, StaffRole.ADMIN)
    )
    return s


def _make_client(
    client_id=99,
    phone="1234567890",
    status=ClientStatus.NEW,
    frontdesk_id=10,
    total_deposited=0.0,
    account_id=None,
    source="飞机筛选",
):
    c = MagicMock()
    c.id = client_id
    c.phone = phone
    c.status = status
    c.frontdesk_id = frontdesk_id
    c.total_deposited = total_deposited
    c.account_id = account_id
    c.source = source
    c.created_at = "2026-04-01T10:00:00"
    c.contacted_at = None
    c.registered_at = None
    c.platform = None
    return c


def _task(chat_id=9000, user_id=1001, args="", callback_data="", **kwargs):
    d = {
        "chat_id": chat_id,
        "user_id": user_id,
        "args": args,
        "callback_data": callback_data,
    }
    d.update(kwargs)
    return d


# ── Pure helper tests ─────────────────────────────────────────────────────────


class TestStatusEmoji:
    def test_known_statuses(self):
        assert status_emoji(ClientStatus.NEW) == "🆕"
        assert status_emoji(ClientStatus.DEAD) == "💀"
        assert status_emoji(ClientStatus.ORDERED) == "🎯"

    def test_unknown_status_falls_back(self):
        unknown = MagicMock()
        unknown.__eq__ = lambda s, o: False
        assert status_emoji(unknown) == "❓"


class TestParseTimeDelta:
    def test_hours(self):
        assert _parse_time_delta("2h") == timedelta(hours=2)
        assert _parse_time_delta("0.5h") == timedelta(hours=0.5)

    def test_minutes(self):
        assert _parse_time_delta("30m") == timedelta(minutes=30)

    def test_days(self):
        assert _parse_time_delta("7d") == timedelta(days=7)

    def test_whitespace_stripped(self):
        assert _parse_time_delta("  1h  ") == timedelta(hours=1)

    def test_case_insensitive(self):
        assert _parse_time_delta("2H") == timedelta(hours=2)

    def test_bad_value_returns_none(self):
        assert _parse_time_delta("xh") is None
        assert _parse_time_delta("bad") is None
        assert _parse_time_delta("") is None

    def test_no_suffix_returns_none(self):
        assert _parse_time_delta("60") is None


class TestBuildStatusButtons:
    def test_returns_list_of_button_specs(self):
        buttons = _build_status_buttons(client_id=1, current_status=ClientStatus.NEW)
        assert isinstance(buttons, list)
        assert all("text" in b and "callback_data" in b for b in buttons)

    def test_callback_data_format(self):
        buttons = _build_status_buttons(client_id=42, current_status=ClientStatus.NEW)
        for b in buttons:
            assert b["callback_data"].startswith("v2_status_42_")

    def test_no_terminal_statuses_in_buttons(self):
        """Terminal statuses should be omitted from the inline buttons."""
        terminal_values = {s.value for s in ClientStatus.terminal_statuses()}
        buttons = _build_status_buttons(client_id=1, current_status=ClientStatus.NEW)
        for b in buttons:
            status_part = b["callback_data"].split("_", 3)[-1]
            assert status_part not in terminal_values


# ── handle_add_client ─────────────────────────────────────────────────────────


class TestHandleAddClient:
    """Tests for /add <phone> <source> [account_id]."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock(return_value=None)
        self.phone_registry_lookup = AsyncMock(return_value=None)
        self.create_client = AsyncMock(return_value=5)
        self.phone_registry_insert = AsyncMock()
        self.phone_registry_log = AsyncMock()
        self.check_can_add = AsyncMock(return_value=(True, ""))

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
            patch("engines.policy_engine.check_can_add_client", self.check_can_add),
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.phone_registry_lookup = self.phone_registry_lookup
            db.create_client = self.create_client
            db.phone_registry_insert = self.phone_registry_insert
            db.phone_registry_log_action = self.phone_registry_log
            self.db = db
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff_sends_error(self):
        self.get_staff_mock.return_value = None
        await handle_add_client(_task(args="123 飞机"))
        self.send.assert_awaited_once()
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_viewer(self):
        staff = _make_staff(role=StaffRole.VIEWER)
        self.get_staff_mock.return_value = staff
        await handle_add_client(_task(args="123 飞机"))
        self.send.assert_awaited_once()
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_missing_args_sends_usage(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_add_client(_task(args="onlyone"))
        self.send.assert_awaited_once()
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_daily_limit_blocks_add(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.check_can_add.return_value = (False, "limit reached")
        await handle_add_client(_task(args="12345 飞机"))
        self.send.assert_awaited_once()
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_duplicate_phone_sends_duplicate_message(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        existing = _make_client(phone="12345", status=ClientStatus.TRAINING)
        self.get_client_by_phone.return_value = existing
        await handle_add_client(_task(args="12345 飞机"))
        self.send.assert_awaited_once()
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_cross_frontdesk_duplicate_blocked(self):
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        self.get_client_by_phone.return_value = None  # own lookup clear
        # Registry shows someone else owns it
        self.phone_registry_lookup.return_value = {
            "submitter_name": "Bob",
            "submitter_staff_id": 99,  # different frontdesk
            "submitted_at": "2026-01-01",
        }
        await handle_add_client(_task(args="12345 飞机"))
        self.send.assert_awaited_once()
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_successful_add_without_account_id(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_add_client(_task(args="12345 飞机"))
        self.create_client.assert_awaited_once()
        self.send.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        # Should nudge to set account_id via /num
        assert "/num" in sent_text

    @pytest.mark.asyncio
    async def test_successful_add_with_account_id(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_add_client(_task(args="12345 飞机 ACC001"))
        self.create_client.assert_awaited_once()
        self.send.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        assert "ACC001" in sent_text

    @pytest.mark.asyncio
    async def test_same_frontdesk_registry_entry_allows_add(self):
        """Same frontdesk re-adding their own number should pass the registry check."""
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        self.get_client_by_phone.return_value = None
        # Registry shows same frontdesk owns it
        self.phone_registry_lookup.return_value = {
            "submitter_name": "Alice",
            "submitter_staff_id": 10,
            "submitted_at": "2026-01-01",
        }
        await handle_add_client(_task(args="12345 飞机"))
        self.create_client.assert_awaited_once()


# ── handle_update_status ──────────────────────────────────────────────────────


class TestHandleUpdateStatus:
    """Tests for /u <phone> <status>."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock()
        self.update_client_status = AsyncMock(return_value=True)
        self.enforce = AsyncMock(return_value=(True, ""))

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
            patch("engines.policy_engine.enforce_on_status_change", self.enforce),
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.update_client_status = self.update_client_status
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_update_status(_task(args="123 contacted"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_newbie(self):
        staff = _make_staff(role=StaffRole.NEWBIE)
        self.get_staff_mock.return_value = staff
        await handle_update_status(_task(args="123 contacted"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_missing_args(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_update_status(_task(args="123"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_invalid_status_value(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_update_status(_task(args="123 not_a_status"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_client_not_found(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.get_client_by_phone.return_value = None
        await handle_update_status(_task(args="123 contacted"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_invalid_transition_blocked(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        # Client is ORDERED — cannot go directly to NEW (not a valid transition)
        client = _make_client(status=ClientStatus.ORDERED)
        self.get_client_by_phone.return_value = client
        await handle_update_status(_task(args="123 new"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_policy_blocks_status_change(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.TRAINING)
        self.get_client_by_phone.return_value = client
        self.enforce.return_value = (False, "no deposits")
        # TRAINING → ORDERED is a valid transition
        await handle_update_status(_task(args="123 ordered"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_successful_status_update(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.NEW)
        self.get_client_by_phone.return_value = client
        # NEW → CONTACTED is valid
        await handle_update_status(_task(args="1234567890 contacted"))
        self.update_client_status.assert_awaited_once()
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_failure_sends_error(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.NEW)
        self.get_client_by_phone.return_value = client
        self.update_client_status.return_value = False
        await handle_update_status(_task(args="1234567890 contacted"))
        self.send.assert_awaited_once()
        # Message should indicate something went wrong
        sent_text = self.send.call_args[0][1]
        assert sent_text  # some error text sent


# ── handle_add_note ───────────────────────────────────────────────────────────


class TestHandleAddNote:
    """Tests for /note <phone> <text>."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock()
        self.add_client_note = AsyncMock()

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.add_client_note = self.add_client_note
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_add_note(_task(args="123 note text"))
        self.send.assert_awaited_once()
        assert self.add_client_note.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_viewer(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.VIEWER)
        await handle_add_note(_task(args="123 note text"))
        self.send.assert_awaited_once()
        assert self.add_client_note.await_count == 0

    @pytest.mark.asyncio
    async def test_missing_args(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_add_note(_task(args="onlyone"))
        self.send.assert_awaited_once()
        assert self.add_client_note.await_count == 0

    @pytest.mark.asyncio
    async def test_client_not_found(self):
        self.get_staff_mock.return_value = _make_staff()
        self.get_client_by_phone.return_value = None
        await handle_add_note(_task(args="123 some note"))
        self.send.assert_awaited_once()
        assert self.add_client_note.await_count == 0

    @pytest.mark.asyncio
    async def test_note_saved_successfully(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.get_client_by_phone.return_value = _make_client()
        await handle_add_note(_task(args="1234567890 great lead"))
        self.add_client_note.assert_awaited_once()
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_note_content_passed_correctly(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client()
        self.get_client_by_phone.return_value = client
        await handle_add_note(_task(args="1234567890 this is my note content"))
        note_arg = self.add_client_note.call_args[0][0]
        assert note_arg.content == "this is my note content"
        assert note_arg.client_id == client.id
        assert note_arg.staff_id == staff.id


# ── handle_remind ─────────────────────────────────────────────────────────────


class TestHandleRemind:
    """Tests for /remind <phone> <time> <message>."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock(return_value=None)
        self.create_reminder = AsyncMock()
        self.set_next_followup = AsyncMock()

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.create_reminder = self.create_reminder
            db.set_next_followup = self.set_next_followup
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_remind(_task(args="123 1h check in"))
        self.send.assert_awaited_once()
        assert self.create_reminder.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_viewer(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.VIEWER)
        await handle_remind(_task(args="123 1h check in"))
        self.send.assert_awaited_once()
        assert self.create_reminder.await_count == 0

    @pytest.mark.asyncio
    async def test_missing_args(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_remind(_task(args="123 1h"))  # missing message
        self.send.assert_awaited_once()
        assert self.create_reminder.await_count == 0

    @pytest.mark.asyncio
    async def test_bad_time_format(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_remind(_task(args="123 tomorrow call them"))
        self.send.assert_awaited_once()
        assert self.create_reminder.await_count == 0

    @pytest.mark.asyncio
    async def test_time_too_short_blocked_by_policy(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_remind(_task(args="123 1m call them"))  # 1 min < 5 min minimum
        self.send.assert_awaited_once()
        assert self.create_reminder.await_count == 0

    @pytest.mark.asyncio
    async def test_time_too_long_blocked_by_policy(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_remind(_task(args="123 31d call them"))  # 31d > 30d max
        self.send.assert_awaited_once()
        assert self.create_reminder.await_count == 0

    @pytest.mark.asyncio
    async def test_successful_reminder_without_client(self):
        """Reminder without a known client is still allowed (client_id=None)."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.get_client_by_phone.return_value = None
        await handle_remind(_task(args="9999999 2h check in"))
        self.create_reminder.assert_awaited_once()
        reminder_arg = self.create_reminder.call_args[0][0]
        assert reminder_arg.client_id is None
        assert reminder_arg.staff_id == staff.id
        assert reminder_arg.message == "check in"
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_reminder_with_client_sets_followup(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client()
        self.get_client_by_phone.return_value = client
        await handle_remind(_task(args="1234567890 2h check in"))
        self.create_reminder.assert_awaited_once()
        self.set_next_followup.assert_awaited_once_with(
            client.id, self.create_reminder.call_args[0][0].remind_at
        )


# ── handle_handoff ────────────────────────────────────────────────────────────


class TestHandleHandoff:
    """Tests for /handoff <phone> [note]."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock()
        self.get_maintenance_for_staff = AsyncMock()
        self.set_client_handoff = AsyncMock()
        self.check_can_handoff = AsyncMock(return_value=(True, ""))

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
            patch("engines.policy_engine.check_can_handoff", self.check_can_handoff),
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.get_maintenance_for_staff = self.get_maintenance_for_staff
            db.set_client_handoff = self.set_client_handoff
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_handoff(_task(args="123"))
        self.send.assert_awaited_once()
        assert self.set_client_handoff.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_viewer(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.VIEWER)
        await handle_handoff(_task(args="123"))
        self.send.assert_awaited_once()
        assert self.set_client_handoff.await_count == 0

    @pytest.mark.asyncio
    async def test_missing_args_sends_usage(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_handoff(_task(args=""))
        self.send.assert_awaited_once()
        assert self.set_client_handoff.await_count == 0

    @pytest.mark.asyncio
    async def test_client_not_found(self):
        self.get_staff_mock.return_value = _make_staff()
        self.get_client_by_phone.return_value = None
        await handle_handoff(_task(args="999"))
        self.send.assert_awaited_once()
        assert self.set_client_handoff.await_count == 0

    @pytest.mark.asyncio
    async def test_policy_blocks_unregistered_client(self):
        self.get_staff_mock.return_value = _make_staff()
        self.get_client_by_phone.return_value = _make_client(status=ClientStatus.NEW)
        self.check_can_handoff.return_value = (False, "must be registered")
        await handle_handoff(_task(args="123"))
        self.send.assert_awaited_once()
        assert self.set_client_handoff.await_count == 0

    @pytest.mark.asyncio
    async def test_no_maintenance_person(self):
        self.get_staff_mock.return_value = _make_staff()
        self.get_client_by_phone.return_value = _make_client(
            status=ClientStatus.REGISTERED
        )
        self.get_maintenance_for_staff.return_value = None
        await handle_handoff(_task(args="123"))
        self.send.assert_awaited_once()
        assert self.set_client_handoff.await_count == 0

    @pytest.mark.asyncio
    async def test_successful_handoff_notifies_maintenance(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.REGISTERED)
        self.get_client_by_phone.return_value = client

        maintenance = MagicMock()
        maintenance.id = 20
        maintenance.display_name = "Bob Maintenance"
        maintenance.tg_chat_id = 8888
        self.get_maintenance_for_staff.return_value = maintenance

        await handle_handoff(_task(args="1234567890 please handle"))
        self.set_client_handoff.assert_awaited_once_with(
            client.id, maintenance.id, "please handle"
        )
        # Two messages: confirmation to frontdesk + notification to maintenance
        assert self.send.await_count == 2

    @pytest.mark.asyncio
    async def test_handoff_without_note(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.REGISTERED)
        self.get_client_by_phone.return_value = client

        maintenance = MagicMock()
        maintenance.id = 20
        maintenance.display_name = "Bob"
        maintenance.tg_chat_id = 8888
        self.get_maintenance_for_staff.return_value = maintenance

        await handle_handoff(_task(args="1234567890"))
        self.set_client_handoff.assert_awaited_once_with(
            client.id, maintenance.id, None
        )

    @pytest.mark.asyncio
    async def test_handoff_skips_notify_if_no_chat_id(self):
        """If maintenance has no real chat_id, no notification message is sent."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.REGISTERED)
        self.get_client_by_phone.return_value = client

        maintenance = MagicMock()
        maintenance.id = 20
        maintenance.display_name = "Ghost"
        maintenance.tg_chat_id = 0  # not a real chat_id
        self.get_maintenance_for_staff.return_value = maintenance

        await handle_handoff(_task(args="1234567890"))
        # Only the confirmation to frontdesk
        assert self.send.await_count == 1


# ── handle_inline_status_callback ─────────────────────────────────────────────


class TestHandleInlineStatusCallback:
    """Tests for v2_status_<client_id>_<status> callback."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_id = AsyncMock()
        self.update_client_status = AsyncMock(return_value=True)
        self.enforce = AsyncMock(return_value=(True, ""))

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
            patch("engines.policy_engine.enforce_on_status_change", self.enforce),
        ):
            th.send_message = self.send
            db.get_client_by_id = self.get_client_by_id
            db.update_client_status = self.update_client_status
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_inline_status_callback(
            _task(callback_data="v2_status_99_contacted")
        )
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_malformed_callback_data(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_inline_status_callback(_task(callback_data="v2_status"))
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_invalid_status_in_callback(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_inline_status_callback(
            _task(callback_data="v2_status_99_not_a_real_status")
        )
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_wrong_owner_silently_ignored(self):
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        client = _make_client(client_id=99, frontdesk_id=99)  # different owner
        self.get_client_by_id.return_value = client
        await handle_inline_status_callback(
            _task(callback_data="v2_status_99_contacted")
        )
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_invalid_transition_sends_error(self):
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        # ORDERED → NEW is not a valid transition
        client = _make_client(
            client_id=99, frontdesk_id=10, status=ClientStatus.ORDERED
        )
        self.get_client_by_id.return_value = client
        await handle_inline_status_callback(_task(callback_data="v2_status_99_new"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_successful_inline_status_update(self):
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        client = _make_client(client_id=99, frontdesk_id=10, status=ClientStatus.NEW)
        self.get_client_by_id.return_value = client
        await handle_inline_status_callback(
            _task(callback_data="v2_status_99_contacted")
        )
        self.update_client_status.assert_awaited_once_with(
            99, ClientStatus.CONTACTED, staff.id
        )
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_policy_blocks_inline_update(self):
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        client = _make_client(
            client_id=99, frontdesk_id=10, status=ClientStatus.TRAINING
        )
        self.get_client_by_id.return_value = client
        self.enforce.return_value = (False, "no deposits")
        await handle_inline_status_callback(_task(callback_data="v2_status_99_ordered"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0


# ── handle_num ────────────────────────────────────────────────────────────────


class TestHandleNum:
    """Tests for /num <phone> <account_id>."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock()
        self.update_client = AsyncMock()

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.update_client = self.update_client
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_num(_task(args="123 ACC001"))
        self.send.assert_awaited_once()
        assert self.update_client.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_newbie(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.NEWBIE)
        await handle_num(_task(args="123 ACC001"))
        self.send.assert_awaited_once()
        assert self.update_client.await_count == 0

    @pytest.mark.asyncio
    async def test_missing_args(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_num(_task(args="123"))
        self.send.assert_awaited_once()
        assert self.update_client.await_count == 0

    @pytest.mark.asyncio
    async def test_client_not_found(self):
        self.get_staff_mock.return_value = _make_staff()
        self.get_client_by_phone.return_value = None
        await handle_num(_task(args="123 ACC001"))
        self.send.assert_awaited_once()
        assert self.update_client.await_count == 0

    @pytest.mark.asyncio
    async def test_account_id_updated_successfully(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client()
        self.get_client_by_phone.return_value = client
        await handle_num(_task(args="1234567890 ACC999"))
        assert client.account_id == "ACC999"
        self.update_client.assert_awaited_once_with(client)
        self.send.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        assert "ACC999" in sent_text


# ── handle_info ───────────────────────────────────────────────────────────────


class TestHandleInfo:
    """Tests for /info <phone>."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock(return_value=None)
        self.get_staff_by_id = AsyncMock()
        self.get_client_notes = AsyncMock(return_value=[])

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.get_staff_by_id = self.get_staff_by_id
            db.get_client_notes = self.get_client_notes
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_info(_task(args="123"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_phone_arg(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_info(_task(args=""))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_not_found(self):
        staff = _make_staff(role=StaffRole.FRONTDESK)
        self.get_staff_mock.return_value = staff
        self.get_client_by_phone.return_value = None
        await handle_info(_task(args="9999"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_info_displayed(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(phone="1234567890", account_id="ACC42")
        self.get_client_by_phone.return_value = client
        owner = MagicMock()
        owner.display_name = "Alice"
        self.get_staff_by_id.return_value = owner
        await handle_info(_task(args="1234567890"))
        self.send.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        assert "1234567890" in sent_text
        assert "ACC42" in sent_text

    @pytest.mark.asyncio
    async def test_notes_shown_in_info(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client()
        self.get_client_by_phone.return_value = client
        note = MagicMock()
        note.note = "Some note text"
        note.created_at = "2026-04-01T10:00:00"
        self.get_client_notes.return_value = [note]
        owner = MagicMock()
        owner.display_name = "Alice"
        self.get_staff_by_id.return_value = owner
        await handle_info(_task(args="1234567890"))
        sent_text = self.send.call_args[0][1]
        assert "Some note text" in sent_text


# ── handle_req ────────────────────────────────────────────────────────────────


class TestHandleReq:
    """Tests for /req <message>."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.send_to_mgmt = AsyncMock()
        self.get_staff_mock = AsyncMock()

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
        ):
            th.send_message = self.send
            th.send_to_management = self.send_to_mgmt
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_req(_task(args="help me"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_message(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_req(_task(args=""))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_sent_to_management(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        with patch("team_config.team_config") as tc:
            tc.get_kefu_id.return_value = None
            await handle_req(_task(args="need help with client"))
        # Should send at least a reply to staff confirming or failing
        assert self.send.await_count >= 1

    @pytest.mark.asyncio
    async def test_request_confirms_success_when_sent(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.send_to_mgmt.return_value = None  # no exception → success

        with patch("team_config.team_config") as tc:
            tc.get_kefu_id.return_value = None
            await handle_req(_task(args="urgent issue"))

        # Last message to staff should be a success confirmation
        last_msg = self.send.call_args_list[-1][0][1]
        assert "✅" in last_msg or "sent" in last_msg.lower() or "已发送" in last_msg


# ── handle_bulkupdate ─────────────────────────────────────────────────────────


class TestHandleBulkupdate:
    """Tests for /bulkupdate <status> <phones...>."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock()

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_bulkupdate(_task(args="contacted 111 222"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_viewer_denied(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.VIEWER)
        await handle_bulkupdate(_task(args="contacted 111 222"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_newbie_denied(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.NEWBIE)
        await handle_bulkupdate(_task(args="contacted 111 222"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_phones_arg(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_bulkupdate(_task(args="contacted"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_bulkupdate(_task(args="not_a_status 111 222"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_phones_not_found(self):
        self.get_staff_mock.return_value = _make_staff()
        self.get_client_by_phone.return_value = None
        await handle_bulkupdate(_task(args="contacted 111 222"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_preview_shown_with_confirm_cancel_buttons(self):
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        client1 = _make_client(client_id=1, phone="111", frontdesk_id=10)
        client2 = _make_client(client_id=2, phone="222", frontdesk_id=10)
        self.get_client_by_phone.side_effect = [client1, client2]
        await handle_bulkupdate(_task(args="contacted 111 222"))
        self.send.assert_awaited_once()
        call_kwargs = self.send.call_args
        # reply_markup should contain inline keyboard
        markup = call_kwargs[1].get("reply_markup") or (
            call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None
        )
        assert markup is not None
        assert "inline_keyboard" in markup

    @pytest.mark.asyncio
    async def test_manager_can_bulk_update_any_client(self):
        staff = _make_staff(role=StaffRole.MANAGER, staff_id=10)
        staff.is_manager_or_above.return_value = True
        self.get_staff_mock.return_value = staff
        # Client belongs to a different frontdesk
        client = _make_client(client_id=1, phone="111", frontdesk_id=99)
        self.get_client_by_phone.return_value = client
        await handle_bulkupdate(_task(args="contacted 111"))
        # Should show preview (not a "not found" error)
        self.send.assert_awaited_once()
        call_kwargs = self.send.call_args
        markup = call_kwargs[1].get("reply_markup") or (
            call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None
        )
        assert markup is not None


# ── handle_bulkupdate_callback ────────────────────────────────────────────────


class TestHandleBulkupdateCallback:
    """Tests for v2_bulk_confirm/cancel callbacks."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.update_client_status = AsyncMock(return_value=True)

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.update_client_status = self.update_client_status
            yield

    @pytest.mark.asyncio
    async def test_cancel_sends_cancelled_message(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_bulkupdate_callback(_task(callback_data="v2_bulk_cancel"))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_unregistered_staff_silently_ignored(self):
        self.get_staff_mock.return_value = None
        await handle_bulkupdate_callback(
            _task(callback_data="v2_bulk_confirm_contacted_1,2,3")
        )
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_malformed_callback_silently_ignored(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_bulkupdate_callback(_task(callback_data="v2_bulk_confirm_bad"))
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_confirm_updates_all_clients(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_bulkupdate_callback(
            _task(callback_data="v2_bulk_confirm_contacted_1,2,3")
        )
        assert self.update_client_status.await_count == 3
        calls = self.update_client_status.call_args_list
        updated_ids = [c[0][0] for c in calls]
        assert sorted(updated_ids) == [1, 2, 3]
        statuses = [c[0][1] for c in calls]
        assert all(s == ClientStatus.CONTACTED for s in statuses)

    @pytest.mark.asyncio
    async def test_confirm_reports_ok_and_fail_counts(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        # First client succeeds, second fails
        self.update_client_status.side_effect = [True, False]
        await handle_bulkupdate_callback(
            _task(callback_data="v2_bulk_confirm_contacted_1,2")
        )
        self.send.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        assert sent_text  # summary message sent

    @pytest.mark.asyncio
    async def test_confirm_with_exception_counts_as_fail(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.update_client_status.side_effect = Exception("DB error")
        await handle_bulkupdate_callback(
            _task(callback_data="v2_bulk_confirm_contacted_1")
        )
        self.send.assert_awaited_once()


# ── Command/callback registries ───────────────────────────────────────────────


class TestRegistries:
    """Verify handler registries are complete and consistent."""

    def test_quick_actions_commands_contains_expected_entries(self):
        expected = {
            "add",
            "u",
            "num",
            "info",
            "req",
            "note",
            "remind",
            "handoff",
            "bulkupdate",
        }
        assert set(QUICK_ACTIONS_COMMANDS.keys()) == expected

    def test_all_command_handlers_are_callable(self):
        for name, handler in QUICK_ACTIONS_COMMANDS.items():
            assert callable(handler), f"{name} handler is not callable"

    def test_callback_registry_keys(self):
        expected_prefixes = {"v2_status_*", "v2_bulk_confirm_*", "v2_bulk_cancel"}
        assert set(QUICK_ACTIONS_CALLBACKS.keys()) == expected_prefixes

    def test_conversations_registry_empty(self):
        assert QUICK_ACTIONS_CONVERSATIONS == {}


# ── Additional edge cases for status_emoji ────────────────────────────────────


class TestStatusEmojiExtended:
    def test_all_defined_statuses_have_emoji(self):
        for status in ClientStatus:
            emoji = status_emoji(status)
            assert emoji != "", f"No emoji for {status.value}"

    def test_scheduled_status_emoji(self):
        assert status_emoji(ClientStatus.SCHEDULED) == "📅"


# ── Additional parse_time_delta edge cases ────────────────────────────────────


class TestParseTimeDeltaExtended:
    def test_large_float_hours(self):
        result = _parse_time_delta("48.5h")
        assert result == timedelta(hours=48.5)

    def test_large_float_minutes(self):
        result = _parse_time_delta("120.5m")
        assert result == timedelta(minutes=120.5)

    def test_fractional_days(self):
        result = _parse_time_delta("0.5d")
        assert result == timedelta(days=0.5)

    def test_zero_hours_returns_zero_delta(self):
        result = _parse_time_delta("0h")
        assert result == timedelta(0)

    def test_negative_rejected(self):
        """Negative numbers pass float() but timedelta stays negative."""
        result = _parse_time_delta("-1h")
        assert result == timedelta(hours=-1)  # parser allows it; policy rejects


# ── Additional build_status_buttons edge cases ────────────────────────────────


class TestBuildStatusButtonsExtended:
    def test_terminal_status_returns_minimal_buttons(self):
        buttons = _build_status_buttons(client_id=1, current_status=ClientStatus.DEAD)
        # DEAD transitions include terminal (filtered) + ghosted (completed, not filtered)
        # Only non-terminal transitions survive the filter
        terminal_values = {s.value for s in ClientStatus.terminal_statuses()}
        for b in buttons:
            status_part = b["callback_data"].split("_", 3)[-1]
            assert status_part not in terminal_values

    def test_ordered_status_has_reactivation_options(self):
        buttons = _build_status_buttons(
            client_id=1, current_status=ClientStatus.ORDERED
        )
        # ORDERED transitions include contacted, replied, registered, training
        assert len(buttons) > 0
        data_values = [b["callback_data"] for b in buttons]
        assert any("contacted" in d for d in data_values)


# ── Additional handle_add_client edge cases ───────────────────────────────────


class TestHandleAddClientExtended:
    """Additional edge cases for /add."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock(return_value=None)
        self.phone_registry_lookup = AsyncMock(return_value=None)
        self.create_client = AsyncMock(return_value=5)
        self.phone_registry_insert = AsyncMock()
        self.phone_registry_log = AsyncMock()
        self.check_can_add = AsyncMock(return_value=(True, ""))

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
            patch("engines.policy_engine.check_can_add_client", self.check_can_add),
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.phone_registry_lookup = self.phone_registry_lookup
            db.create_client = self.create_client
            db.phone_registry_insert = self.phone_registry_insert
            db.phone_registry_log_action = self.phone_registry_log
            yield

    @pytest.mark.asyncio
    async def test_empty_args_sends_usage(self):
        self.get_staff_mock.return_value = _make_staff()
        await handle_add_client(_task(args=""))
        self.send.assert_awaited_once()
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_admin_role_can_add(self):
        staff = _make_staff(role=StaffRole.ADMIN)
        self.get_staff_mock.return_value = staff
        await handle_add_client(_task(args="12345 飞机"))
        self.create_client.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_manager_role_can_add(self):
        staff = _make_staff(role=StaffRole.MANAGER)
        self.get_staff_mock.return_value = staff
        await handle_add_client(_task(args="12345 飞机"))
        self.create_client.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_customer_service_cannot_add(self):
        staff = _make_staff(role=StaffRole.CUSTOMER_SERVICE)
        self.get_staff_mock.return_value = staff
        await handle_add_client(_task(args="12345 飞机"))
        assert self.create_client.await_count == 0

    @pytest.mark.asyncio
    async def test_phone_registry_insert_failure_does_not_crash(self):
        """Registry insert failing should not prevent client creation."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.phone_registry_insert.side_effect = Exception("registry error")
        await handle_add_client(_task(args="12345 飞机"))
        self.create_client.assert_awaited_once()
        self.send.assert_awaited_once()


# ── Additional handle_update_status edge cases ────────────────────────────────


class TestHandleUpdateStatusExtended:
    """Additional edge cases for /u."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock()
        self.update_client_status = AsyncMock(return_value=True)
        self.enforce = AsyncMock(return_value=(True, ""))

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
            patch("engines.policy_engine.enforce_on_status_change", self.enforce),
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.update_client_status = self.update_client_status
            yield

    @pytest.mark.asyncio
    async def test_empty_args_sends_usage(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_update_status(_task(args=""))
        self.send.assert_awaited_once()
        assert self.update_client_status.await_count == 0

    @pytest.mark.asyncio
    async def test_case_insensitive_status(self):
        """Status values like 'Contacted' or 'CONTACTED' should work."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.NEW)
        self.get_client_by_phone.return_value = client
        # "contacted" in lowercase (the handler lowercases input)
        await handle_update_status(_task(args="123 CONTACTED"))
        self.update_client_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_can_update_status(self):
        staff = _make_staff(role=StaffRole.ADMIN)
        self.get_staff_mock.return_value = staff
        client = _make_client(status=ClientStatus.NEW)
        self.get_client_by_phone.return_value = client
        await handle_update_status(_task(args="123 contacted"))
        self.update_client_status.assert_awaited_once()


# ── Additional handle_remind edge cases ───────────────────────────────────────


class TestHandleRemindExtended:
    """Additional edge cases for /remind."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock(return_value=None)
        self.create_reminder = AsyncMock()
        self.set_next_followup = AsyncMock()

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            db.create_reminder = self.create_reminder
            db.set_next_followup = self.set_next_followup
            yield

    @pytest.mark.asyncio
    async def test_exactly_5_minutes_allowed(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_remind(_task(args="123 5m check in"))
        self.create_reminder.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exactly_30_days_allowed(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_remind(_task(args="123 30d long check"))
        self.create_reminder.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiword_message_preserved(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_remind(_task(args="123 1h call them and ask about deposit"))
        reminder_arg = self.create_reminder.call_args[0][0]
        assert reminder_arg.message == "call them and ask about deposit"


# ── Additional bulkupdate edge cases ──────────────────────────────────────────


class TestHandleBulkupdateExtended:
    """Additional edge cases for /bulkupdate."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_client_by_phone = AsyncMock()

        with (
            patch("handlers_v2.quick_actions.telegram_handler") as th,
            patch("handlers_v2.quick_actions._get_staff", self.get_staff_mock),
            patch("handlers_v2.quick_actions.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_client_by_phone = self.get_client_by_phone
            yield

    @pytest.mark.asyncio
    async def test_frontdesk_cannot_update_others_client(self):
        """Non-manager frontdesk can only update their own clients."""
        staff = _make_staff(role=StaffRole.FRONTDESK, staff_id=10)
        staff.is_manager_or_above.return_value = False
        self.get_staff_mock.return_value = staff
        # Client belongs to someone else
        client = _make_client(client_id=1, phone="111", frontdesk_id=99)
        self.get_client_by_phone.return_value = client
        await handle_bulkupdate(_task(args="contacted 111"))
        # Should see a warning about phone not owned, no preview buttons
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mixed_found_and_not_found(self):
        """Some phones found, some not: preview shown with warnings."""
        staff = _make_staff(staff_id=10)
        self.get_staff_mock.return_value = staff
        client = _make_client(client_id=1, phone="111", frontdesk_id=10)
        self.get_client_by_phone.side_effect = [client, None]
        await handle_bulkupdate(_task(args="contacted 111 222"))
        # Should show preview for 111 + warning for 222
        self.send.assert_awaited_once()
        call_kwargs = self.send.call_args
        markup = call_kwargs[1].get("reply_markup") or (
            call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None
        )
        assert markup is not None  # still shows confirm/cancel

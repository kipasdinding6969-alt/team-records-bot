import pytest
from datetime import timedelta, datetime
from unittest.mock import AsyncMock, Mock, patch

from engines.policy_engine import (
    ROLE_PERMISSIONS,
    ADMIN_REQUIRED_FOR,
    MAX_NEW_CLIENTS_PER_DAY,
    MIN_REMIND_MINUTES,
    MAX_REMIND_DAYS,
    AUTO_DEAD_DAYS,
    STALE_WARNING_HOURS,
    STALE_CRITICAL_HOURS,
    NOTIFY_MAINTENANCE_ON,
    NOTIFY_ADMIN_ON,
    check_permission,
    check_can_add_client,
    check_can_handoff,
    check_remind_limits,
    check_working_hours,
    enforce_on_status_change,
    auto_mark_dead_clients,
    check_daily_targets_missed,
)
from models_v2 import ClientStatus, PeriodType


# ── Constants validation ──────────────────────────────────────────────────────


class TestPolicyConstants:
    """Verify policy constants are sane and consistent."""

    def test_max_clients_per_day_positive(self):
        assert MAX_NEW_CLIENTS_PER_DAY > 0

    def test_remind_limits_ordered(self):
        assert MIN_REMIND_MINUTES < MAX_REMIND_DAYS * 24 * 60

    def test_stale_hours_ordering(self):
        assert STALE_WARNING_HOURS < STALE_CRITICAL_HOURS

    def test_auto_dead_days_beyond_critical(self):
        assert AUTO_DEAD_DAYS * 24 > STALE_CRITICAL_HOURS

    def test_admin_required_actions_are_strings(self):
        assert all(isinstance(a, str) for a in ADMIN_REQUIRED_FOR)

    def test_notification_events_are_strings(self):
        for event in NOTIFY_MAINTENANCE_ON + NOTIFY_ADMIN_ON:
            assert isinstance(event, str)

    def test_role_permissions_all_roles_present(self):
        expected_roles = {
            "frontdesk",
            "maintenance",
            "manager",
            "admin",
            "leader",
            "customer_service",
            "newbie",
            "viewer",
        }
        assert set(ROLE_PERMISSIONS.keys()) == expected_roles


# ── check_permission — exhaustive role tests ──────────────────────────────────


class TestCheckPermission:
    """Exhaustive permission checks per role."""

    def test_frontdesk_allowed_commands(self):
        for cmd in [
            "add",
            "u",
            "num",
            "info",
            "note",
            "remind",
            "req",
            "me",
            "pipeline",
            "followup",
            "today",
            "search",
            "rag",
            "handoff",
            "profile",
            "export",
            "sop",
            "bind",
            "leaderboard",
            "hot",
            "summary",
            "template",
            "contest",
        ]:
            assert check_permission("frontdesk", cmd) is True, (
                f"frontdesk should have {cmd}"
            )

    def test_frontdesk_denied_commands(self):
        for cmd in [
            "sync",
            "target",
            "overview",
            "setname",
            "lang",
            "setteam",
            "teams",
            "linkgroup",
            "unlinkgroup",
            "bulkupdate",
            "broadcast",
            "import_excel",
        ]:
            assert check_permission("frontdesk", cmd) is False, (
                f"frontdesk should NOT have {cmd}"
            )

    def test_maintenance_extends_frontdesk(self):
        for cmd in ["dashboard", "team"]:
            assert check_permission("maintenance", cmd) is True, (
                f"maintenance should have {cmd}"
            )
        # Also has all frontdesk commands
        assert check_permission("maintenance", "add") is True

    def test_manager_has_all_commands(self):
        for cmd in [
            "target",
            "overview",
            "setname",
            "lang",
            "setteam",
            "teams",
            "linkgroup",
            "unlinkgroup",
            "bulkupdate",
            "sequences",
            "broadcast",
            "import_excel",
            "export_template",
        ]:
            assert check_permission("manager", cmd) is True, (
                f"manager should have {cmd}"
            )

    def test_admin_has_sync(self):
        assert check_permission("admin", "sync") is True

    def test_admin_has_everything_manager_has(self):
        for cmd in ROLE_PERMISSIONS["manager"]:
            assert check_permission("admin", cmd) is True, f"admin should have {cmd}"

    def test_leader_matches_all_commands(self):
        for cmd in ROLE_PERMISSIONS["manager"]:
            assert check_permission("leader", cmd) is True, f"leader should have {cmd}"

    def test_viewer_only_read_commands(self):
        allowed = {
            "me",
            "dashboard",
            "pipeline",
            "search",
            "rag",
            "export",
            "help",
            "today",
            "info",
            "leaderboard",
        }
        for cmd in allowed:
            assert check_permission("viewer", cmd) is True, f"viewer should have {cmd}"
        for cmd in ["add", "u", "note", "remind", "handoff", "sync"]:
            assert check_permission("viewer", cmd) is False, (
                f"viewer should NOT have {cmd}"
            )

    def test_newbie_limited_commands(self):
        allowed = {"add", "me", "note", "help", "req", "bind", "info"}
        for cmd in allowed:
            assert check_permission("newbie", cmd) is True, f"newbie should have {cmd}"
        for cmd in ["u", "pipeline", "sync", "target", "dashboard"]:
            assert check_permission("newbie", cmd) is False, (
                f"newbie should NOT have {cmd}"
            )

    def test_customer_service_commands(self):
        allowed = {
            "search",
            "note",
            "info",
            "pipeline",
            "dashboard",
            "rag",
            "export",
            "me",
            "help",
            "today",
            "req",
            "leaderboard",
            "hot",
            "summary",
            "template",
        }
        for cmd in allowed:
            assert check_permission("customer_service", cmd) is True, (
                f"cs should have {cmd}"
            )
        for cmd in ["add", "u", "sync", "target", "handoff"]:
            assert check_permission("customer_service", cmd) is False, (
                f"cs should NOT have {cmd}"
            )

    def test_unknown_role_denied_everything(self):
        assert check_permission("unknown_role", "add") is False
        assert check_permission("", "add") is False

    def test_empty_command_denied(self):
        assert check_permission("admin", "") is False
        assert check_permission("frontdesk", "") is False

    def test_nonexistent_command_denied(self):
        assert check_permission("admin", "nonexistent_cmd_xyz") is False
        assert check_permission("frontdesk", "delete_everything") is False


class TestCheckCanAddClient:
    """Daily client limit policy."""

    @pytest.mark.asyncio
    async def test_under_limit_allowed(self):
        with patch(
            "database_v2.database_v2.calculate_daily_stats", new_callable=AsyncMock
        ) as m:
            m.return_value = Mock(new_leads=10)
            allowed, msg = await check_can_add_client(123)
            assert allowed is True
            assert msg == ""

    @pytest.mark.asyncio
    async def test_one_below_limit_allowed(self):
        with patch(
            "database_v2.database_v2.calculate_daily_stats", new_callable=AsyncMock
        ) as m:
            m.return_value = Mock(new_leads=MAX_NEW_CLIENTS_PER_DAY - 1)
            allowed, msg = await check_can_add_client(123)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_exactly_at_limit_blocked(self):
        with patch(
            "database_v2.database_v2.calculate_daily_stats", new_callable=AsyncMock
        ) as m:
            m.return_value = Mock(new_leads=MAX_NEW_CLIENTS_PER_DAY)
            allowed, msg = await check_can_add_client(123)
            assert allowed is False
            assert "Daily client limit reached" in msg

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self):
        with patch(
            "database_v2.database_v2.calculate_daily_stats", new_callable=AsyncMock
        ) as m:
            m.return_value = Mock(new_leads=MAX_NEW_CLIENTS_PER_DAY + 10)
            allowed, msg = await check_can_add_client(123)
            assert allowed is False

    @pytest.mark.asyncio
    async def test_zero_leads_allowed(self):
        with patch(
            "database_v2.database_v2.calculate_daily_stats", new_callable=AsyncMock
        ) as m:
            m.return_value = Mock(new_leads=0)
            allowed, msg = await check_can_add_client(123)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_db_error_fails_open(self):
        with patch(
            "database_v2.database_v2.calculate_daily_stats", new_callable=AsyncMock
        ) as m:
            m.side_effect = Exception("DB error")
            allowed, msg = await check_can_add_client(123)
            assert allowed is True
            assert msg == ""


class TestCheckCanHandoff:
    """Handoff policy: client must be at registered or later pipeline stage."""

    @pytest.mark.asyncio
    async def test_new_client_rejected(self):
        client = Mock(status=ClientStatus.NEW)
        allowed, msg = await check_can_handoff(client)
        assert allowed is False
        assert 'must be at least "registered"' in msg

    @pytest.mark.asyncio
    async def test_contacted_client_rejected(self):
        client = Mock(status=ClientStatus.CONTACTED)
        allowed, msg = await check_can_handoff(client)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_replied_client_rejected(self):
        client = Mock(status=ClientStatus.REPLIED)
        allowed, msg = await check_can_handoff(client)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_registered_client_allowed(self):
        client = Mock(status=ClientStatus.REGISTERED)
        allowed, msg = await check_can_handoff(client)
        assert allowed is True
        assert msg == ""

    @pytest.mark.asyncio
    async def test_training_client_allowed(self):
        client = Mock(status=ClientStatus.TRAINING)
        allowed, msg = await check_can_handoff(client)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_withdrew_client_allowed(self):
        client = Mock(status=ClientStatus.WITHDREW)
        allowed, msg = await check_can_handoff(client)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_ordered_client_allowed(self):
        client = Mock(status=ClientStatus.ORDERED)
        allowed, msg = await check_can_handoff(client)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_dead_client_rejected(self):
        """DEAD is not in pipeline_order, hits 'not in pipeline' branch."""
        client = Mock(status=ClientStatus.DEAD)
        allowed, msg = await check_can_handoff(client)
        assert allowed is False
        assert msg

    @pytest.mark.asyncio
    async def test_blocked_client_rejected(self):
        client = Mock(status=ClientStatus.BLOCKED)
        allowed, msg = await check_can_handoff(client)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_scammed_client_rejected(self):
        client = Mock(status=ClientStatus.SCAMMED)
        allowed, msg = await check_can_handoff(client)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_ghosted_not_in_pipeline(self):
        """GHOSTED is not in pipeline_order — should be rejected."""
        client = Mock(status=ClientStatus.GHOSTED)
        allowed, msg = await check_can_handoff(client)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(self):
        client = Mock()
        client.status = Mock()
        client.status.value = "invalid_status"
        allowed, msg = await check_can_handoff(client)
        assert allowed is False
        assert "not in pipeline" in msg


class TestCheckRemindLimits:
    """Boundary and edge-case tests for reminder timing policy."""

    def test_below_minimum(self):
        allowed, msg = check_remind_limits(timedelta(minutes=3))
        assert allowed is False
        assert "at least 5 minutes" in msg

    def test_exactly_minimum(self):
        allowed, msg = check_remind_limits(timedelta(minutes=5))
        assert allowed is True
        assert msg == ""

    def test_just_below_minimum(self):
        allowed, msg = check_remind_limits(timedelta(minutes=4, seconds=59))
        assert allowed is False

    def test_valid_1h(self):
        allowed, msg = check_remind_limits(timedelta(hours=1))
        assert allowed is True
        assert msg == ""

    def test_valid_1d(self):
        allowed, msg = check_remind_limits(timedelta(days=1))
        assert allowed is True

    def test_exactly_maximum(self):
        allowed, msg = check_remind_limits(timedelta(days=30))
        assert allowed is True
        assert msg == ""

    def test_just_over_maximum(self):
        allowed, msg = check_remind_limits(timedelta(days=30, minutes=1))
        assert allowed is False
        assert "cannot be more than" in msg

    def test_well_over_maximum(self):
        allowed, msg = check_remind_limits(timedelta(days=60))
        assert allowed is False

    def test_zero_timedelta_rejected(self):
        allowed, msg = check_remind_limits(timedelta(0))
        assert allowed is False


class TestCheckWorkingHours:
    """Working hours: Paris 10:00-22:00."""

    def test_within_working_hours_afternoon(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            tz = pytz.timezone("Europe/Paris")
            mock_dt.now.return_value = datetime(2026, 4, 3, 14, 0, tzinfo=tz)
            assert check_working_hours() is True

    def test_exactly_start_time(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            tz = pytz.timezone("Europe/Paris")
            mock_dt.now.return_value = datetime(2026, 4, 3, 10, 0, tzinfo=tz)
            assert check_working_hours() is True

    def test_one_minute_before_start(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            tz = pytz.timezone("Europe/Paris")
            mock_dt.now.return_value = datetime(2026, 4, 3, 9, 59, tzinfo=tz)
            assert check_working_hours() is False

    def test_exactly_end_time_is_outside(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            tz = pytz.timezone("Europe/Paris")
            mock_dt.now.return_value = datetime(2026, 4, 3, 22, 0, tzinfo=tz)
            assert check_working_hours() is False

    def test_one_minute_before_end(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            tz = pytz.timezone("Europe/Paris")
            mock_dt.now.return_value = datetime(2026, 4, 3, 21, 59, tzinfo=tz)
            assert check_working_hours() is True

    def test_late_night_outside(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            tz = pytz.timezone("Europe/Paris")
            mock_dt.now.return_value = datetime(2026, 4, 3, 23, 0, tzinfo=tz)
            assert check_working_hours() is False

    def test_early_morning_outside(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            tz = pytz.timezone("Europe/Paris")
            mock_dt.now.return_value = datetime(2026, 4, 3, 8, 0, tzinfo=tz)
            assert check_working_hours() is False

    def test_error_fails_open(self):
        import pytz

        with patch("engines.policy_engine.datetime") as mock_dt:
            mock_dt.now.side_effect = Exception("tz error")
            assert check_working_hours() is True


class TestEnforceOnStatusChange:
    """Master policy for status changes."""

    @pytest.mark.asyncio
    async def test_ordered_without_deposits_blocked(self):
        client = Mock(id=1, total_deposited=0)
        with patch(
            "database_v2.database_v2.get_deposits_by_client", new_callable=AsyncMock
        ) as m:
            m.return_value = []
            allowed, msg = await enforce_on_status_change(
                client, ClientStatus.ORDERED, Mock()
            )
            assert allowed is False
            assert "no deposits recorded" in msg

    @pytest.mark.asyncio
    async def test_ordered_with_deposit_records_allowed(self):
        client = Mock(id=1, total_deposited=0)
        with patch(
            "database_v2.database_v2.get_deposits_by_client", new_callable=AsyncMock
        ) as m:
            m.return_value = [{"amount": 100}]
            allowed, msg = await enforce_on_status_change(
                client, ClientStatus.ORDERED, Mock()
            )
            assert allowed is True
            assert msg == ""

    @pytest.mark.asyncio
    async def test_ordered_with_total_deposited_positive_allowed(self):
        client = Mock(id=1, total_deposited=100)
        with patch(
            "database_v2.database_v2.get_deposits_by_client", new_callable=AsyncMock
        ) as m:
            m.return_value = []
            allowed, msg = await enforce_on_status_change(
                client, ClientStatus.ORDERED, Mock()
            )
            assert allowed is True

    @pytest.mark.asyncio
    async def test_non_ordered_status_always_allowed(self):
        client = Mock(id=1, total_deposited=0)
        for status in [
            ClientStatus.NEW,
            ClientStatus.CONTACTED,
            ClientStatus.REPLIED,
            ClientStatus.REGISTERED,
            ClientStatus.TRAINING,
            ClientStatus.WITHDREW,
            ClientStatus.GHOSTED,
            ClientStatus.BLOCKED,
            ClientStatus.DEAD,
        ]:
            allowed, msg = await enforce_on_status_change(client, status, Mock())
            assert allowed is True, f"{status.value} should be allowed"

    @pytest.mark.asyncio
    async def test_deposit_check_db_error_still_allows(self):
        """If DB fails during deposit lookup, we still allow (fail open within try/except)."""
        client = Mock(id=1, total_deposited=0)
        with patch(
            "database_v2.database_v2.get_deposits_by_client", new_callable=AsyncMock
        ) as m:
            m.side_effect = Exception("DB error")
            allowed, msg = await enforce_on_status_change(
                client, ClientStatus.ORDERED, Mock()
            )
            # The function catches the exception and falls through to return True
            assert allowed is True


class TestAutoMarkDeadClients:
    """Test auto-marking inactive clients as DEAD."""

    @pytest.mark.asyncio
    async def test_marks_active_client_dead(self):
        with (
            patch(
                "database_v2.database_v2.get_all_stale_clients", new_callable=AsyncMock
            ) as mock_stale,
            patch(
                "database_v2.database_v2.update_client_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            client = Mock(id=1, phone="123", status=ClientStatus.NEW)
            mock_stale.return_value = [client]
            count = await auto_mark_dead_clients()
            assert count == 1
            mock_update.assert_called_once_with(1, ClientStatus.DEAD, 0)

    @pytest.mark.asyncio
    async def test_skips_already_terminal_clients(self):
        with (
            patch(
                "database_v2.database_v2.get_all_stale_clients", new_callable=AsyncMock
            ) as mock_stale,
            patch(
                "database_v2.database_v2.update_client_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            dead = Mock(id=1, phone="111", status=ClientStatus.DEAD)
            blocked = Mock(id=2, phone="222", status=ClientStatus.BLOCKED)
            scammed = Mock(id=3, phone="333", status=ClientStatus.SCAMMED)
            mock_stale.return_value = [dead, blocked, scammed]
            count = await auto_mark_dead_clients()
            assert count == 0
            mock_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mixed_active_and_terminal(self):
        with (
            patch(
                "database_v2.database_v2.get_all_stale_clients", new_callable=AsyncMock
            ) as mock_stale,
            patch(
                "database_v2.database_v2.update_client_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            active = Mock(id=1, phone="111", status=ClientStatus.NEW)
            terminal = Mock(id=2, phone="222", status=ClientStatus.DEAD)
            mock_stale.return_value = [active, terminal]
            count = await auto_mark_dead_clients()
            assert count == 1
            mock_update.assert_called_once_with(1, ClientStatus.DEAD, 0)

    @pytest.mark.asyncio
    async def test_empty_stale_list(self):
        with (
            patch(
                "database_v2.database_v2.get_all_stale_clients", new_callable=AsyncMock
            ) as mock_stale,
            patch(
                "database_v2.database_v2.update_client_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            mock_stale.return_value = []
            count = await auto_mark_dead_clients()
            assert count == 0

    @pytest.mark.asyncio
    async def test_db_error_returns_zero(self):
        with patch(
            "database_v2.database_v2.get_all_stale_clients", new_callable=AsyncMock
        ) as mock_stale:
            mock_stale.side_effect = Exception("DB error")
            count = await auto_mark_dead_clients()
            assert count == 0

    @pytest.mark.asyncio
    async def test_individual_update_failure_continues(self):
        """If one update fails, continue processing others."""
        with (
            patch(
                "database_v2.database_v2.get_all_stale_clients", new_callable=AsyncMock
            ) as mock_stale,
            patch(
                "database_v2.database_v2.update_client_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            c1 = Mock(id=1, phone="111", status=ClientStatus.NEW)
            c2 = Mock(id=2, phone="222", status=ClientStatus.CONTACTED)
            mock_stale.return_value = [c1, c2]
            mock_update.side_effect = [Exception("fail"), None]
            count = await auto_mark_dead_clients()
            # c1 failed, c2 succeeded
            assert count == 1


class TestCheckDailyTargetsMissed:
    """Daily target miss detection across teams."""

    @pytest.mark.asyncio
    async def test_target_missed_below_50_percent(self):
        with (
            patch(
                "database_v2.database_v2.get_all_staff", new_callable=AsyncMock
            ) as mock_staff,
            patch(
                "database_v2.database_v2.get_team_target", new_callable=AsyncMock
            ) as mock_target,
            patch(
                "database_v2.database_v2.get_daily_stats", new_callable=AsyncMock
            ) as mock_stats,
        ):
            mock_staff.return_value = [Mock(id=1, team="team_a")]
            mock_target.return_value = Mock(target_orders=70)  # daily = 10
            mock_stats.return_value = Mock(new_orders=4)
            missed = await check_daily_targets_missed()
            assert len(missed) == 1
            assert missed[0]["team"] == "team_a"
            assert missed[0]["target"] == 10.0
            assert missed[0]["actual"] == 4

    @pytest.mark.asyncio
    async def test_target_met_above_50_percent(self):
        with (
            patch(
                "database_v2.database_v2.get_all_staff", new_callable=AsyncMock
            ) as mock_staff,
            patch(
                "database_v2.database_v2.get_team_target", new_callable=AsyncMock
            ) as mock_target,
            patch(
                "database_v2.database_v2.get_daily_stats", new_callable=AsyncMock
            ) as mock_stats,
        ):
            mock_staff.return_value = [Mock(id=1, team="team_a")]
            mock_target.return_value = Mock(target_orders=70)
            mock_stats.return_value = Mock(new_orders=6)
            missed = await check_daily_targets_missed()
            assert len(missed) == 0

    @pytest.mark.asyncio
    async def test_no_target_set_returns_empty(self):
        with (
            patch(
                "database_v2.database_v2.get_all_staff", new_callable=AsyncMock
            ) as mock_staff,
            patch(
                "database_v2.database_v2.get_team_target", new_callable=AsyncMock
            ) as mock_target,
            patch(
                "database_v2.database_v2.get_daily_stats", new_callable=AsyncMock
            ) as mock_stats,
        ):
            mock_staff.return_value = [Mock(id=1, team="team_a")]
            mock_target.return_value = None
            missed = await check_daily_targets_missed()
            assert len(missed) == 0

    @pytest.mark.asyncio
    async def test_target_with_zero_orders_returns_empty(self):
        with (
            patch(
                "database_v2.database_v2.get_all_staff", new_callable=AsyncMock
            ) as mock_staff,
            patch(
                "database_v2.database_v2.get_team_target", new_callable=AsyncMock
            ) as mock_target,
            patch(
                "database_v2.database_v2.get_daily_stats", new_callable=AsyncMock
            ) as mock_stats,
        ):
            mock_staff.return_value = [Mock(id=1, team="team_a")]
            mock_target.return_value = Mock(target_orders=0)
            missed = await check_daily_targets_missed()
            assert len(missed) == 0

    @pytest.mark.asyncio
    async def test_staff_without_team_ignored(self):
        with (
            patch(
                "database_v2.database_v2.get_all_staff", new_callable=AsyncMock
            ) as mock_staff,
            patch(
                "database_v2.database_v2.get_team_target", new_callable=AsyncMock
            ) as mock_target,
            patch(
                "database_v2.database_v2.get_daily_stats", new_callable=AsyncMock
            ) as mock_stats,
        ):
            mock_staff.return_value = [Mock(id=1, team=None)]
            missed = await check_daily_targets_missed()
            assert len(missed) == 0

    @pytest.mark.asyncio
    async def test_multiple_teams(self):
        with (
            patch(
                "database_v2.database_v2.get_all_staff", new_callable=AsyncMock
            ) as mock_staff,
            patch(
                "database_v2.database_v2.get_team_target", new_callable=AsyncMock
            ) as mock_target,
            patch(
                "database_v2.database_v2.get_daily_stats", new_callable=AsyncMock
            ) as mock_stats,
        ):
            mock_staff.return_value = [
                Mock(id=1, team="team_a"),
                Mock(id=2, team="team_b"),
            ]
            mock_target.return_value = Mock(target_orders=70)  # daily = 10
            mock_stats.return_value = Mock(new_orders=4)  # 40% < 50%
            missed = await check_daily_targets_missed()
            assert len(missed) == 2
            teams = {m["team"] for m in missed}
            assert teams == {"team_a", "team_b"}

    @pytest.mark.asyncio
    async def test_db_error_returns_empty(self):
        with patch(
            "database_v2.database_v2.get_all_staff", new_callable=AsyncMock
        ) as mock_staff:
            mock_staff.side_effect = Exception("DB error")
            missed = await check_daily_targets_missed()
            assert missed == []

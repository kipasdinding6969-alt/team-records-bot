"""Tests for handlers_v2/pipeline.py — /pipeline, /followup, /today, /search,
/rag, /me, /overview, /sop and helper functions."""

import pytest
from datetime import date, datetime, timedelta
from collections import Counter
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from handlers_v2.pipeline import (
    _build_pipeline_text,
    handle_pipeline,
    handle_followup,
    handle_today,
    handle_search,
    handle_rag_search,
    handle_me,
    handle_overview,
    handle_sop,
    PIPELINE_COMMANDS,
    PIPELINE_CALLBACKS,
    PIPELINE_CONVERSATIONS,
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
        return_value=role
        in (StaffRole.MAINTENANCE, StaffRole.MANAGER, StaffRole.ADMIN, StaffRole.LEADER)
    )
    s.is_admin = MagicMock(return_value=role == StaffRole.ADMIN)
    return s


def _make_client(
    client_id=99,
    phone="1234567890",
    status=ClientStatus.NEW,
    frontdesk_id=10,
    source="飞机筛选",
    status_note=None,
    updated_at=None,
):
    c = MagicMock()
    c.id = client_id
    c.phone = phone
    c.status = status
    c.frontdesk_id = frontdesk_id
    c.source = source
    c.status_note = status_note
    c.updated_at = updated_at or datetime.now()
    c.status_emoji = MagicMock(return_value="🆕")
    return c


def _make_stat(
    new_leads=5,
    contacted=4,
    replied=3,
    registered=2,
    training=1,
    withdrew=1,
    new_orders=1,
    reply_rate=75.0,
    conversion_rate=50.0,
    total_deposit=100.0,
):
    s = MagicMock()
    s.new_leads = new_leads
    s.contacted = contacted
    s.replied = replied
    s.registered = registered
    s.training = training
    s.withdrew = withdrew
    s.new_orders = new_orders
    s.reply_rate = reply_rate
    s.conversion_rate = conversion_rate
    s.total_deposit = total_deposit
    return s


def _task(
    chat_id=9000, user_id=1001, args="", chat_type="private", group_team=None, **kwargs
):
    d = {
        "chat_id": chat_id,
        "user_id": user_id,
        "args": args,
        "chat_type": chat_type,
    }
    if group_team:
        d["group_team"] = group_team
    d.update(kwargs)
    return d


# ── _build_pipeline_text ──────────────────────────────────────────────────────


class TestBuildPipelineText:
    """Test the pipeline text builder helper."""

    def test_basic_output_with_counts(self):
        counts = {
            "new": 5,
            "contacted": 3,
            "replied": 2,
            "registered": 1,
            "training": 1,
            "withdrew": 0,
            "ordered": 0,
        }
        text = _build_pipeline_text(counts, "Alice", "zh")
        assert "Alice" in text
        assert "New (5)" in text
        assert "Contacted (3)" in text
        assert "12" in text  # total

    def test_empty_counts(self):
        text = _build_pipeline_text({}, "Alice", "zh")
        assert "0" in text  # all stages 0

    def test_other_statuses_included_when_present(self):
        counts = {"ghosted": 2, "blocked": 1, "scammed": 0, "dead": 3}
        text = _build_pipeline_text(counts, "Alice", "zh")
        assert "Other (6)" in text

    def test_other_statuses_omitted_when_zero(self):
        counts = {"new": 1}
        text = _build_pipeline_text(counts, "Alice", "zh")
        assert "Other" not in text

    def test_stages_in_correct_order(self):
        counts = {"new": 1, "ordered": 1}
        text = _build_pipeline_text(counts, "Alice", "zh")
        new_pos = text.find("New")
        ordered_pos = text.find("Ordered")
        assert new_pos < ordered_pos


# ── Registries ────────────────────────────────────────────────────────────────


class TestPipelineRegistries:
    """Verify handler registries are complete and consistent."""

    def test_pipeline_commands_contains_expected_entries(self):
        expected = {
            "me",
            "overview",
            "pipeline",
            "followup",
            "today",
            "search",
            "rag",
            "sop",
        }
        assert set(PIPELINE_COMMANDS.keys()) == expected

    def test_all_handlers_are_callable(self):
        for name, handler in PIPELINE_COMMANDS.items():
            assert callable(handler), f"{name} handler is not callable"

    def test_callbacks_registry_empty(self):
        assert PIPELINE_CALLBACKS == {}

    def test_conversations_registry_empty(self):
        assert PIPELINE_CONVERSATIONS == {}


# ── handle_pipeline ───────────────────────────────────────────────────────────


class TestHandlePipeline:
    """/pipeline — funnel view."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_pipeline_counts = AsyncMock(return_value={"new": 3, "contacted": 2})
        self.get_stale_clients = AsyncMock(return_value=[])
        self.get_followup_due = AsyncMock(return_value=[])

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
            patch("handlers_v2.pipeline.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_pipeline_counts = self.get_pipeline_counts
            db.get_stale_clients = self.get_stale_clients
            db.get_followup_due = self.get_followup_due
            self.db = db
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_pipeline(_task())
        self.send.assert_awaited_once()
        assert self.get_pipeline_counts.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_newbie(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.NEWBIE)
        await handle_pipeline(_task())
        self.send.assert_awaited_once()
        assert self.get_pipeline_counts.await_count == 0

    @pytest.mark.asyncio
    async def test_personal_pipeline_in_dm(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_pipeline(_task(chat_type="private"))
        self.get_pipeline_counts.assert_awaited_once_with(staff.id)
        self.send.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        assert "Alice" in sent_text

    @pytest.mark.asyncio
    async def test_stale_warning_shown(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.get_stale_clients.return_value = [_make_client(), _make_client()]
        await handle_pipeline(_task())
        sent_text = self.send.call_args[0][1]
        assert "2" in sent_text  # stale count

    @pytest.mark.asyncio
    async def test_followup_due_shown(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.get_followup_due.return_value = [_make_client()]
        await handle_pipeline(_task())
        sent_text = self.send.call_args[0][1]
        assert "1" in sent_text

    @pytest.mark.asyncio
    async def test_team_pipeline_in_group(self):
        staff = _make_staff(team="team_a")
        self.get_staff_mock.return_value = staff
        # get_team_staff_ids is imported inside handle_pipeline from handlers_v2
        with patch("handlers_v2.get_team_staff_ids", new_callable=AsyncMock) as gts:
            gts.return_value = [10, 11]
            await handle_pipeline(_task(chat_type="supergroup", group_team="team_a"))
        # Should aggregate counts across team members
        assert self.get_pipeline_counts.await_count == 2

    @pytest.mark.asyncio
    async def test_viewer_can_see_pipeline(self):
        staff = _make_staff(role=StaffRole.VIEWER)
        self.get_staff_mock.return_value = staff
        await handle_pipeline(_task())
        self.get_pipeline_counts.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_footer_contains_help_commands(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_pipeline(_task())
        sent_text = self.send.call_args[0][1]
        assert "/followup" in sent_text
        assert "/today" in sent_text
        assert "/add" in sent_text


# ── handle_followup ───────────────────────────────────────────────────────────


class TestHandleFollowup:
    """/followup — list clients needing attention."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_stale_clients = AsyncMock(return_value=[])
        self.get_followup_due = AsyncMock(return_value=[])

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
            patch("handlers_v2.pipeline.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_stale_clients = self.get_stale_clients
            db.get_followup_due = self.get_followup_due
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_followup(_task())
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_permission_denied_for_newbie(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.NEWBIE)
        await handle_followup(_task())
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_followups_sends_empty_message(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_followup(_task())
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_followup_clients_listed(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(phone="555", status_note="needs call")
        self.get_stale_clients.return_value = [client]
        await handle_followup(_task())
        sent_text = self.send.call_args[0][1]
        assert "555" in sent_text

    @pytest.mark.asyncio
    async def test_status_note_shown(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(phone="555", status_note="needs call")
        self.get_stale_clients.return_value = [client]
        await handle_followup(_task())
        sent_text = self.send.call_args[0][1]
        assert "needs call" in sent_text

    @pytest.mark.asyncio
    async def test_deduplication_of_stale_and_followup(self):
        """Clients in both stale and followup lists appear once."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(client_id=1, phone="555")
        self.get_stale_clients.return_value = [client]
        self.get_followup_due.return_value = [client]
        await handle_followup(_task())
        sent_text = self.send.call_args[0][1]
        # Phone should appear once (deduplicated by id)
        assert sent_text.count("555") == 1

    @pytest.mark.asyncio
    async def test_max_20_clients_shown(self):
        """If more than 20 clients need follow-up, show 20 + 'more' message."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        clients = [_make_client(client_id=i, phone=str(1000 + i)) for i in range(25)]
        self.get_stale_clients.return_value = clients
        await handle_followup(_task())
        sent_text = self.send.call_args[0][1]
        # Should indicate there are more clients
        assert "5" in sent_text  # 25-20 = 5 more

    @pytest.mark.asyncio
    async def test_hours_ago_display(self):
        """Hours since last update should be shown."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(
            phone="555",
            updated_at=datetime.now() - timedelta(hours=48),
        )
        self.get_stale_clients.return_value = [client]
        await handle_followup(_task())
        sent_text = self.send.call_args[0][1]
        assert "h ago" in sent_text


# ── handle_today ──────────────────────────────────────────────────────────────


class TestHandleToday:
    """/today — daily stats."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.calculate_daily_stats = AsyncMock(return_value=_make_stat())
        self.upsert_daily_stats = AsyncMock()
        self.get_daily_stats = AsyncMock(return_value=None)

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
            patch("handlers_v2.pipeline.database_v2") as db,
        ):
            th.send_message = self.send
            db.calculate_daily_stats = self.calculate_daily_stats
            db.upsert_daily_stats = self.upsert_daily_stats
            db.get_daily_stats = self.get_daily_stats
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_today(_task())
        self.send.assert_awaited_once()
        assert self.calculate_daily_stats.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_newbie(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.NEWBIE)
        await handle_today(_task())
        self.send.assert_awaited_once()
        assert self.calculate_daily_stats.await_count == 0

    @pytest.mark.asyncio
    async def test_today_stats_displayed(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_today(_task())
        self.calculate_daily_stats.assert_awaited_once_with(staff.id)
        self.upsert_daily_stats.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        assert "5" in sent_text  # new_leads
        assert "75" in sent_text  # reply_rate

    @pytest.mark.asyncio
    async def test_deposit_shown_when_nonzero(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        stat = _make_stat(total_deposit=250.50)
        self.calculate_daily_stats.return_value = stat
        await handle_today(_task())
        sent_text = self.send.call_args[0][1]
        assert "250.50" in sent_text

    @pytest.mark.asyncio
    async def test_deposit_hidden_when_zero(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        stat = _make_stat(total_deposit=0)
        self.calculate_daily_stats.return_value = stat
        await handle_today(_task())
        sent_text = self.send.call_args[0][1]
        assert "$0" not in sent_text

    @pytest.mark.asyncio
    async def test_yesterday_comparison_shown(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        yesterday_stat = _make_stat(new_leads=3, registered=1, new_orders=0)
        self.get_daily_stats.return_value = yesterday_stat
        await handle_today(_task())
        sent_text = self.send.call_args[0][1]
        # Should show delta: +2 new_leads (5-3), +1 registered (2-1), +1 orders (1-0)
        assert "+2" in sent_text or "+1" in sent_text

    @pytest.mark.asyncio
    async def test_no_yesterday_comparison_when_no_data(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.get_daily_stats.return_value = None
        await handle_today(_task())
        # Should still work — no crash
        self.send.assert_awaited_once()


# ── handle_search ─────────────────────────────────────────────────────────────


class TestHandleSearch:
    """/search <query> — keyword search."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.search_clients = AsyncMock(return_value=[])

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
            patch("handlers_v2.pipeline.database_v2") as db,
        ):
            th.send_message = self.send
            db.search_clients = self.search_clients
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_search(_task(args="test"))
        self.send.assert_awaited_once()
        assert self.search_clients.await_count == 0

    @pytest.mark.asyncio
    async def test_permission_denied_for_newbie(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.NEWBIE)
        await handle_search(_task(args="test"))
        self.send.assert_awaited_once()
        assert self.search_clients.await_count == 0

    @pytest.mark.asyncio
    async def test_empty_query_sends_usage(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_search(_task(args=""))
        self.send.assert_awaited_once()
        assert self.search_clients.await_count == 0

    @pytest.mark.asyncio
    async def test_no_results_sends_message(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.search_clients.return_value = []
        await handle_search(_task(args="xyz"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_results_shown_with_status(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(
            phone="999",
            status=ClientStatus.CONTACTED,
            source="飞机",
            status_note="good lead",
        )
        self.search_clients.return_value = [client]
        await handle_search(_task(args="999"))
        sent_text = self.send.call_args[0][1]
        assert "999" in sent_text

    @pytest.mark.asyncio
    async def test_max_10_results_shown(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        clients = [_make_client(client_id=i, phone=str(1000 + i)) for i in range(15)]
        self.search_clients.return_value = clients
        await handle_search(_task(args="test"))
        sent_text = self.send.call_args[0][1]
        assert "5" in sent_text  # 15-10 = 5 more

    @pytest.mark.asyncio
    async def test_status_note_truncated(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(status_note="x" * 100)
        self.search_clients.return_value = [client]
        await handle_search(_task(args="test"))
        sent_text = self.send.call_args[0][1]
        assert len(sent_text) > 0


# ── handle_rag_search ─────────────────────────────────────────────────────────


class TestHandleRagSearch:
    """/rag <query> — semantic search."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
        ):
            th.send_message = self.send
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_rag_search(_task(args="test"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_permission_denied_for_newbie(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.NEWBIE)
        await handle_rag_search(_task(args="test"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_query_sends_usage(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_rag_search(_task(args=""))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rag_unavailable_sends_error(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        with patch(
            "engines.rag_engine.search_similar", side_effect=Exception("no ollama")
        ):
            await handle_rag_search(_task(args="test"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_results(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        with patch(
            "engines.rag_engine.search_similar", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []
            await handle_rag_search(_task(args="test"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_results_shown_with_score(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        results = [
            {
                "source_type": "note",
                "source_id": 1,
                "score": 0.85,
                "text_chunk": "Client mentioned interest in training",
            },
        ]
        with patch(
            "engines.rag_engine.search_similar", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = results
            await handle_rag_search(_task(args="training"))
        sent_text = self.send.call_args[0][1]
        assert "85%" in sent_text
        assert "training" in sent_text.lower()


# ── handle_me ─────────────────────────────────────────────────────────────────


class TestHandleMe:
    """/me — all-in-one personal dashboard."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.get_pipeline_counts = AsyncMock(return_value={"new": 3, "contacted": 2})
        self.calculate_daily_stats = AsyncMock(return_value=_make_stat())
        self.upsert_daily_stats = AsyncMock()
        self.get_followup_due = AsyncMock(return_value=[])
        self.get_stale_clients = AsyncMock(return_value=[])

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
            patch("handlers_v2.pipeline.database_v2") as db,
        ):
            th.send_message = self.send
            db.get_pipeline_counts = self.get_pipeline_counts
            db.calculate_daily_stats = self.calculate_daily_stats
            db.upsert_daily_stats = self.upsert_daily_stats
            db.get_followup_due = self.get_followup_due
            db.get_stale_clients = self.get_stale_clients
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_me(_task())
        self.send.assert_awaited_once()
        assert self.get_pipeline_counts.await_count == 0

    @pytest.mark.asyncio
    async def test_viewer_can_use_me(self):
        staff = _make_staff(role=StaffRole.VIEWER)
        self.get_staff_mock.return_value = staff
        await handle_me(_task())
        self.get_pipeline_counts.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_me_shows_pipeline_section(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "PIPELINE" in sent_text

    @pytest.mark.asyncio
    async def test_me_shows_today_section(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "TODAY" in sent_text

    @pytest.mark.asyncio
    async def test_me_shows_staff_name(self):
        staff = _make_staff(display_name="TestUser")
        self.get_staff_mock.return_value = staff
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "TestUser" in sent_text

    @pytest.mark.asyncio
    async def test_me_shows_team(self):
        staff = _make_staff(team="alpha")
        self.get_staff_mock.return_value = staff
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "alpha" in sent_text

    @pytest.mark.asyncio
    async def test_me_shows_all_clear_when_no_urgent(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        self.get_followup_due.return_value = []
        self.get_stale_clients.return_value = []
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "ALL CLEAR" in sent_text

    @pytest.mark.asyncio
    async def test_me_shows_attention_section_with_stale(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        client = _make_client(
            phone="999", updated_at=datetime.now() - timedelta(hours=72)
        )
        self.get_stale_clients.return_value = [client]
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "NEEDS ATTENTION" in sent_text
        assert "999" in sent_text

    @pytest.mark.asyncio
    async def test_me_caps_urgent_at_8(self):
        """Only first 8 urgent clients shown inline."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        clients = [_make_client(client_id=i, phone=str(1000 + i)) for i in range(12)]
        self.get_stale_clients.return_value = clients
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "+4 more" in sent_text  # 12 - 8

    @pytest.mark.asyncio
    async def test_me_deposit_shown_when_positive(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        stat = _make_stat(total_deposit=500.0)
        self.calculate_daily_stats.return_value = stat
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "500.00" in sent_text

    @pytest.mark.asyncio
    async def test_me_no_team_hides_team_line(self):
        staff = _make_staff(team=None)
        self.get_staff_mock.return_value = staff
        await handle_me(_task())
        sent_text = self.send.call_args[0][1]
        assert "Team:" not in sent_text


# ── handle_overview ───────────────────────────────────────────────────────────


class TestHandleOverview:
    """/overview — manager-only team dashboard."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()
        self.recalculate = AsyncMock()
        self.get_all_staff = AsyncMock(return_value=[])
        self.get_daily_stats = AsyncMock(return_value=None)
        self.get_stale_clients = AsyncMock(return_value=[])
        self.get_staff_by_id = AsyncMock(return_value=None)

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
            patch("handlers_v2.pipeline.database_v2") as db,
        ):
            th.send_message = self.send
            db.recalculate_all_today_stats = self.recalculate
            db.get_all_staff = self.get_all_staff
            db.get_daily_stats = self.get_daily_stats
            db.get_stale_clients = self.get_stale_clients
            db.get_staff_by_id = self.get_staff_by_id
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_overview(_task())
        self.send.assert_awaited_once()
        assert self.get_all_staff.await_count == 0

    @pytest.mark.asyncio
    async def test_frontdesk_denied(self):
        staff = _make_staff(role=StaffRole.FRONTDESK)
        staff.is_manager_or_above.return_value = False
        self.get_staff_mock.return_value = staff
        await handle_overview(_task())
        self.send.assert_awaited_once()
        assert self.get_all_staff.await_count == 0

    @pytest.mark.asyncio
    async def test_viewer_denied(self):
        staff = _make_staff(role=StaffRole.VIEWER)
        staff.is_manager_or_above.return_value = False
        self.get_staff_mock.return_value = staff
        await handle_overview(_task())
        self.send.assert_awaited_once()
        assert self.get_all_staff.await_count == 0

    @pytest.mark.asyncio
    async def test_manager_can_view(self):
        staff = _make_staff(role=StaffRole.MANAGER)
        self.get_staff_mock.return_value = staff
        await handle_overview(_task())
        self.recalculate.assert_awaited_once()
        self.get_all_staff.assert_awaited_once()
        self.send.assert_awaited_once()
        sent_text = self.send.call_args[0][1]
        assert "TEAM OVERVIEW" in sent_text

    @pytest.mark.asyncio
    async def test_admin_can_view(self):
        staff = _make_staff(role=StaffRole.ADMIN)
        self.get_staff_mock.return_value = staff
        await handle_overview(_task())
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_overview_with_teams(self):
        staff = _make_staff(role=StaffRole.MANAGER)
        self.get_staff_mock.return_value = staff

        # Create mock frontdesk staff with teams
        fd1 = MagicMock()
        fd1.id = 1
        fd1.display_name = "Alice"
        fd1.role = MagicMock()
        fd1.role.value = "frontdesk"
        fd1.team = "team_a"
        fd1.maintenance_id = None

        fd2 = MagicMock()
        fd2.id = 2
        fd2.display_name = "Bob"
        fd2.role = MagicMock()
        fd2.role.value = "frontdesk"
        fd2.team = "team_a"
        fd2.maintenance_id = None

        self.get_all_staff.return_value = [fd1, fd2]
        self.get_daily_stats.return_value = _make_stat(
            new_leads=3, registered=1, new_orders=1
        )
        self.get_stale_clients.return_value = []

        await handle_overview(_task())
        sent_text = self.send.call_args[0][1]
        assert "team_a" in sent_text
        assert "Alice" in sent_text
        assert "Bob" in sent_text
        assert "GRAND TOTAL" in sent_text

    @pytest.mark.asyncio
    async def test_overview_no_stale_shows_clear(self):
        staff = _make_staff(role=StaffRole.MANAGER)
        self.get_staff_mock.return_value = staff
        self.get_all_staff.return_value = []
        await handle_overview(_task())
        sent_text = self.send.call_args[0][1]
        assert "No stale clients" in sent_text

    @pytest.mark.asyncio
    async def test_overview_with_stale_shows_warning(self):
        staff = _make_staff(role=StaffRole.MANAGER)
        self.get_staff_mock.return_value = staff

        fd = MagicMock()
        fd.id = 1
        fd.display_name = "Alice"
        fd.role = MagicMock()
        fd.role.value = "frontdesk"
        fd.team = "team_a"
        fd.maintenance_id = None

        self.get_all_staff.return_value = [fd]
        self.get_daily_stats.return_value = _make_stat()
        self.get_stale_clients.return_value = [_make_client(), _make_client()]

        await handle_overview(_task())
        sent_text = self.send.call_args[0][1]
        assert "stale" in sent_text.lower()


# ── handle_sop ────────────────────────────────────────────────────────────────


class TestHandleSop:
    """/sop <topic> — SOP search."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        self.send = AsyncMock()
        self.get_staff_mock = AsyncMock()

        with (
            patch("handlers_v2.pipeline.telegram_handler") as th,
            patch("handlers_v2.pipeline._get_staff", self.get_staff_mock),
        ):
            th.send_message = self.send
            yield

    @pytest.mark.asyncio
    async def test_unregistered_staff(self):
        self.get_staff_mock.return_value = None
        await handle_sop(_task(args="registration"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_permission_denied_for_viewer(self):
        self.get_staff_mock.return_value = _make_staff(role=StaffRole.VIEWER)
        await handle_sop(_task(args="registration"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_obsidian_content_found(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        with patch("engines.obsidian_brain.obsidian_brain") as ob:
            ob.get_sop = AsyncMock(return_value="Step 1: Register the client...")
            await handle_sop(_task(args="registration"))
        sent_text = self.send.call_args[0][1]
        assert "Step 1" in sent_text

    @pytest.mark.asyncio
    async def test_obsidian_failure_fallback_to_rag(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        with (
            patch("engines.obsidian_brain.obsidian_brain") as ob,
            patch("engines.rag_engine.search_similar", new_callable=AsyncMock) as rag,
        ):
            ob.get_sop = AsyncMock(side_effect=Exception("file not found"))
            rag.return_value = [
                {
                    "source_type": "obsidian_sop",
                    "text_chunk": "RAG SOP content",
                    "score": 0.9,
                },
            ]
            await handle_sop(_task(args="registration"))
        sent_text = self.send.call_args[0][1]
        assert "RAG SOP content" in sent_text

    @pytest.mark.asyncio
    async def test_no_content_found_anywhere(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        with patch("engines.obsidian_brain.obsidian_brain") as ob:
            ob.get_sop = AsyncMock(return_value="")
            with patch(
                "engines.rag_engine.search_similar", new_callable=AsyncMock
            ) as rag:
                rag.return_value = []
                await handle_sop(_task(args="unknown_topic"))
        self.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_content_truncated_at_2000_chars(self):
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        long_content = "x" * 5000
        with patch("engines.obsidian_brain.obsidian_brain") as ob:
            ob.get_sop = AsyncMock(return_value=long_content)
            await handle_sop(_task(args="long topic"))
        sent_text = self.send.call_args[0][1]
        # Total sent should be header + content[:2000]
        # The content portion should not exceed 2000 chars
        assert len(sent_text) < 2200  # header + 2000 content

    @pytest.mark.asyncio
    async def test_obsidian_empty_but_rag_non_sop_ignored(self):
        """RAG results that aren't obsidian/policy type should not show."""
        staff = _make_staff()
        self.get_staff_mock.return_value = staff
        with (
            patch("engines.obsidian_brain.obsidian_brain") as ob,
            patch("engines.rag_engine.search_similar", new_callable=AsyncMock) as rag,
        ):
            ob.get_sop = AsyncMock(return_value="")
            rag.return_value = [
                {
                    "source_type": "client_note",
                    "text_chunk": "irrelevant",
                    "score": 0.9,
                },
            ]
            await handle_sop(_task(args="topic"))
        # Should say not found since client_note is not an sop/policy source
        self.send.assert_awaited_once()

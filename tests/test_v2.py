"""V2 test suite — DB operations, status transitions, pipeline queries, stats, RAG, migration."""
import asyncio
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Import after setting path
from database_v2 import DatabaseV2
from models_v2 import (
    Client, ClientNote, ClientStatus, DailyStat, Deposit, NoteType,
    PeriodType, Reminder, Staff, StaffRole, TeamTarget,
)


@pytest_asyncio.fixture
async def db(tmp_path):
    """File-based temp DB, fresh per test (aiosqlite :memory: doesn't persist across connections)."""
    db_file = str(tmp_path / 'test_v2.db')
    d = DatabaseV2(db_file)
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def staff_row(db):
    """Create a test staff member."""
    s = Staff(
        tg_user_id=1001,
        tg_chat_id=2001,
        display_name='阿YIM',
        role=StaffRole.FRONTDESK,
        language='zh',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager_row(db):
    """Create a test manager."""
    s = Staff(
        tg_user_id=1002,
        tg_chat_id=2002,
        display_name='Manager',
        role=StaffRole.MANAGER,
        language='zh',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client_row(db, staff_row):
    """Create a test client."""
    c = Client(
        frontdesk_id=staff_row.id,
        phone='1234567890',
        source='飞机筛选',
    )
    c.id = await db.create_client(c)
    return c


# ─── Staff tests ───────────────────────────────────────────────────────────────

class TestStaff:
    @pytest.mark.asyncio
    async def test_create_and_get_staff(self, db):
        s = Staff(tg_user_id=9001, tg_chat_id=9002, display_name='Test')
        staff_id = await db.create_staff(s)
        assert staff_id > 0

        found = await db.get_staff_by_tg_id(9001)
        assert found is not None
        assert found.display_name == 'Test'
        assert found.role == StaffRole.FRONTDESK

    @pytest.mark.asyncio
    async def test_get_staff_by_id(self, db, staff_row):
        found = await db.get_staff_by_id(staff_row.id)
        assert found is not None
        assert found.display_name == '阿YIM'

    @pytest.mark.asyncio
    async def test_update_staff(self, db, staff_row):
        staff_row.display_name = '阿YIM Updated'
        staff_row.role = StaffRole.MANAGER
        await db.update_staff(staff_row)
        found = await db.get_staff_by_id(staff_row.id)
        assert found.display_name == '阿YIM Updated'
        assert found.role == StaffRole.MANAGER

    @pytest.mark.asyncio
    async def test_upsert_staff(self, db, staff_row):
        # Second upsert should update, not create duplicate
        staff_row.display_name = '阿YIM v2'
        new_id = await db.upsert_staff(staff_row)
        assert new_id == staff_row.id
        found = await db.get_staff_by_id(staff_row.id)
        assert found.display_name == '阿YIM v2'

    @pytest.mark.asyncio
    async def test_get_all_staff(self, db, staff_row, manager_row):
        all_s = await db.get_all_staff()
        # seed_team_structure adds 2 maintenance staff (阿俊 + 何军) on every init
        names = {s.display_name for s in all_s}
        assert staff_row.display_name in names
        assert manager_row.display_name in names
        assert len(all_s) >= 2

    @pytest.mark.asyncio
    async def test_staff_role_checks(self):
        fd = Staff(tg_user_id=1, tg_chat_id=1, display_name='FD', role=StaffRole.FRONTDESK)
        maint = Staff(tg_user_id=2, tg_chat_id=2, display_name='MAINT', role=StaffRole.MAINTENANCE)
        mgr = Staff(tg_user_id=3, tg_chat_id=3, display_name='MGR', role=StaffRole.MANAGER)
        adm = Staff(tg_user_id=4, tg_chat_id=4, display_name='ADM', role=StaffRole.ADMIN)
        assert not fd.is_manager_or_above()
        assert maint.is_manager_or_above()
        assert mgr.is_manager_or_above()
        assert adm.is_manager_or_above()
        assert adm.is_admin()
        assert not mgr.is_admin()


# ─── Client tests ──────────────────────────────────────────────────────────────

class TestClient:
    @pytest.mark.asyncio
    async def test_create_and_get_client(self, db, staff_row):
        c = Client(frontdesk_id=staff_row.id, phone='555123', source='UK表单粉')
        cid = await db.create_client(c)
        assert cid > 0

        found = await db.get_client_by_phone('555123', staff_row.id)
        assert found is not None
        assert found.status == ClientStatus.NEW
        assert found.source == 'UK表单粉'

    @pytest.mark.asyncio
    async def test_get_client_by_id(self, db, client_row):
        found = await db.get_client_by_id(client_row.id)
        assert found is not None
        assert found.phone == '1234567890'

    @pytest.mark.asyncio
    async def test_update_status_sets_timestamp(self, db, client_row, staff_row):
        ok = await db.update_client_status(
            client_row.id, ClientStatus.CONTACTED, staff_row.id, 'first contact')
        assert ok is True

        updated = await db.get_client_by_id(client_row.id)
        assert updated.status == ClientStatus.CONTACTED
        assert updated.contacted_at is not None

    @pytest.mark.asyncio
    async def test_full_pipeline_transition(self, db, client_row, staff_row):
        """Walk a client through the full pipeline."""
        pipeline = [
            ClientStatus.CONTACTED,
            ClientStatus.REPLIED,
            ClientStatus.REGISTERED,
            ClientStatus.TRAINING,
            ClientStatus.WITHDREW,
        ]
        for status in pipeline:
            ok = await db.update_client_status(client_row.id, status, staff_row.id)
            assert ok is True
            c = await db.get_client_by_id(client_row.id)
            assert c.status == status

    @pytest.mark.asyncio
    async def test_search_clients(self, db, client_row, staff_row):
        results = await db.search_clients(staff_row.id, '123456')
        assert len(results) >= 1
        assert results[0].phone == '1234567890'

    @pytest.mark.asyncio
    async def test_get_clients_by_status(self, db, client_row, staff_row):
        results = await db.get_clients_by_status(staff_row.id, ClientStatus.NEW)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_client_not_found_returns_none(self, db, staff_row):
        found = await db.get_client_by_phone('nonexistent', staff_row.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_stale_client_detection(self, db, staff_row):
        """Client with old updated_at should appear in stale list."""
        c = Client(frontdesk_id=staff_row.id, phone='stale999', source='test')
        cid = await db.create_client(c)
        # Manually backdate updated_at
        async with db.get_connection() as conn:
            old_time = (datetime.now() - timedelta(hours=100)).isoformat()
            await conn.execute(
                'UPDATE clients SET updated_at=? WHERE id=?', (old_time, cid))
            await conn.commit()
        stale = await db.get_stale_clients(staff_row.id, hours=72)
        assert any(c.id == cid for c in stale)

    @pytest.mark.asyncio
    async def test_status_emoji(self):
        c = Client(frontdesk_id=1, phone='x', source='y', status=ClientStatus.REGISTERED)
        assert c.status_emoji() == '✅'
        c.status = ClientStatus.DEAD
        assert c.status_emoji() == '💀'


# ─── ClientNote tests ──────────────────────────────────────────────────────────

class TestClientNotes:
    @pytest.mark.asyncio
    async def test_add_and_get_notes(self, db, client_row, staff_row):
        note = ClientNote(
            client_id=client_row.id,
            staff_id=staff_row.id,
            note_type=NoteType.NOTE,
            content='Test note content',
        )
        note_id = await db.add_client_note(note)
        assert note_id > 0

        notes = await db.get_client_notes(client_row.id)
        assert len(notes) >= 1
        assert notes[0].content == 'Test note content'

    @pytest.mark.asyncio
    async def test_status_change_creates_note(self, db, client_row, staff_row):
        await db.update_client_status(
            client_row.id, ClientStatus.CONTACTED, staff_row.id, 'first touch')
        notes = await db.get_client_notes(client_row.id)
        status_notes = [n for n in notes if n.note_type == NoteType.STATUS_CHANGE]
        assert len(status_notes) >= 1
        assert status_notes[0].new_status == 'contacted'


# ─── DailyStat tests ───────────────────────────────────────────────────────────

class TestDailyStats:
    @pytest.mark.asyncio
    async def test_calculate_daily_stats(self, db, staff_row, client_row):
        """Stats should reflect today's activity (UTC, matching SQLite CURRENT_TIMESTAMP)."""
        await db.update_client_status(
            client_row.id, ClientStatus.CONTACTED, staff_row.id)
        # Pass UTC date explicitly — SQLite CURRENT_TIMESTAMP is UTC
        utc_today = datetime.now(timezone.utc).date()
        stat = await db.calculate_daily_stats(staff_row.id, stat_date=utc_today)
        assert stat.contacted >= 1

    @pytest.mark.asyncio
    async def test_upsert_daily_stats(self, db, staff_row):
        stat = DailyStat(
            staff_id=staff_row.id,
            stat_date=date.today(),
            new_leads=10,
            replied=5,
            registered=3,
        )
        stat.calculate_rates()
        await db.upsert_daily_stats(stat)

        found = await db.get_daily_stats(staff_row.id)
        assert found is not None
        assert found.new_leads == 10
        assert found.registered == 3

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self, db, staff_row):
        """Second upsert updates, not duplicates."""
        stat = DailyStat(staff_id=staff_row.id, stat_date=date.today(), new_leads=5)
        await db.upsert_daily_stats(stat)
        stat.new_leads = 15
        await db.upsert_daily_stats(stat)
        found = await db.get_daily_stats(staff_row.id)
        assert found.new_leads == 15

    @pytest.mark.asyncio
    async def test_reply_rate_calculation(self):
        stat = DailyStat(staff_id=1, stat_date=date.today(), new_leads=100, contacted=80, replied=40)
        stat.calculate_rates()
        assert stat.reply_rate == 50.0  # 40/80 contacted

    @pytest.mark.asyncio
    async def test_conversion_rate_calculation(self):
        stat = DailyStat(staff_id=1, stat_date=date.today(), new_leads=100, registered=50, new_orders=5)
        stat.calculate_rates()
        assert stat.conversion_rate == 10.0  # 5/50 registered

    @pytest.mark.asyncio
    async def test_zero_leads_no_div_zero(self):
        stat = DailyStat(staff_id=1, stat_date=date.today(), new_leads=0)
        stat.calculate_rates()
        assert stat.reply_rate == 0.0
        assert stat.conversion_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_team_daily_stats(self, db, staff_row, manager_row):
        for sid in [staff_row.id, manager_row.id]:
            stat = DailyStat(staff_id=sid, stat_date=date.today(), new_leads=5)
            await db.upsert_daily_stats(stat)
        team = await db.get_team_daily_stats()
        assert len(team) == 2


# ─── Deposit tests ─────────────────────────────────────────────────────────────

class TestDeposits:
    @pytest.mark.asyncio
    async def test_create_deposit_updates_client(self, db, client_row, staff_row):
        d = Deposit(
            client_id=client_row.id,
            frontdesk_id=staff_row.id,
            amount=500.0,
            deposit_date=date.today(),
        )
        dep_id = await db.create_deposit(d)
        assert dep_id > 0

        c = await db.get_client_by_id(client_row.id)
        assert c.total_deposited == 500.0

    @pytest.mark.asyncio
    async def test_get_deposits_by_client(self, db, client_row, staff_row):
        d = Deposit(
            client_id=client_row.id,
            frontdesk_id=staff_row.id,
            amount=100.0,
            deposit_date=date.today(),
            knife_number=1,
        )
        await db.create_deposit(d)
        deps = await db.get_deposits_by_client(client_row.id)
        assert len(deps) >= 1
        assert deps[0].amount == 100.0


# ─── Reminder tests ────────────────────────────────────────────────────────────

class TestReminders:
    @pytest.mark.asyncio
    async def test_create_and_get_reminder(self, db, staff_row):
        remind_at = datetime.now() - timedelta(minutes=1)  # already due
        r = Reminder(
            staff_id=staff_row.id,
            remind_at=remind_at,
            message='Test reminder',
        )
        rid = await db.create_reminder(r)
        assert rid > 0

        pending = await db.get_pending_reminders_v2()
        assert any(r.id == rid for r in pending)

    @pytest.mark.asyncio
    async def test_mark_reminder_sent(self, db, staff_row):
        remind_at = datetime.now() - timedelta(minutes=1)
        r = Reminder(staff_id=staff_row.id, remind_at=remind_at, message='Done')
        rid = await db.create_reminder(r)
        await db.mark_reminder_sent(rid)

        pending = await db.get_pending_reminders_v2()
        assert not any(r.id == rid for r in pending)

    @pytest.mark.asyncio
    async def test_future_reminder_not_in_pending(self, db, staff_row):
        # Use a far-future date to avoid any timezone edge cases
        remind_at = datetime(2099, 12, 31, 23, 59, 59)
        r = Reminder(staff_id=staff_row.id, remind_at=remind_at, message='Future')
        rid = await db.create_reminder(r)

        # Only check reminders due before now
        pending = await db.get_pending_reminders_v2(before=datetime.now())
        assert not any(r.id == rid for r in pending)

    @pytest.mark.asyncio
    async def test_reminder_is_due(self):
        past = Reminder(staff_id=1, remind_at=datetime.now() - timedelta(hours=1), message='past')
        future = Reminder(staff_id=1, remind_at=datetime.now() + timedelta(hours=1), message='future')
        assert past.is_due()
        assert not future.is_due()


# ─── Pipeline query tests ─────────────────────────────────────────────────────

class TestPipelineQueries:
    @pytest.mark.asyncio
    async def test_get_pipeline_counts(self, db, staff_row):
        for phone in ['111', '222', '333']:
            c = Client(frontdesk_id=staff_row.id, phone=phone, source='test')
            await db.create_client(c)
        counts = await db.get_pipeline_counts(staff_row.id)
        assert counts.get('new', 0) >= 3

    @pytest.mark.asyncio
    async def test_followup_due(self, db, staff_row, client_row):
        # Use a definitely-past date to avoid timezone ambiguity
        past = datetime(2020, 1, 1, 0, 0, 0)
        await db.set_next_followup(client_row.id, past)
        due = await db.get_followup_due(staff_row.id)
        assert any(c.id == client_row.id for c in due)

    @pytest.mark.asyncio
    async def test_search_by_source(self, db, staff_row, client_row):
        results = await db.search_clients(staff_row.id, '飞机')
        assert len(results) >= 1


# ─── Settings tests ────────────────────────────────────────────────────────────

class TestSettings:
    @pytest.mark.asyncio
    async def test_set_and_get_setting(self, db):
        await db.set_setting('test_key', 'test_value', 'a test setting')
        val = await db.get_setting('test_key')
        assert val == 'test_value'

    @pytest.mark.asyncio
    async def test_get_missing_setting_returns_default(self, db):
        val = await db.get_setting('missing_key', 'default')
        assert val == 'default'

    @pytest.mark.asyncio
    async def test_update_setting(self, db):
        await db.set_setting('key', 'v1')
        await db.set_setting('key', 'v2')
        val = await db.get_setting('key')
        assert val == 'v2'


# ─── Embedding tests ──────────────────────────────────────────────────────────

class TestEmbeddings:
    @pytest.mark.asyncio
    async def test_upsert_and_retrieve_embedding(self, db):
        vec = [0.1, 0.2, 0.3, 0.4]
        await db.upsert_embedding('client_notes', 1, 'test chunk', vec)
        all_emb = await db.get_all_embeddings()
        assert len(all_emb) == 1
        assert all_emb[0]['text_chunk'] == 'test chunk'
        assert len(all_emb[0]['embedding']) == 4

    @pytest.mark.asyncio
    async def test_upsert_replaces_old(self, db):
        await db.upsert_embedding('client_notes', 1, 'v1', [0.1])
        await db.upsert_embedding('client_notes', 1, 'v2', [0.2])
        all_emb = await db.get_all_embeddings()
        assert len(all_emb) == 1
        assert all_emb[0]['text_chunk'] == 'v2'


# ─── ClientStatus model tests ─────────────────────────────────────────────────

class TestClientStatusModel:
    def test_active_statuses(self):
        active = ClientStatus.active_statuses()
        assert ClientStatus.NEW in active
        assert ClientStatus.CONTACTED in active
        assert ClientStatus.REGISTERED in active
        assert ClientStatus.ORDERED not in active

    def test_terminal_statuses(self):
        terminal = ClientStatus.terminal_statuses()
        assert ClientStatus.DEAD in terminal
        assert ClientStatus.BLOCKED in terminal
        assert ClientStatus.SCAMMED in terminal
        assert ClientStatus.ORDERED not in terminal  # ordered clients are still active
        assert ClientStatus.NEW not in terminal

    def test_valid_transitions_from_new(self):
        transitions = ClientStatus.valid_transitions(ClientStatus.NEW)
        assert ClientStatus.CONTACTED in transitions
        assert ClientStatus.DEAD in transitions

    def test_pipeline_order(self):
        order = ClientStatus.pipeline_order()
        assert order[0] == ClientStatus.NEW
        assert order[-1] == ClientStatus.ORDERED

    def test_all_statuses_have_emoji(self):
        c = Client(frontdesk_id=1, phone='x', source='y')
        for s in ClientStatus:
            c.status = s
            emoji = c.status_emoji()
            assert emoji != '❓', f'Missing emoji for {s}'


# ─── RAG engine unit tests (mocked Ollama) ───────────────────────────────────

class TestRagEngine:
    @pytest.mark.asyncio
    async def test_cosine_similarity_identical(self):
        from engines.rag_engine import _cosine_similarity
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_cosine_similarity_orthogonal(self):
        from engines.rag_engine import _cosine_similarity
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_search_similar_empty_db(self, db):
        """Search with empty embeddings returns empty list."""
        with patch('engines.rag_engine.database_v2', db):
            with patch('engines.rag_engine.embed_text', new=AsyncMock(return_value=[0.1, 0.2])):
                from engines.rag_engine import search_similar
                results = await search_similar('test query', top_k=3)
                assert results == []

    @pytest.mark.asyncio
    async def test_search_similar_returns_ranked(self, db):
        """Search returns results ranked by similarity."""
        await db.upsert_embedding('client_notes', 1, 'hello world', [1.0, 0.0])
        await db.upsert_embedding('client_notes', 2, 'goodbye world', [0.0, 1.0])

        with patch('engines.rag_engine.database_v2', db):
            with patch('engines.rag_engine.embed_text', new=AsyncMock(return_value=[1.0, 0.0])):
                from engines.rag_engine import search_similar
                results = await search_similar('hello', top_k=2)
                assert len(results) == 2
                assert results[0]['source_id'] == 1  # most similar

    @pytest.mark.asyncio
    async def test_embed_text_failure_returns_empty(self, db):
        """If Ollama is down, search_similar returns []."""
        with patch('engines.rag_engine.database_v2', db):
            with patch('engines.rag_engine.embed_text', new=AsyncMock(side_effect=Exception('conn refused'))):
                from engines.rag_engine import search_similar
                results = await search_similar('test', top_k=3)
                assert results == []


# ─── Migration logic tests ────────────────────────────────────────────────────

class TestMigration:
    def test_map_status_registered(self):
        from migrate import _map_status
        assert _map_status('注册', '注册') == ClientStatus.REGISTERED
        assert _map_status('不注册', '注册') == ClientStatus.REGISTERED

    def test_map_status_not_registered(self):
        from migrate import _map_status
        assert _map_status('不注册', '不注册') == ClientStatus.CONTACTED
        assert _map_status('', '') == ClientStatus.NEW  # empty = never contacted

    @pytest.mark.asyncio
    async def test_migration_empty_old_db(self, tmp_path):
        """Migration with no old DB creates clean V2 DB (only seeded maintenance staff)."""
        new_db = str(tmp_path / 'new.db')
        db = DatabaseV2(new_db)
        await db.initialize()
        staff = await db.get_all_staff(active_only=False)
        # seed_team_structure creates 阿俊 and 何军 as maintenance staff
        names = {s.display_name for s in staff}
        assert '阿俊' in names
        assert '何军' in names
        maintenance_roles = [s for s in staff if s.role.value == 'maintenance']
        assert len(maintenance_roles) == 2


# ─── Feature 1: New roles + permission system ─────────────────────────────────

class TestNewRoles:
    def test_new_role_values(self):
        assert StaffRole.LEADER.value == 'leader'
        assert StaffRole.CUSTOMER_SERVICE.value == 'customer_service'
        assert StaffRole.NEWBIE.value == 'newbie'
        assert StaffRole.VIEWER.value == 'viewer'

    def test_viewer_is_read_only(self):
        viewer = Staff(tg_user_id=10, tg_chat_id=10, display_name='V', role=StaffRole.VIEWER)
        assert viewer.is_read_only()
        assert not viewer.can_modify_pipeline()
        assert not viewer.is_manager_or_above()

    def test_newbie_cannot_modify_pipeline(self):
        newbie = Staff(tg_user_id=11, tg_chat_id=11, display_name='N', role=StaffRole.NEWBIE)
        assert not newbie.can_modify_pipeline()
        assert not newbie.is_read_only()

    def test_cs_cannot_modify_pipeline(self):
        cs = Staff(tg_user_id=12, tg_chat_id=12, display_name='CS', role=StaffRole.CUSTOMER_SERVICE)
        assert not cs.can_modify_pipeline()

    def test_leader_is_manager_or_above(self):
        leader = Staff(tg_user_id=13, tg_chat_id=13, display_name='L', role=StaffRole.LEADER)
        assert leader.is_manager_or_above()
        assert leader.is_leader()
        assert not leader.is_admin()

    def test_frontdesk_can_modify_pipeline(self):
        fd = Staff(tg_user_id=14, tg_chat_id=14, display_name='FD', role=StaffRole.FRONTDESK)
        assert fd.can_modify_pipeline()


class TestCheckPermission:
    def _make(self, role: StaffRole) -> Staff:
        return Staff(tg_user_id=99, tg_chat_id=99, display_name='X', role=role)

    def test_admin_can_do_everything(self):
        from models_v2 import check_permission
        adm = self._make(StaffRole.ADMIN)
        for cmd in ['add', 'sync', 'dashboard', 'setteam', 'export']:
            assert check_permission(adm, cmd)

    def test_viewer_only_allowed_commands(self):
        from models_v2 import check_permission
        viewer = self._make(StaffRole.VIEWER)
        assert check_permission(viewer, 'dashboard')
        assert check_permission(viewer, 'pipeline')
        assert not check_permission(viewer, 'add')
        assert not check_permission(viewer, 'u')
        assert not check_permission(viewer, 'sync')

    def test_newbie_only_allowed_commands(self):
        from models_v2 import check_permission
        newbie = self._make(StaffRole.NEWBIE)
        assert check_permission(newbie, 'add')
        assert check_permission(newbie, 'me')
        assert not check_permission(newbie, 'dashboard')
        assert not check_permission(newbie, 'export')
        assert not check_permission(newbie, 'sync')

    def test_cs_allowed_commands(self):
        from models_v2 import check_permission
        cs = self._make(StaffRole.CUSTOMER_SERVICE)
        assert check_permission(cs, 'search')
        assert check_permission(cs, 'note')
        assert check_permission(cs, 'pipeline')
        assert not check_permission(cs, 'add')
        assert not check_permission(cs, 'u')
        assert not check_permission(cs, 'sync')

    def test_leader_can_all_commands(self):
        from models_v2 import check_permission
        leader = self._make(StaffRole.LEADER)
        for cmd in ['add', 'dashboard', 'export', 'setteam']:
            assert check_permission(leader, cmd)

    def test_command_with_slash_prefix(self):
        from models_v2 import check_permission
        viewer = self._make(StaffRole.VIEWER)
        assert check_permission(viewer, '/dashboard')
        assert not check_permission(viewer, '/add')

    def test_policy_engine_check_permission_teams(self):
        from engines.policy_engine import check_permission as policy_check
        assert policy_check('manager', 'setteam')
        assert policy_check('admin', 'setteam')
        assert policy_check('manager', 'teams')

    def test_policy_engine_check_permission(self):
        from engines.policy_engine import check_permission as policy_check
        assert policy_check('viewer', 'dashboard')
        assert not policy_check('viewer', 'add')
        assert policy_check('newbie', 'add')
        assert not policy_check('newbie', 'export')
        assert policy_check('customer_service', 'search')
        assert not policy_check('customer_service', 'u')
        assert policy_check('leader', 'setteam')
        assert policy_check('admin', 'sync')


# ─── Feature 2: Team assignment ───────────────────────────────────────────────

class TestTeamAssignment:
    @pytest.mark.asyncio
    async def test_auto_assign_teams_by_name(self, db):
        """Staff matching TEAM_STRUCTURE member names get auto-assigned."""
        from database_v2 import TEAM_STRUCTURE
        s = Staff(tg_user_id=5001, tg_chat_id=5001, display_name='阿YIM', role=StaffRole.FRONTDESK)
        s.id = await db.create_staff(s)
        # Initially no team
        found = await db.get_staff_by_id(s.id)
        # Run auto_assign
        count = await db.auto_assign_teams()
        assert count >= 1
        found = await db.get_staff_by_id(s.id)
        assert found.team == '阿俊'

    @pytest.mark.asyncio
    async def test_auto_assign_does_not_overwrite_existing_team(self, db):
        """Staff already assigned to a team are not re-assigned."""
        s = Staff(tg_user_id=5002, tg_chat_id=5002, display_name='阿YIM',
                  role=StaffRole.FRONTDESK, team='custom_team')
        s.id = await db.create_staff(s)
        count = await db.auto_assign_teams()
        found = await db.get_staff_by_id(s.id)
        assert found.team == 'custom_team'

    @pytest.mark.asyncio
    async def test_get_staff_by_username(self, db):
        s = Staff(tg_user_id=5003, tg_chat_id=5003, display_name='TestUser',
                  tg_username='testuser123')
        s.id = await db.create_staff(s)
        found = await db.get_staff_by_username('@testuser123')
        assert found is not None
        assert found.id == s.id
        found2 = await db.get_staff_by_username('testuser123')
        assert found2 is not None
        assert found2.id == s.id

    @pytest.mark.asyncio
    async def test_get_staff_by_username_not_found(self, db):
        result = await db.get_staff_by_username('@nobody')
        assert result is None

    @pytest.mark.asyncio
    async def test_set_staff_team(self, db, staff_row):
        await db.set_staff_team(staff_row.id, '阿俊')
        found = await db.get_staff_by_id(staff_row.id)
        assert found.team == '阿俊'

    @pytest.mark.asyncio
    async def test_get_staff_by_team(self, db, staff_row):
        await db.set_staff_team(staff_row.id, '阿俊')
        members = await db.get_staff_by_team('阿俊')
        ids = [m.id for m in members]
        assert staff_row.id in ids

    @pytest.mark.asyncio
    async def test_get_all_teams(self, db, staff_row):
        await db.set_staff_team(staff_row.id, '阿俊')
        teams = await db.get_all_teams()
        assert '阿俊' in teams


# ─── Feature 3: Group chat support ───────────────────────────────────────────

class TestGroupChat:
    @pytest.mark.asyncio
    async def test_link_and_get_group(self, db):
        with patch('handlers_v2.group_chat.database_v2', db):
            await db.link_group(-1001234567, 'Test Group', '阿俊', 'team')
            rec = await db.get_group(-1001234567)
            assert rec is not None
            assert rec['team'] == '阿俊'
            assert rec['group_name'] == 'Test Group'

    @pytest.mark.asyncio
    async def test_unlink_group(self, db):
        await db.link_group(-1009999, 'Some Group', '何军', 'team')
        deleted = await db.unlink_group(-1009999)
        assert deleted is True
        assert await db.get_group(-1009999) is None

    @pytest.mark.asyncio
    async def test_unlink_nonexistent_returns_false(self, db):
        deleted = await db.unlink_group(-9999999)
        assert deleted is False

    def test_is_group_chat_group(self):
        from handlers_v2.group_chat import is_group_chat
        assert is_group_chat({'chat_type': 'group'})
        assert is_group_chat({'chat_type': 'supergroup'})
        assert not is_group_chat({'chat_type': 'private'})
        assert not is_group_chat({})

    def test_is_command_message(self):
        from handlers_v2.group_chat import is_command_message
        assert is_command_message({'text': '/pipeline'})
        assert not is_command_message({'text': 'hello world'})
        assert not is_command_message({})

    @pytest.mark.asyncio
    async def test_group_middleware_drops_non_commands(self, db):
        from handlers_v2.group_chat import group_middleware
        task = {'chat_type': 'group', 'text': 'hello', 'chat_id': -123}
        result = await group_middleware(task)
        assert result is False

    @pytest.mark.asyncio
    async def test_group_middleware_passes_commands(self, db):
        from handlers_v2.group_chat import group_middleware
        with patch('handlers_v2.group_chat.database_v2', db):
            task = {'chat_type': 'group', 'text': '/pipeline', 'chat_id': -123}
            result = await group_middleware(task)
            assert result is True

    @pytest.mark.asyncio
    async def test_group_middleware_injects_team(self, db):
        from handlers_v2.group_chat import group_middleware
        with patch('handlers_v2.group_chat.database_v2', db):
            await db.link_group(-777, 'G', '阿俊', 'team')
            task = {'chat_type': 'supergroup', 'text': '/today', 'chat_id': -777}
            result = await group_middleware(task)
            assert result is True
            assert task.get('group_team') == '阿俊'

    @pytest.mark.asyncio
    async def test_group_middleware_dm_always_passes(self, db):
        from handlers_v2.group_chat import group_middleware
        task = {'chat_type': 'private', 'text': 'anything', 'chat_id': 123}
        result = await group_middleware(task)
        assert result is True

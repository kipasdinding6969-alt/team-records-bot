"""Database-level tests for Phase 16.5 features."""
import os
import tempfile

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Client, ClientNote, ClientStatus, Staff, StaffRole


@pytest_asyncio.fixture
async def db():
    """Create a temporary database for testing."""
    temp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    temp.close()
    database = DatabaseV2(temp.name)
    await database.connect()
    await database.initialize()
    yield database
    await database.close()
    try:
        os.unlink(temp.name)
    except FileNotFoundError:
        pass


@pytest_asyncio.fixture
async def seeded_db(db):
    """Database with test data."""
    staff = Staff(
        tg_user_id=100001, tg_chat_id=100001, display_name='TestFD',
        role=StaffRole.FRONTDESK, team='TestTeam', language='zh',
    )
    staff_id = await db.create_staff(staff)

    staff2 = Staff(
        tg_user_id=100002, tg_chat_id=100002, display_name='TestFD2',
        role=StaffRole.FRONTDESK, team='TestTeam', language='en',
    )
    staff2_id = await db.create_staff(staff2)

    client = Client(
        frontdesk_id=staff_id, phone='+8613800001111', source='test',
        status=ClientStatus.NEW,
    )
    client_id = await db.create_client(client)

    client2 = Client(
        frontdesk_id=staff2_id, phone='+8613800002222', source='test2',
        status=ClientStatus.REGISTERED,
    )
    client2_id = await db.create_client(client2)

    return db, staff_id, staff2_id, client_id, client2_id


# ─── Client Notes Tests ─────────────────────────────────────────────────────

class TestClientComments:
    @pytest.mark.asyncio
    async def test_add_comment(self, seeded_db):
        db, staff_id, _, client_id, _ = seeded_db
        note_id = await db.add_client_comment(
            client_id, staff_id, 'TestFD', 'Hello world', 'comment')
        assert note_id > 0

    @pytest.mark.asyncio
    async def test_add_comment_with_phone(self, seeded_db):
        db, staff_id, _, client_id, _ = seeded_db
        note_id = await db.add_client_comment(
            client_id, staff_id, 'TestFD', 'With phone',
            phone_normalized='8613800001111')
        assert note_id > 0

    @pytest.mark.asyncio
    async def test_get_comments(self, seeded_db):
        db, staff_id, _, client_id, _ = seeded_db
        await db.add_client_comment(client_id, staff_id, 'TestFD', 'Comment 1')
        await db.add_client_comment(client_id, staff_id, 'TestFD', 'Comment 2')
        notes = await db.get_client_comments(client_id)
        assert len(notes) >= 2
        assert any(n['content'] == 'Comment 1' for n in notes)

    @pytest.mark.asyncio
    async def test_comments_ordered_desc(self, seeded_db):
        db, staff_id, _, client_id, _ = seeded_db
        await db.add_client_comment(client_id, staff_id, 'A', 'First')
        await db.add_client_comment(client_id, staff_id, 'B', 'Second')
        notes = await db.get_client_comments(client_id)
        dates = [n['created_at'] for n in notes]
        assert dates == sorted(dates, reverse=True)


# ─── Client Timeline Tests ──────────────────────────────────────────────────

class TestClientTimeline:
    @pytest.mark.asyncio
    async def test_timeline_includes_notes(self, seeded_db):
        db, staff_id, _, client_id, _ = seeded_db
        await db.add_client_comment(client_id, staff_id, 'TestFD', 'Timeline note')
        items = await db.get_client_timeline(client_id)
        assert len(items) >= 1
        note_items = [i for i in items if i.get('timeline_type') == 'note']
        assert len(note_items) >= 1

    @pytest.mark.asyncio
    async def test_timeline_includes_links(self, seeded_db):
        db, staff_id, _, client_id, client2_id = seeded_db
        await db.create_client_link(client_id, client2_id, 'related', 'test', staff_id)
        items = await db.get_client_timeline(client_id)
        link_items = [i for i in items if i.get('timeline_type') == 'link']
        assert len(link_items) >= 1


# ─── Client Links Tests ─────────────────────────────────────────────────────

class TestClientLinksDB:
    @pytest.mark.asyncio
    async def test_create_and_get_link(self, seeded_db):
        db, staff_id, _, client_id, client2_id = seeded_db
        link_id = await db.create_client_link(client_id, client2_id, 'same_person')
        assert link_id > 0
        links = await db.get_client_links(client_id)
        assert len(links) >= 1

    @pytest.mark.asyncio
    async def test_create_and_remove_link(self, seeded_db):
        db, _, _, client_id, client2_id = seeded_db
        await db.create_client_link(client_id, client2_id, 'referral')
        removed = await db.remove_client_link(client_id, client2_id)
        assert removed is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_link(self, seeded_db):
        db, _, _, _, _ = seeded_db
        removed = await db.remove_client_link(99998, 99999)
        assert removed is False


# ─── Permission Overrides Tests ──────────────────────────────────────────────

class TestPermissionOverridesDB:
    @pytest.mark.asyncio
    async def test_set_and_get_override(self, seeded_db):
        db, staff_id, _, _, _ = seeded_db
        await db.set_permission_override(staff_id, 'view_clients', True, reason='Test')
        ov = await db.get_permission_override(staff_id, 'view_clients')
        assert ov is not None

    @pytest.mark.asyncio
    async def test_get_override_denied(self, seeded_db):
        db, staff_id, _, _, _ = seeded_db
        await db.set_permission_override(staff_id, 'test_cmd', False)
        ov = await db.get_permission_override(staff_id, 'test_cmd')
        assert ov is not None
        assert ov['allowed'] == 0

    @pytest.mark.asyncio
    async def test_get_all_overrides(self, seeded_db):
        db, staff_id, _, _, _ = seeded_db
        await db.set_permission_override(staff_id, 'all_test_cmd', True)
        overrides = await db.get_all_permission_overrides(staff_id)
        assert isinstance(overrides, list)
        assert len(overrides) >= 1

    @pytest.mark.asyncio
    async def test_remove_override(self, seeded_db):
        db, staff_id, _, _, _ = seeded_db
        await db.set_permission_override(staff_id, 'removable_cmd', True)
        removed = await db.remove_permission_override(staff_id, 'removable_cmd')
        assert removed is True

    @pytest.mark.asyncio
    async def test_upsert_override(self, seeded_db):
        db, staff_id, _, _, _ = seeded_db
        await db.set_permission_override(staff_id, 'toggle_cmd', True)
        await db.set_permission_override(staff_id, 'toggle_cmd', False)
        ov = await db.get_permission_override(staff_id, 'toggle_cmd')
        assert ov['allowed'] == 0


# ─── Performance Dashboard Tests ─────────────────────────────────────────────

class TestPerformanceDB:
    @pytest.mark.asyncio
    async def test_get_daily(self, seeded_db):
        db, _, _, _, _ = seeded_db
        from datetime import date, timezone, datetime
        today = datetime.now(timezone.utc).date().isoformat()
        # Insert stats
        async with db.get_connection() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO daily_stats
                   (staff_id, stat_date, new_leads, replied, registered, new_orders, total_deposit)
                   VALUES (?, ?, 10, 5, 3, 2, 100.0)""",
                (1, today))
            await conn.commit()
        result = await db.get_performance_daily(today)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_summary(self, seeded_db):
        db, _, _, _, _ = seeded_db
        from datetime import date, timezone, datetime
        today = datetime.now(timezone.utc).date().isoformat()
        result = await db.get_performance_summary(today, today)
        assert isinstance(result, list)


# ─── Phone Registry Enhanced Tests ───────────────────────────────────────────

class TestPhoneRegistryDB:
    @pytest.mark.asyncio
    async def test_insert_and_lookup(self, seeded_db):
        db, staff_id, _, _, _ = seeded_db
        await db.phone_registry_insert(
            '+8613800009999', 'TestFD', '2026-01-01T00:00:00',
            submitter_staff_id=staff_id)
        entry = await db.phone_registry_lookup('+8613800009999')
        assert entry is not None
        assert entry['submitter_name'] == 'TestFD'

    @pytest.mark.asyncio
    async def test_update_and_get_detail(self, seeded_db):
        db, staff_id, _, _, _ = seeded_db
        # Insert first
        await db.phone_registry_insert(
            '+8613800008888', 'TestFD', '2026-01-01T00:00:00',
            submitter_staff_id=staff_id)
        # Update fields
        updated = await db.phone_registry_update_fields(
            '+8613800008888',
            category='UK表单粉', recruiter='小王', team_name='阿毛')
        assert updated is True
        # Get detail
        detail = await db.phone_registry_get_detail('+8613800008888')
        assert detail is not None
        assert detail['category'] == 'UK表单粉'
        assert detail['team_name'] == '阿毛'

    @pytest.mark.asyncio
    async def test_find_client_by_phone_fuzzy(self, seeded_db):
        db, _, _, _, _ = seeded_db
        clients = await db.find_client_by_phone_fuzzy('+8613800001111')
        assert isinstance(clients, list)
        assert len(clients) >= 1

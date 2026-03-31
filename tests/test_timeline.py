"""Tests for Phase 9B: Client Timeline."""
import json
import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole, Client, ClientStatus


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_timeline.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=8001, tg_chat_id=7001, tg_username='timelinestaff',
        display_name='时间轴员工', role=StaffRole.FRONTDESK,
        team='何军', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client(db, staff):
    c = Client(
        frontdesk_id=staff.id, phone='0200000001', source='wechat',
        status=ClientStatus.NEW, nickname='时间轴客户',
    )
    c.id = await db.create_client(c)
    return c


# ─── log_event ────────────────────────────────────────────────────────────────

class TestLogEvent:
    @pytest.mark.asyncio
    async def test_log_returns_id(self, db, client, staff):
        event_id = await db.log_event(client.id, 'note_added', '{"note_preview":"test"}', staff.id)
        assert event_id > 0

    @pytest.mark.asyncio
    async def test_log_multiple_events(self, db, client, staff):
        await db.log_event(client.id, 'status_change', '{"from":"new","to":"replied"}', staff.id)
        await db.log_event(client.id, 'note_added', '{"note_preview":"good"}', staff.id)
        await db.log_event(client.id, 'deposit', '{"amount":500,"platform":"USDT"}', staff.id)
        events = await db.get_client_timeline(client.id, limit=10)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_log_event_without_staff(self, db, client):
        event_id = await db.log_event(client.id, 'client_created', None, None)
        assert event_id > 0


# ─── get_client_timeline ──────────────────────────────────────────────────────

class TestGetClientTimeline:
    @pytest.mark.asyncio
    async def test_returns_newest_first(self, db, client, staff):
        await db.log_event(client.id, 'status_change', '{"from":"new","to":"contacted"}', staff.id)
        await db.log_event(client.id, 'note_added', '{"note_preview":"second"}', staff.id)
        events = await db.get_client_timeline(client.id, limit=10)
        assert events[0]['event_type'] == 'note_added'
        assert events[1]['event_type'] == 'status_change'

    @pytest.mark.asyncio
    async def test_respects_limit(self, db, client, staff):
        for i in range(15):
            await db.log_event(client.id, 'note_added', f'{{"note_preview":"note{i}"}}', staff.id)
        events = await db.get_client_timeline(client.id, limit=5)
        assert len(events) == 5

    @pytest.mark.asyncio
    async def test_empty_client_returns_empty_list(self, db, client):
        events = await db.get_client_timeline(client.id)
        assert events == []

    @pytest.mark.asyncio
    async def test_event_data_includes_staff_name(self, db, client, staff):
        await db.log_event(client.id, 'tag_added', '{"tag":"vip"}', staff.id)
        events = await db.get_client_timeline(client.id)
        assert events[0]['staff_name'] == staff.display_name

    @pytest.mark.asyncio
    async def test_today_only_filter(self, db, client, staff):
        await db.log_event(client.id, 'note_added', '{"note_preview":"today"}', staff.id)
        events_today = await db.get_client_timeline(client.id, today_only=True)
        events_all = await db.get_client_timeline(client.id, limit=50)
        assert len(events_today) <= len(events_all)
        assert len(events_today) >= 1

    @pytest.mark.asyncio
    async def test_event_types_logged_correctly(self, db, client, staff):
        event_types = ['status_change', 'note_added', 'deposit',
                       'tag_added', 'tag_removed', 'voice_update',
                       'follow_up_sent', 'handoff']
        for et in event_types:
            await db.log_event(client.id, et, '{}', staff.id)
        events = await db.get_client_timeline(client.id, limit=20)
        logged_types = {e['event_type'] for e in events}
        for et in event_types:
            assert et in logged_types

    @pytest.mark.asyncio
    async def test_json_event_data_preserved(self, db, client, staff):
        data = {'amount': 1000, 'platform': 'BTC'}
        await db.log_event(client.id, 'deposit', json.dumps(data), staff.id)
        events = await db.get_client_timeline(client.id)
        stored = json.loads(events[0]['event_data'])
        assert stored['amount'] == 1000
        assert stored['platform'] == 'BTC'

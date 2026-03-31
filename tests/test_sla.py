"""Tests for Phase 9C: SLA Tracking."""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole, Client, ClientStatus


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_sla.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=9200, tg_chat_id=8200, tg_username='slastaff',
        display_name='SLA员工', role=StaffRole.FRONTDESK,
        team='阿俊', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client(db, staff):
    c = Client(
        frontdesk_id=staff.id, phone='0300000001', source='telegram',
        status=ClientStatus.NEW,
    )
    c.id = await db.create_client(c)
    return c


# ─── SLA Config ───────────────────────────────────────────────────────────────

class TestSLAConfig:
    @pytest.mark.asyncio
    async def test_default_configs_seeded(self, db):
        configs = await db.get_sla_config()
        event_types = {c['event_type'] for c in configs}
        assert 'first_response' in event_types
        assert 'status_update' in event_types
        assert 'follow_up_response' in event_types

    @pytest.mark.asyncio
    async def test_default_first_response_target(self, db):
        configs = await db.get_sla_config('first_response')
        assert len(configs) == 1
        assert configs[0]['target_minutes'] == 30
        assert configs[0]['warning_minutes'] == 20
        assert configs[0]['critical_minutes'] == 45

    @pytest.mark.asyncio
    async def test_set_sla_config_updates(self, db):
        await db.set_sla_config('first_response', 45, 30, 60)
        configs = await db.get_sla_config('first_response')
        assert configs[0]['target_minutes'] == 45
        assert configs[0]['warning_minutes'] == 30
        assert configs[0]['critical_minutes'] == 60

    @pytest.mark.asyncio
    async def test_set_sla_config_insert_new(self, db):
        await db.set_sla_config('custom_type', 90, 60, 120)
        configs = await db.get_sla_config('custom_type')
        assert len(configs) == 1
        assert configs[0]['target_minutes'] == 90


# ─── SLA Events ───────────────────────────────────────────────────────────────

class TestSLAEvents:
    @pytest.mark.asyncio
    async def test_start_sla_event_returns_id(self, db, client, staff):
        sla_id = await db.start_sla_event(client.id, staff.id, 'first_response', 30)
        assert sla_id > 0

    @pytest.mark.asyncio
    async def test_open_sla_events_listed(self, db, client, staff):
        await db.start_sla_event(client.id, staff.id, 'first_response', 30)
        open_events = await db.get_open_sla_events()
        assert len(open_events) == 1

    @pytest.mark.asyncio
    async def test_complete_sla_event_met(self, db, client, staff):
        started = datetime.utcnow() - timedelta(minutes=15)
        sla_id = await db.start_sla_event(client.id, staff.id, 'first_response', 30, started)
        result = await db.complete_sla_event(sla_id)
        assert result is True
        # Should no longer be in open events
        open_events = await db.get_open_sla_events()
        assert not any(e['id'] == sla_id for e in open_events)

    @pytest.mark.asyncio
    async def test_complete_sla_event_breach(self, db, client, staff):
        started = datetime.utcnow() - timedelta(minutes=60)
        sla_id = await db.start_sla_event(client.id, staff.id, 'first_response', 30, started)
        await db.complete_sla_event(sla_id)
        async with db.get_connection() as conn:
            cur = await conn.execute(
                'SELECT met, actual_minutes FROM sla_events WHERE id=?', (sla_id,))
            row = await cur.fetchone()
        assert row['met'] == 0  # breached
        assert row['actual_minutes'] >= 59

    @pytest.mark.asyncio
    async def test_complete_nonexistent_returns_false(self, db):
        result = await db.complete_sla_event(999999)
        assert result is False

    @pytest.mark.asyncio
    async def test_sla_stats_aggregation(self, db, client, staff):
        # Met event (15 min, target 30)
        s1 = datetime.utcnow() - timedelta(minutes=15)
        id1 = await db.start_sla_event(client.id, staff.id, 'first_response', 30, s1)
        await db.complete_sla_event(id1)
        # Breached event (50 min, target 30)
        s2 = datetime.utcnow() - timedelta(minutes=50)
        id2 = await db.start_sla_event(client.id, staff.id, 'first_response', 30, s2)
        await db.complete_sla_event(id2)

        stats = await db.get_sla_stats(staff_id=staff.id, days=1)
        fr = stats.get('first_response', {})
        assert fr['total'] == 2
        assert fr['met'] == 1
        assert fr['compliance_pct'] == 50.0

    @pytest.mark.asyncio
    async def test_staff_sla_summary(self, db, client, staff):
        s1 = datetime.utcnow() - timedelta(minutes=10)
        id1 = await db.start_sla_event(client.id, staff.id, 'first_response', 30, s1)
        await db.complete_sla_event(id1)
        summary = await db.get_staff_sla_summary(days=1)
        assert len(summary) >= 1
        row = next((r for r in summary if r['staff_id'] == staff.id), None)
        assert row is not None
        assert row['total'] == 1

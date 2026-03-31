"""Phase 10C: Shift handoff tests."""
import asyncio
import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import (
    Client, ClientStatus, ShiftHandoff, Staff, StaffRole,
)


@pytest_asyncio.fixture
async def db(tmp_path):
    db_file = str(tmp_path / 'test_handoff.db')
    d = DatabaseV2(db_file)
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def from_staff(db):
    s = Staff(tg_user_id=7001, tg_chat_id=8001, display_name='Outgoing',
              role=StaffRole.FRONTDESK, team='阿俊', language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def to_staff(db):
    s = Staff(tg_user_id=7002, tg_chat_id=8002, display_name='Incoming',
              role=StaffRole.FRONTDESK, team='阿俊', language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def clients(db, from_staff):
    """Create 3 active clients for from_staff."""
    ids = []
    for i in range(3):
        c = Client(frontdesk_id=from_staff.id, phone=f'600{i}', source='telegram',
                   status=ClientStatus.CONTACTED)
        cid = await db.create_client(c)
        ids.append(cid)
    return ids


@pytest_asyncio.fixture
async def handoff_row(db, from_staff, to_staff, clients):
    """Create a pending handoff."""
    h = ShiftHandoff(
        from_staff_id=from_staff.id,
        to_staff_id=to_staff.id,
        team='阿俊',
        status='pending',
        notes='End of shift notes',
        client_ids=json.dumps(clients),
    )
    h.id = await db.create_handoff(h)
    return h


class TestHandoffCreation:
    @pytest.mark.asyncio
    async def test_create_handoff(self, db, from_staff, to_staff, clients):
        h = ShiftHandoff(
            from_staff_id=from_staff.id,
            to_staff_id=to_staff.id,
            team='阿俊',
            client_ids=json.dumps(clients),
        )
        hid = await db.create_handoff(h)
        assert hid > 0

    @pytest.mark.asyncio
    async def test_get_handoff_by_id(self, db, handoff_row):
        found = await db.get_handoff_by_id(handoff_row.id)
        assert found is not None
        assert found.from_staff_id == handoff_row.from_staff_id
        assert found.to_staff_id == handoff_row.to_staff_id
        assert found.status == 'pending'

    @pytest.mark.asyncio
    async def test_handoff_model_fields(self, db, handoff_row):
        found = await db.get_handoff_by_id(handoff_row.id)
        assert isinstance(found, ShiftHandoff)
        assert found.team == '阿俊'
        assert found.notes == 'End of shift notes'
        client_ids = json.loads(found.client_ids)
        assert len(client_ids) == 3

    @pytest.mark.asyncio
    async def test_create_handoff_no_target(self, db, from_staff, clients):
        """Handoff with no target staff (to_staff_id=None)."""
        h = ShiftHandoff(
            from_staff_id=from_staff.id,
            to_staff_id=None,
            team='阿俊',
            client_ids=json.dumps(clients),
        )
        hid = await db.create_handoff(h)
        found = await db.get_handoff_by_id(hid)
        assert found.to_staff_id is None


class TestHandoffAcceptDecline:
    @pytest.mark.asyncio
    async def test_accept_handoff(self, db, handoff_row, to_staff, clients):
        success = await db.accept_handoff(handoff_row.id, to_staff.id)
        assert success is True
        found = await db.get_handoff_by_id(handoff_row.id)
        assert found.status == 'accepted'
        assert found.to_staff_id == to_staff.id
        assert found.accepted_at is not None
        assert found.completed_at is not None

    @pytest.mark.asyncio
    async def test_accept_reassigns_clients(self, db, handoff_row, to_staff, clients):
        await db.accept_handoff(handoff_row.id, to_staff.id)
        for cid in clients:
            client = await db.get_client_by_id(cid)
            assert client.frontdesk_id == to_staff.id

    @pytest.mark.asyncio
    async def test_accept_nonexistent_handoff(self, db, to_staff):
        success = await db.accept_handoff(9999, to_staff.id)
        assert success is False

    @pytest.mark.asyncio
    async def test_accept_already_accepted(self, db, handoff_row, to_staff):
        await db.accept_handoff(handoff_row.id, to_staff.id)
        # Second accept should fail
        success = await db.accept_handoff(handoff_row.id, to_staff.id)
        assert success is False

    @pytest.mark.asyncio
    async def test_decline_handoff(self, db, handoff_row):
        success = await db.decline_handoff(handoff_row.id)
        assert success is True
        found = await db.get_handoff_by_id(handoff_row.id)
        assert found.status == 'completed'

    @pytest.mark.asyncio
    async def test_decline_nonexistent(self, db):
        success = await db.decline_handoff(9999)
        assert success is False


class TestPendingHandoffs:
    @pytest.mark.asyncio
    async def test_get_pending_by_team(self, db, handoff_row):
        pending = await db.get_pending_handoffs(team='阿俊')
        assert len(pending) >= 1
        assert all(h.status == 'pending' for h in pending)

    @pytest.mark.asyncio
    async def test_get_pending_by_staff(self, db, handoff_row, to_staff):
        pending = await db.get_pending_handoffs(to_staff_id=to_staff.id)
        assert len(pending) >= 1

    @pytest.mark.asyncio
    async def test_no_pending_after_accept(self, db, handoff_row, to_staff):
        await db.accept_handoff(handoff_row.id, to_staff.id)
        pending = await db.get_pending_handoffs(team='阿俊')
        # Should have 0 pending (the one we had was accepted)
        assert all(h.id != handoff_row.id for h in pending)


class TestActiveClientsForStaff:
    @pytest.mark.asyncio
    async def test_get_active_clients(self, db, from_staff, clients):
        active = await db.get_active_clients_for_staff(from_staff.id)
        assert len(active) == 3
        for c in active:
            assert c.status in ClientStatus.active_statuses()

    @pytest.mark.asyncio
    async def test_no_active_clients(self, db, to_staff):
        active = await db.get_active_clients_for_staff(to_staff.id)
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_excludes_terminal_clients(self, db, from_staff):
        # Create a terminal client
        c = Client(frontdesk_id=from_staff.id, phone='999', source='test')
        cid = await db.create_client(c)
        await db.update_client_status(cid, ClientStatus.BLOCKED, from_staff.id)
        active = await db.get_active_clients_for_staff(from_staff.id)
        blocked_ids = [a.id for a in active if a.status == ClientStatus.BLOCKED]
        assert len(blocked_ids) == 0

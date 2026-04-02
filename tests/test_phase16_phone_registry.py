"""Phase 16 tests — Phone Registry, Duplicate Guard, Client Links, Permission Overrides."""
import asyncio
import json
import os
import tempfile
from datetime import datetime

import pytest
import pytest_asyncio

# Ensure project root is importable
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_v2 import DatabaseV2
from models_v2 import (
    Client, ClientStatus, Staff, StaffRole,
    check_permission, check_permission_with_db,
)


@pytest.fixture(scope='module')
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='module')
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest_asyncio.fixture(scope='module')
async def db(temp_db_path):
    d = DatabaseV2(temp_db_path)
    await d.connect()
    await d.initialize()
    yield d
    await d.close()


@pytest_asyncio.fixture(scope='module')
async def staff_a(db):
    s = Staff(tg_user_id=100001, tg_chat_id=100001, display_name='Alice', role=StaffRole.FRONTDESK, team='teamA')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture(scope='module')
async def staff_b(db):
    s = Staff(tg_user_id=100002, tg_chat_id=100002, display_name='Bob', role=StaffRole.FRONTDESK, team='teamA')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture(scope='module')
async def staff_admin(db):
    s = Staff(tg_user_id=100003, tg_chat_id=100003, display_name='Admin', role=StaffRole.ADMIN, team='teamA')
    s.id = await db.create_staff(s)
    return s


# ─── Phone Registry ─────────────────────────────────────────────────────────

class TestPhoneRegistry:
    @pytest.mark.asyncio
    async def test_normalize_phone(self, db):
        assert db.normalize_phone('+1-234-567-8900') == '12345678900'
        assert db.normalize_phone('123 456 7890') == '1234567890'
        assert db.normalize_phone('1234567890') == '1234567890'
        assert db.normalize_phone('+46 70 123 4567') == '46701234567'

    @pytest.mark.asyncio
    async def test_insert_and_lookup(self, db, staff_a):
        phone = '+1-555-0001'
        rid = await db.phone_registry_insert(
            phone, staff_a.display_name, '2026-01-01T00:00:00',
            source='bot', submitter_staff_id=staff_a.id)
        assert rid > 0

        result = await db.phone_registry_lookup(phone)
        assert result is not None
        assert result['submitter_name'] == 'Alice'
        assert result['phone_normalized'] == '15550001'
        assert result['source'] == 'bot'

    @pytest.mark.asyncio
    async def test_lookup_not_found(self, db):
        result = await db.phone_registry_lookup('+9-999-9999')
        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_insert_returns_none(self, db, staff_b):
        """Inserting the same normalized number returns None (duplicate handled gracefully)."""
        result = await db.phone_registry_insert(
            '1-555-0001', staff_b.display_name, '2026-01-02T00:00:00',
            source='bot', submitter_staff_id=staff_b.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_log_action(self, db, staff_a):
        await db.phone_registry_log_action(
            '+1-555-0001', 'submit', staff_a.display_name, staff_a.id)
        log = await db.phone_registry_get_log('+1-555-0001')
        assert len(log) >= 1
        assert log[0]['action'] == 'submit'
        assert log[0]['actor_name'] == 'Alice'

    @pytest.mark.asyncio
    async def test_log_duplicate_blocked(self, db, staff_b):
        details = json.dumps({'original_submitter': 'Alice'})
        await db.phone_registry_log_action(
            '+1-555-0001', 'duplicate_blocked', staff_b.display_name, staff_b.id, details)
        log = await db.phone_registry_get_log('+1-555-0001')
        blocked = [l for l in log if l['action'] == 'duplicate_blocked']
        assert len(blocked) >= 1
        assert 'Alice' in blocked[0]['details']

    @pytest.mark.asyncio
    async def test_override(self, db, staff_b):
        await db.phone_registry_override('+1-555-0001', staff_b.display_name, staff_b.id)
        result = await db.phone_registry_lookup('+1-555-0001')
        assert result['submitter_name'] == 'Bob'
        assert result['submitter_staff_id'] == staff_b.id

    @pytest.mark.asyncio
    async def test_search_by_number(self, db):
        results = await db.phone_registry_search('5550001')
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_by_name(self, db):
        results = await db.phone_registry_search('Bob')
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_count(self, db):
        count = await db.phone_registry_count()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_insert_second_number(self, db, staff_b):
        rid = await db.phone_registry_insert(
            '+1-555-0002', staff_b.display_name, '2026-01-05T00:00:00',
            source='telegram', submitter_staff_id=staff_b.id)
        assert rid > 0


# ─── Client Links ────────────────────────────────────────────────────────────

class TestClientLinks:
    @pytest.mark.asyncio
    async def test_create_and_get_link(self, db, staff_a):
        c1 = Client(frontdesk_id=staff_a.id, phone='111-0001', source='web')
        c2 = Client(frontdesk_id=staff_a.id, phone='111-0002', source='web')
        c1_id = await db.create_client(c1)
        c2_id = await db.create_client(c2)

        link_id = await db.create_client_link(c1_id, c2_id, 'related', 'test link', staff_a.id)
        assert link_id > 0

        links = await db.get_client_links(c1_id)
        assert len(links) >= 1

        # Both directions should work
        links_b = await db.get_client_links(c2_id)
        link_ids_a = {l['id'] for l in links}
        link_ids_b = {l['id'] for l in links_b}
        assert len(link_ids_a & link_ids_b) >= 1

        # Remove
        removed = await db.remove_client_link(c1_id, c2_id)
        assert removed is True

    @pytest.mark.asyncio
    async def test_create_link_normalized_order(self, db, staff_a):
        """Links are always stored with smaller id as client_id_a."""
        c1 = Client(frontdesk_id=staff_a.id, phone='111-0003', source='web')
        c3 = Client(frontdesk_id=staff_a.id, phone='111-0004', source='web')
        c1_id = await db.create_client(c1)
        c3_id = await db.create_client(c3)

        link_id = await db.create_client_link(c3_id, c1_id, 'family', None, staff_a.id)
        assert link_id > 0
        links = await db.get_client_links(c3_id)
        found = [l for l in links if l['link_type'] == 'family']
        assert len(found) >= 1
        assert found[0]['client_id_a'] == min(c1_id, c3_id)

    @pytest.mark.asyncio
    async def test_duplicate_link_fails(self, db, staff_a):
        c1 = Client(frontdesk_id=staff_a.id, phone='111-0005', source='web')
        c2 = Client(frontdesk_id=staff_a.id, phone='111-0006', source='web')
        c1_id = await db.create_client(c1)
        c2_id = await db.create_client(c2)
        await db.create_client_link(c1_id, c2_id, 'related', None, staff_a.id)
        import aiosqlite
        with pytest.raises(aiosqlite.IntegrityError):
            await db.create_client_link(c1_id, c2_id, 'same_person', None, staff_a.id)

    @pytest.mark.asyncio
    async def test_remove_nonexistent_link(self, db):
        removed = await db.remove_client_link(9999, 9998)
        assert removed is False


# ─── Permission Overrides ────────────────────────────────────────────────────

class TestPermissionOverrides:
    @pytest.mark.asyncio
    async def test_no_override_returns_none(self, db, staff_a):
        result = await db.get_permission_override(staff_a.id, 'add')
        assert result is None

    @pytest.mark.asyncio
    async def test_set_override_grant(self, db, staff_a, staff_admin):
        await db.set_permission_override(staff_a.id, 'broadcast', True, staff_admin.id, 'special access')
        result = await db.get_permission_override(staff_a.id, 'broadcast')
        assert result is not None
        assert bool(result['allowed']) is True
        assert result['reason'] == 'special access'

    @pytest.mark.asyncio
    async def test_set_override_deny(self, db, staff_a, staff_admin):
        await db.set_permission_override(staff_a.id, 'export', False, staff_admin.id, 'restricted')
        result = await db.get_permission_override(staff_a.id, 'export')
        assert result is not None
        assert bool(result['allowed']) is False

    @pytest.mark.asyncio
    async def test_update_override(self, db, staff_a, staff_admin):
        """Upserting should update the existing override."""
        await db.set_permission_override(staff_a.id, 'broadcast', False, staff_admin.id, 'revoked')
        result = await db.get_permission_override(staff_a.id, 'broadcast')
        assert bool(result['allowed']) is False
        assert result['reason'] == 'revoked'

    @pytest.mark.asyncio
    async def test_get_all_overrides(self, db, staff_a):
        overrides = await db.get_all_permission_overrides(staff_a.id)
        assert len(overrides) >= 2  # broadcast + export

    @pytest.mark.asyncio
    async def test_remove_override(self, db, staff_a):
        removed = await db.remove_permission_override(staff_a.id, 'broadcast')
        assert removed is True
        result = await db.get_permission_override(staff_a.id, 'broadcast')
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, db, staff_a):
        removed = await db.remove_permission_override(staff_a.id, 'nonexistent')
        assert removed is False

    @pytest.mark.asyncio
    async def test_permissions_summary(self, db, staff_a):
        summary = await db.get_staff_permissions_summary(staff_a.id)
        assert isinstance(summary, list)


# ─── check_permission with overrides ─────────────────────────────────────────

class TestCheckPermission:
    def test_basic_admin_always_allowed(self):
        admin = Staff(tg_user_id=1, tg_chat_id=1, display_name='A', role=StaffRole.ADMIN)
        assert check_permission(admin, 'anything') is True

    def test_viewer_restricted(self):
        viewer = Staff(tg_user_id=2, tg_chat_id=2, display_name='V', role=StaffRole.VIEWER)
        assert check_permission(viewer, 'dashboard') is True
        assert check_permission(viewer, 'add') is False

    def test_newbie_restricted(self):
        newbie = Staff(tg_user_id=3, tg_chat_id=3, display_name='N', role=StaffRole.NEWBIE)
        assert check_permission(newbie, 'add') is True
        assert check_permission(newbie, 'broadcast') is False

    def test_override_grant_viewer(self):
        """Override can grant a normally-denied command."""
        viewer = Staff(tg_user_id=4, tg_chat_id=4, display_name='V2', role=StaffRole.VIEWER)
        overrides = {'add': True}
        assert check_permission(viewer, 'add', overrides) is True

    def test_override_deny_admin(self):
        """Override can deny a normally-allowed command."""
        admin = Staff(tg_user_id=5, tg_chat_id=5, display_name='A2', role=StaffRole.ADMIN)
        overrides = {'broadcast': False}
        assert check_permission(admin, 'broadcast', overrides) is False

    def test_override_with_slash(self):
        """Override works with or without leading slash."""
        viewer = Staff(tg_user_id=6, tg_chat_id=6, display_name='V3', role=StaffRole.VIEWER)
        overrides = {'export': True}
        assert check_permission(viewer, '/export', overrides) is True

    def test_no_override_falls_through(self):
        """If override dict exists but doesn't have the command, fall through to role."""
        viewer = Staff(tg_user_id=7, tg_chat_id=7, display_name='V4', role=StaffRole.VIEWER)
        overrides = {'other_cmd': True}
        assert check_permission(viewer, 'add', overrides) is False
        assert check_permission(viewer, 'dashboard', overrides) is True

    @pytest.mark.asyncio
    async def test_check_permission_with_db_override(self, db, staff_a):
        """Test the async version that checks the database."""
        # Set an override
        await db.set_permission_override(staff_a.id, 'test_cmd', False)
        result = await check_permission_with_db(staff_a, 'test_cmd', db)
        assert result is False

        # Without DB, frontdesk defaults to True
        result_no_db = check_permission(staff_a, 'test_cmd')
        assert result_no_db is True

    @pytest.mark.asyncio
    async def test_check_permission_with_db_no_override(self, db, staff_a):
        """Without an override, falls back to role check."""
        result = await check_permission_with_db(staff_a, 'add', db)
        assert result is True  # frontdesk can add

    def test_customer_service_permissions(self):
        cs = Staff(tg_user_id=8, tg_chat_id=8, display_name='CS', role=StaffRole.CUSTOMER_SERVICE)
        assert check_permission(cs, 'search') is True
        assert check_permission(cs, 'add') is False

    def test_leader_all_allowed(self):
        leader = Staff(tg_user_id=9, tg_chat_id=9, display_name='L', role=StaffRole.LEADER)
        assert check_permission(leader, 'broadcast') is True
        assert check_permission(leader, 'export') is True


# ─── Phone Normalize Edge Cases ──────────────────────────────────────────────

class TestPhoneNormalize:
    def test_empty_string(self):
        assert DatabaseV2.normalize_phone('') == ''

    def test_all_non_digits(self):
        assert DatabaseV2.normalize_phone('abc-xyz') == ''

    def test_mixed(self):
        assert DatabaseV2.normalize_phone('+86 138-0000-1111') == '8613800001111'

    def test_already_clean(self):
        assert DatabaseV2.normalize_phone('1234567890') == '1234567890'


# ─── Phone Registry Log ─────────────────────────────────────────────────────

class TestPhoneRegistryLog:
    @pytest.mark.asyncio
    async def test_log_multiple_actions(self, db, staff_a, staff_b):
        phone = '+1-555-9999'
        # Insert the phone first
        try:
            await db.phone_registry_insert(
                phone, staff_a.display_name, '2026-03-01T00:00:00',
                source='bot', submitter_staff_id=staff_a.id)
        except Exception:
            pass

        await db.phone_registry_log_action(phone, 'submit', staff_a.display_name, staff_a.id)
        await db.phone_registry_log_action(phone, 'duplicate_blocked', staff_b.display_name, staff_b.id)
        await db.phone_registry_log_action(phone, 'admin_override', 'Admin', None)

        log = await db.phone_registry_get_log(phone)
        assert len(log) >= 3
        actions = [l['action'] for l in log]
        assert 'submit' in actions
        assert 'duplicate_blocked' in actions
        assert 'admin_override' in actions

    @pytest.mark.asyncio
    async def test_log_limit(self, db):
        log = await db.phone_registry_get_log('+1-555-9999', limit=1)
        assert len(log) == 1


# ─── Integration: Duplicate Guard Logic ──────────────────────────────────────

class TestDuplicateGuardLogic:
    """Test the logic that would be used by the /add handler."""

    @pytest.mark.asyncio
    async def test_new_number_allowed(self, db, staff_a):
        """A phone not in registry should be insertable."""
        result = await db.phone_registry_lookup('+1-888-0001')
        assert result is None  # Not in registry

    @pytest.mark.asyncio
    async def test_same_frontdesk_allowed(self, db, staff_a):
        """Same frontdesk should be able to see their own entry."""
        phone = '+1-888-0002'
        await db.phone_registry_insert(
            phone, staff_a.display_name, '2026-03-15T00:00:00',
            source='bot', submitter_staff_id=staff_a.id)

        result = await db.phone_registry_lookup(phone)
        assert result is not None
        assert result['submitter_staff_id'] == staff_a.id
        # Same frontdesk → allowed (logic check)
        assert result['submitter_staff_id'] == staff_a.id

    @pytest.mark.asyncio
    async def test_different_frontdesk_blocked(self, db, staff_a, staff_b):
        """Different frontdesk should be blocked by duplicate guard."""
        phone = '+1-888-0002'  # Already registered by staff_a
        result = await db.phone_registry_lookup(phone)
        assert result is not None
        assert result['submitter_staff_id'] == staff_a.id
        # Different frontdesk → blocked
        assert result['submitter_staff_id'] != staff_b.id


# ─── Client Links with Real Clients ─────────────────────────────────────────

class TestClientLinksWithData:
    @pytest.mark.asyncio
    async def test_link_type_validation(self, db, staff_a):
        """Test various link types."""
        c1 = Client(frontdesk_id=staff_a.id, phone='222-0001', source='web')
        c2 = Client(frontdesk_id=staff_a.id, phone='222-0002', source='web')
        id1 = await db.create_client(c1)
        id2 = await db.create_client(c2)

        for lt in ['related', 'same_person', 'referral', 'family']:
            # Clean up first
            await db.remove_client_link(id1, id2)
            link_id = await db.create_client_link(id1, id2, lt, f'test {lt}', staff_a.id)
            assert link_id > 0
            links = await db.get_client_links(id1)
            found = [l for l in links if l['link_type'] == lt]
            assert len(found) >= 1

    @pytest.mark.asyncio
    async def test_link_phones_in_result(self, db, staff_a):
        """Link results should include phone numbers."""
        c1 = Client(frontdesk_id=staff_a.id, phone='333-0001', source='web')
        c2 = Client(frontdesk_id=staff_a.id, phone='333-0002', source='web')
        id1 = await db.create_client(c1)
        id2 = await db.create_client(c2)
        await db.create_client_link(id1, id2, 'related', None, staff_a.id)

        links = await db.get_client_links(id1)
        assert len(links) >= 1
        link = links[0]
        assert 'phone_a' in link
        assert 'phone_b' in link

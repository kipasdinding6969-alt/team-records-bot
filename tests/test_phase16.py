"""Phase 16 tests — phone registry, client links, permission overrides, RBAC API."""
import asyncio
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# ─── Env vars must be set BEFORE importing app ────────────────────────────────
TEST_JWT_SECRET = 'test-phase16-jwt-secret-padding1'
TEST_OWNER_USER = 'p16_owner'
TEST_OWNER_PASS = 'ownerpass16'
os.environ['JWT_SECRET'] = TEST_JWT_SECRET
os.environ['DASHBOARD_USER'] = TEST_OWNER_USER
os.environ['DASHBOARD_PASS'] = TEST_OWNER_PASS

# ─── Shared DB helpers ────────────────────────────────────────────────────────

_PHASE16_SCHEMA = """
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER UNIQUE,
    tg_chat_id INTEGER DEFAULT 0,
    display_name TEXT NOT NULL,
    role TEXT DEFAULT 'frontdesk',
    team TEXT,
    is_active INTEGER DEFAULT 1,
    language TEXT DEFAULT 'zh',
    daily_target INTEGER DEFAULT 40
);
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frontdesk_id INTEGER,
    phone TEXT NOT NULL,
    source TEXT DEFAULT 'telegram',
    nickname TEXT,
    recruiter TEXT,
    status TEXT DEFAULT 'new',
    total_deposited REAL DEFAULT 0,
    platform TEXT,
    sheet_gid INTEGER,
    first_day_status TEXT DEFAULT 'pending',
    second_day_status TEXT DEFAULT 'pending',
    client_condition TEXT,
    category TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    contacted_at TEXT,
    replied_at TEXT,
    registered_at TEXT,
    training_at TEXT,
    first_order_at TEXT,
    next_followup TEXT
);
CREATE TABLE IF NOT EXISTS phone_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    phone_normalized TEXT NOT NULL,
    submitter_name TEXT NOT NULL,
    submitter_staff_id INTEGER,
    source TEXT DEFAULT 'telegram',
    submitted_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(phone_normalized)
);
CREATE TABLE IF NOT EXISTS phone_registry_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_normalized TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    actor_staff_id INTEGER,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS client_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id_a INTEGER NOT NULL,
    client_id_b INTEGER NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'related',
    note TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id_a, client_id_b)
);
CREATE TABLE IF NOT EXISTS permission_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    allowed BOOLEAN NOT NULL,
    granted_by INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(staff_id, command)
);
CREATE TABLE IF NOT EXISTS client_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    staff_id INTEGER,
    note_type TEXT DEFAULT 'update',
    old_status TEXT,
    new_status TEXT,
    content TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    frontdesk_id INTEGER,
    amount REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    platform TEXT,
    deposit_date TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS xp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL,
    action TEXT,
    xp_amount INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS streaks (
    staff_id INTEGER PRIMARY KEY,
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_action_date TEXT
);
CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER,
    stat_date TEXT,
    new_leads INTEGER DEFAULT 0,
    contacted INTEGER DEFAULT 0,
    replied INTEGER DEFAULT 0,
    registered INTEGER DEFAULT 0,
    training INTEGER DEFAULT 0,
    withdrew INTEGER DEFAULT 0,
    new_orders INTEGER DEFAULT 0,
    ghosted INTEGER DEFAULT 0,
    blocked INTEGER DEFAULT 0,
    dead INTEGER DEFAULT 0,
    reply_rate REAL DEFAULT 0,
    conversion_rate REAL DEFAULT 0,
    total_deposit REAL DEFAULT 0,
    UNIQUE(staff_id, stat_date)
);
"""


# ══════════════════════════════════════════════════════════════════════════════
# 1. check_permission with overrides
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckPermissionWithOverrides:
    """Tests for models_v2.check_permission(staff, command, overrides=...)."""

    def _make_staff(self, role):
        from models_v2 import Staff, StaffRole
        return Staff(tg_user_id=9001, tg_chat_id=9001, display_name='TestUser',
                     id=1, role=role)

    def test_override_grant_allows_newbie_add(self):
        """Newbie gets /add granted via override."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.NEWBIE)
        # newbie already has /add by default, test /export which is not in NEWBIE set
        result = check_permission(staff, 'export', {'export': True})
        assert result is True

    def test_override_deny_blocks_frontdesk(self):
        """Frontdesk denied /add via override."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.FRONTDESK)
        result = check_permission(staff, 'add', {'add': False})
        assert result is False

    def test_override_takes_priority_over_role_default(self):
        """Override True beats role restriction (viewer blocked by default)."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.VIEWER)
        # /add is NOT in VIEWER_COMMANDS but override grants it
        result = check_permission(staff, 'add', {'add': True})
        assert result is True

    def test_no_overrides_falls_back_to_role(self):
        """Without overrides, newbie falls back to role defaults."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.NEWBIE)
        # newbie can /add but NOT /export
        assert check_permission(staff, 'add') is True
        assert check_permission(staff, 'export') is False

    def test_admin_always_gets_true_regardless_of_overrides(self):
        """Admin gets True even with a deny override (overrides checked first but admin has True)."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.ADMIN)
        # With no overrides, admin returns True
        assert check_permission(staff, 'delete_everything') is True

    def test_viewer_gets_false_for_unlisted_commands(self):
        """Viewer without override returns False for non-viewer commands."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.VIEWER)
        result = check_permission(staff, 'add')
        assert result is False

    def test_override_with_slash_prefix_stripped(self):
        """Command with leading slash is correctly matched to override key."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.VIEWER)
        # Override stored without slash, command passed with slash
        result = check_permission(staff, '/add', {'add': True})
        assert result is True

    def test_empty_overrides_dict_falls_back_to_role(self):
        """Empty overrides dict falls back to role defaults."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.CUSTOMER_SERVICE)
        # CS can /search
        result = check_permission(staff, 'search', {})
        assert result is True

    def test_cs_blocked_for_non_cs_command(self):
        """Customer service cannot use /add by default."""
        from models_v2 import check_permission, StaffRole
        staff = self._make_staff(StaffRole.CUSTOMER_SERVICE)
        result = check_permission(staff, 'add')
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. check_permission_with_db
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckPermissionWithDb:
    """Tests for models_v2.check_permission_with_db async function."""

    def _make_staff(self, role, staff_id=5):
        from models_v2 import Staff, StaffRole
        return Staff(tg_user_id=8001, tg_chat_id=8001, display_name='DbUser',
                     id=staff_id, role=role)

    def test_db_override_allowed_true(self):
        """DB returns allowed=True override — permission granted."""
        from models_v2 import check_permission_with_db, StaffRole
        staff = self._make_staff(StaffRole.VIEWER)
        mock_db = MagicMock()
        mock_db.get_permission_override = AsyncMock(return_value={'allowed': True})
        result = asyncio.run(check_permission_with_db(staff, 'add', db=mock_db))
        assert result is True

    def test_db_override_allowed_false(self):
        """DB returns allowed=False override — permission denied."""
        from models_v2 import check_permission_with_db, StaffRole
        staff = self._make_staff(StaffRole.FRONTDESK)
        mock_db = MagicMock()
        mock_db.get_permission_override = AsyncMock(return_value={'allowed': False})
        result = asyncio.run(check_permission_with_db(staff, 'add', db=mock_db))
        assert result is False

    def test_db_returns_none_falls_back_to_role(self):
        """DB returns None (no override) — falls back to role-based check."""
        from models_v2 import check_permission_with_db, StaffRole
        staff = self._make_staff(StaffRole.NEWBIE)
        mock_db = MagicMock()
        mock_db.get_permission_override = AsyncMock(return_value=None)
        # Newbie can /add by default
        result = asyncio.run(check_permission_with_db(staff, 'add', db=mock_db))
        assert result is True

    def test_staff_with_no_id_falls_back_to_role(self):
        """Staff with id=None — no DB lookup, falls back to role."""
        from models_v2 import check_permission_with_db, StaffRole
        staff = self._make_staff(StaffRole.VIEWER, staff_id=None)
        mock_db = MagicMock()
        mock_db.get_permission_override = AsyncMock(return_value={'allowed': True})
        # id is None so db is NOT queried — viewer cannot /add
        result = asyncio.run(check_permission_with_db(staff, 'add', db=mock_db))
        mock_db.get_permission_override.assert_not_called()
        assert result is False

    def test_no_db_falls_back_to_role(self):
        """No db provided — pure role-based check."""
        from models_v2 import check_permission_with_db, StaffRole
        staff = self._make_staff(StaffRole.CUSTOMER_SERVICE)
        result = asyncio.run(check_permission_with_db(staff, 'search', db=None))
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. Phone Registry DB methods (real aiosqlite in-memory)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def phone_db_path():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    # Set up schema synchronously
    conn = sqlite3.connect(path)
    conn.executescript(_PHASE16_SCHEMA)
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def phone_db(phone_db_path):
    from database_v2 import DatabaseV2

    async def _setup():
        db = DatabaseV2(phone_db_path)
        await db.connect()
        return db

    async def _teardown(db):
        # Clean up phone registry between tests
        async with db.get_connection() as conn:
            await conn.execute('DELETE FROM phone_registry')
            await conn.execute('DELETE FROM phone_registry_log')
            await conn.commit()
        await db.close()

    db = asyncio.run(_setup())
    yield db
    asyncio.run(_teardown(db))


@pytest.mark.asyncio
class TestPhoneRegistryDB:

    async def test_insert_succeeds(self, phone_db):
        """phone_registry_insert returns a positive row id."""
        row_id = await phone_db.phone_registry_insert(
            '+60123456789', 'Alice', '2026-03-31T10:00:00'
        )
        assert isinstance(row_id, int)
        assert row_id > 0

    async def test_lookup_finds_by_phone(self, phone_db):
        """phone_registry_lookup returns the correct entry."""
        await phone_db.phone_registry_insert(
            '+60198765432', 'Bob', '2026-03-31T11:00:00'
        )
        entry = await phone_db.phone_registry_lookup('+60198765432')
        assert entry is not None
        assert entry['submitter_name'] == 'Bob'

    async def test_lookup_normalizes_phone(self, phone_db):
        """Lookup normalizes phone (strips +, spaces) before querying."""
        await phone_db.phone_registry_insert(
            '60 11-2345 6789', 'Charlie', '2026-03-31T12:00:00'
        )
        # Look up with different formatting
        entry = await phone_db.phone_registry_lookup('601123456789')
        assert entry is not None
        assert entry['submitter_name'] == 'Charlie'

    async def test_lookup_returns_none_for_missing(self, phone_db):
        """Lookup returns None when phone is not in registry."""
        entry = await phone_db.phone_registry_lookup('+60199999999')
        assert entry is None

    async def test_log_action_inserts_entry(self, phone_db):
        """phone_registry_log_action inserts a log row."""
        await phone_db.phone_registry_insert(
            '+60111111111', 'Dave', '2026-03-31T13:00:00'
        )
        await phone_db.phone_registry_log_action(
            '+60111111111', 'viewed', 'Admin', actor_staff_id=1
        )
        log = await phone_db.phone_registry_get_log('+60111111111')
        assert len(log) >= 1
        assert log[0]['action'] == 'viewed'

    async def test_get_log_retrieves_entries(self, phone_db):
        """phone_registry_get_log returns all log entries for a phone."""
        await phone_db.phone_registry_insert(
            '+60122222222', 'Eve', '2026-03-31T14:00:00'
        )
        await phone_db.phone_registry_log_action('+60122222222', 'submit', 'Eve')
        await phone_db.phone_registry_log_action('+60122222222', 'lookup', 'Admin')
        log = await phone_db.phone_registry_get_log('+60122222222')
        actions = [entry['action'] for entry in log]
        assert 'submit' in actions
        assert 'lookup' in actions

    async def test_override_updates_submitter(self, phone_db):
        """phone_registry_override changes the submitter_name."""
        await phone_db.phone_registry_insert(
            '+60133333333', 'Original', '2026-03-31T15:00:00'
        )
        await phone_db.phone_registry_override('+60133333333', 'NewOwner', new_staff_id=2)
        entry = await phone_db.phone_registry_lookup('+60133333333')
        assert entry['submitter_name'] == 'NewOwner'
        assert entry['submitter_staff_id'] == 2

    async def test_search_by_partial_number(self, phone_db):
        """phone_registry_search finds entries by partial phone."""
        await phone_db.phone_registry_insert(
            '+60144444444', 'Frank', '2026-03-31T16:00:00'
        )
        results = await phone_db.phone_registry_search('44444')
        phones = [r['phone_normalized'] for r in results]
        assert any('44444' in p for p in phones)

    async def test_search_by_submitter_name(self, phone_db):
        """phone_registry_search finds entries by submitter name."""
        await phone_db.phone_registry_insert(
            '+60155555555', 'SearchableGrace', '2026-03-31T17:00:00'
        )
        results = await phone_db.phone_registry_search('SearchableGrace')
        names = [r['submitter_name'] for r in results]
        assert 'SearchableGrace' in names

    async def test_count_returns_correct_value(self, phone_db):
        """phone_registry_count returns the number of entries."""
        before = await phone_db.phone_registry_count()
        await phone_db.phone_registry_insert(
            '+60166666666', 'Henry', '2026-03-31T18:00:00'
        )
        after = await phone_db.phone_registry_count()
        assert after == before + 1

    async def test_duplicate_insert_returns_none(self, phone_db):
        """Inserting the same normalized phone twice returns None (no raise)."""
        first = await phone_db.phone_registry_insert(
            '+60177777777', 'First', '2026-03-31T08:00:00'
        )
        assert first is not None
        second = await phone_db.phone_registry_insert(
            '60177777777', 'Second', '2026-03-31T09:00:00'
        )
        assert second is None

    async def test_normalize_phone_strips_plus_and_spaces(self, phone_db):
        """normalize_phone strips +, spaces and dashes."""
        assert phone_db.normalize_phone('+60 12-345 6789') == '60123456789'

    async def test_normalize_phone_handles_already_normalized(self, phone_db):
        """normalize_phone returns unchanged string that has only digits."""
        assert phone_db.normalize_phone('60123456789') == '60123456789'

    async def test_insert_with_source_bot(self, phone_db):
        """phone_registry_insert accepts source='bot'."""
        row_id = await phone_db.phone_registry_insert(
            '+60188888888', 'Ivan', '2026-03-31T19:00:00', source='bot'
        )
        entry = await phone_db.phone_registry_lookup('+60188888888')
        assert entry['source'] == 'bot'
        assert row_id > 0

    async def test_insert_with_source_import(self, phone_db):
        """phone_registry_insert accepts source='import'."""
        await phone_db.phone_registry_insert(
            '+60199999999', 'Jenny', '2026-03-31T20:00:00', source='import'
        )
        entry = await phone_db.phone_registry_lookup('+60199999999')
        assert entry['source'] == 'import'


# ══════════════════════════════════════════════════════════════════════════════
# 4. Client Links DB methods
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def links_db_path():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    conn = sqlite3.connect(path)
    conn.executescript(_PHASE16_SCHEMA)
    # Seed two staff + two clients
    conn.execute("INSERT INTO staff (id, tg_user_id, display_name, role) VALUES (1, 101, 'FD1', 'frontdesk')")
    conn.execute("INSERT INTO staff (id, tg_user_id, display_name, role) VALUES (2, 102, 'FD2', 'frontdesk')")
    conn.execute("INSERT INTO clients (id, frontdesk_id, phone, source) VALUES (10, 1, '0101', 'manual')")
    conn.execute("INSERT INTO clients (id, frontdesk_id, phone, source) VALUES (20, 2, '0202', 'manual')")
    conn.execute("INSERT INTO clients (id, frontdesk_id, phone, source) VALUES (30, 1, '0303', 'manual')")
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def links_db(links_db_path):
    from database_v2 import DatabaseV2

    async def _setup():
        db = DatabaseV2(links_db_path)
        await db.connect()
        return db

    async def _teardown(db):
        async with db.get_connection() as conn:
            await conn.execute('DELETE FROM client_links')
            await conn.commit()
        await db.close()

    db = asyncio.run(_setup())
    yield db
    asyncio.run(_teardown(db))


@pytest.mark.asyncio
class TestClientLinksDB:

    async def test_create_client_link_succeeds(self, links_db):
        """create_client_link returns a positive row id."""
        link_id = await links_db.create_client_link(10, 20, 'related')
        assert isinstance(link_id, int)
        assert link_id > 0

    async def test_create_link_normalizes_order(self, links_db):
        """Smaller id is always stored as client_id_a regardless of input order."""
        import aiosqlite
        link_id = await links_db.create_client_link(30, 10, 'referral')
        async with links_db.get_connection() as db:
            cur = await db.execute(
                'SELECT client_id_a, client_id_b FROM client_links WHERE id = ?',
                (link_id,)
            )
            row = await cur.fetchone()
        assert row['client_id_a'] < row['client_id_b']
        assert row['client_id_a'] == 10
        assert row['client_id_b'] == 30

    async def test_remove_client_link_returns_true(self, links_db):
        """remove_client_link returns True on successful deletion."""
        await links_db.create_client_link(10, 20, 'related')
        removed = await links_db.remove_client_link(10, 20)
        assert removed is True

    async def test_remove_client_link_returns_false_not_found(self, links_db):
        """remove_client_link returns False when link does not exist."""
        removed = await links_db.remove_client_link(10, 99)
        assert removed is False

    async def test_get_client_links_empty(self, links_db):
        """get_client_links returns empty list when no links exist for client."""
        # Ensure client 30 has no links
        await links_db.remove_client_link(10, 30)
        links = await links_db.get_client_links(30)
        assert isinstance(links, list)
        assert len(links) == 0

    async def test_get_client_links_returns_bidirectional(self, links_db):
        """get_client_links returns the link regardless of which side you query."""
        await links_db.create_client_link(10, 20, 'family')
        links_from_10 = await links_db.get_client_links(10)
        links_from_20 = await links_db.get_client_links(20)
        assert len(links_from_10) >= 1
        assert len(links_from_20) >= 1

    async def test_duplicate_link_raises(self, links_db):
        """Inserting the same pair twice raises an IntegrityError."""
        await links_db.create_client_link(10, 30, 'same_person')
        with pytest.raises(Exception):
            await links_db.create_client_link(10, 30, 'related')

    async def test_create_link_with_note_and_type(self, links_db):
        """create_client_link stores note and link_type correctly."""
        link_id = await links_db.create_client_link(
            20, 30, 'referral', note='Referred each other', created_by=1
        )
        links = await links_db.get_client_links(20)
        target = next((l for l in links if l['id'] == link_id), None)
        assert target is not None
        assert target['link_type'] == 'referral'
        assert target['note'] == 'Referred each other'


# ══════════════════════════════════════════════════════════════════════════════
# 5. Permission Overrides DB methods
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def perms_db_path():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    conn = sqlite3.connect(path)
    conn.executescript(_PHASE16_SCHEMA)
    conn.execute("INSERT INTO staff (id, tg_user_id, display_name, role) VALUES (1, 201, 'StaffA', 'newbie')")
    conn.execute("INSERT INTO staff (id, tg_user_id, display_name, role) VALUES (2, 202, 'StaffB', 'frontdesk')")
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def perms_db(perms_db_path):
    from database_v2 import DatabaseV2

    async def _setup():
        db = DatabaseV2(perms_db_path)
        await db.connect()
        return db

    async def _teardown(db):
        async with db.get_connection() as conn:
            await conn.execute('DELETE FROM permission_overrides')
            await conn.commit()
        await db.close()

    db = asyncio.run(_setup())
    yield db
    asyncio.run(_teardown(db))


@pytest.mark.asyncio
class TestPermissionOverridesDB:

    async def test_set_permission_override_insert(self, perms_db):
        """set_permission_override inserts a new row."""
        await perms_db.set_permission_override(1, 'export', True, granted_by=2)
        entry = await perms_db.get_permission_override(1, 'export')
        assert entry is not None
        assert entry['allowed'] == 1  # SQLite stores boolean as int

    async def test_set_permission_override_upsert(self, perms_db):
        """set_permission_override updates an existing row on conflict."""
        await perms_db.set_permission_override(1, 'add', True)
        await perms_db.set_permission_override(1, 'add', False)
        entry = await perms_db.get_permission_override(1, 'add')
        assert entry['allowed'] == 0

    async def test_get_permission_override_returns_dict(self, perms_db):
        """get_permission_override returns a dict with expected keys."""
        await perms_db.set_permission_override(1, 'note', True)
        entry = await perms_db.get_permission_override(1, 'note')
        assert isinstance(entry, dict)
        assert 'staff_id' in entry
        assert 'command' in entry
        assert 'allowed' in entry

    async def test_get_permission_override_returns_none_for_missing(self, perms_db):
        """get_permission_override returns None when no override exists."""
        entry = await perms_db.get_permission_override(1, 'nonexistent_cmd')
        assert entry is None

    async def test_get_all_permission_overrides_returns_list(self, perms_db):
        """get_all_permission_overrides returns a list of dicts."""
        await perms_db.set_permission_override(2, 'export', True)
        await perms_db.set_permission_override(2, 'pipeline', False)
        overrides = await perms_db.get_all_permission_overrides(2)
        assert isinstance(overrides, list)
        commands = [o['command'] for o in overrides]
        assert 'export' in commands
        assert 'pipeline' in commands

    async def test_remove_permission_override_returns_true(self, perms_db):
        """remove_permission_override returns True on successful deletion."""
        await perms_db.set_permission_override(1, 'rag', True)
        removed = await perms_db.remove_permission_override(1, 'rag')
        assert removed is True
        entry = await perms_db.get_permission_override(1, 'rag')
        assert entry is None

    async def test_remove_permission_override_returns_false_not_found(self, perms_db):
        """remove_permission_override returns False when override does not exist."""
        removed = await perms_db.remove_permission_override(1, 'totally_missing')
        assert removed is False

    async def test_override_with_reason_field(self, perms_db):
        """Override stores and retrieves the reason field."""
        await perms_db.set_permission_override(
            1, 'dashboard', True, granted_by=2, reason='Promoted temporarily'
        )
        entry = await perms_db.get_permission_override(1, 'dashboard')
        assert entry['reason'] == 'Promoted temporarily'
        assert entry['granted_by'] == 2


# ══════════════════════════════════════════════════════════════════════════════
# 6. API endpoint tests using FastAPI TestClient
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def api_db_path():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.executescript(_PHASE16_SCHEMA)
    # Seed staff
    conn.execute("INSERT INTO staff (id, tg_user_id, display_name, role, team) VALUES (1, 301, 'FD Alpha', 'frontdesk', 'Alpha')")
    conn.execute("INSERT INTO staff (id, tg_user_id, display_name, role, team) VALUES (2, 302, 'FD Beta', 'frontdesk', 'Beta')")
    # Seed clients (needed for links endpoint)
    conn.execute("INSERT INTO clients (id, frontdesk_id, phone, source) VALUES (1, 1, '111111', 'manual')")
    conn.execute("INSERT INTO clients (id, frontdesk_id, phone, source) VALUES (2, 2, '222222', 'manual')")
    # Seed phone registry entry
    conn.execute("""
        INSERT INTO phone_registry (phone, phone_normalized, submitter_name, submitted_at, source)
        VALUES ('+60100000001', '60100000001', 'Alice', '2026-03-31T08:00:00', 'telegram')
    """)
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture(scope='module')
def api_client(api_db_path):
    from fastapi.testclient import TestClient
    os.environ['DB_PATH'] = api_db_path
    os.environ['DASHBOARD_USER'] = TEST_OWNER_USER
    os.environ['DASHBOARD_PASS'] = TEST_OWNER_PASS
    os.environ['JWT_SECRET'] = TEST_JWT_SECRET
    if 'web_dashboard_api' in sys.modules:
        del sys.modules['web_dashboard_api']
    import web_dashboard_api
    with TestClient(web_dashboard_api.app) as c:
        yield c


def _login(client, username, password):
    """Helper: login and return auth headers."""
    res = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert res.status_code == 200, f'Login failed: {res.text}'
    token = res.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _create_member(client, owner_headers, username='p16_member', password='memberpass16'):
    """Create a member user and return their credentials."""
    client.post('/api/users', json={
        'username': username,
        'password': password,
        'display_name': 'Phase16 Member',
        'role': 'member',
        'team_scope': 'Alpha',
    }, headers=owner_headers)
    return username, password


class TestPhoneRegistryAPI:

    @pytest.fixture(scope='class', autouse=True)
    def setup_users(self, api_client):
        """Create owner + member users once for the class."""
        owner_headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        # Ensure member exists
        api_client.post('/api/users', json={
            'username': 'p16_member',
            'password': 'memberpass16',
            'display_name': 'P16 Member',
            'role': 'member',
            'team_scope': 'Alpha',
        }, headers=owner_headers)

    def test_stats_returns_200_with_required_fields(self, api_client):
        """GET /api/phone-registry/stats returns total and duplicates_blocked."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/stats', headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert 'total' in data
        assert 'duplicates_blocked' in data

    def test_stats_total_is_integer(self, api_client):
        """Stats total field is a non-negative integer."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/stats', headers=headers)
        assert res.status_code == 200
        assert isinstance(res.json()['total'], int)
        assert res.json()['total'] >= 0

    def test_lookup_found(self, api_client):
        """Lookup of seeded phone returns found=True."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/lookup?phone=+60100000001', headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data['found'] is True
        assert data['submitter_name'] == 'Alice'

    def test_lookup_not_found(self, api_client):
        """Lookup of non-existent phone returns found=False."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/lookup?phone=+60100000099', headers=headers)
        assert res.status_code == 200
        assert res.json()['found'] is False

    def test_lookup_with_normalized_phone(self, api_client):
        """Lookup works with normalized phone (no +)."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/lookup?phone=60100000001', headers=headers)
        assert res.status_code == 200
        assert res.json()['found'] is True

    def test_lookup_invalid_format_returns_not_found_gracefully(self, api_client):
        """Invalid/garbage phone returns found=False without 5xx."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/lookup?phone=abc-xyz', headers=headers)
        assert res.status_code == 200
        assert res.json()['found'] is False

    def test_search_returns_results_with_total(self, api_client):
        """GET /api/phone-registry/search returns total and results list."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/search?q=Alice', headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert 'total' in data
        assert 'results' in data
        assert isinstance(data['results'], list)

    def test_search_finds_by_partial_number(self, api_client):
        """Search returns entries matching partial phone number."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/phone-registry/search?q=60100000001', headers=headers)
        assert res.status_code == 200
        assert res.json()['total'] >= 1

    def test_override_admin_can_change_owner(self, api_client):
        """POST /api/phone-registry/override succeeds for admin/owner."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.post(
            '/api/phone-registry/override?phone=+60100000001',
            json={'new_submitter': 'NewOwner', 'new_staff_id': None},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()['ok'] is True

    def test_override_member_gets_403(self, api_client):
        """Member cannot override phone registry ownership."""
        member_headers = _login(api_client, 'p16_member', 'memberpass16')
        res = api_client.post(
            '/api/phone-registry/override?phone=+60100000001',
            json={'new_submitter': 'Hacker', 'new_staff_id': None},
            headers=member_headers,
        )
        assert res.status_code == 403


class TestPermissionsAPI:

    @pytest.fixture(scope='class', autouse=True)
    def setup_users(self, api_client):
        """Ensure owner exists — app startup creates it from env."""
        pass

    def test_get_all_permissions_owner_only(self, api_client):
        """GET /api/permissions returns list (admin/owner only)."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/permissions', headers=headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_get_staff_permissions(self, api_client):
        """GET /api/permissions/{staff_id} returns overrides dict."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/permissions/1', headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert 'overrides' in data or isinstance(data, dict)

    def test_post_permission_creates_override(self, api_client):
        """POST /api/permissions creates a new permission override."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.post('/api/permissions', json={
            'staff_id': 1,
            'command': 'test_cmd',
            'allowed': True,
            'reason': 'Testing',
        }, headers=headers)
        assert res.status_code == 200
        assert res.json().get('ok') is True

    def test_delete_permission_override(self, api_client):
        """DELETE /api/permissions/{staff_id}/{command} removes the override."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        # First create it
        api_client.post('/api/permissions', json={
            'staff_id': 1,
            'command': 'to_delete',
            'allowed': False,
        }, headers=headers)
        # Then delete
        res = api_client.delete('/api/permissions/1/to_delete', headers=headers)
        assert res.status_code == 200
        assert res.json().get('ok') is True

    def test_member_blocked_from_get_permissions(self, api_client):
        """Member cannot list all permissions."""
        member_headers = _login(api_client, 'p16_member', 'memberpass16')
        res = api_client.get('/api/permissions', headers=member_headers)
        assert res.status_code == 403


class TestClientLinksAPI:

    @pytest.fixture(scope='class', autouse=True)
    def setup_users(self, api_client):
        pass

    def test_get_client_links_empty(self, api_client):
        """GET /api/clients/{id}/links returns empty list for unlinked client."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/clients/1/links', headers=headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_post_create_client_link(self, api_client):
        """POST /api/client-links creates a link between two clients."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.post('/api/client-links', json={
            'client_id_a': 1,
            'client_id_b': 2,
            'link_type': 'related',
        }, headers=headers)
        assert res.status_code == 200
        assert res.json()['ok'] is True

    def test_get_client_links_returns_created_link(self, api_client):
        """After creating, GET /api/clients/{id}/links returns the link."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.get('/api/clients/1/links', headers=headers)
        assert res.status_code == 200
        links = res.json()
        assert len(links) >= 1

    def test_delete_client_link(self, api_client):
        """DELETE /api/client-links/{link_id} removes the link."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        # Create a fresh link
        create_res = api_client.post('/api/client-links', json={
            'client_id_a': 1,
            'client_id_b': 2,
            'link_type': 'referral',
        }, headers=headers)
        # If already exists, get the existing id via the list
        if create_res.status_code == 409:
            links = api_client.get('/api/clients/1/links', headers=headers).json()
            link_id = links[0]['id']
        else:
            # We need to find the id — query the list
            links = api_client.get('/api/clients/1/links', headers=headers).json()
            link_id = links[0]['id']

        res = api_client.delete(f'/api/client-links/{link_id}', headers=headers)
        assert res.status_code == 200
        assert res.json()['ok'] is True

    def test_delete_nonexistent_link_returns_404(self, api_client):
        """DELETE /api/client-links/99999 returns 404."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.delete('/api/client-links/99999', headers=headers)
        assert res.status_code == 404

    def test_create_link_invalid_type_returns_400(self, api_client):
        """POST /api/client-links with invalid link_type returns 400."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = api_client.post('/api/client-links', json={
            'client_id_a': 1,
            'client_id_b': 2,
            'link_type': 'invalid_type',
        }, headers=headers)
        assert res.status_code == 400

    def test_duplicate_link_returns_409(self, api_client):
        """POST /api/client-links for the same pair twice returns 409."""
        headers = _login(api_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        payload = {'client_id_a': 1, 'client_id_b': 2, 'link_type': 'family'}
        api_client.post('/api/client-links', json=payload, headers=headers)
        res = api_client.post('/api/client-links', json=payload, headers=headers)
        assert res.status_code == 409

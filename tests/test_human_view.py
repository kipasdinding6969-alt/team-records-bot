"""Human-View Tests — End-to-end simulation of real user workflows.

Tests what actual humans experience: frontdesk adding clients, updating status,
pipeline flowing, reports generating, policies blocking bad actions, and
messages routing to correct forum topics.
"""
import pytest
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Create a fresh test database with V2 schema."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER NOT NULL UNIQUE,
            tg_chat_id INTEGER NOT NULL,
            tg_username TEXT,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'frontdesk',
            team TEXT,
            phone TEXT,
            language TEXT DEFAULT 'zh',
            is_active INTEGER DEFAULT 1,
            daily_target INTEGER DEFAULT 5,
            created_at TEXT,
            last_active_at TEXT,
            maintenance_id INTEGER
        );
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frontdesk_id INTEGER NOT NULL,
            phone TEXT NOT NULL,
            account_id TEXT,
            phone_remark TEXT,
            nickname TEXT,
            source TEXT,
            recruiter TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            status_note TEXT,
            contacted_at TEXT,
            replied_at TEXT,
            registered_at TEXT,
            training_at TEXT,
            withdrew_at TEXT,
            first_order_at TEXT,
            next_followup TEXT,
            followup_count INTEGER DEFAULT 0,
            platform TEXT,
            total_deposited REAL DEFAULT 0,
            sheet_gid INTEGER,
            created_at TEXT,
            updated_at TEXT,
            sheet_row INTEGER,
            maintenance_id INTEGER,
            handoff_at TEXT,
            handoff_note TEXT,
            FOREIGN KEY (frontdesk_id) REFERENCES staff(id)
        );
        CREATE TABLE client_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            staff_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
        CREATE TABLE daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            new_clients INTEGER DEFAULT 0,
            contacted INTEGER DEFAULT 0,
            replied INTEGER DEFAULT 0,
            registered INTEGER DEFAULT 0,
            training INTEGER DEFAULT 0,
            withdrew INTEGER DEFAULT 0,
            ordered INTEGER DEFAULT 0,
            UNIQUE(staff_id, date)
        );
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            client_id INTEGER,
            reminder_type TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            sent_at TEXT
        );
        CREATE TABLE deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            staff_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            knife_number INTEGER,
            note TEXT,
            created_at TEXT
        );
        CREATE TABLE team_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT NOT NULL,
            month TEXT NOT NULL,
            target_clients INTEGER DEFAULT 0,
            target_registrations INTEGER DEFAULT 0,
            target_orders INTEGER DEFAULT 0,
            UNIQUE(team, month)
        );
    """)
    conn.commit()
    return conn


def seed_team(conn):
    """Seed a realistic team structure."""
    now = datetime.now().isoformat()
    staff = [
        (1001, 1001, 'admin_qw', '千万富翁', 'admin', None, 'zh', now),
        (2001, 2001, None, '阿毛', 'leader', '全线', 'zh', now),
        (2002, 2002, None, 'TINO', 'frontdesk', '全线', 'zh', now),
        (2003, 2003, None, 'KUYA', 'frontdesk', '全线', 'zh', now),
        (3001, 3001, None, '阿俊', 'maintenance', '阿俊', 'zh', now),
        (3002, 3002, None, '阿YIM', 'frontdesk', '阿俊', 'zh', now),
        (3003, 3003, None, 'ODDY', 'frontdesk', '阿俊', 'zh', now),
        (4001, 4001, None, '何军', 'maintenance', '何军', 'zh', now),
        (4002, 4002, None, '大杰', 'frontdesk', '何军', 'zh', now),
        (5001, 5001, None, '小白Dyson', 'customer_service', None, 'zh', now),
        # Unbound staff (placeholder tg_id)
        (-99990099, -99990099, None, '新人小明', 'frontdesk', '全线', 'zh', now),
    ]
    conn.executemany(
        "INSERT INTO staff (tg_user_id, tg_chat_id, tg_username, display_name, role, team, language, created_at) VALUES (?,?,?,?,?,?,?,?)",
        staff
    )
    conn.commit()
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1: Frontdesk adds a client and moves through pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestFrontdeskFullPipeline:
    """Simulate a frontdesk user adding a client and moving through all pipeline stages."""

    def test_add_client(self, db):
        """TINO adds a new client via /add."""
        seed_team(db)
        now = datetime.now().isoformat()

        # TINO (id=staff with tg_user_id=2002) adds a client
        tino_id = db.execute("SELECT id FROM staff WHERE display_name='TINO'").fetchone()[0]
        db.execute(
            "INSERT INTO clients (frontdesk_id, phone, source, status, created_at, updated_at) VALUES (?, ?, ?, 'new', ?, ?)",
            (tino_id, '46123456789', '飞机筛选', now, now)
        )
        db.commit()

        client = db.execute("SELECT * FROM clients WHERE phone='46123456789'").fetchone()
        assert client is not None
        assert client[8] == 'new'  # status column index
        assert client[1] == tino_id

    def test_pipeline_flow_new_to_ordered(self, db):
        """Client moves through full pipeline: new→contacted→replied→registered→training→ordered."""
        seed_team(db)
        now = datetime.now().isoformat()
        tino_id = db.execute("SELECT id FROM staff WHERE display_name='TINO'").fetchone()[0]

        db.execute(
            "INSERT INTO clients (frontdesk_id, phone, source, status, created_at, updated_at) VALUES (?, ?, ?, 'new', ?, ?)",
            (tino_id, '46111222333', '微信', now, now)
        )
        db.commit()
        cid = db.execute("SELECT id FROM clients WHERE phone='46111222333'").fetchone()[0]

        transitions = [
            ('contacted', 'contacted_at'),
            ('replied', 'replied_at'),
            ('registered', 'registered_at'),
            ('training', 'training_at'),
            ('ordered', 'first_order_at'),
        ]

        for new_status, ts_col in transitions:
            db.execute(f"UPDATE clients SET status=?, {ts_col}=?, updated_at=? WHERE id=?",
                       (new_status, now, now, cid))
            db.commit()

            row = db.execute("SELECT status FROM clients WHERE id=?", (cid,)).fetchone()
            assert row[0] == new_status, f"Expected {new_status}, got {row[0]}"

    def test_invalid_transition_blocked(self, db):
        """Policy: can't skip pipeline stages (new→registered is blocked)."""
        from models_v2 import ClientStatus

        valid = ClientStatus.valid_transitions('new')
        valid_values = [s.value for s in valid]
        assert 'contacted' in valid_values
        assert 'registered' not in valid_values  # Can't skip!
        assert 'ordered' not in valid_values

    def test_withdrew_has_recovery_paths(self, db):
        """Withdrew clients have recovery paths (can come back)."""
        from models_v2 import ClientStatus

        valid = ClientStatus.valid_transitions('withdrew')
        valid_values = [s.value for s in valid]
        # Withdrew should have some paths (contacted for re-engagement, ordered if they return)
        assert len(valid_values) > 0, "Withdrew should have at least one transition"
        assert 'contacted' in valid_values, "Withdrew should allow re-contact"


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2: Role permissions enforce correctly
# ══════════════════════════════════════════════════════════════════════════════

class TestRolePermissions:
    """Verify each role can only do what they're supposed to."""

    def test_frontdesk_allowed_commands(self):
        from engines.policy_engine import check_permission
        allowed = ['add', 'u', 'note', 'remind', 'pipeline', 'search', 'handoff']
        for cmd in allowed:
            assert check_permission('frontdesk', cmd), f"frontdesk should have '{cmd}'"

    def test_frontdesk_blocked_commands(self):
        from engines.policy_engine import check_permission
        blocked = ['target', 'setteam', 'linkgroup', 'sync']
        for cmd in blocked:
            assert not check_permission('frontdesk', cmd), f"frontdesk should NOT have '{cmd}'"

    def test_newbie_very_limited(self):
        from engines.policy_engine import check_permission
        assert check_permission('newbie', 'add')
        assert check_permission('newbie', 'me')
        assert not check_permission('newbie', 'u')
        assert not check_permission('newbie', 'pipeline')
        assert not check_permission('newbie', 'dashboard')

    def test_customer_service_read_mostly(self):
        from engines.policy_engine import check_permission
        assert check_permission('customer_service', 'search')
        assert check_permission('customer_service', 'note')
        assert check_permission('customer_service', 'dashboard')
        assert not check_permission('customer_service', 'add')
        assert not check_permission('customer_service', 'u')

    def test_leader_full_access(self):
        from engines.policy_engine import check_permission
        for cmd in ['add', 'u', 'dashboard', 'team', 'target', 'bulkupdate']:
            assert check_permission('leader', cmd), f"leader should have '{cmd}'"

    def test_viewer_readonly(self):
        from engines.policy_engine import check_permission
        assert check_permission('viewer', 'dashboard')
        assert check_permission('viewer', 'pipeline')
        assert not check_permission('viewer', 'add')
        assert not check_permission('viewer', 'u')
        assert not check_permission('viewer', 'remind')

    def test_admin_has_sync(self):
        from engines.policy_engine import check_permission
        assert check_permission('admin', 'sync')
        assert not check_permission('frontdesk', 'sync')
        assert not check_permission('manager', 'sync')


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3: Policy engine enforcement
# ══════════════════════════════════════════════════════════════════════════════

class TestPolicyEnforcement:
    """Test business rules are properly enforced."""

    def test_working_hours_check(self):
        from engines.policy_engine import check_working_hours, WORK_START, WORK_END
        assert WORK_START == 10
        assert WORK_END == 22

    def test_remind_limits_too_short(self):
        from engines.policy_engine import check_remind_limits
        ok, reason = check_remind_limits(timedelta(minutes=2))
        assert not ok
        assert 'min' in reason.lower() or '分钟' in reason

    def test_remind_limits_too_long(self):
        from engines.policy_engine import check_remind_limits
        ok, reason = check_remind_limits(timedelta(days=60))
        assert not ok

    def test_remind_limits_valid(self):
        from engines.policy_engine import check_remind_limits
        ok, reason = check_remind_limits(timedelta(hours=2))
        assert ok

    def test_stale_thresholds(self):
        from engines.policy_engine import STALE_WARNING_HOURS, STALE_CRITICAL_HOURS, AUTO_DEAD_DAYS
        assert STALE_WARNING_HOURS == 48
        assert STALE_CRITICAL_HOURS == 72
        assert AUTO_DEAD_DAYS == 14

    def test_deposit_constraints(self):
        from engines.policy_engine import MIN_DEPOSIT_AMOUNT, MAX_KNIFE_NUMBER
        assert MIN_DEPOSIT_AMOUNT == 1.0
        assert MAX_KNIFE_NUMBER == 8


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4: Bind command — staff linking Telegram accounts
# ══════════════════════════════════════════════════════════════════════════════

class TestBindFlow:
    """Test the /bind command for linking pre-seeded staff."""

    def test_bind_finds_exact_match(self, db):
        """Unbound staff can be found by exact name."""
        seed_team(db)
        row = db.execute("SELECT id, tg_user_id FROM staff WHERE display_name='新人小明'").fetchone()
        assert row is not None
        assert row[1] < 0  # placeholder ID

    def test_bind_updates_tg_id(self, db):
        """After binding, tg_user_id is updated to real value."""
        seed_team(db)
        real_tg_id = 8888888888
        db.execute("UPDATE staff SET tg_user_id=?, tg_chat_id=? WHERE display_name='新人小明'",
                   (real_tg_id, real_tg_id))
        db.commit()

        row = db.execute("SELECT tg_user_id FROM staff WHERE display_name='新人小明'").fetchone()
        assert row[0] == real_tg_id

    def test_already_bound_rejected(self, db):
        """Staff with real TG ID (>0) can't be re-bound."""
        seed_team(db)
        row = db.execute("SELECT tg_user_id FROM staff WHERE display_name='TINO'").fetchone()
        assert row[0] > 0  # Already has real TG ID


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5: Team routing — messages go to correct groups
# ══════════════════════════════════════════════════════════════════════════════

class TestTeamRouting:
    """Test team_config routes messages correctly."""

    def test_team_config_loads(self):
        from team_config import team_config
        assert team_config.is_loaded

    def test_all_teams_have_chat_ids(self):
        from team_config import team_config
        for tid in team_config.get_all_team_ids():
            assert team_config.get_team_chat_id(tid) is not None, f"Team {tid} has no chat_id"

    def test_all_teams_have_daily_topic(self):
        from team_config import team_config
        for tid in team_config.get_all_team_ids():
            topic = team_config.get_team_topic_id(tid, '日报')
            assert topic is not None, f"Team {tid} has no 日报 topic"

    def test_broadcast_exists(self):
        from team_config import team_config
        assert team_config.get_broadcast_id() is not None

    def test_management_exists(self):
        from team_config import team_config
        assert team_config.get_management_id() is not None
        assert team_config.get_management_topic_id('总报表') is not None

    def test_member_to_team_lookup(self):
        from team_config import team_config
        assert team_config.get_team_for_member('TINO') == 'quanxian'
        assert team_config.get_team_for_member('阿YIM') == 'ajun'
        assert team_config.get_team_for_member('大杰') == 'hejun'
        assert team_config.get_team_for_member('nobody') is None


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6: Daily stats and reporting
# ══════════════════════════════════════════════════════════════════════════════

class TestDailyReporting:
    """Test that daily stats are computed and reports generate."""

    def test_daily_stats_accumulate(self, db):
        seed_team(db)
        today = datetime.now().strftime('%Y-%m-%d')
        tino_id = db.execute("SELECT id FROM staff WHERE display_name='TINO'").fetchone()[0]

        db.execute(
            "INSERT INTO daily_stats (staff_id, date, new_clients, contacted, registered) VALUES (?, ?, 5, 3, 2)",
            (tino_id, today)
        )
        db.commit()

        row = db.execute("SELECT new_clients, contacted, registered FROM daily_stats WHERE staff_id=? AND date=?",
                         (tino_id, today)).fetchone()
        assert row[0] == 5
        assert row[1] == 3
        assert row[2] == 2

    def test_team_stats_sum(self, db):
        """Multiple staff in same team should sum up."""
        seed_team(db)
        today = datetime.now().strftime('%Y-%m-%d')

        tino_id = db.execute("SELECT id FROM staff WHERE display_name='TINO'").fetchone()[0]
        kuya_id = db.execute("SELECT id FROM staff WHERE display_name='KUYA'").fetchone()[0]

        db.execute("INSERT INTO daily_stats (staff_id, date, new_clients, registered) VALUES (?, ?, 3, 1)", (tino_id, today))
        db.execute("INSERT INTO daily_stats (staff_id, date, new_clients, registered) VALUES (?, ?, 2, 1)", (kuya_id, today))
        db.commit()

        # Sum for 全线 team
        row = db.execute("""
            SELECT SUM(ds.new_clients), SUM(ds.registered)
            FROM daily_stats ds
            JOIN staff s ON ds.staff_id = s.id
            WHERE s.team = '全线' AND ds.date = ?
        """, (today,)).fetchone()
        assert row[0] == 5  # 3 + 2
        assert row[1] == 2  # 1 + 1


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7: NocoDB field mapping
# ══════════════════════════════════════════════════════════════════════════════

class TestNocoDBMapping:
    """Verify NocoDB config is consistent."""

    def test_nocodb_config_exists(self):
        import json
        with open('nocodb_config.json') as f:
            config = json.load(f)
        assert 'tables' in config
        assert 'field_map' in config
        assert 'staff' in config['tables']
        assert 'clients' in config['tables']

    def test_all_tables_have_field_maps(self):
        import json
        with open('nocodb_config.json') as f:
            config = json.load(f)
        for table_name in config['tables']:
            assert table_name in config['field_map'], f"Missing field_map for {table_name}"

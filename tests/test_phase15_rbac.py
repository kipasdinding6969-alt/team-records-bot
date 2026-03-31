"""Phase 15 RBAC tests — dashboard_users table, 3-tier auth, data scoping."""
import os
import sqlite3
import sys
import tempfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

# Env vars must be set before importing the app
TEST_JWT_SECRET = 'test-rbac-jwt-secret-2026'
TEST_OWNER_USER = 'rbac_owner'
TEST_OWNER_PASS = 'ownerpass123'
os.environ['JWT_SECRET'] = TEST_JWT_SECRET
os.environ['DASHBOARD_USER'] = TEST_OWNER_USER
os.environ['DASHBOARD_PASS'] = TEST_OWNER_PASS


# ─── DB fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture(scope='module', autouse=True)
def setup_schema(temp_db_path):
    """Seed DB with staff + clients for two teams."""
    today = date.today().isoformat()
    today_ts = f'{today}T08:00:00'

    conn = sqlite3.connect(temp_db_path)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT DEFAULT 'frontdesk',
            team TEXT,
            is_active INTEGER DEFAULT 1,
            daily_target INTEGER DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            source TEXT,
            nickname TEXT,
            frontdesk_id INTEGER REFERENCES staff(id),
            total_deposited REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            contacted_at TEXT,
            replied_at TEXT,
            registered_at TEXT,
            training_at TEXT,
            first_order_at TEXT,
            next_followup TEXT
        );
        CREATE TABLE IF NOT EXISTS client_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL REFERENCES clients(id),
            staff_id INTEGER REFERENCES staff(id),
            note_type TEXT DEFAULT 'update',
            old_status TEXT,
            new_status TEXT,
            content TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL REFERENCES clients(id),
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
    ''')

    # Staff: team Alpha (staff_id=1) and team Beta (staff_id=2)
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (1001, '阿强', 'frontdesk', 'Alpha')")
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (1002, '阿美', 'frontdesk', 'Beta')")

    # Clients for team Alpha (frontdesk_id=1)
    conn.execute(f"INSERT INTO clients (phone, status, frontdesk_id, created_at) VALUES ('111', 'new', 1, '{today_ts}')")
    conn.execute(f"INSERT INTO clients (phone, status, frontdesk_id, created_at) VALUES ('112', 'ordered', 1, '{today_ts}')")
    # Clients for team Beta (frontdesk_id=2)
    conn.execute(f"INSERT INTO clients (phone, status, frontdesk_id, created_at) VALUES ('221', 'new', 2, '{today_ts}')")

    conn.commit()
    conn.close()


@pytest.fixture(scope='module')
def app_client(temp_db_path, setup_schema):
    os.environ['DB_PATH'] = temp_db_path
    # Restore our own credentials before reimporting (isolation from other test files)
    os.environ['DASHBOARD_USER'] = TEST_OWNER_USER
    os.environ['DASHBOARD_PASS'] = TEST_OWNER_PASS
    os.environ['JWT_SECRET'] = TEST_JWT_SECRET
    if 'web_dashboard_api' in sys.modules:
        del sys.modules['web_dashboard_api']
    import web_dashboard_api
    with TestClient(web_dashboard_api.app) as c:
        yield c


# ─── Helper: login and get headers ────────────────────────────────────────────

def login_as(client, username: str, password: str) -> dict:
    res = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert res.status_code == 200, f'Login failed for {username}: {res.text}'
    token = res.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


# ─── 1. Table creation and auto-migration ─────────────────────────────────────

class TestMigration:
    def test_owner_auto_created_from_env(self, app_client):
        """On startup with empty table + env vars, owner account is auto-created."""
        res = app_client.post('/api/auth/login', json={
            'username': TEST_OWNER_USER, 'password': TEST_OWNER_PASS
        })
        assert res.status_code == 200
        data = res.json()
        assert data['role'] == 'owner'
        assert data['team_scope'] is None
        assert data['username'] == TEST_OWNER_USER

    def test_login_response_includes_role_info(self, app_client):
        res = app_client.post('/api/auth/login', json={
            'username': TEST_OWNER_USER, 'password': TEST_OWNER_PASS
        })
        assert res.status_code == 200
        data = res.json()
        assert 'role' in data
        assert 'team_scope' in data
        assert 'display_name' in data
        assert 'user_id' in data

    def test_jwt_contains_role(self, app_client):
        """JWT payload must carry role and team_scope."""
        import base64, json
        res = app_client.post('/api/auth/login', json={
            'username': TEST_OWNER_USER, 'password': TEST_OWNER_PASS
        })
        token = res.json()['access_token']
        payload_b64 = token.split('.')[1]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        payload = json.loads(base64.b64decode(payload_b64))
        assert 'role' in payload
        assert 'team_scope' in payload
        assert 'user_id' in payload
        assert payload['role'] == 'owner'


# ─── 2. Setup endpoint ────────────────────────────────────────────────────────

class TestSetupEndpoint:
    def test_setup_blocked_when_users_exist(self, app_client):
        """Setup endpoint must fail once owner already exists."""
        res = app_client.post('/api/auth/setup', json={
            'username': 'another_owner', 'password': 'pass123', 'display_name': 'Test'
        })
        assert res.status_code == 400


# ─── 3. Verify endpoint ───────────────────────────────────────────────────────

class TestVerify:
    def test_verify_returns_full_auth_info(self, app_client):
        headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = app_client.get('/api/auth/verify', headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data['ok'] is True
        assert data['username'] == TEST_OWNER_USER
        assert data['role'] == 'owner'
        assert 'team_scope' in data
        assert 'display_name' in data


# ─── 4. User CRUD — owner capabilities ───────────────────────────────────────

class TestOwnerUserCRUD:
    @pytest.fixture(scope='class')
    def owner_headers(self, app_client):
        return login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)

    def test_owner_can_create_admin(self, app_client, owner_headers):
        res = app_client.post('/api/users', json={
            'username': 'admin_alpha', 'password': 'adminpass1',
            'display_name': 'Alpha管理员', 'role': 'admin', 'team_scope': 'Alpha'
        }, headers=owner_headers)
        assert res.status_code == 201
        assert res.json()['ok'] is True

    def test_owner_can_create_member(self, app_client, owner_headers):
        res = app_client.post('/api/users', json={
            'username': 'member_alpha', 'password': 'memberpass1',
            'display_name': 'Alpha成员', 'role': 'member', 'team_scope': 'Alpha',
            'staff_id': 1
        }, headers=owner_headers)
        assert res.status_code == 201

    def test_owner_can_create_beta_admin(self, app_client, owner_headers):
        res = app_client.post('/api/users', json={
            'username': 'admin_beta', 'password': 'adminpass2',
            'display_name': 'Beta管理员', 'role': 'admin', 'team_scope': 'Beta'
        }, headers=owner_headers)
        assert res.status_code == 201

    def test_owner_can_create_beta_member(self, app_client, owner_headers):
        res = app_client.post('/api/users', json={
            'username': 'member_beta', 'password': 'memberpass2',
            'display_name': 'Beta成员', 'role': 'member', 'team_scope': 'Beta',
            'staff_id': 2
        }, headers=owner_headers)
        assert res.status_code == 201

    def test_owner_lists_all_users(self, app_client, owner_headers):
        res = app_client.get('/api/users', headers=owner_headers)
        assert res.status_code == 200
        users = res.json()
        usernames = [u['username'] for u in users]
        assert TEST_OWNER_USER in usernames
        assert 'admin_alpha' in usernames
        assert 'member_alpha' in usernames
        assert 'admin_beta' in usernames

    def test_duplicate_username_rejected(self, app_client, owner_headers):
        res = app_client.post('/api/users', json={
            'username': 'admin_alpha', 'password': 'pass123',
            'display_name': 'Dup', 'role': 'member'
        }, headers=owner_headers)
        assert res.status_code == 409

    def test_invalid_role_rejected(self, app_client, owner_headers):
        res = app_client.post('/api/users', json={
            'username': 'bad_role', 'password': 'pass123',
            'display_name': 'Bad', 'role': 'superuser'
        }, headers=owner_headers)
        assert res.status_code == 400

    def test_owner_can_update_user(self, app_client, owner_headers):
        # Get user list to find member_alpha id
        users = app_client.get('/api/users', headers=owner_headers).json()
        member = next(u for u in users if u['username'] == 'member_alpha')
        res = app_client.put(f'/api/users/{member["id"]}', json={
            'display_name': 'Alpha成员-更新'
        }, headers=owner_headers)
        assert res.status_code == 200

    def test_owner_reset_password(self, app_client, owner_headers):
        users = app_client.get('/api/users', headers=owner_headers).json()
        member = next(u for u in users if u['username'] == 'member_alpha')
        res = app_client.post(f'/api/users/{member["id"]}/reset-password', json={
            'new_password': 'newpass456'
        }, headers=owner_headers)
        assert res.status_code == 200
        # Verify can login with new password
        res2 = app_client.post('/api/auth/login', json={
            'username': 'member_alpha', 'password': 'newpass456'
        })
        assert res2.status_code == 200


# ─── 5. Admin RBAC constraints ────────────────────────────────────────────────

class TestAdminRBAC:
    @pytest.fixture(scope='class')
    def admin_alpha_headers(self, app_client):
        return login_as(app_client, 'admin_alpha', 'adminpass1')

    def test_admin_cannot_create_admin(self, app_client, admin_alpha_headers):
        res = app_client.post('/api/users', json={
            'username': 'another_admin', 'password': 'pass123',
            'display_name': 'Another', 'role': 'admin', 'team_scope': 'Alpha'
        }, headers=admin_alpha_headers)
        assert res.status_code == 403

    def test_admin_cannot_create_owner(self, app_client, admin_alpha_headers):
        res = app_client.post('/api/users', json={
            'username': 'new_owner', 'password': 'pass123',
            'display_name': 'New Owner', 'role': 'owner'
        }, headers=admin_alpha_headers)
        assert res.status_code == 403

    def test_admin_cannot_create_member_in_other_team(self, app_client, admin_alpha_headers):
        res = app_client.post('/api/users', json={
            'username': 'beta_member2', 'password': 'pass123',
            'display_name': 'Beta Member', 'role': 'member', 'team_scope': 'Beta'
        }, headers=admin_alpha_headers)
        assert res.status_code == 403

    def test_admin_can_create_member_in_own_team(self, app_client, admin_alpha_headers):
        res = app_client.post('/api/users', json={
            'username': 'alpha_extra', 'password': 'pass123',
            'display_name': 'Alpha Extra', 'role': 'member', 'team_scope': 'Alpha'
        }, headers=admin_alpha_headers)
        assert res.status_code == 201

    def test_admin_lists_only_own_team(self, app_client, admin_alpha_headers):
        res = app_client.get('/api/users', headers=admin_alpha_headers)
        assert res.status_code == 200
        users = res.json()
        # Should only see Alpha team users
        for u in users:
            assert u['team_scope'] == 'Alpha', f"Admin sees user from other team: {u}"

    def test_admin_cannot_edit_other_team_member(self, app_client, admin_alpha_headers):
        owner_headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        users = app_client.get('/api/users', headers=owner_headers).json()
        beta_member = next(u for u in users if u['username'] == 'member_beta')
        res = app_client.put(f'/api/users/{beta_member["id"]}', json={
            'display_name': 'Hacked'
        }, headers=admin_alpha_headers)
        assert res.status_code == 403

    def test_admin_cannot_deactivate_other_team_member(self, app_client, admin_alpha_headers):
        owner_headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        users = app_client.get('/api/users', headers=owner_headers).json()
        beta_member = next(u for u in users if u['username'] == 'member_beta')
        res = app_client.delete(f'/api/users/{beta_member["id"]}', headers=admin_alpha_headers)
        assert res.status_code == 403

    def test_admin_deactivate_own_team_member(self, app_client, admin_alpha_headers):
        # Get alpha_extra id
        users = app_client.get('/api/users', headers=admin_alpha_headers).json()
        extra = next((u for u in users if u['username'] == 'alpha_extra'), None)
        if extra:
            res = app_client.delete(f'/api/users/{extra["id"]}', headers=admin_alpha_headers)
            assert res.status_code == 200

    def test_admin_reset_own_team_member_password(self, app_client, admin_alpha_headers):
        users = app_client.get('/api/users', headers=admin_alpha_headers).json()
        member = next(u for u in users if u['username'] == 'member_alpha')
        res = app_client.post(f'/api/users/{member["id"]}/reset-password', json={
            'new_password': 'resetbyAdmin123'
        }, headers=admin_alpha_headers)
        assert res.status_code == 200


# ─── 6. Member RBAC constraints ───────────────────────────────────────────────

class TestMemberRBAC:
    @pytest.fixture(scope='class')
    def member_beta_headers(self, app_client):
        return login_as(app_client, 'member_beta', 'memberpass2')

    def test_member_cannot_list_users(self, app_client, member_beta_headers):
        res = app_client.get('/api/users', headers=member_beta_headers)
        assert res.status_code == 403

    def test_member_cannot_create_user(self, app_client, member_beta_headers):
        res = app_client.post('/api/users', json={
            'username': 'new_user', 'password': 'pass123',
            'display_name': 'New', 'role': 'member'
        }, headers=member_beta_headers)
        assert res.status_code == 403

    def test_member_cannot_delete_user(self, app_client, member_beta_headers):
        res = app_client.delete('/api/users/1', headers=member_beta_headers)
        assert res.status_code == 403

    def test_member_can_change_own_password(self, app_client, member_beta_headers):
        res = app_client.post('/api/auth/change-password', json={
            'current_password': 'memberpass2',
            'new_password': 'newbetapass123'
        }, headers=member_beta_headers)
        assert res.status_code == 200

    def test_member_cannot_change_password_wrong_current(self, app_client):
        headers = login_as(app_client, 'member_beta', 'newbetapass123')
        res = app_client.post('/api/auth/change-password', json={
            'current_password': 'wrongpass',
            'new_password': 'something123'
        }, headers=headers)
        assert res.status_code == 401


# ─── 7. Deactivation prevents login ──────────────────────────────────────────

class TestDeactivation:
    def test_deactivated_user_cannot_login(self, app_client):
        # Create + deactivate a user
        owner_headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        app_client.post('/api/users', json={
            'username': 'deactivate_me', 'password': 'pass123',
            'display_name': 'Temp', 'role': 'member'
        }, headers=owner_headers)
        # Find the user
        users = app_client.get('/api/users', headers=owner_headers).json()
        target = next(u for u in users if u['username'] == 'deactivate_me')
        # Deactivate
        app_client.delete(f'/api/users/{target["id"]}', headers=owner_headers)
        # Try to login
        res = app_client.post('/api/auth/login', json={
            'username': 'deactivate_me', 'password': 'pass123'
        })
        assert res.status_code == 401

    def test_cannot_deactivate_self(self, app_client):
        owner_headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        users = app_client.get('/api/users', headers=owner_headers).json()
        owner = next(u for u in users if u['username'] == TEST_OWNER_USER)
        res = app_client.delete(f'/api/users/{owner["id"]}', headers=owner_headers)
        assert res.status_code == 400


# ─── 8. Data scoping ──────────────────────────────────────────────────────────

class TestDataScoping:
    def test_owner_sees_all_clients(self, app_client):
        headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = app_client.get('/api/clients', headers=headers)
        assert res.status_code == 200
        total = res.json()['total']
        assert total >= 3, f'Owner should see all 3+ clients, got {total}'

    def test_admin_sees_only_team_clients(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/clients', headers=headers)
        assert res.status_code == 200
        clients = res.json()['clients']
        for c in clients:
            assert c['team'] == 'Alpha', f"Admin sees non-Alpha client: {c}"

    def test_member_sees_only_own_clients(self, app_client):
        headers = login_as(app_client, 'member_beta', 'newbetapass123')
        res = app_client.get('/api/clients', headers=headers)
        assert res.status_code == 200
        clients = res.json()['clients']
        # member_beta has staff_id=2
        for c in clients:
            assert c['frontdesk_name'] == '阿美', f"Member sees other's client: {c}"

    def test_admin_dashboard_scoped(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/dashboard', headers=headers)
        assert res.status_code == 200
        data = res.json()
        # Alpha has 2 clients
        assert data['total_clients'] == 2

    def test_owner_dashboard_sees_all(self, app_client):
        headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = app_client.get('/api/dashboard', headers=headers)
        assert res.status_code == 200
        assert res.json()['total_clients'] >= 3

    def test_admin_funnel_scoped(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/funnel', headers=headers)
        assert res.status_code == 200
        stages = {s['stage']: s['count'] for s in res.json()}
        # Alpha has 1 new + 1 ordered = 2 total, not 3
        total_in_funnel = sum(stages.values())
        assert total_in_funnel <= 2

    def test_admin_staff_scoped(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/staff', headers=headers)
        assert res.status_code == 200
        staff = res.json()
        for s in staff:
            assert s['team'] == 'Alpha', f"Admin sees non-Alpha staff: {s}"

    def test_admin_blocked_from_other_team_performance(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/team/Beta/performance', headers=headers)
        assert res.status_code == 403

    def test_admin_can_access_own_team_performance(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/team/Alpha/performance', headers=headers)
        assert res.status_code == 200

    def test_admin_client_detail_blocked_for_other_team(self, app_client):
        # Client ID 3 belongs to Beta (frontdesk_id=2)
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/clients/3', headers=headers)
        assert res.status_code == 403

    def test_admin_client_detail_allowed_for_own_team(self, app_client):
        # Client ID 1 belongs to Alpha (frontdesk_id=1)
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/clients/1', headers=headers)
        assert res.status_code == 200


# ─── 9. Auth edge cases ───────────────────────────────────────────────────────

class TestAuthEdgeCases:
    def test_wrong_password_returns_401(self, app_client):
        res = app_client.post('/api/auth/login', json={
            'username': TEST_OWNER_USER, 'password': 'wrongpassword'
        })
        assert res.status_code == 401

    def test_nonexistent_user_returns_401(self, app_client):
        res = app_client.post('/api/auth/login', json={
            'username': 'ghost', 'password': 'pass123'
        })
        assert res.status_code == 401

    def test_no_token_returns_401(self, app_client):
        res = app_client.get('/api/dashboard')
        assert res.status_code == 401

    def test_invalid_token_returns_401(self, app_client):
        res = app_client.get('/api/dashboard', headers={'Authorization': 'Bearer bad.token'})
        assert res.status_code == 401

    def test_remember_me_login(self, app_client):
        """remember_me flag should still produce valid token."""
        res = app_client.post('/api/auth/login', json={
            'username': TEST_OWNER_USER,
            'password': TEST_OWNER_PASS,
            'remember_me': True
        })
        assert res.status_code == 200
        token = res.json()['access_token']
        # Verify the token works
        res2 = app_client.get('/api/auth/verify', headers={'Authorization': f'Bearer {token}'})
        assert res2.status_code == 200
        assert res2.json()['ok'] is True

    def test_password_too_short_rejected(self, app_client):
        owner_headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = app_client.post('/api/users', json={
            'username': 'shortpwd', 'password': '123',
            'display_name': 'Short', 'role': 'member'
        }, headers=owner_headers)
        assert res.status_code == 400

    def test_unauthenticated_user_management_returns_401(self, app_client):
        res = app_client.get('/api/users')
        assert res.status_code == 401

    def test_health_endpoint_unauthenticated(self, app_client):
        res = app_client.get('/health')
        assert res.status_code == 200
        assert res.json()['status'] == 'ok'


# ─── 10. Export scoping ───────────────────────────────────────────────────────

class TestExportScoping:
    def test_owner_export_clients(self, app_client):
        headers = login_as(app_client, TEST_OWNER_USER, TEST_OWNER_PASS)
        res = app_client.get('/api/export/clients', headers=headers)
        assert res.status_code == 200
        assert 'text/csv' in res.headers['content-type']

    def test_admin_export_scoped_csv(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/export/clients', headers=headers)
        assert res.status_code == 200
        content = res.text
        # Should not contain Beta's phone numbers
        assert '221' not in content

    def test_export_report_daily_scoped(self, app_client):
        headers = login_as(app_client, 'admin_alpha', 'adminpass1')
        res = app_client.get('/api/export/report?period=daily', headers=headers)
        assert res.status_code == 200

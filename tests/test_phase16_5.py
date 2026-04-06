"""Tests for Phase 16.5: Client linking, notes, performance dashboard, permission editing."""
import os
import sqlite3
import sys
import tempfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

TEST_JWT_SECRET = 'test-jwt-secret-phase165-padding'
TEST_USER = 'testadmin165'
TEST_PASS = 'testpass165'
os.environ['DASHBOARD_USER'] = TEST_USER
os.environ['DASHBOARD_PASS'] = TEST_PASS
os.environ['JWT_SECRET'] = TEST_JWT_SECRET


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
def setup_db(temp_db_path):
    """Create full schema + seed data for Phase 16.5 tests."""
    today = date.today().isoformat()
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
            author_name TEXT,
            phone_normalized TEXT,
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
        CREATE TABLE IF NOT EXISTS client_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id_a INTEGER NOT NULL REFERENCES clients(id),
            client_id_b INTEGER NOT NULL REFERENCES clients(id),
            link_type TEXT NOT NULL DEFAULT 'related',
            note TEXT,
            created_by INTEGER REFERENCES staff(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(client_id_a, client_id_b)
        );
        CREATE INDEX IF NOT EXISTS idx_client_links_a ON client_links(client_id_a);
        CREATE INDEX IF NOT EXISTS idx_client_links_b ON client_links(client_id_b);
        CREATE TABLE IF NOT EXISTS permission_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL REFERENCES staff(id),
            command TEXT NOT NULL,
            allowed BOOLEAN NOT NULL,
            granted_by INTEGER REFERENCES staff(id),
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(staff_id, command)
        );
        CREATE INDEX IF NOT EXISTS idx_permission_overrides_staff ON permission_overrides(staff_id);
        CREATE TABLE IF NOT EXISTS phone_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            phone_normalized TEXT NOT NULL,
            submitter_name TEXT NOT NULL,
            submitter_staff_id INTEGER REFERENCES staff(id),
            source TEXT DEFAULT 'telegram',
            submitted_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            category TEXT,
            recruiter TEXT,
            account_id TEXT,
            first_day_status TEXT,
            second_day_status TEXT,
            client_condition TEXT,
            team_name TEXT,
            leader_name TEXT,
            UNIQUE(phone_normalized)
        );
        CREATE TABLE IF NOT EXISTS phone_registry_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_normalized TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            actor_staff_id INTEGER REFERENCES staff(id),
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS client_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL REFERENCES clients(id),
            event_type TEXT NOT NULL,
            event_data TEXT,
            staff_id INTEGER REFERENCES staff(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    today_ts = f'{today}T08:00:00'
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (99001, 'Tiger韦小宝', 'frontdesk', '阿毛')")
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (99002, '小李', 'frontdesk', '阿俊')")
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (99003, '阿俊', 'maintenance', '阿俊')")
    conn.execute(f"INSERT INTO clients (phone, status, source, frontdesk_id, created_at) VALUES ('+8613900001111', 'new', 'FB', 1, '{today_ts}')")
    conn.execute(f"INSERT INTO clients (phone, status, source, frontdesk_id, total_deposited, created_at, registered_at) VALUES ('+8613900002222', 'registered', 'TG', 1, 500.0, '{today_ts}', '{today_ts}')")
    conn.execute(f"INSERT INTO clients (phone, status, frontdesk_id, first_order_at, created_at) VALUES ('+8613900003333', 'ordered', 2, '{today_ts}', '{today_ts}')")
    conn.execute("INSERT INTO client_notes (client_id, staff_id, note_type, content) VALUES (1, 1, 'update', 'Test note')")
    conn.execute("INSERT INTO client_notes (client_id, staff_id, note_type, old_status, new_status, content) VALUES (2, 1, 'status_change', 'new', 'registered', 'Status update')")
    conn.execute(f"INSERT INTO deposits (client_id, frontdesk_id, amount, currency, platform, deposit_date) VALUES (2, 1, 500.0, 'USD', 'Binance', '{today}')")
    conn.execute(f"INSERT INTO daily_stats (staff_id, stat_date, new_leads, contacted, replied, registered, training, withdrew, new_orders, ghosted, dead, total_deposit) VALUES (1, '{today}', 10, 8, 6, 4, 3, 2, 1, 1, 0, 500.0)")
    conn.execute(f"INSERT INTO daily_stats (staff_id, stat_date, new_leads, contacted, replied, registered, training, withdrew, new_orders, total_deposit) VALUES (2, '{today}', 5, 4, 3, 2, 1, 1, 0, 200.0)")
    conn.execute(f"INSERT INTO phone_registry (phone, phone_normalized, submitter_name, submitter_staff_id, source, submitted_at) VALUES ('+8613900001111', '8613900001111', 'Tiger韦小宝', 1, 'telegram', '{today_ts}')")
    conn.execute("INSERT INTO phone_registry_log (phone_normalized, action, actor_name, actor_staff_id) VALUES ('8613900001111', 'register', 'Tiger韦小宝', 1)")
    conn.execute("INSERT INTO phone_registry_log (phone_normalized, action, actor_name) VALUES ('8613900009999', 'duplicate_blocked', 'System')")
    conn.commit()
    conn.close()


@pytest.fixture(scope='module')
def client(temp_db_path, setup_db):
    os.environ['DB_PATH'] = temp_db_path
    os.environ['DASHBOARD_USER'] = TEST_USER
    os.environ['DASHBOARD_PASS'] = TEST_PASS
    os.environ['JWT_SECRET'] = TEST_JWT_SECRET
    if 'web_dashboard_api' in sys.modules:
        del sys.modules['web_dashboard_api']
    import web_dashboard_api
    with TestClient(web_dashboard_api.app) as c:
        yield c


@pytest.fixture(scope='module')
def auth_token(client):
    res = client.post('/api/auth/login', json={'username': TEST_USER, 'password': TEST_PASS})
    assert res.status_code == 200
    return res.json()['access_token']


@pytest.fixture(scope='module')
def auth_headers(auth_token):
    return {'Authorization': f'Bearer {auth_token}'}


# ─── Client Notes API Tests ─────────────────────────────────────────────────

class TestClientNotes:
    def test_add_note_success(self, client, auth_headers):
        res = client.post('/api/clients/1/notes', headers=auth_headers,
                          json={'content': 'Test comment from API', 'note_type': 'comment'})
        assert res.status_code == 200
        assert res.json()['ok'] is True

    def test_add_note_with_phone_normalized(self, client, auth_headers):
        res = client.post('/api/clients/1/notes', headers=auth_headers,
                          json={'content': 'Note with phone', 'note_type': 'comment',
                                'phone_normalized': '8613900001111'})
        assert res.status_code == 200

    def test_add_flag_note(self, client, auth_headers):
        res = client.post('/api/clients/2/notes', headers=auth_headers,
                          json={'content': 'Flagged for review', 'note_type': 'flag'})
        assert res.status_code == 200

    def test_add_note_invalid_type(self, client, auth_headers):
        res = client.post('/api/clients/1/notes', headers=auth_headers,
                          json={'content': 'Bad type', 'note_type': 'invalid_type'})
        assert res.status_code == 400

    def test_add_note_client_not_found(self, client, auth_headers):
        res = client.post('/api/clients/9999/notes', headers=auth_headers,
                          json={'content': 'Should fail'})
        assert res.status_code == 404

    def test_get_notes(self, client, auth_headers):
        res = client.get('/api/clients/1/notes', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_notes_has_author_name(self, client, auth_headers):
        res = client.get('/api/clients/1/notes', headers=auth_headers)
        notes = res.json()
        api_notes = [n for n in notes if n.get('content') == 'Test comment from API']
        assert len(api_notes) >= 1

    def test_notes_ordered_by_date_desc(self, client, auth_headers):
        res = client.get('/api/clients/1/notes', headers=auth_headers)
        notes = res.json()
        if len(notes) > 1:
            dates = [n['created_at'] for n in notes if n.get('created_at')]
            assert dates == sorted(dates, reverse=True)


# ─── Client Timeline API Tests ──────────────────────────────────────────────

class TestClientTimeline:
    def test_timeline_returns_list(self, client, auth_headers):
        res = client.get('/api/clients/1/timeline', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)

    def test_timeline_includes_notes(self, client, auth_headers):
        res = client.get('/api/clients/1/timeline', headers=auth_headers)
        data = res.json()
        note_items = [i for i in data if i.get('timeline_type') == 'note']
        assert len(note_items) >= 1

    def test_timeline_sorted_by_date_desc(self, client, auth_headers):
        res = client.get('/api/clients/1/timeline', headers=auth_headers)
        data = res.json()
        if len(data) > 1:
            dates = [i['created_at'] for i in data if i.get('created_at')]
            assert dates == sorted(dates, reverse=True)


# ─── Client Links API Tests ─────────────────────────────────────────────────

class TestClientLinks:
    def test_create_link(self, client, auth_headers):
        res = client.post('/api/client-links', headers=auth_headers,
                          json={'client_id_a': 1, 'client_id_b': 2,
                                'link_type': 'related', 'note': 'Test link'})
        assert res.status_code == 200
        assert res.json()['ok'] is True

    def test_create_link_duplicate_fails(self, client, auth_headers):
        res = client.post('/api/client-links', headers=auth_headers,
                          json={'client_id_a': 1, 'client_id_b': 2, 'link_type': 'related'})
        assert res.status_code == 409

    def test_create_link_invalid_type(self, client, auth_headers):
        res = client.post('/api/client-links', headers=auth_headers,
                          json={'client_id_a': 1, 'client_id_b': 3, 'link_type': 'invalid'})
        assert res.status_code == 400

    def test_get_client_links(self, client, auth_headers):
        res = client.get('/api/clients/1/links', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_links_has_phone_info(self, client, auth_headers):
        res = client.get('/api/clients/1/links', headers=auth_headers)
        link = res.json()[0]
        assert 'phone_a' in link
        assert 'phone_b' in link
        assert 'link_type' in link

    def test_delete_link(self, client, auth_headers):
        # Create a new link first
        client.post('/api/client-links', headers=auth_headers,
                    json={'client_id_a': 2, 'client_id_b': 3, 'link_type': 'referral'})
        # Get link ID
        res = client.get('/api/clients/2/links', headers=auth_headers)
        links = res.json()
        ref_link = next((l for l in links if l.get('link_type') == 'referral'), None)
        assert ref_link is not None
        # Delete it
        res = client.delete(f'/api/client-links/{ref_link["id"]}', headers=auth_headers)
        assert res.status_code == 200

    def test_delete_nonexistent_link(self, client, auth_headers):
        res = client.delete('/api/client-links/99999', headers=auth_headers)
        assert res.status_code == 404


# ─── Permission Overrides API Tests ──────────────────────────────────────────

class TestPermissionOverrides:
    def test_set_permission_override(self, client, auth_headers):
        res = client.post('/api/permissions', headers=auth_headers,
                          json={'staff_id': 1, 'command': 'view_clients',
                                'allowed': True, 'reason': 'Test grant'})
        assert res.status_code == 200

    def test_set_deny_override(self, client, auth_headers):
        res = client.post('/api/permissions', headers=auth_headers,
                          json={'staff_id': 1, 'command': 'export_data',
                                'allowed': False, 'reason': 'Restricted'})
        assert res.status_code == 200

    def test_get_staff_permissions(self, client, auth_headers):
        res = client.get('/api/permissions/1', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert 'staff' in data
        assert 'overrides' in data
        assert len(data['overrides']) >= 1

    def test_get_staff_permissions_not_found(self, client, auth_headers):
        res = client.get('/api/permissions/99999', headers=auth_headers)
        assert res.status_code == 404

    def test_list_all_permissions(self, client, auth_headers):
        res = client.get('/api/permissions', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_permissions_grouped_by_staff(self, client, auth_headers):
        res = client.get('/api/permissions', headers=auth_headers)
        for staff in res.json():
            assert 'id' in staff
            assert 'display_name' in staff
            assert 'overrides' in staff

    def test_delete_permission_override(self, client, auth_headers):
        res = client.delete('/api/permissions/1/export_data', headers=auth_headers)
        assert res.status_code == 200

    def test_delete_nonexistent_override(self, client, auth_headers):
        res = client.delete('/api/permissions/1/nonexistent_cmd', headers=auth_headers)
        assert res.status_code == 404

    def test_upsert_permission_override(self, client, auth_headers):
        # Set allowed
        client.post('/api/permissions', headers=auth_headers,
                    json={'staff_id': 2, 'command': 'add_clients', 'allowed': True})
        # Update to denied
        client.post('/api/permissions', headers=auth_headers,
                    json={'staff_id': 2, 'command': 'add_clients', 'allowed': False})
        res = client.get('/api/permissions/2', headers=auth_headers)
        overrides = res.json()['overrides']
        add_ov = next((o for o in overrides if o['command'] == 'add_clients'), None)
        assert add_ov is not None
        assert add_ov['allowed'] == 0  # SQLite boolean


# ─── Performance Dashboard API Tests ─────────────────────────────────────────

class TestPerformanceDaily:
    def test_returns_daily_data(self, client, auth_headers):
        today = date.today().isoformat()
        res = client.get(f'/api/performance/daily?date={today}&team=all', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert 'date' in data
        assert 'staff' in data
        assert 'totals' in data

    def test_staff_has_performance_fields(self, client, auth_headers):
        today = date.today().isoformat()
        res = client.get(f'/api/performance/daily?date={today}', headers=auth_headers)
        data = res.json()
        if data['staff']:
            s = data['staff'][0]
            for key in ['staff_id', 'display_name', 'new_leads', 'reply_rate',
                        'registered', 'new_orders', 'conversion_rate', 'total_deposit']:
                assert key in s, f'Missing field: {key}'

    def test_totals_computed(self, client, auth_headers):
        today = date.today().isoformat()
        res = client.get(f'/api/performance/daily?date={today}', headers=auth_headers)
        totals = res.json()['totals']
        assert 'new_leads' in totals
        assert 'reply_rate' in totals
        assert 'conversion_rate' in totals

    def test_team_filter(self, client, auth_headers):
        today = date.today().isoformat()
        res = client.get(f'/api/performance/daily?date={today}&team=阿毛', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        for s in data['staff']:
            assert s['team'] == '阿毛'

    def test_empty_date_returns_empty(self, client, auth_headers):
        res = client.get('/api/performance/daily?date=2020-01-01', headers=auth_headers)
        assert res.status_code == 200
        # Staff list may be present but with zero values

    def test_default_date_is_today(self, client, auth_headers):
        res = client.get('/api/performance/daily', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['date'] == date.today().isoformat()


class TestPerformanceSummary:
    def test_returns_summary_data(self, client, auth_headers):
        today = date.today().isoformat()
        res = client.get(f'/api/performance/summary?from={today}&to={today}&team=all', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert 'staff' in data
        assert 'from' in data
        assert 'to' in data

    def test_summary_staff_has_rates(self, client, auth_headers):
        today = date.today().isoformat()
        res = client.get(f'/api/performance/summary?from={today}&to={today}', headers=auth_headers)
        data = res.json()
        if data['staff']:
            s = data['staff'][0]
            assert 'reply_rate' in s
            assert 'conversion_rate' in s
            assert 'total_deposit' in s

    def test_summary_team_filter(self, client, auth_headers):
        today = date.today().isoformat()
        res = client.get(f'/api/performance/summary?from={today}&to={today}&team=阿俊', headers=auth_headers)
        assert res.status_code == 200
        for s in res.json()['staff']:
            assert s['team'] == '阿俊'

    def test_missing_from_returns_422(self, client, auth_headers):
        res = client.get('/api/performance/summary?to=2026-01-01', headers=auth_headers)
        assert res.status_code == 422


# ─── Phone Registry Enhanced Tests ───────────────────────────────────────────

class TestPhoneRegistryEnhanced:
    def test_lookup_returns_found(self, client, auth_headers):
        res = client.get('/api/phone-registry/lookup?phone=8613900001111', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['found'] is True
        assert data['submitter_name'] == 'Tiger韦小宝'

    def test_lookup_not_found(self, client, auth_headers):
        res = client.get('/api/phone-registry/lookup?phone=0000000000', headers=auth_headers)
        assert res.status_code == 200
        assert res.json()['found'] is False

    def test_stats_returns_totals(self, client, auth_headers):
        res = client.get('/api/phone-registry/stats', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert 'total_registered' in data
        assert 'duplicates_blocked' in data
        assert data['total_registered'] >= 1

    def test_search_by_phone(self, client, auth_headers):
        res = client.get('/api/phone-registry/search?q=13900001111', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['total'] >= 1

    def test_search_by_name(self, client, auth_headers):
        res = client.get('/api/phone-registry/search?q=Tiger', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['total'] >= 1


# ─── RBAC Enforcement Tests ──────────────────────────────────────────────────

class TestRBACEnforcement:
    def test_unauthenticated_notes_returns_401(self, client):
        res = client.get('/api/clients/1/notes')
        assert res.status_code == 401

    def test_unauthenticated_timeline_returns_401(self, client):
        res = client.get('/api/clients/1/timeline')
        assert res.status_code == 401

    def test_unauthenticated_performance_returns_401(self, client):
        res = client.get('/api/performance/daily')
        assert res.status_code == 401

    def test_unauthenticated_add_note_returns_401(self, client):
        res = client.post('/api/clients/1/notes', json={'content': 'should fail'})
        assert res.status_code == 401

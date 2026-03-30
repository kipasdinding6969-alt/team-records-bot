"""Tests for the Web Dashboard FastAPI backend (port 8501)."""
import os
import sqlite3
import sys
import tempfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

# Set env before importing app
TEST_JWT_SECRET = 'test-jwt-secret-dashboard-2026'
TEST_USER = 'testadmin'
TEST_PASS = 'testpass123'
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
    """Create minimal schema + seed data."""
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

    today_ts = f'{today}T08:00:00'
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (88001, '阿YIM', 'frontdesk', '阿俊')")
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (88002, '小王', 'manager', '全线')")
    conn.execute(f"INSERT INTO clients (phone, status, source, frontdesk_id, created_at) VALUES ('+8613800001111', 'new', 'FB', 1, '{today_ts}')")
    conn.execute(f"INSERT INTO clients (phone, status, source, frontdesk_id, total_deposited, created_at, registered_at) VALUES ('+8613800002222', 'registered', 'TG', 1, 500.0, '{today_ts}', '{today_ts}')")
    conn.execute(f"INSERT INTO clients (phone, status, frontdesk_id, first_order_at) VALUES ('+8613800003333', 'ordered', 1, '{today_ts}')")
    conn.execute("INSERT INTO client_notes (client_id, staff_id, note_type, content) VALUES (1, 1, 'update', '初次联系')")
    conn.execute("INSERT INTO client_notes (client_id, staff_id, note_type, old_status, new_status, content) VALUES (2, 1, 'status_change', 'new', 'registered', '状态更新')")
    conn.execute(f"INSERT INTO deposits (client_id, frontdesk_id, amount, currency, platform, deposit_date) VALUES (2, 1, 500.0, 'USD', 'Binance', '{today}')")
    conn.execute("INSERT INTO xp_events (staff_id, action, xp_amount) VALUES (1, 'contact', 10)")
    conn.execute("INSERT INTO xp_events (staff_id, action, xp_amount) VALUES (1, 'registration', 50)")
    conn.execute("INSERT INTO streaks (staff_id, current_streak) VALUES (1, 5)")
    conn.execute(f"INSERT INTO daily_stats (staff_id, stat_date, new_leads, new_orders, total_deposit) VALUES (1, '{today}', 3, 1, 500.0)")
    conn.commit()
    conn.close()


@pytest.fixture(scope='module')
def client(temp_db_path, setup_db):
    os.environ['DB_PATH'] = temp_db_path
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


# ─── Auth tests ───────────────────────────────────────────────────────────────

class TestAuth:
    def test_login_success(self, client):
        res = client.post('/api/auth/login', json={'username': TEST_USER, 'password': TEST_PASS})
        assert res.status_code == 200
        data = res.json()
        assert 'access_token' in data
        assert data['token_type'] == 'bearer'
        assert len(data['access_token']) > 20

    def test_login_wrong_password(self, client):
        res = client.post('/api/auth/login', json={'username': TEST_USER, 'password': 'wrong'})
        assert res.status_code == 401

    def test_login_wrong_username(self, client):
        res = client.post('/api/auth/login', json={'username': 'hacker', 'password': TEST_PASS})
        assert res.status_code == 401

    def test_verify_valid_token(self, client, auth_headers):
        res = client.get('/api/auth/verify', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['ok'] is True
        assert data['username'] == TEST_USER

    def test_protected_route_without_token_returns_401(self, client):
        res = client.get('/api/dashboard')
        assert res.status_code == 401

    def test_protected_route_with_invalid_token_returns_401(self, client):
        res = client.get('/api/dashboard', headers={'Authorization': 'Bearer invalid.token.here'})
        assert res.status_code == 401

    def test_protected_route_with_tampered_token_returns_401(self, client):
        res = client.get('/api/dashboard', headers={'Authorization': 'Bearer eyJ.tampered.xyz'})
        assert res.status_code == 401


# ─── Dashboard tests ──────────────────────────────────────────────────────────

class TestDashboard:
    def test_returns_stats(self, client, auth_headers):
        res = client.get('/api/dashboard', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        required = [
            'total_clients', 'total_active', 'total_staff', 'total_deposits',
            'today_new', 'today_contacts', 'today_orders', 'today_deposits',
            'overdue_followups', 'conversion_rate', 'by_status',
        ]
        for key in required:
            assert key in data, f'Missing key: {key}'

    def test_total_clients_correct(self, client, auth_headers):
        res = client.get('/api/dashboard', headers=auth_headers)
        assert res.status_code == 200
        assert res.json()['total_clients'] >= 3

    def test_today_new_reflects_seeded_data(self, client, auth_headers):
        res = client.get('/api/dashboard', headers=auth_headers)
        assert res.json()['today_new'] >= 2

    def test_conversion_rate_is_percentage(self, client, auth_headers):
        res = client.get('/api/dashboard', headers=auth_headers)
        rate = res.json()['conversion_rate']
        assert 0 <= rate <= 100

    def test_by_status_is_dict(self, client, auth_headers):
        res = client.get('/api/dashboard', headers=auth_headers)
        assert isinstance(res.json()['by_status'], dict)


# ─── Funnel tests ─────────────────────────────────────────────────────────────

class TestFunnel:
    def test_returns_list(self, client, auth_headers):
        res = client.get('/api/funnel', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 6  # 6 pipeline stages

    def test_each_stage_has_required_fields(self, client, auth_headers):
        res = client.get('/api/funnel', headers=auth_headers)
        for stage in res.json():
            assert 'stage' in stage
            assert 'count' in stage
            assert 'pct' in stage

    def test_stages_in_order(self, client, auth_headers):
        res = client.get('/api/funnel', headers=auth_headers)
        stages = [s['stage'] for s in res.json()]
        expected = ['new', 'contacted', 'replied', 'registered', 'training', 'ordered']
        assert stages == expected

    def test_pct_is_float(self, client, auth_headers):
        res = client.get('/api/funnel', headers=auth_headers)
        for stage in res.json():
            assert isinstance(stage['pct'], (int, float))


# ─── Activity tests ───────────────────────────────────────────────────────────

class TestActivity:
    def test_returns_list(self, client, auth_headers):
        res = client.get('/api/activity', headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_activity_has_required_fields(self, client, auth_headers):
        res = client.get('/api/activity', headers=auth_headers)
        for item in res.json():
            assert 'id' in item
            assert 'note_type' in item
            assert 'created_at' in item

    def test_at_most_50_items(self, client, auth_headers):
        res = client.get('/api/activity', headers=auth_headers)
        assert len(res.json()) <= 50


# ─── Staff tests ──────────────────────────────────────────────────────────────

class TestStaff:
    def test_returns_list(self, client, auth_headers):
        res = client.get('/api/staff', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_entry_has_required_fields(self, client, auth_headers):
        res = client.get('/api/staff', headers=auth_headers)
        for entry in res.json():
            for key in ['id', 'display_name', 'role', 'xp_total', 'current_streak']:
                assert key in entry

    def test_sorted_by_xp_desc(self, client, auth_headers):
        res = client.get('/api/staff', headers=auth_headers)
        xps = [e['xp_total'] for e in res.json()]
        assert xps == sorted(xps, reverse=True)

    def test_today_stats_included(self, client, auth_headers):
        res = client.get('/api/staff', headers=auth_headers)
        staff1 = next((e for e in res.json() if e['display_name'] == '阿YIM'), None)
        assert staff1 is not None
        assert 'today_leads' in staff1
        assert 'today_orders' in staff1


# ─── Trends tests ─────────────────────────────────────────────────────────────

class TestTrends:
    def test_returns_all_trend_types(self, client, auth_headers):
        res = client.get('/api/trends', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert 'daily_new' in data
        assert 'daily_orders' in data
        assert 'daily_deposits' in data

    def test_daily_new_has_correct_fields(self, client, auth_headers):
        res = client.get('/api/trends', headers=auth_headers)
        for item in res.json()['daily_new']:
            assert 'day' in item
            assert 'new_clients' in item

    def test_daily_orders_has_correct_fields(self, client, auth_headers):
        res = client.get('/api/trends', headers=auth_headers)
        for item in res.json()['daily_orders']:
            assert 'day' in item
            assert 'orders' in item


# ─── Clients list tests ───────────────────────────────────────────────────────

class TestClientsList:
    def test_returns_paginated_list(self, client, auth_headers):
        res = client.get('/api/clients', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert 'total' in data
        assert 'clients' in data
        assert 'page' in data
        assert data['total'] >= 3

    def test_filter_by_status(self, client, auth_headers):
        res = client.get('/api/clients?status=new', headers=auth_headers)
        assert res.status_code == 200
        for c in res.json()['clients']:
            assert c['status'] == 'new'

    def test_search_by_phone(self, client, auth_headers):
        res = client.get('/api/clients?search=13800001111', headers=auth_headers)
        assert res.status_code == 200
        clients = res.json()['clients']
        assert any('13800001111' in c['phone'] for c in clients)

    def test_pagination(self, client, auth_headers):
        res = client.get('/api/clients?page=1&per_page=2', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data['clients']) <= 2
        assert data['page'] == 1
        assert data['per_page'] == 2


# ─── Client detail tests ──────────────────────────────────────────────────────

class TestClientDetail:
    def test_returns_client_with_notes_and_deposits(self, client, auth_headers):
        res = client.get('/api/clients/2', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['id'] == 2
        assert data['phone'] == '+8613800002222'
        assert 'notes' in data
        assert 'deposits' in data
        assert data['total_deposited'] == 500.0

    def test_deposits_list(self, client, auth_headers):
        res = client.get('/api/clients/2', headers=auth_headers)
        deposits = res.json()['deposits']
        assert len(deposits) == 1
        assert deposits[0]['amount'] == 500.0
        assert deposits[0]['platform'] == 'Binance'

    def test_notes_list(self, client, auth_headers):
        res = client.get('/api/clients/1', headers=auth_headers)
        notes = res.json()['notes']
        assert any(n['content'] == '初次联系' for n in notes)

    def test_404_for_missing_client(self, client, auth_headers):
        res = client.get('/api/clients/9999', headers=auth_headers)
        assert res.status_code == 404


# ─── Export tests ─────────────────────────────────────────────────────────────

class TestExport:
    def test_export_clients_csv(self, client, auth_headers):
        res = client.get('/api/export/clients', headers=auth_headers)
        assert res.status_code == 200
        assert 'text/csv' in res.headers['content-type']
        content = res.text
        assert len(content) > 0
        # Should have header row
        lines = content.strip().split('\n')
        assert len(lines) >= 2  # header + data

    def test_export_clients_filter_by_status(self, client, auth_headers):
        res = client.get('/api/export/clients?status=new', headers=auth_headers)
        assert res.status_code == 200
        assert 'text/csv' in res.headers['content-type']

    def test_export_report_daily(self, client, auth_headers):
        res = client.get('/api/export/report?period=daily', headers=auth_headers)
        assert res.status_code == 200
        assert 'text/csv' in res.headers['content-type']

    def test_export_report_weekly(self, client, auth_headers):
        res = client.get('/api/export/report?period=weekly', headers=auth_headers)
        assert res.status_code == 200

    def test_export_report_monthly(self, client, auth_headers):
        res = client.get('/api/export/report?period=monthly', headers=auth_headers)
        assert res.status_code == 200

    def test_export_report_invalid_period(self, client, auth_headers):
        res = client.get('/api/export/report?period=yearly', headers=auth_headers)
        assert res.status_code == 422


# ─── Health test ──────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_endpoint(self, client):
        res = client.get('/health')
        assert res.status_code == 200
        data = res.json()
        assert data['status'] == 'ok'
        assert data['service'] == 'dashboard'
        assert data['port'] == 8501


# ─── Team performance tests ───────────────────────────────────────────────────

class TestTeamPerformance:
    def test_returns_team_data(self, client, auth_headers):
        res = client.get('/api/team/阿俊/performance', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['team'] == '阿俊'
        assert 'members' in data
        assert 'totals' in data

    def test_empty_team_returns_empty(self, client, auth_headers):
        res = client.get('/api/team/nonexistent_team/performance', headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['members'] == []

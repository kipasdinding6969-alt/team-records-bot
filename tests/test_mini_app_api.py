"""Tests for the Mini App FastAPI backend."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
from datetime import date
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

# Override env before importing the app
TEST_BOT_TOKEN = 'test_token_1234567890'
os.environ['BOT_TOKEN'] = TEST_BOT_TOKEN


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
    """Create minimal schema + seed data using synchronous sqlite3."""
    today = date.today().isoformat()
    conn = sqlite3.connect(temp_db_path)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT DEFAULT 'frontdesk',
            team TEXT,
            language TEXT DEFAULT 'zh',
            is_active INTEGER DEFAULT 1,
            daily_target INTEGER DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            source TEXT,
            nickname TEXT,
            recruiter TEXT,
            frontdesk_id INTEGER REFERENCES staff(id),
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
            last_action_date TEXT,
            freeze_available INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            emoji TEXT,
            description TEXT,
            xp_threshold INTEGER DEFAULT 0,
            action_type TEXT
        );
        CREATE TABLE IF NOT EXISTS staff_badges (
            staff_id INTEGER,
            badge_id INTEGER,
            earned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (staff_id, badge_id)
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

    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (99001, '阿YIM', 'frontdesk', '阿俊')")
    conn.execute("INSERT INTO staff (tg_user_id, display_name, role, team) VALUES (99002, '小王', 'manager', '全线')")
    conn.execute(f"INSERT INTO clients (phone, status, source, frontdesk_id, created_at) VALUES ('+8613800001111', 'new', 'FB', 1, '{today}T08:00:00')")
    conn.execute(f"INSERT INTO clients (phone, status, source, frontdesk_id, total_deposited, created_at, registered_at) VALUES ('+8613800002222', 'registered', 'TG', 1, 500.0, '{today}T07:00:00', '{today}T09:00:00')")
    conn.execute("INSERT INTO clients (phone, status, frontdesk_id) VALUES ('+8613800003333', 'ordered', 1)")
    conn.execute("INSERT INTO client_notes (client_id, staff_id, note_type, content) VALUES (1, 1, 'update', '初次联系')")
    conn.execute(f"INSERT INTO deposits (client_id, frontdesk_id, amount, currency, platform, deposit_date) VALUES (2, 1, 500.0, 'USD', 'Binance', '{today}')")
    conn.execute("INSERT INTO xp_events (staff_id, action, xp_amount) VALUES (1, 'contact', 10)")
    conn.execute("INSERT INTO xp_events (staff_id, action, xp_amount) VALUES (1, 'registration', 50)")
    conn.execute("INSERT INTO streaks (staff_id, current_streak, longest_streak) VALUES (1, 5, 10)")
    conn.execute("INSERT INTO badges (name, emoji, description) VALUES ('首单王', '🏆', '首次完成订单')")
    conn.execute("INSERT INTO staff_badges (staff_id, badge_id) VALUES (1, 1)")
    conn.execute(f"INSERT INTO daily_stats (staff_id, stat_date, new_leads, new_orders) VALUES (1, '{today}', 3, 1)")
    conn.commit()
    conn.close()


@pytest.fixture(scope='module')
def client(temp_db_path, setup_db):
    """Create FastAPI test client with test DB."""
    os.environ['DB_PATH'] = temp_db_path
    import importlib
    import sys
    # Reload module to pick up new DB_PATH
    if 'mini_app_api' in sys.modules:
        del sys.modules['mini_app_api']
    import mini_app_api
    with TestClient(mini_app_api.app) as c:
        yield c


def make_init_data(user_id: int = 99001) -> str:
    """Generate valid Telegram initData for tests."""
    user = json.dumps({'id': user_id, 'first_name': 'Test'})
    pairs = {
        'user': user,
        'auth_date': '1700000000',
        'query_id': 'test_query',
    }
    data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b'WebAppData', TEST_BOT_TOKEN.encode(), hashlib.sha256).digest()
    pairs['hash'] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


VALID_INIT_DATA = make_init_data(99001)


class TestPipeline:
    def test_returns_grouped_by_status(self, client):
        r = client.get('/api/pipeline', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        # We seeded 'new', 'registered', 'ordered' clients
        assert 'new' in data
        assert 'registered' in data

    def test_each_client_has_required_fields(self, client):
        r = client.get('/api/pipeline', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        for status, clients in r.json().items():
            for c in clients:
                assert 'id' in c
                assert 'phone' in c
                assert 'status' in c

    def test_rejects_invalid_auth(self, client):
        r = client.get('/api/pipeline', headers={'x-telegram-init-data': 'invalid'})
        assert r.status_code == 401


class TestClientDetail:
    def test_returns_client_with_notes_and_deposits(self, client):
        r = client.get('/api/client/2', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        data = r.json()
        assert data['id'] == 2
        assert data['phone'] == '+8613800002222'
        assert 'notes' in data
        assert 'deposits' in data
        assert data['total_deposited'] == 500.0
        assert len(data['deposits']) == 1
        assert data['deposits'][0]['amount'] == 500.0

    def test_notes_returned(self, client):
        r = client.get('/api/client/1', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        data = r.json()
        assert len(data['notes']) == 1
        assert data['notes'][0]['content'] == '初次联系'

    def test_404_for_missing_client(self, client):
        r = client.get('/api/client/9999', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 404


class TestStatusUpdate:
    def test_updates_status(self, client):
        r = client.patch(
            '/api/client/1/status',
            json={'status': 'contacted'},
            headers={'x-telegram-init-data': VALID_INIT_DATA},
        )
        assert r.status_code == 200
        data = r.json()
        assert data['ok'] is True
        assert data['new_status'] == 'contacted'
        assert data['old_status'] == 'new'

    def test_rejects_invalid_status(self, client):
        r = client.patch(
            '/api/client/1/status',
            json={'status': 'invalid_status'},
            headers={'x-telegram-init-data': VALID_INIT_DATA},
        )
        assert r.status_code == 400

    def test_404_for_missing_client(self, client):
        r = client.patch(
            '/api/client/9999/status',
            json={'status': 'contacted'},
            headers={'x-telegram-init-data': VALID_INIT_DATA},
        )
        assert r.status_code == 404

    def test_logs_note_on_status_change(self, client):
        # Update client 3 status and verify note is logged
        client.patch(
            '/api/client/3/status',
            json={'status': 'training'},
            headers={'x-telegram-init-data': VALID_INIT_DATA},
        )
        r = client.get('/api/client/3', headers={'x-telegram-init-data': VALID_INIT_DATA})
        notes = r.json()['notes']
        assert any('状态更新' in n['content'] for n in notes)


class TestAddNote:
    def test_adds_note(self, client):
        r = client.post(
            '/api/client/1/note',
            json={'content': '测试备注'},
            headers={'x-telegram-init-data': VALID_INIT_DATA},
        )
        assert r.status_code == 200
        assert r.json()['ok'] is True

    def test_note_appears_in_detail(self, client):
        r = client.get('/api/client/1', headers={'x-telegram-init-data': VALID_INIT_DATA})
        notes = r.json()['notes']
        assert any(n['content'] == '测试备注' for n in notes)

    def test_rejects_empty_note(self, client):
        r = client.post(
            '/api/client/1/note',
            json={'content': '   '},
            headers={'x-telegram-init-data': VALID_INIT_DATA},
        )
        assert r.status_code == 400


class TestStats:
    def test_returns_stats(self, client):
        r = client.get('/api/stats', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        data = r.json()
        assert 'by_status' in data
        assert 'today_new' in data
        assert 'today_contacts' in data
        assert 'today_orders' in data
        assert 'overdue_followups' in data
        assert 'total_active' in data
        assert 'total_clients' in data

    def test_total_clients_correct(self, client):
        r = client.get('/api/stats', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        data = r.json()
        assert data['total_clients'] >= 3

    def test_today_new_reflects_seeded_data(self, client):
        r = client.get('/api/stats', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        # We seeded 2 clients today
        assert r.json()['today_new'] >= 2


class TestLeaderboard:
    def test_returns_list(self, client):
        r = client.get('/api/leaderboard', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_entry_has_required_fields(self, client):
        r = client.get('/api/leaderboard', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        for entry in r.json():
            assert 'id' in entry
            assert 'display_name' in entry
            assert 'xp_total' in entry
            assert 'current_streak' in entry
            assert 'badges' in entry

    def test_sorted_by_xp_desc(self, client):
        r = client.get('/api/leaderboard', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        entries = r.json()
        xps = [e['xp_total'] for e in entries]
        assert xps == sorted(xps, reverse=True)

    def test_badges_included(self, client):
        r = client.get('/api/leaderboard', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        staff1 = next((e for e in r.json() if e['display_name'] == '阿YIM'), None)
        assert staff1 is not None
        assert any(b['emoji'] == '🏆' for b in staff1['badges'])


class TestStaffMe:
    def test_returns_staff_data(self, client):
        r = client.get('/api/staff/me', headers={'x-telegram-init-data': VALID_INIT_DATA})
        assert r.status_code == 200
        data = r.json()
        assert data['tg_user_id'] == 99001
        assert data['display_name'] == '阿YIM'
        assert 'xp_total' in data
        assert 'current_streak' in data

    def test_404_for_unknown_user(self, client):
        unknown_init_data = make_init_data(user_id=99999)
        r = client.get('/api/staff/me', headers={'x-telegram-init-data': unknown_init_data})
        assert r.status_code == 404


class TestHealth:
    def test_health_endpoint(self, client):
        r = client.get('/health')
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'


class TestAuth:
    def test_missing_init_data_returns_401(self, client):
        r = client.get('/api/pipeline')
        assert r.status_code == 401

    def test_tampered_hash_returns_401(self, client):
        r = client.get('/api/pipeline', headers={'x-telegram-init-data': 'hash=tampered&auth_date=1234&user=%7B%7D'})
        assert r.status_code == 401

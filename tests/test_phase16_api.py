"""Phase 16 tests — API endpoints for phone registry, permissions, client links.

Uses FastAPI TestClient (sync) to avoid httpx dependency.
"""
import asyncio
import os
import tempfile

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch DB path before importing
_fd, _TEST_DB = tempfile.mkstemp(suffix='.db')
os.close(_fd)
os.environ['DB_PATH'] = _TEST_DB
os.environ['JWT_SECRET'] = 'test-secret-phase16-api'

try:
    import aiosqlite
    from fastapi.testclient import TestClient
    import web_dashboard_api
    from web_dashboard_api import app, _hash_password
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason='fastapi not installed')


@pytest.fixture(scope='module', autouse=True)
def setup_db():
    """Create tables and seed data synchronously."""
    import sqlite3
    conn = sqlite3.connect(_TEST_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER UNIQUE NOT NULL,
            tg_chat_id INTEGER NOT NULL,
            tg_username TEXT,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'frontdesk',
            team TEXT,
            phone TEXT,
            language TEXT DEFAULT 'zh',
            is_active BOOLEAN DEFAULT TRUE,
            daily_target INTEGER DEFAULT 40,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frontdesk_id INTEGER NOT NULL REFERENCES staff(id),
            phone TEXT NOT NULL,
            account_id TEXT, phone_remark TEXT, nickname TEXT,
            source TEXT NOT NULL, recruiter TEXT,
            status TEXT NOT NULL DEFAULT 'new', status_note TEXT,
            contacted_at TIMESTAMP, replied_at TIMESTAMP,
            registered_at TIMESTAMP, training_at TIMESTAMP,
            withdrew_at TIMESTAMP, first_order_at TIMESTAMP,
            next_followup TIMESTAMP, followup_count INTEGER DEFAULT 0,
            platform TEXT, total_deposited REAL DEFAULT 0, sheet_gid INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS dashboard_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner','admin','member')),
            staff_id INTEGER REFERENCES staff(id),
            team_scope TEXT,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS phone_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            phone_normalized TEXT NOT NULL,
            submitter_name TEXT NOT NULL,
            submitter_staff_id INTEGER REFERENCES staff(id),
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
            actor_staff_id INTEGER REFERENCES staff(id),
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    """)

    hashed = _hash_password('test123')
    conn.execute(
        "INSERT INTO staff (tg_user_id, tg_chat_id, display_name, role, team) VALUES (1001, 1001, 'TestOwner', 'admin', 'teamA')"
    )
    conn.execute(
        "INSERT INTO staff (tg_user_id, tg_chat_id, display_name, role, team) VALUES (1002, 1002, 'TestUser', 'frontdesk', 'teamA')"
    )
    conn.execute(
        "INSERT INTO dashboard_users (username, password_hash, display_name, role, staff_id, team_scope) VALUES (?, ?, 'Owner', 'owner', 1, NULL)",
        ('owner', hashed)
    )
    conn.execute(
        "INSERT INTO dashboard_users (username, password_hash, display_name, role, staff_id, team_scope) VALUES (?, ?, 'Admin', 'admin', 1, 'teamA')",
        ('admin', hashed)
    )
    conn.execute(
        "INSERT INTO clients (frontdesk_id, phone, source) VALUES (1, '555-0001', 'web')"
    )
    conn.execute(
        "INSERT INTO clients (frontdesk_id, phone, source) VALUES (1, '555-0002', 'web')"
    )
    conn.execute(
        "INSERT INTO phone_registry (phone, phone_normalized, submitter_name, submitter_staff_id, source, submitted_at) VALUES ('555-1000', '5551000', 'TestOwner', 1, 'import', '2026-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO phone_registry_log (phone_normalized, action, actor_name) VALUES ('5551000', 'import', 'system')"
    )
    conn.commit()
    conn.close()
    yield
    try:
        os.unlink(_TEST_DB)
    except Exception:
        pass


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username='owner', password='test123'):
    resp = client.post('/api/auth/login', json={
        'username': username, 'password': password,
    })
    return resp.json()['access_token']


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


# ─── Phone Registry Endpoints ────────────────────────────────────────────────

class TestPhoneRegistryAPI:
    def test_lookup_found(self, client):
        token = _login(client)
        resp = client.get('/api/phone-registry/lookup?phone=555-1000', headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data['found'] is True
        assert data['submitter_name'] == 'TestOwner'

    def test_lookup_not_found(self, client):
        token = _login(client)
        resp = client.get('/api/phone-registry/lookup?phone=999-9999', headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()['found'] is False

    def test_search(self, client):
        token = _login(client)
        resp = client.get('/api/phone-registry/search?q=555', headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()['total'] >= 1

    def test_stats(self, client):
        token = _login(client)
        resp = client.get('/api/phone-registry/stats', headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert 'total' in data
        assert 'total_registered' in data
        assert 'duplicates_blocked' in data

    def test_override(self, client):
        token = _login(client)
        resp = client.post(
            '/api/phone-registry/override?phone=555-1000',
            json={'new_submitter': 'NewOwner'},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        # Verify
        resp = client.get('/api/phone-registry/lookup?phone=555-1000', headers=_auth(token))
        assert resp.json()['submitter_name'] == 'NewOwner'

    def test_lookup_requires_auth(self, client):
        resp = client.get('/api/phone-registry/lookup?phone=555-1000')
        assert resp.status_code == 401


# ─── Client Links Endpoints ──────────────────────────────────────────────────

class TestClientLinksAPI:
    def test_create_link(self, client):
        token = _login(client)
        resp = client.post('/api/client-links', json={
            'client_id_a': 1, 'client_id_b': 2, 'link_type': 'related',
        }, headers=_auth(token))
        assert resp.status_code == 200

    def test_get_links(self, client):
        token = _login(client)
        resp = client.get('/api/clients/1/links', headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_invalid_link_type(self, client):
        token = _login(client)
        resp = client.post('/api/client-links', json={
            'client_id_a': 1, 'client_id_b': 2, 'link_type': 'invalid',
        }, headers=_auth(token))
        assert resp.status_code == 400


# ─── Permission Overrides Endpoints ──────────────────────────────────────────

class TestPermissionsAPI:
    def test_set_override(self, client):
        token = _login(client)
        resp = client.post('/api/permissions', json={
            'staff_id': 2, 'command': 'broadcast', 'allowed': True, 'reason': 'test grant',
        }, headers=_auth(token))
        assert resp.status_code == 200

    def test_get_staff_permissions(self, client):
        token = _login(client)
        resp = client.get('/api/permissions/2', headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert 'staff' in data
        assert 'overrides' in data

    def test_list_all_permissions(self, client):
        token = _login(client)
        resp = client.get('/api/permissions', headers=_auth(token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_delete_override(self, client):
        token = _login(client)
        resp = client.delete('/api/permissions/2/broadcast', headers=_auth(token))
        assert resp.status_code == 200

    def test_permissions_requires_auth(self, client):
        resp = client.get('/api/permissions/1')
        assert resp.status_code == 401

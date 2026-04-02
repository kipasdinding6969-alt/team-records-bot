"""Web Dashboard API for Team Records Bot V2 — port 8501.

Separate from mini_app_api.py (port 8500). Uses JWT auth with 3-tier RBAC:
OWNER → ADMIN → MEMBER backed by dashboard_users table (bcrypt passwords).
"""
import bcrypt
import csv
import io
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager as _acm
from datetime import UTC, date, datetime, timedelta
from typing import Optional

import sqlite3

import aiosqlite
import jwt
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

DB_PATH = os.getenv('DB_PATH', './team_records_v2.db')
DASHBOARD_USER = os.getenv('DASHBOARD_USER', '')
DASHBOARD_PASS = os.getenv('DASHBOARD_PASS', '')
JWT_SECRET = os.getenv('JWT_SECRET', '')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_HOURS = 24
DASHBOARD_DIST = os.path.join(os.path.dirname(__file__), 'web_dashboard', 'dist')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    logger.warning(
        'JWT_SECRET not set — generated random secret. '
        'Sessions will NOT survive restart. Set JWT_SECRET env var for production.'
    )

_CREATE_DASHBOARD_USERS_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('owner', 'admin', 'member')),
    staff_id INTEGER REFERENCES staff(id),
    team_scope TEXT,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES dashboard_users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
)
"""


# ─── DB helpers ───────────────────────────────────────────────────────────────

@_acm
async def _connect_db():
    async with aiosqlite.connect(DB_PATH, timeout=15) as db:
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA foreign_keys = ON')
        await db.execute('PRAGMA journal_mode = WAL')
        yield db


def row_to_dict(row) -> dict:
    return dict(row)


# ─── Password helpers ─────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


# ─── Lifespan: create table + auto-migrate from env vars ──────────────────────

@_acm
async def _lifespan(app):
    async with _connect_db() as db:
        await db.execute(_CREATE_DASHBOARD_USERS_SQL)
        await db.commit()
        async with db.execute('SELECT COUNT(*) AS cnt FROM dashboard_users') as cur:
            count = (await cur.fetchone())['cnt']
        if count == 0 and DASHBOARD_USER and DASHBOARD_PASS:
            hashed = _hash_password(DASHBOARD_PASS)
            await db.execute(
                """INSERT INTO dashboard_users
                   (username, password_hash, display_name, role, team_scope, is_active)
                   VALUES (?, ?, ?, 'owner', NULL, 1)""",
                (DASHBOARD_USER, hashed, 'Owner'),
            )
            await db.commit()
            logger.info(f'Auto-migrated owner account from env: {DASHBOARD_USER}')
    yield


app = FastAPI(title='Team Records Dashboard API', version='2.0.0', lifespan=_lifespan)

_ALLOWED_ORIGINS = [
    'https://dash.sem-rush.com',
    'http://127.0.0.1:8501',
    'http://localhost:8501',
    'http://127.0.0.1:5173',  # vite dev
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# ─── Auth models ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class SetupRequest(BaseModel):
    username: str
    password: str
    display_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str
    team_scope: Optional[str] = None
    staff_id: Optional[int] = None


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    team_scope: Optional[str] = None
    staff_id: Optional[int] = None
    is_active: Optional[bool] = None


# ─── JWT + auth dependencies ──────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


def _create_token(user: dict, remember_me: bool = False) -> str:
    hours = 24 * 30 if remember_me else JWT_EXPIRE_HOURS
    payload = {
        'sub': user['username'],
        'role': user['role'],
        'team_scope': user.get('team_scope'),
        'staff_id': user.get('staff_id'),
        'user_id': user['id'],
        'display_name': user['display_name'],
        'exp': datetime.now(UTC) + timedelta(hours=hours),
        'iat': datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail='Missing token')
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get('sub')
        if not username:
            raise HTTPException(status_code=401, detail='Invalid token')
        return {
            'username': username,
            'role': payload.get('role', 'member'),
            'team_scope': payload.get('team_scope'),
            'staff_id': payload.get('staff_id'),
            'user_id': payload.get('user_id'),
            'display_name': payload.get('display_name', username),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')


def _require_owner_or_admin(user: dict = Depends(get_current_user)) -> dict:
    if user['role'] not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail='Admin or owner access required')
    return user


async def _check_section_permission(user: dict, command: str) -> bool:
    """Check if user has permission for a specific section/command.

    Owner always has all permissions. For admin/member, checks permission_overrides table.
    If no override exists, permission defaults to True (allowed).
    """
    if user['role'] == 'owner':
        return True
    staff_id = user.get('staff_id')
    if not staff_id:
        return True  # No staff link = no overrides to check
    async with _connect_db() as db:
        cur = await db.execute(
            'SELECT allowed FROM permission_overrides WHERE staff_id = ? AND command = ?',
            (staff_id, command)
        )
        row = await cur.fetchone()
        if row is None:
            return True  # No override = allowed by default
        return bool(row['allowed'])


async def _require_permission(user: dict, command: str):
    """Raise 403 if user doesn't have permission for the given command."""
    if not await _check_section_permission(user, command):
        raise HTTPException(
            status_code=403,
            detail=f'Permission denied: {command}'
        )


# ─── Data scoping helpers ─────────────────────────────────────────────────────

def _scope_clients(user: dict) -> tuple[list[str], list]:
    """WHERE conditions for queries joining clients c with staff s."""
    role = user['role']
    if role == 'owner':
        return [], []
    if role == 'admin':
        return ['s.team = ?'], [user['team_scope']]
    # member: staff_id required
    sid = user.get('staff_id')
    if sid:
        return ['c.frontdesk_id = ?'], [sid]
    return ['1 = 0'], []


async def _check_client_access(client_id: int, user: dict, db):
    """Verify user can access this client. Raises 403 if denied."""
    if user['role'] == 'owner':
        return
    async with db.execute(
        'SELECT c.frontdesk_id, s.team FROM clients c LEFT JOIN staff s ON c.frontdesk_id = s.id WHERE c.id = ?',
        (client_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return  # client not found — let the endpoint handle 404
    if user['role'] == 'admin':
        if row['team'] != user.get('team_scope'):
            raise HTTPException(status_code=403, detail='Access denied — client outside your team')
    elif user['role'] == 'member':
        if row['frontdesk_id'] != user.get('staff_id'):
            raise HTTPException(status_code=403, detail='Access denied — not your client')


def _scope_staff(user: dict) -> tuple[list[str], list]:
    """WHERE conditions for queries on staff s only."""
    role = user['role']
    if role == 'owner':
        return [], []
    if role == 'admin':
        return ['s.team = ?'], [user['team_scope']]
    sid = user.get('staff_id')
    if sid:
        return ['s.id = ?'], [sid]
    return ['1 = 0'], []


def _scope_daily_stats(user: dict) -> tuple[list[str], list]:
    """WHERE conditions for daily_stats joined with staff."""
    role = user['role']
    if role == 'owner':
        return [], []
    if role == 'admin':
        return ['s.team = ?'], [user['team_scope']]
    sid = user.get('staff_id')
    if sid:
        return ['ds.staff_id = ?'], [sid]
    return ['1 = 0'], []


# ─── Auth endpoints ───────────────────────────────────────────────────────────

@app.post('/api/auth/setup')
async def setup_first_owner(body: SetupRequest):
    """Create first owner account. Only works when dashboard_users is empty."""
    async with _connect_db() as db:
        async with db.execute('SELECT COUNT(*) AS cnt FROM dashboard_users') as cur:
            count = (await cur.fetchone())['cnt']
        if count > 0:
            raise HTTPException(status_code=400, detail='Setup already complete')
        if len(body.password) < 6:
            raise HTTPException(status_code=400, detail='Password must be at least 6 characters')
        hashed = _hash_password(body.password)
        await db.execute(
            """INSERT INTO dashboard_users (username, password_hash, display_name, role, is_active)
               VALUES (?, ?, ?, 'owner', 1)""",
            (body.username, hashed, body.display_name),
        )
        await db.commit()
    return {'ok': True, 'message': 'Owner account created'}


@app.post('/api/auth/login')
async def login(body: LoginRequest):
    async with _connect_db() as db:
        async with db.execute(
            """SELECT id, username, password_hash, display_name, role, team_scope,
                      staff_id, is_active
               FROM dashboard_users WHERE username = ?""",
            (body.username,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    user = row_to_dict(row)
    if not user['is_active']:
        raise HTTPException(status_code=401, detail='Account deactivated')
    if not _verify_password(body.password, user['password_hash']):
        raise HTTPException(status_code=401, detail='Invalid credentials')

    # Update last_login
    async with _connect_db() as db:
        await db.execute(
            'UPDATE dashboard_users SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
            (user['id'],)
        )
        await db.commit()

    token = _create_token(user, body.remember_me)
    return {
        'access_token': token,
        'token_type': 'bearer',
        'username': user['username'],
        'display_name': user['display_name'],
        'role': user['role'],
        'team_scope': user['team_scope'],
        'staff_id': user['staff_id'],
        'user_id': user['id'],
    }


@app.get('/api/auth/verify')
async def verify_auth(user: dict = Depends(get_current_user)):
    return {
        'ok': True,
        'username': user['username'],
        'role': user['role'],
        'team_scope': user['team_scope'],
        'display_name': user['display_name'],
        'staff_id': user['staff_id'],
        'user_id': user['user_id'],
    }


@app.post('/api/auth/change-password')
async def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    async with _connect_db() as db:
        async with db.execute(
            'SELECT password_hash FROM dashboard_users WHERE username = ?',
            (user['username'],)
        ) as cur:
            row = await cur.fetchone()
        if not row or not _verify_password(body.current_password, row['password_hash']):
            raise HTTPException(status_code=401, detail='Current password incorrect')
        if len(body.new_password) < 6:
            raise HTTPException(status_code=400, detail='Password must be at least 6 characters')
        hashed = _hash_password(body.new_password)
        await db.execute(
            'UPDATE dashboard_users SET password_hash = ? WHERE username = ?',
            (hashed, user['username'])
        )
        await db.commit()
    return {'ok': True}


# ─── User management endpoints ────────────────────────────────────────────────

@app.get('/api/users')
async def list_users(user: dict = Depends(_require_owner_or_admin)):
    async with _connect_db() as db:
        if user['role'] == 'owner':
            async with db.execute(
                """SELECT id, username, display_name, role, team_scope, staff_id,
                          is_active, last_login, created_at
                   FROM dashboard_users ORDER BY created_at"""
            ) as cur:
                rows = [row_to_dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                """SELECT id, username, display_name, role, team_scope, staff_id,
                          is_active, last_login, created_at
                   FROM dashboard_users WHERE team_scope = ?
                   ORDER BY created_at""",
                (user['team_scope'],)
            ) as cur:
                rows = [row_to_dict(r) for r in await cur.fetchall()]
    return rows


@app.post('/api/users', status_code=201)
async def create_user(body: CreateUserRequest, user: dict = Depends(_require_owner_or_admin)):
    # RBAC: admin can only create members in their own team
    if user['role'] == 'admin':
        if body.role != 'member':
            raise HTTPException(status_code=403, detail='Admin can only create member accounts')
        if body.team_scope != user['team_scope']:
            raise HTTPException(status_code=403, detail='Admin can only create users in their own team')

    valid_roles = ('owner', 'admin', 'member')
    if body.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f'Invalid role. Must be one of: {valid_roles}')
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail='Password must be at least 6 characters')

    hashed = _hash_password(body.password)
    async with _connect_db() as db:
        try:
            await db.execute(
                """INSERT INTO dashboard_users
                   (username, password_hash, display_name, role, team_scope, staff_id, is_active, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (body.username, hashed, body.display_name, body.role,
                 body.team_scope, body.staff_id, user['user_id'])
            )
            await db.commit()
            async with db.execute(
                'SELECT id FROM dashboard_users WHERE username = ?', (body.username,)
            ) as cur:
                new_id = (await cur.fetchone())['id']
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail='Username already exists')

    return {'ok': True, 'id': new_id}


@app.put('/api/users/{user_id}')
async def update_user(
    user_id: int, body: UpdateUserRequest, actor: dict = Depends(_require_owner_or_admin)
):
    async with _connect_db() as db:
        async with db.execute(
            'SELECT id, username, role, team_scope, is_active FROM dashboard_users WHERE id = ?',
            (user_id,)
        ) as cur:
            target = await cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail='User not found')
        target = row_to_dict(target)

        # RBAC checks
        if actor['role'] == 'admin':
            if target['team_scope'] != actor['team_scope']:
                raise HTTPException(status_code=403, detail='Cannot edit users outside your team')
            if target['role'] != 'member':
                raise HTTPException(status_code=403, detail='Admin can only edit member accounts')
            if body.role is not None and body.role != 'member':
                raise HTTPException(status_code=403, detail='Admin cannot change role to non-member')
            if body.team_scope is not None and body.team_scope != actor['team_scope']:
                raise HTTPException(status_code=403, detail='Admin cannot move users to other teams')

        updates = {}
        if body.display_name is not None:
            updates['display_name'] = body.display_name
        if body.role is not None:
            if body.role not in ('owner', 'admin', 'member'):
                raise HTTPException(status_code=400, detail='Invalid role')
            updates['role'] = body.role
        if body.team_scope is not None:
            updates['team_scope'] = body.team_scope
        if body.staff_id is not None:
            updates['staff_id'] = body.staff_id
        if body.is_active is not None:
            updates['is_active'] = 1 if body.is_active else 0

        if not updates:
            return {'ok': True}

        set_clause = ', '.join(f'{k} = ?' for k in updates)
        params = list(updates.values()) + [user_id]
        await db.execute(f'UPDATE dashboard_users SET {set_clause} WHERE id = ?', params)
        await db.commit()

    return {'ok': True}


@app.delete('/api/users/{user_id}')
async def deactivate_user(user_id: int, actor: dict = Depends(_require_owner_or_admin)):
    if actor['user_id'] == user_id:
        raise HTTPException(status_code=400, detail='Cannot deactivate your own account')

    async with _connect_db() as db:
        async with db.execute(
            'SELECT id, role, team_scope FROM dashboard_users WHERE id = ?', (user_id,)
        ) as cur:
            target = await cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail='User not found')
        target = row_to_dict(target)

        if actor['role'] == 'admin':
            if target['team_scope'] != actor['team_scope']:
                raise HTTPException(status_code=403, detail='Cannot deactivate users outside your team')
            if target['role'] != 'member':
                raise HTTPException(status_code=403, detail='Admin can only deactivate members')

        await db.execute('UPDATE dashboard_users SET is_active = 0 WHERE id = ?', (user_id,))
        await db.commit()

    return {'ok': True}


@app.post('/api/users/{user_id}/reset-password')
async def reset_password(
    user_id: int, body: ResetPasswordRequest, actor: dict = Depends(_require_owner_or_admin)
):
    async with _connect_db() as db:
        async with db.execute(
            'SELECT id, role, team_scope FROM dashboard_users WHERE id = ?', (user_id,)
        ) as cur:
            target = await cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail='User not found')
        target = row_to_dict(target)

        if actor['role'] == 'admin':
            if target['team_scope'] != actor['team_scope']:
                raise HTTPException(status_code=403, detail='Cannot reset password for users outside your team')
            if target['role'] != 'member':
                raise HTTPException(status_code=403, detail='Admin can only reset member passwords')

        if len(body.new_password) < 6:
            raise HTTPException(status_code=400, detail='Password must be at least 6 characters')

        hashed = _hash_password(body.new_password)
        await db.execute('UPDATE dashboard_users SET password_hash = ? WHERE id = ?', (hashed, user_id))
        await db.commit()

    return {'ok': True}


# ─── Dashboard aggregate (scoped) ─────────────────────────────────────────────

@app.get('/api/dashboard')
async def get_dashboard(user: dict = Depends(get_current_user)):
    await _require_permission(user, 'performance.view')
    today = date.today().isoformat()
    now_iso = datetime.now(UTC).isoformat()
    scope_conds, scope_params = _scope_clients(user)

    # Build client-level scope for the aggregate (no staff join in subquery)
    if user['role'] == 'owner':
        client_where = ''
        client_params: list = []
    elif user['role'] == 'admin':
        client_where = 'WHERE frontdesk_id IN (SELECT id FROM staff WHERE team = ?)'
        client_params = [user['team_scope']]
    else:
        sid = user.get('staff_id')
        if sid:
            client_where = 'WHERE frontdesk_id = ?'
            client_params = [sid]
        else:
            client_where = 'WHERE 1 = 0'
            client_params = []

    async with _connect_db() as db:
        async with db.execute(
            f"""SELECT
                COUNT(*) AS total_clients,
                SUM(CASE WHEN status IN ('new','contacted','replied','registered','training','scheduled')
                    THEN 1 ELSE 0 END) AS total_active,
                SUM(CASE WHEN DATE(created_at) = ? THEN 1 ELSE 0 END) AS today_new,
                SUM(CASE WHEN DATE(contacted_at) = ? THEN 1 ELSE 0 END) AS today_contacts,
                SUM(CASE WHEN DATE(first_order_at) = ? THEN 1 ELSE 0 END) AS today_orders,
                SUM(CASE WHEN next_followup IS NOT NULL AND next_followup < ?
                    AND status NOT IN ('ordered','withdrew','dead','blocked','scammed')
                    THEN 1 ELSE 0 END) AS overdue_followups,
                SUM(CASE WHEN status = 'ordered' THEN 1 ELSE 0 END) AS ordered_count
               FROM clients {client_where}""",
            (today, today, today, now_iso, *client_params)
        ) as cur:
            agg = row_to_dict(await cur.fetchone())

        async with db.execute(
            f'SELECT status, COUNT(*) AS cnt FROM clients {client_where} GROUP BY status',
            client_params
        ) as cur:
            by_status = {r['status']: r['cnt'] for r in await cur.fetchall()}

        deposit_where = client_where.replace('frontdesk_id', 'client_id IN (SELECT id FROM clients WHERE frontdesk_id')
        # Simpler: just subquery for scoped deposits
        if user['role'] == 'owner':
            dep_filter = ''
            dep_params: list = []
        elif user['role'] == 'admin':
            dep_filter = 'WHERE client_id IN (SELECT c.id FROM clients c JOIN staff s ON c.frontdesk_id = s.id WHERE s.team = ?)'
            dep_params = [user['team_scope']]
        else:
            sid = user.get('staff_id')
            if sid:
                dep_filter = 'WHERE client_id IN (SELECT id FROM clients WHERE frontdesk_id = ?)'
                dep_params = [sid]
            else:
                dep_filter = 'WHERE 1 = 0'
                dep_params = []

        async with db.execute(
            f"SELECT COALESCE(SUM(amount), 0) AS total FROM deposits {dep_filter} AND DATE(deposit_date) = ?"
            if dep_filter else
            "SELECT COALESCE(SUM(amount), 0) AS total FROM deposits WHERE DATE(deposit_date) = ?",
            (*dep_params, today) if dep_filter else (today,)
        ) as cur:
            today_deposits = float((await cur.fetchone())['total'])

        async with db.execute(
            f"SELECT COALESCE(SUM(amount), 0) AS total FROM deposits {dep_filter}",
            dep_params
        ) as cur:
            total_deposits = float((await cur.fetchone())['total'])

        if user['role'] == 'owner':
            staff_sql = 'SELECT COUNT(*) AS cnt FROM staff WHERE is_active = 1'
            staff_params: list = []
        elif user['role'] == 'admin':
            staff_sql = 'SELECT COUNT(*) AS cnt FROM staff WHERE is_active = 1 AND team = ?'
            staff_params = [user['team_scope']]
        else:
            sid = user.get('staff_id')
            if sid:
                staff_sql = 'SELECT COUNT(*) AS cnt FROM staff WHERE is_active = 1 AND id = ?'
                staff_params = [sid]
            else:
                staff_sql = 'SELECT 0 AS cnt'
                staff_params = []

        async with db.execute(staff_sql, staff_params) as cur:
            total_staff = (await cur.fetchone())['cnt']

    total_clients = agg['total_clients'] or 0
    ordered_count = agg['ordered_count'] or 0
    conversion_rate = round(ordered_count / max(total_clients, 1) * 100, 1)

    return {
        'total_clients': total_clients,
        'total_active': agg['total_active'] or 0,
        'total_staff': total_staff,
        'total_deposits': total_deposits,
        'today_new': agg['today_new'] or 0,
        'today_contacts': agg['today_contacts'] or 0,
        'today_orders': agg['today_orders'] or 0,
        'today_deposits': today_deposits,
        'overdue_followups': agg['overdue_followups'] or 0,
        'conversion_rate': conversion_rate,
        'by_status': by_status,
    }


# ─── Funnel (scoped) ──────────────────────────────────────────────────────────

PIPELINE_STAGES = ['new', 'contacted', 'replied', 'registered', 'training', 'ordered']


@app.get('/api/funnel')
async def get_funnel(user: dict = Depends(get_current_user)):
    if user['role'] == 'owner':
        where, params = '', []
    elif user['role'] == 'admin':
        where = 'WHERE frontdesk_id IN (SELECT id FROM staff WHERE team = ?)'
        params = [user['team_scope']]
    else:
        sid = user.get('staff_id')
        if sid:
            where, params = 'WHERE frontdesk_id = ?', [sid]
        else:
            where, params = 'WHERE 1 = 0', []

    async with _connect_db() as db:
        async with db.execute(
            f'SELECT status, COUNT(*) AS cnt FROM clients {where} GROUP BY status', params
        ) as cur:
            counts = {r['status']: r['cnt'] for r in await cur.fetchall()}

    top = counts.get('new', 0) or 1
    funnel = []
    for stage in PIPELINE_STAGES:
        cnt = counts.get(stage, 0)
        funnel.append({'stage': stage, 'count': cnt, 'pct': round(cnt / top * 100, 1)})
    return funnel


# ─── Activity feed (scoped) ───────────────────────────────────────────────────

@app.get('/api/activity')
async def get_activity(user: dict = Depends(get_current_user)):
    if user['role'] == 'owner':
        where, params = '', []
    elif user['role'] == 'admin':
        where = 'WHERE s.team = ?'
        params = [user['team_scope']]
    else:
        sid = user.get('staff_id')
        if sid:
            where, params = 'WHERE cn.staff_id = ?', [sid]
        else:
            where, params = 'WHERE 1 = 0', []

    async with _connect_db() as db:
        async with db.execute(
            f"""SELECT cn.id, cn.note_type, cn.old_status, cn.new_status, cn.content,
                      cn.created_at, s.display_name AS staff_name,
                      c.phone AS client_phone, c.id AS client_id
               FROM client_notes cn
               LEFT JOIN staff s ON cn.staff_id = s.id
               LEFT JOIN clients c ON cn.client_id = c.id
               {where}
               ORDER BY cn.created_at DESC
               LIMIT 50""",
            params
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


# ─── Staff list (scoped) ──────────────────────────────────────────────────────

@app.get('/api/staff')
async def get_staff(user: dict = Depends(get_current_user)):
    today = date.today().isoformat()

    if user['role'] == 'owner':
        staff_where = 'WHERE s.is_active = 1'
        staff_params: list = []
    elif user['role'] == 'admin':
        staff_where = 'WHERE s.is_active = 1 AND s.team = ?'
        staff_params = [user['team_scope']]
    else:
        sid = user.get('staff_id')
        if sid:
            staff_where = 'WHERE s.is_active = 1 AND s.id = ?'
            staff_params = [sid]
        else:
            return []

    async with _connect_db() as db:
        async with db.execute(
            f"""SELECT s.id, s.display_name, s.role, s.team, s.is_active, s.daily_target,
                      COALESCE(SUM(x.xp_amount), 0) AS xp_total,
                      COALESCE(st.current_streak, 0) AS current_streak
               FROM staff s
               LEFT JOIN xp_events x ON x.staff_id = s.id
               LEFT JOIN streaks st ON st.staff_id = s.id
               {staff_where}
               GROUP BY s.id
               ORDER BY xp_total DESC""",
            staff_params
        ) as cur:
            staff_rows = [row_to_dict(r) for r in await cur.fetchall()]

        if not staff_rows:
            return []

        staff_ids = [r['id'] for r in staff_rows]
        id_map = {r['id']: r for r in staff_rows}
        ph = ','.join('?' * len(staff_ids))

        async with db.execute(
            f"""SELECT frontdesk_id,
                       COUNT(*) AS total_clients,
                       SUM(CASE WHEN status = 'ordered' THEN 1 ELSE 0 END) AS total_orders
                FROM clients WHERE frontdesk_id IN ({ph})
                GROUP BY frontdesk_id""",
            staff_ids
        ) as cur:
            for r in await cur.fetchall():
                sid = r['frontdesk_id']
                id_map[sid]['total_clients'] = r['total_clients']
                id_map[sid]['total_orders'] = r['total_orders']

        async with db.execute(
            f"""SELECT staff_id, new_leads, new_orders, total_deposit
                FROM daily_stats WHERE stat_date = ? AND staff_id IN ({ph})""",
            (today, *staff_ids)
        ) as cur:
            for r in await cur.fetchall():
                sid = r['staff_id']
                id_map[sid]['today_leads'] = r['new_leads'] or 0
                id_map[sid]['today_orders'] = r['new_orders'] or 0
                id_map[sid]['today_deposit'] = float(r['total_deposit'] or 0)

    result = []
    for r in staff_rows:
        sid = r['id']
        d = id_map[sid]
        result.append({
            'id': sid,
            'display_name': d['display_name'],
            'role': d['role'],
            'team': d.get('team'),
            'is_active': d.get('is_active', 1),
            'daily_target': d.get('daily_target', 5),
            'xp_total': int(d['xp_total']),
            'current_streak': d.get('current_streak', 0) or 0,
            'total_clients': d.get('total_clients', 0) or 0,
            'total_orders': d.get('total_orders', 0) or 0,
            'today_leads': d.get('today_leads', 0),
            'today_orders': d.get('today_orders', 0),
            'today_deposit': d.get('today_deposit', 0.0),
        })
    return result


# ─── Team performance (scoped) ────────────────────────────────────────────────

@app.get('/api/team/{team}/performance')
async def get_team_performance(team: str, user: dict = Depends(get_current_user)):
    # Admin can only view their own team
    if user['role'] == 'admin' and user['team_scope'] != team:
        raise HTTPException(status_code=403, detail='Access denied to other teams')

    today = date.today().isoformat()
    async with _connect_db() as db:
        if user['role'] == 'member':
            sid = user.get('staff_id')
            if not sid:
                return {'team': team, 'members': [], 'totals': {}}
            async with db.execute(
                'SELECT id, display_name, role FROM staff WHERE team = ? AND is_active = 1 AND id = ?',
                (team, sid)
            ) as cur:
                members = [row_to_dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                'SELECT id, display_name, role FROM staff WHERE team = ? AND is_active = 1',
                (team,)
            ) as cur:
                members = [row_to_dict(r) for r in await cur.fetchall()]

        if not members:
            return {'team': team, 'members': [], 'totals': {}}

        member_ids = [m['id'] for m in members]
        ph = ','.join('?' * len(member_ids))

        async with db.execute(
            f"""SELECT staff_id, new_leads, new_orders, total_deposit
                FROM daily_stats WHERE stat_date = ? AND staff_id IN ({ph})""",
            (today, *member_ids)
        ) as cur:
            stats = {r['staff_id']: row_to_dict(r) for r in await cur.fetchall()}

        for m in members:
            s = stats.get(m['id'], {})
            m['today_leads'] = s.get('new_leads', 0) or 0
            m['today_orders'] = s.get('new_orders', 0) or 0
            m['today_deposit'] = float(s.get('total_deposit', 0) or 0)

    totals = {
        'today_leads': sum(m['today_leads'] for m in members),
        'today_orders': sum(m['today_orders'] for m in members),
        'today_deposit': sum(m['today_deposit'] for m in members),
    }
    return {'team': team, 'members': members, 'totals': totals}


# ─── Trends (scoped) ──────────────────────────────────────────────────────────

@app.get('/api/trends')
async def get_trends(user: dict = Depends(get_current_user)):
    if user['role'] == 'owner':
        client_filter, dep_filter = '', ''
        c_params: list = []
        d_params: list = []
    elif user['role'] == 'admin':
        client_filter = 'AND frontdesk_id IN (SELECT id FROM staff WHERE team = ?)'
        dep_filter = 'AND client_id IN (SELECT c.id FROM clients c JOIN staff s ON c.frontdesk_id = s.id WHERE s.team = ?)'
        c_params = [user['team_scope']]
        d_params = [user['team_scope']]
    else:
        sid = user.get('staff_id')
        if sid:
            client_filter = 'AND frontdesk_id = ?'
            dep_filter = 'AND client_id IN (SELECT id FROM clients WHERE frontdesk_id = ?)'
            c_params = [sid]
            d_params = [sid]
        else:
            client_filter = 'AND 1 = 0'
            dep_filter = 'AND 1 = 0'
            c_params = []
            d_params = []

    async with _connect_db() as db:
        async with db.execute(
            f"""SELECT DATE(created_at) AS day, COUNT(*) AS new_clients
               FROM clients
               WHERE DATE(created_at) >= DATE('now', '-30 days')
               {client_filter}
               GROUP BY day ORDER BY day""",
            c_params
        ) as cur:
            daily_new = [row_to_dict(r) for r in await cur.fetchall()]

        async with db.execute(
            f"""SELECT DATE(first_order_at) AS day, COUNT(*) AS orders
               FROM clients
               WHERE first_order_at IS NOT NULL
               AND DATE(first_order_at) >= DATE('now', '-30 days')
               {client_filter}
               GROUP BY day ORDER BY day""",
            c_params
        ) as cur:
            daily_orders = [row_to_dict(r) for r in await cur.fetchall()]

        async with db.execute(
            f"""SELECT DATE(deposit_date) AS day, COALESCE(SUM(amount), 0) AS total
               FROM deposits
               WHERE DATE(deposit_date) >= DATE('now', '-30 days')
               {dep_filter}
               GROUP BY day ORDER BY day""",
            d_params
        ) as cur:
            daily_deposits = [row_to_dict(r) for r in await cur.fetchall()]

    return {
        'daily_new': daily_new,
        'daily_orders': daily_orders,
        'daily_deposits': daily_deposits,
    }


# ─── Clients list (paginated, filterable, scoped) ─────────────────────────────

@app.get('/api/clients')
async def list_clients(
    status: Optional[str] = None,
    team: Optional[str] = None,
    staff_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, le=200),
    user: dict = Depends(get_current_user),
):
    await _require_permission(user, 'clients.view')
    conditions: list[str] = []
    params: list = []

    # Data scope: apply before user filters
    scope_conds, scope_params = _scope_clients(user)
    conditions.extend(scope_conds)
    params.extend(scope_params)

    if status:
        conditions.append('c.status = ?')
        params.append(status)
    # Admin can't bypass their team scope via team param
    if team and user['role'] == 'owner':
        conditions.append('s.team = ?')
        params.append(team)
    elif team and user['role'] == 'admin' and team == user['team_scope']:
        pass  # already scoped to their team
    if staff_id and user['role'] != 'member':
        conditions.append('c.frontdesk_id = ?')
        params.append(staff_id)
    if search:
        conditions.append('(c.phone LIKE ? OR c.source LIKE ? OR c.nickname LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    where = f'WHERE {" AND ".join(conditions)}' if conditions else ''
    offset = (page - 1) * per_page

    async with _connect_db() as db:
        async with db.execute(
            f"""SELECT COUNT(*) AS cnt FROM clients c
                LEFT JOIN staff s ON c.frontdesk_id = s.id {where}""",
            params
        ) as cur:
            total = (await cur.fetchone())['cnt']

        async with db.execute(
            f"""SELECT c.id, c.phone, c.status, c.source, c.total_deposited,
                       c.created_at, c.contacted_at, c.replied_at, c.registered_at,
                       c.training_at, c.first_order_at, c.next_followup,
                       c.first_day_status, c.second_day_status,
                       s.display_name AS frontdesk_name, s.team
                FROM clients c
                LEFT JOIN staff s ON c.frontdesk_id = s.id
                {where}
                ORDER BY c.created_at DESC LIMIT ? OFFSET ?""",
            (*params, per_page, offset)
        ) as cur:
            clients = [row_to_dict(r) for r in await cur.fetchall()]

    return {'total': total, 'page': page, 'per_page': per_page, 'clients': clients}


# ─── Client detail (scoped) ───────────────────────────────────────────────────

@app.get('/api/clients/{client_id}')
async def get_client_detail(client_id: int, user: dict = Depends(get_current_user)):
    await _require_permission(user, 'clients.view')
    async with _connect_db() as db:
        async with db.execute(
            """SELECT c.id, c.phone, c.status, c.source, c.total_deposited,
                      c.created_at, c.contacted_at, c.replied_at, c.registered_at,
                      c.training_at, c.first_order_at, c.next_followup,
                      c.first_day_status, c.second_day_status,
                      s.display_name AS frontdesk_name, s.team, c.frontdesk_id,
                      s.team AS staff_team
               FROM clients c
               LEFT JOIN staff s ON c.frontdesk_id = s.id
               WHERE c.id = ?""",
            (client_id,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail='Client not found')
        client = row_to_dict(row)

        # Scope check
        if user['role'] == 'admin' and client.get('staff_team') != user['team_scope']:
            raise HTTPException(status_code=403, detail='Access denied')
        if user['role'] == 'member':
            sid = user.get('staff_id')
            if client.get('frontdesk_id') != sid:
                raise HTTPException(status_code=403, detail='Access denied')

        async with db.execute(
            """SELECT cn.id, cn.content, cn.note_type, cn.old_status, cn.new_status,
                      cn.created_at, s.display_name AS staff_name
               FROM client_notes cn
               LEFT JOIN staff s ON cn.staff_id = s.id
               WHERE cn.client_id = ?
               ORDER BY cn.created_at DESC LIMIT 50""",
            (client_id,)
        ) as cur:
            client['notes'] = [row_to_dict(r) for r in await cur.fetchall()]

        async with db.execute(
            """SELECT id, amount, currency, platform, deposit_date
               FROM deposits WHERE client_id = ?
               ORDER BY deposit_date DESC""",
            (client_id,)
        ) as cur:
            client['deposits'] = [row_to_dict(r) for r in await cur.fetchall()]

    # Remove internal fields before returning
    client.pop('frontdesk_id', None)
    client.pop('staff_team', None)
    return client


# ─── Export clients CSV (scoped) ──────────────────────────────────────────────

@app.get('/api/export/clients')
async def export_clients(
    status: Optional[str] = None,
    team: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    await _require_permission(user, 'reports.export')
    conditions: list[str] = []
    params: list = []
    scope_conds, scope_params = _scope_clients(user)
    conditions.extend(scope_conds)
    params.extend(scope_params)

    if status:
        conditions.append('c.status = ?')
        params.append(status)
    if team and user['role'] == 'owner':
        conditions.append('s.team = ?')
        params.append(team)

    where = f'WHERE {" AND ".join(conditions)}' if conditions else ''

    async with _connect_db() as db:
        async with db.execute(
            f"""SELECT c.id, c.phone, c.status, c.source, c.total_deposited,
                       c.created_at, c.contacted_at, c.replied_at, c.registered_at,
                       c.training_at, c.first_order_at,
                       s.display_name AS frontdesk_name, s.team
                FROM clients c
                LEFT JOIN staff s ON c.frontdesk_id = s.id
                {where} ORDER BY c.created_at DESC""",
            params
        ) as cur:
            rows = [row_to_dict(r) for r in await cur.fetchall()]

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write('No data\n')

    output.seek(0)
    fname = f'clients_{date.today().isoformat()}.csv'
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename={fname}'},
    )


# ─── Export report CSV (scoped) ───────────────────────────────────────────────

@app.get('/api/export/report')
async def export_report(
    period: str = Query(default='daily', pattern='^(daily|weekly|monthly)$'),
    user: dict = Depends(get_current_user),
):
    await _require_permission(user, 'reports.export')
    today = date.today().isoformat()

    if user['role'] == 'owner':
        scope_where = ''
        scope_params: list = []
    elif user['role'] == 'admin':
        scope_where = 'AND s.team = ?'
        scope_params = [user['team_scope']]
    else:
        sid = user.get('staff_id')
        if sid:
            scope_where = 'AND ds.staff_id = ?'
            scope_params = [sid]
        else:
            scope_where = 'AND 1 = 0'
            scope_params = []

    async with _connect_db() as db:
        if period == 'daily':
            async with db.execute(
                f"""SELECT s.display_name, s.team, ds.new_leads, ds.contacted,
                          ds.replied, ds.registered, ds.new_orders, ds.total_deposit,
                          ds.reply_rate, ds.conversion_rate
                   FROM daily_stats ds
                   JOIN staff s ON ds.staff_id = s.id
                   WHERE ds.stat_date = ?
                   {scope_where}
                   ORDER BY ds.new_orders DESC""",
                (today, *scope_params)
            ) as cur:
                rows = [row_to_dict(r) for r in await cur.fetchall()]
        else:
            days = 7 if period == 'weekly' else 30
            async with db.execute(
                f"""SELECT s.display_name, s.team,
                           SUM(ds.new_leads) AS new_leads,
                           SUM(ds.contacted) AS contacted,
                           SUM(ds.replied) AS replied,
                           SUM(ds.registered) AS registered,
                           SUM(ds.new_orders) AS new_orders,
                           SUM(ds.total_deposit) AS total_deposit
                   FROM daily_stats ds
                   JOIN staff s ON ds.staff_id = s.id
                   WHERE ds.stat_date >= DATE('now', '-{days} days')
                   {scope_where}
                   GROUP BY ds.staff_id
                   ORDER BY new_orders DESC""",
                scope_params
            ) as cur:
                rows = [row_to_dict(r) for r in await cur.fetchall()]

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write('No data\n')

    output.seek(0)
    fname = f'report_{period}_{today}.csv'
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename={fname}'},
    )


# ─── Phase 16: Phone Registry API ────────────────────────────────────────────

import re as _re


def _normalize_phone(phone: str) -> str:
    return _re.sub(r'[^\d]', '', phone)


class PhoneOverrideRequest(BaseModel):
    new_submitter: str
    new_staff_id: Optional[int] = None


@app.get('/api/phone-registry/lookup')
async def phone_registry_lookup(
    phone: str = Query(..., min_length=1),
    user: dict = Depends(get_current_user),
):
    """Look up a phone number in the registry."""
    await _require_permission(user, 'phone.lookup')
    normalized = _normalize_phone(phone)
    async with _connect_db() as db:
        async with db.execute(
            """SELECT id, phone, phone_normalized, submitter_name,
                      submitter_staff_id, source, submitted_at, created_at
               FROM phone_registry WHERE phone_normalized = ?""",
            (normalized,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            # Fallback: check chat_export_phones
            try:
                async with db.execute(
                    """SELECT phone, phone_normalized, submitter_name,
                              submitter_tg_id, first_submitted_at, last_submitted_at,
                              message_count, is_duplicate_flagged, staff_id
                       FROM chat_export_phones
                       WHERE phone_normalized = ?
                       ORDER BY first_submitted_at ASC LIMIT 1""",
                    (normalized,)
                ) as cur:
                    export_row = await cur.fetchone()
                if export_row:
                    er = row_to_dict(export_row)
                    return {
                        'found': True,
                        'phone': er.get('phone', phone),
                        'phone_normalized': er.get('phone_normalized', normalized),
                        'submitter_name': er.get('submitter_name', 'Unknown'),
                        'submitter_staff_id': er.get('staff_id'),
                        'source': 'chat_export',
                        'submitted_at': er.get('first_submitted_at'),
                        'duplicate_flagged': bool(er.get('is_duplicate_flagged', 0)),
                        'message_count': er.get('message_count', 1),
                        'linked_clients': [],
                        'log': [],
                    }
            except Exception:
                pass
            return {'found': False, 'phone': phone}

        entry = row_to_dict(row)

        # Get linked clients
        async with db.execute(
            'SELECT id, phone, status, frontdesk_id FROM clients WHERE phone LIKE ?',
            (f'%{normalized[-8:]}%',)
        ) as cur:
            clients = [row_to_dict(r) for r in await cur.fetchall()]

        # Get log
        async with db.execute(
            """SELECT id, action, actor_name, details, created_at
               FROM phone_registry_log
               WHERE phone_normalized = ?
               ORDER BY created_at DESC LIMIT 20""",
            (normalized,)
        ) as cur:
            log = [row_to_dict(r) for r in await cur.fetchall()]

    entry['found'] = True
    entry['linked_clients'] = clients
    entry['history'] = log
    entry['log'] = log  # alias for frontend compatibility
    return entry


@app.get('/api/phone-registry/search')
async def phone_registry_search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """Search phone registry by number or submitter."""
    await _require_permission(user, 'phone.lookup')
    normalized = _normalize_phone(q)
    offset = (page - 1) * per_page
    async with _connect_db() as db:
        async with db.execute(
            """SELECT COUNT(*) AS cnt FROM phone_registry
               WHERE phone_normalized LIKE ? OR submitter_name LIKE ?""",
            (f'%{normalized}%', f'%{q}%')
        ) as cur:
            total = (await cur.fetchone())['cnt']

        async with db.execute(
            """SELECT id, phone, phone_normalized, submitter_name,
                      submitter_staff_id, source, submitted_at
               FROM phone_registry
               WHERE phone_normalized LIKE ? OR submitter_name LIKE ?
               ORDER BY submitted_at DESC
               LIMIT ? OFFSET ?""",
            (f'%{normalized}%', f'%{q}%', per_page, offset)
        ) as cur:
            results = [row_to_dict(r) for r in await cur.fetchall()]

    return {'total': total, 'page': page, 'per_page': per_page, 'results': results}


@app.get('/api/phone-registry/stats')
async def phone_registry_stats(user: dict = Depends(get_current_user)):
    """Get phone registry statistics."""
    async with _connect_db() as db:
        async with db.execute('SELECT COUNT(*) AS cnt FROM phone_registry') as cur:
            total = (await cur.fetchone())['cnt']
        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM phone_registry_log WHERE action = 'duplicate_blocked'"
        ) as cur:
            duplicates = (await cur.fetchone())['cnt']
        async with db.execute(
            'SELECT source, COUNT(*) AS cnt FROM phone_registry GROUP BY source'
        ) as cur:
            by_source = {r['source']: r['cnt'] for r in await cur.fetchall()}
        # Include chat export stats
        chat_export_total = 0
        chat_export_flagged = 0
        try:
            async with db.execute('SELECT COUNT(DISTINCT phone_normalized) AS cnt FROM chat_export_phones') as cur:
                chat_export_total = (await cur.fetchone())['cnt']
            async with db.execute('SELECT COUNT(*) AS cnt FROM chat_export_phones WHERE is_duplicate_flagged = 1') as cur:
                chat_export_flagged = (await cur.fetchone())['cnt']
        except Exception:
            pass
    return {
        'total': total, 'total_registered': total + chat_export_total,
        'duplicates_blocked': duplicates + chat_export_flagged,
        'by_source': by_source,
        'chat_export_phones': chat_export_total,
        'chat_export_duplicates': chat_export_flagged,
    }


@app.post('/api/phone-registry/override')
async def phone_registry_override(
    phone: str = Query(...),
    body: PhoneOverrideRequest = ...,
    user: dict = Depends(_require_owner_or_admin),
):
    """Override phone number ownership. Owner/Admin only."""
    normalized = _normalize_phone(phone)
    async with _connect_db() as db:
        async with db.execute(
            'SELECT submitter_name FROM phone_registry WHERE phone_normalized = ?',
            (normalized,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Phone not in registry')

        old_owner = row['submitter_name']
        import json as _json
        await db.execute(
            'UPDATE phone_registry SET submitter_name = ?, submitter_staff_id = ? WHERE phone_normalized = ?',
            (body.new_submitter, body.new_staff_id, normalized)
        )
        await db.execute(
            """INSERT INTO phone_registry_log
               (phone_normalized, action, actor_name, actor_staff_id, details)
               VALUES (?, 'admin_override', ?, ?, ?)""",
            (normalized, user['display_name'], user.get('staff_id'),
             _json.dumps({'previous_owner': old_owner, 'new_owner': body.new_submitter}))
        )
        await db.commit()

    # Phase 24: Audit log
    await _audit(user, 'update', 'phone_registry', None,
                 old_values={'submitter_name': old_owner, 'phone': normalized},
                 new_values={'submitter_name': body.new_submitter, 'staff_id': body.new_staff_id})

    return {'ok': True}


# ─── Phase 16: Client Links API ─────────────────────────────────────────────


class GlobalClientLinkRequest(BaseModel):
    client_id_a: int
    client_id_b: int
    link_type: str = 'related'
    note: Optional[str] = None

@app.post('/api/client-links')
async def create_client_link_global(body: GlobalClientLinkRequest, user: dict = Depends(get_current_user)):
    valid_types = ('related', 'same_person', 'referral', 'family')
    if body.link_type not in valid_types:
        raise HTTPException(status_code=400, detail=f'Invalid link_type. Valid: {valid_types}')

    a, b = min(body.client_id_a, body.client_id_b), max(body.client_id_a, body.client_id_b)
    async with _connect_db() as db:
        try:
            await db.execute(
                'INSERT INTO client_links (client_id_a, client_id_b, link_type, note, created_by) VALUES (?, ?, ?, ?, ?)',
                (a, b, body.link_type, body.note, user.get('user_id'))
            )
            await db.commit()
        except Exception:
            raise HTTPException(status_code=409, detail='Link already exists')
    return {'ok': True}

class ClientLinkRequest(BaseModel):
    linked_client_id: int
    link_type: str = 'related'
    note: Optional[str] = None


@app.get('/api/clients/{client_id}/links')
async def get_client_links(client_id: int, user: dict = Depends(get_current_user)):
    """Get all links for a client."""
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        async with db.execute(
            """SELECT cl.id, cl.client_id_a, cl.client_id_b, cl.link_type,
                      cl.note, cl.created_at,
                      ca.phone AS phone_a, cb.phone AS phone_b,
                      ca.status AS status_a, cb.status AS status_b,
                      sa.display_name AS name_a, sb.display_name AS name_b
               FROM client_links cl
               JOIN clients ca ON cl.client_id_a = ca.id
               JOIN clients cb ON cl.client_id_b = cb.id
               LEFT JOIN staff sa ON ca.frontdesk_id = sa.id
               LEFT JOIN staff sb ON cb.frontdesk_id = sb.id
               WHERE cl.client_id_a = ? OR cl.client_id_b = ?
               ORDER BY cl.created_at DESC""",
            (client_id, client_id)
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


@app.post('/api/clients/{client_id}/links')
async def create_client_link(client_id: int, body: ClientLinkRequest, user: dict = Depends(get_current_user)):
    """Create a link between two clients."""
    valid_types = ('related', 'same_person', 'referral', 'family')
    if body.link_type not in valid_types:
        raise HTTPException(status_code=400, detail=f'Invalid link_type. Valid: {valid_types}')

    a, b = min(client_id, body.linked_client_id), max(client_id, body.linked_client_id)
    async with _connect_db() as db:
        try:
            await db.execute(
                'INSERT INTO client_links (client_id_a, client_id_b, link_type, note, created_by) VALUES (?, ?, ?, ?, ?)',
                (a, b, body.link_type, body.note, user.get('user_id'))
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail='Link already exists')
    return {'ok': True}


@app.delete('/api/clients/{client_id}/links/{linked_client_id}')
async def delete_client_link(client_id: int, linked_client_id: int, user: dict = Depends(get_current_user)):
    """Delete a client link."""
    a, b = min(client_id, linked_client_id), max(client_id, linked_client_id)
    async with _connect_db() as db:
        cur = await db.execute('DELETE FROM client_links WHERE client_id_a = ? AND client_id_b = ?', (a, b))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Link not found')
    return {'ok': True}


@app.delete('/api/client-links/{link_id}')
async def delete_client_link_by_id(link_id: int, user: dict = Depends(get_current_user)):
    """Delete a client link by link row ID."""
    async with _connect_db() as db:
        cur = await db.execute('DELETE FROM client_links WHERE id = ?', (link_id,))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Link not found')
    return {'ok': True}


# ─── Phase 16: Permission Overrides API ─────────────────────────────────────

class PermissionOverrideRequest(BaseModel):
    staff_id: int
    command: str
    allowed: bool
    reason: Optional[str] = None


@app.get('/api/permissions/{staff_id}')
async def get_staff_permissions(staff_id: int, user: dict = Depends(get_current_user)):
    """Get permission overrides for a staff member."""
    # RBAC: admin can only see staff in their team
    if user['role'] == 'admin':
        async with _connect_db() as db:
            async with db.execute('SELECT team FROM staff WHERE id = ?', (staff_id,)) as cur:
                row = await cur.fetchone()
            if not row or row['team'] != user['team_scope']:
                raise HTTPException(status_code=403, detail='Access denied')

    async with _connect_db() as db:
        async with db.execute(
            """SELECT s.id, s.display_name, s.role, s.team
               FROM staff s WHERE s.id = ?""",
            (staff_id,)
        ) as cur:
            staff_row = await cur.fetchone()
        if not staff_row:
            raise HTTPException(status_code=404, detail='Staff not found')

        async with db.execute(
            """SELECT po.id, po.command, po.allowed, po.reason,
                      po.created_at, po.updated_at,
                      gs.display_name AS granted_by_name
               FROM permission_overrides po
               LEFT JOIN staff gs ON po.granted_by = gs.id
               WHERE po.staff_id = ?
               ORDER BY po.command""",
            (staff_id,)
        ) as cur:
            overrides = [row_to_dict(r) for r in await cur.fetchall()]

    return {
        'staff': row_to_dict(staff_row),
        'overrides': overrides,
    }


@app.get('/api/permissions')
async def list_all_permissions(user: dict = Depends(_require_owner_or_admin)):
    """List all permission overrides. Owner/Admin only."""
    async with _connect_db() as db:
        if user['role'] == 'owner':
            where, params = '', []
        else:
            where = 'WHERE s.team = ?'
            params = [user['team_scope']]

        async with db.execute(
            f"""SELECT s.id AS staff_id, s.display_name, s.role, s.team,
                       po.id AS override_id, po.command, po.allowed, po.reason
               FROM staff s
               LEFT JOIN permission_overrides po ON po.staff_id = s.id
               {where}
               ORDER BY s.display_name, po.command""",
            params
        ) as cur:
            rows = [row_to_dict(r) for r in await cur.fetchall()]

    # Group by staff
    staff_map: dict = {}
    for r in rows:
        sid = r['staff_id']
        if sid not in staff_map:
            staff_map[sid] = {
                'id': sid,
                'display_name': r['display_name'],
                'role': r['role'],
                'team': r['team'],
                'overrides': [],
            }
        if r.get('override_id'):
            staff_map[sid]['overrides'].append({
                'id': r['override_id'],
                'command': r['command'],
                'allowed': r['allowed'],
                'reason': r['reason'],
            })

    return list(staff_map.values())


@app.post('/api/permissions')
async def set_permission_override(
    body: PermissionOverrideRequest,
    user: dict = Depends(_require_owner_or_admin),
):
    """Set or update a permission override."""
    # RBAC: admin can only manage staff in their team
    if user['role'] == 'admin':
        async with _connect_db() as db:
            async with db.execute('SELECT team FROM staff WHERE id = ?', (body.staff_id,)) as cur:
                row = await cur.fetchone()
            if not row or row['team'] != user['team_scope']:
                raise HTTPException(status_code=403, detail='Cannot manage permissions for staff outside your team')

    cmd = body.command.lstrip('/')
    async with _connect_db() as db:
        await db.execute(
            """INSERT INTO permission_overrides
               (staff_id, command, allowed, granted_by, reason)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(staff_id, command)
               DO UPDATE SET allowed = excluded.allowed,
                             granted_by = excluded.granted_by,
                             reason = excluded.reason,
                             updated_at = CURRENT_TIMESTAMP""",
            (body.staff_id, cmd, body.allowed, user.get('staff_id'), body.reason)
        )
        await db.commit()
    return {'ok': True}


@app.delete('/api/permissions/{staff_id}/{command}')
async def delete_permission_override(
    staff_id: int,
    command: str,
    user: dict = Depends(_require_owner_or_admin),
):
    """Remove a permission override."""
    async with _connect_db() as db:
        # RBAC: admin can only manage staff in their team
        if user['role'] == 'admin':
            async with db.execute('SELECT team FROM staff WHERE id = ?', (staff_id,)) as cur:
                staff_row = await cur.fetchone()
            if not staff_row:
                raise HTTPException(status_code=404, detail='Staff not found')
            if staff_row['team'] != user.get('team_scope'):
                raise HTTPException(status_code=403, detail='Cannot manage permissions outside your team')

        cur = await db.execute(
            'DELETE FROM permission_overrides WHERE staff_id = ? AND command = ?',
            (staff_id, command)
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Override not found')
    return {'ok': True}


# ─── Phase 16.5: Client Notes API ────────────────────────────────────────────

class AddNoteRequest(BaseModel):
    content: str
    note_type: str = 'comment'
    phone_normalized: Optional[str] = None


@app.post('/api/clients/{client_id}/notes')
async def add_client_note(
    client_id: int,
    body: AddNoteRequest,
    user: dict = Depends(get_current_user),
):
    """Add a comment/note to a client record."""
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        async with db.execute('SELECT id FROM clients WHERE id = ?', (client_id,)) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail='Client not found')

        valid_types = ('comment', 'status_change', 'flag', 'link_note')
        if body.note_type not in valid_types:
            raise HTTPException(status_code=400, detail=f'Invalid note_type. Valid: {valid_types}')

        await db.execute(
            """INSERT INTO client_notes
               (client_id, staff_id, note_type, content, author_name, phone_normalized)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (client_id, user.get('staff_id'), body.note_type,
             body.content, user['display_name'], body.phone_normalized)
        )
        await db.commit()
    return {'ok': True}


@app.get('/api/clients/{client_id}/notes')
async def get_client_notes(client_id: int, user: dict = Depends(get_current_user)):
    """Get all notes for a client."""
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        async with db.execute(
            """SELECT cn.id, cn.note_type, cn.old_status, cn.new_status,
                      cn.content, cn.author_name, cn.phone_normalized,
                      cn.created_at, s.display_name AS staff_name
               FROM client_notes cn
               LEFT JOIN staff s ON cn.staff_id = s.id
               WHERE cn.client_id = ?
               ORDER BY cn.created_at DESC LIMIT 100""",
            (client_id,)
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


@app.get('/api/clients/{client_id}/timeline')
async def get_client_timeline(client_id: int, user: dict = Depends(get_current_user)):
    """Unified timeline: notes + status changes + links + events."""
    items = []
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        # Notes and status changes
        async with db.execute(
            """SELECT cn.id, 'note' AS timeline_type, cn.note_type,
                      cn.old_status, cn.new_status, cn.content,
                      cn.created_at, cn.author_name,
                      s.display_name AS staff_name
               FROM client_notes cn
               LEFT JOIN staff s ON cn.staff_id = s.id
               WHERE cn.client_id = ?
               ORDER BY cn.created_at DESC LIMIT 100""",
            (client_id,)
        ) as cur:
            items.extend([row_to_dict(r) for r in await cur.fetchall()])

        # Client links
        async with db.execute(
            """SELECT cl.id, 'link' AS timeline_type,
                      cl.link_type AS note_type, cl.note AS content,
                      cl.created_at,
                      s.display_name AS staff_name,
                      ca.phone AS phone_a, cb.phone AS phone_b
               FROM client_links cl
               JOIN clients ca ON cl.client_id_a = ca.id
               JOIN clients cb ON cl.client_id_b = cb.id
               LEFT JOIN staff s ON cl.created_by = s.id
               WHERE cl.client_id_a = ? OR cl.client_id_b = ?
               ORDER BY cl.created_at DESC""",
            (client_id, client_id)
        ) as cur:
            items.extend([row_to_dict(r) for r in await cur.fetchall()])

    items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return items[:100]


# ─── Phase 16.5: Performance Dashboard API ──────────────────────────────────

@app.get('/api/performance/daily')
async def get_performance_daily(
    date: str = Query(default=None),
    team: str = Query(default='all'),
    user: dict = Depends(get_current_user),
):
    """Daily performance stats per frontdesk."""
    from datetime import date as date_type
    stat_date = date or date_type.today().isoformat()

    # Scope enforcement
    if user['role'] == 'admin' and team != user['team_scope'] and team != 'all':
        raise HTTPException(status_code=403, detail='Access denied to other teams')

    effective_team = team
    if user['role'] == 'admin' and team == 'all':
        effective_team = user['team_scope']
    elif user['role'] == 'member':
        # Member: only their own stats
        pass

    async with _connect_db() as db:
        sql = """SELECT s.id AS staff_id, s.display_name, s.team,
                        COALESCE(ds.new_leads, 0) AS new_leads,
                        COALESCE(ds.contacted, 0) AS contacted,
                        COALESCE(ds.replied, 0) AS replied,
                        COALESCE(ds.registered, 0) AS registered,
                        COALESCE(ds.training, 0) AS training,
                        COALESCE(ds.withdrew, 0) AS withdrew,
                        COALESCE(ds.new_orders, 0) AS new_orders,
                        COALESCE(ds.ghosted, 0) AS ghosted,
                        COALESCE(ds.dead, 0) AS dead,
                        COALESCE(ds.total_deposit, 0) AS total_deposit
                 FROM staff s
                 LEFT JOIN daily_stats ds ON s.id = ds.staff_id AND ds.stat_date = ?
                 WHERE s.is_active = 1
                   AND s.role IN ('frontdesk', 'newbie', 'customer_service')"""
        params: list = [stat_date]

        if user['role'] == 'member':
            sql += ' AND s.id = ?'
            params.append(user.get('staff_id'))
        elif effective_team and effective_team != 'all':
            sql += ' AND s.team = ?'
            params.append(effective_team)

        sql += ' ORDER BY new_orders DESC, new_leads DESC'
        async with db.execute(sql, params) as cur:
            rows = [row_to_dict(r) for r in await cur.fetchall()]

    # Compute rates
    for d in rows:
        nl = d.get('new_leads', 0) or 0
        rp = d.get('replied', 0) or 0
        reg = d.get('registered', 0) or 0
        no = d.get('new_orders', 0) or 0
        tr = d.get('training', 0) or 0
        d['reply_rate'] = round(rp / max(nl, 1) * 100, 1)
        d['registration_rate'] = round(reg / max(rp, 1) * 100, 1)
        d['training_rate'] = round(tr / max(reg, 1) * 100, 1)
        d['conversion_rate'] = round(no / max(nl, 1) * 100, 1)

    # Team totals
    totals = {}
    for key in ['new_leads', 'contacted', 'replied', 'registered', 'training',
                'withdrew', 'new_orders', 'ghosted', 'dead', 'total_deposit']:
        totals[key] = sum(d.get(key, 0) or 0 for d in rows)
    tnl = totals.get('new_leads', 0) or 0
    trp = totals.get('replied', 0) or 0
    treg = totals.get('registered', 0) or 0
    tno = totals.get('new_orders', 0) or 0
    ttr = totals.get('training', 0) or 0
    totals['reply_rate'] = round(trp / max(tnl, 1) * 100, 1)
    totals['registration_rate'] = round(treg / max(trp, 1) * 100, 1)
    totals['training_rate'] = round(ttr / max(treg, 1) * 100, 1)
    totals['conversion_rate'] = round(tno / max(tnl, 1) * 100, 1)
    totals['total_deposit'] = round(totals.get('total_deposit', 0), 2)

    return {'date': stat_date, 'team': team, 'staff': rows, 'totals': totals}


@app.get('/api/performance/summary')
async def get_performance_summary(
    date_from: str = Query(..., alias='from'),
    date_to: str = Query(..., alias='to'),
    team: str = Query(default='all'),
    user: dict = Depends(get_current_user),
):
    """Performance summary over a date range."""
    if user['role'] == 'admin' and team != user['team_scope'] and team != 'all':
        raise HTTPException(status_code=403, detail='Access denied')

    effective_team = team
    if user['role'] == 'admin' and team == 'all':
        effective_team = user['team_scope']

    async with _connect_db() as db:
        sql = """SELECT s.id AS staff_id, s.display_name, s.team,
                        COALESCE(SUM(ds.new_leads), 0) AS new_leads,
                        COALESCE(SUM(ds.contacted), 0) AS contacted,
                        COALESCE(SUM(ds.replied), 0) AS replied,
                        COALESCE(SUM(ds.registered), 0) AS registered,
                        COALESCE(SUM(ds.training), 0) AS training,
                        COALESCE(SUM(ds.withdrew), 0) AS withdrew,
                        COALESCE(SUM(ds.new_orders), 0) AS new_orders,
                        COALESCE(SUM(ds.ghosted), 0) AS ghosted,
                        COALESCE(SUM(ds.dead), 0) AS dead,
                        COALESCE(SUM(ds.total_deposit), 0) AS total_deposit
                 FROM staff s
                 LEFT JOIN daily_stats ds ON s.id = ds.staff_id
                      AND ds.stat_date >= ? AND ds.stat_date <= ?
                 WHERE s.is_active = 1
                   AND s.role IN ('frontdesk', 'newbie', 'customer_service')"""
        params: list = [date_from, date_to]

        if user['role'] == 'member':
            sql += ' AND s.id = ?'
            params.append(user.get('staff_id'))
        elif effective_team and effective_team != 'all':
            sql += ' AND s.team = ?'
            params.append(effective_team)

        sql += ' GROUP BY s.id ORDER BY new_orders DESC, new_leads DESC'
        async with db.execute(sql, params) as cur:
            rows = [row_to_dict(r) for r in await cur.fetchall()]

    for d in rows:
        nl = d.get('new_leads', 0) or 0
        rp = d.get('replied', 0) or 0
        reg = d.get('registered', 0) or 0
        no = d.get('new_orders', 0) or 0
        tr = d.get('training', 0) or 0
        d['reply_rate'] = round(rp / max(nl, 1) * 100, 1)
        d['registration_rate'] = round(reg / max(rp, 1) * 100, 1)
        d['training_rate'] = round(tr / max(reg, 1) * 100, 1)
        d['conversion_rate'] = round(no / max(nl, 1) * 100, 1)
        d['total_deposit'] = round(d.get('total_deposit', 0) or 0, 2)

    return {'from': date_from, 'to': date_to, 'team': team, 'staff': rows}


# ─── Phase 17: Auto-Recalculate Daily Stats ──────────────────────────────────

@app.post('/api/performance/recalculate')
async def recalculate_daily_stats(
    user: dict = Depends(_require_owner_or_admin),
):
    """Recalculate daily_stats from client data for all active staff (today)."""
    from datetime import date as date_type
    today = date_type.today().isoformat()
    updated = 0
    async with _connect_db() as db:
        async with db.execute(
            "SELECT id, display_name, team FROM staff WHERE is_active = 1"
        ) as cur:
            staff_list = [row_to_dict(r) for r in await cur.fetchall()]

        for s in staff_list:
            sid = s['id']
            # Count clients by status created/updated today
            counts = {}
            for status_name in ['new', 'contacted', 'replied', 'registered', 'training',
                                'withdrew', 'ordered', 'ghosted', 'blocked', 'dead']:
                col_map = {
                    'new': 'created_at', 'contacted': 'contacted_at', 'replied': 'replied_at',
                    'registered': 'registered_at', 'training': 'training_at',
                    'withdrew': 'withdrew_at', 'ordered': 'first_order_at',
                }
                if status_name in ('ghosted', 'blocked', 'dead'):
                    async with db.execute(
                        f"SELECT COUNT(*) FROM clients WHERE frontdesk_id = ? AND status = ?",
                        (sid, status_name)
                    ) as c:
                        counts[status_name] = (await c.fetchone())[0]
                else:
                    date_col = col_map.get(status_name, 'created_at')
                    async with db.execute(
                        f"SELECT COUNT(*) FROM clients WHERE frontdesk_id = ? AND DATE({date_col}) = ?",
                        (sid, today)
                    ) as c:
                        counts[status_name] = (await c.fetchone())[0]

            # Get total deposit for today
            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE frontdesk_id = ? AND DATE(deposit_date) = ?",
                (sid, today)
            ) as c:
                total_dep = (await c.fetchone())[0]

            nl = counts.get('new', 0)
            rp = counts.get('replied', 0)
            reg = counts.get('registered', 0)
            no = counts.get('ordered', 0)
            reply_rate = round(rp / max(nl, 1) * 100, 2)
            conv_rate = round(no / max(reg, 1) * 100, 2)

            await db.execute(
                """INSERT INTO daily_stats
                   (staff_id, stat_date, new_leads, contacted, replied, registered,
                    training, withdrew, new_orders, ghosted, blocked, dead,
                    reply_rate, conversion_rate, total_deposit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(staff_id, stat_date)
                   DO UPDATE SET new_leads=excluded.new_leads, contacted=excluded.contacted,
                     replied=excluded.replied, registered=excluded.registered,
                     training=excluded.training, withdrew=excluded.withdrew,
                     new_orders=excluded.new_orders, ghosted=excluded.ghosted,
                     blocked=excluded.blocked, dead=excluded.dead,
                     reply_rate=excluded.reply_rate, conversion_rate=excluded.conversion_rate,
                     total_deposit=excluded.total_deposit""",
                (sid, today, nl, counts.get('contacted', 0), rp, reg,
                 counts.get('training', 0), counts.get('withdrew', 0), no,
                 counts.get('ghosted', 0), counts.get('blocked', 0), counts.get('dead', 0),
                 reply_rate, conv_rate, total_dep)
            )
            updated += 1
        await db.commit()
    return {'ok': True, 'date': today, 'staff_updated': updated}


# ─── Phase 17: Staff Management API ──────────────────────────────────────────

class UpdateStaffRequest(BaseModel):
    team: Optional[str] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    daily_target: Optional[int] = None
    is_active: Optional[bool] = None


@app.put('/api/staff/{staff_id}')
async def update_staff(
    staff_id: int,
    body: UpdateStaffRequest,
    user: dict = Depends(_require_owner_or_admin),
):
    """Update staff member (team, role, name, target, active status). Owner/Admin only."""
    valid_roles = ('frontdesk', 'maintenance', 'manager', 'admin', 'leader',
                   'customer_service', 'newbie', 'viewer')

    async with _connect_db() as db:
        async with db.execute('SELECT id, team, role FROM staff WHERE id = ?', (staff_id,)) as cur:
            staff = await cur.fetchone()
        if not staff:
            raise HTTPException(status_code=404, detail='Staff not found')

        # Admin can only modify staff in their team
        if user['role'] == 'admin':
            if staff['team'] and staff['team'] != user['team_scope']:
                raise HTTPException(status_code=403, detail='Cannot modify staff outside your team')
            if staff['role'] in ('admin', 'leader', 'manager', 'maintenance'):
                raise HTTPException(status_code=403, detail='Cannot modify staff at or above your level')

        updates = []
        params = []
        if body.team is not None:
            updates.append('team = ?')
            params.append(body.team)
        if body.role is not None:
            if body.role not in valid_roles:
                raise HTTPException(status_code=400, detail=f'Invalid role. Valid: {valid_roles}')
            # Only owner can set admin/leader/manager roles
            if body.role in ('admin', 'leader', 'manager') and user['role'] != 'owner':
                raise HTTPException(status_code=403, detail='Only owner can assign admin/leader roles')
            updates.append('role = ?')
            params.append(body.role)
        if body.display_name is not None:
            updates.append('display_name = ?')
            params.append(body.display_name)
        if body.daily_target is not None:
            updates.append('daily_target = ?')
            params.append(body.daily_target)
        if body.is_active is not None:
            updates.append('is_active = ?')
            params.append(int(body.is_active))

        if not updates:
            raise HTTPException(status_code=400, detail='No fields to update')

        old_values = {'team': staff['team'], 'role': staff['role']}
        params.append(staff_id)
        await db.execute(f"UPDATE staff SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()

    # Phase 24: Audit log
    new_vals = {}
    if body.team is not None:
        new_vals['team'] = body.team
    if body.role is not None:
        new_vals['role'] = body.role
    if body.display_name is not None:
        new_vals['display_name'] = body.display_name
    if body.daily_target is not None:
        new_vals['daily_target'] = body.daily_target
    if body.is_active is not None:
        new_vals['is_active'] = body.is_active
    await _audit(user, 'update', 'staff', staff_id,
                 old_values=old_values, new_values=new_vals)

    return {'ok': True}


@app.get('/api/staff/all')
async def list_all_staff(user: dict = Depends(get_current_user)):
    """List all staff with team/role info. Scoped by role."""
    async with _connect_db() as db:
        where = 'WHERE s.is_active = 1'
        params: list = []
        if user['role'] == 'admin':
            # Admin sees their team + unassigned
            where += ' AND (s.team = ? OR s.team IS NULL)'
            params.append(user['team_scope'])
        elif user['role'] == 'member':
            where += ' AND s.team = ?'
            params.append(user.get('team_scope', ''))

        async with db.execute(
            f"""SELECT s.id, s.display_name, s.role, s.team, s.tg_username,
                       s.daily_target, s.is_active, s.phone, s.language,
                       (SELECT COUNT(*) FROM clients c WHERE c.frontdesk_id = s.id) AS client_count
                FROM staff s {where}
                ORDER BY s.team NULLS LAST, s.display_name""",
            params
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


# ─── Phase 17: Org Chart / Team Hierarchy API ────────────────────────────────

@app.get('/api/org-chart')
async def get_org_chart(user: dict = Depends(get_current_user)):
    """Return team hierarchy tree. Owner sees all, admin sees own team, member sees own team."""
    async with _connect_db() as db:
        where = 'WHERE s.is_active = 1'
        params: list = []

        if user['role'] == 'admin':
            where += ' AND s.team = ?'
            params.append(user['team_scope'])
        elif user['role'] == 'member':
            where += ' AND s.team = ?'
            params.append(user.get('team_scope', ''))

        async with db.execute(
            f"""SELECT s.id, s.display_name, s.role, s.team, s.maintenance_id,
                       s.tg_username, s.daily_target, s.last_active_at,
                       (SELECT COUNT(*) FROM clients c WHERE c.frontdesk_id = s.id
                        AND c.status NOT IN ('dead', 'blocked', 'scammed')) AS active_clients,
                       (SELECT COUNT(*) FROM permission_overrides po WHERE po.staff_id = s.id) AS override_count
                FROM staff s {where}
                ORDER BY s.role, s.team, s.display_name""",
            params
        ) as cur:
            staff_rows = [row_to_dict(r) for r in await cur.fetchall()]

    # Build tree: teams → leaders → members
    teams: dict = {}
    unassigned = []
    for s in staff_rows:
        team = s.get('team')
        if not team:
            unassigned.append(s)
            continue
        if team not in teams:
            teams[team] = {'name': team, 'leader': None, 'members': []}
        if s['role'] in ('maintenance', 'leader', 'manager'):
            teams[team]['leader'] = s
        else:
            teams[team]['members'].append(s)

    result = []
    for team_name, team_data in sorted(teams.items()):
        node = {
            'team': team_name,
            'leader': team_data['leader'],
            'members': team_data['members'],
            'member_count': len(team_data['members']),
            'total_clients': sum(m.get('active_clients', 0) for m in team_data['members']),
        }
        if team_data['leader']:
            node['total_clients'] += team_data['leader'].get('active_clients', 0)
        result.append(node)

    return {'teams': result, 'unassigned': unassigned}


# ─── Phase 17: Cross-Client Linked Timeline ──────────────────────────────────

@app.get('/api/clients/{client_id}/linked-timeline')
async def get_linked_timeline(
    client_id: int,
    user: dict = Depends(get_current_user),
):
    """Get unified timeline across a client AND all their linked clients.
    Shows notes, status changes, deposits from linked records for full picture."""
    items = []
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        # Get all linked client IDs (including self)
        async with db.execute(
            """SELECT client_id_b AS linked_id FROM client_links WHERE client_id_a = ?
               UNION
               SELECT client_id_a AS linked_id FROM client_links WHERE client_id_b = ?""",
            (client_id, client_id)
        ) as cur:
            linked_ids = [row['linked_id'] for row in await cur.fetchall()]

        all_ids = [client_id] + linked_ids
        placeholders = ','.join('?' * len(all_ids))

        # Notes from all linked clients
        async with db.execute(
            f"""SELECT cn.id, cn.client_id, 'note' AS timeline_type,
                       cn.note_type, cn.content, cn.created_at,
                       cn.author_name, cn.old_status, cn.new_status,
                       c.phone AS client_phone,
                       s.display_name AS staff_name
                FROM client_notes cn
                JOIN clients c ON cn.client_id = c.id
                LEFT JOIN staff s ON cn.staff_id = s.id
                WHERE cn.client_id IN ({placeholders})
                ORDER BY cn.created_at DESC LIMIT 200""",
            all_ids
        ) as cur:
            items.extend([row_to_dict(r) for r in await cur.fetchall()])

        # Deposits from all linked clients
        async with db.execute(
            f"""SELECT d.id, d.client_id, 'deposit' AS timeline_type,
                       'deposit' AS note_type,
                       d.amount, d.currency, d.platform, d.deposit_date AS created_at,
                       c.phone AS client_phone,
                       s.display_name AS staff_name
                FROM deposits d
                JOIN clients c ON d.client_id = c.id
                LEFT JOIN staff s ON d.frontdesk_id = s.id
                WHERE d.client_id IN ({placeholders})
                ORDER BY d.deposit_date DESC LIMIT 100""",
            all_ids
        ) as cur:
            for r in await cur.fetchall():
                rd = row_to_dict(r)
                rd['content'] = f"${rd.get('amount', 0):.2f} {rd.get('currency', 'USD')} ({rd.get('platform', 'unknown')})"
                items.append(rd)

        # Link events
        async with db.execute(
            f"""SELECT cl.id, cl.client_id_a AS client_id, 'link' AS timeline_type,
                       cl.link_type AS note_type, cl.note AS content,
                       cl.created_at,
                       s.display_name AS staff_name,
                       ca.phone AS phone_a, cb.phone AS phone_b
                FROM client_links cl
                JOIN clients ca ON cl.client_id_a = ca.id
                JOIN clients cb ON cl.client_id_b = cb.id
                LEFT JOIN staff s ON cl.created_by = s.id
                WHERE cl.client_id_a IN ({placeholders}) OR cl.client_id_b IN ({placeholders})
                ORDER BY cl.created_at DESC""",
            all_ids + all_ids
        ) as cur:
            items.extend([row_to_dict(r) for r in await cur.fetchall()])

    items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return {
        'client_id': client_id,
        'linked_client_ids': linked_ids,
        'timeline': items[:200],
    }


# ─── Phase 17: Dashboard Duplicate Check API ─────────────────────────────────

class CreateClientRequest(BaseModel):
    phone: str
    source: str
    account_id: Optional[str] = None
    nickname: Optional[str] = None
    platform: Optional[str] = None
    phone_remark: Optional[str] = None
    recruiter: Optional[str] = None
    category: Optional[str] = None  # UK表单粉, CA表单粉, etc.
    first_day_status: Optional[str] = 'pending'
    second_day_status: Optional[str] = 'pending'
    client_condition: Optional[str] = None


@app.post('/api/clients')
async def create_client_via_dashboard(
    body: CreateClientRequest,
    user: dict = Depends(get_current_user),
):
    """Create a client via dashboard with phone_registry duplicate guard."""
    await _require_permission(user, 'clients.create')
    staff_id = user.get('staff_id')
    if not staff_id:
        # Owner without linked staff — try to find any admin staff
        if user['role'] == 'owner':
            async with _connect_db() as db:
                async with db.execute("SELECT id FROM staff WHERE role = 'admin' LIMIT 1") as cur:
                    row = await cur.fetchone()
                    if row:
                        staff_id = row['id']
        if not staff_id:
            raise HTTPException(status_code=403, detail='No linked staff account. Link your account to a staff member in User Management.')

    import re
    phone_normalized = re.sub(r'[^\d]', '', body.phone)
    if len(phone_normalized) < 7 or len(phone_normalized) > 15:
        raise HTTPException(status_code=400, detail='Invalid phone number: must be 7-15 digits')

    async with _connect_db() as db:
        # Check clients table (same frontdesk)
        async with db.execute(
            'SELECT id, status FROM clients WHERE phone = ? AND frontdesk_id = ?',
            (body.phone, staff_id)
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f'You already have this client (ID #{existing["id"]}, status: {existing["status"]})'
            )

        # Check phone_registry (cross-frontdesk)
        async with db.execute(
            'SELECT submitter_name, submitter_staff_id, submitted_at FROM phone_registry WHERE phone_normalized = ?',
            (phone_normalized,)
        ) as cur:
            registry = await cur.fetchone()

        if registry and registry['submitter_staff_id'] and registry['submitter_staff_id'] != staff_id:
            # Log the blocked attempt
            await db.execute(
                """INSERT INTO phone_registry_log
                   (phone_normalized, action, actor_name, actor_staff_id, details)
                   VALUES (?, 'duplicate_blocked_dashboard', ?, ?, ?)""",
                (phone_normalized, user['display_name'], staff_id,
                 json.dumps({"original_submitter": registry["submitter_name"]}))
            )
            await db.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    'type': 'duplicate',
                    'owner': registry['submitter_name'],
                    'submitted_at': registry['submitted_at'],
                    'message': f'This number is owned by {registry["submitter_name"]} (submitted {registry["submitted_at"]}). Contact admin to override.'
                }
            )

        # Create the client
        cur = await db.execute(
            """INSERT INTO clients
               (frontdesk_id, phone, source, account_id, nickname, platform, phone_remark, recruiter,
                first_day_status, second_day_status, client_condition, category, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')""",
            (staff_id, body.phone, body.source, body.account_id,
             body.nickname, body.platform, body.phone_remark, body.recruiter,
             body.first_day_status or 'pending', body.second_day_status or 'pending',
             body.client_condition, body.category)
        )
        client_id = cur.lastrowid

        # Register in phone_registry if new
        if not registry:
            from datetime import datetime as _dt
            try:
                await db.execute(
                    """INSERT INTO phone_registry
                       (phone, phone_normalized, submitter_name, submitter_staff_id, source, submitted_at)
                       VALUES (?, ?, ?, ?, 'dashboard', ?)""",
                    (body.phone, phone_normalized, user['display_name'], staff_id,
                     _dt.now(UTC).isoformat())
                )
                await db.execute(
                    """INSERT INTO phone_registry_log
                       (phone_normalized, action, actor_name, actor_staff_id)
                       VALUES (?, 'submit_dashboard', ?, ?)""",
                    (phone_normalized, user['display_name'], staff_id)
                )
            except aiosqlite.IntegrityError:
                pass  # race condition, already registered

        await db.commit()

    # Phase 24: Auto-recalculate daily stats for this staff member
    try:
        today = date.today().isoformat()
        await _recalculate_staff_daily_stats(staff_id, today)
    except Exception as e:
        logger.warning(f'Auto-stats recalculate failed after client create: {e}')

    # Phase 24: Audit log
    await _audit(user, 'create', 'client', client_id,
                 new_values={'phone': body.phone, 'source': body.source,
                             'account_id': body.account_id, 'staff_id': staff_id})

    return {'ok': True, 'client_id': client_id}


# ─── Phase 17: Bulk Permission Management ────────────────────────────────────

class BulkPermissionRequest(BaseModel):
    staff_id: int
    permissions: dict  # {command: bool} e.g. {"add": true, "export": false}
    reason: Optional[str] = None


@app.post('/api/permissions/bulk')
async def set_bulk_permissions(
    body: BulkPermissionRequest,
    user: dict = Depends(_require_owner_or_admin),
):
    """Set multiple permission overrides at once. Admin can only manage own team."""
    if user['role'] == 'admin':
        async with _connect_db() as db:
            async with db.execute('SELECT team, role FROM staff WHERE id = ?', (body.staff_id,)) as cur:
                row = await cur.fetchone()
            if not row or row['team'] != user['team_scope']:
                raise HTTPException(status_code=403, detail='Cannot manage permissions for staff outside your team')
            # Admin cannot modify admin/leader/maintenance permissions (same or higher level)
            if row['role'] in ('admin', 'leader', 'manager', 'maintenance'):
                raise HTTPException(status_code=403, detail='Cannot modify permissions for staff at or above your level')

    granter_id = user.get('staff_id')
    async with _connect_db() as db:
        for cmd, allowed in body.permissions.items():
            cmd_clean = cmd.lstrip('/')
            await db.execute(
                """INSERT INTO permission_overrides
                   (staff_id, command, allowed, granted_by, reason)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(staff_id, command)
                   DO UPDATE SET allowed = excluded.allowed,
                                 granted_by = excluded.granted_by,
                                 reason = excluded.reason,
                                 updated_at = CURRENT_TIMESTAMP""",
                (body.staff_id, cmd_clean, allowed, granter_id, body.reason)
            )
        await db.commit()

    # Phase 24: Audit log
    await _audit(user, 'permission_change', 'permission', body.staff_id,
                 new_values={'permissions': body.permissions, 'reason': body.reason})

    return {'ok': True, 'updated': len(body.permissions)}


# ─── Phase 17: Phone Registry Duplicate Check (pre-submit) ───────────────────

@app.get('/api/phone-registry/check')
async def check_phone_duplicate(
    phone: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Quick duplicate check before submission. Returns owner info if exists."""
    import re
    normalized = re.sub(r'[^\d]', '', phone)
    staff_id = user.get('staff_id')

    result = {'phone': phone, 'normalized': normalized, 'status': 'available'}

    async with _connect_db() as db:
        # Check phone_registry
        async with db.execute(
            """SELECT submitter_name, submitter_staff_id, submitted_at, category, team_name
               FROM phone_registry WHERE phone_normalized = ?""",
            (normalized,)
        ) as cur:
            registry = await cur.fetchone()

        if registry:
            is_own = registry['submitter_staff_id'] == staff_id
            result['status'] = 'own' if is_own else 'taken'
            result['owner'] = registry['submitter_name']
            result['submitted_at'] = registry['submitted_at']
            result['category'] = registry['category']
            result['team_name'] = registry['team_name']
            result['editable'] = is_own

        # Also check clients table
        async with db.execute(
            """SELECT c.id, c.status, c.frontdesk_id, s.display_name AS frontdesk_name
               FROM clients c LEFT JOIN staff s ON c.frontdesk_id = s.id
               WHERE c.phone = ? LIMIT 1""",
            (phone,)
        ) as cur:
            client = await cur.fetchone()

        if client:
            result['client_id'] = client['id']
            result['client_status'] = client['status']
            result['client_owner'] = client['frontdesk_name']
            result['is_own_client'] = client['frontdesk_id'] == staff_id

        # Check chat_export_phones (imported from Telegram duplicate group)
        if result['status'] == 'available':
            try:
                async with db.execute(
                    """SELECT submitter_name, submitter_tg_id, first_submitted_at,
                              is_duplicate_flagged, staff_id AS export_staff_id
                       FROM chat_export_phones
                       WHERE phone_normalized = ?
                       ORDER BY first_submitted_at ASC LIMIT 1""",
                    (normalized,)
                ) as cur:
                    export_record = await cur.fetchone()
                if export_record:
                    export_is_own = export_record['export_staff_id'] == staff_id if export_record['export_staff_id'] else False
                    result['status'] = 'own' if export_is_own else 'taken'
                    result['owner'] = export_record['submitter_name'] or 'Unknown'
                    result['submitted_at'] = export_record['first_submitted_at']
                    result['source'] = 'chat_export'
                    result['editable'] = export_is_own
                    result['duplicate_flagged'] = bool(export_record['is_duplicate_flagged'])
            except Exception:
                pass  # chat_export_phones table may not exist yet

    return result


# ─── Phase 19: Team Targets API ──────────────────────────────────────────────

class SetTargetRequest(BaseModel):
    team: str
    period_type: str = 'weekly'  # weekly or monthly
    period_start: str  # YYYY-MM-DD
    period_end: str
    target_leads: Optional[int] = None
    target_registers: Optional[int] = None
    target_orders: Optional[int] = None
    target_deposit: Optional[float] = None


@app.get('/api/targets')
async def get_targets(
    team: str = Query(default='all'),
    user: dict = Depends(get_current_user),
):
    """Get team targets. Scoped by role."""
    async with _connect_db() as db:
        where = '1=1'
        params: list = []
        if team != 'all':
            where = 'tt.team = ?'
            params = [team]
        elif user['role'] == 'admin':
            where = 'tt.team = ?'
            params = [user['team_scope']]

        async with db.execute(
            f"""SELECT tt.id, tt.team, tt.period_type, tt.period_start, tt.period_end,
                       tt.target_leads, tt.target_registers, tt.target_orders, tt.target_deposit,
                       s.display_name AS created_by_name, tt.created_at
                FROM team_targets tt
                LEFT JOIN staff s ON tt.created_by = s.id
                WHERE {where}
                ORDER BY tt.period_start DESC LIMIT 50""",
            params
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


@app.post('/api/targets')
async def set_target(
    body: SetTargetRequest,
    user: dict = Depends(_require_owner_or_admin),
):
    """Set or update a team target."""
    if user['role'] == 'admin' and body.team != user['team_scope']:
        raise HTTPException(status_code=403, detail='Cannot set targets for other teams')

    async with _connect_db() as db:
        await db.execute(
            """INSERT INTO team_targets
               (team, period_type, period_start, period_end, target_leads, target_registers, target_orders, target_deposit, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(team, period_type, period_start)
               DO UPDATE SET period_end=excluded.period_end, target_leads=excluded.target_leads,
                 target_registers=excluded.target_registers, target_orders=excluded.target_orders,
                 target_deposit=excluded.target_deposit""",
            (body.team, body.period_type, body.period_start, body.period_end,
             body.target_leads, body.target_registers, body.target_orders, body.target_deposit,
             user.get('staff_id'))
        )
        await db.commit()
    return {'ok': True}


# ─── Phase 19: Real 7-Day Trend Data ────────────────────────────────────────

@app.get('/api/performance/trend')
async def get_performance_trend(
    staff_id: int = Query(...),
    days: int = Query(default=7),
    user: dict = Depends(get_current_user),
):
    """Get N-day daily stats trend for a staff member."""
    async with _connect_db() as db:
        async with db.execute(
            """SELECT stat_date, new_leads, contacted, replied, registered,
                      training, withdrew, new_orders, ghosted, dead, total_deposit,
                      reply_rate, conversion_rate
               FROM daily_stats
               WHERE staff_id = ? AND stat_date >= DATE('now', ?)
               ORDER BY stat_date ASC""",
            (staff_id, f'-{min(days, 90)} days')
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


@app.get('/api/performance/trends-batch')
async def get_trends_batch(
    team: str = Query(default='all'),
    days: int = Query(default=7),
    user: dict = Depends(get_current_user),
):
    """Get 7-day new_leads trend for all staff in a team. Used for sparklines."""
    async with _connect_db() as db:
        where = "s.is_active = 1 AND s.role IN ('frontdesk', 'newbie', 'customer_service')"
        params: list = [f'-{min(days, 90)} days']

        effective_team = team
        if user['role'] == 'admin' and team == 'all':
            effective_team = user['team_scope']
        elif user['role'] == 'member':
            where += ' AND s.id = ?'
            params.append(user.get('staff_id'))

        if effective_team and effective_team != 'all':
            where += ' AND s.team = ?'
            params.append(effective_team)

        async with db.execute(
            f"""SELECT s.id AS staff_id, ds.stat_date, ds.new_leads
                FROM staff s
                LEFT JOIN daily_stats ds ON s.id = ds.staff_id AND ds.stat_date >= DATE('now', ?)
                WHERE {where}
                ORDER BY s.id, ds.stat_date ASC""",
            params
        ) as cur:
            rows = [row_to_dict(r) for r in await cur.fetchall()]

    # Group by staff_id
    trends: dict = {}
    for r in rows:
        sid = r['staff_id']
        if sid not in trends:
            trends[sid] = []
        if r.get('stat_date'):
            trends[sid].append(r['new_leads'] or 0)

    return trends


# ─── Phase 19: Commission API ───────────────────────────────────────────────

@app.get('/api/commissions')
async def get_commissions(
    period: str = Query(default=None),
    team: str = Query(default='all'),
    user: dict = Depends(get_current_user),
):
    """Get commissions. Scoped by role."""
    async with _connect_db() as db:
        where_parts = ['1=1']
        params: list = []

        if period:
            where_parts.append('co.period = ?')
            params.append(period)

        if user['role'] == 'member':
            where_parts.append('co.staff_id = ?')
            params.append(user.get('staff_id'))
        elif user['role'] == 'admin':
            where_parts.append('s.team = ?')
            params.append(user['team_scope'])
        elif team != 'all':
            where_parts.append('s.team = ?')
            params.append(team)

        where = ' AND '.join(where_parts)
        async with db.execute(
            f"""SELECT co.id, co.staff_id, co.trigger_type, co.amount, co.status,
                       co.period, co.created_at,
                       s.display_name AS staff_name, s.team
                FROM commissions co
                JOIN staff s ON co.staff_id = s.id
                WHERE {where}
                ORDER BY co.created_at DESC LIMIT 200""",
            params
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


@app.get('/api/commissions/summary')
async def get_commission_summary(
    period: str = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Aggregate commission summary per staff."""
    async with _connect_db() as db:
        where = '1=1'
        params: list = []
        if period:
            where += ' AND co.period = ?'
            params.append(period)
        if user['role'] == 'admin':
            where += ' AND s.team = ?'
            params.append(user['team_scope'])
        elif user['role'] == 'member':
            where += ' AND co.staff_id = ?'
            params.append(user.get('staff_id'))

        async with db.execute(
            f"""SELECT co.staff_id, s.display_name, s.team,
                       SUM(CASE WHEN co.status = 'approved' THEN co.amount ELSE 0 END) AS approved_total,
                       SUM(CASE WHEN co.status = 'pending' THEN co.amount ELSE 0 END) AS pending_total,
                       COUNT(*) AS total_entries
                FROM commissions co
                JOIN staff s ON co.staff_id = s.id
                WHERE {where}
                GROUP BY co.staff_id
                ORDER BY approved_total DESC""",
            params
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


# ─── Phase 19: Message Templates API ────────────────────────────────────────

@app.get('/api/templates')
async def get_templates(user: dict = Depends(get_current_user)):
    """List all message templates."""
    async with _connect_db() as db:
        async with db.execute(
            """SELECT mt.id, mt.name, mt.content, mt.category, mt.is_default, mt.created_at,
                      s.display_name AS created_by_name
               FROM message_templates mt
               LEFT JOIN staff s ON mt.created_by = s.id
               ORDER BY mt.category, mt.name"""
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


class TemplateRequest(BaseModel):
    name: str
    content: str
    category: str = 'general'
    is_default: bool = False


@app.post('/api/templates')
async def create_template(
    body: TemplateRequest,
    user: dict = Depends(_require_owner_or_admin),
):
    """Create a message template."""
    async with _connect_db() as db:
        cur = await db.execute(
            "INSERT INTO message_templates (name, content, category, is_default, created_by) VALUES (?, ?, ?, ?, ?)",
            (body.name, body.content, body.category, int(body.is_default), user.get('staff_id'))
        )
        await db.commit()
        return {'ok': True, 'id': cur.lastrowid}


@app.put('/api/templates/{template_id}')
async def update_template(
    template_id: int,
    body: TemplateRequest,
    user: dict = Depends(_require_owner_or_admin),
):
    """Update a message template."""
    async with _connect_db() as db:
        cur = await db.execute(
            "UPDATE message_templates SET name=?, content=?, category=?, is_default=? WHERE id=?",
            (body.name, body.content, body.category, int(body.is_default), template_id)
        )
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Template not found')
    return {'ok': True}


@app.delete('/api/templates/{template_id}')
async def delete_template(
    template_id: int,
    user: dict = Depends(_require_owner_or_admin),
):
    """Delete a message template."""
    async with _connect_db() as db:
        cur = await db.execute("DELETE FROM message_templates WHERE id = ?", (template_id,))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Template not found')
    return {'ok': True}


# ─── Phase 19: Contests / Gamification API ───────────────────────────────────

@app.get('/api/contests')
async def get_contests(user: dict = Depends(get_current_user)):
    """List all contests."""
    async with _connect_db() as db:
        async with db.execute(
            """SELECT c.id, c.title, c.metric, c.target, c.team, c.start_date, c.end_date,
                      c.status, c.created_at,
                      sw.display_name AS winner_name,
                      sc.display_name AS created_by_name
               FROM contests c
               LEFT JOIN staff sw ON c.winner_id = sw.id
               LEFT JOIN staff sc ON c.created_by = sc.id
               ORDER BY c.start_date DESC"""
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


class ContestRequest(BaseModel):
    title: str
    metric: str  # new_leads, registered, deposits, etc.
    target: int
    team: Optional[str] = None
    start_date: str
    end_date: str


@app.post('/api/contests')
async def create_contest(
    body: ContestRequest,
    user: dict = Depends(_require_owner_or_admin),
):
    """Create a contest."""
    async with _connect_db() as db:
        cur = await db.execute(
            """INSERT INTO contests (title, metric, target, team, start_date, end_date, status, created_by)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?)""",
            (body.title, body.metric, body.target, body.team, body.start_date, body.end_date,
             user.get('staff_id'))
        )
        await db.commit()
        return {'ok': True, 'id': cur.lastrowid}


@app.get('/api/contests/{contest_id}/leaderboard')
async def get_contest_leaderboard(contest_id: int, user: dict = Depends(get_current_user)):
    """Get leaderboard for a contest."""
    async with _connect_db() as db:
        async with db.execute(
            """SELECT cs.staff_id, cs.score, cs.updated_at,
                      s.display_name, s.team
               FROM contest_scores cs
               JOIN staff s ON cs.staff_id = s.id
               WHERE cs.contest_id = ?
               ORDER BY cs.score DESC""",
            (contest_id,)
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


# ─── Phase 19: XP & Badges API ──────────────────────────────────────────────

@app.get('/api/gamification/{staff_id}')
async def get_staff_gamification(staff_id: int, user: dict = Depends(get_current_user)):
    """Get XP, streak, and badges for a staff member."""
    async with _connect_db() as db:
        # Total XP
        async with db.execute(
            "SELECT COALESCE(SUM(xp_amount), 0) AS total_xp FROM xp_events WHERE staff_id = ?",
            (staff_id,)
        ) as cur:
            xp = (await cur.fetchone())['total_xp']

        # Streak
        async with db.execute(
            "SELECT current_streak, longest_streak, last_action_date FROM streaks WHERE staff_id = ?",
            (staff_id,)
        ) as cur:
            streak_row = await cur.fetchone()
            streak = row_to_dict(streak_row) if streak_row else {'current_streak': 0, 'longest_streak': 0}

        # Badges
        async with db.execute(
            """SELECT b.name, b.emoji, b.description, sb.earned_at
               FROM staff_badges sb
               JOIN badges b ON sb.badge_id = b.id
               WHERE sb.staff_id = ?
               ORDER BY sb.earned_at DESC""",
            (staff_id,)
        ) as cur:
            badges = [row_to_dict(r) for r in await cur.fetchall()]

        # Recent XP events
        async with db.execute(
            "SELECT action, xp_amount, created_at FROM xp_events WHERE staff_id = ? ORDER BY created_at DESC LIMIT 20",
            (staff_id,)
        ) as cur:
            recent_xp = [row_to_dict(r) for r in await cur.fetchall()]

    return {
        'staff_id': staff_id,
        'total_xp': xp,
        'streak': streak,
        'badges': badges,
        'recent_xp': recent_xp,
    }


# ─── Health ───────────────────────────────────────────────────────────────────

# ─── Phase 20: Frontdesk Entry Stats ─────────────────────────────────────────

@app.get('/api/frontdesk/my-stats')
async def frontdesk_my_stats(user: dict = Depends(get_current_user)):
    """Get current user's frontdesk submission stats."""
    staff_id = user.get('staff_id')
    today = date.today().isoformat()
    result = {'today_entries': 0, 'total_entries': 0, 'recent': []}
    async with _connect_db() as db:
        if staff_id:
            async with db.execute(
                "SELECT COUNT(*) AS cnt FROM clients WHERE frontdesk_id = ? AND DATE(created_at) = ?",
                (staff_id, today)
            ) as cur:
                result['today_entries'] = (await cur.fetchone())['cnt']
            async with db.execute(
                "SELECT COUNT(*) AS cnt FROM clients WHERE frontdesk_id = ?",
                (staff_id,)
            ) as cur:
                result['total_entries'] = (await cur.fetchone())['cnt']
            async with db.execute(
                """SELECT id, phone, status, source, created_at
                   FROM clients WHERE frontdesk_id = ?
                   ORDER BY created_at DESC LIMIT 10""",
                (staff_id,)
            ) as cur:
                result['recent'] = [row_to_dict(r) for r in await cur.fetchall()]
    return result


@app.get('/api/frontdesk/recent')
async def frontdesk_recent(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Get recent frontdesk entries across all staff (for admins) or own (for members)."""
    staff_id = user.get('staff_id')
    role = user.get('role', 'member')
    team_scope = user.get('team_scope')
    async with _connect_db() as db:
        if role == 'owner':
            query = """SELECT c.id, c.phone, c.status, c.source, c.created_at,
                              s.display_name AS frontdesk_name, s.team
                       FROM clients c LEFT JOIN staff s ON c.frontdesk_id = s.id
                       ORDER BY c.created_at DESC LIMIT ?"""
            params = (limit,)
        elif role == 'admin' and team_scope:
            query = """SELECT c.id, c.phone, c.status, c.source, c.created_at,
                              s.display_name AS frontdesk_name, s.team
                       FROM clients c LEFT JOIN staff s ON c.frontdesk_id = s.id
                       WHERE s.team = ?
                       ORDER BY c.created_at DESC LIMIT ?"""
            params = (team_scope, limit)
        elif team_scope:
            query = """SELECT c.id, c.phone, c.status, c.source, c.created_at,
                              s.display_name AS frontdesk_name, s.team
                       FROM clients c LEFT JOIN staff s ON c.frontdesk_id = s.id
                       WHERE s.team = ?
                       ORDER BY c.created_at DESC LIMIT ?"""
            params = (team_scope, limit)
        else:
            query = """SELECT c.id, c.phone, c.status, c.source, c.created_at,
                              s.display_name AS frontdesk_name, s.team
                       FROM clients c LEFT JOIN staff s ON c.frontdesk_id = s.id
                       WHERE c.frontdesk_id = ?
                       ORDER BY c.created_at DESC LIMIT ?"""
            params = (staff_id, limit)
        async with db.execute(query, params) as cur:
            rows = [row_to_dict(r) for r in await cur.fetchall()]
    return rows


# ─── Phase 20: Client Reassignment (Maintainer) ─────────────────────────────

class ReassignRequest(BaseModel):
    client_ids: list[int]
    from_staff_id: int
    to_staff_id: int
    reason: str = ''


@app.post('/api/maintainer/reassign')
async def maintainer_reassign(
    body: ReassignRequest,
    user: dict = Depends(get_current_user),
):
    """Bulk reassign clients from one staff to another."""
    if user.get('role') not in ('owner', 'admin'):
        raise HTTPException(403, 'Admin access required')
    async with _connect_db() as db:
        updated = 0
        for cid in body.client_ids:
            result = await db.execute(
                "UPDATE clients SET frontdesk_id = ? WHERE id = ? AND frontdesk_id = ?",
                (body.to_staff_id, cid, body.from_staff_id)
            )
            if result.rowcount > 0:
                updated += 1
                await db.execute(
                    """INSERT INTO client_notes (client_id, staff_id, note_type, content, created_at)
                       VALUES (?, ?, 'reassign', ?, datetime('now'))""",
                    (cid, user.get('staff_id'), f"Reassigned from staff #{body.from_staff_id} to #{body.to_staff_id}. Reason: {body.reason}")
                )
        await db.commit()
    return {'ok': True, 'reassigned': updated}


@app.get('/api/maintainer/team-members')
async def maintainer_team_members(
    team: str = Query(None),
    user: dict = Depends(get_current_user),
):
    """Get team members with client counts for maintainer view."""
    role = user.get('role', 'member')
    team_scope = user.get('team_scope')
    target_team = team or team_scope
    async with _connect_db() as db:
        if role in ('owner', 'admin') and not target_team:
            query = """SELECT s.id, s.display_name, s.role, s.team, s.daily_target, s.is_active,
                              COUNT(c.id) AS client_count,
                              SUM(CASE WHEN c.status = 'new' THEN 1 ELSE 0 END) AS new_count,
                              SUM(CASE WHEN c.next_followup < datetime('now') THEN 1 ELSE 0 END) AS overdue_count
                       FROM staff s LEFT JOIN clients c ON s.id = c.frontdesk_id
                       GROUP BY s.id ORDER BY s.team, s.display_name"""
            async with db.execute(query) as cur:
                rows = [row_to_dict(r) for r in await cur.fetchall()]
        else:
            query = """SELECT s.id, s.display_name, s.role, s.team, s.daily_target, s.is_active,
                              COUNT(c.id) AS client_count,
                              SUM(CASE WHEN c.status = 'new' THEN 1 ELSE 0 END) AS new_count,
                              SUM(CASE WHEN c.next_followup < datetime('now') THEN 1 ELSE 0 END) AS overdue_count
                       FROM staff s LEFT JOIN clients c ON s.id = c.frontdesk_id
                       WHERE s.team = ?
                       GROUP BY s.id ORDER BY s.display_name"""
            async with db.execute(query, (target_team,)) as cur:
                rows = [row_to_dict(r) for r in await cur.fetchall()]
    return rows


# ─── Phase 20: Customer Service Quick Actions ────────────────────────────────

@app.get('/api/cs/recent-interactions')
async def cs_recent_interactions(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Get recent client interactions for CS view."""
    async with _connect_db() as db:
        async with db.execute(
            """SELECT cn.id, cn.client_id, cn.note_type, cn.content, cn.created_at,
                      c.phone, c.status, s.display_name AS staff_name
               FROM client_notes cn
               JOIN clients c ON cn.client_id = c.id
               LEFT JOIN staff s ON cn.staff_id = s.id
               ORDER BY cn.created_at DESC LIMIT ?""",
            (limit,)
        ) as cur:
            rows = [row_to_dict(r) for r in await cur.fetchall()]
    return rows


@app.post('/api/cs/quick-note')
async def cs_quick_note(
    phone: str = Query(...),
    content: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Add a quick note to a client by phone number."""
    import re
    normalized = re.sub(r'[^\d]', '', phone)
    async with _connect_db() as db:
        async with db.execute(
            "SELECT id FROM clients WHERE phone LIKE ? LIMIT 1",
            (f'%{normalized[-8:]}%',)
        ) as cur:
            client = await cur.fetchone()
        if not client:
            raise HTTPException(404, 'Client not found for this phone number')
        await db.execute(
            """INSERT INTO client_notes (client_id, staff_id, note_type, content, created_at)
               VALUES (?, ?, 'comment', ?, datetime('now'))""",
            (client['id'], user.get('staff_id') or user.get('user_id'), content)
        )
        await db.commit()
    return {'ok': True, 'client_id': client['id']}


# ─── Phase 20: Permission Cascade (Hierarchy-Aware) ─────────────────────────

ROLE_HIERARCHY = {'owner': 4, 'admin': 3, 'leader': 2, 'maintenance': 2, 'frontdesk': 1, 'customer_service': 1, 'member': 0, 'newbie': 0, 'viewer': 0}

@app.get('/api/permissions/hierarchy')
async def permissions_hierarchy(user: dict = Depends(get_current_user)):
    """Get permissions organized by hierarchy for tree view."""
    caller_role = user.get('role', 'member')
    caller_level = ROLE_HIERARCHY.get(caller_role, 0)
    async with _connect_db() as db:
        async with db.execute(
            """SELECT s.id, s.display_name, s.role, s.team, s.is_active
               FROM staff s WHERE s.is_active = 1 ORDER BY s.team, s.role DESC, s.display_name"""
        ) as cur:
            all_staff = [row_to_dict(r) for r in await cur.fetchall()]
        async with db.execute(
            "SELECT staff_id, command, allowed, reason FROM permission_overrides"
        ) as cur:
            all_overrides = [row_to_dict(r) for r in await cur.fetchall()]

    overrides_by_staff = {}
    for ov in all_overrides:
        sid = ov['staff_id']
        if sid not in overrides_by_staff:
            overrides_by_staff[sid] = []
        overrides_by_staff[sid].append(ov)

    result = []
    for s in all_staff:
        staff_level = ROLE_HIERARCHY.get(s['role'], 0)
        result.append({
            **s,
            'overrides': overrides_by_staff.get(s['id'], []),
            'editable': caller_level > staff_level,
            'level': staff_level,
        })
    return result


@app.get('/health')
async def health():
    return {'status': 'ok', 'db': DB_PATH, 'service': 'dashboard', 'port': 8501}


# ─── Feature 1: Frontdesk Entry Enhancement ──────────────────────────────────


@app.get('/api/frontdesk/history')
async def frontdesk_history(
    staff_id: int = None, page: int = 1, per_page: int = 50,
    user=Depends(get_current_user),
):
    """Get paginated entry history for a frontdesk user."""
    role = user.get('role', 'member')
    user_staff_id = user.get('staff_id')
    team_scope = user.get('team_scope')
    sid = staff_id or user_staff_id

    # Scope check: members can only see their own data
    if role == 'member' and sid != user_staff_id:
        raise HTTPException(status_code=403, detail='You can only view your own history')

    async with _connect_db() as db:
        # Admin can only see staff within their team_scope
        if role == 'admin' and sid != user_staff_id and team_scope:
            check = await db.execute(
                'SELECT id FROM staff WHERE id = ? AND team = ?', (sid, team_scope),
            )
            if not await check.fetchone():
                raise HTTPException(status_code=403, detail='Staff not in your team scope')

        offset = (page - 1) * per_page
        count_row = await db.execute(
            'SELECT COUNT(id) as cnt FROM clients WHERE frontdesk_id = ?', (sid,),
        )
        total = (await count_row.fetchone())[0]
        cursor = await db.execute(
            'SELECT id, phone, source as category, first_day_status, second_day_status, '
            'client_condition, recruiter, status, created_at '
            'FROM clients WHERE frontdesk_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (sid, per_page, offset),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        return {'total': total, 'entries': rows}


@app.put('/api/clients/{client_id}/day-status')
async def update_day_status(
    client_id: int, body: dict = Body(...), user=Depends(get_current_user),
):
    """Update first/second day status on a client. Auto-recalculates daily stats."""
    async with _connect_db() as db:
        day = body.get('day')  # 1 or 2
        status = body.get('status')  # '注册', '不注册', 'pending'
        col = 'first_day_status' if day == 1 else 'second_day_status'

        # Fetch old value for audit
        async with db.execute(
            f'SELECT frontdesk_id, {col} AS old_val FROM clients WHERE id = ?', (client_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Client not found')

        old_val = row['old_val']
        frontdesk_id = row['frontdesk_id']

        await db.execute(
            f"UPDATE clients SET {col} = ?, updated_at = datetime('now') WHERE id = ?",
            (status, client_id),
        )
        await db.commit()

    # Phase 24: Auto-recalculate daily stats for this staff member
    try:
        today = date.today().isoformat()
        await _recalculate_staff_daily_stats(frontdesk_id, today)
    except Exception as e:
        logger.warning(f'Auto-stats recalculate failed after day-status update: {e}')

    # Phase 24: Audit log
    await _audit(user, 'update', 'client', client_id,
                 old_values={col: old_val}, new_values={col: status})

    return {'ok': True}


# ─── Feature 2: Granular Performance ─────────────────────────────────────────


@app.get('/api/performance/granular')
async def performance_granular(
    date: str = None, team: str = None, user=Depends(get_current_user),
):
    """Get per-person per-category granular performance data."""
    async with _connect_db() as db:
        d = date or datetime.now().strftime('%Y-%m-%d')
        query = (
            'SELECT dp.id, dp.staff_id, dp.stat_date, dp.category, dp.powder_count, '
            'dp.no_reply_start, dp.reply_rate, dp.stuck_explanation, dp.blocked_playing, '
            'dp.been_scammed, dp.sent_link_no_reply, dp.completed_registration, dp.audit_rate, '
            'dp.completed_training, dp.scheduled_time, dp.withdrawal, dp.new_order, '
            'dp.conversion_rate, dp.new_kill, dp.dead_client, dp.note, '
            's.display_name, s.team '
            'FROM daily_performance dp '
            'JOIN staff s ON dp.staff_id = s.id '
            'WHERE dp.stat_date = ?'
        )
        params: list = [d]
        if team and team != 'all':
            query += ' AND s.team = ?'
            params.append(team)
        query += ' ORDER BY s.team, s.display_name, dp.category'
        cursor = await db.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]
        return {'date': d, 'rows': rows}


@app.post('/api/performance/granular')
async def upsert_granular_performance(
    body: dict = Body(...), user=Depends(_require_owner_or_admin),
):
    """Insert or update a daily performance record."""
    async with _connect_db() as db:
        cols = [
            'staff_id', 'stat_date', 'category', 'powder_count', 'no_reply_start',
            'reply_rate', 'stuck_explanation', 'blocked_playing', 'been_scammed',
            'sent_link_no_reply', 'completed_registration', 'audit_rate',
            'completed_training', 'scheduled_time', 'withdrawal', 'new_order',
            'conversion_rate', 'new_kill', 'dead_client', 'note',
        ]
        values = [
            body.get(c, 0 if c not in ('staff_id', 'stat_date', 'category', 'note') else body.get(c))
            for c in cols
        ]
        placeholders = ', '.join(['?'] * len(cols))
        col_names = ', '.join(cols)
        update_cols = ', '.join([
            f'{c} = excluded.{c}' for c in cols
            if c not in ('staff_id', 'stat_date', 'category')
        ])
        await db.execute(
            f'INSERT INTO daily_performance ({col_names}) VALUES ({placeholders}) '
            f"ON CONFLICT(staff_id, stat_date, category) DO UPDATE SET {update_cols}, updated_at = datetime('now')",
            values,
        )
        await db.commit()
        return {'ok': True}


@app.get('/api/performance/blown-accounts')
async def get_blown_accounts(
    date: str = None, team: str = None, user=Depends(get_current_user),
):
    async with _connect_db() as db:
        d = date or datetime.now().strftime('%Y-%m-%d')
        query = (
            'SELECT ba.id, ba.staff_id, ba.blown_date, ba.account_type, ba.phone_number, '
            'ba.account_identifier, ba.reason, ba.category, ba.created_at, '
            's.display_name, s.team '
            'FROM blown_accounts ba '
            'JOIN staff s ON ba.staff_id = s.id '
            'WHERE ba.blown_date = ?'
        )
        params: list = [d]
        if team and team != 'all':
            query += ' AND s.team = ?'
            params.append(team)
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]


@app.post('/api/performance/blown-accounts')
async def add_blown_account(
    body: dict = Body(...), user=Depends(_require_owner_or_admin),
):
    async with _connect_db() as db:
        await db.execute(
            'INSERT INTO blown_accounts (staff_id, blown_date, account_type, phone_number, '
            'account_identifier, reason, category) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                body['staff_id'],
                body.get('blown_date', datetime.now().strftime('%Y-%m-%d')),
                body.get('account_type', 'whatsapp'),
                body.get('phone_number'),
                body.get('account_identifier'),
                body.get('reason'),
                body.get('category'),
            ),
        )
        await db.commit()
        return {'ok': True}


# ─── Feature 3: Group Comparison ─────────────────────────────────────────────


@app.get('/api/groups/compare')
async def group_compare(date: str = None, user=Depends(get_current_user)):
    """Get all groups with daily + cumulative stats for comparison."""
    async with _connect_db() as db:
        d = date or datetime.now().strftime('%Y-%m-%d')
        cursor = await db.execute(
            'SELECT DISTINCT team FROM staff WHERE team IS NOT NULL AND is_active = 1',
        )
        teams = [r[0] for r in await cursor.fetchall()]

        result = []
        for team_name in teams:
            # Today stats from daily_performance
            cursor = await db.execute(
                'SELECT dp.staff_id, s.display_name, dp.category, dp.powder_count, '
                'dp.completed_registration, dp.completed_training, dp.withdrawal, '
                'dp.new_order, dp.conversion_rate, dp.reply_rate '
                'FROM daily_performance dp '
                'JOIN staff s ON dp.staff_id = s.id '
                'WHERE dp.stat_date = ? AND s.team = ? ORDER BY s.display_name',
                (d, team_name),
            )
            today_rows = [dict(r) for r in await cursor.fetchall()]

            # Cumulative stats (all time for this team)
            cursor = await db.execute(
                'SELECT dp.staff_id, s.display_name, '
                'SUM(dp.powder_count) as powder_count, '
                'SUM(dp.completed_registration) as completed_registration, '
                'SUM(dp.completed_training) as completed_training, '
                'SUM(dp.withdrawal) as withdrawal, '
                'SUM(dp.new_order) as new_order, '
                'CASE WHEN SUM(dp.powder_count) > 0 '
                'THEN ROUND(CAST(SUM(dp.new_order) AS REAL) / SUM(dp.powder_count) * 100, 1) '
                'ELSE 0 END as conversion_rate '
                'FROM daily_performance dp '
                'JOIN staff s ON dp.staff_id = s.id '
                'WHERE s.team = ? GROUP BY dp.staff_id ORDER BY s.display_name',
                (team_name,),
            )
            cumulative_rows = [dict(r) for r in await cursor.fetchall()]

            # Get leader
            cursor = await db.execute(
                "SELECT display_name FROM staff WHERE team = ? AND role IN ('leader', 'maintenance') LIMIT 1",
                (team_name,),
            )
            leader_row = await cursor.fetchone()

            result.append({
                'team': team_name,
                'leader': leader_row[0] if leader_row else None,
                'today': today_rows,
                'cumulative': cumulative_rows,
            })

        return {'date': d, 'groups': result}


# ─── Feature 4: Exam System ──────────────────────────────────────────────────


@app.get('/api/exams')
async def get_exams(user=Depends(get_current_user)):
    async with _connect_db() as db:
        cursor = await db.execute(
            'SELECT id, exam_name, team, start_date, end_date, status, created_at '
            'FROM exam_periods ORDER BY created_at DESC',
        )
        return [dict(r) for r in await cursor.fetchall()]


@app.post('/api/exams')
async def create_exam(body: dict = Body(...), user=Depends(_require_owner_or_admin)):
    async with _connect_db() as db:
        cursor = await db.execute(
            'INSERT INTO exam_periods (exam_name, team, start_date, end_date, created_by) '
            'VALUES (?, ?, ?, ?, ?)',
            (body['exam_name'], body.get('team'), body['start_date'], body['end_date'], user.get('staff_id')),
        )
        await db.commit()
        return {'ok': True, 'id': cursor.lastrowid}


@app.get('/api/exams/{exam_id}/results')
async def exam_results(exam_id: int, user=Depends(get_current_user)):
    async with _connect_db() as db:
        cursor = await db.execute(
            'SELECT id, exam_name, team, start_date, end_date, status '
            'FROM exam_periods WHERE id = ?',
            (exam_id,),
        )
        exam_row = await cursor.fetchone()
        if not exam_row:
            raise HTTPException(status_code=404, detail='Exam not found')
        exam = dict(exam_row)

        # Aggregate daily_performance for exam date range
        query = (
            'SELECT dp.staff_id, s.display_name, s.team, s.role, '
            'SUM(dp.powder_count) as total_powder, '
            'CASE WHEN SUM(dp.powder_count) > 0 '
            'THEN ROUND(CAST(SUM(CASE WHEN dp.reply_rate > 0 '
            'THEN dp.powder_count * dp.reply_rate / 100 ELSE 0 END) AS REAL) '
            '/ SUM(dp.powder_count) * 100, 1) ELSE 0 END as avg_reply_rate, '
            'SUM(dp.completed_registration) as total_registrations, '
            'SUM(dp.completed_training) as total_training, '
            'SUM(dp.withdrawal) as total_withdrawals, '
            'SUM(dp.new_order) as total_new_orders, '
            'CASE WHEN SUM(dp.powder_count) > 0 '
            'THEN ROUND(CAST(SUM(dp.new_order) AS REAL) / SUM(dp.powder_count) * 100, 1) '
            'ELSE 0 END as conversion_rate, '
            'SUM(dp.new_kill) as total_new_kills '
            'FROM daily_performance dp '
            'JOIN staff s ON dp.staff_id = s.id '
            'WHERE dp.stat_date BETWEEN ? AND ?'
        )
        params: list = [exam['start_date'], exam['end_date']]
        if exam.get('team'):
            query += ' AND s.team = ?'
            params.append(exam['team'])
        query += ' GROUP BY dp.staff_id ORDER BY total_new_orders DESC, total_powder DESC'

        cursor = await db.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]

        return {'exam': exam, 'results': rows}


@app.put('/api/exams/{exam_id}/close')
async def close_exam(exam_id: int, user=Depends(_require_owner_or_admin)):
    async with _connect_db() as db:
        await db.execute(
            "UPDATE exam_periods SET status = 'completed' WHERE id = ?", (exam_id,),
        )
        await db.commit()
        return {'ok': True}


# ─── Feature 5: Maintainer Deposits ──────────────────────────────────────────


@app.get('/api/maintainer/deposits')
async def maintainer_deposits(
    group_number: str = None, team: str = None, user=Depends(get_current_user),
):
    async with _connect_db() as db:
        query = (
            'SELECT d.id, d.client_id, c.phone, d.amount, '
            'd.pressure_amount, d.total_in, d.deposit_group_id, d.platform, d.deposit_date, '
            'dg.group_number, dg.total_pressure, dg.total_collected, dg.cut_count '
            'FROM deposits d '
            'JOIN clients c ON d.client_id = c.id '
            'LEFT JOIN deposit_groups dg ON d.deposit_group_id = dg.id '
            'WHERE 1=1'
        )
        params: list = []
        if group_number:
            query += ' AND dg.group_number = ?'
            params.append(group_number)
        query += ' ORDER BY d.deposit_date DESC LIMIT 200'
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]


@app.post('/api/maintainer/deposits')
async def create_maintainer_deposit(
    body: dict = Body(...), user=Depends(get_current_user),
):
    async with _connect_db() as db:
        # Create or get deposit group
        group_id = body.get('deposit_group_id')
        if not group_id and body.get('group_number'):
            cursor = await db.execute(
                'INSERT INTO deposit_groups (client_id, group_number, total_pressure) '
                'VALUES (?, ?, ?)',
                (body['client_id'], body['group_number'], body.get('pressure_amount', 0)),
            )
            await db.commit()
            group_id = cursor.lastrowid

        staff_id = user.get('staff_id')
        if not staff_id:
            raise HTTPException(status_code=400, detail='No staff_id linked to your account')

        cursor = await db.execute(
            'INSERT INTO deposits (client_id, frontdesk_id, amount, currency, platform, '
            'pressure_amount, total_in, deposit_group_id, '
            'deposit_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                body['client_id'], staff_id, body.get('amount', 0),
                body.get('currency', 'USD'), body.get('platform'),
                body.get('pressure_amount', 0), body.get('total_in', 0),
                group_id,
                body.get('deposit_date', datetime.now().strftime('%Y-%m-%d')),
            ),
        )
        await db.commit()

        # Update deposit group totals
        if group_id:
            await db.execute(
                'UPDATE deposit_groups SET '
                'total_collected = (SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE deposit_group_id = ?), '
                'cut_count = (SELECT COUNT(id) FROM deposits WHERE deposit_group_id = ?), '
                "updated_at = datetime('now') WHERE id = ?",
                (group_id, group_id, group_id),
            )
            await db.commit()

        return {'ok': True, 'id': cursor.lastrowid}


# ─── Feature 6: CS Financial ─────────────────────────────────────────────────


@app.get('/api/cs/crypto-ledger')
async def crypto_ledger(
    from_date: str = None, to_date: str = None, user=Depends(get_current_user),
):
    async with _connect_db() as db:
        query = (
            'SELECT ct.id, ct.txn_type, ct.client_name, ct.client_number, ct.maintainer_id, '
            'ct.country, ct.amount_usdt, ct.situation, ct.group_name, ct.txn_date, ct.created_at, '
            's.display_name as maintainer_name '
            'FROM crypto_transactions ct '
            'LEFT JOIN staff s ON ct.maintainer_id = s.id '
            'WHERE 1=1'
        )
        params: list = []
        if from_date:
            query += ' AND ct.txn_date >= ?'
            params.append(from_date)
        if to_date:
            query += ' AND ct.txn_date <= ?'
            params.append(to_date)
        query += ' ORDER BY ct.txn_date DESC, ct.created_at DESC'
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]


@app.post('/api/cs/crypto-ledger')
async def add_crypto_transaction(
    body: dict = Body(...), user=Depends(_require_owner_or_admin),
):
    async with _connect_db() as db:
        cursor = await db.execute(
            'INSERT INTO crypto_transactions (txn_type, client_name, client_number, '
            'maintainer_id, country, amount_usdt, situation, group_name, txn_date, created_by) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                body['txn_type'], body['client_name'], body.get('client_number'),
                body.get('maintainer_id'), body.get('country'), body['amount_usdt'],
                body.get('situation'), body.get('group_name'),
                body.get('txn_date', datetime.now().strftime('%Y-%m-%d')),
                user.get('staff_id'),
            ),
        )
        await db.commit()
        return {'ok': True, 'id': cursor.lastrowid}


@app.get('/api/cs/daily-financial')
async def daily_financial(date: str = None, user=Depends(get_current_user)):
    async with _connect_db() as db:
        d = date or datetime.now().strftime('%Y-%m-%d')
        cursor = await db.execute(
            'SELECT summary_date, country, new_orders, deposit_count, total_deposits, '
            'avg_per_client, second_filter_in, second_filter_out, rcs_in, rcs_out '
            'FROM daily_financial_summary WHERE summary_date = ? ORDER BY country',
            (d,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

        # Auto-calculate from deposits if no manual summary exists
        if not rows:
            country_map = {
                '+47': 'Norway', '+46': 'Sweden', '+41': 'Switzerland', '+33': 'France',
            }
            cursor = await db.execute(
                'SELECT c.phone, d.amount FROM deposits d '
                'JOIN clients c ON d.client_id = c.id WHERE d.deposit_date = ?',
                (d,),
            )
            deposit_rows = await cursor.fetchall()
            country_data: dict = {}
            for dr in deposit_rows:
                phone = dr[0] or ''
                country = 'Other'
                for prefix, name in country_map.items():
                    if phone.startswith(prefix) or phone.lstrip('+').startswith(prefix.lstrip('+')):
                        country = name
                        break
                if country not in country_data:
                    country_data[country] = {'new_orders': 0, 'deposit_count': 0, 'total_deposits': 0}
                country_data[country]['deposit_count'] += 1
                country_data[country]['total_deposits'] += dr[1] or 0

            rows = [
                {
                    'summary_date': d, 'country': c,
                    'new_orders': v['new_orders'], 'deposit_count': v['deposit_count'],
                    'total_deposits': v['total_deposits'],
                    'avg_per_client': round(v['total_deposits'] / max(v['deposit_count'], 1), 2),
                }
                for c, v in country_data.items()
            ]

        return {'date': d, 'countries': rows}


@app.post('/api/cs/daily-financial')
async def upsert_daily_financial(
    body: dict = Body(...), user=Depends(_require_owner_or_admin),
):
    async with _connect_db() as db:
        await db.execute(
            'INSERT INTO daily_financial_summary (summary_date, country, new_orders, '
            'deposit_count, total_deposits, avg_per_client, second_filter_in, second_filter_out, '
            'rcs_in, rcs_out, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(summary_date, country) DO UPDATE SET '
            'new_orders=excluded.new_orders, deposit_count=excluded.deposit_count, '
            'total_deposits=excluded.total_deposits, avg_per_client=excluded.avg_per_client, '
            'second_filter_in=excluded.second_filter_in, second_filter_out=excluded.second_filter_out, '
            'rcs_in=excluded.rcs_in, rcs_out=excluded.rcs_out',
            (
                body['summary_date'], body['country'], body.get('new_orders', 0),
                body.get('deposit_count', 0), body.get('total_deposits', 0),
                body.get('avg_per_client', 0), body.get('second_filter_in', 0),
                body.get('second_filter_out', 0), body.get('rcs_in', 0),
                body.get('rcs_out', 0), user.get('staff_id'),
            ),
        )
        await db.commit()
        return {'ok': True}


# ─── Phase 24: Audit Log Helper ──────────────────────────────────────────────

async def _audit(user: dict, action: str, entity_type: str,
                 entity_id: Optional[int] = None,
                 old_values: Optional[dict] = None,
                 new_values: Optional[dict] = None,
                 ip_address: Optional[str] = None):
    """Write an audit log entry. Non-blocking — errors are logged, not raised."""
    try:
        async with _connect_db() as db:
            await db.execute(
                """INSERT INTO audit_log
                   (user_id, username, action, entity_type, entity_id,
                    old_values, new_values, ip_address)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user.get('user_id', 0), user.get('username', 'unknown'),
                 action, entity_type, entity_id,
                 json.dumps(old_values) if old_values else None,
                 json.dumps(new_values) if new_values else None,
                 ip_address))
            await db.commit()
    except Exception as e:
        logger.warning(f'audit_log write failed: {e}')


# ─── Phase 24: Auto-Stats Recalculate Helper ────────────────────────────────

async def _recalculate_staff_daily_stats(staff_id: int, stat_date: str):
    """Recalculate daily_stats for a single staff member on a given date."""
    async with _connect_db() as db:
        counts = {}
        for status_name in ['new', 'contacted', 'replied', 'registered', 'training',
                            'withdrew', 'ordered', 'ghosted', 'blocked', 'dead']:
            col_map = {
                'new': 'created_at', 'contacted': 'contacted_at', 'replied': 'replied_at',
                'registered': 'registered_at', 'training': 'training_at',
                'withdrew': 'withdrew_at', 'ordered': 'first_order_at',
            }
            if status_name in ('ghosted', 'blocked', 'dead'):
                async with db.execute(
                    "SELECT COUNT(*) FROM clients WHERE frontdesk_id = ? AND status = ?",
                    (staff_id, status_name)
                ) as c:
                    counts[status_name] = (await c.fetchone())[0]
            else:
                date_col = col_map.get(status_name, 'created_at')
                async with db.execute(
                    f"SELECT COUNT(*) FROM clients WHERE frontdesk_id = ? AND DATE({date_col}) = ?",
                    (staff_id, stat_date)
                ) as c:
                    counts[status_name] = (await c.fetchone())[0]

        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE frontdesk_id = ? AND DATE(deposit_date) = ?",
            (staff_id, stat_date)
        ) as c:
            total_dep = (await c.fetchone())[0]

        nl = counts.get('new', 0)
        rp = counts.get('replied', 0)
        reg = counts.get('registered', 0)
        no = counts.get('ordered', 0)
        reply_rate = round(rp / max(nl, 1) * 100, 2)
        conv_rate = round(no / max(reg, 1) * 100, 2)

        await db.execute(
            """INSERT INTO daily_stats
               (staff_id, stat_date, new_leads, contacted, replied, registered,
                training, withdrew, new_orders, ghosted, blocked, dead,
                reply_rate, conversion_rate, total_deposit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(staff_id, stat_date)
               DO UPDATE SET new_leads=excluded.new_leads, contacted=excluded.contacted,
                 replied=excluded.replied, registered=excluded.registered,
                 training=excluded.training, withdrew=excluded.withdrew,
                 new_orders=excluded.new_orders, ghosted=excluded.ghosted,
                 blocked=excluded.blocked, dead=excluded.dead,
                 reply_rate=excluded.reply_rate, conversion_rate=excluded.conversion_rate,
                 total_deposit=excluded.total_deposit""",
            (staff_id, stat_date, nl, counts.get('contacted', 0), rp, reg,
             counts.get('training', 0), counts.get('withdrew', 0), no,
             counts.get('ghosted', 0), counts.get('blocked', 0), counts.get('dead', 0),
             reply_rate, conv_rate, total_dep)
        )
        await db.commit()


# ─── Phase 24: Client Comments API ──────────────────────────────────────────


class CreateCommentRequest(BaseModel):
    content: str
    parent_comment_id: Optional[int] = None


class UpdateCommentRequest(BaseModel):
    content: str


@app.get('/api/clients/{client_id}/comments')
async def get_client_comments(
    client_id: int,
    user: dict = Depends(get_current_user),
):
    """Get all comments for a client (threaded)."""
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        async with db.execute(
            'SELECT id FROM clients WHERE id = ?', (client_id,)
        ) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail='Client not found')

        async with db.execute(
            """SELECT id, client_id, staff_id, staff_name, content,
                      parent_comment_id, is_system, is_deleted,
                      created_at, updated_at
               FROM client_comments
               WHERE client_id = ? AND is_deleted = 0
               ORDER BY created_at ASC LIMIT 100""",
            (client_id,)
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


@app.post('/api/clients/{client_id}/comments')
async def create_client_comment(
    client_id: int,
    body: CreateCommentRequest,
    user: dict = Depends(get_current_user),
):
    """Add a comment to a client thread."""
    if not body.content or not body.content.strip():
        raise HTTPException(status_code=400, detail='Comment content cannot be empty')

    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        async with db.execute(
            'SELECT id FROM clients WHERE id = ?', (client_id,)
        ) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail='Client not found')

        # Validate parent exists if specified
        if body.parent_comment_id is not None:
            async with db.execute(
                'SELECT id, client_id FROM client_comments WHERE id = ? AND is_deleted = 0',
                (body.parent_comment_id,)
            ) as cur:
                parent = await cur.fetchone()
            if not parent:
                raise HTTPException(status_code=404, detail='Parent comment not found')
            if parent['client_id'] != client_id:
                raise HTTPException(status_code=400, detail='Parent comment belongs to a different client')

        staff_id = user.get('staff_id') or 0
        staff_name = user.get('display_name', user.get('username', 'Unknown'))

        cur = await db.execute(
            """INSERT INTO client_comments
               (client_id, staff_id, staff_name, content, parent_comment_id, is_system)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (client_id, staff_id, staff_name, body.content.strip(), body.parent_comment_id))
        comment_id = cur.lastrowid
        await db.commit()

    await _audit(user, 'create', 'client_comment', comment_id,
                 new_values={'client_id': client_id, 'content': body.content.strip()})

    return {'ok': True, 'comment_id': comment_id}


@app.put('/api/comments/{comment_id}')
async def update_comment(
    comment_id: int,
    body: UpdateCommentRequest,
    user: dict = Depends(get_current_user),
):
    """Edit own comment."""
    if not body.content or not body.content.strip():
        raise HTTPException(status_code=400, detail='Comment content cannot be empty')

    async with _connect_db() as db:
        async with db.execute(
            """SELECT id, client_id, staff_id, staff_name, content, is_deleted
               FROM client_comments WHERE id = ?""",
            (comment_id,)
        ) as cur:
            comment = await cur.fetchone()
        if not comment:
            raise HTTPException(status_code=404, detail='Comment not found')
        if comment['is_deleted']:
            raise HTTPException(status_code=410, detail='Comment has been deleted')

        # Only the author or owner/admin can edit
        comment_staff_id = comment['staff_id']
        user_staff_id = user.get('staff_id')
        if user['role'] not in ('owner', 'admin') and comment_staff_id != user_staff_id:
            raise HTTPException(status_code=403, detail='Can only edit your own comments')

        old_content = comment['content']
        await db.execute(
            """UPDATE client_comments
               SET content = ?, updated_at = datetime('now')
               WHERE id = ? AND is_deleted = 0""",
            (body.content.strip(), comment_id))
        await db.commit()

    await _audit(user, 'update', 'client_comment', comment_id,
                 old_values={'content': old_content},
                 new_values={'content': body.content.strip()})

    return {'ok': True}


@app.delete('/api/comments/{comment_id}')
async def delete_comment(
    comment_id: int,
    user: dict = Depends(get_current_user),
):
    """Soft-delete a comment. Author or admin/owner."""
    async with _connect_db() as db:
        async with db.execute(
            """SELECT id, client_id, staff_id, content, is_deleted
               FROM client_comments WHERE id = ?""",
            (comment_id,)
        ) as cur:
            comment = await cur.fetchone()
        if not comment:
            raise HTTPException(status_code=404, detail='Comment not found')
        if comment['is_deleted']:
            raise HTTPException(status_code=410, detail='Comment already deleted')

        comment_staff_id = comment['staff_id']
        user_staff_id = user.get('staff_id')
        if user['role'] not in ('owner', 'admin') and comment_staff_id != user_staff_id:
            raise HTTPException(status_code=403, detail='Can only delete your own comments')

        await db.execute(
            """UPDATE client_comments
               SET is_deleted = 1, updated_at = datetime('now')
               WHERE id = ?""",
            (comment_id,))
        await db.commit()

    await _audit(user, 'delete', 'client_comment', comment_id,
                 old_values={'content': comment['content'], 'client_id': comment['client_id']})

    return {'ok': True}


# ─── Phase 24: Audit Log API ────────────────────────────────────────────────


@app.get('/api/audit-log')
async def get_audit_log(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None, alias='user_id'),
    from_date: Optional[str] = Query(None, alias='from'),
    to_date: Optional[str] = Query(None, alias='to'),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: dict = Depends(_require_owner_or_admin),
):
    """Query audit log. Owner/Admin only."""
    conditions: list[str] = []
    params: list = []
    if entity_type:
        conditions.append('entity_type = ?')
        params.append(entity_type)
    if entity_id is not None:
        conditions.append('entity_id = ?')
        params.append(entity_id)
    if user_id is not None:
        conditions.append('user_id = ?')
        params.append(user_id)
    if from_date:
        conditions.append('created_at >= ?')
        params.append(from_date)
    if to_date:
        conditions.append('created_at <= ?')
        params.append(to_date)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    offset = (page - 1) * per_page

    async with _connect_db() as db:
        async with db.execute(
            f'SELECT COUNT(*) AS cnt FROM audit_log {where}', params
        ) as cur:
            total = (await cur.fetchone())['cnt']

        async with db.execute(
            f"""SELECT id, user_id, username, action, entity_type, entity_id,
                       old_values, new_values, ip_address, created_at
                FROM audit_log {where}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ) as cur:
            entries = [row_to_dict(r) for r in await cur.fetchall()]

    return {'total': total, 'page': page, 'per_page': per_page, 'entries': entries}


# ─── Phase 24: Phone Registry Enhanced ───────────────────────────────────────


@app.get('/api/phone-registry/duplicates')
async def phone_registry_duplicates(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """List all cross-user duplicate phone numbers."""
    async with _connect_db() as db:
        count_sql = """
            SELECT COUNT(*) AS cnt FROM (
                SELECT phone_normalized
                FROM chat_export_phones
                WHERE phone_normalized IS NOT NULL
                GROUP BY phone_normalized
                HAVING COUNT(DISTINCT submitter_tg_id) > 1
            )
        """
        try:
            async with db.execute(count_sql) as cur:
                total = (await cur.fetchone())['cnt']
        except Exception:
            return {'total': 0, 'page': page, 'per_page': per_page, 'results': []}

        offset = (page - 1) * per_page
        async with db.execute(
            """SELECT cep.phone_normalized, cep.phone,
                      COUNT(DISTINCT cep.submitter_tg_id) AS submitter_count,
                      GROUP_CONCAT(DISTINCT cep.submitter_name) AS submitters,
                      MIN(cep.first_submitted_at) AS earliest,
                      MAX(cep.last_submitted_at) AS latest
               FROM chat_export_phones cep
               WHERE cep.phone_normalized IS NOT NULL
               GROUP BY cep.phone_normalized
               HAVING COUNT(DISTINCT cep.submitter_tg_id) > 1
               ORDER BY submitter_count DESC, earliest ASC
               LIMIT ? OFFSET ?""",
            (per_page, offset)
        ) as cur:
            results = [row_to_dict(r) for r in await cur.fetchall()]

    return {'total': total, 'page': page, 'per_page': per_page, 'results': results}


@app.get('/api/phone-registry/history/{phone}')
async def phone_registry_history(
    phone: str,
    user: dict = Depends(get_current_user),
):
    """Full submission history for a phone number from all sources."""
    normalized = _normalize_phone(phone)
    entries: list[dict] = []
    async with _connect_db() as db:
        # phone_registry entries
        async with db.execute(
            """SELECT 'phone_registry' AS source_table, id, phone, phone_normalized,
                      submitter_name, submitter_staff_id, source, submitted_at, created_at
               FROM phone_registry WHERE phone_normalized = ?""",
            (normalized,)
        ) as cur:
            entries.extend([row_to_dict(r) for r in await cur.fetchall()])

        # chat_export_phones entries
        try:
            async with db.execute(
                """SELECT 'chat_export' AS source_table, id, phone, phone_normalized,
                          submitter_name, submitter_tg_id, staff_id AS submitter_staff_id,
                          first_submitted_at AS submitted_at, message_count,
                          is_duplicate_flagged, imported_at AS created_at
                   FROM chat_export_phones WHERE phone_normalized = ?
                   ORDER BY first_submitted_at ASC""",
                (normalized,)
            ) as cur:
                entries.extend([row_to_dict(r) for r in await cur.fetchall()])
        except Exception:
            pass

        # phone_registry_log entries
        async with db.execute(
            """SELECT 'registry_log' AS source_table, id, phone_normalized,
                      action, actor_name, actor_staff_id, details, created_at
               FROM phone_registry_log WHERE phone_normalized = ?
               ORDER BY created_at ASC""",
            (normalized,)
        ) as cur:
            entries.extend([row_to_dict(r) for r in await cur.fetchall()])

    return {'phone': phone, 'normalized': normalized, 'entries': entries}


class BulkCheckRequest(BaseModel):
    phones: list[str]


@app.post('/api/phone-registry/bulk-check')
async def phone_registry_bulk_check(
    body: BulkCheckRequest,
    user: dict = Depends(get_current_user),
):
    """Check multiple phone numbers at once."""
    if len(body.phones) > 500:
        raise HTTPException(status_code=400, detail='Maximum 500 phones per request')

    results: list[dict] = []
    async with _connect_db() as db:
        for phone in body.phones:
            normalized = _normalize_phone(phone)
            if not normalized:
                results.append({'phone': phone, 'normalized': '', 'found': False})
                continue

            async with db.execute(
                """SELECT id, phone, submitter_name, submitter_staff_id, source, submitted_at
                   FROM phone_registry WHERE phone_normalized = ?""",
                (normalized,)
            ) as cur:
                row = await cur.fetchone()

            if row:
                d = row_to_dict(row)
                d['phone_input'] = phone
                d['normalized'] = normalized
                d['found'] = True
                d['source_table'] = 'phone_registry'
                results.append(d)
                continue

            # Fallback: check chat_export_phones
            try:
                async with db.execute(
                    """SELECT id, phone, submitter_name, submitter_tg_id, staff_id,
                              first_submitted_at AS submitted_at, is_duplicate_flagged
                       FROM chat_export_phones WHERE phone_normalized = ?
                       ORDER BY first_submitted_at ASC LIMIT 1""",
                    (normalized,)
                ) as cur:
                    erow = await cur.fetchone()
                if erow:
                    d = row_to_dict(erow)
                    d['phone_input'] = phone
                    d['normalized'] = normalized
                    d['found'] = True
                    d['source_table'] = 'chat_export'
                    results.append(d)
                    continue
            except Exception:
                pass

            results.append({'phone': phone, 'phone_input': phone, 'normalized': normalized, 'found': False})

    return {'total': len(results), 'found': sum(1 for r in results if r['found']), 'results': results}


@app.get('/api/phone-registry/by-staff/{staff_id}')
async def phone_registry_by_staff(
    staff_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """All phone numbers submitted by a specific staff member."""
    async with _connect_db() as db:
        async with db.execute(
            'SELECT COUNT(*) AS cnt FROM phone_registry WHERE submitter_staff_id = ?',
            (staff_id,)
        ) as cur:
            total = (await cur.fetchone())['cnt']

        offset = (page - 1) * per_page
        async with db.execute(
            """SELECT id, phone, phone_normalized, submitter_name,
                      source, submitted_at, created_at
               FROM phone_registry
               WHERE submitter_staff_id = ?
               ORDER BY submitted_at DESC LIMIT ? OFFSET ?""",
            (staff_id, per_page, offset)
        ) as cur:
            results = [row_to_dict(r) for r in await cur.fetchall()]

    return {'total': total, 'page': page, 'per_page': per_page, 'results': results}


# ─── Phase 26: Client Pipeline ──────────────────────────────────────────────

# Mapping of valid step names to their SQL for pipeline upsert (avoids f-string SQL injection)
_PIPELINE_STEP_SQL = {
    'contacted_at': 'INSERT INTO client_pipeline_status (client_id, contacted_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET contacted_at = ?, updated_at = CURRENT_TIMESTAMP',
    'replied_at': 'INSERT INTO client_pipeline_status (client_id, replied_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET replied_at = ?, updated_at = CURRENT_TIMESTAMP',
    'registered_at': 'INSERT INTO client_pipeline_status (client_id, registered_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET registered_at = ?, updated_at = CURRENT_TIMESTAMP',
    'training_completed_at': 'INSERT INTO client_pipeline_status (client_id, training_completed_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET training_completed_at = ?, updated_at = CURRENT_TIMESTAMP',
    'bonus_withdrew_at': 'INSERT INTO client_pipeline_status (client_id, bonus_withdrew_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET bonus_withdrew_at = ?, updated_at = CURRENT_TIMESTAMP',
    'day1_complete': 'INSERT INTO client_pipeline_status (client_id, day1_complete) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET day1_complete = ?, updated_at = CURRENT_TIMESTAMP',
    'day2_training_at': 'INSERT INTO client_pipeline_status (client_id, day2_training_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET day2_training_at = ?, updated_at = CURRENT_TIMESTAMP',
    'own_tasks_started_at': 'INSERT INTO client_pipeline_status (client_id, own_tasks_started_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET own_tasks_started_at = ?, updated_at = CURRENT_TIMESTAMP',
    'insufficient_funds_at': 'INSERT INTO client_pipeline_status (client_id, insufficient_funds_at) VALUES (?, ?) ON CONFLICT(client_id) DO UPDATE SET insufficient_funds_at = ?, updated_at = CURRENT_TIMESTAMP',
}

_VALID_ROLE_TYPES = ['frontdesk', 'maintainer', 'group_hype', 'newbie_actor', 'customer_service', 'opener_legacy', 'full_line']
_VALID_KILL_TYPES = ['register_kill', 'new_order_kill', 'pressure_kill', 'salary_kill']
_VALID_ACTOR_ROLES = ['newbie_actor', 'group_hype', 'passerby']
_VALID_UNIT_TYPES = ['organization', 'branch', 'group', 'subgroup']

class PipelineUpdateRequest(BaseModel):
    step: str  # contacted, replied, registered, training_completed, bonus_withdrew, day1_complete, day2_training, own_tasks_started, insufficient_funds
    value: Optional[str] = None  # timestamp or amount

@app.get('/api/clients/{client_id}/pipeline')
async def get_client_pipeline(client_id: int, user: dict = Depends(get_current_user)):
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        cur = await db.execute(
            'SELECT id, client_id, contacted_at, replied_at, registered_at, training_completed_at, bonus_withdrew_at, day1_complete, day2_training_at, own_tasks_started_at, insufficient_funds_at, new_order_amount, new_order_at, pressure_amount, pressure_at, kill_type, kill_knife, kill_at, is_unkilled, unkill_reason, total_deposited, updated_at FROM client_pipeline_status WHERE client_id = ?',
            (client_id,)
        )
        row = await cur.fetchone()
        if not row:
            # Auto-create empty pipeline row
            try:
                await db.execute(
                    'INSERT INTO client_pipeline_status (client_id) VALUES (?)',
                    (client_id,)
                )
                await db.commit()
            except sqlite3.IntegrityError:
                pass  # race condition — row was created between SELECT and INSERT
            cur = await db.execute(
                'SELECT id, client_id, contacted_at, replied_at, registered_at, training_completed_at, bonus_withdrew_at, day1_complete, day2_training_at, own_tasks_started_at, insufficient_funds_at, new_order_amount, new_order_at, pressure_amount, pressure_at, kill_type, kill_knife, kill_at, is_unkilled, unkill_reason, total_deposited, updated_at FROM client_pipeline_status WHERE client_id = ?',
                (client_id,)
            )
            row = await cur.fetchone()
        return row_to_dict(row)

@app.put('/api/clients/{client_id}/pipeline')
async def update_client_pipeline(client_id: int, body: PipelineUpdateRequest, user: dict = Depends(get_current_user)):
    sql = _PIPELINE_STEP_SQL.get(body.step)
    if not sql:
        raise HTTPException(400, f'Invalid step: {body.step}. Must be one of: {list(_PIPELINE_STEP_SQL.keys())}')
    val = body.value or datetime.now(UTC).isoformat()
    if body.step == 'day1_complete':
        val = '1'
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        try:
            await db.execute(sql, (client_id, val, val))
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}


# ─── Phase 26: Role Assignments ─────────────────────────────────────────────

class RoleAssignRequest(BaseModel):
    staff_id: int
    role_type: str  # frontdesk, maintainer, group_hype, newbie_actor, customer_service, opener_legacy, full_line

@app.get('/api/clients/{client_id}/roles')
async def get_client_roles(client_id: int, user: dict = Depends(get_current_user)):
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        cur = await db.execute(
            '''SELECT cra.id, cra.client_id, cra.staff_id, cra.role_type, cra.assigned_at, cra.ended_at, cra.handoff_reason, cra.is_active, s.display_name AS staff_name
               FROM client_role_assignments cra
               LEFT JOIN staff s ON cra.staff_id = s.id
               WHERE cra.client_id = ?
               ORDER BY cra.assigned_at''',
            (client_id,)
        )
        return [row_to_dict(r) for r in await cur.fetchall()]

@app.post('/api/clients/{client_id}/roles', status_code=201)
async def assign_client_role(client_id: int, body: RoleAssignRequest, user: dict = Depends(_require_owner_or_admin)):
    if body.role_type not in _VALID_ROLE_TYPES:
        raise HTTPException(400, f'Invalid role_type. Must be one of: {_VALID_ROLE_TYPES}')
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        try:
            await db.execute(
                'INSERT INTO client_role_assignments (client_id, staff_id, role_type) VALUES (?, ?, ?)',
                (client_id, body.staff_id, body.role_type)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}

@app.post('/api/clients/{client_id}/handoff')
async def record_handoff(client_id: int, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Record frontdesk->maintainer handoff at insufficient funds."""
    maintainer_id = body.get('maintainer_staff_id')
    if not maintainer_id:
        raise HTTPException(400, 'maintainer_staff_id required')
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        try:
            # End frontdesk assignment
            await db.execute(
                "UPDATE client_role_assignments SET is_active = 0, ended_at = CURRENT_TIMESTAMP, handoff_reason = 'insufficient_funds' WHERE client_id = ? AND role_type = 'frontdesk' AND is_active = 1",
                (client_id,)
            )
            # Create maintainer assignment
            await db.execute(
                "INSERT INTO client_role_assignments (client_id, staff_id, role_type) VALUES (?, ?, 'maintainer')",
                (client_id, maintainer_id)
            )
            # Update pipeline
            await db.execute(
                'INSERT INTO client_pipeline_status (client_id, insufficient_funds_at) VALUES (?, CURRENT_TIMESTAMP) ON CONFLICT(client_id) DO UPDATE SET insufficient_funds_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP',
                (client_id,)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}


# ─── Phase 26: Knife Deposits ───────────────────────────────────────────────

class KnifeDepositRequest(BaseModel):
    knife_number: int
    amount: float
    deposit_day: Optional[int] = None
    platform: Optional[str] = None
    notes: Optional[str] = None

@app.get('/api/clients/{client_id}/knives')
async def get_knife_deposits(client_id: int, user: dict = Depends(get_current_user)):
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        cur = await db.execute(
            'SELECT id, client_id, knife_number, amount, deposit_day, platform, maintainer_id, notes, created_at FROM knife_deposits WHERE client_id = ? ORDER BY knife_number',
            (client_id,)
        )
        return [row_to_dict(r) for r in await cur.fetchall()]

@app.post('/api/clients/{client_id}/knives', status_code=201)
async def add_knife_deposit(client_id: int, body: KnifeDepositRequest, user: dict = Depends(get_current_user)):
    if body.knife_number < 1:
        raise HTTPException(400, 'knife_number must be >= 1')
    if body.amount <= 0:
        raise HTTPException(400, 'amount must be > 0')
    staff_id = user.get('staff_id')
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        try:
            await db.execute(
                'INSERT INTO knife_deposits (client_id, knife_number, amount, deposit_day, platform, maintainer_id, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (client_id, body.knife_number, body.amount, body.deposit_day, body.platform, staff_id, body.notes)
            )
            # Update total_deposited in pipeline (SUM recalculates, no need for body.amount param)
            await db.execute(
                'INSERT INTO client_pipeline_status (client_id, total_deposited) VALUES (?, 0) ON CONFLICT(client_id) DO UPDATE SET total_deposited = (SELECT COALESCE(SUM(amount), 0) FROM knife_deposits WHERE client_id = ?), updated_at = CURRENT_TIMESTAMP',
                (client_id, client_id)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}

class KillRequest(BaseModel):
    kill_type: str  # register_kill, new_order_kill, pressure_kill, salary_kill
    kill_knife: Optional[int] = None

@app.put('/api/clients/{client_id}/kill')
async def record_kill(client_id: int, body: KillRequest, user: dict = Depends(_require_owner_or_admin)):
    if body.kill_type not in _VALID_KILL_TYPES:
        raise HTTPException(400, f'Invalid kill_type. Must be one of: {_VALID_KILL_TYPES}')
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        try:
            await db.execute(
                'INSERT INTO client_pipeline_status (client_id, kill_type, kill_knife, kill_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(client_id) DO UPDATE SET kill_type = ?, kill_knife = ?, kill_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP',
                (client_id, body.kill_type, body.kill_knife, body.kill_type, body.kill_knife)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}

@app.put('/api/clients/{client_id}/unkill')
async def unkill_client(client_id: int, body: dict = Body(...), user: dict = Depends(_require_owner_or_admin)):
    reason = body.get('reason', '')
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        # Check current knife - only allow unkill at knife 1 or 2
        cur = await db.execute(
            'SELECT kill_knife FROM client_pipeline_status WHERE client_id = ?', (client_id,)
        )
        row = await cur.fetchone()
        if row and row['kill_knife'] and row['kill_knife'] > 2:
            raise HTTPException(400, 'Cannot unkill after knife 2. Only knife 1 and knife 2 are reversible.')
        try:
            await db.execute(
                'UPDATE client_pipeline_status SET kill_type = NULL, kill_knife = NULL, kill_at = NULL, is_unkilled = 1, unkill_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE client_id = ?',
                (reason, client_id)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}


# ─── Phase 26: Cross-Role Notes ─────────────────────────────────────────────

class CrossRoleNoteRequest(BaseModel):
    from_role: str
    content: str

@app.get('/api/clients/{client_id}/role-notes')
async def get_cross_role_notes(client_id: int, role: Optional[str] = None, user: dict = Depends(get_current_user)):
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        if role:
            cur = await db.execute(
                'SELECT id, client_id, from_role, from_staff_id, content, created_at FROM cross_role_notes WHERE client_id = ? AND from_role = ? ORDER BY created_at DESC',
                (client_id, role)
            )
        else:
            cur = await db.execute(
                'SELECT id, client_id, from_role, from_staff_id, content, created_at FROM cross_role_notes WHERE client_id = ? ORDER BY created_at DESC',
                (client_id,)
            )
        return [row_to_dict(r) for r in await cur.fetchall()]

@app.post('/api/clients/{client_id}/role-notes', status_code=201)
async def add_cross_role_note(client_id: int, body: CrossRoleNoteRequest, user: dict = Depends(get_current_user)):
    if body.from_role not in _VALID_ROLE_TYPES:
        raise HTTPException(400, f'Invalid from_role. Must be one of: {_VALID_ROLE_TYPES}')
    if not body.content or not body.content.strip():
        raise HTTPException(400, 'content must not be empty')
    staff_id = user.get('staff_id')
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        try:
            await db.execute(
                'INSERT INTO cross_role_notes (client_id, from_role, from_staff_id, content) VALUES (?, ?, ?, ?)',
                (client_id, body.from_role, staff_id, body.content)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}


# ─── Phase 26: Group Interactions ────────────────────────────────────────────

class GroupInteractionRequest(BaseModel):
    group_id: Optional[str] = None
    actor_role: str  # newbie_actor, group_hype, passerby
    day_number: Optional[int] = None
    script_completed: Optional[bool] = False
    client_read_messages: Optional[bool] = False
    client_replied: Optional[bool] = False
    client_pm_character: Optional[bool] = False
    client_left_group: Optional[bool] = False
    notes: Optional[str] = None

@app.get('/api/clients/{client_id}/group-interactions')
async def get_group_interactions(client_id: int, user: dict = Depends(get_current_user)):
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        cur = await db.execute(
            '''SELECT gi.id, gi.client_id, gi.group_id, gi.actor_staff_id, gi.actor_role, gi.day_number,
                      gi.script_completed, gi.client_read_messages, gi.client_replied,
                      gi.client_pm_character, gi.client_left_group, gi.notes, gi.created_at,
                      s.display_name AS actor_name
               FROM group_interactions gi
               LEFT JOIN staff s ON gi.actor_staff_id = s.id
               WHERE gi.client_id = ?
               ORDER BY gi.day_number, gi.created_at''',
            (client_id,)
        )
        return [row_to_dict(r) for r in await cur.fetchall()]

@app.post('/api/clients/{client_id}/group-interactions', status_code=201)
async def add_group_interaction(client_id: int, body: GroupInteractionRequest, user: dict = Depends(get_current_user)):
    if body.actor_role not in _VALID_ACTOR_ROLES:
        raise HTTPException(400, f'Invalid actor_role. Must be one of: {_VALID_ACTOR_ROLES}')
    staff_id = user.get('staff_id')
    async with _connect_db() as db:
        await _check_client_access(client_id, user, db)
        try:
            await db.execute(
                '''INSERT INTO group_interactions
                   (client_id, group_id, actor_staff_id, actor_role, day_number,
                    script_completed, client_read_messages, client_replied,
                    client_pm_character, client_left_group, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (client_id, body.group_id, staff_id, body.actor_role, body.day_number,
                 int(body.script_completed or 0), int(body.client_read_messages or 0),
                 int(body.client_replied or 0), int(body.client_pm_character or 0),
                 int(body.client_left_group or 0), body.notes)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
    return {'ok': True}


# ─── Phase 26: Organization Units ───────────────────────────────────────────

class OrgUnitRequest(BaseModel):
    name: str
    unit_type: str  # organization, branch, group, subgroup
    parent_id: Optional[int] = None
    leader_staff_id: Optional[int] = None

@app.get('/api/org/tree')
async def get_org_tree(user: dict = Depends(get_current_user)):
    async with _connect_db() as db:
        cur = await db.execute(
            '''SELECT ou.id, ou.name, ou.unit_type, ou.parent_id, ou.leader_staff_id, ou.is_active,
                      s.display_name AS leader_name
               FROM organization_units ou
               LEFT JOIN staff s ON ou.leader_staff_id = s.id
               WHERE ou.is_active = 1
               ORDER BY ou.unit_type, ou.name'''
        )
        units = [row_to_dict(r) for r in await cur.fetchall()]

        # Build tree
        by_id = {u['id']: {**u, 'children': []} for u in units}
        roots = []
        for u in units:
            node = by_id[u['id']]
            if u['parent_id'] and u['parent_id'] in by_id:
                by_id[u['parent_id']]['children'].append(node)
            else:
                roots.append(node)
        return roots

@app.post('/api/org/units', status_code=201)
async def create_org_unit(body: OrgUnitRequest, user: dict = Depends(_require_owner_or_admin)):
    if body.unit_type not in _VALID_UNIT_TYPES:
        raise HTTPException(400, f'Invalid unit_type. Must be one of: {_VALID_UNIT_TYPES}')
    if not body.name or not body.name.strip():
        raise HTTPException(400, 'name must not be empty')
    async with _connect_db() as db:
        try:
            cur = await db.execute(
                'INSERT INTO organization_units (name, unit_type, parent_id, leader_staff_id) VALUES (?, ?, ?, ?)',
                (body.name, body.unit_type, body.parent_id, body.leader_staff_id)
            )
            await db.commit()
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f'Conflict: {e}')
        return {'ok': True, 'id': cur.lastrowid}


# ─── Serve built React app ────────────────────────────────────────────────────

_assets_dir = os.path.join(DASHBOARD_DIST, 'assets')
if os.path.isdir(DASHBOARD_DIST):
    if os.path.isdir(_assets_dir):
        app.mount('/assets', StaticFiles(directory=_assets_dir), name='assets')

    @app.get('/{path:path}')
    async def serve_dashboard(path: str):
        file_path = os.path.join(DASHBOARD_DIST, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        index = os.path.join(DASHBOARD_DIST, 'index.html')
        if os.path.exists(index):
            return FileResponse(index)
        raise HTTPException(status_code=404)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('web_dashboard_api:app', host='127.0.0.1', port=8501, reload=False)

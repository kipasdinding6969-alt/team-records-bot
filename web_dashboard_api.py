"""Web Dashboard API for Team Records Bot V2 — port 8501.

Separate from mini_app_api.py (port 8500). Uses JWT auth with 3-tier RBAC:
OWNER → ADMIN → MEMBER backed by dashboard_users table (bcrypt passwords).
"""
import bcrypt
import csv
import io
import logging
import os
import secrets
from contextlib import asynccontextmanager as _acm
from datetime import UTC, date, datetime, timedelta
from typing import Optional

import aiosqlite
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
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
    async with _connect_db() as db:
        async with db.execute(
            """SELECT c.id, c.phone, c.status, c.source, c.total_deposited,
                      c.created_at, c.contacted_at, c.replied_at, c.registered_at,
                      c.training_at, c.first_order_at, c.next_followup,
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
    return {'total': total, 'total_registered': total, 'duplicates_blocked': duplicates, 'by_source': by_source}


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
    return {'ok': True}


# ─── Phase 16: Client Links API ─────────────────────────────────────────────

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

        params.append(staff_id)
        await db.execute(f"UPDATE staff SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()

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


@app.post('/api/clients')
async def create_client_via_dashboard(
    body: CreateClientRequest,
    user: dict = Depends(get_current_user),
):
    """Create a client via dashboard with phone_registry duplicate guard."""
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
                 f'{{"original_submitter": "{registry["submitter_name"]}"}}')
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
               (frontdesk_id, phone, source, account_id, nickname, platform, phone_remark, recruiter, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')""",
            (staff_id, body.phone, body.source, body.account_id,
             body.nickname, body.platform, body.phone_remark, body.recruiter)
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

@app.get('/health')
async def health():
    return {'status': 'ok', 'db': DB_PATH, 'service': 'dashboard', 'port': 8501}


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

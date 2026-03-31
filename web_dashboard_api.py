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

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
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

class CreateLinkRequest(BaseModel):
    client_id_a: int
    client_id_b: int
    link_type: str = 'related'
    note: Optional[str] = None


@app.get('/api/clients/{client_id}/links')
async def get_client_links(client_id: int, user: dict = Depends(get_current_user)):
    """Get all links for a client."""
    async with _connect_db() as db:
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


@app.post('/api/client-links')
async def create_client_link(body: CreateLinkRequest, user: dict = Depends(get_current_user)):
    """Create a link between two clients."""
    valid_types = ('related', 'same_person', 'referral', 'family')
    if body.link_type not in valid_types:
        raise HTTPException(status_code=400, detail=f'Invalid link_type. Valid: {valid_types}')

    a, b = min(body.client_id_a, body.client_id_b), max(body.client_id_a, body.client_id_b)
    async with _connect_db() as db:
        try:
            await db.execute(
                'INSERT INTO client_links (client_id_a, client_id_b, link_type, note, created_by) VALUES (?, ?, ?, ?, ?)',
                (a, b, body.link_type, body.note, user.get('staff_id'))
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail='Link already exists')
    return {'ok': True}


@app.delete('/api/client-links/{link_id}')
async def delete_client_link(link_id: int, user: dict = Depends(get_current_user)):
    """Delete a client link."""
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

"""Web Dashboard API for Team Records Bot V2 — port 8501.

Separate from mini_app_api.py (port 8500). Uses JWT auth for managers.
"""
import csv
import io
import logging
import os
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

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DB_PATH = os.getenv('DB_PATH', './team_records_v2.db')
DASHBOARD_USER = os.getenv('DASHBOARD_USER', 'admin')
DASHBOARD_PASS = os.getenv('DASHBOARD_PASS', 'admin')
JWT_SECRET = os.getenv('JWT_SECRET', 'changeme-dashboard-secret-2026')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_HOURS = 24
DASHBOARD_DIST = os.path.join(os.path.dirname(__file__), 'web_dashboard', 'dist')

app = FastAPI(title='Team Records Dashboard API', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# ─── Auth ─────────────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


def create_token(username: str) -> str:
    payload = {
        'sub': username,
        'exp': datetime.now(UTC) + timedelta(hours=JWT_EXPIRE_HOURS),
        'iat': datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail='Missing token')
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get('sub')
        if not username:
            raise HTTPException(status_code=401, detail='Invalid token')
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')


@app.post('/api/auth/login')
async def login(body: LoginRequest):
    if body.username != DASHBOARD_USER or body.password != DASHBOARD_PASS:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    token = create_token(body.username)
    return {'access_token': token, 'token_type': 'bearer'}


@app.get('/api/auth/verify')
async def verify_auth(username: str = Depends(verify_token)):
    return {'ok': True, 'username': username}


# ─── DB helpers ───────────────────────────────────────────────────────────────

@_acm
async def _connect_db():
    async with aiosqlite.connect(DB_PATH, timeout=15) as db:
        db.row_factory = aiosqlite.Row
        yield db


def row_to_dict(row) -> dict:
    return dict(row)


# ─── Dashboard aggregate ──────────────────────────────────────────────────────

@app.get('/api/dashboard')
async def get_dashboard(username: str = Depends(verify_token)):
    today = date.today().isoformat()
    async with _connect_db() as db:
        async with db.execute('SELECT status, COUNT(*) AS cnt FROM clients GROUP BY status') as cur:
            by_status = {r['status']: r['cnt'] for r in await cur.fetchall()}

        async with db.execute('SELECT COUNT(*) AS cnt FROM clients') as cur:
            total_clients = (await cur.fetchone())['cnt']

        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM clients WHERE DATE(created_at) = ?", (today,)
        ) as cur:
            today_new = (await cur.fetchone())['cnt']

        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM clients WHERE DATE(contacted_at) = ?", (today,)
        ) as cur:
            today_contacts = (await cur.fetchone())['cnt']

        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM clients WHERE DATE(first_order_at) = ?", (today,)
        ) as cur:
            today_orders = (await cur.fetchone())['cnt']

        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM clients WHERE status IN "
            "('new','contacted','replied','registered','training','scheduled')"
        ) as cur:
            total_active = (await cur.fetchone())['cnt']

        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM deposits WHERE DATE(deposit_date) = ?",
            (today,)
        ) as cur:
            today_deposits = float((await cur.fetchone())['total'])

        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM deposits"
        ) as cur:
            total_deposits = float((await cur.fetchone())['total'])

        async with db.execute("SELECT COUNT(*) AS cnt FROM staff WHERE is_active = 1") as cur:
            total_staff = (await cur.fetchone())['cnt']

        now_iso = datetime.now(UTC).isoformat()
        async with db.execute(
            """SELECT COUNT(*) AS cnt FROM clients
               WHERE next_followup IS NOT NULL AND next_followup < ?
               AND status NOT IN ('ordered','withdrew','dead','blocked','scammed')""",
            (now_iso,)
        ) as cur:
            overdue_followups = (await cur.fetchone())['cnt']

    ordered_count = by_status.get('ordered', 0)
    conversion_rate = round(ordered_count / max(total_clients, 1) * 100, 1)

    return {
        'total_clients': total_clients,
        'total_active': total_active,
        'total_staff': total_staff,
        'total_deposits': total_deposits,
        'today_new': today_new,
        'today_contacts': today_contacts,
        'today_orders': today_orders,
        'today_deposits': today_deposits,
        'overdue_followups': overdue_followups,
        'conversion_rate': conversion_rate,
        'by_status': by_status,
    }


# ─── Funnel ───────────────────────────────────────────────────────────────────

PIPELINE_STAGES = ['new', 'contacted', 'replied', 'registered', 'training', 'ordered']


@app.get('/api/funnel')
async def get_funnel(username: str = Depends(verify_token)):
    async with _connect_db() as db:
        async with db.execute('SELECT status, COUNT(*) AS cnt FROM clients GROUP BY status') as cur:
            counts = {r['status']: r['cnt'] for r in await cur.fetchall()}

    top = counts.get('new', 0) or 1
    funnel = []
    for stage in PIPELINE_STAGES:
        cnt = counts.get(stage, 0)
        funnel.append({
            'stage': stage,
            'count': cnt,
            'pct': round(cnt / top * 100, 1),
        })
    return funnel


# ─── Activity feed ────────────────────────────────────────────────────────────

@app.get('/api/activity')
async def get_activity(username: str = Depends(verify_token)):
    async with _connect_db() as db:
        async with db.execute(
            """SELECT cn.id, cn.note_type, cn.old_status, cn.new_status, cn.content,
                      cn.created_at, s.display_name AS staff_name,
                      c.phone AS client_phone, c.id AS client_id
               FROM client_notes cn
               LEFT JOIN staff s ON cn.staff_id = s.id
               LEFT JOIN clients c ON cn.client_id = c.id
               ORDER BY cn.created_at DESC
               LIMIT 50"""
        ) as cur:
            return [row_to_dict(r) for r in await cur.fetchall()]


# ─── Staff list ───────────────────────────────────────────────────────────────

@app.get('/api/staff')
async def get_staff(username: str = Depends(verify_token)):
    today = date.today().isoformat()
    async with _connect_db() as db:
        async with db.execute(
            """SELECT s.id, s.display_name, s.role, s.team, s.is_active, s.daily_target,
                      COALESCE(SUM(x.xp_amount), 0) AS xp_total
               FROM staff s
               LEFT JOIN xp_events x ON x.staff_id = s.id
               WHERE s.is_active = 1
               GROUP BY s.id
               ORDER BY xp_total DESC"""
        ) as cur:
            staff_rows = [row_to_dict(r) for r in await cur.fetchall()]

        if not staff_rows:
            return []

        staff_ids = [r['id'] for r in staff_rows]
        id_map = {r['id']: r for r in staff_rows}
        ph = ','.join('?' * len(staff_ids))

        async with db.execute(
            f'SELECT staff_id, current_streak FROM streaks WHERE staff_id IN ({ph})',
            staff_ids
        ) as cur:
            for r in await cur.fetchall():
                id_map[r['staff_id']]['current_streak'] = r['current_streak']

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


# ─── Team performance ─────────────────────────────────────────────────────────

@app.get('/api/team/{team}/performance')
async def get_team_performance(team: str, username: str = Depends(verify_token)):
    today = date.today().isoformat()
    async with _connect_db() as db:
        async with db.execute(
            "SELECT id, display_name, role FROM staff WHERE team = ? AND is_active = 1",
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


# ─── Trends (30 days) ─────────────────────────────────────────────────────────

@app.get('/api/trends')
async def get_trends(username: str = Depends(verify_token)):
    async with _connect_db() as db:
        async with db.execute(
            """SELECT DATE(created_at) AS day, COUNT(*) AS new_clients
               FROM clients
               WHERE DATE(created_at) >= DATE('now', '-30 days')
               GROUP BY day ORDER BY day"""
        ) as cur:
            daily_new = [row_to_dict(r) for r in await cur.fetchall()]

        async with db.execute(
            """SELECT DATE(first_order_at) AS day, COUNT(*) AS orders
               FROM clients
               WHERE first_order_at IS NOT NULL
               AND DATE(first_order_at) >= DATE('now', '-30 days')
               GROUP BY day ORDER BY day"""
        ) as cur:
            daily_orders = [row_to_dict(r) for r in await cur.fetchall()]

        async with db.execute(
            """SELECT DATE(deposit_date) AS day, COALESCE(SUM(amount), 0) AS total
               FROM deposits
               WHERE DATE(deposit_date) >= DATE('now', '-30 days')
               GROUP BY day ORDER BY day"""
        ) as cur:
            daily_deposits = [row_to_dict(r) for r in await cur.fetchall()]

    return {
        'daily_new': daily_new,
        'daily_orders': daily_orders,
        'daily_deposits': daily_deposits,
    }


# ─── Clients list (paginated, filterable) ─────────────────────────────────────

@app.get('/api/clients')
async def list_clients(
    status: Optional[str] = None,
    team: Optional[str] = None,
    staff_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, le=200),
    username: str = Depends(verify_token),
):
    conditions: list[str] = []
    params: list = []

    if status:
        conditions.append('c.status = ?')
        params.append(status)
    if team:
        conditions.append('s.team = ?')
        params.append(team)
    if staff_id:
        conditions.append('c.frontdesk_id = ?')
        params.append(staff_id)
    if search:
        conditions.append('(c.phone LIKE ? OR c.source LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%'])

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


# ─── Client detail ────────────────────────────────────────────────────────────

@app.get('/api/clients/{client_id}')
async def get_client_detail(client_id: int, username: str = Depends(verify_token)):
    async with _connect_db() as db:
        async with db.execute(
            """SELECT c.id, c.phone, c.status, c.source, c.total_deposited,
                      c.created_at, c.contacted_at, c.replied_at, c.registered_at,
                      c.training_at, c.first_order_at, c.next_followup,
                      s.display_name AS frontdesk_name, s.team
               FROM clients c
               LEFT JOIN staff s ON c.frontdesk_id = s.id
               WHERE c.id = ?""",
            (client_id,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail='Client not found')
        client = row_to_dict(row)

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

    return client


# ─── Export clients CSV ───────────────────────────────────────────────────────

@app.get('/api/export/clients')
async def export_clients(
    status: Optional[str] = None,
    team: Optional[str] = None,
    username: str = Depends(verify_token),
):
    conditions: list[str] = []
    params: list = []
    if status:
        conditions.append('c.status = ?')
        params.append(status)
    if team:
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


# ─── Export report CSV ────────────────────────────────────────────────────────

@app.get('/api/export/report')
async def export_report(
    period: str = Query(default='daily', pattern='^(daily|weekly|monthly)$'),
    username: str = Depends(verify_token),
):
    today = date.today().isoformat()
    async with _connect_db() as db:
        if period == 'daily':
            async with db.execute(
                """SELECT s.display_name, s.team, ds.new_leads, ds.contacted,
                          ds.replied, ds.registered, ds.new_orders, ds.total_deposit,
                          ds.reply_rate, ds.conversion_rate
                   FROM daily_stats ds
                   JOIN staff s ON ds.staff_id = s.id
                   WHERE ds.stat_date = ?
                   ORDER BY ds.new_orders DESC""",
                (today,)
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
                   GROUP BY ds.staff_id
                   ORDER BY new_orders DESC"""
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

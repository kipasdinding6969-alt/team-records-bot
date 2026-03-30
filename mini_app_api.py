"""FastAPI backend for Team Records Mini App — port 8500."""
import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, unquote

import aiosqlite
from contextlib import asynccontextmanager as _acm
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DB_PATH = os.getenv('DB_PATH', './team_records_v2.db')
BOT_TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'bot_token.txt')
MINI_APP_DIST = os.path.join(os.path.dirname(__file__), 'mini_app', 'dist')

app = FastAPI(title='Team Records Mini App API', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# ─── Bot token ────────────────────────────────────────────────────────────────

def _load_bot_token() -> str:
    token = os.getenv('BOT_TOKEN', '')
    if not token and os.path.exists(BOT_TOKEN_FILE):
        token = Path(BOT_TOKEN_FILE).read_text().strip()
    return token


BOT_TOKEN = _load_bot_token()


# ─── Auth ─────────────────────────────────────────────────────────────────────

def validate_init_data(init_data: str) -> Optional[dict]:
    """Validate Telegram Mini App initData via HMAC-SHA256.

    Returns parsed data dict on success, None on failure.
    """
    if not init_data or not BOT_TOKEN:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_value = pairs.pop('hash', '')
        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(pairs.items())
        )
        secret_key = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, hash_value):
            return None
        return pairs
    except Exception:
        return None


def get_tg_user_id(init_data_str: str) -> Optional[int]:
    """Extract user ID from validated initData."""
    parsed = validate_init_data(init_data_str)
    if not parsed:
        return None
    user_raw = parsed.get('user')
    if not user_raw:
        return None
    try:
        user = json.loads(unquote(user_raw))
        return int(user.get('id', 0)) or None
    except Exception:
        return None


def require_auth(x_telegram_init_data: str = '') -> Optional[int]:
    """Return user_id from initData, or raise 401."""
    uid = get_tg_user_id(x_telegram_init_data)
    if uid is None and BOT_TOKEN:
        raise HTTPException(status_code=401, detail='Unauthorized')
    return uid


# ─── DB helpers ───────────────────────────────────────────────────────────────

@_acm
async def _connect_db():
    """Async context manager that yields a configured aiosqlite connection."""
    async with aiosqlite.connect(DB_PATH, timeout=15) as db:
        db.row_factory = aiosqlite.Row
        yield db


def row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(row)


def _fmt_date(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return str(val)


# ─── Pydantic models ──────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str


class NoteCreate(BaseModel):
    content: str


# ─── Pipeline endpoint ────────────────────────────────────────────────────────

@app.get('/api/pipeline')
async def get_pipeline(x_telegram_init_data: str = Header(default='')):
    require_auth(x_telegram_init_data)
    async with _connect_db() as db:
        async with db.execute(
            '''SELECT c.id, c.phone, c.status, c.source,
                      c.total_deposited, c.created_at, c.contacted_at,
                      c.replied_at, c.registered_at, c.training_at,
                      c.first_order_at, c.next_followup,
                      s.display_name AS frontdesk_name
               FROM clients c
               LEFT JOIN staff s ON c.frontdesk_id = s.id
               ORDER BY c.created_at DESC'''
        ) as cur:
            rows = await cur.fetchall()

    result: dict[str, list] = {}
    for row in rows:
        d = row_to_dict(row)
        status = d['status'] or 'new'
        result.setdefault(status, []).append(d)
    return result


# ─── Client detail ────────────────────────────────────────────────────────────

@app.get('/api/client/{client_id}')
async def get_client(client_id: int, x_telegram_init_data: str = Header(default='')):
    require_auth(x_telegram_init_data)
    async with _connect_db() as db:
        async with db.execute(
            '''SELECT c.id, c.phone, c.status, c.source,
                      c.total_deposited, c.created_at, c.contacted_at,
                      c.replied_at, c.registered_at, c.training_at,
                      c.first_order_at, c.next_followup,
                      s.display_name AS frontdesk_name
               FROM clients c
               LEFT JOIN staff s ON c.frontdesk_id = s.id
               WHERE c.id = ?''',
            (client_id,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail='Client not found')
        client = row_to_dict(row)

        # Notes
        async with db.execute(
            '''SELECT cn.id, cn.content, cn.note_type, cn.old_status, cn.new_status,
                      cn.created_at, s.display_name AS staff_name
               FROM client_notes cn
               LEFT JOIN staff s ON cn.staff_id = s.id
               WHERE cn.client_id = ?
               ORDER BY cn.created_at DESC
               LIMIT 20''',
            (client_id,)
        ) as cur:
            notes = [row_to_dict(r) for r in await cur.fetchall()]

        # Deposits
        async with db.execute(
            '''SELECT id, amount, currency, platform, deposit_date
               FROM deposits
               WHERE client_id = ?
               ORDER BY deposit_date DESC''',
            (client_id,)
        ) as cur:
            deposits = [row_to_dict(r) for r in await cur.fetchall()]

    client['notes'] = notes
    client['deposits'] = deposits
    return client


# ─── Status update ────────────────────────────────────────────────────────────

VALID_STATUSES = {
    'new', 'contacted', 'replied', 'registered', 'training',
    'withdrew', 'ordered', 'ghosted', 'blocked', 'scammed', 'scheduled', 'dead',
}


@app.patch('/api/client/{client_id}/status')
async def update_client_status(
    client_id: int,
    body: StatusUpdate,
    x_telegram_init_data: str = Header(default=''),
):
    uid = require_auth(x_telegram_init_data)
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f'Invalid status: {body.status}')

    async with _connect_db() as db:
        # Verify client exists + get old status
        async with db.execute(
            'SELECT id, status FROM clients WHERE id = ?', (client_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Client not found')

        old_status = row['status']
        now = datetime.now(UTC).isoformat()

        await db.execute(
            'UPDATE clients SET status = ? WHERE id = ?',
            (body.status, client_id)
        )

        # Log status change as a note
        staff_id = None
        if uid:
            async with db.execute(
                'SELECT id FROM staff WHERE tg_user_id = ?', (uid,)
            ) as cur:
                sr = await cur.fetchone()
                if sr:
                    staff_id = sr['id']

        await db.execute(
            '''INSERT INTO client_notes (client_id, staff_id, note_type, old_status, new_status, content, created_at)
               VALUES (?, ?, 'status_change', ?, ?, ?, ?)''',
            (client_id, staff_id, old_status, body.status,
             f'状态更新: {old_status} → {body.status} (via Mini App)', now)
        )
        await db.commit()

    return {'ok': True, 'old_status': old_status, 'new_status': body.status}


# ─── Add note ─────────────────────────────────────────────────────────────────

@app.post('/api/client/{client_id}/note')
async def add_note(
    client_id: int,
    body: NoteCreate,
    x_telegram_init_data: str = Header(default=''),
):
    uid = require_auth(x_telegram_init_data)
    if not body.content.strip():
        raise HTTPException(status_code=400, detail='Note content required')

    async with _connect_db() as db:
        async with db.execute('SELECT id FROM clients WHERE id = ?', (client_id,)) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail='Client not found')

        staff_id = None
        if uid:
            async with db.execute('SELECT id FROM staff WHERE tg_user_id = ?', (uid,)) as cur:
                sr = await cur.fetchone()
                if sr:
                    staff_id = sr['id']

        now = datetime.now(UTC).isoformat()
        await db.execute(
            '''INSERT INTO client_notes (client_id, staff_id, note_type, content, created_at)
               VALUES (?, ?, 'update', ?, ?)''',
            (client_id, staff_id, body.content.strip(), now)
        )
        await db.commit()

    return {'ok': True}


# ─── Stats ────────────────────────────────────────────────────────────────────

@app.get('/api/stats')
async def get_stats(x_telegram_init_data: str = Header(default='')):
    require_auth(x_telegram_init_data)
    today = date.today().isoformat()

    async with _connect_db() as db:
        # Count by status
        async with db.execute(
            'SELECT status, COUNT(*) AS cnt FROM clients GROUP BY status'
        ) as cur:
            by_status = {r['status']: r['cnt'] for r in await cur.fetchall()}

        # Today new leads
        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM clients WHERE DATE(created_at) = ?", (today,)
        ) as cur:
            today_new = (await cur.fetchone())['cnt']

        # Today contacts (clients first touched today)
        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM clients WHERE DATE(contacted_at) = ?", (today,)
        ) as cur:
            today_contacts = (await cur.fetchone())['cnt']

        # Today orders
        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM clients WHERE DATE(first_order_at) = ?", (today,)
        ) as cur:
            today_orders = (await cur.fetchone())['cnt']

        # Overdue follow-ups
        now_iso = datetime.now(UTC).isoformat()
        async with db.execute(
            '''SELECT COUNT(*) AS cnt FROM clients
               WHERE next_followup IS NOT NULL
               AND next_followup < ?
               AND status NOT IN ('ordered', 'withdrew', 'dead', 'blocked', 'scammed')''',
            (now_iso,)
        ) as cur:
            overdue_followups = (await cur.fetchone())['cnt']

        # Active clients
        active_statuses = ('new', 'contacted', 'replied', 'registered', 'training', 'scheduled')
        placeholders = ','.join('?' * len(active_statuses))
        async with db.execute(
            f'SELECT COUNT(*) AS cnt FROM clients WHERE status IN ({placeholders})',
            active_statuses
        ) as cur:
            total_active = (await cur.fetchone())['cnt']

        # Total
        async with db.execute('SELECT COUNT(*) AS cnt FROM clients') as cur:
            total_clients = (await cur.fetchone())['cnt']

    return {
        'by_status': by_status,
        'today_new': today_new,
        'today_contacts': today_contacts,
        'today_orders': today_orders,
        'overdue_followups': overdue_followups,
        'total_active': total_active,
        'total_clients': total_clients,
    }


# ─── Leaderboard ─────────────────────────────────────────────────────────────

@app.get('/api/leaderboard')
async def get_leaderboard(x_telegram_init_data: str = Header(default='')):
    require_auth(x_telegram_init_data)
    today = date.today().isoformat()

    async with _connect_db() as db:
        # XP totals per staff
        async with db.execute(
            '''SELECT s.id, s.display_name, s.team,
                      COALESCE(SUM(x.xp_amount), 0) AS xp_total
               FROM staff s
               LEFT JOIN xp_events x ON x.staff_id = s.id
               WHERE s.is_active = 1
               GROUP BY s.id
               ORDER BY xp_total DESC
               LIMIT 20'''
        ) as cur:
            staff_rows = [row_to_dict(r) for r in await cur.fetchall()]

        if not staff_rows:
            return []

        staff_ids = [r['id'] for r in staff_rows]
        id_map = {r['id']: r for r in staff_rows}

        # Streaks
        placeholders = ','.join('?' * len(staff_ids))
        async with db.execute(
            f'SELECT staff_id, current_streak, longest_streak FROM streaks WHERE staff_id IN ({placeholders})',
            staff_ids
        ) as cur:
            for r in await cur.fetchall():
                sid = r['staff_id']
                id_map[sid]['current_streak'] = r['current_streak']
                id_map[sid]['longest_streak'] = r['longest_streak']

        # Badges per staff
        async with db.execute(
            f'''SELECT sb.staff_id, b.name, b.emoji, b.description
                FROM staff_badges sb
                JOIN badges b ON b.id = sb.badge_id
                WHERE sb.staff_id IN ({placeholders})''',
            staff_ids
        ) as cur:
            for r in await cur.fetchall():
                sid = r['staff_id']
                id_map[sid].setdefault('badges', []).append({
                    'name': r['name'],
                    'emoji': r['emoji'],
                    'description': r['description'],
                })

        # Today's stats
        async with db.execute(
            f'''SELECT staff_id, new_leads, new_orders
                FROM daily_stats
                WHERE stat_date = ? AND staff_id IN ({placeholders})''',
            (today, *staff_ids)
        ) as cur:
            for r in await cur.fetchall():
                sid = r['staff_id']
                id_map[sid]['today_leads'] = r['new_leads'] or 0
                id_map[sid]['today_orders'] = r['new_orders'] or 0

    result = []
    for entry in staff_rows:
        sid = entry['id']
        data = id_map[sid]
        result.append({
            'id': sid,
            'display_name': data['display_name'],
            'team': data.get('team'),
            'xp_total': int(data['xp_total']),
            'current_streak': data.get('current_streak', 0) or 0,
            'longest_streak': data.get('longest_streak', 0) or 0,
            'badges': data.get('badges', []),
            'today_leads': data.get('today_leads', 0),
            'today_orders': data.get('today_orders', 0),
            'today_deposits': 0,
        })

    return result


# ─── Staff me ─────────────────────────────────────────────────────────────────

@app.get('/api/staff/me')
async def get_staff_me(x_telegram_init_data: str = Header(default='')):
    uid = require_auth(x_telegram_init_data)
    if uid is None:
        raise HTTPException(status_code=401, detail='No user ID in initData')

    async with _connect_db() as db:
        async with db.execute(
            '''SELECT s.id, s.display_name, s.role, s.team, s.tg_user_id, s.daily_target,
                      COALESCE(SUM(x.xp_amount), 0) AS xp_total
               FROM staff s
               LEFT JOIN xp_events x ON x.staff_id = s.id
               WHERE s.tg_user_id = ?
               GROUP BY s.id''',
            (uid,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail='Staff not found')

        staff = row_to_dict(row)

        async with db.execute(
            'SELECT current_streak FROM streaks WHERE staff_id = ?', (staff['id'],)
        ) as cur:
            sr = await cur.fetchone()
            staff['current_streak'] = sr['current_streak'] if sr else 0

    return staff


# ─── Static files (serve built React app) ─────────────────────────────────────

if os.path.isdir(MINI_APP_DIST):
    app.mount('/app', StaticFiles(directory=MINI_APP_DIST, html=True), name='mini_app')

    @app.get('/app/{path:path}')
    async def serve_spa(path: str):
        """Fallback: serve index.html for SPA routing."""
        index = os.path.join(MINI_APP_DIST, 'index.html')
        if os.path.exists(index):
            return FileResponse(index)
        raise HTTPException(status_code=404)


@app.get('/health')
async def health():
    return {'status': 'ok', 'db': DB_PATH}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('mini_app_api:app', host='127.0.0.1', port=8500, reload=False)

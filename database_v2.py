"""V2 database — async SQLite with aiosqlite, 8-table schema."""
import asyncio
import hashlib
import logging
import struct
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta, timezone


def _utc_today() -> date:
    """Return today's date in UTC — matches SQLite CURRENT_TIMESTAMP."""
    return datetime.now(timezone.utc).date()
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import aiosqlite

from models_v2 import (
    Client, ClientNote, ClientStatus, DailyStat, Deposit, NoteType,
    PeriodType, Reminder, Staff, StaffRole, TeamTarget,
)

# Fallback team structure — authoritative source is team_structure.json.
# This dict is used only when team_structure.json cannot be loaded.
TEAM_STRUCTURE = {
    '阿俊': ['阿YIM', 'ODDY', '燕燕', 'MEYMEY'],
    '何军': ['大杰', '阿勇', '小龙', '小宏', 'TINO', 'KUYA'],
}

# Romanized → Chinese name mappings used across sheets
NAME_ALIASES: dict = {
    'Ah YIM': '阿YIM',
    'Ah YONG': '阿勇',
    'Ah Jun': '阿俊',
    'Da Jie': '大杰',
    'Xiao Long': '小龙',
    'Xiao Hong': '小宏',
    'Yan Yan': '燕燕',
    'He Jun': '何军',
}

logger = logging.getLogger(__name__)

DB_PATH = 'team_records_v2.db'

# Hooks called after a client status change: async callable(client_id: int, new_status: str)
_status_change_hooks: list = []


class DatabaseV2:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Open and cache a persistent connection for the lifetime of the process."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute('PRAGMA foreign_keys = ON')
            await self._conn.execute('PRAGMA journal_mode = WAL')

    async def close(self):
        """Close the persistent connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        if self._conn is not None:
            # Serialize all operations through the shared persistent connection.
            async with self._lock:
                yield self._conn
        else:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            try:
                await conn.execute('PRAGMA foreign_keys = ON')
                await conn.execute('PRAGMA journal_mode = WAL')
                yield conn
            finally:
                await conn.close()

    async def initialize(self):
        """Create all 8 tables."""
        async with self.get_connection() as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS staff (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_user_id      INTEGER UNIQUE NOT NULL,
                    tg_chat_id      INTEGER NOT NULL,
                    tg_username     TEXT,
                    display_name    TEXT NOT NULL,
                    role            TEXT NOT NULL DEFAULT 'frontdesk',
                    team            TEXT,
                    phone           TEXT,
                    language        TEXT DEFAULT 'zh',
                    is_active       BOOLEAN DEFAULT TRUE,
                    daily_target    INTEGER DEFAULT 40,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_staff_display_name ON staff(display_name);
                CREATE INDEX IF NOT EXISTS idx_staff_tg_username ON staff(tg_username);

                CREATE TABLE IF NOT EXISTS clients (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    frontdesk_id    INTEGER NOT NULL REFERENCES staff(id),
                    phone           TEXT NOT NULL,
                    account_id      TEXT,
                    phone_remark    TEXT,
                    nickname        TEXT,
                    source          TEXT NOT NULL,
                    recruiter       TEXT,
                    status          TEXT NOT NULL DEFAULT 'new',
                    status_note     TEXT,
                    contacted_at    TIMESTAMP,
                    replied_at      TIMESTAMP,
                    registered_at   TIMESTAMP,
                    training_at     TIMESTAMP,
                    withdrew_at     TIMESTAMP,
                    first_order_at  TIMESTAMP,
                    next_followup   TIMESTAMP,
                    followup_count  INTEGER DEFAULT 0,
                    platform        TEXT,
                    total_deposited REAL DEFAULT 0,
                    sheet_gid       INTEGER,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_clients_frontdesk ON clients(frontdesk_id);
                CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
                CREATE INDEX IF NOT EXISTS idx_clients_followup ON clients(next_followup);
                CREATE INDEX IF NOT EXISTS idx_clients_created ON clients(created_at);
                CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone);

                CREATE TABLE IF NOT EXISTS client_notes (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id       INTEGER NOT NULL REFERENCES clients(id),
                    staff_id        INTEGER NOT NULL REFERENCES staff(id),
                    note_type       TEXT NOT NULL,
                    old_status      TEXT,
                    new_status      TEXT,
                    content         TEXT,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_notes_client ON client_notes(client_id);
                CREATE INDEX IF NOT EXISTS idx_notes_created ON client_notes(created_at);
                CREATE INDEX IF NOT EXISTS idx_notes_staff_status ON client_notes(staff_id, new_status, created_at);

                CREATE TABLE IF NOT EXISTS daily_stats (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id        INTEGER NOT NULL REFERENCES staff(id),
                    stat_date       DATE NOT NULL,
                    new_leads       INTEGER DEFAULT 0,
                    contacted       INTEGER DEFAULT 0,
                    replied         INTEGER DEFAULT 0,
                    registered      INTEGER DEFAULT 0,
                    training        INTEGER DEFAULT 0,
                    withdrew        INTEGER DEFAULT 0,
                    new_orders      INTEGER DEFAULT 0,
                    ghosted         INTEGER DEFAULT 0,
                    blocked         INTEGER DEFAULT 0,
                    dead            INTEGER DEFAULT 0,
                    reply_rate      REAL DEFAULT 0,
                    conversion_rate REAL DEFAULT 0,
                    total_deposit   REAL DEFAULT 0,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(staff_id, stat_date)
                );

                CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(stat_date);
                CREATE INDEX IF NOT EXISTS idx_daily_stats_staff ON daily_stats(staff_id);

                CREATE TABLE IF NOT EXISTS deposits (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id       INTEGER NOT NULL REFERENCES clients(id),
                    frontdesk_id    INTEGER NOT NULL REFERENCES staff(id),
                    amount          REAL NOT NULL,
                    currency        TEXT DEFAULT 'USD',
                    platform        TEXT,
                    knife_number    INTEGER,
                    role_type       TEXT,
                    note            TEXT,
                    deposit_date    DATE NOT NULL,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_deposits_client ON deposits(client_id);
                CREATE INDEX IF NOT EXISTS idx_deposits_frontdesk ON deposits(frontdesk_id);
                CREATE INDEX IF NOT EXISTS idx_deposits_date ON deposits(deposit_date);

                CREATE TABLE IF NOT EXISTS reminders (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id        INTEGER NOT NULL REFERENCES staff(id),
                    client_id       INTEGER REFERENCES clients(id),
                    remind_at       TIMESTAMP NOT NULL,
                    message         TEXT NOT NULL,
                    is_sent         BOOLEAN DEFAULT FALSE,
                    sent_at         TIMESTAMP,
                    source          TEXT DEFAULT 'manual',
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(remind_at, is_sent);
                CREATE INDEX IF NOT EXISTS idx_reminders_staff ON reminders(staff_id);

                CREATE TABLE IF NOT EXISTS team_targets (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    team            TEXT NOT NULL,
                    period_type     TEXT NOT NULL,
                    period_start    DATE NOT NULL,
                    period_end      DATE NOT NULL,
                    target_leads    INTEGER,
                    target_registers INTEGER,
                    target_orders   INTEGER,
                    target_deposit  REAL,
                    created_by      INTEGER REFERENCES staff(id),
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(team, period_type, period_start)
                );

                CREATE TABLE IF NOT EXISTS bot_settings (
                    key             TEXT PRIMARY KEY,
                    value           TEXT NOT NULL,
                    description     TEXT,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS embeddings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type     TEXT NOT NULL,
                    source_id       INTEGER NOT NULL,
                    text_chunk      TEXT NOT NULL,
                    embedding       BLOB NOT NULL,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_embeddings_source ON embeddings(source_type, source_id);

                CREATE TABLE IF NOT EXISTS groups (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_group_id     INTEGER UNIQUE NOT NULL,
                    group_name      TEXT,
                    team            TEXT,
                    group_type      TEXT DEFAULT 'custom',
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_groups_tg_id ON groups(tg_group_id);

                CREATE TABLE IF NOT EXISTS bot_tasks (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type       TEXT NOT NULL,
                    priority        INTEGER DEFAULT 1,
                    data            TEXT,
                    status          TEXT DEFAULT 'pending',
                    scheduled_time  TIMESTAMP,
                    attempts        INTEGER DEFAULT 0,
                    max_attempts    INTEGER DEFAULT 3,
                    error_message   TEXT,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_bot_tasks_status ON bot_tasks(status, priority);

                CREATE TABLE IF NOT EXISTS conversation_states (
                    user_id         INTEGER PRIMARY KEY,
                    state_data      TEXT,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS message_templates (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    category    TEXT DEFAULT 'general',
                    created_by  INTEGER REFERENCES staff(id),
                    is_default  INTEGER DEFAULT 0,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS contests (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    metric      TEXT NOT NULL,
                    target      REAL,
                    team        TEXT,
                    start_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_date    TIMESTAMP NOT NULL,
                    status      TEXT DEFAULT 'active',
                    winner_id   INTEGER REFERENCES staff(id),
                    created_by  INTEGER REFERENCES staff(id),
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS contest_scores (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id  INTEGER NOT NULL REFERENCES contests(id),
                    staff_id    INTEGER NOT NULL REFERENCES staff(id),
                    score       REAL DEFAULT 0,
                    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(contest_id, staff_id)
                );

                CREATE TABLE IF NOT EXISTS xp_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id    INTEGER NOT NULL REFERENCES staff(id),
                    action      TEXT NOT NULL,
                    xp_amount   INTEGER NOT NULL,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_xp_events_staff ON xp_events(staff_id, created_at);

                CREATE TABLE IF NOT EXISTS streaks (
                    staff_id            INTEGER PRIMARY KEY REFERENCES staff(id),
                    current_streak      INTEGER DEFAULT 0,
                    longest_streak      INTEGER DEFAULT 0,
                    last_action_date    DATE,
                    freeze_available    INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS badges (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT NOT NULL,
                    emoji           TEXT NOT NULL,
                    description     TEXT,
                    xp_threshold    INTEGER,
                    action_type     TEXT
                );

                CREATE TABLE IF NOT EXISTS staff_badges (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id    INTEGER NOT NULL REFERENCES staff(id),
                    badge_id    INTEGER NOT NULL REFERENCES badges(id),
                    earned_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(staff_id, badge_id)
                );

                CREATE TABLE IF NOT EXISTS follow_up_sequences (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT NOT NULL UNIQUE,
                    stage           TEXT NOT NULL,
                    delays_json     TEXT NOT NULL,
                    templates_json  TEXT NOT NULL,
                    enabled         BOOLEAN DEFAULT 1,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_followup_seq_stage ON follow_up_sequences(stage);

                CREATE TABLE IF NOT EXISTS follow_up_queue (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id       INTEGER NOT NULL REFERENCES clients(id),
                    sequence_id     INTEGER NOT NULL REFERENCES follow_up_sequences(id),
                    step            INTEGER DEFAULT 0,
                    next_send_at    DATETIME NOT NULL,
                    status          TEXT DEFAULT 'pending',
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at    DATETIME NULL
                );

                CREATE INDEX IF NOT EXISTS idx_followup_queue_client ON follow_up_queue(client_id);
                CREATE INDEX IF NOT EXISTS idx_followup_queue_due ON follow_up_queue(next_send_at, status);

                CREATE TABLE IF NOT EXISTS broadcast_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id        INTEGER NOT NULL,
                    template        TEXT NOT NULL,
                    segment_filter  TEXT,
                    total_targets   INTEGER DEFAULT 0,
                    sent_count      INTEGER DEFAULT 0,
                    failed_count    INTEGER DEFAULT 0,
                    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at    TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_broadcast_log_staff ON broadcast_log(staff_id, started_at);

                -- Phase 9A: Smart Tags
                CREATE TABLE IF NOT EXISTS client_tags (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id   INTEGER NOT NULL REFERENCES clients(id),
                    tag         TEXT NOT NULL,
                    tagged_by   INTEGER REFERENCES staff(id),
                    created_at  TIMESTAMP DEFAULT (datetime('now')),
                    UNIQUE(client_id, tag)
                );
                CREATE INDEX IF NOT EXISTS idx_client_tags_client ON client_tags(client_id);
                CREATE INDEX IF NOT EXISTS idx_client_tags_tag ON client_tags(tag);

                -- Phase 9B: Client Timeline
                CREATE TABLE IF NOT EXISTS client_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id   INTEGER NOT NULL REFERENCES clients(id),
                    event_type  TEXT NOT NULL,
                    event_data  TEXT,
                    staff_id    INTEGER REFERENCES staff(id),
                    created_at  TIMESTAMP DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_client_events_client ON client_events(client_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_client_events_type ON client_events(event_type, created_at);

                -- Phase 9C: SLA Tracking
                CREATE TABLE IF NOT EXISTS sla_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id       INTEGER NOT NULL REFERENCES clients(id),
                    staff_id        INTEGER NOT NULL REFERENCES staff(id),
                    event_type      TEXT NOT NULL,
                    target_minutes  INTEGER NOT NULL,
                    actual_minutes  INTEGER,
                    met             BOOLEAN,
                    started_at      TIMESTAMP NOT NULL,
                    completed_at    TIMESTAMP,
                    created_at      TIMESTAMP DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_sla_events_staff ON sla_events(staff_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_sla_events_open ON sla_events(completed_at, started_at);

                CREATE TABLE IF NOT EXISTS sla_config (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type      TEXT NOT NULL UNIQUE,
                    target_minutes  INTEGER NOT NULL,
                    warning_minutes INTEGER NOT NULL,
                    critical_minutes INTEGER NOT NULL
                );
            """)
            await db.commit()

        # Safe migrations — each is idempotent via try/except
        migrations = [
            ('clients',  'ALTER TABLE clients ADD COLUMN sheet_row INTEGER'),
            ('staff',    'ALTER TABLE staff ADD COLUMN maintenance_id INTEGER REFERENCES staff(id)'),
            ('clients',  'ALTER TABLE clients ADD COLUMN maintenance_id INTEGER REFERENCES staff(id)'),
            ('clients',  'ALTER TABLE clients ADD COLUMN handoff_at TIMESTAMP'),
            ('clients',  'ALTER TABLE clients ADD COLUMN handoff_note TEXT'),
            ('staff',    'ALTER TABLE staff ADD COLUMN tg_username TEXT'),
        ]
        async with self.get_connection() as db:
            for _tbl, sql in migrations:
                try:
                    await db.execute(sql)
                    await db.commit()
                    logger.info(f'Migration applied: {sql[:60]}')
                except Exception:
                    pass  # column already exists

        await self.seed_team_structure()
        await self.auto_assign_teams()
        await self.seed_sla_defaults()
        logger.info("DatabaseV2 initialized")

    # ─── Staff CRUD ─────────────────────────────────────────────────────────

    def _row_to_staff(self, row: aiosqlite.Row) -> Staff:
        keys = row.keys()
        return Staff(
            id=row['id'],
            tg_user_id=row['tg_user_id'],
            tg_chat_id=row['tg_chat_id'],
            tg_username=row['tg_username'],
            display_name=row['display_name'],
            role=StaffRole(row['role']),
            team=row['team'],
            phone=row['phone'],
            language=row['language'] or 'zh',
            is_active=bool(row['is_active']),
            daily_target=row['daily_target'] or 40,
            maintenance_id=row['maintenance_id'] if 'maintenance_id' in keys else None,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            last_active_at=datetime.fromisoformat(row['last_active_at']) if row['last_active_at'] else None,
        )

    async def create_staff(self, s: Staff) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO staff (tg_user_id, tg_chat_id, tg_username, display_name, role,
                   team, phone, language, is_active, daily_target)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (s.tg_user_id, s.tg_chat_id, s.tg_username, s.display_name,
                 s.role.value, s.team, s.phone, s.language, s.is_active, s.daily_target)
            )
            await db.commit()
            return cur.lastrowid

    async def get_staff_by_tg_id(self, tg_user_id: int) -> Optional[Staff]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM staff WHERE tg_user_id = ?', (tg_user_id,))
            row = await cur.fetchone()
            return self._row_to_staff(row) if row else None

    async def get_staff_by_id(self, staff_id: int) -> Optional[Staff]:
        async with self.get_connection() as db:
            cur = await db.execute('SELECT * FROM staff WHERE id = ?', (staff_id,))
            row = await cur.fetchone()
            return self._row_to_staff(row) if row else None

    async def get_all_staff(self, active_only: bool = True) -> List[Staff]:
        async with self.get_connection() as db:
            if active_only:
                cur = await db.execute('SELECT * FROM staff WHERE is_active = 1 ORDER BY display_name')
            else:
                cur = await db.execute('SELECT * FROM staff ORDER BY display_name')
            rows = await cur.fetchall()
            return [self._row_to_staff(r) for r in rows]

    async def update_staff(self, s: Staff):
        async with self.get_connection() as db:
            await db.execute(
                """UPDATE staff SET tg_chat_id=?, tg_username=?, display_name=?, role=?,
                   team=?, phone=?, language=?, is_active=?, daily_target=?, last_active_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (s.tg_chat_id, s.tg_username, s.display_name, s.role.value,
                 s.team, s.phone, s.language, s.is_active, s.daily_target, s.id)
            )
            await db.commit()

    async def upsert_staff(self, s: Staff) -> int:
        existing = await self.get_staff_by_tg_id(s.tg_user_id)
        if existing:
            s.id = existing.id
            await self.update_staff(s)
            return existing.id
        return await self.create_staff(s)

    # ─── Client CRUD ────────────────────────────────────────────────────────

    def _row_to_client(self, row: aiosqlite.Row) -> Client:
        def _dt(v): return datetime.fromisoformat(v) if v else None
        keys = row.keys()
        return Client(
            id=row['id'],
            frontdesk_id=row['frontdesk_id'],
            phone=row['phone'],
            account_id=row['account_id'],
            phone_remark=row['phone_remark'],
            nickname=row['nickname'],
            source=row['source'],
            recruiter=row['recruiter'],
            status=ClientStatus(row['status']),
            status_note=row['status_note'],
            contacted_at=_dt(row['contacted_at']),
            replied_at=_dt(row['replied_at']),
            registered_at=_dt(row['registered_at']),
            training_at=_dt(row['training_at']),
            withdrew_at=_dt(row['withdrew_at']),
            first_order_at=_dt(row['first_order_at']),
            next_followup=_dt(row['next_followup']),
            followup_count=row['followup_count'] or 0,
            platform=row['platform'],
            total_deposited=row['total_deposited'] or 0.0,
            maintenance_id=row['maintenance_id'] if 'maintenance_id' in keys else None,
            handoff_at=_dt(row['handoff_at']) if 'handoff_at' in keys else None,
            handoff_note=row['handoff_note'] if 'handoff_note' in keys else None,
            sheet_gid=row['sheet_gid'],
            sheet_row=row['sheet_row'] if 'sheet_row' in keys else None,
            created_at=_dt(row['created_at']),
            updated_at=_dt(row['updated_at']),
        )

    async def create_client(self, c: Client) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO clients (frontdesk_id, phone, account_id, phone_remark, nickname,
                   source, recruiter, status, status_note, platform, sheet_gid)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (c.frontdesk_id, c.phone, c.account_id, c.phone_remark, c.nickname,
                 c.source, c.recruiter, c.status.value, c.status_note, c.platform, c.sheet_gid)
            )
            await db.commit()
            return cur.lastrowid

    async def get_client_by_phone(self, phone: str, frontdesk_id: Optional[int] = None) -> Optional[Client]:
        async with self.get_connection() as db:
            if frontdesk_id:
                cur = await db.execute(
                    'SELECT * FROM clients WHERE phone=? AND frontdesk_id=? ORDER BY created_at DESC LIMIT 1',
                    (phone, frontdesk_id))
            else:
                cur = await db.execute(
                    'SELECT * FROM clients WHERE phone=? ORDER BY created_at DESC LIMIT 1', (phone,))
            row = await cur.fetchone()
            return self._row_to_client(row) if row else None

    async def get_client_by_id(self, client_id: int) -> Optional[Client]:
        async with self.get_connection() as db:
            cur = await db.execute('SELECT * FROM clients WHERE id=?', (client_id,))
            row = await cur.fetchone()
            return self._row_to_client(row) if row else None

    async def update_client_status(self, client_id: int, new_status: ClientStatus,
                                    staff_id: int, note: Optional[str] = None) -> bool:
        async with self.get_connection() as db:
            try:
                # SELECT + UPDATE + INSERT are wrapped in a single atomic transaction.
                cur = await db.execute('SELECT status FROM clients WHERE id=?', (client_id,))
                row = await cur.fetchone()
                if not row:
                    return False
                old_status = row['status']

                # Build timestamp update based on new status.
                # Column names are hardcoded in a whitelist — no user input in SQL.
                _TS_COLUMNS = {
                    ClientStatus.CONTACTED: 'contacted_at',
                    ClientStatus.REPLIED: 'replied_at',
                    ClientStatus.REGISTERED: 'registered_at',
                    ClientStatus.TRAINING: 'training_at',
                    ClientStatus.WITHDREW: 'withdrew_at',
                    ClientStatus.ORDERED: 'first_order_at',
                }
                ts_col = _TS_COLUMNS.get(new_status)

                if ts_col:
                    # Safe: ts_col comes from a hardcoded dict, never from user input.
                    sql = (
                        "UPDATE clients SET status=?, status_note=?, "
                        + ts_col + "=CURRENT_TIMESTAMP, "
                        "updated_at=CURRENT_TIMESTAMP WHERE id=?"
                    )
                    await db.execute(sql, (new_status.value, note, client_id))
                else:
                    await db.execute(
                        "UPDATE clients SET status=?, status_note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (new_status.value, note, client_id)
                    )

                # Log the status change
                await db.execute(
                    """INSERT INTO client_notes (client_id, staff_id, note_type, old_status, new_status, content)
                       VALUES (?,?,?,?,?,?)""",
                    (client_id, staff_id, NoteType.STATUS_CHANGE.value, old_status, new_status.value, note)
                )
                # Fire status-change hooks BEFORE commit so a hook failure can abort the transaction.
                for _hook in _status_change_hooks:
                    try:
                        await _hook(client_id, new_status.value)
                    except Exception as _he:
                        logger.warning(f'status_change_hook error: {_he}')
                await db.commit()
                return True
            except Exception:
                await db.rollback()
                raise

    async def add_client_note(self, note: ClientNote) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO client_notes (client_id, staff_id, note_type, old_status, new_status, content)
                   VALUES (?,?,?,?,?,?)""",
                (note.client_id, note.staff_id, note.note_type.value,
                 note.old_status, note.new_status, note.content)
            )
            # Update client updated_at
            await db.execute(
                'UPDATE clients SET updated_at=CURRENT_TIMESTAMP WHERE id=?', (note.client_id,))
            await db.commit()
            return cur.lastrowid

    async def get_client_notes(self, client_id: int, limit: int = 10) -> List[ClientNote]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM client_notes WHERE client_id=? ORDER BY created_at DESC LIMIT ?',
                (client_id, limit))
            rows = await cur.fetchall()
            return [ClientNote(
                id=r['id'], client_id=r['client_id'], staff_id=r['staff_id'],
                note_type=NoteType(r['note_type']), old_status=r['old_status'],
                new_status=r['new_status'], content=r['content'],
                created_at=datetime.fromisoformat(r['created_at']) if r['created_at'] else None,
            ) for r in rows]

    # ─── Pipeline queries ────────────────────────────────────────────────────

    async def get_pipeline_counts(self, frontdesk_id: int) -> Dict[str, int]:
        """Return count per status for a frontdesk member."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT status, COUNT(*) as cnt FROM clients WHERE frontdesk_id=? GROUP BY status',
                (frontdesk_id,))
            rows = await cur.fetchall()
            return {r['status']: r['cnt'] for r in rows}

    async def get_stale_clients(self, frontdesk_id: int, hours: int = 72) -> List[Client]:
        """Clients in active status with no update for >hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        active = [s.value for s in ClientStatus.active_statuses()]
        placeholders = ','.join('?' * len(active))
        async with self.get_connection() as db:
            cur = await db.execute(
                f"""SELECT * FROM clients
                    WHERE frontdesk_id=? AND status IN ({placeholders})
                    AND updated_at < ?
                    ORDER BY updated_at ASC""",
                (frontdesk_id, *active, cutoff.strftime('%Y-%m-%d %H:%M:%S'))
            )
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    async def get_all_stale_clients(self, hours: int = 72) -> List[Client]:
        """All stale clients across all staff."""
        cutoff = datetime.now() - timedelta(hours=hours)
        active = [s.value for s in ClientStatus.active_statuses()]
        placeholders = ','.join('?' * len(active))
        async with self.get_connection() as db:
            cur = await db.execute(
                f"""SELECT * FROM clients
                    WHERE status IN ({placeholders}) AND updated_at < ?
                    ORDER BY updated_at ASC""",
                (*active, cutoff.strftime('%Y-%m-%d %H:%M:%S'))
            )
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    async def get_followup_due(self, frontdesk_id: int) -> List[Client]:
        """Clients where next_followup is in the past AND status is still active."""
        active = [s.value for s in ClientStatus.active_statuses()]
        placeholders = ','.join('?' * len(active))
        async with self.get_connection() as db:
            cur = await db.execute(
                f"""SELECT * FROM clients
                   WHERE frontdesk_id=? AND next_followup IS NOT NULL
                   AND next_followup <= CURRENT_TIMESTAMP
                   AND status IN ({placeholders})
                   ORDER BY next_followup ASC""",
                (frontdesk_id, *active))
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    async def search_clients(self, frontdesk_id: int, query: str) -> List[Client]:
        """Search clients by phone, nickname, account_id, or status_note."""
        q = f'%{query}%'
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT * FROM clients
                   WHERE frontdesk_id=?
                   AND (phone LIKE ? OR nickname LIKE ? OR account_id LIKE ? OR status_note LIKE ? OR source LIKE ?)
                   ORDER BY updated_at DESC LIMIT 20""",
                (frontdesk_id, q, q, q, q, q))
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    async def get_clients_by_status(self, frontdesk_id: int, status: ClientStatus) -> List[Client]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM clients WHERE frontdesk_id=? AND status=? ORDER BY updated_at DESC',
                (frontdesk_id, status.value))
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    async def set_next_followup(self, client_id: int, remind_at: datetime):
        async with self.get_connection() as db:
            await db.execute(
                'UPDATE clients SET next_followup=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (remind_at.strftime('%Y-%m-%d %H:%M:%S'), client_id))
            await db.commit()

    # ─── Daily Stats ────────────────────────────────────────────────────────

    async def calculate_daily_stats(self, staff_id: int, stat_date: Optional[date] = None) -> DailyStat:
        """Auto-calculate stats from client data for a given staff/date.

        Note: SQLite CURRENT_TIMESTAMP stores UTC.  We compare using DATE()
        in SQLite which also operates on the stored UTC string, so we must
        pass the UTC date — not the local date — to avoid mismatches around
        midnight in non-UTC timezones.
        """
        if stat_date is None:
            stat_date = _utc_today()
        date_str = stat_date.isoformat()

        async with self.get_connection() as db:
            # Count clients created today (new leads)
            cur = await db.execute(
                'SELECT COUNT(*) FROM clients WHERE frontdesk_id=? AND DATE(created_at)=?',
                (staff_id, date_str))
            new_leads = (await cur.fetchone())[0]

            # Count status changes today from client_notes
            async def count_status(new_st: str) -> int:
                c = await db.execute(
                    """SELECT COUNT(*) FROM client_notes
                       WHERE staff_id=? AND note_type='status_change' AND new_status=?
                       AND DATE(created_at)=?""",
                    (staff_id, new_st, date_str))
                return (await c.fetchone())[0]

            contacted = await count_status('contacted')
            replied = await count_status('replied')
            registered = await count_status('registered')
            training = await count_status('training')
            withdrew = await count_status('withdrew')
            new_orders = await count_status('ordered')
            ghosted = await count_status('ghosted')
            blocked = await count_status('blocked')
            dead = await count_status('dead')

            # Sum deposits for today
            cur = await db.execute(
                'SELECT COALESCE(SUM(amount),0) FROM deposits WHERE frontdesk_id=? AND deposit_date=?',
                (staff_id, date_str))
            total_deposit = (await cur.fetchone())[0]

        stat = DailyStat(
            staff_id=staff_id,
            stat_date=stat_date,
            new_leads=new_leads,
            contacted=contacted,
            replied=replied,
            registered=registered,
            training=training,
            withdrew=withdrew,
            new_orders=new_orders,
            ghosted=ghosted,
            blocked=blocked,
            dead=dead,
            total_deposit=total_deposit,
        )
        stat.calculate_rates()
        return stat

    async def upsert_daily_stats(self, stat: DailyStat):
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO daily_stats (staff_id, stat_date, new_leads, contacted, replied,
                   registered, training, withdrew, new_orders, ghosted, blocked, dead,
                   reply_rate, conversion_rate, total_deposit)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(staff_id, stat_date) DO UPDATE SET
                   new_leads=excluded.new_leads, contacted=excluded.contacted,
                   replied=excluded.replied, registered=excluded.registered,
                   training=excluded.training, withdrew=excluded.withdrew,
                   new_orders=excluded.new_orders, ghosted=excluded.ghosted,
                   blocked=excluded.blocked, dead=excluded.dead,
                   reply_rate=excluded.reply_rate, conversion_rate=excluded.conversion_rate,
                   total_deposit=excluded.total_deposit""",
                (stat.staff_id, stat.stat_date.isoformat(), stat.new_leads, stat.contacted,
                 stat.replied, stat.registered, stat.training, stat.withdrew, stat.new_orders,
                 stat.ghosted, stat.blocked, stat.dead, stat.reply_rate, stat.conversion_rate,
                 stat.total_deposit)
            )
            await db.commit()

    async def recalculate_all_today_stats(self):
        """Recalculate stats for all active staff for today."""
        staff_list = await self.get_all_staff()
        for s in staff_list:
            stat = await self.calculate_daily_stats(s.id)
            await self.upsert_daily_stats(stat)

    async def get_daily_stats(self, staff_id: int, stat_date: Optional[date] = None) -> Optional[DailyStat]:
        if stat_date is None:
            stat_date = _utc_today()
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM daily_stats WHERE staff_id=? AND stat_date=?',
                (staff_id, stat_date.isoformat()))
            row = await cur.fetchone()
            if not row:
                return None
            return DailyStat(
                id=row['id'], staff_id=row['staff_id'],
                stat_date=date.fromisoformat(row['stat_date']),
                new_leads=row['new_leads'], contacted=row['contacted'],
                replied=row['replied'], registered=row['registered'],
                training=row['training'], withdrew=row['withdrew'],
                new_orders=row['new_orders'], ghosted=row['ghosted'],
                blocked=row['blocked'], dead=row['dead'],
                reply_rate=row['reply_rate'], conversion_rate=row['conversion_rate'],
                total_deposit=row['total_deposit'],
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            )

    async def get_team_daily_stats(self, stat_date: Optional[date] = None) -> List[DailyStat]:
        """Get all staff stats for a date."""
        if stat_date is None:
            stat_date = _utc_today()
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM daily_stats WHERE stat_date=? ORDER BY staff_id',
                (stat_date.isoformat(),))
            rows = await cur.fetchall()
            return [DailyStat(
                id=r['id'], staff_id=r['staff_id'],
                stat_date=date.fromisoformat(r['stat_date']),
                new_leads=r['new_leads'], contacted=r['contacted'],
                replied=r['replied'], registered=r['registered'],
                training=r['training'], withdrew=r['withdrew'],
                new_orders=r['new_orders'], ghosted=r['ghosted'],
                blocked=r['blocked'], dead=r['dead'],
                reply_rate=r['reply_rate'], conversion_rate=r['conversion_rate'],
                total_deposit=r['total_deposit'],
            ) for r in rows]

    # ─── Deposits ────────────────────────────────────────────────────────────

    async def create_deposit(self, d: Deposit) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO deposits (client_id, frontdesk_id, amount, currency, platform,
                   knife_number, role_type, note, deposit_date)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (d.client_id, d.frontdesk_id, d.amount, d.currency, d.platform,
                 d.knife_number, d.role_type, d.note, d.deposit_date.isoformat())
            )
            # Update client total
            await db.execute(
                'UPDATE clients SET total_deposited=total_deposited+? WHERE id=?',
                (d.amount, d.client_id))
            await db.commit()
            return cur.lastrowid

    async def get_deposits_by_client(self, client_id: int) -> List[Deposit]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM deposits WHERE client_id=? ORDER BY deposit_date DESC',
                (client_id,))
            rows = await cur.fetchall()
            return [Deposit(
                id=r['id'], client_id=r['client_id'], frontdesk_id=r['frontdesk_id'],
                amount=r['amount'], currency=r['currency'], platform=r['platform'],
                knife_number=r['knife_number'], role_type=r['role_type'], note=r['note'],
                deposit_date=date.fromisoformat(r['deposit_date']),
                created_at=datetime.fromisoformat(r['created_at']) if r['created_at'] else None,
            ) for r in rows]

    # ─── Reminders ──────────────────────────────────────────────────────────

    async def create_reminder(self, r: Reminder) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO reminders (staff_id, client_id, remind_at, message, source)
                   VALUES (?,?,?,?,?)""",
                (r.staff_id, r.client_id, r.remind_at.strftime('%Y-%m-%d %H:%M:%S'), r.message, r.source)
            )
            await db.commit()
            return cur.lastrowid

    async def get_pending_reminders_v2(self, before: Optional[datetime] = None) -> List[Reminder]:
        if before is None:
            before = datetime.now()
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT * FROM reminders WHERE is_sent=0 AND remind_at <= ?
                   ORDER BY remind_at ASC""",
                (before.strftime('%Y-%m-%d %H:%M:%S'),))
            rows = await cur.fetchall()
            return [Reminder(
                id=r['id'], staff_id=r['staff_id'], client_id=r['client_id'],
                remind_at=datetime.fromisoformat(r['remind_at']),
                message=r['message'], is_sent=bool(r['is_sent']),
                sent_at=datetime.fromisoformat(r['sent_at']) if r['sent_at'] else None,
                source=r['source'],
                created_at=datetime.fromisoformat(r['created_at']) if r['created_at'] else None,
            ) for r in rows]

    async def mark_reminder_sent(self, reminder_id: int):
        async with self.get_connection() as db:
            await db.execute(
                'UPDATE reminders SET is_sent=1, sent_at=CURRENT_TIMESTAMP WHERE id=?',
                (reminder_id,))
            await db.commit()

    # ─── Team Targets ────────────────────────────────────────────────────────

    async def upsert_team_target(self, t: TeamTarget) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO team_targets (team, period_type, period_start, period_end,
                   target_leads, target_registers, target_orders, target_deposit, created_by)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(team, period_type, period_start) DO UPDATE SET
                   period_end=excluded.period_end, target_leads=excluded.target_leads,
                   target_registers=excluded.target_registers, target_orders=excluded.target_orders,
                   target_deposit=excluded.target_deposit""",
                (t.team, t.period_type.value, t.period_start.isoformat(),
                 t.period_end.isoformat(), t.target_leads, t.target_registers,
                 t.target_orders, t.target_deposit, t.created_by)
            )
            await db.commit()
            return cur.lastrowid

    async def get_team_target(self, team: str, period_type: PeriodType,
                               period_start: date) -> Optional[TeamTarget]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM team_targets WHERE team=? AND period_type=? AND period_start=?',
                (team, period_type.value, period_start.isoformat()))
            row = await cur.fetchone()
            if not row:
                return None
            return TeamTarget(
                id=row['id'], team=row['team'],
                period_type=PeriodType(row['period_type']),
                period_start=date.fromisoformat(row['period_start']),
                period_end=date.fromisoformat(row['period_end']),
                target_leads=row['target_leads'], target_registers=row['target_registers'],
                target_orders=row['target_orders'], target_deposit=row['target_deposit'],
                created_by=row['created_by'],
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            )

    # ─── Bot Settings ────────────────────────────────────────────────────────

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with self.get_connection() as db:
            cur = await db.execute('SELECT value FROM bot_settings WHERE key=?', (key,))
            row = await cur.fetchone()
            return row['value'] if row else default

    async def set_setting(self, key: str, value: str, description: Optional[str] = None):
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO bot_settings (key, value, description, updated_at)
                   VALUES (?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
                (key, value, description))
            await db.commit()

    # ─── Embeddings ──────────────────────────────────────────────────────────

    def _pack_embedding(self, embedding: list) -> bytes:
        return struct.pack(f'{len(embedding)}f', *embedding)

    def _unpack_embedding(self, blob: bytes) -> list:
        n = len(blob) // 4
        return list(struct.unpack(f'{n}f', blob))

    async def upsert_embedding(self, source_type: str, source_id: int,
                                text_chunk: str, embedding: list):
        blob = self._pack_embedding(embedding)
        async with self.get_connection() as db:
            # Delete old embeddings for same source
            await db.execute(
                'DELETE FROM embeddings WHERE source_type=? AND source_id=?',
                (source_type, source_id))
            await db.execute(
                'INSERT INTO embeddings (source_type, source_id, text_chunk, embedding) VALUES (?,?,?,?)',
                (source_type, source_id, text_chunk, blob))
            await db.commit()

    async def get_all_embeddings(self) -> List[Dict[str, Any]]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT id, source_type, source_id, text_chunk, embedding FROM embeddings')
            rows = await cur.fetchall()
            return [{
                'id': r['id'],
                'source_type': r['source_type'],
                'source_id': r['source_id'],
                'text_chunk': r['text_chunk'],
                'embedding': self._unpack_embedding(r['embedding']),
            } for r in rows]

    # ─── Export ──────────────────────────────────────────────────────────────

    async def export_clients_csv(self, frontdesk_id: Optional[int] = None) -> List[Dict]:
        async with self.get_connection() as db:
            if frontdesk_id:
                cur = await db.execute(
                    'SELECT * FROM clients WHERE frontdesk_id=? ORDER BY created_at DESC',
                    (frontdesk_id,))
            else:
                cur = await db.execute('SELECT * FROM clients ORDER BY created_at DESC')
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ─── Additional helper methods ───────────────────────────────────────────

    async def get_staff_by_display_name(self, name: str) -> Optional[Staff]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM staff WHERE display_name=? LIMIT 1', (name,))
            row = await cur.fetchone()
            return self._row_to_staff(row) if row else None

    async def get_total_client_count(self, frontdesk_id: Optional[int] = None) -> int:
        async with self.get_connection() as db:
            if frontdesk_id is not None:
                cur = await db.execute(
                    'SELECT COUNT(*) FROM clients WHERE frontdesk_id=?', (frontdesk_id,))
            else:
                cur = await db.execute('SELECT COUNT(*) FROM clients')
            return (await cur.fetchone())[0]

    async def get_clients_by_frontdesk(self, frontdesk_id: int, limit: int = 50) -> List[Client]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM clients WHERE frontdesk_id=? ORDER BY updated_at DESC LIMIT ?',
                (frontdesk_id, limit))
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    async def update_client(self, client: Client):
        """Update mutable fields of an existing client (not status — use update_client_status)."""
        async with self.get_connection() as db:
            await db.execute(
                """UPDATE clients SET phone_remark=?, nickname=?, platform=?, account_id=?,
                   recruiter=?, status_note=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (client.phone_remark, client.nickname, client.platform, client.account_id,
                 client.recruiter, client.status_note, client.id)
            )
            await db.commit()

    async def set_client_handoff(self, client_id: int, maintenance_id: int,
                                  note: Optional[str] = None):
        """Mark client as handed off to maintenance person."""
        async with self.get_connection() as db:
            await db.execute(
                """UPDATE clients SET handoff_at=CURRENT_TIMESTAMP, handoff_note=?,
                   maintenance_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (note, maintenance_id, client_id))
            await db.commit()

    # ─── Team helpers ────────────────────────────────────────────────────────

    async def get_team_by_maintenance(self, maintenance_id: int) -> List[Staff]:
        """Return all frontdesk staff assigned to a maintenance person."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM staff WHERE maintenance_id=? AND is_active=1 ORDER BY display_name',
                (maintenance_id,))
            rows = await cur.fetchall()
            return [self._row_to_staff(r) for r in rows]

    async def get_maintenance_for_staff(self, staff_id: int) -> Optional[Staff]:
        """Return the maintenance person for a given frontdesk staff member."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT maintenance_id FROM staff WHERE id=?', (staff_id,))
            row = await cur.fetchone()
            if not row or not row['maintenance_id']:
                return None
            return await self.get_staff_by_id(row['maintenance_id'])

    async def get_all_clients_active(self, limit: int = 500) -> List[Client]:
        """All non-terminal clients across all staff, sorted by staleness."""
        terminal = ['blocked', 'scammed', 'dead']
        placeholders = ','.join('?' * len(terminal))
        async with self.get_connection() as db:
            cur = await db.execute(
                f"""SELECT * FROM clients WHERE status NOT IN ({placeholders})
                    ORDER BY updated_at ASC LIMIT ?""",
                (*terminal, limit))
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    # ─── Seed ────────────────────────────────────────────────────────────────

    async def seed_team_structure(self):
        """Create maintenance staff and wire frontdesk assignments (idempotent)."""
        seeded = await self.get_setting('team_structure_seeded')
        if seeded == '2':
            return

        async with self.get_connection() as db:
            maintenance_ids: Dict[str, int] = {}

            for maint_name in TEAM_STRUCTURE.keys():
                # Find existing staff by display_name
                cur = await db.execute(
                    'SELECT id FROM staff WHERE display_name=? LIMIT 1', (maint_name,))
                row = await cur.fetchone()

                if row:
                    maint_id = row['id']
                    await db.execute(
                        "UPDATE staff SET role='maintenance' WHERE id=?", (maint_id,))
                else:
                    # Create synthetic staff — deterministic negative TG ID
                    h = int(hashlib.md5(f'maint_{maint_name}'.encode()).hexdigest()[:8], 16)
                    synthetic_id = -(h % 900_000_000 + 1)
                    cur = await db.execute(
                        """INSERT INTO staff (tg_user_id, tg_chat_id, display_name, role, language, is_active)
                           VALUES (?, 0, ?, 'maintenance', 'zh', 1)
                           ON CONFLICT(tg_user_id) DO UPDATE SET role='maintenance'""",
                        (synthetic_id, maint_name))
                    maint_id = cur.lastrowid

                maintenance_ids[maint_name] = maint_id

            # Wire frontdesk staff to their maintenance person
            for maint_name, frontdesk_names in TEAM_STRUCTURE.items():
                maint_id = maintenance_ids[maint_name]
                for fd_name in frontdesk_names:
                    await db.execute(
                        'UPDATE staff SET maintenance_id=? WHERE display_name=?',
                        (maint_id, fd_name))

            await db.commit()

        await self.set_setting('team_structure_seeded', '2', 'Team structure seeded v2')
        logger.info('Team structure seeded: 阿俊 and 何军 assigned as maintenance (v2 + TINO/KUYA)')


    async def seed_additional_staff(self):
        """Ensure extra staff (阿文 etc.) exist as unassigned frontdesk (idempotent)."""
        EXTRA_FRONTDESK = ['阿文']
        async with self.get_connection() as db:
            for name in EXTRA_FRONTDESK:
                cur = await db.execute('SELECT id FROM staff WHERE display_name=? LIMIT 1', (name,))
                if await cur.fetchone():
                    continue
                h = int(hashlib.md5(f'extra_{name}'.encode()).hexdigest()[:8], 16)
                synthetic_id = -(h % 900_000_000 + 1_000_000)
                await db.execute(
                    """INSERT INTO staff (tg_user_id, tg_chat_id, display_name, role, language, is_active)
                       VALUES (?, 0, ?, 'frontdesk', 'zh', 1)
                       ON CONFLICT(tg_user_id) DO NOTHING""",
                    (synthetic_id, name))
            await db.commit()
        logger.info(f'seed_additional_staff: ensured {EXTRA_FRONTDESK}')

    async def auto_assign_teams(self) -> int:
        """Assign staff with team=NULL to teams based on TEAM_STRUCTURE name matching.

        Checks each staff member's display_name against TEAM_STRUCTURE member lists
        and sets their team column to the matching maintenance person name.
        Returns count of staff updated.
        """
        count = 0
        async with self.get_connection() as db:
            cur = await db.execute('SELECT id, display_name, team FROM staff WHERE team IS NULL')
            rows = await cur.fetchall()
            for row in rows:
                name = row['display_name']
                for team_name, members in TEAM_STRUCTURE.items():
                    if name in members:
                        await db.execute(
                            'UPDATE staff SET team=? WHERE id=?',
                            (team_name, row['id']))
                        count += 1
                        break
                # Also assign the maintenance leaders themselves
                if name in TEAM_STRUCTURE:
                    await db.execute(
                        'UPDATE staff SET team=? WHERE id=?',
                        (name, row['id']))
                    count += 1
            await db.commit()
        if count:
            logger.info(f'auto_assign_teams: assigned {count} staff')
        return count

    async def get_staff_by_username(self, username: str) -> Optional[Staff]:
        """Look up staff by Telegram username (with or without @)."""
        uname = username.lstrip('@')
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM staff WHERE tg_username = ? LIMIT 1', (uname,))
            row = await cur.fetchone()
            return self._row_to_staff(row) if row else None

    async def set_staff_team(self, staff_id: int, team: str):
        """Set the team for a staff member."""
        async with self.get_connection() as db:
            await db.execute('UPDATE staff SET team=? WHERE id=?', (team, staff_id))
            await db.commit()

    async def get_staff_by_team(self, team: str) -> List[Staff]:
        """Get all active staff in a given team."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT * FROM staff WHERE team=? AND is_active=1 ORDER BY display_name',
                (team,))
            rows = await cur.fetchall()
            return [self._row_to_staff(r) for r in rows]

    async def get_all_teams(self) -> List[str]:
        """Return distinct non-null team names."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT DISTINCT team FROM staff WHERE team IS NOT NULL ORDER BY team')
            rows = await cur.fetchall()
            return [r['team'] for r in rows]

    # ─── Groups CRUD ──────────────────────────────────────────────────────────

    async def link_group(self, tg_group_id: int, group_name: str, team: str, group_type: str = 'team'):
        """Link a Telegram group to a team (upsert)."""
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO groups (tg_group_id, group_name, team, group_type)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(tg_group_id) DO UPDATE SET
                       group_name=excluded.group_name,
                       team=excluded.team,
                       group_type=excluded.group_type""",
                (tg_group_id, group_name, team, group_type))
            await db.commit()

    async def unlink_group(self, tg_group_id: int) -> bool:
        """Remove a group link. Returns True if a row was deleted."""
        async with self.get_connection() as db:
            cur = await db.execute('DELETE FROM groups WHERE tg_group_id=?', (tg_group_id,))
            await db.commit()
            return cur.rowcount > 0

    async def get_group(self, tg_group_id: int) -> Optional[Dict[str, Any]]:
        """Return group record as dict, or None."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT tg_group_id, group_name, team, group_type, created_at FROM groups WHERE tg_group_id=?',
                (tg_group_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    # ─── Task Queue ──────────────────────────────────────────────────────────

    async def create_task(self, task: Any) -> int:
        import json
        scheduled = task.scheduled_time.strftime('%Y-%m-%d %H:%M:%S') if task.scheduled_time else None
        data_json = json.dumps(task.data) if task.data else None
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO bot_tasks (task_type, priority, data, status, scheduled_time, max_attempts)
                   VALUES (?,?,?,?,?,?)""",
                (task.task_type, task.priority, data_json,
                 getattr(task, 'status', 'pending'), scheduled,
                 getattr(task, 'max_attempts', 3))
            )
            await db.commit()
            return cur.lastrowid

    async def get_next_task(self) -> Optional[Any]:
        import json
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT * FROM bot_tasks WHERE status='pending'
                   AND (scheduled_time IS NULL OR scheduled_time <= CURRENT_TIMESTAMP)
                   ORDER BY priority ASC, created_at ASC LIMIT 1""")
            row = await cur.fetchone()
            if not row:
                return None
        from models_v2 import BotTask
        return BotTask(
            id=row['id'],
            task_type=row['task_type'],
            priority=row['priority'],
            data=json.loads(row['data']) if row['data'] else {},
            status=row['status'],
            scheduled_time=datetime.fromisoformat(row['scheduled_time']) if row['scheduled_time'] else None,
            attempts=row['attempts'],
            max_attempts=row['max_attempts'],
            error_message=row['error_message'],
        )

    async def update_task_status(self, task_id: int, status: str, error: str = None):
        async with self.get_connection() as db:
            await db.execute(
                """UPDATE bot_tasks SET status=?, error_message=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (status, error, task_id)
            )
            if status == 'processing':
                await db.execute(
                    'UPDATE bot_tasks SET attempts=attempts+1 WHERE id=?', (task_id,))
            await db.commit()

    async def cleanup_old_tasks(self, days_old: int = 1):
        async with self.get_connection() as db:
            await db.execute(
                """DELETE FROM bot_tasks WHERE status IN ('completed','failed')
                   AND updated_at <= datetime('now', ? || ' days')""",
                (f'-{days_old}',)
            )
            await db.commit()

    # ─── Conversation States ─────────────────────────────────────────────────

    async def set_conversation_state(self, user_id: int, state: Dict[str, Any]):
        import json
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO conversation_states (user_id, state_data, updated_at)
                   VALUES (?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(user_id) DO UPDATE SET
                       state_data=excluded.state_data,
                       updated_at=CURRENT_TIMESTAMP""",
                (user_id, json.dumps(state))
            )
            await db.commit()

    async def get_conversation_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        import json
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT state_data FROM conversation_states WHERE user_id=?', (user_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return json.loads(row['state_data']) if row['state_data'] else None

    async def clear_conversation_state(self, user_id: int):
        async with self.get_connection() as db:
            await db.execute('DELETE FROM conversation_states WHERE user_id=?', (user_id,))
            await db.commit()

    async def cleanup_old_conversation_states(self, hours_old: int = 24):
        async with self.get_connection() as db:
            await db.execute(
                "DELETE FROM conversation_states WHERE updated_at <= datetime('now', ? || ' hours')",
                (f'-{hours_old}',)
            )
            await db.commit()

    # ─── User Activity ───────────────────────────────────────────────────────

    async def register_or_update_activity(
        self, tg_user_id: int, tg_chat_id: int,
        username: Optional[str], first_name: Optional[str], last_name: Optional[str]
    ) -> 'Staff':
        display = first_name or username or str(tg_user_id)
        if first_name and last_name:
            display = f'{first_name} {last_name}'
        existing = await self.get_staff_by_tg_id(tg_user_id)
        if existing:
            async with self.get_connection() as db:
                await db.execute(
                    'UPDATE staff SET tg_chat_id=?, tg_username=?, last_active_at=CURRENT_TIMESTAMP WHERE tg_user_id=?',
                    (tg_chat_id, username, tg_user_id)
                )
                await db.commit()
            return existing
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO staff (tg_user_id, tg_chat_id, tg_username, display_name, role, language, is_active)
                   VALUES (?,?,?,?,'viewer','zh',1)""",
                (tg_user_id, tg_chat_id, username, display)
            )
            await db.commit()
        return await self.get_staff_by_tg_id(tg_user_id)

    async def get_user_language(self, user_id: int) -> Optional[str]:
        async with self.get_connection() as db:
            cur = await db.execute('SELECT language FROM staff WHERE tg_user_id=?', (user_id,))
            row = await cur.fetchone()
            return row['language'] if row else None

    async def set_user_language(self, user_id: int, language: str):
        async with self.get_connection() as db:
            await db.execute('UPDATE staff SET language=? WHERE tg_user_id=?', (language, user_id))
            await db.commit()

    # ─── Health / Stats / Backup ─────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, int]:
        tables = [
            'staff', 'clients', 'client_notes', 'daily_stats', 'deposits',
            'reminders', 'team_targets', 'bot_settings', 'bot_tasks', 'conversation_states',
        ]
        stats: Dict[str, int] = {}
        async with self.get_connection() as db:
            for table in tables:
                try:
                    cur = await db.execute(f'SELECT COUNT(*) FROM {table}')
                    stats[table] = (await cur.fetchone())[0]
                except Exception:
                    stats[table] = 0
        return stats

    async def backup_database(self) -> str:
        import shutil
        backup_path = self.db_path + '.bak'
        try:
            shutil.copy2(self.db_path, backup_path)
            logger.info(f'Database backed up to {backup_path}')
            return backup_path
        except Exception as e:
            logger.error(f'Database backup failed: {e}')
            return ''

    # ─── Gamification: Leaderboard ───────────────────────────────────────────────

    async def get_leaderboard(self, period: str = 'today', team: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return staff ranked by leads/orders/deposits/reply_rate for period.
        period: 'today' | 'week' | 'month'
        """
        today = _utc_today()
        if period == 'today':
            date_filter = today.isoformat()
            where_clause = 'ds.stat_date = ?'
            params_date = [date_filter]
        elif period == 'week':
            week_start = (today - timedelta(days=today.weekday())).isoformat()
            where_clause = 'ds.stat_date >= ?'
            params_date = [week_start]
        else:  # month
            month_start = today.replace(day=1).isoformat()
            where_clause = 'ds.stat_date >= ?'
            params_date = [month_start]

        async with self.get_connection() as db:
            team_filter = 'AND s.team = ?' if team else ''
            params = params_date + ([team] if team else [])
            cur = await db.execute(
                f"""SELECT s.id, s.display_name, s.team,
                           COALESCE(SUM(ds.new_leads), 0) as total_leads,
                           COALESCE(SUM(ds.new_orders), 0) as total_orders,
                           COALESCE(SUM(ds.total_deposit), 0) as total_deposits,
                           COALESCE(AVG(ds.reply_rate), 0) as avg_reply_rate
                    FROM staff s
                    LEFT JOIN daily_stats ds ON s.id = ds.staff_id AND {where_clause}
                    WHERE s.is_active = 1 AND s.role IN ('frontdesk','newbie','customer_service') {team_filter}
                    GROUP BY s.id, s.display_name, s.team
                    ORDER BY total_orders DESC, total_leads DESC, total_deposits DESC""",
                params
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ─── Gamification: Hot Leads ─────────────────────────────────────────────────

    async def get_hot_leads(self, frontdesk_id: Optional[int] = None,
                             team_staff_ids: Optional[List[int]] = None,
                             limit: int = 10) -> List[Dict[str, Any]]:
        """Score and return top hot leads.
        Score = 10 (base) + 20 (replied) + 30 (registered) + 15 (deposit>0)
                + 10 (updated<24h) - 5*stale_days + 5*deposit_count, capped 100.
        """
        async with self.get_connection() as db:
            if frontdesk_id:
                cur = await db.execute(
                    """SELECT c.id, c.phone, c.nickname, c.status, c.total_deposited,
                              c.replied_at, c.registered_at, c.updated_at, c.frontdesk_id,
                              s.display_name as frontdesk_name,
                              (SELECT COUNT(*) FROM deposits d WHERE d.client_id = c.id) as deposit_count
                       FROM clients c
                       JOIN staff s ON c.frontdesk_id = s.id
                       WHERE c.frontdesk_id = ?
                       AND c.status NOT IN ('blocked','scammed','dead')""",
                    (frontdesk_id,)
                )
            elif team_staff_ids:
                placeholders = ','.join('?' * len(team_staff_ids))
                cur = await db.execute(
                    f"""SELECT c.id, c.phone, c.nickname, c.status, c.total_deposited,
                               c.replied_at, c.registered_at, c.updated_at, c.frontdesk_id,
                               s.display_name as frontdesk_name,
                               (SELECT COUNT(*) FROM deposits d WHERE d.client_id = c.id) as deposit_count
                        FROM clients c
                        JOIN staff s ON c.frontdesk_id = s.id
                        WHERE c.frontdesk_id IN ({placeholders})
                        AND c.status NOT IN ('blocked','scammed','dead')""",
                    team_staff_ids
                )
            else:
                cur = await db.execute(
                    """SELECT c.id, c.phone, c.nickname, c.status, c.total_deposited,
                              c.replied_at, c.registered_at, c.updated_at, c.frontdesk_id,
                              s.display_name as frontdesk_name,
                              (SELECT COUNT(*) FROM deposits d WHERE d.client_id = c.id) as deposit_count
                       FROM clients c
                       JOIN staff s ON c.frontdesk_id = s.id
                       WHERE c.status NOT IN ('blocked','scammed','dead')"""
                )
            rows = await cur.fetchall()

        now = datetime.now()
        scored = []
        for r in rows:
            score = 10  # base
            if r['replied_at']:
                score += 20
            if r['registered_at']:
                score += 30
            if r['total_deposited'] and r['total_deposited'] > 0:
                score += 15
            updated = datetime.fromisoformat(r['updated_at']) if r['updated_at'] else now
            hours_since = (now - updated).total_seconds() / 3600
            if hours_since < 24:
                score += 10
            else:
                stale_days = int(hours_since / 24) - 1
                score -= stale_days * 5
            deposit_count = r['deposit_count'] or 0
            score += deposit_count * 5
            score = min(100, max(0, score))
            d = dict(r)
            d['score'] = score
            scored.append(d)

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:limit]

    # ─── Gamification: Templates ─────────────────────────────────────────────────

    async def get_templates(self, team: Optional[str] = None) -> List[Dict[str, Any]]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT id, name, content, category, is_default, created_at FROM message_templates ORDER BY is_default DESC, name ASC'
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_template_by_id(self, template_id: int) -> Optional[Dict[str, Any]]:
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT id, name, content, category, is_default, created_at FROM message_templates WHERE id=?',
                (template_id,)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def create_template(self, name: str, content: str, category: str,
                               created_by: int, is_default: bool = False) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                'INSERT INTO message_templates (name, content, category, created_by, is_default) VALUES (?,?,?,?,?)',
                (name, content, category, created_by, 1 if is_default else 0)
            )
            await db.commit()
            return cur.lastrowid

    async def delete_template(self, template_id: int) -> bool:
        async with self.get_connection() as db:
            cur = await db.execute('DELETE FROM message_templates WHERE id=? AND is_default=0', (template_id,))
            await db.commit()
            return cur.rowcount > 0

    async def seed_default_templates(self):
        """Seed 5 default Chinese message templates (idempotent)."""
        seeded = await self.get_setting('default_templates_seeded')
        if seeded == '1':
            return
        defaults = [
            ('初次问候', '你好！我是平台客服，请问您有什么可以帮您的吗？😊', 'greeting'),
            ('注册引导', '欢迎加入！请点击以下链接完成注册，只需2分钟即可开始赚钱：', 'onboarding'),
            ('跟进提醒', '您好，我们已经准备好了您的专属资料，方便现在为您介绍吗？', 'followup'),
            ('存款引导', '恭喜您完成注册！首次存款即可获得额外奖励，立即体验！💰', 'deposit'),
            ('复活跟进', '好久不见！最近平台有新活动，您是否有兴趣了解一下？🎁', 'reactivate'),
        ]
        async with self.get_connection() as db:
            for name, content, category in defaults:
                await db.execute(
                    'INSERT INTO message_templates (name, content, category, created_by, is_default) VALUES (?,?,?,NULL,1)',
                    (name, content, category)
                )
            await db.commit()
        await self.set_setting('default_templates_seeded', '1', 'Default templates seeded')

    # ─── Gamification: Contests ──────────────────────────────────────────────────

    async def create_contest(self, title: str, metric: str, target: Optional[float],
                              team: Optional[str], end_date: datetime, created_by: int) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO contests (title, metric, target, team, end_date, status, created_by)
                   VALUES (?,?,?,?,?,?,?)""",
                (title, metric, target, team, end_date.strftime('%Y-%m-%d %H:%M:%S'), 'active', created_by)
            )
            await db.commit()
            return cur.lastrowid

    async def get_active_contest(self, team: Optional[str] = None) -> Optional[Dict[str, Any]]:
        async with self.get_connection() as db:
            if team:
                cur = await db.execute(
                    """SELECT * FROM contests
                       WHERE status='active' AND (team=? OR team IS NULL)
                       AND end_date > CURRENT_TIMESTAMP
                       ORDER BY created_at DESC LIMIT 1""",
                    (team,)
                )
            else:
                cur = await db.execute(
                    """SELECT * FROM contests
                       WHERE status='active' AND end_date > CURRENT_TIMESTAMP
                       ORDER BY created_at DESC LIMIT 1"""
                )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def end_contest(self, contest_id: int) -> Optional[Dict[str, Any]]:
        """Mark contest ended, compute winner from contest_scores."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT cs.staff_id, cs.score, s.display_name
                   FROM contest_scores cs
                   JOIN staff s ON cs.staff_id = s.id
                   WHERE cs.contest_id = ?
                   ORDER BY cs.score DESC LIMIT 1""",
                (contest_id,)
            )
            winner_row = await cur.fetchone()
            winner_id = winner_row['staff_id'] if winner_row else None
            await db.execute(
                'UPDATE contests SET status=?, winner_id=? WHERE id=?',
                ('ended', winner_id, contest_id)
            )
            await db.commit()
            return dict(winner_row) if winner_row else None

    async def get_contest_scores(self, contest_id: int) -> List[Dict[str, Any]]:
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT cs.staff_id, cs.score, cs.updated_at, s.display_name
                   FROM contest_scores cs
                   JOIN staff s ON cs.staff_id = s.id
                   WHERE cs.contest_id = ?
                   ORDER BY cs.score DESC""",
                (contest_id,)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def upsert_contest_score(self, contest_id: int, staff_id: int, score: float):
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO contest_scores (contest_id, staff_id, score, updated_at)
                   VALUES (?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(contest_id, staff_id) DO UPDATE SET
                   score=excluded.score, updated_at=CURRENT_TIMESTAMP""",
                (contest_id, staff_id, score)
            )
            await db.commit()

    async def refresh_contest_scores(self, contest_id: int):
        """Recalculate scores for all staff in an active contest based on metric."""
        contest = await self.get_active_contest()
        if not contest or contest['id'] != contest_id:
            return
        metric = contest['metric']
        today = _utc_today()
        start = datetime.fromisoformat(contest['start_date']).date() if contest.get('start_date') else today
        all_staff = await self.get_all_staff()
        for s in all_staff:
            if contest.get('team') and s.team != contest['team']:
                continue
            if s.role.value not in ('frontdesk', 'newbie', 'customer_service'):
                continue
            async with self.get_connection() as db:
                if metric == 'leads':
                    cur = await db.execute(
                        'SELECT COALESCE(SUM(new_leads),0) FROM daily_stats WHERE staff_id=? AND stat_date >= ?',
                        (s.id, start.isoformat())
                    )
                elif metric == 'orders':
                    cur = await db.execute(
                        'SELECT COALESCE(SUM(new_orders),0) FROM daily_stats WHERE staff_id=? AND stat_date >= ?',
                        (s.id, start.isoformat())
                    )
                elif metric == 'deposits':
                    cur = await db.execute(
                        'SELECT COALESCE(SUM(total_deposit),0) FROM daily_stats WHERE staff_id=? AND stat_date >= ?',
                        (s.id, start.isoformat())
                    )
                elif metric == 'reply_rate':
                    cur = await db.execute(
                        'SELECT COALESCE(AVG(reply_rate),0) FROM daily_stats WHERE staff_id=? AND stat_date >= ?',
                        (s.id, start.isoformat())
                    )
                else:
                    continue
                score = (await cur.fetchone())[0] or 0
            await self.upsert_contest_score(contest_id, s.id, score)

    async def auto_end_expired_contests(self) -> int:
        """End all contests whose end_date has passed. Returns count ended."""
        async with self.get_connection() as db:
            cur = await db.execute(
                "SELECT id FROM contests WHERE status='active' AND end_date <= CURRENT_TIMESTAMP"
            )
            rows = await cur.fetchall()
        count = 0
        for row in rows:
            await self.end_contest(row['id'])
            count += 1
        return count

    # ─── Gamification V2: XP ─────────────────────────────────────────────────────

    async def award_xp(self, staff_id: int, action: str, amount: int) -> int:
        """Insert XP event and update streak. Returns amount awarded."""
        async with self.get_connection() as db:
            await db.execute(
                'INSERT INTO xp_events (staff_id, action, xp_amount) VALUES (?,?,?)',
                (staff_id, action, amount)
            )
            await db.commit()
        await self.update_streak(staff_id)
        return amount

    async def get_staff_xp(self, staff_id: int, period: str = 'all') -> int:
        """Return total XP for staff over period (today|week|month|all)."""
        today = _utc_today()
        async with self.get_connection() as db:
            if period == 'today':
                cur = await db.execute(
                    'SELECT COALESCE(SUM(xp_amount),0) FROM xp_events WHERE staff_id=? AND DATE(created_at)=?',
                    (staff_id, today.isoformat())
                )
            elif period == 'week':
                week_start = (today - timedelta(days=today.weekday())).isoformat()
                cur = await db.execute(
                    'SELECT COALESCE(SUM(xp_amount),0) FROM xp_events WHERE staff_id=? AND DATE(created_at)>=?',
                    (staff_id, week_start)
                )
            elif period == 'month':
                month_start = today.replace(day=1).isoformat()
                cur = await db.execute(
                    'SELECT COALESCE(SUM(xp_amount),0) FROM xp_events WHERE staff_id=? AND DATE(created_at)>=?',
                    (staff_id, month_start)
                )
            else:
                cur = await db.execute(
                    'SELECT COALESCE(SUM(xp_amount),0) FROM xp_events WHERE staff_id=?',
                    (staff_id,)
                )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    # ─── Gamification V2: Streaks ────────────────────────────────────────────────

    async def update_streak(self, staff_id: int):
        """Update daily streak for staff based on today's activity."""
        today = _utc_today()
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT current_streak, longest_streak, last_action_date, freeze_available FROM streaks WHERE staff_id=?',
                (staff_id,)
            )
            row = await cur.fetchone()

            if row is None:
                await db.execute(
                    'INSERT INTO streaks (staff_id, current_streak, longest_streak, last_action_date, freeze_available) VALUES (?,1,1,?,1)',
                    (staff_id, today.isoformat())
                )
                await db.commit()
                return

            current = row['current_streak'] or 0
            longest = row['longest_streak'] or 0
            last_date_str = row['last_action_date']

            if last_date_str:
                last_date = date.fromisoformat(last_date_str)
                if last_date == today:
                    return  # already active today, no change
                gap = (today - last_date).days
                if gap == 1:
                    current += 1
                else:
                    current = 1  # streak broken
            else:
                current = 1

            longest = max(longest, current)
            await db.execute(
                'UPDATE streaks SET current_streak=?, longest_streak=?, last_action_date=? WHERE staff_id=?',
                (current, longest, today.isoformat(), staff_id)
            )
            await db.commit()

    async def get_streak(self, staff_id: int) -> Dict[str, Any]:
        """Return streak row for staff (or defaults if not found)."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT current_streak, longest_streak, last_action_date, freeze_available FROM streaks WHERE staff_id=?',
                (staff_id,)
            )
            row = await cur.fetchone()
        if row:
            return dict(row)
        return {'current_streak': 0, 'longest_streak': 0, 'last_action_date': None, 'freeze_available': 1}

    async def use_streak_freeze(self, staff_id: int) -> bool:
        """Use one streak freeze for staff. Returns True if freeze was available."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT freeze_available FROM streaks WHERE staff_id=?',
                (staff_id,)
            )
            row = await cur.fetchone()
            if not row or row['freeze_available'] < 1:
                return False
            await db.execute(
                'UPDATE streaks SET freeze_available=freeze_available-1 WHERE staff_id=?',
                (staff_id,)
            )
            await db.commit()
        return True

    async def reset_weekly_streak_freezes(self):
        """Reset freeze_available to 1 for all staff (run on Mondays)."""
        async with self.get_connection() as db:
            await db.execute('UPDATE streaks SET freeze_available=1')
            await db.commit()

    # ─── Gamification V2: Badges ─────────────────────────────────────────────────

    async def seed_badges(self):
        """Seed 10 default badges (idempotent)."""
        seeded = await self.get_setting('badges_seeded_v2')
        if seeded == '1':
            return
        defaults = [
            ('首次连续',   '🔥', '保持3天连续打卡',     None,  'streak_3'),
            ('速度之星',   '⚡', '快速回复10次',        None,  'fast_reply_10'),
            ('百发百中',   '🎯', '完成100次状态更新',   None,  'update_100'),
            ('语音达人',   '🗣️', '发送50次语音更新',    None,  'voice_50'),
            ('勤劳蜜蜂',   '🏃', '保持7天连续打卡',     None,  'streak_7'),
            ('钻石选手',   '💎', '保持30天连续打卡',    None,  'streak_30'),
            ('新星',       '🌟', '累计获得50 XP',       50,    None),
            ('MVP',        '🏆', '累计获得1000 XP',     1000,  None),
            ('增长王',     '📈', '新增50个客户',        None,  'add_client_50'),
            ('传奇',       '👑', '保持100天连续打卡',   None,  'streak_100'),
        ]
        async with self.get_connection() as db:
            for name, emoji, desc, xp_threshold, action_type in defaults:
                await db.execute(
                    'INSERT INTO badges (name, emoji, description, xp_threshold, action_type) VALUES (?,?,?,?,?)',
                    (name, emoji, desc, xp_threshold, action_type)
                )
            await db.commit()
        await self.set_setting('badges_seeded_v2', '1', 'Default badges seeded')

    async def check_and_award_badges(self, staff_id: int) -> List[Dict[str, Any]]:
        """Check all unearned badges and award any newly qualified. Returns newly awarded badges."""
        total_xp = await self.get_staff_xp(staff_id, 'all')
        streak = await self.get_streak(staff_id)
        current_streak = streak.get('current_streak', 0)

        # Count action-based events
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT action, COUNT(*) as cnt FROM xp_events WHERE staff_id=? GROUP BY action',
                (staff_id,)
            )
            rows = await cur.fetchall()
        action_counts = {r['action']: r['cnt'] for r in rows}

        # Load all badges
        async with self.get_connection() as db:
            cur = await db.execute('SELECT id, name, emoji, description, xp_threshold, action_type FROM badges')
            all_badges = [dict(r) for r in await cur.fetchall()]

        # Load already-earned badge IDs
        async with self.get_connection() as db:
            cur = await db.execute('SELECT badge_id FROM staff_badges WHERE staff_id=?', (staff_id,))
            earned_ids = {r['badge_id'] for r in await cur.fetchall()}

        newly_awarded = []
        for badge in all_badges:
            if badge['id'] in earned_ids:
                continue
            qualified = False
            if badge['xp_threshold'] is not None and total_xp >= badge['xp_threshold']:
                qualified = True
            elif badge['action_type']:
                atype = badge['action_type']
                if atype == 'streak_3' and current_streak >= 3:
                    qualified = True
                elif atype == 'streak_7' and current_streak >= 7:
                    qualified = True
                elif atype == 'streak_30' and current_streak >= 30:
                    qualified = True
                elif atype == 'streak_100' and current_streak >= 100:
                    qualified = True
                elif atype == 'fast_reply_10' and action_counts.get('reply_within_1h', 0) >= 10:
                    qualified = True
                elif atype == 'update_100' and action_counts.get('update_status', 0) >= 100:
                    qualified = True
                elif atype == 'voice_50' and action_counts.get('voice_update', 0) >= 50:
                    qualified = True
                elif atype == 'add_client_50' and action_counts.get('add_client', 0) >= 50:
                    qualified = True
            if qualified:
                try:
                    async with self.get_connection() as db:
                        await db.execute(
                            'INSERT OR IGNORE INTO staff_badges (staff_id, badge_id) VALUES (?,?)',
                            (staff_id, badge['id'])
                        )
                        await db.commit()
                    newly_awarded.append(badge)
                except Exception:
                    pass
        return newly_awarded

    async def get_staff_badges(self, staff_id: int) -> List[Dict[str, Any]]:
        """Return all badges earned by staff with badge details."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT b.id, b.name, b.emoji, b.description, b.xp_threshold, b.action_type,
                          sb.earned_at
                   FROM staff_badges sb
                   JOIN badges b ON sb.badge_id = b.id
                   WHERE sb.staff_id=?
                   ORDER BY sb.earned_at ASC""",
                (staff_id,)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_all_badges(self) -> List[Dict[str, Any]]:
        """Return all badge definitions."""
        async with self.get_connection() as db:
            cur = await db.execute('SELECT id, name, emoji, description, xp_threshold, action_type FROM badges ORDER BY id')
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ─── Follow-up Sequences ─────────────────────────────────────────────────

    async def create_sequence(self, name: str, stage: str, delays: list, templates: list) -> int:
        import json as _json
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT OR IGNORE INTO follow_up_sequences (name, stage, delays_json, templates_json, enabled)
                   VALUES (?,?,?,?,1)""",
                (name, stage, _json.dumps(delays, ensure_ascii=False),
                 _json.dumps(templates, ensure_ascii=False))
            )
            await db.commit()
            return cur.lastrowid or 0

    async def get_sequences(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        import json as _json
        async with self.get_connection() as db:
            if enabled_only:
                cur = await db.execute(
                    'SELECT id, name, stage, delays_json, templates_json, enabled, created_at '
                    'FROM follow_up_sequences WHERE enabled=1 ORDER BY id')
            else:
                cur = await db.execute(
                    'SELECT id, name, stage, delays_json, templates_json, enabled, created_at '
                    'FROM follow_up_sequences ORDER BY id')
            rows = await cur.fetchall()
            result = []
            for r in rows:
                result.append({
                    'id': r['id'], 'name': r['name'], 'stage': r['stage'],
                    'delays': _json.loads(r['delays_json']),
                    'templates': _json.loads(r['templates_json']),
                    'enabled': bool(r['enabled']),
                    'created_at': r['created_at'],
                })
            return result

    async def toggle_sequence(self, seq_id: int, enabled: bool) -> bool:
        async with self.get_connection() as db:
            cur = await db.execute(
                'UPDATE follow_up_sequences SET enabled=? WHERE id=?', (1 if enabled else 0, seq_id))
            await db.commit()
            return cur.rowcount > 0

    async def enqueue_followup(self, client_id: int, sequence_id: int, next_send_at: datetime) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO follow_up_queue (client_id, sequence_id, step, next_send_at, status)
                   VALUES (?,?,0,?,?)""",
                (client_id, sequence_id, next_send_at.isoformat(), 'pending')
            )
            await db.commit()
            return cur.lastrowid

    async def get_due_followups(self, before: Optional[datetime] = None) -> List[Dict[str, Any]]:
        import json as _json
        if before is None:
            before = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT q.id, q.client_id, q.sequence_id, q.step, q.next_send_at, q.status,
                          s.name AS seq_name, s.stage, s.delays_json, s.templates_json
                   FROM follow_up_queue q
                   JOIN follow_up_sequences s ON s.id = q.sequence_id
                   WHERE q.status = 'pending' AND q.next_send_at <= ?
                   ORDER BY q.next_send_at ASC""",
                (before.isoformat(),)
            )
            rows = await cur.fetchall()
            result = []
            for r in rows:
                result.append({
                    'id': r['id'], 'client_id': r['client_id'],
                    'sequence_id': r['sequence_id'], 'step': r['step'],
                    'next_send_at': r['next_send_at'], 'status': r['status'],
                    'seq_name': r['seq_name'], 'stage': r['stage'],
                    'delays': _json.loads(r['delays_json']),
                    'templates': _json.loads(r['templates_json']),
                })
            return result

    async def advance_followup_step(self, queue_id: int, next_step: int, next_send_at: datetime):
        async with self.get_connection() as db:
            await db.execute(
                'UPDATE follow_up_queue SET step=?, next_send_at=?, status=? WHERE id=?',
                (next_step, next_send_at.isoformat(), 'pending', queue_id)
            )
            await db.commit()

    async def complete_followup(self, queue_id: int, status: str = 'completed'):
        async with self.get_connection() as db:
            await db.execute(
                "UPDATE follow_up_queue SET status=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, queue_id)
            )
            await db.commit()

    async def cancel_followup(self, client_id: int):
        async with self.get_connection() as db:
            await db.execute(
                "UPDATE follow_up_queue SET status='cancelled', completed_at=CURRENT_TIMESTAMP "
                "WHERE client_id=? AND status='pending'",
                (client_id,)
            )
            await db.commit()

    async def get_client_active_followup(self, client_id: int) -> Optional[Dict[str, Any]]:
        import json as _json
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT q.id, q.client_id, q.sequence_id, q.step, q.next_send_at, q.status,
                          s.name AS seq_name, s.stage, s.delays_json, s.templates_json
                   FROM follow_up_queue q
                   JOIN follow_up_sequences s ON s.id = q.sequence_id
                   WHERE q.client_id=? AND q.status='pending'
                   ORDER BY q.created_at DESC LIMIT 1""",
                (client_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {
                'id': row['id'], 'client_id': row['client_id'],
                'sequence_id': row['sequence_id'], 'step': row['step'],
                'next_send_at': row['next_send_at'], 'status': row['status'],
                'seq_name': row['seq_name'], 'stage': row['stage'],
                'delays': _json.loads(row['delays_json']),
                'templates': _json.loads(row['templates_json']),
            }

    async def get_xp_leaderboard(self, period: str = 'today', team_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """XP-based leaderboard with streak info."""
        today = _utc_today()
        if period == 'today':
            date_filter = today.isoformat()
            xp_sql = f"AND DATE(xe.created_at) = '{date_filter}'"
        elif period == 'week':
            week_start = (today - timedelta(days=today.weekday())).isoformat()
            xp_sql = f"AND DATE(xe.created_at) >= '{week_start}'"
        elif period == 'month':
            month_start = today.replace(day=1).isoformat()
            xp_sql = f"AND DATE(xe.created_at) >= '{month_start}'"
        else:
            xp_sql = ''

        team_clause = f"AND s.team = '{team_id}'" if team_id else ''

        query = f"""
            SELECT s.id, s.display_name, s.team,
                   COALESCE(SUM(xe.xp_amount), 0) AS total_xp,
                   COALESCE(st.current_streak, 0) AS current_streak
            FROM staff s
            LEFT JOIN xp_events xe ON xe.staff_id = s.id {xp_sql}
            LEFT JOIN streaks st ON st.staff_id = s.id
            WHERE s.is_active = 1 {team_clause}
            GROUP BY s.id, s.display_name, s.team, st.current_streak
            ORDER BY total_xp DESC, current_streak DESC
            LIMIT 20
        """
        async with self.get_connection() as db:
            cur = await db.execute(query)
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ─── Broadcast ───────────────────────────────────────────────────────────

    async def create_broadcast_log(self, staff_id: int, template: str,
                                   segment_filter: str, total_targets: int) -> int:
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO broadcast_log (staff_id, template, segment_filter, total_targets)
                   VALUES (?, ?, ?, ?)""",
                (staff_id, template, segment_filter, total_targets))
            await db.commit()
            return cur.lastrowid

    async def update_broadcast_log(self, log_id: int, sent_count: int,
                                   failed_count: int, completed: bool = False):
        async with self.get_connection() as db:
            if completed:
                await db.execute(
                    """UPDATE broadcast_log SET sent_count=?, failed_count=?,
                       completed_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (sent_count, failed_count, log_id))
            else:
                await db.execute(
                    'UPDATE broadcast_log SET sent_count=?, failed_count=? WHERE id=?',
                    (sent_count, failed_count, log_id))
            await db.commit()

    async def get_broadcast_targets(self, segment_type: str, segment_value: str,
                                    date_from: Optional[str] = None,
                                    date_to: Optional[str] = None) -> List[Dict]:
        """Return clients matching the segment filter for broadcast."""
        async with self.get_connection() as db:
            if segment_type == 'status':
                cur = await db.execute(
                    """SELECT c.id, c.phone, c.nickname, c.status, c.source,
                              c.contacted_at, s.display_name as frontdesk_name
                       FROM clients c
                       JOIN staff s ON c.frontdesk_id = s.id
                       WHERE c.status = ?""",
                    (segment_value,))
            elif segment_type == 'team':
                cur = await db.execute(
                    """SELECT c.id, c.phone, c.nickname, c.status, c.source,
                              c.contacted_at, s.display_name as frontdesk_name
                       FROM clients c
                       JOIN staff s ON c.frontdesk_id = s.id
                       WHERE s.team = ?""",
                    (segment_value,))
            elif segment_type == 'source':
                cur = await db.execute(
                    """SELECT c.id, c.phone, c.nickname, c.status, c.source,
                              c.contacted_at, s.display_name as frontdesk_name
                       FROM clients c
                       JOIN staff s ON c.frontdesk_id = s.id
                       WHERE c.source = ?""",
                    (segment_value,))
            elif segment_type == 'date_range' and date_from and date_to:
                cur = await db.execute(
                    """SELECT c.id, c.phone, c.nickname, c.status, c.source,
                              c.contacted_at, s.display_name as frontdesk_name
                       FROM clients c
                       JOIN staff s ON c.frontdesk_id = s.id
                       WHERE DATE(c.created_at) BETWEEN ? AND ?""",
                    (date_from, date_to))
            else:
                return []
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_broadcast_logs(self, staff_id: Optional[int] = None,
                                 limit: int = 10) -> List[Dict]:
        async with self.get_connection() as db:
            if staff_id:
                cur = await db.execute(
                    """SELECT * FROM broadcast_log WHERE staff_id=?
                       ORDER BY started_at DESC LIMIT ?""",
                    (staff_id, limit))
            else:
                cur = await db.execute(
                    'SELECT * FROM broadcast_log ORDER BY started_at DESC LIMIT ?',
                    (limit,))
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


    # ─── Phase 9A: Client Tags ────────────────────────────────────────────────

    async def add_tag(self, client_id: int, tag: str, tagged_by: int) -> bool:
        """Add a tag to a client. Returns True if inserted, False if already existed."""
        import sqlite3
        async with self.get_connection() as db:
            try:
                await db.execute(
                    'INSERT INTO client_tags (client_id, tag, tagged_by) VALUES (?,?,?)',
                    (client_id, tag.lower().strip(), tagged_by))
                await db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    async def remove_tag(self, client_id: int, tag: str) -> bool:
        """Remove a tag from a client. Returns True if deleted."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'DELETE FROM client_tags WHERE client_id=? AND tag=?',
                (client_id, tag.lower().strip()))
            await db.commit()
            return cur.rowcount > 0

    async def get_client_tags(self, client_id: int) -> List[str]:
        """Return list of tag strings for a client."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT tag FROM client_tags WHERE client_id=? ORDER BY created_at',
                (client_id,))
            rows = await cur.fetchall()
            return [r['tag'] for r in rows]

    async def get_all_tags_with_counts(self, team: Optional[str] = None) -> List[Dict]:
        """Return all tags with usage counts, optionally scoped to a team."""
        async with self.get_connection() as db:
            if team:
                cur = await db.execute(
                    """SELECT ct.tag, COUNT(*) as cnt
                       FROM client_tags ct
                       JOIN clients c ON ct.client_id = c.id
                       JOIN staff s ON c.frontdesk_id = s.id
                       WHERE s.team = ?
                       GROUP BY ct.tag ORDER BY cnt DESC""",
                    (team,))
            else:
                cur = await db.execute(
                    'SELECT tag, COUNT(*) as cnt FROM client_tags GROUP BY tag ORDER BY cnt DESC')
            rows = await cur.fetchall()
            return [{'tag': r['tag'], 'count': r['cnt']} for r in rows]

    async def filter_clients_by_criteria(self, frontdesk_id: Optional[int],
                                          team: Optional[str],
                                          criteria: Dict) -> List[Dict]:
        """Filter clients by tag, status, source, stale days, registered flag."""
        async with self.get_connection() as db:
            conditions = []
            params: list = []

            if frontdesk_id:
                conditions.append('c.frontdesk_id = ?')
                params.append(frontdesk_id)
            elif team:
                conditions.append('s.team = ?')
                params.append(team)

            tag = criteria.get('tag')
            status = criteria.get('status')
            source = criteria.get('source')
            stale_days = criteria.get('stale')
            registered = criteria.get('registered')

            if tag:
                conditions.append('EXISTS (SELECT 1 FROM client_tags ct WHERE ct.client_id=c.id AND ct.tag=?)')
                params.append(tag.lower())
            if status:
                conditions.append('c.status = ?')
                params.append(status)
            if source:
                conditions.append('c.source LIKE ?')
                params.append(f'%{source}%')
            if stale_days is not None:
                cutoff = datetime.now() - timedelta(days=int(stale_days))
                conditions.append('c.updated_at < ?')
                params.append(cutoff.strftime('%Y-%m-%d %H:%M:%S'))
            if registered == 'no':
                conditions.append("c.status NOT IN ('registered','training','withdrew','ordered')")
            elif registered == 'yes':
                conditions.append("c.status IN ('registered','training','withdrew','ordered')")

            where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
            sql = f"""SELECT c.id, c.phone, c.nickname, c.status, c.source,
                             c.updated_at, s.display_name as frontdesk_name
                      FROM clients c
                      JOIN staff s ON c.frontdesk_id = s.id
                      {where}
                      ORDER BY c.updated_at DESC LIMIT 50"""
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ─── Phase 9B: Client Events (Timeline) ──────────────────────────────────

    async def log_event(self, client_id: int, event_type: str,
                         event_data: Optional[str], staff_id: Optional[int]) -> int:
        """Insert a client timeline event. Returns inserted id."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO client_events (client_id, event_type, event_data, staff_id)
                   VALUES (?,?,?,?)""",
                (client_id, event_type, event_data, staff_id))
            await db.commit()
            return cur.lastrowid

    async def get_client_timeline(self, client_id: int,
                                   limit: int = 10,
                                   today_only: bool = False) -> List[Dict]:
        """Return timeline events for a client, newest first."""
        async with self.get_connection() as db:
            if today_only:
                cur = await db.execute(
                    """SELECT ce.*, s.display_name as staff_name
                       FROM client_events ce
                       LEFT JOIN staff s ON ce.staff_id = s.id
                       WHERE ce.client_id=? AND DATE(ce.created_at)=DATE('now')
                       ORDER BY ce.created_at DESC""",
                    (client_id,))
            else:
                cur = await db.execute(
                    """SELECT ce.*, s.display_name as staff_name
                       FROM client_events ce
                       LEFT JOIN staff s ON ce.staff_id = s.id
                       WHERE ce.client_id=?
                       ORDER BY ce.created_at DESC LIMIT ?""",
                    (client_id, limit))
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ─── Phase 9C: SLA ───────────────────────────────────────────────────────

    async def seed_sla_defaults(self):
        """Insert default SLA config rows if not present."""
        defaults = [
            ('first_response',    30,  20,  45),
            ('status_update',     120, 90,  180),
            ('follow_up_response', 60, 45,  90),
        ]
        async with self.get_connection() as db:
            for ev_type, target, warn, crit in defaults:
                try:
                    await db.execute(
                        """INSERT OR IGNORE INTO sla_config
                           (event_type, target_minutes, warning_minutes, critical_minutes)
                           VALUES (?,?,?,?)""",
                        (ev_type, target, warn, crit))
                except Exception:
                    pass
            await db.commit()

    async def get_sla_config(self, event_type: Optional[str] = None) -> List[Dict]:
        async with self.get_connection() as db:
            if event_type:
                cur = await db.execute(
                    'SELECT * FROM sla_config WHERE event_type=?', (event_type,))
            else:
                cur = await db.execute('SELECT * FROM sla_config ORDER BY event_type')
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def set_sla_config(self, event_type: str, target_minutes: int,
                              warning_minutes: int, critical_minutes: int):
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO sla_config (event_type, target_minutes, warning_minutes, critical_minutes)
                   VALUES (?,?,?,?)
                   ON CONFLICT(event_type) DO UPDATE SET
                   target_minutes=excluded.target_minutes,
                   warning_minutes=excluded.warning_minutes,
                   critical_minutes=excluded.critical_minutes""",
                (event_type, target_minutes, warning_minutes, critical_minutes))
            await db.commit()

    async def start_sla_event(self, client_id: int, staff_id: int,
                               event_type: str, target_minutes: int,
                               started_at: Optional[datetime] = None) -> int:
        """Open a new SLA event. Returns inserted id."""
        ts = started_at or datetime.utcnow()
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO sla_events
                   (client_id, staff_id, event_type, target_minutes, started_at)
                   VALUES (?,?,?,?,?)""",
                (client_id, staff_id, event_type, target_minutes,
                 ts.strftime('%Y-%m-%d %H:%M:%S')))
            await db.commit()
            return cur.lastrowid

    async def complete_sla_event(self, sla_id: int, completed_at: Optional[datetime] = None) -> bool:
        """Close an open SLA event, compute actual_minutes and met."""
        now = completed_at or datetime.utcnow()
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT started_at, target_minutes FROM sla_events WHERE id=? AND completed_at IS NULL',
                (sla_id,))
            row = await cur.fetchone()
            if not row:
                return False
            started = datetime.fromisoformat(row['started_at'])
            actual = int((now - started).total_seconds() / 60)
            met = actual <= row['target_minutes']
            await db.execute(
                """UPDATE sla_events SET actual_minutes=?, met=?, completed_at=?
                   WHERE id=?""",
                (actual, met, now.strftime('%Y-%m-%d %H:%M:%S'), sla_id))
            await db.commit()
            return True

    async def get_open_sla_events(self) -> List[Dict]:
        """Return all SLA events that are still open (completed_at IS NULL)."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT se.*, s.display_name as staff_name, s.tg_chat_id,
                          c.phone as client_phone
                   FROM sla_events se
                   JOIN staff s ON se.staff_id = s.id
                   JOIN clients c ON se.client_id = c.id
                   WHERE se.completed_at IS NULL
                   ORDER BY se.started_at""")
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_sla_stats(self, staff_id: Optional[int] = None,
                             team: Optional[str] = None,
                             days: int = 7) -> Dict:
        """Aggregate SLA compliance stats."""
        async with self.get_connection() as db:
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            if staff_id:
                cur = await db.execute(
                    """SELECT COUNT(*) as total,
                              SUM(CASE WHEN met=1 THEN 1 ELSE 0 END) as met_count,
                              AVG(actual_minutes) as avg_minutes,
                              event_type
                       FROM sla_events
                       WHERE staff_id=? AND completed_at IS NOT NULL AND created_at >= ?
                       GROUP BY event_type""",
                    (staff_id, cutoff))
            elif team:
                cur = await db.execute(
                    """SELECT COUNT(*) as total,
                              SUM(CASE WHEN se.met=1 THEN 1 ELSE 0 END) as met_count,
                              AVG(se.actual_minutes) as avg_minutes,
                              se.event_type
                       FROM sla_events se
                       JOIN staff s ON se.staff_id = s.id
                       WHERE s.team=? AND se.completed_at IS NOT NULL AND se.created_at >= ?
                       GROUP BY se.event_type""",
                    (team, cutoff))
            else:
                cur = await db.execute(
                    """SELECT COUNT(*) as total,
                              SUM(CASE WHEN met=1 THEN 1 ELSE 0 END) as met_count,
                              AVG(actual_minutes) as avg_minutes,
                              event_type
                       FROM sla_events
                       WHERE completed_at IS NOT NULL AND created_at >= ?
                       GROUP BY event_type""",
                    (cutoff,))
            rows = await cur.fetchall()
            result: Dict = {}
            for r in rows:
                total = r['total'] or 0
                met_count = r['met_count'] or 0
                result[r['event_type']] = {
                    'total': total,
                    'met': met_count,
                    'compliance_pct': round(met_count / total * 100, 1) if total > 0 else 0.0,
                    'avg_minutes': round(r['avg_minutes'] or 0, 1),
                }
            return result

    async def get_staff_sla_summary(self, days: int = 7) -> List[Dict]:
        """Per-staff SLA compliance summary for the dashboard."""
        async with self.get_connection() as db:
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            cur = await db.execute(
                """SELECT s.id as staff_id, s.display_name,
                          COUNT(*) as total,
                          SUM(CASE WHEN se.met=1 THEN 1 ELSE 0 END) as met_count,
                          AVG(se.actual_minutes) as avg_minutes
                   FROM sla_events se
                   JOIN staff s ON se.staff_id = s.id
                   WHERE se.completed_at IS NOT NULL AND se.created_at >= ?
                   GROUP BY se.staff_id
                   ORDER BY met_count DESC""",
                (cutoff,))
            rows = await cur.fetchall()
            out = []
            for r in rows:
                total = r['total'] or 0
                met = r['met_count'] or 0
                out.append({
                    'staff_id': r['staff_id'],
                    'display_name': r['display_name'],
                    'total': total,
                    'met': met,
                    'compliance_pct': round(met / total * 100, 1) if total > 0 else 0.0,
                    'avg_minutes': round(r['avg_minutes'] or 0, 1),
                })
            return out


# Global singleton
database_v2 = DatabaseV2()

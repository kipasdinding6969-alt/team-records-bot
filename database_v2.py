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
    Client, ClientNote, ClientStatus, Commission, CommissionRule, DailyStat,
    Deposit, NoteType, PeriodType, Reminder, ShiftHandoff, Staff, StaffRole,
    TeamTarget,
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

                -- Phase 10A: Commission Rules
                CREATE TABLE IF NOT EXISTS commission_rules (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    team            TEXT,
                    status_trigger  TEXT NOT NULL,
                    rate_type       TEXT NOT NULL,
                    rate_value      REAL NOT NULL,
                    min_amount      REAL DEFAULT 0,
                    max_commission  REAL,
                    is_active       INTEGER DEFAULT 1,
                    created_at      TIMESTAMP DEFAULT (datetime('now'))
                );

                -- Phase 10A: Commissions
                CREATE TABLE IF NOT EXISTS commissions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id        INTEGER NOT NULL REFERENCES staff(id),
                    client_id       INTEGER REFERENCES clients(id),
                    deposit_id      INTEGER REFERENCES deposits(id),
                    rule_id         INTEGER REFERENCES commission_rules(id),
                    trigger_type    TEXT NOT NULL,
                    amount          REAL NOT NULL,
                    status          TEXT DEFAULT 'pending',
                    approved_by     INTEGER REFERENCES staff(id),
                    period          TEXT,
                    created_at      TIMESTAMP DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_commissions_staff ON commissions(staff_id, period);
                CREATE INDEX IF NOT EXISTS idx_commissions_status ON commissions(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_commission_rules_active_trigger ON commission_rules(status_trigger, team, is_active);
                CREATE INDEX IF NOT EXISTS idx_commissions_staff_period ON commissions(staff_id, period, status);
                CREATE INDEX IF NOT EXISTS idx_clients_frontdesk_status ON clients(frontdesk_id, status);
                CREATE INDEX IF NOT EXISTS idx_deposits_client_id ON deposits(client_id);

                -- Phase 10C: Shift Handoffs
                CREATE TABLE IF NOT EXISTS shift_handoffs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_staff_id   INTEGER NOT NULL REFERENCES staff(id),
                    to_staff_id     INTEGER REFERENCES staff(id),
                    team            TEXT,
                    status          TEXT DEFAULT 'pending',
                    notes           TEXT,
                    client_ids      TEXT,
                    created_at      TIMESTAMP DEFAULT (datetime('now')),
                    accepted_at     TIMESTAMP,
                    completed_at    TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_handoffs_status_team ON shift_handoffs(status, team, to_staff_id);

                -- Phase 16A: Phone Registry (duplicate guard)
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
                CREATE INDEX IF NOT EXISTS idx_phone_registry_normalized ON phone_registry(phone_normalized);
                CREATE INDEX IF NOT EXISTS idx_phone_registry_submitter ON phone_registry(submitter_name);

                -- Phase 16A: Phone Registry Audit Log
                CREATE TABLE IF NOT EXISTS phone_registry_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_normalized TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_name TEXT NOT NULL,
                    actor_staff_id INTEGER REFERENCES staff(id),
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_phone_registry_log_phone ON phone_registry_log(phone_normalized);

                -- Phase 16B: Client Links (cross-linking)
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

                -- Phase 16C: Permission Overrides
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
            # Phase 16.5: client_notes enhancements
            ('client_notes', 'ALTER TABLE client_notes ADD COLUMN phone_normalized TEXT'),
            ('client_notes', 'ALTER TABLE client_notes ADD COLUMN author_name TEXT'),
            # Phase 16.5: phone_registry extra fields
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN category TEXT'),
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN recruiter TEXT'),
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN account_id TEXT'),
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN first_day_status TEXT'),
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN second_day_status TEXT'),
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN client_condition TEXT'),
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN team_name TEXT'),
            ('phone_registry', 'ALTER TABLE phone_registry ADD COLUMN leader_name TEXT'),
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


    # ─── Phase 10A: Commission Rules & Commissions ─────────────────────────

    async def seed_commission_rules(self):
        """Insert default commission rules if none exist."""
        async with self.get_connection() as db:
            cur = await db.execute('SELECT COUNT(*) FROM commission_rules')
            count = (await cur.fetchone())[0]
            if count > 0:
                return
            defaults = [
                (None, 'deposit', 'percentage', 0.05, 0, None),
                (None, 'first_deposit', 'fixed', 10.0, 0, None),
                (None, 'registration', 'fixed', 2.0, 0, None),
            ]
            for team, trigger, rtype, rval, min_amt, max_comm in defaults:
                await db.execute(
                    """INSERT INTO commission_rules
                       (team, status_trigger, rate_type, rate_value, min_amount, max_commission)
                       VALUES (?,?,?,?,?,?)""",
                    (team, trigger, rtype, rval, min_amt, max_comm))
            await db.commit()

    def _row_to_commission_rule(self, row) -> CommissionRule:
        return CommissionRule(
            id=row['id'],
            team=row['team'],
            status_trigger=row['status_trigger'],
            rate_type=row['rate_type'],
            rate_value=row['rate_value'],
            min_amount=row['min_amount'] or 0.0,
            max_commission=row['max_commission'],
            is_active=bool(row['is_active']),
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
        )

    def _row_to_commission(self, row) -> Commission:
        return Commission(
            id=row['id'],
            staff_id=row['staff_id'],
            client_id=row['client_id'],
            deposit_id=row['deposit_id'],
            rule_id=row['rule_id'],
            trigger_type=row['trigger_type'],
            amount=row['amount'],
            status=row['status'],
            approved_by=row['approved_by'],
            period=row['period'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
        )

    async def get_active_commission_rules(self, team: Optional[str] = None,
                                           trigger: Optional[str] = None) -> List[CommissionRule]:
        """Get active commission rules, optionally filtered by team/trigger."""
        async with self.get_connection() as db:
            sql = 'SELECT * FROM commission_rules WHERE is_active=1'
            params: list = []
            if trigger:
                sql += ' AND status_trigger=?'
                params.append(trigger)
            if team:
                sql += ' AND (team IS NULL OR team=?)'
                params.append(team)
            else:
                sql += ' AND team IS NULL'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [self._row_to_commission_rule(r) for r in rows]

    async def set_commission_rule(self, trigger: str, rate_type: str,
                                   rate_value: float, team: Optional[str] = None,
                                   min_amount: float = 0, max_commission: Optional[float] = None) -> int:
        """Create or update a commission rule for a trigger/team combo."""
        async with self.get_connection() as db:
            # Deactivate existing rules for same trigger/team
            if team:
                await db.execute(
                    'UPDATE commission_rules SET is_active=0 WHERE status_trigger=? AND team=?',
                    (trigger, team))
            else:
                await db.execute(
                    'UPDATE commission_rules SET is_active=0 WHERE status_trigger=? AND team IS NULL',
                    (trigger,))
            cur = await db.execute(
                """INSERT INTO commission_rules
                   (team, status_trigger, rate_type, rate_value, min_amount, max_commission)
                   VALUES (?,?,?,?,?,?)""",
                (team, trigger, rate_type, rate_value, min_amount, max_commission))
            await db.commit()
            return cur.lastrowid

    def _current_week_period(self) -> str:
        """Return ISO week period string like '2026-W13'."""
        now = datetime.utcnow()
        return f'{now.year}-W{now.isocalendar()[1]:02d}'

    def _current_month_period(self) -> str:
        """Return month period string like '2026-03'."""
        now = datetime.utcnow()
        return f'{now.year}-{now.month:02d}'

    async def calculate_commission(self, staff_id: int, client_id: Optional[int],
                                    deposit_id: Optional[int], trigger_type: str,
                                    amount: float = 0, team: Optional[str] = None) -> Optional[int]:
        """Calculate and create commission record based on active rules.

        Returns commission record ID, or None if no rule matched.
        """
        rules = await self.get_active_commission_rules(team=team, trigger=trigger_type)
        if not rules:
            # Fallback: try global rules (team=None)
            if team:
                rules = await self.get_active_commission_rules(team=None, trigger=trigger_type)
        if not rules:
            return None

        rule = rules[0]  # Use first matching rule

        if rule.min_amount and amount < rule.min_amount:
            return None

        if rule.rate_type == 'percentage':
            commission_amount = amount * rule.rate_value
        else:  # fixed
            commission_amount = rule.rate_value

        if rule.max_commission and commission_amount > rule.max_commission:
            commission_amount = rule.max_commission

        commission_amount = round(commission_amount, 2)
        period = self._current_week_period()

        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO commissions
                   (staff_id, client_id, deposit_id, rule_id, trigger_type, amount, status, period)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (staff_id, client_id, deposit_id, rule.id, trigger_type,
                 commission_amount, 'pending', period))
            await db.commit()
            return cur.lastrowid

    async def get_commissions(self, staff_id: Optional[int] = None,
                               period: Optional[str] = None,
                               status: Optional[str] = None,
                               team: Optional[str] = None) -> List[Commission]:
        """Get commission records with optional filters."""
        async with self.get_connection() as db:
            sql = 'SELECT c.* FROM commissions c'
            conditions: list = []
            params: list = []
            if team:
                sql += ' JOIN staff s ON c.staff_id = s.id'
                conditions.append('s.team=?')
                params.append(team)
            if staff_id:
                conditions.append('c.staff_id=?')
                params.append(staff_id)
            if period:
                conditions.append('c.period=?')
                params.append(period)
            if status:
                conditions.append('c.status=?')
                params.append(status)
            if conditions:
                sql += ' WHERE ' + ' AND '.join(conditions)
            sql += ' ORDER BY c.created_at DESC'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [self._row_to_commission(r) for r in rows]

    async def get_commission_summary(self, staff_id: Optional[int] = None,
                                      period: Optional[str] = None,
                                      team: Optional[str] = None) -> Dict:
        """Summarize commissions: total, pending, approved, by trigger type."""
        async with self.get_connection() as db:
            sql = """SELECT
                        COUNT(*) as total_count,
                        COALESCE(SUM(c.amount), 0) as total_amount,
                        COALESCE(SUM(CASE WHEN c.status='pending' THEN c.amount ELSE 0 END), 0) as pending_amount,
                        COALESCE(SUM(CASE WHEN c.status='approved' THEN c.amount ELSE 0 END), 0) as approved_amount,
                        COALESCE(SUM(CASE WHEN c.status='paid' THEN c.amount ELSE 0 END), 0) as paid_amount
                     FROM commissions c"""
            conditions: list = []
            params: list = []
            if team:
                sql += ' JOIN staff s ON c.staff_id = s.id'
                conditions.append('s.team=?')
                params.append(team)
            if staff_id:
                conditions.append('c.staff_id=?')
                params.append(staff_id)
            if period:
                conditions.append('c.period=?')
                params.append(period)
            if conditions:
                sql += ' WHERE ' + ' AND '.join(conditions)
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            return {
                'total_count': row['total_count'] or 0,
                'total_amount': round(row['total_amount'] or 0, 2),
                'pending_amount': round(row['pending_amount'] or 0, 2),
                'approved_amount': round(row['approved_amount'] or 0, 2),
                'paid_amount': round(row['paid_amount'] or 0, 2),
            }

    async def approve_commissions(self, approver_id: int,
                                    staff_id: Optional[int] = None,
                                    period: Optional[str] = None) -> int:
        """Approve all pending commissions. Returns count approved."""
        async with self.get_connection() as db:
            sql = "UPDATE commissions SET status='approved', approved_by=? WHERE status='pending'"
            params: list = [approver_id]
            if staff_id:
                sql += ' AND staff_id=?'
                params.append(staff_id)
            if period:
                sql += ' AND period=?'
                params.append(period)
            cur = await db.execute(sql, params)
            await db.commit()
            return cur.rowcount

    async def is_first_deposit(self, client_id: int) -> bool:
        """Check if client has no prior deposits."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'SELECT COUNT(*) FROM deposits WHERE client_id=?', (client_id,))
            count = (await cur.fetchone())[0]
            return count == 0

    async def is_first_registration(self, client_id: int) -> bool:
        """Check if this is the first time client reached 'registered' status."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT COUNT(*) FROM client_notes
                   WHERE client_id=? AND note_type='status_change' AND new_status='registered'""",
                (client_id,))
            count = (await cur.fetchone())[0]
            # 0 means this is the first (about to happen), 1 means it already happened once
            return count <= 1

    # ─── Phase 10B: Advanced Analytics ─────────────────────────────────────

    async def get_pipeline_stats(self, period_start: str, period_end: str,
                                  team: Optional[str] = None) -> Dict[str, int]:
        """Count clients per status created/changed within a date range."""
        async with self.get_connection() as db:
            sql = """SELECT c.status, COUNT(*) as cnt FROM clients c"""
            conditions = ['c.created_at >= ?', 'c.created_at <= ?']
            params: list = [period_start, period_end]
            if team:
                sql += ' JOIN staff s ON c.frontdesk_id = s.id'
                conditions.append('s.team=?')
                params.append(team)
            sql += ' WHERE ' + ' AND '.join(conditions) + ' GROUP BY c.status'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return {r['status']: r['cnt'] for r in rows}

    async def get_conversion_rates(self, period_start: str, period_end: str,
                                    team: Optional[str] = None) -> Dict:
        """Stage-to-stage conversion rates for a period (single query)."""
        async with self.get_connection() as db:
            join = ''
            team_cond = ''
            params: list = [period_start, period_end]
            if team:
                join = ' JOIN staff s ON c.frontdesk_id = s.id'
                team_cond = ' AND s.team=?'
                params.append(team)

            sql = f"""SELECT
                COUNT(*) as total,
                SUM(CASE WHEN c.contacted_at IS NOT NULL THEN 1 ELSE 0 END) as contacted,
                SUM(CASE WHEN c.replied_at IS NOT NULL THEN 1 ELSE 0 END) as replied,
                SUM(CASE WHEN c.registered_at IS NOT NULL THEN 1 ELSE 0 END) as registered,
                SUM(CASE WHEN c.total_deposited > 0 THEN 1 ELSE 0 END) as deposited
                FROM clients c{join}
                WHERE c.created_at >= ? AND c.created_at <= ?{team_cond}"""

            cur = await db.execute(sql, params)
            row = await cur.fetchone()

            result = {
                'total': row[0] or 0,
                'contacted': row[1] or 0,
                'replied': row[2] or 0,
                'registered': row[3] or 0,
                'deposited': row[4] or 0,
            }

            # Calculate rates
            total = result['total']
            result['contact_rate'] = round(result['contacted'] / total * 100, 1) if total > 0 else 0
            result['reply_rate'] = round(result['replied'] / result['contacted'] * 100, 1) if result['contacted'] > 0 else 0
            result['register_rate'] = round(result['registered'] / result['replied'] * 100, 1) if result['replied'] > 0 else 0
            result['deposit_rate'] = round(result['deposited'] / result['registered'] * 100, 1) if result['registered'] > 0 else 0
            return result

    async def get_staff_rankings(self, period_start: str, period_end: str,
                                  team: Optional[str] = None,
                                  metric: str = 'deposits') -> List[Dict]:
        """Ranked staff by metric (deposits, registrations, new_clients)."""
        async with self.get_connection() as db:
            if metric == 'deposits':
                sql = """SELECT s.id as staff_id, s.display_name,
                                COUNT(d.id) as count, COALESCE(SUM(d.amount), 0) as total_amount
                         FROM staff s
                         LEFT JOIN deposits d ON s.id = d.frontdesk_id
                              AND d.deposit_date >= ? AND d.deposit_date <= ?
                         WHERE s.is_active=1"""
                params: list = [period_start, period_end]
                if team:
                    sql += ' AND s.team=?'
                    params.append(team)
                sql += ' GROUP BY s.id ORDER BY total_amount DESC'
            elif metric == 'registrations':
                sql = """SELECT s.id as staff_id, s.display_name,
                                COUNT(cn.id) as count, 0 as total_amount
                         FROM staff s
                         LEFT JOIN client_notes cn ON s.id = cn.staff_id
                              AND cn.note_type='status_change' AND cn.new_status='registered'
                              AND cn.created_at >= ? AND cn.created_at <= ?
                         WHERE s.is_active=1"""
                params = [period_start, period_end]
                if team:
                    sql += ' AND s.team=?'
                    params.append(team)
                sql += ' GROUP BY s.id ORDER BY count DESC'
            else:  # new_clients
                sql = """SELECT s.id as staff_id, s.display_name,
                                COUNT(c.id) as count, 0 as total_amount
                         FROM staff s
                         LEFT JOIN clients c ON s.id = c.frontdesk_id
                              AND c.created_at >= ? AND c.created_at <= ?
                         WHERE s.is_active=1"""
                params = [period_start, period_end]
                if team:
                    sql += ' AND s.team=?'
                    params.append(team)
                sql += ' GROUP BY s.id ORDER BY count DESC'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [{'staff_id': r['staff_id'], 'display_name': r['display_name'],
                     'count': r['count'], 'total_amount': round(r['total_amount'], 2)} for r in rows]

    async def get_source_analysis(self, period_start: str, period_end: str,
                                   team: Optional[str] = None) -> List[Dict]:
        """Breakdown of clients by lead source with conversion info."""
        async with self.get_connection() as db:
            sql = """SELECT c.source,
                            COUNT(*) as total,
                            SUM(CASE WHEN c.status IN ('registered','training','withdrew','ordered') THEN 1 ELSE 0 END) as converted,
                            COALESCE(SUM(c.total_deposited), 0) as deposit_total
                     FROM clients c"""
            conditions = ['c.created_at >= ?', 'c.created_at <= ?']
            params: list = [period_start, period_end]
            if team:
                sql += ' JOIN staff s ON c.frontdesk_id = s.id'
                conditions.append('s.team=?')
                params.append(team)
            sql += ' WHERE ' + ' AND '.join(conditions) + ' GROUP BY c.source ORDER BY total DESC'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [{'source': r['source'], 'total': r['total'],
                     'converted': r['converted'],
                     'conversion_rate': round(r['converted'] / r['total'] * 100, 1) if r['total'] > 0 else 0,
                     'deposit_total': round(r['deposit_total'], 2)} for r in rows]

    async def get_period_comparison(self, period1_start: str, period1_end: str,
                                     period2_start: str, period2_end: str,
                                     team: Optional[str] = None) -> Dict:
        """Compare two periods — returns counts and deltas."""
        p1 = await self.get_conversion_rates(period1_start, period1_end, team)
        p2 = await self.get_conversion_rates(period2_start, period2_end, team)
        comparison = {}
        for key in ['total', 'contacted', 'replied', 'registered', 'deposited']:
            v1 = p1.get(key, 0)
            v2 = p2.get(key, 0)
            delta = v1 - v2
            pct_change = round((delta / v2) * 100, 1) if v2 > 0 else 0
            comparison[key] = {'current': v1, 'previous': v2, 'delta': delta, 'pct_change': pct_change}
        return comparison

    async def get_stale_clients_analytics(self, days: int = 7,
                                           team: Optional[str] = None) -> List[Dict]:
        """Clients with no activity in N days — for analytics reports."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        active = [s.value for s in ClientStatus.active_statuses()]
        placeholders = ','.join('?' * len(active))
        async with self.get_connection() as db:
            sql = f"""SELECT c.id, c.phone, c.nickname, c.status, c.updated_at,
                             s.display_name as staff_name
                      FROM clients c
                      JOIN staff s ON c.frontdesk_id = s.id
                      WHERE c.status IN ({placeholders}) AND c.updated_at < ?"""
            params: list = list(active) + [cutoff]
            if team:
                sql += ' AND s.team=?'
                params.append(team)
            sql += ' ORDER BY c.updated_at ASC'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_deposit_total(self, period_start: str, period_end: str,
                                 team: Optional[str] = None) -> float:
        """Total deposit amount for a period."""
        async with self.get_connection() as db:
            sql = 'SELECT COALESCE(SUM(d.amount), 0) FROM deposits d'
            conditions = ['d.deposit_date >= ?', 'd.deposit_date <= ?']
            params: list = [period_start, period_end]
            if team:
                sql += ' JOIN staff s ON d.frontdesk_id = s.id'
                conditions.append('s.team=?')
                params.append(team)
            sql += ' WHERE ' + ' AND '.join(conditions)
            cur = await db.execute(sql, params)
            return round((await cur.fetchone())[0], 2)

    # ─── Phase 10C: Shift Handoffs ────────────────────────────────────────

    def _row_to_handoff(self, row) -> ShiftHandoff:
        def _dt(v): return datetime.fromisoformat(v) if v else None
        return ShiftHandoff(
            id=row['id'],
            from_staff_id=row['from_staff_id'],
            to_staff_id=row['to_staff_id'],
            team=row['team'],
            status=row['status'],
            notes=row['notes'],
            client_ids=row['client_ids'],
            created_at=_dt(row['created_at']),
            accepted_at=_dt(row['accepted_at']),
            completed_at=_dt(row['completed_at']),
        )

    async def create_handoff(self, handoff: ShiftHandoff) -> int:
        """Create a shift handoff record."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO shift_handoffs
                   (from_staff_id, to_staff_id, team, status, notes, client_ids)
                   VALUES (?,?,?,?,?,?)""",
                (handoff.from_staff_id, handoff.to_staff_id, handoff.team,
                 handoff.status, handoff.notes, handoff.client_ids))
            await db.commit()
            return cur.lastrowid

    async def get_handoff_by_id(self, handoff_id: int) -> Optional[ShiftHandoff]:
        async with self.get_connection() as db:
            cur = await db.execute('SELECT * FROM shift_handoffs WHERE id=?', (handoff_id,))
            row = await cur.fetchone()
            return self._row_to_handoff(row) if row else None

    async def get_pending_handoffs(self, team: Optional[str] = None,
                                    to_staff_id: Optional[int] = None) -> List[ShiftHandoff]:
        """Get pending handoffs for a team or specific staff."""
        async with self.get_connection() as db:
            sql = "SELECT * FROM shift_handoffs WHERE status='pending'"
            params: list = []
            if team:
                sql += ' AND team=?'
                params.append(team)
            if to_staff_id:
                sql += ' AND (to_staff_id=? OR to_staff_id IS NULL)'
                params.append(to_staff_id)
            sql += ' ORDER BY created_at DESC'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [self._row_to_handoff(r) for r in rows]

    async def accept_handoff(self, handoff_id: int, accepting_staff_id: int) -> bool:
        """Accept a handoff — update status and reassign clients."""
        async with self.get_connection() as db:
            try:
                cur = await db.execute(
                    'SELECT * FROM shift_handoffs WHERE id=? AND status=?',
                    (handoff_id, 'pending'))
                row = await cur.fetchone()
                if not row:
                    return False

                handoff = self._row_to_handoff(row)

                # Update handoff status
                await db.execute(
                    """UPDATE shift_handoffs
                       SET status='accepted', to_staff_id=?,
                           accepted_at=datetime('now'), completed_at=datetime('now')
                       WHERE id=?""",
                    (accepting_staff_id, handoff_id))

                # Reassign clients
                import json
                if handoff.client_ids:
                    client_ids = json.loads(handoff.client_ids)
                    for cid in client_ids:
                        await db.execute(
                            'UPDATE clients SET frontdesk_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                            (accepting_staff_id, cid))

                await db.commit()
                return True
            except Exception:
                await db.rollback()
                raise

    async def decline_handoff(self, handoff_id: int) -> bool:
        """Decline/cancel a handoff."""
        async with self.get_connection() as db:
            cur = await db.execute(
                "UPDATE shift_handoffs SET status='completed', completed_at=datetime('now') WHERE id=? AND status='pending'",
                (handoff_id,))
            await db.commit()
            return cur.rowcount > 0

    async def get_active_clients_for_staff(self, staff_id: int) -> List[Client]:
        """Get all clients in active statuses for a staff member."""
        active = [s.value for s in ClientStatus.active_statuses()]
        placeholders = ','.join('?' * len(active))
        async with self.get_connection() as db:
            cur = await db.execute(
                f"""SELECT * FROM clients
                    WHERE frontdesk_id=? AND status IN ({placeholders})
                    ORDER BY updated_at DESC""",
                (staff_id, *active))
            rows = await cur.fetchall()
            return [self._row_to_client(r) for r in rows]

    # ─── Phase 16: Phone Registry ────────────────────────────────────────────

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Strip non-digit characters for consistent lookup."""
        import re
        return re.sub(r'[^\d]', '', phone)

    async def phone_registry_lookup(self, phone: str) -> Optional[Dict]:
        """Look up a phone number in the registry. Returns dict or None."""
        normalized = self.normalize_phone(phone)
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT id, phone, phone_normalized, submitter_name,
                          submitter_staff_id, source, submitted_at, created_at
                   FROM phone_registry WHERE phone_normalized = ?""",
                (normalized,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def phone_registry_insert(self, phone: str, submitter_name: str,
                                     submitted_at: str, source: str = 'telegram',
                                     submitter_staff_id: Optional[int] = None) -> int:
        """Insert a phone into the registry. Returns row id."""
        normalized = self.normalize_phone(phone)
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO phone_registry
                   (phone, phone_normalized, submitter_name, submitter_staff_id, source, submitted_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (phone, normalized, submitter_name, submitter_staff_id, source, submitted_at))
            await db.commit()
            return cur.lastrowid

    async def phone_registry_log_action(self, phone: str, action: str,
                                         actor_name: str, actor_staff_id: Optional[int] = None,
                                         details: Optional[str] = None):
        """Log an action in the phone registry audit trail."""
        normalized = self.normalize_phone(phone)
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO phone_registry_log
                   (phone_normalized, action, actor_name, actor_staff_id, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (normalized, action, actor_name, actor_staff_id, details))
            await db.commit()

    async def phone_registry_get_log(self, phone: str, limit: int = 50) -> List[Dict]:
        """Get audit log entries for a phone number."""
        normalized = self.normalize_phone(phone)
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT id, phone_normalized, action, actor_name,
                          actor_staff_id, details, created_at
                   FROM phone_registry_log
                   WHERE phone_normalized = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (normalized, limit))
            return [dict(r) for r in await cur.fetchall()]

    async def phone_registry_override(self, phone: str, new_submitter: str,
                                       new_staff_id: Optional[int] = None):
        """Override ownership of a phone number in the registry."""
        normalized = self.normalize_phone(phone)
        async with self.get_connection() as db:
            await db.execute(
                """UPDATE phone_registry
                   SET submitter_name = ?, submitter_staff_id = ?
                   WHERE phone_normalized = ?""",
                (new_submitter, new_staff_id, normalized))
            await db.commit()

    async def phone_registry_search(self, query: str, limit: int = 50) -> List[Dict]:
        """Search phone registry by number or submitter name."""
        normalized = self.normalize_phone(query)
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT id, phone, phone_normalized, submitter_name,
                          submitter_staff_id, source, submitted_at, created_at
                   FROM phone_registry
                   WHERE phone_normalized LIKE ? OR submitter_name LIKE ?
                   ORDER BY submitted_at DESC LIMIT ?""",
                (f'%{normalized}%', f'%{query}%', limit))
            return [dict(r) for r in await cur.fetchall()]

    async def phone_registry_count(self) -> int:
        """Get total count of phone registry entries."""
        async with self.get_connection() as db:
            cur = await db.execute('SELECT COUNT(*) AS cnt FROM phone_registry')
            return (await cur.fetchone())['cnt']

    # ─── Phase 16: Client Links ──────────────────────────────────────────────

    async def create_client_link(self, client_id_a: int, client_id_b: int,
                                  link_type: str = 'related', note: Optional[str] = None,
                                  created_by: Optional[int] = None) -> int:
        """Link two clients. Always stores smaller id as client_id_a."""
        a, b = min(client_id_a, client_id_b), max(client_id_a, client_id_b)
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO client_links (client_id_a, client_id_b, link_type, note, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (a, b, link_type, note, created_by))
            await db.commit()
            return cur.lastrowid

    async def remove_client_link(self, client_id_a: int, client_id_b: int) -> bool:
        """Remove a link between two clients."""
        a, b = min(client_id_a, client_id_b), max(client_id_a, client_id_b)
        async with self.get_connection() as db:
            cur = await db.execute(
                'DELETE FROM client_links WHERE client_id_a = ? AND client_id_b = ?',
                (a, b))
            await db.commit()
            return cur.rowcount > 0

    async def get_client_links(self, client_id: int) -> List[Dict]:
        """Get all links for a client."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT cl.id, cl.client_id_a, cl.client_id_b, cl.link_type,
                          cl.note, cl.created_by, cl.created_at,
                          ca.phone AS phone_a, cb.phone AS phone_b,
                          sa.display_name AS name_a, sb.display_name AS name_b
                   FROM client_links cl
                   JOIN clients ca ON cl.client_id_a = ca.id
                   JOIN clients cb ON cl.client_id_b = cb.id
                   LEFT JOIN staff sa ON ca.frontdesk_id = sa.id
                   LEFT JOIN staff sb ON cb.frontdesk_id = sb.id
                   WHERE cl.client_id_a = ? OR cl.client_id_b = ?
                   ORDER BY cl.created_at DESC""",
                (client_id, client_id))
            return [dict(r) for r in await cur.fetchall()]

    # ─── Phase 16: Permission Overrides ──────────────────────────────────────

    async def get_permission_override(self, staff_id: int, command: str) -> Optional[Dict]:
        """Check if there's an explicit permission override for staff+command."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT id, staff_id, command, allowed, granted_by, reason,
                          created_at, updated_at
                   FROM permission_overrides
                   WHERE staff_id = ? AND command = ?""",
                (staff_id, command))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_all_permission_overrides(self, staff_id: int) -> List[Dict]:
        """Get all permission overrides for a staff member."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT id, staff_id, command, allowed, granted_by, reason,
                          created_at, updated_at
                   FROM permission_overrides
                   WHERE staff_id = ?
                   ORDER BY command""",
                (staff_id,))
            return [dict(r) for r in await cur.fetchall()]

    async def set_permission_override(self, staff_id: int, command: str,
                                       allowed: bool, granted_by: Optional[int] = None,
                                       reason: Optional[str] = None):
        """Set or update a permission override."""
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO permission_overrides
                   (staff_id, command, allowed, granted_by, reason)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(staff_id, command)
                   DO UPDATE SET allowed = excluded.allowed,
                                 granted_by = excluded.granted_by,
                                 reason = excluded.reason,
                                 updated_at = CURRENT_TIMESTAMP""",
                (staff_id, command, allowed, granted_by, reason))
            await db.commit()

    async def remove_permission_override(self, staff_id: int, command: str) -> bool:
        """Remove a permission override."""
        async with self.get_connection() as db:
            cur = await db.execute(
                'DELETE FROM permission_overrides WHERE staff_id = ? AND command = ?',
                (staff_id, command))
            await db.commit()
            return cur.rowcount > 0

    async def get_staff_permissions_summary(self, staff_id: int) -> List[Dict]:
        """Get all permission overrides for a staff member with staff info."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT po.id, po.command, po.allowed, po.reason,
                          po.created_at, po.updated_at,
                          s.display_name AS granted_by_name
                   FROM permission_overrides po
                   LEFT JOIN staff s ON po.granted_by = s.id
                   WHERE po.staff_id = ?
                   ORDER BY po.command""",
                (staff_id,))
            return [dict(r) for r in await cur.fetchall()]

    # ─── Phase 16.5: Enhanced Client Notes ────────────────────────────────────

    async def add_client_comment(self, client_id: int, staff_id: int,
                                  author_name: str, content: str,
                                  note_type: str = 'comment',
                                  phone_normalized: Optional[str] = None) -> int:
        """Add a comment/note to a client record."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """INSERT INTO client_notes
                   (client_id, staff_id, note_type, content, author_name, phone_normalized)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (client_id, staff_id, note_type, content, author_name, phone_normalized))
            await db.commit()
            return cur.lastrowid

    async def get_client_comments(self, client_id: int, limit: int = 50) -> List[Dict]:
        """Get all notes/comments for a client."""
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT cn.id, cn.client_id, cn.staff_id, cn.note_type,
                          cn.old_status, cn.new_status, cn.content,
                          cn.author_name, cn.phone_normalized, cn.created_at,
                          s.display_name AS staff_name
                   FROM client_notes cn
                   LEFT JOIN staff s ON cn.staff_id = s.id
                   WHERE cn.client_id = ?
                   ORDER BY cn.created_at DESC LIMIT ?""",
                (client_id, limit))
            return [dict(r) for r in await cur.fetchall()]

    async def get_client_unified_timeline(self, client_id: int, limit: int = 100) -> List[Dict]:
        """Unified timeline: notes + status changes + links + events."""
        items: List[Dict] = []
        async with self.get_connection() as db:
            # Notes and status changes
            cur = await db.execute(
                """SELECT cn.id, 'note' AS timeline_type, cn.note_type,
                          cn.old_status, cn.new_status, cn.content,
                          cn.created_at, cn.author_name,
                          s.display_name AS staff_name
                   FROM client_notes cn
                   LEFT JOIN staff s ON cn.staff_id = s.id
                   WHERE cn.client_id = ?
                   ORDER BY cn.created_at DESC LIMIT ?""",
                (client_id, limit))
            items.extend([dict(r) for r in await cur.fetchall()])

            # Client links
            cur = await db.execute(
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
                (client_id, client_id))
            items.extend([dict(r) for r in await cur.fetchall()])

            # Client events
            cur = await db.execute(
                """SELECT ce.id, 'event' AS timeline_type,
                          ce.event_type AS note_type, ce.event_data AS content,
                          ce.created_at,
                          s.display_name AS staff_name
                   FROM client_events ce
                   LEFT JOIN staff s ON ce.staff_id = s.id
                   WHERE ce.client_id = ?
                   ORDER BY ce.created_at DESC LIMIT ?""",
                (client_id, limit))
            items.extend([dict(r) for r in await cur.fetchall()])

        # Sort by created_at descending
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return items[:limit]

    # ─── Phase 16.5: Performance Dashboard ────────────────────────────────────

    async def get_performance_daily(self, stat_date: str,
                                     team: Optional[str] = None) -> List[Dict]:
        """Daily performance stats per frontdesk."""
        async with self.get_connection() as db:
            sql = """SELECT s.id AS staff_id, s.display_name, s.team,
                            ds.new_leads, ds.contacted, ds.replied, ds.registered,
                            ds.training, ds.withdrew, ds.new_orders,
                            ds.ghosted, ds.dead,
                            ds.reply_rate, ds.conversion_rate, ds.total_deposit
                     FROM daily_stats ds
                     JOIN staff s ON ds.staff_id = s.id
                     WHERE ds.stat_date = ? AND s.is_active = 1"""
            params: list = [stat_date]
            if team and team != 'all':
                sql += ' AND s.team = ?'
                params.append(team)
            sql += ' ORDER BY ds.new_orders DESC, ds.new_leads DESC'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()

        result = []
        for r in rows:
            d = dict(r)
            new_leads = d.get('new_leads', 0) or 0
            replied = d.get('replied', 0) or 0
            registered = d.get('registered', 0) or 0
            new_orders = d.get('new_orders', 0) or 0
            d['reply_rate'] = round(replied / max(new_leads, 1) * 100, 1)
            d['registration_rate'] = round(registered / max(replied, 1) * 100, 1)
            d['training_rate'] = round((d.get('training', 0) or 0) / max(registered, 1) * 100, 1)
            d['conversion_rate'] = round(new_orders / max(new_leads, 1) * 100, 1)
            result.append(d)
        return result

    async def get_performance_summary(self, date_from: str, date_to: str,
                                       team: Optional[str] = None) -> List[Dict]:
        """Performance summary over a date range, grouped by staff."""
        async with self.get_connection() as db:
            sql = """SELECT s.id AS staff_id, s.display_name, s.team,
                            SUM(ds.new_leads) AS new_leads,
                            SUM(ds.contacted) AS contacted,
                            SUM(ds.replied) AS replied,
                            SUM(ds.registered) AS registered,
                            SUM(ds.training) AS training,
                            SUM(ds.withdrew) AS withdrew,
                            SUM(ds.new_orders) AS new_orders,
                            SUM(ds.ghosted) AS ghosted,
                            SUM(ds.dead) AS dead,
                            SUM(ds.total_deposit) AS total_deposit
                     FROM daily_stats ds
                     JOIN staff s ON ds.staff_id = s.id
                     WHERE ds.stat_date >= ? AND ds.stat_date <= ? AND s.is_active = 1"""
            params: list = [date_from, date_to]
            if team and team != 'all':
                sql += ' AND s.team = ?'
                params.append(team)
            sql += ' GROUP BY s.id ORDER BY new_orders DESC, new_leads DESC'
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()

        result = []
        for r in rows:
            d = dict(r)
            new_leads = d.get('new_leads', 0) or 0
            replied = d.get('replied', 0) or 0
            registered = d.get('registered', 0) or 0
            new_orders = d.get('new_orders', 0) or 0
            d['reply_rate'] = round(replied / max(new_leads, 1) * 100, 1)
            d['registration_rate'] = round(registered / max(replied, 1) * 100, 1)
            d['training_rate'] = round((d.get('training', 0) or 0) / max(registered, 1) * 100, 1)
            d['conversion_rate'] = round(new_orders / max(new_leads, 1) * 100, 1)
            d['total_deposit'] = round(d.get('total_deposit', 0) or 0, 2)
            result.append(d)
        return result

    # ─── Phase 16.5: Enhanced Phone Registry ─────────────────────────────────

    async def phone_registry_update_fields(self, phone: str, **kwargs) -> bool:
        """Update extra fields on a phone registry entry."""
        normalized = self.normalize_phone(phone)
        allowed = {'category', 'recruiter', 'account_id', 'first_day_status',
                    'second_day_status', 'client_condition', 'team_name', 'leader_name'}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return False
        set_clause = ', '.join(f'{k} = ?' for k in updates)
        params = list(updates.values()) + [normalized]
        async with self.get_connection() as db:
            cur = await db.execute(
                f'UPDATE phone_registry SET {set_clause} WHERE phone_normalized = ?',
                params)
            await db.commit()
            return cur.rowcount > 0

    async def phone_registry_get_detail(self, phone: str) -> Optional[Dict]:
        """Get full phone registry entry with all Phase 16.5 fields."""
        normalized = self.normalize_phone(phone)
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT id, phone, phone_normalized, submitter_name,
                          submitter_staff_id, source, submitted_at, created_at,
                          category, recruiter, account_id, first_day_status,
                          second_day_status, client_condition, team_name, leader_name
                   FROM phone_registry WHERE phone_normalized = ?""",
                (normalized,))
            row = await cur.fetchone()
            return dict(row) if row else None

    # ─── Phase 16.5: Link by Phone ───────────────────────────────────────────

    async def find_client_by_phone_fuzzy(self, phone: str) -> List[Dict]:
        """Find clients by phone number (fuzzy last 8 digits)."""
        normalized = self.normalize_phone(phone)
        suffix = normalized[-8:] if len(normalized) >= 8 else normalized
        async with self.get_connection() as db:
            cur = await db.execute(
                """SELECT c.id, c.phone, c.status, c.frontdesk_id,
                          s.display_name AS frontdesk_name, s.team
                   FROM clients c
                   LEFT JOIN staff s ON c.frontdesk_id = s.id
                   WHERE c.phone LIKE ?
                   ORDER BY c.created_at DESC LIMIT 20""",
                (f'%{suffix}%',))
            return [dict(r) for r in await cur.fetchall()]


# Global singleton
database_v2 = DatabaseV2()

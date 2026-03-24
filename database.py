"""Database operations using SQLite with aiosqlite."""
import asyncio
import aiosqlite
import sqlite3
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
import json
import logging

from models import (
    ClientRecord, PerformanceRecord, FinancialRecord,
    DailySummaryRecord, TeamWeeklyRecord, TeamMember,
    Reminder, BotTask, ReportTemplate
)
from config import config

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager with async operations."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.database.db_path
        self._connection_pool = {}
        self._pool_size = 10
        self._current_connections = 0
        self._max_connections = 20

    def get_connection(self):
        """Get database connection context manager."""
        return aiosqlite.connect(self.db_path)

    async def initialize(self):
        """Initialize database with all tables."""
        async with self.get_connection() as db:
            await self._create_tables(db)
            await db.commit()

    async def _create_tables(self, db: aiosqlite.Connection):
        """Create all database tables."""

        # Client Records (Type 1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS client_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                row_num INTEGER NOT NULL,
                date TEXT NOT NULL,
                phone_remark TEXT NOT NULL,
                frontdesk TEXT NOT NULL,
                category TEXT NOT NULL,
                recruiter TEXT NOT NULL,
                frontdesk_number TEXT NOT NULL,
                frontdesk_username TEXT NOT NULL,
                client_number TEXT NOT NULL,
                account_id TEXT NOT NULL,
                first_day TEXT NOT NULL,
                second_day TEXT NOT NULL,
                client_condition TEXT,
                sheet_gid INTEGER,
                block_number INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Performance Records (Type 2)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS performance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                powder_count INTEGER NOT NULL,
                no_initial_reply INTEGER NOT NULL,
                reply_rate REAL NOT NULL,
                stuck_explanation INTEGER NOT NULL,
                blocked_or_play INTEGER NOT NULL,
                been_scammed INTEGER NOT NULL,
                sent_link_no_reply INTEGER NOT NULL,
                completed_register INTEGER NOT NULL,
                review_rate REAL NOT NULL,
                completed_training INTEGER NOT NULL,
                scheduled_time INTEGER NOT NULL,
                withdrawal INTEGER NOT NULL,
                new_order INTEGER NOT NULL,
                conversion_rate REAL NOT NULL,
                new_kill INTEGER NOT NULL,
                dead_client INTEGER NOT NULL,
                is_sum_row BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Financial Records (Type 3)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS financial_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                account_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                frontdesk TEXT NOT NULL,
                maintenance TEXT NOT NULL,
                frontdesk_number TEXT NOT NULL,
                platform TEXT NOT NULL,
                new_order_amount REAL,
                pressure_amount REAL,
                note TEXT,
                knife_1 REAL,
                knife_2 REAL,
                knife_3 REAL,
                knife_4 REAL,
                knife_5 REAL,
                knife_6 REAL,
                knife_7 REAL,
                knife_8 REAL,
                total_in REAL,
                role_frontdesk TEXT,
                role_order_opener TEXT,
                role_newbie TEXT,
                role_group_chat TEXT,
                role_customer_service TEXT,
                role_maintenance TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily Summary Records (Type 4)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frontdesk TEXT NOT NULL,
                section TEXT NOT NULL,
                new_powder INTEGER,
                today_reply INTEGER,
                today_register INTEGER,
                today_completed_training INTEGER,
                today_withdraw INTEGER,
                today_new_order INTEGER,
                total_powder INTEGER,
                total_reply INTEGER,
                total_register INTEGER,
                total_completed_training INTEGER,
                total_withdraw INTEGER,
                total_new_order INTEGER,
                today_training INTEGER,
                today_not_withdraw INTEGER,
                today_training_and_withdraw INTEGER,
                today_conversion INTEGER,
                report_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Team Weekly Records (Type 5)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS team_weekly_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL,
                date_range TEXT NOT NULL,
                frontdesk TEXT NOT NULL,
                section TEXT NOT NULL,
                day_number INTEGER NOT NULL,
                new_powder INTEGER,
                today_reply INTEGER,
                today_register INTEGER,
                today_completed_training INTEGER,
                today_withdraw INTEGER,
                today_new_order INTEGER,
                today_training INTEGER,
                today_not_withdraw INTEGER,
                today_training_and_withdraw INTEGER,
                is_sum_row BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Team Members
        await db.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone_number TEXT,
                frontdesk_name TEXT,
                role TEXT DEFAULT 'frontdesk',
                is_active BOOLEAN DEFAULT TRUE,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Reminders
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_record_id INTEGER,
                frontdesk_user_id INTEGER,
                reminder_type TEXT NOT NULL,
                scheduled_time TIMESTAMP NOT NULL,
                message TEXT,
                is_sent BOOLEAN DEFAULT FALSE,
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_record_id) REFERENCES client_records (id),
                FOREIGN KEY (frontdesk_user_id) REFERENCES team_members (id)
            )
        """)

        # Bot Tasks (for Ralph Loop)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                priority INTEGER DEFAULT 1,
                data TEXT,  -- JSON data
                status TEXT DEFAULT 'pending',
                scheduled_time TIMESTAMP,
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Conversation states table (for persistent conversation management)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_states (
                user_id INTEGER PRIMARY KEY,
                state_data TEXT,  -- JSON data
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for better performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_client_records_frontdesk ON client_records(frontdesk)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_client_records_date ON client_records(date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_performance_records_name ON performance_records(name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_financial_records_date ON financial_records(date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_team_members_user_id ON team_members(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_scheduled ON reminders(scheduled_time, is_sent)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bot_tasks_status ON bot_tasks(status, priority)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_conversation_states_user_id ON conversation_states(user_id)")

    # Client Records CRUD
    async def create_client_record(self, record: ClientRecord) -> int:
        """Create a new client record."""
        # Basic validation without importing validators to avoid circular dependency
        if not record.date or not record.frontdesk or not record.client_number or not record.account_id:
            raise ValueError("Required fields missing: date, frontdesk, client_number, account_id are required")

        async with self.get_connection() as db:
            # SQLite with aiosqlite handles transactions automatically in context manager
            cursor = await db.execute("""
                INSERT INTO client_records (
                    row_num, date, phone_remark, frontdesk, category, recruiter,
                    frontdesk_number, frontdesk_username, client_number, account_id,
                    first_day, second_day, client_condition, sheet_gid, block_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.row_num, record.date, record.phone_remark, record.frontdesk,
                record.category, record.recruiter, record.frontdesk_number,
                record.frontdesk_username, record.client_number, record.account_id,
                record.first_day, record.second_day, record.client_condition,
                record.sheet_gid, record.block_number
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_client_records_by_frontdesk(self, frontdesk: str) -> List[ClientRecord]:
        """Get all client records for a frontdesk staff."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                SELECT * FROM client_records WHERE frontdesk = ? ORDER BY created_at DESC
            """, (frontdesk,))
            rows = await cursor.fetchall()
            return [self._row_to_client_record(row) for row in rows]

    async def update_client_record_status(self, record_id: int, first_day: str = None, second_day: str = None):
        """Update client record status."""
        if first_day is None and second_day is None:
            return

        # Build safe, parameterized query
        set_clauses = []
        params = []

        if first_day is not None:
            set_clauses.append("first_day = ?")
            params.append(first_day)
        if second_day is not None:
            set_clauses.append("second_day = ?")
            params.append(second_day)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(record_id)

        # Use parameterized query - no f-strings
        query = "UPDATE client_records SET " + ", ".join(set_clauses) + " WHERE id = ?"

        async with self.get_connection() as db:
            await db.execute(query, params)
            await db.commit()

    # Performance Records CRUD
    async def create_performance_record(self, record: PerformanceRecord) -> int:
        """Create a new performance record."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO performance_records (
                    name, category, powder_count, no_initial_reply, reply_rate,
                    stuck_explanation, blocked_or_play, been_scammed, sent_link_no_reply,
                    completed_register, review_rate, completed_training, scheduled_time,
                    withdrawal, new_order, conversion_rate, new_kill, dead_client, is_sum_row
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.name, record.category, record.powder_count, record.no_initial_reply,
                record.reply_rate, record.stuck_explanation, record.blocked_or_play,
                record.been_scammed, record.sent_link_no_reply, record.completed_register,
                record.review_rate, record.completed_training, record.scheduled_time,
                record.withdrawal, record.new_order, record.conversion_rate,
                record.new_kill, record.dead_client, record.is_sum_row
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_performance_records_by_name(self, name: str) -> List[PerformanceRecord]:
        """Get performance records for a specific person."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                SELECT * FROM performance_records WHERE name = ? ORDER BY created_at DESC
            """, (name,))
            rows = await cursor.fetchall()
            return [self._row_to_performance_record(row) for row in rows]

    # Financial Records CRUD
    async def create_financial_record(self, record: FinancialRecord) -> int:
        """Create a new financial record."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO financial_records (
                    date, account_id, group_id, frontdesk, maintenance, frontdesk_number,
                    platform, new_order_amount, pressure_amount, note, knife_1, knife_2,
                    knife_3, knife_4, knife_5, knife_6, knife_7, knife_8, total_in,
                    role_frontdesk, role_order_opener, role_newbie, role_group_chat,
                    role_customer_service, role_maintenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.date, record.account_id, record.group_id, record.frontdesk,
                record.maintenance, record.frontdesk_number, record.platform,
                record.new_order_amount, record.pressure_amount, record.note,
                record.knife_1, record.knife_2, record.knife_3, record.knife_4,
                record.knife_5, record.knife_6, record.knife_7, record.knife_8,
                record.total_in, record.role_frontdesk, record.role_order_opener,
                record.role_newbie, record.role_group_chat, record.role_customer_service,
                record.role_maintenance
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_financial_records_by_date(self, start_date: str, end_date: str = None) -> List[FinancialRecord]:
        """Get financial records for a date range."""
        async with self.get_connection() as db:
            if end_date:
                cursor = await db.execute("""
                    SELECT * FROM financial_records WHERE date BETWEEN ? AND ? ORDER BY date DESC
                """, (start_date, end_date))
            else:
                cursor = await db.execute("""
                    SELECT * FROM financial_records WHERE date = ? ORDER BY created_at DESC
                """, (start_date,))
            rows = await cursor.fetchall()
            return [self._row_to_financial_record(row) for row in rows]

    # Team Members CRUD
    async def create_team_member(self, member: TeamMember) -> int:
        """Register a new team member."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                INSERT OR REPLACE INTO team_members (
                    user_id, chat_id, username, first_name, last_name,
                    phone_number, frontdesk_name, role, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                member.user_id, member.chat_id, member.username, member.first_name,
                member.last_name, member.phone_number, member.frontdesk_name,
                member.role, member.is_active
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_team_member_by_user_id(self, user_id: int) -> Optional[TeamMember]:
        """Get team member by user ID."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                SELECT * FROM team_members WHERE user_id = ? AND is_active = TRUE
            """, (user_id,))
            row = await cursor.fetchone()
            return self._row_to_team_member(row) if row else None

    async def update_team_member_activity(self, user_id: int):
        """Update last activity timestamp for team member."""
        async with self.get_connection() as db:
            await db.execute("""
                UPDATE team_members SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?
            """, (user_id,))
            await db.commit()

    # Reminders CRUD
    async def create_reminder(self, reminder: Reminder) -> int:
        """Create a new reminder."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO reminders (
                    client_record_id, frontdesk_user_id, reminder_type,
                    scheduled_time, message
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                reminder.client_record_id, reminder.frontdesk_user_id,
                reminder.reminder_type, reminder.scheduled_time, reminder.message
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_pending_reminders(self, before_time: datetime = None) -> List[Reminder]:
        """Get all pending reminders scheduled before given time."""
        if before_time is None:
            before_time = datetime.now()

        async with self.get_connection() as db:
            cursor = await db.execute("""
                SELECT * FROM reminders
                WHERE is_sent = FALSE AND scheduled_time <= ?
                ORDER BY scheduled_time ASC
            """, (before_time,))
            rows = await cursor.fetchall()
            return [self._row_to_reminder(row) for row in rows]

    async def mark_reminder_sent(self, reminder_id: int):
        """Mark reminder as sent."""
        async with self.get_connection() as db:
            await db.execute("""
                UPDATE reminders SET is_sent = TRUE, sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (reminder_id,))
            await db.commit()

    # Bot Tasks CRUD (for Ralph Loop)
    async def create_task(self, task: BotTask) -> int:
        """Create a new task for processing."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO bot_tasks (
                    task_type, priority, data, status, scheduled_time, max_attempts
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                task.task_type, task.priority, json.dumps(task.data),
                task.status, task.scheduled_time, task.max_attempts
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_next_task(self) -> Optional[BotTask]:
        """Get the next task to process."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                SELECT * FROM bot_tasks
                WHERE status = 'pending' AND (scheduled_time IS NULL OR scheduled_time <= ?)
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """, (datetime.now(),))
            row = await cursor.fetchone()
            return self._row_to_bot_task(row) if row else None

    async def update_task_status(self, task_id: int, status: str, error_message: str = None):
        """Update task status and increment attempts."""
        async with self.get_connection() as db:
            await db.execute("""
                UPDATE bot_tasks
                SET status = ?, attempts = attempts + 1, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, error_message, task_id))
            await db.commit()

    # Helper methods for converting rows to models
    def _row_to_client_record(self, row) -> ClientRecord:
        """Convert database row to ClientRecord."""
        if not row:
            return None
        return ClientRecord(
            row_num=row[1], date=row[2], phone_remark=row[3], frontdesk=row[4],
            category=row[5], recruiter=row[6], frontdesk_number=row[7],
            frontdesk_username=row[8], client_number=row[9], account_id=row[10],
            first_day=row[11], second_day=row[12], client_condition=row[13],
            sheet_gid=row[14], block_number=row[15]
        )

    def _row_to_performance_record(self, row) -> PerformanceRecord:
        """Convert database row to PerformanceRecord."""
        if not row:
            return None
        return PerformanceRecord(
            name=row[1], category=row[2], powder_count=row[3], no_initial_reply=row[4],
            reply_rate=row[5], stuck_explanation=row[6], blocked_or_play=row[7],
            been_scammed=row[8], sent_link_no_reply=row[9], completed_register=row[10],
            review_rate=row[11], completed_training=row[12], scheduled_time=row[13],
            withdrawal=row[14], new_order=row[15], conversion_rate=row[16],
            new_kill=row[17], dead_client=row[18], is_sum_row=bool(row[19])
        )

    def _row_to_financial_record(self, row) -> FinancialRecord:
        """Convert database row to FinancialRecord."""
        if not row:
            return None
        return FinancialRecord(
            date=row[1], account_id=row[2], group_id=row[3], frontdesk=row[4],
            maintenance=row[5], frontdesk_number=row[6], platform=row[7],
            new_order_amount=row[8], pressure_amount=row[9], note=row[10],
            knife_1=row[11], knife_2=row[12], knife_3=row[13], knife_4=row[14],
            knife_5=row[15], knife_6=row[16], knife_7=row[17], knife_8=row[18],
            total_in=row[19], role_frontdesk=row[20], role_order_opener=row[21],
            role_newbie=row[22], role_group_chat=row[23], role_customer_service=row[24],
            role_maintenance=row[25]
        )

    def _row_to_team_member(self, row) -> TeamMember:
        """Convert database row to TeamMember."""
        if not row:
            return None
        return TeamMember(
            user_id=row[1], chat_id=row[2], username=row[3], first_name=row[4],
            last_name=row[5], phone_number=row[6], frontdesk_name=row[7],
            role=row[8], is_active=bool(row[9])
        )

    def _row_to_reminder(self, row) -> Reminder:
        """Convert database row to Reminder."""
        if not row:
            return None
        return Reminder(
            id=row[0], client_record_id=row[1], frontdesk_user_id=row[2],
            reminder_type=row[3], scheduled_time=datetime.fromisoformat(row[4]),
            message=row[5], is_sent=bool(row[6]),
            sent_at=datetime.fromisoformat(row[7]) if row[7] else None
        )

    def _row_to_bot_task(self, row) -> BotTask:
        """Convert database row to BotTask."""
        if not row:
            return None
        return BotTask(
            id=row[0], task_type=row[1], priority=row[2],
            data=json.loads(row[3]) if row[3] else {},
            status=row[4], scheduled_time=datetime.fromisoformat(row[5]) if row[5] else None,
            attempts=row[6], max_attempts=row[7], error_message=row[8]
        )

    # Utility methods
    async def backup_database(self) -> str:
        """Create a backup of the database."""
        import shutil
        import os
        from datetime import datetime

        backup_dir = config.database.backup_dir
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"team_records_backup_{timestamp}.db")

        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to {backup_path}")
        return backup_path

    async def cleanup_old_tasks(self, days_old: int = 7):
        """Clean up old completed tasks."""
        if days_old <= 0:
            raise ValueError("days_old must be positive")

        async with self.get_connection() as db:
            # Use parameterized query to prevent SQL injection
            cutoff_date = datetime.now() - timedelta(days=days_old)
            await db.execute("""
                DELETE FROM bot_tasks
                WHERE status IN ('completed', 'failed')
                AND updated_at < ?
            """, (cutoff_date.isoformat(),))
            await db.commit()

    # Conversation state management
    async def set_conversation_state(self, user_id: int, state_data: Dict[str, Any]):
        """Set conversation state for a user."""
        # Validate state data structure
        if not isinstance(state_data, dict):
            raise ValueError("Conversation state must be a dictionary")

        # Ensure JSON serializable
        try:
            json_data = json.dumps(state_data, ensure_ascii=False)
            if len(json_data) > 10000:  # Limit to 10KB
                raise ValueError("Conversation state too large")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Conversation state not JSON serializable: {e}")

        async with self.get_connection() as db:
            await db.execute("""
                INSERT OR REPLACE INTO conversation_states
                (user_id, state_data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (user_id, json_data))
            await db.commit()

    async def get_conversation_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get conversation state for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                SELECT state_data FROM conversation_states WHERE user_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse conversation state for user {user_id}: {e}")
                    return None
            return None

    async def clear_conversation_state(self, user_id: int):
        """Clear conversation state for a user."""
        async with self.get_connection() as db:
            await db.execute("""
                DELETE FROM conversation_states WHERE user_id = ?
            """, (user_id,))
            await db.commit()

    async def cleanup_old_conversation_states(self, hours_old: int = 24):
        """Clean up old conversation states."""
        if hours_old <= 0:
            raise ValueError("hours_old must be positive")

        async with self.get_connection() as db:
            cutoff_time = datetime.now() - timedelta(hours=hours_old)
            await db.execute("""
                DELETE FROM conversation_states
                WHERE updated_at < ?
            """, (cutoff_time.isoformat(),))
            await db.commit()

    async def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        stats = {}
        async with self.get_connection() as db:
            for table in ["client_records", "performance_records", "financial_records",
                         "team_members", "reminders", "bot_tasks", "conversation_states"]:
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
                count = await cursor.fetchone()
                stats[table] = count[0]
        return stats


# Global database instance
database = Database()
"""Import phone registry data from data/phone_registry_import.json.

Standalone script: python import_phone_registry.py
"""
import asyncio
import json
import logging
import os
import re
import sys

import aiosqlite

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = os.getenv('DB_PATH', './team_records_v2.db')
IMPORT_FILE = os.path.join(os.path.dirname(__file__), 'data', 'phone_registry_import.json')


def normalize_phone(phone: str) -> str:
    return re.sub(r'[^\d]', '', phone)


async def fuzzy_match_staff(db: aiosqlite.Connection, submitter_name: str) -> int | None:
    """Try to match submitter name to existing staff display_name."""
    if not submitter_name or submitter_name == 'Unknown':
        return None
    # Exact match first
    async with db.execute(
        'SELECT id FROM staff WHERE display_name = ?', (submitter_name,)
    ) as cur:
        row = await cur.fetchone()
        if row:
            return row['id']
    # Partial match (submitter contains staff name or vice versa)
    async with db.execute('SELECT id, display_name FROM staff') as cur:
        rows = await cur.fetchall()
    for row in rows:
        name = row['display_name']
        if name.lower() in submitter_name.lower() or submitter_name.lower() in name.lower():
            return row['id']
    return None


async def run_import():
    if not os.path.exists(IMPORT_FILE):
        logger.error(f'Import file not found: {IMPORT_FILE}')
        sys.exit(1)

    with open(IMPORT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    numbers = data.get('numbers', {})
    logger.info(f'Loaded {len(numbers)} unique numbers from {IMPORT_FILE}')

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA journal_mode = WAL')
        await db.execute('PRAGMA foreign_keys = ON')

        # Ensure tables exist
        await db.execute("""
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
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS phone_registry_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_normalized TEXT NOT NULL,
                action TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                actor_staff_id INTEGER REFERENCES staff(id),
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

        imported = 0
        duplicates_logged = 0
        staff_matched = 0
        unmatched_submitters = set()

        # Cache staff matches
        staff_cache: dict[str, int | None] = {}

        for phone, entry in numbers.items():
            normalized = normalize_phone(phone)
            first_submitter = entry.get('first_submitter', 'Unknown')
            first_date = entry.get('first_date', '2025-01-01T00:00:00')

            # Match submitter to staff
            if first_submitter not in staff_cache:
                staff_cache[first_submitter] = await fuzzy_match_staff(db, first_submitter)
            staff_id = staff_cache[first_submitter]

            if staff_id:
                staff_matched += 1
            elif first_submitter != 'Unknown':
                unmatched_submitters.add(first_submitter)

            # Insert primary record
            try:
                await db.execute(
                    """INSERT OR IGNORE INTO phone_registry
                       (phone, phone_normalized, submitter_name, submitter_staff_id, source, submitted_at)
                       VALUES (?, ?, ?, ?, 'import', ?)""",
                    (phone, normalized, first_submitter, staff_id, first_date)
                )
                imported += 1
            except Exception as e:
                logger.debug(f'Skip {phone}: {e}')

            # Log all submissions
            for sub in entry.get('submissions', []):
                submitter = sub.get('submitter', 'Unknown')
                sub_date = sub.get('date', first_date)
                is_dup = sub.get('is_duplicate', False)
                action = 'duplicate_blocked' if is_dup else 'import'

                if submitter not in staff_cache:
                    staff_cache[submitter] = await fuzzy_match_staff(db, submitter)

                details = json.dumps({
                    'original_submitter': first_submitter,
                    'is_duplicate': is_dup,
                }, ensure_ascii=False) if is_dup else None

                await db.execute(
                    """INSERT INTO phone_registry_log
                       (phone_normalized, action, actor_name, actor_staff_id, details)
                       VALUES (?, ?, ?, ?, ?)""",
                    (normalized, action, submitter, staff_cache[submitter], details)
                )
                if is_dup:
                    duplicates_logged += 1

        await db.commit()

    logger.info(f'--- Import Complete ---')
    logger.info(f'Imported: {imported} phone numbers')
    logger.info(f'Duplicate conflicts logged: {duplicates_logged}')
    logger.info(f'Staff matched: {staff_matched}')
    logger.info(f'Unmatched submitters ({len(unmatched_submitters)}): {sorted(unmatched_submitters)[:20]}')


if __name__ == '__main__':
    asyncio.run(run_import())

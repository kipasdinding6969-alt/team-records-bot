#!/usr/bin/env python3
"""
Import phone numbers from phone_numbers_extracted.json into chat_export_phones.

Reads the pre-extracted JSON (from 64Gram chat export), normalizes phones,
tracks first submitter/date, flags cross-user duplicates, and inserts into
chat_export_phones table. Also merges new entries into phone_registry.

Usage:
    /home/baiwan/repos/team-records-bot-v2/.venv/bin/python scripts/import_chat_phones.py
"""

import json
import re
import sqlite3
import sys
from datetime import datetime

JSON_PATH = "/home/baiwan/Downloads/64Gram Desktop/ChatExport_2026-03-31/phone_numbers_extracted.json"
DB_PATH = "/home/baiwan/repos/team-records-bot-v2/team_records_v2.db"


def normalize_phone(raw: str) -> str:
    """Strip +, spaces, dashes, parentheses -- keep digits only."""
    return re.sub(r"[^\d]", "", raw)


def extract_tg_id(from_id: str) -> int | None:
    """Strip 'user' prefix and return integer."""
    if not from_id:
        return None
    stripped = from_id.replace("user", "").replace("channel", "")
    try:
        return int(stripped)
    except (ValueError, TypeError):
        return None


def create_tables(conn: sqlite3.Connection) -> None:
    """Ensure chat_export_phones table exists."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_export_phones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            phone_normalized TEXT,
            submitter_name TEXT,
            submitter_tg_id INTEGER,
            first_submitted_at TEXT,
            last_submitted_at TEXT,
            message_count INTEGER DEFAULT 1,
            is_duplicate_flagged INTEGER DEFAULT 0,
            staff_id INTEGER REFERENCES staff(id),
            imported_at TEXT DEFAULT (datetime('now')),
            UNIQUE(phone_normalized, submitter_tg_id)
        );
        CREATE INDEX IF NOT EXISTS idx_cep_phone ON chat_export_phones(phone_normalized);
        CREATE INDEX IF NOT EXISTS idx_cep_submitter ON chat_export_phones(submitter_tg_id);
        CREATE INDEX IF NOT EXISTS idx_cep_submitted_at ON chat_export_phones(first_submitted_at);
    """)
    conn.commit()


def load_staff_map(conn: sqlite3.Connection) -> dict[int, int]:
    """Load tg_user_id -> staff.id mapping."""
    cur = conn.execute("SELECT id, tg_user_id FROM staff WHERE tg_user_id IS NOT NULL")
    return {row[1]: row[0] for row in cur.fetchall()}


def main() -> None:
    json_path = sys.argv[1] if len(sys.argv) > 1 else JSON_PATH

    # Load extracted JSON
    print(f"Loading {json_path} ...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    numbers = data.get("numbers", {})
    print(f"Total unique numbers in JSON: {data.get('total_unique_numbers', len(numbers))}")
    print(f"Total entries in JSON: {data.get('total_entries', 'N/A')}")
    print(f"Cross-user duplicates in JSON: {data.get('cross_user_duplicates', 'N/A')}")

    # Build per-(phone, submitter) records from the entries
    # Each number key maps to entries array; a phone may have multiple entries
    # from different users. We aggregate per (normalized_phone, submitter_tg_id).
    records = {}  # (normalized, tg_id) -> dict
    cross_user_set = set()  # normalized phones with cross-user duplicates
    total_entries = 0
    skipped_no_norm = 0

    for phone_key, phone_data in numbers.items():
        entries = phone_data.get("entries", [])
        is_cross_user = phone_data.get("is_cross_user_duplicate", False)

        for entry in entries:
            total_entries += 1
            raw_phone = entry.get("phone_raw", phone_key)
            normalized = normalize_phone(raw_phone)
            if not normalized or len(normalized) < 7:
                skipped_no_norm += 1
                continue

            from_name = entry.get("from", "Unknown")
            from_id = entry.get("from_id", "")
            tg_id = extract_tg_id(from_id)
            date_str = entry.get("date", "")

            if is_cross_user:
                cross_user_set.add(normalized)

            key = (normalized, tg_id)
            if key in records:
                rec = records[key]
                rec["message_count"] += 1
                if date_str and date_str < rec["first_submitted_at"]:
                    rec["first_submitted_at"] = date_str
                if date_str and date_str > rec["last_submitted_at"]:
                    rec["last_submitted_at"] = date_str
            else:
                records[key] = {
                    "phone": raw_phone,
                    "phone_normalized": normalized,
                    "submitter_name": from_name,
                    "submitter_tg_id": tg_id,
                    "first_submitted_at": date_str,
                    "last_submitted_at": date_str,
                    "message_count": 1,
                }

    print(f"\nParsed {total_entries} entries -> {len(records)} unique (phone, submitter) pairs")
    print(f"Cross-user duplicate phones: {len(cross_user_set)}")
    print(f"Skipped (too short): {skipped_no_norm}")

    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        create_tables(conn)
        staff_map = load_staff_map(conn)
        print(f"Loaded {len(staff_map)} staff records for matching")

        # Insert records
        inserted = 0
        updated = 0
        staff_matched = 0
        conflicts = 0

        cur = conn.cursor()
        for (norm, tg_id), rec in records.items():
            is_dup = 1 if norm in cross_user_set else 0
            sid = staff_map.get(tg_id) if tg_id else None
            if sid:
                staff_matched += 1

            cur.execute(
                """
                INSERT INTO chat_export_phones
                    (phone, phone_normalized, submitter_name, submitter_tg_id,
                     first_submitted_at, last_submitted_at, message_count,
                     is_duplicate_flagged, staff_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(phone_normalized, submitter_tg_id) DO UPDATE SET
                    message_count = chat_export_phones.message_count + excluded.message_count,
                    first_submitted_at = MIN(chat_export_phones.first_submitted_at, excluded.first_submitted_at),
                    last_submitted_at = MAX(chat_export_phones.last_submitted_at, excluded.last_submitted_at),
                    is_duplicate_flagged = MAX(chat_export_phones.is_duplicate_flagged, excluded.is_duplicate_flagged),
                    staff_id = COALESCE(excluded.staff_id, chat_export_phones.staff_id)
                """,
                (
                    rec["phone"],
                    norm,
                    rec["submitter_name"],
                    tg_id,
                    rec["first_submitted_at"],
                    rec["last_submitted_at"],
                    rec["message_count"],
                    is_dup,
                    sid,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                updated += 1

        conn.commit()

        # Merge into phone_registry
        merged = 0
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'phone_registry'"
        )
        if cur.fetchone()[0] > 0:
            cur.execute(
                """
                INSERT OR IGNORE INTO phone_registry
                    (phone, phone_normalized, submitter_name, submitter_staff_id,
                     source, submitted_at, origin, tg_user_id, duplicate_count)
                SELECT
                    cep.phone,
                    cep.phone_normalized,
                    cep.submitter_name,
                    cep.staff_id,
                    'import_chatexport',
                    cep.first_submitted_at,
                    'chat_export',
                    CAST(cep.submitter_tg_id AS TEXT),
                    cep.is_duplicate_flagged
                FROM chat_export_phones cep
                WHERE cep.phone_normalized IS NOT NULL
                  AND cep.phone_normalized NOT IN (
                      SELECT phone_normalized FROM phone_registry
                      WHERE phone_normalized IS NOT NULL
                  )
                """
            )
            merged = cur.rowcount
            conn.commit()
            print(f"Merged {merged} new phones into phone_registry")
        else:
            print("phone_registry table not found, skipping merge")

        # Final counts
        cur.execute("SELECT COUNT(*) FROM chat_export_phones")
        db_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chat_export_phones WHERE is_duplicate_flagged = 1")
        db_dup = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chat_export_phones WHERE staff_id IS NOT NULL")
        db_staff = cur.fetchone()[0]

        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"JSON entries processed:          {total_entries:,}")
        print(f"Unique (phone, submitter) pairs: {len(records):,}")
        print(f"Cross-user duplicate phones:     {len(cross_user_set):,}")
        print(f"Inserted into chat_export:       {inserted:,}")
        print(f"Updated (conflict merge):        {updated:,}")
        print(f"Matched to staff:                {staff_matched:,}")
        print(f"Merged to phone_registry:        {merged:,}")
        print(f"Total rows in chat_export_phones:{db_total:,}")
        print(f"Duplicate-flagged in DB:         {db_dup:,}")
        print(f"Staff-linked in DB:              {db_staff:,}")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()

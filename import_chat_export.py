#!/usr/bin/env python3
"""
Import phone numbers from Telegram chat export (撞粉群 / DUPLICATE NUM).

Reads the 64Gram Desktop chat export JSON, extracts phone numbers,
normalizes them with the phonenumbers library, detects duplicate flags
from the bot, and stores everything in the chat_export_phones table.

Usage:
    /home/baiwan/repos/team-records-bot-v2/.venv/bin/python import_chat_export.py
"""

import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

import ijson
import phonenumbers

EXPORT_PATH = "/home/baiwan/Downloads/64Gram Desktop/ChatExport_2026-03-31/result.json"
DB_PATH = "/home/baiwan/repos/team-records-bot-v2/team_records_v2.db"

# The duplicate-checking bot's user ID in the chat
DUP_BOT_FROM_ID = "user6172201682"

# Phone regex for extracting from text/code blocks
PHONE_RE = re.compile(r"^\+?\d{7,15}$")
# Looser regex for inline text
PHONE_INLINE_RE = re.compile(r"\+?\d{7,15}")


def normalize_phone(raw_phone: str) -> str | None:
    """Normalize a phone number using phonenumbers library.

    Tries parsing with +, then without (defaulting to SE/+46 region).
    Returns E.164 format or None if unparseable.
    """
    raw = raw_phone.strip()
    if not raw:
        return None

    # Try parsing as-is (with + prefix if present)
    for region in (None, "SE", "NO", "CN"):
        try:
            parsed = phonenumbers.parse(raw, region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            continue

    # Fallback: strip non-digits and try with + prefix
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7:
        return None
    for attempt in [f"+{digits}", f"+46{digits}"]:
        try:
            parsed = phonenumbers.parse(attempt, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            continue

    # Last resort: return cleaned digits if reasonable length
    if 7 <= len(digits) <= 15:
        return f"+{digits}" if not digits.startswith("+") else digits
    return None


def extract_text_string(text_field) -> str:
    """Flatten the text field (can be str or list of str/dict) into a string."""
    if isinstance(text_field, str):
        return text_field
    if isinstance(text_field, list):
        parts = []
        for item in text_field:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""


def extract_tg_id(from_id: str | None) -> int | None:
    """Strip 'user' prefix from from_id and return integer."""
    if not from_id:
        return None
    stripped = from_id.replace("user", "").replace("channel", "")
    try:
        return int(stripped)
    except (ValueError, TypeError):
        return None


def create_tables(conn: sqlite3.Connection) -> None:
    """Create the chat_export_phones table and indexes."""
    cur = conn.cursor()
    cur.executescript("""
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
    """)
    conn.commit()


def load_staff_map(conn: sqlite3.Connection) -> dict[int, int]:
    """Load tg_user_id -> staff.id mapping."""
    cur = conn.cursor()
    cur.execute("SELECT id, tg_user_id FROM staff WHERE tg_user_id IS NOT NULL")
    return {row[1]: row[0] for row in cur.fetchall()}


def process_messages(filepath: str):
    """Stream-parse the JSON and extract phone records and duplicate flags.

    Returns:
        phone_records: dict of (normalized_phone, submitter_tg_id) -> record dict
        dup_flagged_phones: set of normalized phone numbers flagged as duplicates
        total_messages: int
    """
    print(f"Loading {filepath} ...")

    # Use ijson to stream the messages array
    phone_records = {}  # (normalized_phone, tg_id) -> record
    dup_flagged_phones = set()  # normalized phones flagged by bot
    total_messages = 0
    skipped_service = 0

    with open(filepath, "r", encoding="utf-8") as f:
        messages = ijson.items(f, "messages.item")

        for msg in messages:
            msg_type = msg.get("type")
            if msg_type == "service":
                skipped_service += 1
                continue
            if msg_type != "message":
                continue

            total_messages += 1
            from_name = msg.get("from") or "Unknown"
            from_id_raw = msg.get("from_id")
            tg_id = extract_tg_id(from_id_raw)
            date_str = msg.get("date", "")
            text_entities = msg.get("text_entities", [])
            full_text = extract_text_string(msg.get("text", ""))

            # Check if this is a duplicate-flag message from the bot
            is_bot_msg = from_id_raw == DUP_BOT_FROM_ID
            if is_bot_msg and "⚠" in full_text:
                # Extract the flagged phone from code entities
                for ent in text_entities:
                    if ent.get("type") == "code":
                        raw = ent.get("text", "").strip()
                        if PHONE_RE.match(raw):
                            norm = normalize_phone(raw)
                            if norm:
                                dup_flagged_phones.add(norm)
                continue  # Don't count bot messages as submissions

            # Skip bot confirmation messages (✅ 记录成功)
            if is_bot_msg:
                continue

            # Extract phones from text_entities
            found_phones = set()
            for ent in text_entities:
                ent_type = ent.get("type")
                ent_text = ent.get("text", "").strip()

                if ent_type == "phone":
                    found_phones.add(ent_text)
                elif ent_type == "code" and PHONE_RE.match(ent_text):
                    found_phones.add(ent_text)

            # Also try regex on full text for any missed phones
            for match in PHONE_INLINE_RE.finditer(full_text):
                candidate = match.group()
                # Only add if it looks like a real phone (not a timestamp or random digits)
                digits = re.sub(r"\D", "", candidate)
                if 7 <= len(digits) <= 15:
                    found_phones.add(candidate)

            # Process each found phone
            for raw_phone in found_phones:
                norm = normalize_phone(raw_phone)
                if not norm:
                    continue

                key = (norm, tg_id)
                if key in phone_records:
                    rec = phone_records[key]
                    rec["message_count"] += 1
                    if date_str and date_str < rec["first_submitted_at"]:
                        rec["first_submitted_at"] = date_str
                    if date_str and date_str > rec["last_submitted_at"]:
                        rec["last_submitted_at"] = date_str
                else:
                    phone_records[key] = {
                        "phone": raw_phone,
                        "phone_normalized": norm,
                        "submitter_name": from_name,
                        "submitter_tg_id": tg_id,
                        "first_submitted_at": date_str,
                        "last_submitted_at": date_str,
                        "message_count": 1,
                    }

            if total_messages % 10000 == 0:
                print(f"  ... processed {total_messages} messages, {len(phone_records)} phone records so far")

    print(f"Finished parsing: {total_messages} messages, {skipped_service} service messages skipped")
    return phone_records, dup_flagged_phones, total_messages


def insert_records(
    conn: sqlite3.Connection,
    phone_records: dict,
    dup_flagged_phones: set,
    staff_map: dict[int, int],
) -> tuple[int, int, int]:
    """Insert/update records into chat_export_phones.

    Returns: (inserted, updated, staff_matched)
    """
    cur = conn.cursor()
    inserted = 0
    updated = 0
    staff_matched = 0

    for (norm_phone, tg_id), rec in phone_records.items():
        is_dup = 1 if norm_phone in dup_flagged_phones else 0
        sid = staff_map.get(tg_id) if tg_id else None
        if sid:
            staff_matched += 1

        # Try insert, on conflict update
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
                norm_phone,
                rec["submitter_name"],
                tg_id,
                rec["first_submitted_at"],
                rec["last_submitted_at"],
                rec["message_count"],
                is_dup,
                sid,
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            updated += 1

    conn.commit()
    return inserted, updated, staff_matched


def merge_to_phone_registry(conn: sqlite3.Connection, staff_map: dict[int, int]) -> int:
    """Merge new phones from chat_export_phones into phone_registry if it exists.

    Returns number of new records merged.
    """
    cur = conn.cursor()

    # Check if phone_registry table exists
    cur.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'phone_registry'"
    )
    if cur.fetchone()[0] == 0:
        print("phone_registry table not found, skipping merge.")
        return 0

    # Insert phones that don't exist in phone_registry yet
    cur.execute(
        """
        INSERT OR IGNORE INTO phone_registry
            (phone, phone_normalized, submitter_name, submitter_staff_id, source, submitted_at)
        SELECT
            cep.phone,
            cep.phone_normalized,
            cep.submitter_name,
            cep.staff_id,
            'import_chatexport',
            cep.first_submitted_at
        FROM chat_export_phones cep
        WHERE cep.phone_normalized IS NOT NULL
          AND cep.phone_normalized NOT IN (
              SELECT phone_normalized FROM phone_registry WHERE phone_normalized IS NOT NULL
          )
        """
    )
    merged = cur.rowcount
    conn.commit()
    print(f"Merged {merged} new phones into phone_registry.")
    return merged


def print_summary(
    conn: sqlite3.Connection,
    total_messages: int,
    phone_records: dict,
    dup_flagged_phones: set,
    staff_matched: int,
) -> None:
    """Print import summary stats."""
    cur = conn.cursor()

    # Unique normalized phones
    unique_phones = set()
    for (norm, _), _ in phone_records.items():
        unique_phones.add(norm)

    # Top 10 submitters
    submitter_counts = defaultdict(lambda: {"name": "", "count": 0})
    for (_, tg_id), rec in phone_records.items():
        key = tg_id or 0
        submitter_counts[key]["name"] = rec["submitter_name"]
        submitter_counts[key]["count"] += rec["message_count"]

    top_submitters = sorted(
        submitter_counts.items(), key=lambda x: x[1]["count"], reverse=True
    )[:10]

    # DB totals
    cur.execute("SELECT COUNT(*) FROM chat_export_phones")
    db_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chat_export_phones WHERE is_duplicate_flagged = 1")
    db_dup = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chat_export_phones WHERE staff_id IS NOT NULL")
    db_staff = cur.fetchone()[0]

    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"Total messages processed:       {total_messages:,}")
    print(f"Total phone records (per user):  {len(phone_records):,}")
    print(f"Total unique phones:             {len(unique_phones):,}")
    print(f"Duplicate-flagged phones:        {len(dup_flagged_phones):,}")
    print(f"Matched to existing staff:       {staff_matched:,}")
    print(f"Records in DB (chat_export):     {db_total:,}")
    print(f"Flagged in DB:                   {db_dup:,}")
    print(f"Staff-linked in DB:              {db_staff:,}")
    print()
    print("TOP 10 SUBMITTERS BY MESSAGE COUNT:")
    print(f"  {'Rank':<5} {'Name':<30} {'TG ID':<15} {'Count':<8}")
    print(f"  {'-'*5} {'-'*30} {'-'*15} {'-'*8}")
    for i, (tg_id, info) in enumerate(top_submitters, 1):
        print(f"  {i:<5} {info['name']:<30} {tg_id or 'N/A':<15} {info['count']:<8}")
    print("=" * 60)


def main() -> None:
    global EXPORT_PATH
    if len(sys.argv) > 1:
        EXPORT_PATH = sys.argv[1]

    # Parse messages
    phone_records, dup_flagged_phones, total_messages = process_messages(EXPORT_PATH)

    print(f"\nExtracted {len(phone_records)} phone records, {len(dup_flagged_phones)} duplicate-flagged phones")

    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        # Create table
        create_tables(conn)

        # Load staff mapping
        staff_map = load_staff_map(conn)
        print(f"Loaded {len(staff_map)} staff records for matching")

        # Insert records
        inserted, updated, staff_matched = insert_records(
            conn, phone_records, dup_flagged_phones, staff_map
        )
        print(f"Inserted: {inserted}, Updated: {updated}")

        # Merge to phone_registry
        merge_to_phone_registry(conn, staff_map)

        # Summary
        print_summary(conn, total_messages, phone_records, dup_flagged_phones, staff_matched)

    finally:
        conn.close()


if __name__ == "__main__":
    main()

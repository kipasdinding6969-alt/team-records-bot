import json
import sqlite3
import re
from datetime import datetime

print("Loading JSON...")
try:
    with open('/home/baiwan/Downloads/64Gram Desktop/ChatExport_2026-03-31/result.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print("ChatExport file not found.")
    exit(1)

messages = data.get('messages', [])
print(f"Total messages in export: {len(messages)}")

phones_to_insert = {} # map of normalized_phone -> (original_phone, timestamp, actor_id/name)
for msg in messages:
    if msg.get('type') == 'message':
        # Simple extraction of phone numbers
        text_entities = msg.get('text_entities', [])
        for ent in text_entities:
            if ent.get('type') == 'phone':
                phone = ent.get('text', '')
                clean = re.sub(r'\D', '', phone)
                if clean:
                    # Keep the earliest date
                    ts_str = msg.get('date', '')
                    phones_to_insert[clean] = {
                        'original': phone,
                        'date': ts_str,
                        'from_id': msg.get('from_id', 'unknown'),
                        'from_name': msg.get('from') or 'Unknown User'
                    }

print(f"Total unique phone numbers extracted: {len(phones_to_insert)}")

db_path = '/home/baiwan/team-records-bot/team_records_v2.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Ensure tables exist
c.executescript("""
CREATE TABLE IF NOT EXISTS phone_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    phone_normalized TEXT NOT NULL UNIQUE,
    submitter_name TEXT NOT NULL,
    submitter_staff_id INTEGER,
    source TEXT NOT NULL,
    submitted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phone_registry_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_normalized TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    actor_staff_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    details TEXT
);

CREATE TABLE IF NOT EXISTS client_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id_1 INTEGER NOT NULL,
    client_id_2 INTEGER NOT NULL,
    link_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by_name TEXT NOT NULL,
    created_by_staff_id INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS permission_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT 1,
    granted_by_name TEXT NOT NULL,
    granted_by_staff_id INTEGER,
    granted_at TEXT NOT NULL DEFAULT (datetime('now')),
    reason TEXT
);
""")
conn.commit()

c.execute("SELECT phone_normalized FROM phone_registry")
existing = set([row[0] for row in c.fetchall()])
print(f"Total existing in DB: {len(existing)}")

new_inserts = 0
for clean_phone, info in phones_to_insert.items():
    if clean_phone not in existing:
        try:
            c.execute("""
                INSERT INTO phone_registry 
                (phone, phone_normalized, submitter_name, submitter_staff_id, source, submitted_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (info['original'], clean_phone, info['from_name'], None, 'import_chatexport', info['date']))
            
            c.execute("""
                INSERT INTO phone_registry_log 
                (phone_normalized, action, actor_name, created_at) 
                VALUES (?, ?, ?, ?)
            """, (clean_phone, 'import', 'system', info['date']))
            new_inserts += 1
        except Exception as e:
            print(f"Error inserting {clean_phone}: {e}")

conn.commit()
print(f"Successfully inserted {new_inserts} new phone numbers into registry.")

conn.close()

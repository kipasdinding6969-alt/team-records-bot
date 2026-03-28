#!/usr/bin/env python3
"""NocoDB Setup — Create tables in existing base."""
import requests, json, sys

NOCODB_URL = "http://localhost:8080"
BASE_ID = "pq3jgqmclgw0ila"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImFkbWluQHFpYW5odWIubG9jYWwiLCJkaXNwbGF5X25hbWUiOm51bGwsImF2YXRhciI6bnVsbCwidXNlcl9uYW1lIjpudWxsLCJpZCI6InVzczlibGxlajI2bHM1emsiLCJyb2xlcyI6eyJvcmctbGV2ZWwtY3JlYXRvciI6dHJ1ZSwic3VwZXIiOnRydWV9LCJ0b2tlbl92ZXJzaW9uIjoiNDg5MmZhODg1YjY3NjdmNGVhNzYyZjY5NzhjNWJmMjJkYmQwNmM1ZmQ2NjAzMDEzZWQ0OWNmMDM5YmI2YmRhOWM4ZjIyN2UyNjk0YTFkNDYiLCJpYXQiOjE3NzQ3MzMxNDcsImV4cCI6MTc3NDc2OTE0N30.v1bucnsPIMZo9d4oi_tiRSaFq5KJOFWTyoa2DxGx4h4"

headers = {"xc-auth": JWT, "Content-Type": "application/json"}

def api(method, path, data=None):
    r = getattr(requests, method)(f"{NOCODB_URL}{path}", headers=headers, json=data)
    if r.status_code >= 400:
        print(f"ERROR {method.upper()} {path}: {r.status_code} {r.text[:200]}")
        return None
    try: return r.json()
    except: return r.text

def create_table(title, columns):
    result = api("post", f"/api/v2/meta/bases/{BASE_ID}/tables", {
        "table_name": title, "title": title, "columns": columns
    })
    if result:
        print(f"  ✅ {title} (id: {result.get('id','?')})")
    return result

print("🏗  Creating tables in NocoDB...")

tables = {}

tables["staff"] = create_table("Staff", [
    {"column_name": "tg_user_id", "title": "Telegram ID", "uidt": "Number", "pv": True},
    {"column_name": "display_name", "title": "Display Name", "uidt": "SingleLineText"},
    {"column_name": "username", "title": "Username", "uidt": "SingleLineText"},
    {"column_name": "phone", "title": "Phone", "uidt": "PhoneNumber"},
    {"column_name": "role", "title": "Role", "uidt": "SingleSelect", "dtxp": "'admin','manager','frontdesk','viewer','maintenance'"},
    {"column_name": "team", "title": "Team", "uidt": "SingleSelect", "dtxp": "'阿俊组','何军组'"},
    {"column_name": "language", "title": "Language", "uidt": "SingleSelect", "dtxp": "'zh','en'"},
    {"column_name": "is_active", "title": "Active", "uidt": "Checkbox"},
    {"column_name": "joined_at", "title": "Joined", "uidt": "DateTime"},
])

tables["clients"] = create_table("Clients", [
    {"column_name": "phone", "title": "Phone", "uidt": "PhoneNumber", "pv": True},
    {"column_name": "source", "title": "Source", "uidt": "SingleSelect", "dtxp": "'飞机筛选','RCS筛选','CA表单粉','UK表单粉','其他'"},
    {"column_name": "status", "title": "Status", "uidt": "SingleSelect", "dtxp": "'new','contacted','replied','registered','training','withdrew','ordered','dead'"},
    {"column_name": "platform", "title": "Platform", "uidt": "SingleLineText"},
    {"column_name": "condition", "title": "Condition", "uidt": "LongText"},
    {"column_name": "frontdesk_name", "title": "Frontdesk", "uidt": "SingleLineText"},
    {"column_name": "frontdesk_tg_id", "title": "Frontdesk TG ID", "uidt": "Number"},
    {"column_name": "maintenance_name", "title": "Maintenance By", "uidt": "SingleLineText"},
    {"column_name": "maintenance_id", "title": "Maintenance TG ID", "uidt": "Number"},
    {"column_name": "handoff_at", "title": "Handoff At", "uidt": "DateTime"},
    {"column_name": "handoff_note", "title": "Handoff Note", "uidt": "LongText"},
    {"column_name": "last_contact", "title": "Last Contact", "uidt": "DateTime"},
    {"column_name": "followup_count", "title": "Followups", "uidt": "Number"},
    {"column_name": "deposit_total", "title": "Total Deposits", "uidt": "Decimal"},
    {"column_name": "deposit_count", "title": "Deposit Count", "uidt": "Number"},
])

tables["client_notes"] = create_table("Client Notes", [
    {"column_name": "client_phone", "title": "Client Phone", "uidt": "PhoneNumber", "pv": True},
    {"column_name": "note", "title": "Note", "uidt": "LongText"},
    {"column_name": "author_name", "title": "Author", "uidt": "SingleLineText"},
    {"column_name": "author_tg_id", "title": "Author TG ID", "uidt": "Number"},
    {"column_name": "note_type", "title": "Type", "uidt": "SingleSelect", "dtxp": "'general','followup','handoff','deposit','status_change'"},
])

tables["daily_stats"] = create_table("Daily Stats", [
    {"column_name": "date", "title": "Date", "uidt": "Date", "pv": True},
    {"column_name": "frontdesk_name", "title": "Frontdesk", "uidt": "SingleLineText"},
    {"column_name": "frontdesk_tg_id", "title": "Frontdesk TG ID", "uidt": "Number"},
    {"column_name": "new_clients", "title": "New", "uidt": "Number"},
    {"column_name": "contacted", "title": "Contacted", "uidt": "Number"},
    {"column_name": "replied", "title": "Replied", "uidt": "Number"},
    {"column_name": "registered", "title": "Registered", "uidt": "Number"},
    {"column_name": "training", "title": "Training", "uidt": "Number"},
    {"column_name": "withdrew", "title": "Withdrew", "uidt": "Number"},
    {"column_name": "ordered", "title": "Ordered", "uidt": "Number"},
    {"column_name": "reply_rate", "title": "Reply Rate %", "uidt": "Decimal"},
    {"column_name": "conversion_rate", "title": "Conversion %", "uidt": "Decimal"},
])

tables["deposits"] = create_table("Deposits", [
    {"column_name": "client_phone", "title": "Client Phone", "uidt": "PhoneNumber", "pv": True},
    {"column_name": "amount", "title": "Amount", "uidt": "Decimal"},
    {"column_name": "tier", "title": "Tier", "uidt": "SingleSelect", "dtxp": "'一刀','二刀','三刀','四刀','五刀','六刀','七刀','八刀'"},
    {"column_name": "platform", "title": "Platform", "uidt": "SingleLineText"},
    {"column_name": "frontdesk_name", "title": "Frontdesk", "uidt": "SingleLineText"},
    {"column_name": "maintenance_name", "title": "Maintenance By", "uidt": "SingleLineText"},
    {"column_name": "deposited_at", "title": "Deposited At", "uidt": "DateTime"},
    {"column_name": "verified", "title": "Verified", "uidt": "Checkbox"},
])

tables["reminders"] = create_table("Reminders", [
    {"column_name": "staff_name", "title": "Staff", "uidt": "SingleLineText", "pv": True},
    {"column_name": "staff_tg_id", "title": "Staff TG ID", "uidt": "Number"},
    {"column_name": "client_phone", "title": "Client Phone", "uidt": "PhoneNumber"},
    {"column_name": "message", "title": "Message", "uidt": "LongText"},
    {"column_name": "remind_at", "title": "Remind At", "uidt": "DateTime"},
    {"column_name": "is_sent", "title": "Sent", "uidt": "Checkbox"},
    {"column_name": "reminder_type", "title": "Type", "uidt": "SingleSelect", "dtxp": "'manual','auto_followup','auto_stale'"},
])

tables["team_targets"] = create_table("Team Targets", [
    {"column_name": "month", "title": "Month", "uidt": "SingleLineText", "pv": True},
    {"column_name": "team", "title": "Team", "uidt": "SingleSelect", "dtxp": "'阿俊组','何军组','all'"},
    {"column_name": "target_new", "title": "Target: New", "uidt": "Number"},
    {"column_name": "target_registered", "title": "Target: Registered", "uidt": "Number"},
    {"column_name": "target_ordered", "title": "Target: Ordered", "uidt": "Number"},
    {"column_name": "target_deposits", "title": "Target: Deposits", "uidt": "Decimal"},
])

print(f"\n🎉 Done!")
config = {
    "url": NOCODB_URL,
    "api_token": "l3Q8t5BYkLnrgz4hgFnYkl3C_ij-teaMy3UfiRx2",
    "base_id": BASE_ID,
    "tables": {k: v["id"] if v else None for k, v in tables.items()}
}
with open("nocodb_config.json", "w") as f:
    json.dump(config, f, indent=2)
print("💾 Saved nocodb_config.json")

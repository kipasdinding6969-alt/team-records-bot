"""
Phase 2: Enable forum mode and create topics in already-created supergroups.
Uses the correct Telethon API signatures.
"""
import asyncio
import json
import os
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.functions.channels import ToggleForumRequest
from telethon.tl.functions.messages import CreateForumTopicRequest

API_ID = int(os.getenv("API_ID", "32326218"))
API_HASH = os.getenv("API_HASH", "2f44dfd151f291c8a4ec5c405eb51e94")
SESSION = os.getenv("SESSION_NAME", "team_records_bot")
RATE_DELAY = 3

# Load group IDs from phase 1
with open("team_structure.json", "r") as f:
    structure = json.load(f)

# Topic definitions per group
FORUM_TOPICS = {
    "quanxian": [
        {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
        {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
        {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
        {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
        {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
    ],
    "ajun": [
        {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
        {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
        {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
        {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
        {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
    ],
    "hejun": [
        {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
        {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
        {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
        {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
        {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
    ],
    "chaoqun": [
        {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
        {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
        {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
        {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
        {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
        {"name": "📈 战报 Battle Reports", "icon_color": 0xFB6F5F},
    ],
    "management": [
        {"name": "📊 总报表 Summary", "icon_color": 0x6FB9F0},
        {"name": "💰 财务 Finance", "icon_color": 0xFFD67E},
        {"name": "🔑 决策 Decisions", "icon_color": 0xCB86DB},
        {"name": "📋 会议 Meetings", "icon_color": 0x8EEE98},
        {"name": "🚨 紧急 Urgent", "icon_color": 0xFB6F5F},
    ],
}


async def main():
    print("=" * 60)
    print("🏗️  Phase 2: Enable Forums + Create Topics")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"👤 Logged in as: {me.first_name} (@{me.username})\n")

    for group_id, topics in FORUM_TOPICS.items():
        info = structure.get(group_id)
        if not info:
            print(f"⚠️ {group_id} not found in team_structure.json, skipping")
            continue

        chat_id = info["chat_id"]
        title = info["title"]
        print(f"\n{'─' * 50}")
        print(f"📁 {title} (ID: {chat_id})")
        print(f"{'─' * 50}")

        # Get entity
        try:
            entity = await client.get_entity(chat_id)
        except Exception as e:
            print(f"  ❌ Can't get entity: {e}")
            continue

        # Enable forum mode
        try:
            await client(ToggleForumRequest(channel=entity, enabled=True, tabs=True))
            print(f"  ✅ Forum mode enabled")
            await asyncio.sleep(RATE_DELAY)
        except Exception as e:
            if "FORUM_ENABLED" in str(e) or "already" in str(e).lower():
                print(f"  ✅ Forum already enabled")
            else:
                print(f"  ⚠️ Forum toggle: {e}")
                continue

        # Create topics
        topic_ids = {}
        for topic in topics:
            try:
                result = await client(CreateForumTopicRequest(
                    peer=entity,
                    title=topic["name"],
                    icon_color=topic.get("icon_color", 0x6FB9F0),
                ))
                # Extract topic ID from updates
                topic_id = None
                for update in result.updates:
                    if hasattr(update, 'message') and hasattr(update.message, 'id'):
                        topic_id = update.message.id
                        break
                    if hasattr(update, 'id'):
                        topic_id = update.id
                        break
                
                topic_ids[topic["name"]] = topic_id
                print(f"    📌 {topic['name']} → ID: {topic_id}")
                await asyncio.sleep(RATE_DELAY)
            except Exception as e:
                print(f"    ❌ {topic['name']}: {e}")
                topic_ids[topic["name"]] = None

        # Update structure
        structure[group_id]["topics"] = topic_ids

    # Save updated structure
    with open("team_structure.json", "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Updated team_structure.json with topic IDs")

    # Generate .env update
    print(f"\n{'=' * 60}")
    print("📝 Updated .env values:")
    print(f"{'=' * 60}")
    
    env_lines = []
    for group_id, info in structure.items():
        if info.get("type") == "channel":
            continue
        topics = info.get("topics", {})
        for topic_name, topic_id in topics.items():
            if topic_id and "日报" in topic_name:
                key = group_id.upper()
                env_lines.append(f"TEAM_{key}_DAILY_TOPIC={topic_id}")
            if topic_id and "通知" in topic_name:
                key = group_id.upper()
                env_lines.append(f"TEAM_{key}_NOTICE_TOPIC={topic_id}")
            if topic_id and "总报表" in topic_name:
                env_lines.append(f"MANAGEMENT_SUMMARY_TOPIC={topic_id}")
            if topic_id and "财务" in topic_name:
                env_lines.append(f"MANAGEMENT_FINANCE_TOPIC={topic_id}")
            if topic_id and "紧急" in topic_name:
                env_lines.append(f"MANAGEMENT_URGENT_TOPIC={topic_id}")
    
    for line in env_lines:
        print(f"  {line}")

    await client.disconnect()
    print(f"\n🎉 Phase 2 complete!")


if __name__ == "__main__":
    asyncio.run(main())

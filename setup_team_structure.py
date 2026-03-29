"""
QianHub Team Structure Builder
================================
Creates the full Telegram infrastructure using the USER session (Telethon MTProto).

Architecture (improved from flat groups):
- 1 Broadcast Channel (总频道) — read-only announcements
- 4 Forum Supergroups (per team) — with organized topics
- 1 Management Forum (管理层) — leadership only  
- 1 Customer Service Group (客服中心) — fast support chat

Why Forum Supergroups > Flat Groups:
- Topics = organized threads (日报, 讨论, 问题, 任务)
- Bot posts to specific topics, no message flooding
- One group per team instead of N scattered chats
- Members see only relevant discussions
- Full message history, searchable per topic
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    InviteToChannelRequest,
    EditAdminRequest,
    ToggleForumRequest,
)
from telethon.tl.functions.messages import CreateForumTopicRequest
from telethon.tl.types import ChatAdminRights

# ─── Config ───────────────────────────────────────────────────────────
API_ID = int(os.getenv("API_ID", "32326218"))
API_HASH = os.getenv("API_HASH", "2f44dfd151f291c8a4ec5c405eb51e94")
SESSION = os.getenv("SESSION_NAME", "team_records_bot")
BOT_USERNAME = os.getenv("BOT_USERNAME", "qianhub_records_bot")

# Rate limit: Telegram allows ~20 requests/minute for group creation
RATE_DELAY = 3  # seconds between API calls

# ─── Team Definitions ─────────────────────────────────────────────────
TEAMS = [
    {
        "id": "quanxian",
        "title": "🏢 全线小组 | 阿毛",
        "about": "全线小组 — 组长：阿毛 | QianHub Team Records",
        "leader": "阿毛",
        "members": ["TINO", "KUYA"],
        "support": ["客服阿毛", "小白Dyson"],
        "type": "forum",
        "topics": [
            {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
            {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
            {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
            {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
            {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
        ],
    },
    {
        "id": "ajun",
        "title": "🏢 阿俊小组 | 前台",
        "about": "阿俊小组 — 前台团队 | QianHub Team Records",
        "leader": "阿俊",
        "members": ["阿YIM", "ODDY", "燕燕", "MEYMEY"],
        "support": ["客服阿毛", "小白Dyson"],
        "type": "forum",
        "topics": [
            {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
            {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
            {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
            {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
            {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
        ],
    },
    {
        "id": "hejun",
        "title": "🏢 何军小组 | 前台",
        "about": "何军小组 — 前台团队 | QianHub Team Records",
        "leader": "何军",
        "members": ["大杰", "阿勇", "小龙", "小宏"],
        "support": ["客服阿毛", "小白Dyson"],
        "type": "forum",
        "topics": [
            {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
            {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
            {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
            {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
            {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
        ],
    },
    {
        "id": "chaoqun",
        "title": "🔥 炒群小组 | Juan Juan",
        "about": "炒群小组 — 组长：Juan Juan | QianHub Team Records",
        "leader": "Juan Juan",
        "members": ["阿YIM", "ODDY", "燕燕", "MEYMEY", "大杰", "阿勇", "小龙", "小宏"],
        "support": ["客服阿毛", "小白Dyson"],
        "type": "forum",
        "topics": [
            {"name": "📊 日报 Daily Reports", "icon_color": 0x6FB9F0},
            {"name": "💬 讨论 Discussion", "icon_color": 0xFFD67E},
            {"name": "❓ 问题 Issues", "icon_color": 0xCB86DB},
            {"name": "📋 任务 Tasks", "icon_color": 0x8EEE98},
            {"name": "🔔 通知 Notices", "icon_color": 0xFF93B2},
            {"name": "📈 战报 Battle Reports", "icon_color": 0xFB6F5F},
        ],
    },
]

MANAGEMENT = {
    "id": "management",
    "title": "🎯 管理层 | QianHub",
    "about": "管理层专用 — 组长会议/财务/决策 | QianHub Leadership",
    "type": "forum",
    "topics": [
        {"name": "📊 总报表 Summary", "icon_color": 0x6FB9F0},
        {"name": "💰 财务 Finance", "icon_color": 0xFFD67E},
        {"name": "🔑 决策 Decisions", "icon_color": 0xCB86DB},
        {"name": "📋 会议 Meetings", "icon_color": 0x8EEE98},
        {"name": "🚨 紧急 Urgent", "icon_color": 0xFB6F5F},
    ],
}

CUSTOMER_SERVICE = {
    "id": "kefu",
    "title": "🛎️ 客服中心 | QianHub",
    "about": "客服支持中心 — 快速响应 | QianHub Support",
    "type": "supergroup",  # No forum — fast chat
}

BROADCAST_CHANNEL = {
    "id": "broadcast",
    "title": "📢 QianHub 总频道",
    "about": "QianHub 全员广播频道 — 日报汇总/公告/系统通知\nAll-hands broadcast: daily summaries, announcements, system alerts",
    "type": "channel",
}

# Bot admin rights for forum supergroups
BOT_FORUM_RIGHTS = ChatAdminRights(
    post_messages=True,
    edit_messages=True,
    delete_messages=True,
    ban_users=False,
    invite_users=True,
    pin_messages=True,
    add_admins=False,
    manage_call=False,
    manage_topics=True,  # Critical: bot needs this for forum topics
)

# Bot admin rights for broadcast channel
BOT_CHANNEL_RIGHTS = ChatAdminRights(
    post_messages=True,
    edit_messages=True,
    delete_messages=False,
    ban_users=False,
    invite_users=False,
    pin_messages=True,
    add_admins=False,
    manage_call=False,
)


async def rate_limit():
    """Respect Telegram rate limits."""
    await asyncio.sleep(RATE_DELAY)


async def create_channel(client, title, about, broadcast=False):
    """Create a channel or supergroup."""
    result = await client(CreateChannelRequest(
        title=title,
        about=about,
        megagroup=not broadcast,
        broadcast=broadcast,
    ))
    channel = result.chats[0]
    chat_id = int(f"-100{channel.id}")
    print(f"  ✅ Created: {title} (ID: {chat_id})")
    await rate_limit()
    return channel, chat_id


async def enable_forum(client, channel):
    """Convert supergroup to forum mode."""
    try:
        await client(ToggleForumRequest(channel=channel, enabled=True))
        print(f"  ✅ Forum mode enabled")
        await rate_limit()
    except Exception as e:
        print(f"  ⚠️ Forum toggle: {e}")


async def create_topics(client, channel, topics):
    """Create forum topics in a supergroup."""
    topic_ids = {}
    for topic in topics:
        try:
            result = await client(CreateForumTopicRequest(
                channel=channel,
                title=topic["name"],
                icon_color=topic.get("icon_color", 0x6FB9F0),
            ))
            topic_id = result.updates[1].message.id if result.updates else None
            topic_ids[topic["name"]] = topic_id
            print(f"    📌 Topic: {topic['name']} (ID: {topic_id})")
            await rate_limit()
        except Exception as e:
            print(f"    ⚠️ Topic {topic['name']}: {e}")
            topic_ids[topic["name"]] = None
    return topic_ids


async def add_bot_admin(client, channel, bot_username, rights, rank="QianHub Bot"):
    """Add bot to channel/group as admin."""
    try:
        bot_entity = await client.get_entity(f"@{bot_username}")
        await client(InviteToChannelRequest(channel, [bot_entity]))
        await rate_limit()
        await client(EditAdminRequest(channel, bot_entity, rights, rank=rank))
        print(f"  ✅ @{bot_username} added as admin ({rank})")
        await rate_limit()
    except Exception as e:
        print(f"  ⚠️ Bot admin: {e}")


async def main():
    """Build the entire team structure."""
    print("=" * 60)
    print("🏗️  QianHub Team Structure Builder")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    
    me = await client.get_me()
    print(f"\n👤 Logged in as: {me.first_name} (@{me.username})")
    
    results = {}
    
    # ─── 1. Broadcast Channel ────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print("📢 STEP 1: Creating Broadcast Channel")
    print(f"{'─' * 50}")
    
    bc = BROADCAST_CHANNEL
    channel, chat_id = await create_channel(client, bc["title"], bc["about"], broadcast=True)
    await add_bot_admin(client, channel, BOT_USERNAME, BOT_CHANNEL_RIGHTS, rank="Broadcast Bot")
    results[bc["id"]] = {
        "title": bc["title"],
        "chat_id": chat_id,
        "type": "channel",
    }
    
    # ─── 2. Team Forum Supergroups ───────────────────────────────────
    print(f"\n{'─' * 50}")
    print("🏢 STEP 2: Creating Team Forum Supergroups")
    print(f"{'─' * 50}")
    
    for team in TEAMS:
        print(f"\n  📁 {team['title']}")
        channel, chat_id = await create_channel(client, team["title"], team["about"])
        await enable_forum(client, channel)
        topic_ids = await create_topics(client, channel, team["topics"])
        await add_bot_admin(client, channel, BOT_USERNAME, BOT_FORUM_RIGHTS, rank="Records Bot")
        
        results[team["id"]] = {
            "title": team["title"],
            "chat_id": chat_id,
            "type": "forum",
            "leader": team["leader"],
            "members": team["members"],
            "support": team["support"],
            "topics": topic_ids,
        }
    
    # ─── 3. Management Forum ─────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print("🎯 STEP 3: Creating Management Forum")
    print(f"{'─' * 50}")
    
    mg = MANAGEMENT
    channel, chat_id = await create_channel(client, mg["title"], mg["about"])
    await enable_forum(client, channel)
    topic_ids = await create_topics(client, channel, mg["topics"])
    await add_bot_admin(client, channel, BOT_USERNAME, BOT_FORUM_RIGHTS, rank="Dashboard Bot")
    results[mg["id"]] = {
        "title": mg["title"],
        "chat_id": chat_id,
        "type": "forum",
        "topics": topic_ids,
    }
    
    # ─── 4. Customer Service Group ───────────────────────────────────
    print(f"\n{'─' * 50}")
    print("🛎️ STEP 4: Creating Customer Service Group")
    print(f"{'─' * 50}")
    
    cs = CUSTOMER_SERVICE
    channel, chat_id = await create_channel(client, cs["title"], cs["about"])
    await add_bot_admin(client, channel, BOT_USERNAME, BOT_FORUM_RIGHTS, rank="Support Bot")
    results[cs["id"]] = {
        "title": cs["title"],
        "chat_id": chat_id,
        "type": "supergroup",
    }
    
    # ─── 5. Save Results ─────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print("💾 STEP 5: Saving Configuration")
    print(f"{'─' * 50}")
    
    # Save full config
    config_path = "team_structure.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  ✅ Saved: {config_path}")
    
    # Generate .env additions
    env_lines = [
        "\n# ─── Team Structure (auto-generated) ───",
        f"BROADCAST_CHANNEL_ID={results['broadcast']['chat_id']}",
    ]
    for team in TEAMS:
        key = team["id"].upper()
        env_lines.append(f"TEAM_{key}_CHAT_ID={results[team['id']]['chat_id']}")
        # Add topic IDs for daily reports
        topics = results[team["id"]].get("topics", {})
        for topic_name, topic_id in topics.items():
            if "日报" in topic_name:
                env_lines.append(f"TEAM_{key}_DAILY_TOPIC={topic_id}")
            elif "通知" in topic_name:
                env_lines.append(f"TEAM_{key}_NOTICE_TOPIC={topic_id}")
    
    env_lines.append(f"MANAGEMENT_CHAT_ID={results['management']['chat_id']}")
    mgmt_topics = results["management"].get("topics", {})
    for topic_name, topic_id in mgmt_topics.items():
        if "总报表" in topic_name:
            env_lines.append(f"MANAGEMENT_SUMMARY_TOPIC={topic_id}")
        elif "财务" in topic_name:
            env_lines.append(f"MANAGEMENT_FINANCE_TOPIC={topic_id}")
        elif "紧急" in topic_name:
            env_lines.append(f"MANAGEMENT_URGENT_TOPIC={topic_id}")
    
    env_lines.append(f"KEFU_CHAT_ID={results['kefu']['chat_id']}")
    
    env_text = "\n".join(env_lines) + "\n"
    
    # Append to .env
    with open(".env", "a") as f:
        f.write(env_text)
    print(f"  ✅ Appended to .env")
    
    # Print summary
    print(f"\n{'=' * 60}")
    print("🎉 COMPLETE — Team Structure Created!")
    print(f"{'=' * 60}")
    print(f"\n📢 Broadcast Channel: {results['broadcast']['chat_id']}")
    for team in TEAMS:
        r = results[team["id"]]
        print(f"🏢 {r['title']}: {r['chat_id']} ({len(r.get('topics', {}))} topics)")
    print(f"🎯 Management: {results['management']['chat_id']} ({len(results['management'].get('topics', {}))} topics)")
    print(f"🛎️ Customer Service: {results['kefu']['chat_id']}")
    
    print(f"\n📝 .env additions:")
    print(env_text)
    
    print(f"\n⚠️  NEXT STEPS:")
    print(f"  1. Add team members manually (they need Telegram accounts)")
    print(f"  2. Set group invite links for each team")
    print(f"  3. Update bot config to route reports to correct topics")
    print(f"  4. Test bot posting to each forum topic")
    
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

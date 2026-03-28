"""Create reporting channel and add bot as admin."""
import asyncio
import socks
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest, EditAdminRequest
from telethon.tl.types import ChatAdminRights

API_ID = 32326218
API_HASH = "2f44dfd151f291c8a4ec5c405eb51e94"
SESSION = "team_records_bot"
PROXY = (socks.SOCKS5, "127.0.0.1", 9050)
BOT_USERNAME = "qianhub_records_bot"

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH, proxy=PROXY)
    await client.start()
    
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username})")
    
    # Create supergroup for team reports
    print("\n--- Creating supergroup ---")
    result = await client(CreateChannelRequest(
        title="📊 Team Records Reports",
        about="Automated team performance reports every 3 hours during working hours (10:00-22:00 Paris time)",
        megagroup=True  # supergroup, not channel
    ))
    
    channel = result.chats[0]
    channel_id = channel.id
    # For supergroups, the actual chat_id is -100 + channel_id
    chat_id = int(f"-100{channel_id}")
    
    print(f"Created: {channel.title}")
    print(f"Channel ID: {channel_id}")
    print(f"Chat ID for bot: {chat_id}")
    
    # Add bot as admin
    print(f"\n--- Adding @{BOT_USERNAME} as admin ---")
    bot_entity = await client.get_entity(f"@{BOT_USERNAME}")
    
    admin_rights = ChatAdminRights(
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        ban_users=False,
        invite_users=True,
        pin_messages=True,
        add_admins=False,
        manage_call=False,
    )
    
    await client(InviteToChannelRequest(channel, [bot_entity]))
    await client(EditAdminRequest(channel, bot_entity, admin_rights, rank="Reports Bot"))
    
    print(f"✅ @{BOT_USERNAME} added as admin")
    print(f"\n📝 Add to .env: REPORT_CHANNEL_ID={chat_id}")
    
    # Save
    with open("channel_id.txt", "w") as f:
        f.write(str(chat_id))
    
    await client.disconnect()

asyncio.run(main())
